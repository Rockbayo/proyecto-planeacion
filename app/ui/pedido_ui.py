import streamlit as st
import pandas as pd
import os
from datetime import date, timedelta
import io
from app.models.models import Variedad
from app.services.forecast_service import calcular_curvas_dinamicas, generar_forecast_13wk, isocalendar_to_string
from app.services.mva_service import generar_plan_mva, proyectar_cosecha_desde_mva, combinar_proyecciones_52_semanas
from app.services.alertas_service import obtener_alertas_sop
from app.services.ocupacion_service import (
    obtener_dimensiones_camas_bloques,
    resolver_bloque_tentativo,
    calcular_ocupacion_semanal_52w,
    calcular_cancelaciones_reduccion_area_s2648,
    SEMANA_CORTE_REDUCCION_AREA,
    AREA_PRODUCTIVA_ACTUAL_M2,
    AREA_PRODUCTIVA_REDUCIDA_M2
)

def get_iso_week_string(dt: date) -> str:
    y, w, _ = dt.isocalendar()
    return f"S{y}{w:02d}"

def obtener_stats_jerarquicos(db, alpha: float = None, num_ciclos: int = None):
    """
    Construye las estadísticas jerárquicas biológicas para el pedido de esquejes:
    1. Curva específica de la variedad (desde Historico_Curvas.csv con suavización calibrada por flor)
    2. Promedio ponderado por [Flor, Color]
    3. Promedio por [Flor]
    4. Promedio Global de la Finca
    """
    dyn_curves = calcular_curvas_dinamicas(alpha=alpha, num_ciclos=num_ciclos, db=db)
    vars_db = db.query(Variedad).all()
    v_map = {v.nombre.strip().lower(): (v.flor.strip(), v.color.strip()) for v in vars_db}
    
    curve_records = []
    for var_name, stats in dyn_curves.items():
        sc = sum(stats.get(f'c{i}', 0) for i in range(1, 16))
        if sc <= 0:
            sc = stats.get('aprov', 0)
        dia_pico = stats.get('dia_pico', 90)
        flor, color = v_map.get(var_name.strip().lower(), ('Unknown', 'Unknown'))
        
        curve_records.append({
            'var_norm': var_name.strip().lower(),
            'flor': flor,
            'flor_norm': flor.strip().lower(),
            'color': color,
            'color_norm': color.strip().lower(),
            'aprov': sc,
            'dia_pico': dia_pico
        })
        
    df_c = pd.DataFrame(curve_records)
    
    fc_stats = {}
    if not df_c.empty and 'flor_norm' in df_c.columns:
        fc_stats = df_c.groupby(['flor_norm', 'color_norm']).agg(
            aprov=('aprov', 'mean'),
            dia_pico=('dia_pico', lambda x: int(round(x.mean())))
        ).to_dict('index')
        
    f_stats = {}
    if not df_c.empty and 'flor_norm' in df_c.columns:
        f_stats = df_c.groupby('flor_norm').agg(
            aprov=('aprov', 'mean'),
            dia_pico=('dia_pico', lambda x: int(round(x.mean())))
        ).to_dict('index')
        
    global_aprov = df_c['aprov'].mean() if not df_c.empty else 0.808
    global_dia_pico = int(round(df_c['dia_pico'].mean())) if not df_c.empty else 93
    global_stats = {
        'aprov': global_aprov,
        'dia_pico': global_dia_pico
    }
    
    dyn_lower = {k.strip().lower(): v for k, v in dyn_curves.items()}
    
    return dyn_curves, dyn_lower, fc_stats, f_stats, global_stats

def resolver_curva_variedad(variedad: str, flor: str, color: str, dyn_lower: dict, fc_stats: dict, f_stats: dict, global_stats: dict):
    v_norm = str(variedad).strip().lower()
    fl_norm = str(flor).strip().lower()
    col_norm = str(color).strip().lower()
    
    if v_norm in dyn_lower:
        v_data = dyn_lower[v_norm]
        sc = sum(v_data.get(f'c{i}', 0) for i in range(1, 16))
        if sc <= 0:
            sc = v_data.get('aprov', 0)
        if sc > 0:
            dp = v_data.get('dia_pico', 90)
            return sc, dp, 'Curva Histórica Real'
            
    if (fl_norm, col_norm) in fc_stats:
        s = fc_stats[(fl_norm, col_norm)]
        return s['aprov'], s['dia_pico'], f'Promedio Flor-Color ({flor} - {color})'
        
    if fl_norm in f_stats:
        s = f_stats[fl_norm]
        return s['aprov'], s['dia_pico'], f'Promedio Tipo de Flor ({flor})'
        
    return global_stats['aprov'], global_stats['dia_pico'], 'Promedio Global Finca'

def obtener_forecast_52w_completo(db):
    """
    Obtiene la matriz de pronóstico consolidada de cosecha para las 52 semanas:
    Inventario Vivo en Campo + Proyección MVA (Pedido Consolidado Maestro).
    Esto asegura que no haya semanas con ForeCast en 0 artificialmente.
    """
    from app.services.calibracion_service import cargar_parametros_calibrados
    params_cal = cargar_parametros_calibrados()
    alpha_cal = params_cal.get('alpha', 1.0)
    ciclos_cal = params_cal.get('num_ciclos', 9)
    df_fc_vivo = generar_forecast_13wk(db, alpha=alpha_cal, num_ciclos=ciclos_cal)
    file_master = "PedidoConsolidado_master.xlsx"
    if os.path.exists(file_master):
        try:
            df_mrp = generar_plan_mva(file_master, week_is="Pedido")
            df_proy_mva = proyectar_cosecha_desde_mva(df_mrp, db)
            df_fc_total = combinar_proyecciones_52_semanas(df_fc_vivo, df_proy_mva)
            return df_fc_total
        except Exception:
            return df_fc_vivo
    return df_fc_vivo

def exportar_matriz_estandar_erp(
    df_records: pd.DataFrame, 
    col_semana: str = 'Semana_Pedido', 
    col_valor: str = 'Esquejes',
    preservar_historico_master: bool = False,
    master_file: str = "PedidoConsolidado_master.xlsx"
) -> bytes:
    """
    Genera un archivo Excel exactamente con la estructura estándar requerida por la plataforma ERP:
    - Hoja única: 'Hoja1'
    - Columnas: 'Flor', 'Color', 'Variedad', seguidas de las semanas 'S{YYYYWW}'
    - Sin encabezados adicionales, comentarios ni columnas auxiliares.
    - Si preservar_historico_master=True, rescata las semanas históricas existentes en el maestro previo.
    """
    if df_records.empty and not (preservar_historico_master and os.path.exists(master_file)):
        df_empty = pd.DataFrame(columns=['Flor', 'Color', 'Variedad'])
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            df_empty.to_excel(writer, sheet_name='Hoja1', index=False)
        return out.getvalue()
        
    df_rec = df_records.copy()
    if not df_rec.empty:
        df_rec[col_semana] = df_rec[col_semana].astype(str).str.strip().str.replace('.0', '')
        df_rec[col_semana] = df_rec[col_semana].apply(lambda x: x if x.startswith('S') else f"S{x}")
        df_pivot = df_rec.groupby(['Flor', 'Color', 'Variedad', col_semana])[col_valor].sum().unstack(fill_value=0).reset_index()
        semanas_nuevas = sorted([c for c in df_pivot.columns if str(c).startswith('S')])
        df_pivot.columns.name = None
    else:
        df_pivot = pd.DataFrame(columns=['Flor', 'Color', 'Variedad'])
        semanas_nuevas = []

    if preservar_historico_master and os.path.exists(master_file):
        try:
            df_m = pd.read_excel(master_file)
            if 'Variedad' in df_m.columns:
                df_m = df_m.dropna(subset=['Variedad'])
                df_m = df_m[~df_m['Variedad'].astype(str).str.strip().str.lower().isin(['nan', 'total', 'none', '', 'null', '0'])]
            ren_m = {c: f"S{str(c).replace('.0', '')}" for c in df_m.columns if str(c).startswith('202') and len(str(c).replace('.0', '')) == 6}
            if ren_m:
                df_m = df_m.rename(columns=ren_m)

            semanas_m = sorted([c for c in df_m.columns if str(c).startswith('S202')])
            semanas_hist = [s for s in semanas_m if s not in semanas_nuevas]

            if semanas_hist:
                df_m_sub = df_m[['Flor', 'Color', 'Variedad'] + semanas_hist].copy()
                for c in ['Flor', 'Color', 'Variedad']:
                    df_m_sub[c] = df_m_sub[c].astype(str).str.strip()
                    if c in df_pivot.columns:
                        df_pivot[c] = df_pivot[c].astype(str).str.strip()

                df_merged = pd.merge(df_m_sub, df_pivot, on=['Flor', 'Color', 'Variedad'], how='outer')
                all_semanas = sorted(list(set(semanas_hist + semanas_nuevas)))
                for s in all_semanas:
                    if s not in df_merged.columns:
                        df_merged[s] = 0.0
                    else:
                        df_merged[s] = pd.to_numeric(df_merged[s], errors='coerce').fillna(0)

                df_pivot = df_merged[['Flor', 'Color', 'Variedad'] + all_semanas].sort_values(['Flor', 'Color', 'Variedad']).reset_index(drop=True)
            else:
                if semanas_nuevas:
                    df_pivot = df_pivot[['Flor', 'Color', 'Variedad'] + semanas_nuevas]
        except Exception:
            if semanas_nuevas:
                df_pivot = df_pivot[['Flor', 'Color', 'Variedad'] + semanas_nuevas]
    else:
        if semanas_nuevas:
            df_pivot = df_pivot[['Flor', 'Color', 'Variedad'] + semanas_nuevas]
    
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
        df_pivot.to_excel(writer, sheet_name='Hoja1', index=False)
    return out.getvalue()

def render_pedido_module(db):
    st.header("🌱 Pedido de Material Vegetal (S&OP Propagación)")
    st.markdown("""
    Cálculo maestro del requerimiento de esquejes para propagación y proveedores.
    - Se aplica un **5% adicional de seguridad** sobre la capacidad aprobada.
    - Se redondea en camas físicas estándar de **5,200 esquejes**.
    - El pedido se programa **4 semanas antes de la siembra**.
    """)

    # Gobernanza S&OP
    alertas = obtener_alertas_sop()
    regla_ped = alertas.get("regla_pedido", {})
    with st.container(border=True):
        st.markdown(f"**{regla_ped.get('icono', '📦')} {regla_ped.get('titulo', '3. Pedido Material Vegetal')}** — *{regla_ped.get('deadline', '1ª Semana de cada mes')}*")
        if regla_ped.get('activo', False):
            st.success(regla_ped.get('mensaje', 'Ventana activa para pedido mensual regular.'))
        else:
            st.info(f"{regla_ped.get('mensaje', '')} Para pedidos fuera de ventana regular, contingencias o cancelaciones, use las pestañas correspondientes.")

    plan_file_path = "Plan_Aprobado.csv"
    if not os.path.exists(plan_file_path):
        st.warning("⚠️ No se encontró ningún Plan Aprobado. Ve a 'Plan de Producción (MVA)', procesa el archivo de demanda y guarda una contrapropuesta.")
        return

    df_plan = pd.read_csv(plan_file_path)
    col_flor = 'Flor' if 'Flor' in df_plan.columns else 'Flower'
    col_capacidad = 'Tallos a Producir (Capacidad)' if 'Tallos a Producir (Capacidad)' in df_plan.columns else 'Suma de Tallos'
    
    if 'Variedad' not in df_plan.columns:
        st.error("❌ El Plan Aprobado actual no contiene detalle por Variedad. Por favor regenera la contrapropuesta en 'Plan de Producción'.")
        return

    # Fechas operativas clave
    hoy = date.today()
    sem_actual = get_iso_week_string(hoy)
    sem_siguiente = get_iso_week_string(hoy + timedelta(weeks=1))
    sem_firme_default = get_iso_week_string(hoy + timedelta(weeks=24))

    # Cargar estadísticas biológicas jerárquicas y catálogo maestro de variedades con parámetros calibrados por ML
    from app.services.calibracion_service import cargar_parametros_calibrados
    params_cal = cargar_parametros_calibrados()
    alpha_cal = params_cal.get('alpha', 1.0)
    ciclos_cal = params_cal.get('num_ciclos', 9)
    dyn_curves, dyn_lower, fc_stats, f_stats, global_stats = obtener_stats_jerarquicos(db, alpha=alpha_cal, num_ciclos=ciclos_cal)
    vars_db = db.query(Variedad).all()
    v_map = {v.nombre.strip().lower(): (v.flor.strip(), v.color.strip()) for v in vars_db}

    tab_firme, tab_extemporaneo, tab_cancelacion = st.tabs([
        "📦 Pedido Mensual Regular en Firme (+24 Semanas)", 
        "🚨 Pedidos Extemporáneos Reactivos (< 24 Semanas)",
        "❌ Cancelación de Material Vegetal (Excedentes > 5%)"
    ])

    # =========================================================================
    # TAB 1: PEDIDO REGULAR EN FIRME (+24 SEMANAS)
    # =========================================================================
    with tab_firme:
        st.subheader("📦 Pedido Regular en Firme (+24 Semanas)")
        
        # Banner de Gobernanza S&OP - Ventana Congelada (24 Semanas)
        with st.container(border=True):
            st.markdown(f"""
            🔒 **Horizonte Congelado Inmutable (24 Semanas — S&OP Freeze Zone):**
            * **Regla Inmutable:** Las semanas entre la semana actual (**{sem_actual}**) y **{sem_firme_default}** (24 semanas) ya se encuentran comprometidas en firme y contratadas con las casas de propagación. **No pueden modificarse ni recalcularse en este ciclo regular**.
            * **Horizonte Ejecutable en Firme:** El cálculo del pedido regular aplica estrictamente a partir de **{sem_firme_default}** en adelante.
            * **Régimen de Área Reducida:** Este horizonte regular opera 100% bajo la capacidad reducida de **62,212 m²** (1,120 camas comerciales que rige desde la **Semana 2648**), calibrado dinámicamente según el bloque de destino.
            """)

        col_h1, col_h2 = st.columns([1.5, 2.5])
        with col_h1:
            sem_inicio_firme = st.text_input("Semana Inicio de Pedido Firme", value=sem_firme_default, key="sem_inicio_firme")
            if sem_inicio_firme < sem_firme_default:
                st.warning(f"⚠️ Semana inferior a la ventana de 24 semanas ({sem_firme_default}). Por gobernanza S&OP, se fuerza el inicio en {sem_firme_default}.")
                sem_inicio_firme = sem_firme_default
        with col_h2:
            st.info(f"💡 Pedidos calculados desde **{sem_inicio_firme}** en adelante. Para contingencias o excepciones justificadas (< 24 semanas), use la pestaña **Pedidos Extemporáneos**.")

        st.markdown("#### 📐 Configuración de Dimensionamiento de Camas y Material Vegetal")
        with st.container(border=True):
            col_cfg1, col_cfg2, col_cfg3 = st.columns([1.8, 1.6, 1.2])
            with col_cfg1:
                modo_dim = st.selectbox(
                    "Modo de Dimensionamiento de Camas:",
                    [
                        "🎯 Calibración por Bloque Tentativo de Destino (Recomendado)",
                        "🌐 Promedio Ponderado de Finca (62,212 m² / 1,120 Camas Post-Reducción)",
                        "📏 Estándar Fijo Anterior (5,200 Esquejes/Cama)"
                    ],
                    key="sel_modo_dim"
                )

            with col_cfg2:
                if modo_dim.startswith("🎯"):
                    sel_bloque = st.selectbox(
                        "Asignación de Bloque Tentativo:",
                        [
                            "🔄 Rotación Dinámica según Disponibilidad (Auto)",
                            "Bloque 01 (240 Camas hoy / 224 Camas post-red)",
                            "Bloque 02 (160 Camas hoy / 144 Camas post-red)",
                            "Bloque 03 (184 Camas hoy / 168 Camas post-red)",
                            "Bloque 04 (232 Camas - 51.8 m²)",
                            "Bloque 05 (160 Camas - 49.1 m²)",
                            "Bloque 06 (192 Camas - 48.6 m²)"
                        ],
                        key="sel_bloque_dest"
                    )
                elif modo_dim.startswith("🌐"):
                    st.text_input("Asignación de Bloque:", value="🌐 Finca Consolidada (1,120 Camas)", disabled=True)
                    sel_bloque = "FINCA"
                else:
                    st.text_input("Asignación de Bloque:", value="📏 Estándar Fijo Anterior", disabled=True)
                    sel_bloque = "STD_5200"

            with col_cfg3:
                pct_buffer_val = st.slider(
                    "% Pérdida / Margen Seguridad:",
                    min_value=3.0,
                    max_value=10.0,
                    value=5.0,
                    step=0.5,
                    help="Margen de seguridad para cubrir mermas de enraizamiento, transporte y selección, garantizando que ninguna cama quede corta de plantas.",
                    key="slider_pct_buffer"
                )

            col_sub1, col_sub2 = st.columns([2, 1])
            with col_sub1:
                base_area_sel = st.radio(
                    "Base de Área de Cama:",
                    ["Área Productiva Normalizada (62,212 m² - Recomendado)", "Área Bruta de Planos (Planos sección.csv)"],
                    horizontal=True,
                    key="radio_base_area"
                )
            with col_sub2:
                base_area_code = "productiva" if "Productiva" in base_area_sel else "bruta"
                dims_demo = obtener_dimensiones_camas_bloques(db, base_area=base_area_code, pct_buffer=pct_buffer_val)
                finca_demo = dims_demo.get("FINCA", {})
                st.caption(f"📊 **Promedio Finca:** {finca_demo.get('m2_cama', 52.98)} m²/cama → **{finca_demo.get('esquejes_cama', 4845):,} esquejes/cama** (+{pct_buffer_val}% buffer)")

            with st.expander("🔍 Ver Tabla Maestra de Calibración de Camas por Bloque", expanded=False):
                tbl_rows = []
                for b_k in ['01', '02', '03', '04', '05', '06', 'FINCA']:
                    d_b = dims_demo.get(b_k, {})
                    tbl_rows.append({
                        "Bloque": d_b.get("nombre", b_k),
                        "Camas Instaladas": d_b.get("camas", 0),
                        "m² por Cama": d_b.get("m2_cama", 0.0),
                        "Plantas Netas / Cama (87.1 pl/m²)": d_b.get("plantas_cama", 0),
                        f"Esquejes a Pedir (+{pct_buffer_val}% Buffer)": d_b.get("esquejes_cama", 0),
                        "Ajuste vs Estándar 5,200": f"{d_b.get('dif_vs_5200', 0):+d} esq/cama"
                    })
                st.dataframe(pd.DataFrame(tbl_rows), width="stretch", hide_index=True)

        if st.button("Calcular Pedido Consolidado en Firme", type="primary", key="btn_gen_pedido_firme"):
            with st.spinner("Calculando curvas dinámicas, rotación de bloques y dimensionamiento de esquejes..."):
                try:
                    records_firme = []
                    records_audit = []

                    # Cargar dimensiones físicas calibradas
                    dict_dims = obtener_dimensiones_camas_bloques(db, base_area=base_area_code, pct_buffer=pct_buffer_val)
                    
                    # Cargar ocupación de bloques para rotación automática si aplica
                    _, df_bloques_52w = calcular_ocupacion_semanal_52w(db)

                    # Determinar código de modo de bloque
                    if modo_dim.startswith("🎯"):
                        if sel_bloque.startswith("🔄"):
                            modo_bloque_cod = "AUTO"
                        else:
                            modo_bloque_cod = sel_bloque.split()[1] # '01', '02', etc.
                    elif modo_dim.startswith("🌐"):
                        modo_bloque_cod = "FINCA"
                    else:
                        modo_bloque_cod = "STD_5200"

                    for _, row in df_plan.iterrows():
                        variedad = str(row['Variedad']).strip()
                        flor_orig = str(row[col_flor]).strip()
                        color_orig = str(row['Color']).strip()
                        flor, color = v_map.get(variedad.lower(), (flor_orig, color_orig))
                        sem_cosecha_raw = str(row['Semana']).strip()
                        capacidad = pd.to_numeric(row[col_capacidad], errors='coerce')

                        if pd.isna(capacidad) or capacidad <= 0:
                            continue

                        meta_tallos = capacidad * 1.05

                        aprov, dia_pico, metodo = resolver_curva_variedad(
                            variedad, flor, color, dyn_lower, fc_stats, f_stats, global_stats
                        )

                        # Fechas y semanas operativas
                        try:
                            sem_clean = str(sem_cosecha_raw).split('.')[0].strip()
                            year = int(sem_clean[:4])
                            week = int(sem_clean[4:])
                            fecha_pico = date.fromisocalendar(year, week, 4)
                            fecha_siembra = fecha_pico - timedelta(days=dia_pico)
                            sem_siembra = isocalendar_to_string(fecha_siembra)
                            fecha_pedido = fecha_siembra - timedelta(weeks=4)
                            sem_pedido = get_iso_week_string(fecha_pedido)
                        except Exception:
                            continue

                        # Resolver dimensionamiento del bloque de destino
                        b_cod, b_info = resolver_bloque_tentativo(
                            sem_siembra=sem_siembra,
                            df_bloques_52w=df_bloques_52w,
                            modo_bloque=modo_bloque_cod,
                            dict_dimensiones=dict_dims
                        )

                        plantas_cama = b_info.get("plantas_cama", 4615)
                        esquejes_cama = b_info.get("esquejes_cama", 4845)
                        area_cama_m2 = b_info.get("m2_cama", 52.98)
                        nombre_bloque = b_info.get("nombre", f"Bloque {b_cod}")

                        plantas_teoricas = meta_tallos / aprov
                        camas = round(plantas_teoricas / float(plantas_cama))
                        if camas == 0 and plantas_teoricas > 0:
                            camas = 1

                        esquejes_pedir = camas * esquejes_cama
                        if esquejes_pedir == 0:
                            continue

                        # Comparativa vs Estándar Anterior 5,200
                        camas_5200 = max(1, round(plantas_teoricas / 5200.0))
                        esquejes_5200 = camas_5200 * 5200
                        dif_esquejes = esquejes_pedir - esquejes_5200

                        records_audit.append({
                            "Flor": flor,
                            "Color": color,
                            "Variedad": variedad,
                            "Semana_Cosecha": f"S{sem_clean}",
                            "Semana_Siembra": f"S{sem_siembra}",
                            "Semana_Pedido": sem_pedido,
                            "Bloque_Destino": nombre_bloque,
                            "Area_Cama_m2": area_cama_m2,
                            "Plantas_Cama": plantas_cama,
                            "Esquejes_Cama": esquejes_cama,
                            "Tallos_Plan": capacidad,
                            "Aprovechamiento_%": aprov * 100.0,
                            "Dia_Pico": dia_pico,
                            "Metodo_Curva": metodo,
                            "Camas": camas,
                            "Esquejes_Pedir": esquejes_pedir,
                            "Esquejes_Std_5200": esquejes_5200,
                            "Ajuste_vs_5200": dif_esquejes
                        })

                        sem_inicio_f_fmt = sem_inicio_firme if sem_inicio_firme.startswith("S") else f"S{sem_inicio_firme}"
                        if sem_pedido >= sem_inicio_f_fmt:
                            records_firme.append({
                                "Flor": flor,
                                "Color": color,
                                "Variedad": variedad,
                                "Semana_Pedido": sem_pedido,
                                "Esquejes": esquejes_pedir
                            })

                    df_ped_firme = pd.DataFrame(records_firme)
                    df_audit = pd.DataFrame(records_audit)

                    if df_ped_firme.empty:
                        st.warning(f"No se generaron pedidos para el horizonte en firme desde {sem_inicio_firme}.")
                    else:
                        st.session_state['df_pedido_firme_raw'] = df_ped_firme
                        st.session_state['df_pedido_firme_audit'] = df_audit
                        st.session_state['pedido_modo_dim'] = modo_dim
                        st.session_state['pedido_pct_buffer'] = pct_buffer_val
                        st.success("✅ Pedido Consolidado en Firme generado con calibración de material vegetal.")

                except Exception as e:
                    st.error(f"Error generando pedido en firme: {e}")

        if 'df_pedido_firme_raw' in st.session_state:
            df_raw_f = st.session_state['df_pedido_firme_raw']
            df_audit = st.session_state['df_pedido_firme_audit']

            df_pivot_f = df_raw_f.groupby(['Flor', 'Color', 'Variedad', 'Semana_Pedido'])['Esquejes'].sum().unstack(fill_value=0).reset_index()
            semanas_cols = sorted([c for c in df_pivot_f.columns if str(c).startswith('S')])
            df_pivot_f = df_pivot_f[['Flor', 'Color', 'Variedad'] + semanas_cols]
            df_pivot_f.columns.name = None

            total_esq = df_pivot_f[semanas_cols].sum().sum()
            sem_inicio_f_fmt = sem_inicio_firme if sem_inicio_firme.startswith("S") else f"S{sem_inicio_firme}"
            df_audit_firme = df_audit[df_audit['Semana_Pedido'] >= sem_inicio_f_fmt] if not df_audit.empty else df_audit
            total_cam = df_audit_firme['Camas'].sum() if 'Camas' in df_audit_firme.columns else (total_esq / 4845.0)
            prom_esq_cama = (total_esq / total_cam) if total_cam > 0 else 4845.0

            total_esq_5200 = df_audit_firme['Esquejes_Std_5200'].sum() if 'Esquejes_Std_5200' in df_audit_firme.columns else (total_cam * 5200.0)
            dif_neta = total_esq - total_esq_5200
            total_v = df_pivot_f['Variedad'].nunique()

            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Total Esquejes Firme", f"{total_esq:,.0f}")
            m2.metric("Total Camas Calibradas", f"{total_cam:,.0f} camas")
            m3.metric("Promedio Esquejes/Cama", f"{prom_esq_cama:,.0f} esq", f"vs 5,200 std")
            if dif_neta < 0:
                m4.metric("Ahorro por Sobre-Pedido", f"{abs(dif_neta):,.0f} esq", "Evita pérdidas en B05/B06", delta_color="normal")
            else:
                m4.metric("Protección Faltantes", f"+{dif_neta:,.0f} esq", "Camas grandes B01/B03 abastecidas", delta_color="normal")
            m5.metric("Variedades en Pedido", f"{total_v:,}", f"{len(semanas_cols)} semanas")

            st.dataframe(df_pivot_f, width='stretch')

            with st.expander("🔍 Auditoría Detallada: Dimensionamiento por Bloque, Curvas y Rendimientos", expanded=False):
                st.markdown("##### 📊 Distribución de Camas y Esquejes por Bloque Tentativo")
                if not df_audit_firme.empty and 'Bloque_Destino' in df_audit_firme.columns:
                    col_ab1, col_ab2 = st.columns([1.5, 2.5])
                    with col_ab1:
                        df_bloque_sum = df_audit_firme.groupby('Bloque_Destino').agg(
                            Camas=('Camas', 'sum'),
                            Esquejes=('Esquejes_Pedir', 'sum'),
                            Ahorro_vs_5200=('Ajuste_vs_5200', lambda x: -x.sum())
                        ).reset_index()
                        st.dataframe(
                            df_bloque_sum.style.format({
                                'Camas': '{:,.0f}',
                                'Esquejes': '{:,.0f}',
                                'Ahorro_vs_5200': '{:+,.0f}'
                            }),
                            width='stretch',
                            hide_index=True
                        )
                    with col_ab2:
                        metodos_resumen = df_audit_firme.groupby('Metodo_Curva')['Variedad'].nunique()
                        st.markdown("**Variedades por Origen de Curva Biológica:**")
                        for m_name, count in metodos_resumen.items():
                            st.write(f"- **{m_name}:** {count} variedades")

                st.divider()
                st.markdown("##### 📋 Detalle Fila por Fila (Auditoría Integral)")
                cols_show = ['Flor', 'Color', 'Variedad', 'Semana_Cosecha', 'Semana_Pedido', 'Bloque_Destino', 'Area_Cama_m2', 'Esquejes_Cama', 'Camas', 'Esquejes_Pedir', 'Aprovechamiento_%', 'Dia_Pico', 'Metodo_Curva']
                cols_avail = [c for c in cols_show if c in df_audit_firme.columns]
                st.dataframe(
                    df_audit_firme[cols_avail].head(200).style.format({
                        'Area_Cama_m2': '{:.1f} m²',
                        'Esquejes_Cama': '{:,.0f}',
                        'Camas': '{:.0f}',
                        'Esquejes_Pedir': '{:,.0f}',
                        'Aprovechamiento_%': '{:.1f}%',
                        'Dia_Pico': '{:.0f} d'
                    }),
                    width='stretch',
                    hide_index=True
                )

            excel_consolidado_completo = exportar_matriz_estandar_erp(
                df_raw_f, col_semana='Semana_Pedido', col_valor='Esquejes', preservar_historico_master=True
            )

            col_df1, col_df2 = st.columns(2)
            with col_df1:
                st.download_button(
                    label="📥 Descargar Pedido Consolidado (Histórico + Firme Calibrado)",
                    data=excel_consolidado_completo,
                    file_name=f"PedidoConsolidado_{date.today()}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                    width='stretch'
                )
            with col_df2:
                if st.button("💾 Guardar y Sincronizar PedidoConsolidado_master.xlsx", width='stretch'):
                    with st.spinner("Sincronizando con archivo maestro y preservando histórico..."):
                        from app.services.mva_service import sincronizar_pedido_consolidado_master
                        res_sync_firme = sincronizar_pedido_consolidado_master(df_raw_f)
                        if res_sync_firme.get("status") == "success":
                            n_act = len(res_sync_firme['semanas_actualizadas'])
                            n_hist = len(res_sync_firme['semanas_historicas_preservadas'])
                            st.success(f"✅ 'PedidoConsolidado_master.xlsx' actualizado: {n_act} semanas firmes sincronizadas preservando intactas {n_hist} semanas históricas anteriores. Los módulos de ForeCast ahora proyectarán con este archivo maestro.")
                        else:
                            st.error(f"Error sincronizando archivo maestro: {res_sync_firme.get('message', 'Desconocido')}")

    # =========================================================================
    # TAB 2: PEDIDOS EXTEMPORÁNEOS REACTIVOS (< 24 SEMANAS)
    # =========================================================================
    with tab_extemporaneo:
        st.subheader("🚨 Pedidos Extemporáneos Reactivos (< 24 Semanas)")
        
        st.warning(f"""
        ⚠️ **VENTANA FIRME (< 24 SEMANAS) — SUJETO A APROBACIÓN DE PROPAGACIÓN**
        
        * **Corte Cronológico de Capacidad:** En este momento el área de la finca es de **64,878 m²** (1,168 camas comerciales hasta Semana 2647). A partir de la **Semana 2648**, el área se reduce a **62,212 m²** (-48 camas en 6 naves: B01, B02, B03 con 2 naves c/u, -4.11%). Los análisis evalúan la capacidad real vigente de cada período.
        * **Regla de Negocio Grupo Color:** Si a nivel de `[Flor, Color]` el volumen proyectado cumple con la capacidad del Plan Aprobado, **no se adiciona material**. Se compensan variedades dentro del mismo color comercial (confirmación real de propagación).
        * **Ventana Ejecutable:** Solo se programan pedidos para semanas futuras ejecutables (desde **{sem_siguiente}** hasta **{sem_firme_default}**). No se muestran semanas pasadas ni se acumulan pedidos.
        * **Formato de Archivo:** El Excel descargado mantiene **estrictamente la estructura estándar del pedido** (`Flor | Color | Variedad | Semanas...`) sin comentarios adicionales.
        """)

        modo_ext = st.radio(
            "Método de Determinación de Pedido Extemporáneo:",
            ["⚡ Detección Automática con Compensación de Grupo Color (Plan vs. ForeCast)", "✍️ Solicitud Reactiva Ad-Hoc por Lote/Variedad"],
            horizontal=True,
            key="radio_modo_ext"
        )

        if modo_ext == "⚡ Detección Automática con Compensación de Grupo Color (Plan vs. ForeCast)":
            c_ext1, c_ext2 = st.columns([2, 1])
            with c_ext1:
                st.info(f"📅 **Ventana Ejecutable:** Analiza pedidos entre **{sem_siguiente}** y **{sem_firme_default}**, cruzando el Plan contra el ForeCast consolidado de 52 semanas.")
            with c_ext2:
                filtro_flor_ext = st.selectbox("Filtrar por Flor", ["Todas"] + sorted(list(df_plan[col_flor].dropna().unique())), key="filtro_flor_ext")

            if st.button("Analizar Brecha y Calcular Pedido Extemporáneo", type="primary", key="btn_calc_ext"):
                with st.spinner("Consolidando ForeCast 52 semanas y evaluando balance por Grupo Color..."):
                    try:
                        # 1. Obtener Forecast Consolidado de 52 semanas
                        df_fc_completo = obtener_forecast_52w_completo(db)
                        semanas_fc_cols = [c for c in df_fc_completo.columns if str(c).startswith('202')]

                        fc_melt = df_fc_completo.melt(
                            id_vars=['Flor', 'Color', 'Variedad'],
                            value_vars=semanas_fc_cols,
                            var_name='Semana',
                            value_name='Tallos_Forecast'
                        )
                        fc_melt['Variedad_Norm'] = fc_melt['Variedad'].astype(str).str.strip().str.lower()
                        fc_melt['Flor_Canon'] = fc_melt['Variedad_Norm'].map(lambda vn: v_map.get(vn, (None, None))[0])
                        fc_melt['Color_Canon'] = fc_melt['Variedad_Norm'].map(lambda vn: v_map.get(vn, (None, None))[1])
                        fc_melt['Flor'] = fc_melt['Flor_Canon'].fillna(fc_melt['Flor'])
                        fc_melt['Color'] = fc_melt['Color_Canon'].fillna(fc_melt['Color'])
                        fc_melt['Flor_Norm'] = fc_melt['Flor'].str.strip().str.lower()
                        fc_melt['Color_Norm'] = fc_melt['Color'].str.strip().str.lower()
                        fc_melt['Semana_Clean'] = fc_melt['Semana'].astype(str)

                        # 2. Plan Aprobado
                        df_plan_eval = df_plan.dropna(subset=[col_capacidad]).copy()
                        df_plan_eval = df_plan_eval[df_plan_eval[col_capacidad] > 0]
                        df_plan_eval['Semana_Clean'] = df_plan_eval['Semana'].astype(str).str.split('.').str[0].str.strip()
                        df_plan_eval['Variedad_Norm'] = df_plan_eval['Variedad'].astype(str).str.strip().str.lower()
                        df_plan_eval['Flor_Canon'] = df_plan_eval['Variedad_Norm'].map(lambda vn: v_map.get(vn, (None, None))[0])
                        df_plan_eval['Color_Canon'] = df_plan_eval['Variedad_Norm'].map(lambda vn: v_map.get(vn, (None, None))[1])
                        df_plan_eval[col_flor] = df_plan_eval['Flor_Canon'].fillna(df_plan_eval[col_flor])
                        df_plan_eval['Color'] = df_plan_eval['Color_Canon'].fillna(df_plan_eval['Color'])
                        df_plan_eval['Flor_Norm'] = df_plan_eval[col_flor].astype(str).str.strip().str.lower()
                        df_plan_eval['Color_Norm'] = df_plan_eval['Color'].astype(str).str.strip().str.lower()

                        if filtro_flor_ext != "Todas":
                            df_plan_eval = df_plan_eval[df_plan_eval[col_flor] == filtro_flor_ext]
                            fc_melt = fc_melt[fc_melt['Flor'] == filtro_flor_ext]

                        # 3. Comparación por variedad
                        var_plan = df_plan_eval.groupby(['Variedad_Norm', col_flor, 'Color', 'Variedad', 'Semana_Clean'])[col_capacidad].sum().reset_index()
                        var_fc = fc_melt.groupby(['Variedad_Norm', 'Semana_Clean'])['Tallos_Forecast'].sum().reset_index()
                        var_m = pd.merge(var_plan, var_fc, on=['Variedad_Norm', 'Semana_Clean'], how='left')
                        var_m['Tallos_Forecast'] = var_m['Tallos_Forecast'].fillna(0)
                        var_m['Flor_Norm'] = var_m[col_flor].str.strip().str.lower()
                        var_m['Color_Norm'] = var_m['Color'].str.strip().str.lower()
                        var_m['Raw_Deficit'] = (var_m[col_capacidad] - var_m['Tallos_Forecast']).clip(lower=0)

                        # 4. Balance a nivel de Grupo Color [Flor, Color, Semana]
                        gc_plan = var_m.groupby(['Flor_Norm', 'Color_Norm', 'Semana_Clean'])[col_capacidad].sum().reset_index().rename(columns={col_capacidad: 'GC_Plan'})
                        gc_fc = var_m.groupby(['Flor_Norm', 'Color_Norm', 'Semana_Clean'])['Tallos_Forecast'].sum().reset_index().rename(columns={'Tallos_Forecast': 'GC_FC'})
                        gc_raw_def = var_m.groupby(['Flor_Norm', 'Color_Norm', 'Semana_Clean'])['Raw_Deficit'].sum().reset_index().rename(columns={'Raw_Deficit': 'GC_Raw_Def_Sum'})

                        gc_info = pd.merge(gc_plan, gc_fc, on=['Flor_Norm', 'Color_Norm', 'Semana_Clean'])
                        gc_info = pd.merge(gc_info, gc_raw_def, on=['Flor_Norm', 'Color_Norm', 'Semana_Clean'])
                        gc_info['GC_Net_Deficit'] = (gc_info['GC_Plan'] - gc_info['GC_FC']).clip(lower=0)

                        df_eval = pd.merge(var_m, gc_info, on=['Flor_Norm', 'Color_Norm', 'Semana_Clean'], how='left')

                        # Distribución proporcional solo si el grupo color tiene déficit neto
                        df_eval['Net_Deficit_Var'] = 0.0
                        mask_def = (df_eval['GC_Net_Deficit'] > 50) & (df_eval['GC_Raw_Def_Sum'] > 0) & (df_eval['Raw_Deficit'] > 0)
                        df_eval.loc[mask_def, 'Net_Deficit_Var'] = df_eval.loc[mask_def, 'GC_Net_Deficit'] * (df_eval.loc[mask_def, 'Raw_Deficit'] / df_eval.loc[mask_def, 'GC_Raw_Def_Sum'])

                        ext_records = []
                        for _, r in df_eval[df_eval['Net_Deficit_Var'] > 50].iterrows():
                            v = r['Variedad']
                            fl = r[col_flor]
                            col = r['Color']
                            sem_cos = r['Semana_Clean']
                            net_def = r['Net_Deficit_Var']

                            aprov, dia_pico, metodo = resolver_curva_variedad(
                                v, fl, col, dyn_lower, fc_stats, f_stats, global_stats
                            )

                            try:
                                y = int(sem_cos[:4])
                                w = int(sem_cos[4:])
                                f_pico = date.fromisocalendar(y, w, 4)
                                f_siem = f_pico - timedelta(days=dia_pico)
                                f_ped = f_siem - timedelta(weeks=4)
                                sem_ped = get_iso_week_string(f_ped)
                            except Exception:
                                continue

                            # Filtro estricto: Solo semanas ejecutables futuras
                            if sem_siguiente <= sem_ped < sem_firme_default:
                                tallos_reponer = net_def * 1.05
                                plantas_nec = tallos_reponer / aprov
                                camas = round(plantas_nec / 5200.0)
                                if camas == 0 and plantas_nec > 0:
                                    camas = 1
                                esquejes_pedir = camas * 5200

                                ext_records.append({
                                    "Flor": fl,
                                    "Color": col,
                                    "Variedad": v,
                                    "Semana_Cosecha": f"S{sem_cos}",
                                    "Semana_Pedido": sem_ped,
                                    "Tallos_Plan": int(round(r[col_capacidad])),
                                    "Tallos_ForeCast": int(round(r['Tallos_Forecast'])),
                                    "Balance_Color_Neto": f"Déficit Color: {int(round(r['GC_Net_Deficit'])):,} tll",
                                    "Deficit_Tallos": int(round(net_def)),
                                    "Aprovechamiento_%": round(aprov * 100.0, 1),
                                    "Metodo_Curva": metodo,
                                    "Camas_5200": camas,
                                    "Esquejes": esquejes_pedir,
                                    "Motivo": "Déficit biológico neto del Grupo Color"
                                })

                        if not ext_records:
                            st.success(f"🎉 No se detectaron déficits biológicos netos a nivel de Grupo Color entre {sem_siguiente} y {sem_firme_default}. El volumen total por color está cubierto.")
                        else:
                            df_ext_result = pd.DataFrame(ext_records)
                            st.session_state['df_extemporaneo_raw'] = df_ext_result
                            st.success(f"Déficit biológico neto compensado por Grupo Color: {len(df_ext_result)} requerimientos en ventana.")

                    except Exception as e:
                        st.error(f"Error analizando pedido extemporáneo: {e}")

        else:
            # Modo B: Solicitud Ad-Hoc
            st.markdown("Ingresa una solicitud ad-hoc de pedido reactivo para suplir pérdidas en lotes específicos.")
            with st.form("form_extemporaneo_adhoc"):
                col_ad1, col_ad2, col_ad3 = st.columns(3)
                with col_ad1:
                    flores_disp = sorted(list(df_plan[col_flor].dropna().unique()))
                    flor_sel = st.selectbox("Flor", flores_disp)
                    vars_disp = sorted(list(df_plan[df_plan[col_flor] == flor_sel]['Variedad'].dropna().unique()))
                    var_sel = st.selectbox("Variedad", vars_disp)
                with col_ad2:
                    colores_disp = sorted(list(df_plan[df_plan['Variedad'] == var_sel]['Color'].dropna().unique()))
                    col_sel = colores_disp[0] if colores_disp else "Desconocido"
                    st.text_input("Color", value=col_sel, disabled=True)
                    sem_ped_adhoc = st.text_input(f"Semana de Pedido Requerida (>= {sem_siguiente})", value=sem_siguiente)
                with col_ad3:
                    camas_adhoc = st.number_input("Camas Requeridas (5,200 esquejes)", min_value=1, value=5, step=1)
                    motivo_adhoc = st.selectbox("Motivo", [
                        "Rebalanceo reactivo por reducción de área (Semana 2648 en adelante)",
                        "Compensación de mix MVA post-reducción de área",
                        "Bajo aprovechamiento biológico en curvas piloto",
                        "Pérdida fitosanitaria en campo",
                        "Problemas de prendimiento en enraizamiento",
                        "Incremento repentino de programa comercial"
                    ])

                if st.form_submit_button("Agregar a Pedido Extemporáneo", type="primary"):
                    sem_ped_clean = sem_ped_adhoc if sem_ped_adhoc.startswith("S") else f"S{sem_ped_adhoc}"
                    if sem_ped_clean < sem_siguiente:
                        st.error(f"❌ La semana de pedido debe ser igual o posterior a la semana siguiente ({sem_siguiente}). Semanas pasadas no son ejecutables.")
                    else:
                        aprov, dia_pico, metodo = resolver_curva_variedad(
                            var_sel, flor_sel, col_sel, dyn_lower, fc_stats, f_stats, global_stats
                        )
                        esquejes_tot = camas_adhoc * 5200
                        tallos_rep = int(round(esquejes_tot * aprov / 1.05))

                        nuevo_reg = {
                            "Flor": flor_sel,
                            "Color": col_sel,
                            "Variedad": var_sel,
                            "Semana_Cosecha": "Ad-Hoc",
                            "Semana_Pedido": sem_ped_clean,
                            "Tallos_Plan": tallos_rep,
                            "Tallos_ForeCast": 0,
                            "Balance_Color_Neto": "Ad-Hoc Manual",
                            "Deficit_Tallos": tallos_rep,
                            "Aprovechamiento_%": round(aprov * 100.0, 1),
                            "Metodo_Curva": metodo,
                            "Camas_5200": camas_adhoc,
                            "Esquejes": esquejes_tot,
                            "Motivo": motivo_adhoc
                        }

                        if 'df_extemporaneo_raw' not in st.session_state:
                            st.session_state['df_extemporaneo_raw'] = pd.DataFrame([nuevo_reg])
                        else:
                            st.session_state['df_extemporaneo_raw'] = pd.concat(
                                [st.session_state['df_extemporaneo_raw'], pd.DataFrame([nuevo_reg])], 
                                ignore_index=True
                            )
                        st.success(f"Solicitud extemporánea para '{var_sel}' agregada al pedido.")

        # Visualización de Pedido Extemporáneo
        if 'df_extemporaneo_raw' in st.session_state and not st.session_state['df_extemporaneo_raw'].empty:
            df_ext = st.session_state['df_extemporaneo_raw']

            st.divider()
            st.markdown("### 📋 Resumen del Pedido Extemporáneo (Salidas para Planeación)")
            
            kpi_e1, kpi_e2, kpi_e3, kpi_e4 = st.columns(4)
            tot_esq_ext = df_ext['Esquejes'].sum()
            tot_cam_ext = df_ext['Camas_5200'].sum()
            tot_def_ext = df_ext['Deficit_Tallos'].sum()
            tot_vars_ext = df_ext['Variedad'].nunique()

            kpi_e1.metric("Esquejes Extemporáneos", f"{tot_esq_ext:,.0f}")
            kpi_e2.metric("Camas Adicionales (5,200)", f"{tot_cam_ext:,.0f}")
            kpi_e3.metric("Déficit de Tallos Cubierto", f"{tot_def_ext:,.0f}")
            kpi_e4.metric("Variedades Afectadas", f"{tot_vars_ext:,}")

            # Detalle en pantalla para el equipo de planeación
            st.dataframe(
                df_ext[[
                    'Flor', 'Color', 'Variedad', 'Semana_Cosecha', 'Semana_Pedido',
                    'Tallos_Plan', 'Tallos_ForeCast', 'Balance_Color_Neto', 'Deficit_Tallos',
                    'Aprovechamiento_%', 'Camas_5200', 'Esquejes', 'Motivo'
                ]],
                width='stretch'
            )

            # Generación del archivo en formato estándar ERP (idéntico al pedido regular)
            excel_ext_erp = exportar_matriz_estandar_erp(df_ext, col_semana='Semana_Pedido', col_valor='Esquejes')

            col_dex1, col_dex2 = st.columns([2, 1])
            with col_dex1:
                st.download_button(
                    label="📥 Descargar Archivo para Plataforma (Pedido Extemporáneo - Formato ERP)",
                    data=excel_ext_erp,
                    file_name=f"Pedido_Extemporaneo_{date.today()}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                    width='stretch'
                )
            with col_dex2:
                if st.button("🗑️ Limpiar Pedido Extemporáneo", width='stretch'):
                    del st.session_state['df_extemporaneo_raw']
                    st.rerun()

    # =========================================================================
    # TAB 3: CANCELACIÓN DE MATERIAL VEGETAL (EXCEDENTES > 10% Y MÍNIMO 1 CAMA)
    # =========================================================================
    with tab_cancelacion:
        st.subheader("❌ Cancelación de Material Vegetal (Excedentes > 10% / Mínimo 1 Cama)")
        
        st.markdown(f"""
        Este módulo audita las órdenes del pedido detectando proyecciones biológicas que **superan el límite máximo permitido (+10% sobre el Plan)** 
        (`Tallos Proyectados > Plan × 1.10`), evaluando el balance neto a nivel de **Grupo Color** y asegurando que las cancelaciones sean operativamente viables.
        
        * **Regla de Umbral Operativo (Mínimo 1 Cama):** Solo se generan cancelaciones en múltiplos de **1 cama completa (5,200 esquejes)**. Se descartan recortes marginales o fracciones (ej. 200 o 500 esquejes) que se gestionan directamente al sembrar.
        * **Protección del Surtido al 100%:** Tras aplicar la cancelación, la proyección de la variedad **permanece siempre al 100% o más del Plan Aprobado**, protegiendo el mix comercial por variedad y color sin desabastecer.
        * **Distribución Temporal:** Cada cancelación se asigna a su **semana de pedido respectiva** en la ventana ejecutable (< 24 semanas: entre **{sem_siguiente}** y **{sem_firme_default}**).
        """)

        modo_canc = st.radio(
            "Método de Determinación de Cancelación:",
            [
                "⚡ Detección Automática con Compensación de Grupo Color (> 10% Límite Máximo / Mín. 1 Cama)",
                "🔻 Ajuste Mandatorio por Reducción de Área (Semana 2648 en adelante — Techo 1,120 Camas / -48 Camas en B01, B02, B03)",
                "✍️ Solicitud de Cancelación Directa por Lote"
            ],
            horizontal=True,
            key="radio_modo_canc"
        )

        if modo_canc.startswith("⚡"):
            col_c1, col_c2 = st.columns([2, 1])
            with col_c1:
                st.info(f"💡 Se evalúa la proyección consolidada contra el Plan más 10% de holgura por Grupo Color. Solo cancelaciones ≥ 1 cama completa entre **{sem_siguiente}** y **{sem_firme_default}**.")
            with col_c2:
                filtro_flor_canc = st.selectbox("Filtrar por Flor", ["Todas"] + sorted(list(df_plan[col_flor].dropna().unique())), key="filtro_flor_canc")

            if st.button("Evaluar Excedentes y Generar Solicitud de Cancelación", type="primary", key="btn_eval_canc"):
                with st.spinner("Consolidando ForeCast 52 semanas y detectando sobrecupos netos (> 10% Plan / Mínimo 1 Cama)..."):
                    try:
                        df_fc_completo = obtener_forecast_52w_completo(db)
                        semanas_fc_cols = [c for c in df_fc_completo.columns if str(c).startswith('202')]

                        fc_melt = df_fc_completo.melt(
                            id_vars=['Flor', 'Color', 'Variedad'],
                            value_vars=semanas_fc_cols,
                            var_name='Semana',
                            value_name='Tallos_Forecast'
                        )
                        fc_melt['Variedad_Norm'] = fc_melt['Variedad'].astype(str).str.strip().str.lower()
                        fc_melt['Flor_Canon'] = fc_melt['Variedad_Norm'].map(lambda vn: v_map.get(vn, (None, None))[0])
                        fc_melt['Color_Canon'] = fc_melt['Variedad_Norm'].map(lambda vn: v_map.get(vn, (None, None))[1])
                        fc_melt['Flor'] = fc_melt['Flor_Canon'].fillna(fc_melt['Flor'])
                        fc_melt['Color'] = fc_melt['Color_Canon'].fillna(fc_melt['Color'])
                        fc_melt['Flor_Norm'] = fc_melt['Flor'].str.strip().str.lower()
                        fc_melt['Color_Norm'] = fc_melt['Color'].str.strip().str.lower()
                        fc_melt['Semana_Clean'] = fc_melt['Semana'].astype(str)

                        df_plan_eval = df_plan.dropna(subset=[col_capacidad]).copy()
                        df_plan_eval = df_plan_eval[df_plan_eval[col_capacidad] > 0]
                        df_plan_eval['Semana_Clean'] = df_plan_eval['Semana'].astype(str).str.split('.').str[0].str.strip()
                        df_plan_eval['Variedad_Norm'] = df_plan_eval['Variedad'].astype(str).str.strip().str.lower()
                        df_plan_eval['Flor_Canon'] = df_plan_eval['Variedad_Norm'].map(lambda vn: v_map.get(vn, (None, None))[0])
                        df_plan_eval['Color_Canon'] = df_plan_eval['Variedad_Norm'].map(lambda vn: v_map.get(vn, (None, None))[1])
                        df_plan_eval[col_flor] = df_plan_eval['Flor_Canon'].fillna(df_plan_eval[col_flor])
                        df_plan_eval['Color'] = df_plan_eval['Color_Canon'].fillna(df_plan_eval['Color'])
                        df_plan_eval['Flor_Norm'] = df_plan_eval[col_flor].astype(str).str.strip().str.lower()
                        df_plan_eval['Color_Norm'] = df_plan_eval['Color'].astype(str).str.strip().str.lower()

                        if filtro_flor_canc != "Todas":
                            df_plan_eval = df_plan_eval[df_plan_eval[col_flor] == filtro_flor_canc]
                            fc_melt = fc_melt[fc_melt['Flor'] == filtro_flor_canc]

                        var_plan = df_plan_eval.groupby(['Variedad_Norm', col_flor, 'Color', 'Variedad', 'Semana_Clean'])[col_capacidad].sum().reset_index()
                        var_fc = fc_melt.groupby(['Variedad_Norm', 'Semana_Clean'])['Tallos_Forecast'].sum().reset_index()
                        var_m = pd.merge(var_plan, var_fc, on=['Variedad_Norm', 'Semana_Clean'], how='left')
                        var_m['Tallos_Forecast'] = var_m['Tallos_Forecast'].fillna(0)
                        var_m['Flor_Norm'] = var_m[col_flor].str.strip().str.lower()
                        var_m['Color_Norm'] = var_m['Color'].str.strip().str.lower()
                        # Límite máximo permitido: Plan * 1.10
                        var_m['Raw_Surplus'] = (var_m['Tallos_Forecast'] - var_m[col_capacidad] * 1.10).clip(lower=0)

                        # Balance a nivel de Grupo Color [Flor, Color, Semana] con límite +10%
                        gc_plan = var_m.groupby(['Flor_Norm', 'Color_Norm', 'Semana_Clean'])[col_capacidad].sum().reset_index().rename(columns={col_capacidad: 'GC_Plan'})
                        gc_fc = var_m.groupby(['Flor_Norm', 'Color_Norm', 'Semana_Clean'])['Tallos_Forecast'].sum().reset_index().rename(columns={'Tallos_Forecast': 'GC_FC'})
                        gc_raw_sur = var_m.groupby(['Flor_Norm', 'Color_Norm', 'Semana_Clean'])['Raw_Surplus'].sum().reset_index().rename(columns={'Raw_Surplus': 'GC_Raw_Sur_Sum'})

                        gc_info = pd.merge(gc_plan, gc_fc, on=['Flor_Norm', 'Color_Norm', 'Semana_Clean'])
                        gc_info = pd.merge(gc_info, gc_raw_sur, on=['Flor_Norm', 'Color_Norm', 'Semana_Clean'])
                        gc_info['GC_Net_Surplus'] = (gc_info['GC_FC'] - gc_info['GC_Plan'] * 1.10).clip(lower=0)

                        df_eval = pd.merge(var_m, gc_info, on=['Flor_Norm', 'Color_Norm', 'Semana_Clean'], how='left')

                        # Distribución proporcional si el grupo color supera el 10% neto
                        df_eval['Net_Surplus_Var'] = 0.0
                        mask_sur = (df_eval['GC_Net_Surplus'] > 50) & (df_eval['GC_Raw_Sur_Sum'] > 0) & (df_eval['Raw_Surplus'] > 0)
                        df_eval.loc[mask_sur, 'Net_Surplus_Var'] = df_eval.loc[mask_sur, 'GC_Net_Surplus'] * (df_eval.loc[mask_sur, 'Raw_Surplus'] / df_eval.loc[mask_sur, 'GC_Raw_Sur_Sum'])

                        # Margen general de la finca por semana de cosecha para proteger el volumen total
                        finca_plan = df_plan_eval.groupby('Semana_Clean')[col_capacidad].sum().rename('Finca_Plan')
                        finca_fc = fc_melt.groupby('Semana_Clean')['Tallos_Forecast'].sum().rename('Finca_FC')
                        finca_margin = pd.concat([finca_plan, finca_fc], axis=1).dropna()
                        finca_margin['Finca_Net_Margin'] = finca_margin['Finca_FC'] - finca_margin['Finca_Plan']
                        finca_margin['Finca_Cumplimiento_%'] = (finca_margin['Finca_FC'] / finca_margin['Finca_Plan']) * 100

                        cancel_records = []
                        for _, r in df_eval[df_eval['Net_Surplus_Var'] > 50].iterrows():
                            v = r['Variedad']
                            fl = r[col_flor]
                            col = r['Color']
                            sem_cos = r['Semana_Clean']
                            net_surplus = r['Net_Surplus_Var']

                            aprov, dia_pico, metodo = resolver_curva_variedad(
                                v, fl, col, dyn_lower, fc_stats, f_stats, global_stats
                            )

                            try:
                                y = int(sem_cos[:4])
                                w = int(sem_cos[4:])
                                f_pico = date.fromisocalendar(y, w, 4)
                                f_siem = f_pico - timedelta(days=dia_pico)
                                f_ped = f_siem - timedelta(weeks=4)
                                sem_canc = get_iso_week_string(f_ped)
                            except Exception:
                                continue

                            # Filtro estricto: Solo semanas cancelables futuras en su fecha respectiva
                            if sem_siguiente <= sem_canc < sem_firme_default:
                                plantas_exc = net_surplus / aprov
                                # Regla de Gobernanza: Mínimo 1 cama completa (5,200) y respetar surtido del Plan al 100%
                                camas_canc = int(plantas_exc // 5200.0)
                                if camas_canc >= 1:
                                    tallos_canc = camas_canc * 5200.0 * aprov
                                    # Asegurar que tras cancelar no quede por debajo del 100% del Plan
                                    if (r['Tallos_Forecast'] - tallos_canc) < r[col_capacidad]:
                                        camas_canc = int(max(0, (r['Tallos_Forecast'] - r[col_capacidad]) // (5200.0 * aprov)))
                                        tallos_canc = camas_canc * 5200.0 * aprov

                                    if camas_canc >= 1:
                                        esquejes_canc = camas_canc * 5200

                                        # Evaluar seguridad para el plan general de la finca
                                        f_margin = finca_margin.loc[sem_cos, 'Finca_Net_Margin'] if sem_cos in finca_margin.index else 0
                                        f_cump = finca_margin.loc[sem_cos, 'Finca_Cumplimiento_%'] if sem_cos in finca_margin.index else 100.0
                                        es_segura = bool(f_margin >= 0)

                                        restante_fc = r['Tallos_Forecast'] - tallos_canc
                                        cump_restante_pct = round((restante_fc / r[col_capacidad]) * 100.0, 1) if r[col_capacidad] > 0 else 100.0

                                        cancel_records.append({
                                            "Flor": fl,
                                            "Color": col,
                                            "Variedad": v,
                                            "Semana_Cosecha": f"S{sem_cos}",
                                            "Semana_Siembra": get_iso_week_string(f_siem),
                                            "Semana_Cancelacion": sem_canc,
                                            "Tallos_Plan": int(round(r[col_capacidad])),
                                            "Plan_con_Colchon_10%": int(round(r[col_capacidad] * 1.10)),
                                            "Tallos_ForeCast": int(round(r['Tallos_Forecast'])),
                                            "Excedente_Color_Neto": f"Exceso Color >10%: {int(round(r['GC_Net_Surplus'])):,} tll",
                                            "Excedente_Tallos": int(round(net_surplus)),
                                            "Aprovechamiento_%": round(aprov * 100.0, 1),
                                            "Camas_a_Cancelar": camas_canc,
                                            "Esquejes_a_Cancelar": esquejes_canc,
                                            "Finca_Cumplimiento_%": cump_restante_pct,
                                            "Finca_Margen_Tallos": int(round(restante_fc - r[col_capacidad])),
                                            "Gobernanza_Riesgo": "🟢 Segura (Mín. 1 Cama / Protege 100% Plan)" if es_segura else "🟡 Condicionada a Propagación",
                                            "Es_Segura": es_segura,
                                            "Motivo": f"Supera límite +10% sobre Plan. Libera {camas_canc} cama(s) y mantiene {cump_restante_pct}% de meta"
                                        })

                        if not cancel_records:
                            st.success("🎉 No se detectaron sobrecupos netos por Grupo Color que superen el seguro del 5% en la ventana ejecutable.")
                        else:
                            df_canc_result = pd.DataFrame(cancel_records)
                            st.session_state['df_cancelacion_raw'] = df_canc_result
                            st.success(f"Se identificaron {len(df_canc_result)} cancelaciones netas distribuidas en sus semanas correspondientes.")

                    except Exception as e:
                        st.error(f"Error evaluando cancelaciones: {e}")

        elif modo_canc.startswith("🔻"):
            st.markdown("##### 🔻 Ajuste Mandatorio por Reducción de Área Física (Semana 2648 en adelante)")
            with st.container(border=True):
                st.markdown(f"""
                * **Cronograma de Área:** En este momento el área productiva real de la finca es de **64,878 m²** (1,168 camas comerciales hasta Semana 2647). A partir de la **Semana 2648**, el área se reduce físicamente desmontando **6 naves en total (48 camas)**:
                  - **Bloque 01:** $-2$ naves ($-16$ camas $\to$ capacidad pasa de 240 a 224 camas).
                  - **Bloque 02:** $-2$ naves ($-16$ camas $\to$ capacidad pasa de 160 a 144 camas).
                  - **Bloque 03:** $-2$ naves ($-16$ camas $\to$ capacidad pasa de 184 a 168 camas).
                  - **Bloques 04, 05, 06 e INV:** Permanecen sin cambios.
                  - **Total Finca:** Pasa de 1,168 a **1,120 camas comerciales** (62,212 m², $-4.11\\%$).
                * **Impacto en Pedidos:** Las órdenes programadas para siembra a partir de la semana **202648** en la ventana ejecutable (< 24 semanas) fueron proyectadas para 1,168 camas y tienen un excedente de material vegetal que ya no cabe físicamente en las camas de la finca.
                * **Acción:** Cuantifica y genera la lista oficial de cancelaciones para recortar el material sobrante preservando la estructura del pedido.
                """)

                col_red1, col_red2 = st.columns([2, 1])
                with col_red1:
                    st.info(f"📅 **Ventana Ejecutable:** Pedidos entre **{sem_siguiente}** y **{sem_firme_default}** con siembra >= **S{SEMANA_CORTE_REDUCCION_AREA}**.")
                with col_red2:
                    btn_calc_red = st.button("Evaluar Excedentes por Reducción de Área", type="primary", key="btn_eval_red")

                if btn_calc_red:
                    with st.spinner("Explosión de MRP y cálculo de excedentes de área..."):
                        try:
                            df_canc_red = calcular_cancelaciones_reduccion_area_s2648(
                                archivo_pedido="PedidoConsolidado_master.xlsx",
                                sem_inicio=sem_siguiente,
                                sem_fin=sem_firme_default
                            )
                            if df_canc_red.empty:
                                st.warning("No se encontraron pedidos afectados para la ventana seleccionada.")
                            else:
                                st.session_state['df_cancelacion_raw'] = df_canc_red
                                st.success(f"✅ Se identificaron {len(df_canc_red)} registros de exceso por reducción de área ({df_canc_red['Esquejes_a_Cancelar'].sum():,} esquejes a cancelar).")
                        except Exception as e:
                            st.error(f"Error calculando cancelaciones por reducción de área: {e}")

        else:
            # Modo C: Solicitud Directa
            st.markdown("Ingresa una solicitud directa de cancelación de material vegetal para evitar recibir esquejes excedentes.")
            with st.form("form_cancelacion_directa"):
                col_can1, col_can2, col_can3 = st.columns(3)
                with col_can1:
                    flores_disp_c = sorted(list(df_plan[col_flor].dropna().unique()))
                    flor_sel_c = st.selectbox("Flor", flores_disp_c, key="canc_flor")
                    vars_disp_c = sorted(list(df_plan[df_plan[col_flor] == flor_sel_c]['Variedad'].dropna().unique()))
                    var_sel_c = st.selectbox("Variedad", vars_disp_c, key="canc_var")
                with col_can2:
                    colores_disp_c = sorted(list(df_plan[df_plan['Variedad'] == var_sel_c]['Color'].dropna().unique()))
                    col_sel_c = colores_disp_c[0] if colores_disp_c else "Desconocido"
                    st.text_input("Color", value=col_sel_c, disabled=True, key="canc_col")
                    sem_canc_directa = st.text_input(f"Semana de Cancelación (>= {sem_siguiente})", value=sem_siguiente, key="canc_sem")
                with col_can3:
                    camas_a_canc = st.number_input("Camas a Cancelar (5,200 esquejes)", min_value=1, value=2, step=1, key="canc_camas")
                    motivo_canc = st.selectbox("Motivo de Cancelación", [
                        "Producción en campo supera seguro del 5%",
                        "Cancelación de pedido comercial por cliente",
                        "Reducción de área/camas físicas disponibles",
                        "Excedente proyectado en curva de floración"
                    ], key="canc_motivo")

                if st.form_submit_button("Agregar a Lista de Cancelación", type="primary"):
                    sem_canc_clean = sem_canc_directa if sem_canc_directa.startswith("S") else f"S{sem_canc_directa}"
                    if sem_canc_clean < sem_siguiente:
                        st.error(f"❌ La semana de cancelación debe ser igual o posterior a la semana siguiente ({sem_siguiente}). No es posible cancelar semanas pasadas.")
                    else:
                        sem_siem_dir = sumar_semanas_iso(sem_canc_clean, 4)
                        aprov, dia_pico, metodo = resolver_curva_variedad(
                            var_sel_c, flor_sel_c, col_sel_c, dyn_lower, fc_stats, f_stats, global_stats
                        )
                        esquejes_canc = camas_a_canc * 5200
                        tallos_canc = int(round(esquejes_canc * aprov))

                        nuevo_canc = {
                            "Flor": flor_sel_c,
                            "Color": col_sel_c,
                            "Variedad": var_sel_c,
                            "Semana_Cosecha": "Directa",
                            "Semana_Siembra": sem_siem_dir,
                            "Semana_Cancelacion": sem_canc_clean,
                            "Tallos_Plan": 0,
                            "Tallos_ForeCast": tallos_canc,
                            "Excedente_Color_Neto": "Directa Manual",
                            "Excedente_Tallos": tallos_canc,
                            "Aprovechamiento_%": round(aprov * 100.0, 1),
                            "Camas_a_Cancelar": camas_a_canc,
                            "Esquejes_a_Cancelar": esquejes_canc,
                            "Finca_Cumplimiento_%": 100.0,
                            "Finca_Margen_Tallos": 0,
                            "Gobernanza_Riesgo": "🟢 Manual Directa",
                            "Es_Segura": True,
                            "Motivo": motivo_canc
                        }

                        if 'df_cancelacion_raw' not in st.session_state:
                            st.session_state['df_cancelacion_raw'] = pd.DataFrame([nuevo_canc])
                        else:
                            st.session_state['df_cancelacion_raw'] = pd.concat(
                                [st.session_state['df_cancelacion_raw'], pd.DataFrame([nuevo_canc])], 
                                ignore_index=True
                            )
                        st.success(f"Cancelación de '{camas_a_canc}' camas ({esquejes_canc:,} esquejes) agregada para '{var_sel_c}'.")

        # Visualización de Cancelación de Material Vegetal
        if 'df_cancelacion_raw' in st.session_state and not st.session_state['df_cancelacion_raw'].empty:
            df_canc = st.session_state['df_cancelacion_raw']

            if 'Es_Segura' not in df_canc.columns:
                df_canc['Es_Segura'] = True
            if 'Gobernanza_Riesgo' not in df_canc.columns:
                df_canc['Gobernanza_Riesgo'] = "🟢 Segura"

            st.divider()
            st.markdown("### 📋 Resumen de Material Vegetal a Cancelar (Salidas para Planeación)")

            st.info("""
            🛡️ **Límite Máximo Permitido (+10%) y Protección del Surtido al 100%:**
            * **Tolerancia del 10% Respetada:** El sistema tolera hasta un **+10% de producción sobre el Plan** (`Plan × 1.10`) para absorber eficiencias operativas. Solo se audita el exceso neto que sobrepase ese límite.
            * **Mínimo 1 Cama Completa:** Cada cancelación representa al menos **1 cama completa (5,200 esquejes)** en múltiplos enteros, evitando gestionar fracciones o volúmenes mínimos que se regulan en siembra.
            * **Surtido del Plan Intacto:** Tras la cancelación, la variedad **mantiene siempre al menos el 100% de su meta aprobada**, blindando el mix comercial por variedad y color.
            * **🌱 Conexión con Plan de Enraizamiento:** Al pulsar el botón oficial de sincronización, las camas canceladas se descuentan de inmediato de `Plan_Aprobado_Detallado.csv`, disminuyendo automáticamente las bandejas de 112 y horas de labor en el módulo de Enraizamiento.
            * **🟢 Cancelaciones Seguras (Inmediatas):** Semanas donde la producción general de la finca cubre el 100% del Plan general.
            * **🟡 Cancelaciones Condicionadas a Propagación:** Semanas de alta tensión donde se requiere confirmación de material extemporáneo antes de liberar pedidos.
            """)

            tot_esq_canc = df_canc['Esquejes_a_Cancelar'].sum()
            seg_esq = df_canc[df_canc['Es_Segura'] == True]['Esquejes_a_Cancelar'].sum()
            seg_casos = (df_canc['Es_Segura'] == True).sum()
            cond_esq = df_canc[df_canc['Es_Segura'] == False]['Esquejes_a_Cancelar'].sum()
            cond_casos = (df_canc['Es_Segura'] == False).sum()

            kpi_s1, kpi_s2, kpi_s3 = st.columns(3)
            kpi_s1.metric("Total Excedentes Detectados", f"{tot_esq_canc:,.0f} esq", f"{len(df_canc)} casos")
            kpi_s2.metric("🟢 Cancelaciones Seguras Ya", f"{seg_esq:,.0f} esq", f"{seg_casos} casos (Protege Plan Finca)")
            kpi_s3.metric("🟡 Condicionadas a Propagación", f"{cond_esq:,.0f} esq", f"{cond_casos} casos (En espera)")

            criterio_canc = st.radio(
                "Filtro de Gobernanza para Descarga y Análisis:",
                [
                    "🟢 Solo Cancelaciones Seguras (Protege 100% del Plan General de la Finca)",
                    "📋 Ver Todas las Cancelaciones (Seguras + Condicionadas)",
                    "🟡 Solo Condicionadas a Propagación"
                ],
                horizontal=True,
                key="radio_criterio_canc"
            )

            if "Solo Cancelaciones Seguras" in criterio_canc:
                df_canc_mostrar = df_canc[df_canc['Es_Segura'] == True]
            elif "Solo Condicionadas" in criterio_canc:
                df_canc_mostrar = df_canc[df_canc['Es_Segura'] == False]
            else:
                df_canc_mostrar = df_canc

            if df_canc_mostrar.empty:
                st.info("No hay cancelaciones bajo el criterio seleccionado.")
            else:
                kpi_c1, kpi_c2, kpi_c3, kpi_c4 = st.columns(4)
                m_tot_esq = df_canc_mostrar['Esquejes_a_Cancelar'].sum()
                m_tot_cam = df_canc_mostrar['Camas_a_Cancelar'].sum()
                m_tot_exc = df_canc_mostrar['Excedente_Tallos'].sum()
                m_tot_vars = df_canc_mostrar['Variedad'].nunique()

                kpi_c1.metric("Esquejes en Vista", f"{m_tot_esq:,.0f}")
                kpi_c2.metric("Camas en Vista (5,200)", f"{m_tot_cam:,.0f}")
                kpi_c3.metric("Excedente Tallos Neutralizado", f"{m_tot_exc:,.0f}")
                kpi_c4.metric("Variedades en Vista", f"{m_tot_vars:,}")

                cols_mostrar = [
                    'Flor', 'Color', 'Variedad', 'Semana_Cosecha', 'Semana_Cancelacion',
                    'Gobernanza_Riesgo', 'Finca_Cumplimiento_%',
                    'Tallos_Plan', 'Plan_con_Colchon_5%', 'Tallos_ForeCast', 'Excedente_Color_Neto', 'Excedente_Tallos',
                    'Aprovechamiento_%', 'Camas_a_Cancelar', 'Esquejes_a_Cancelar', 'Motivo'
                ]
                cols_mostrar = [c for c in cols_mostrar if c in df_canc_mostrar.columns]

                st.dataframe(df_canc_mostrar[cols_mostrar], width='stretch')

                excel_canc_erp = exportar_matriz_estandar_erp(
                    df_canc_mostrar, col_semana='Semana_Cancelacion', col_valor='Esquejes_a_Cancelar'
                )

                col_dc1, col_dc2, col_dc3 = st.columns([1.5, 1.8, 0.7])
                with col_dc1:
                    st.download_button(
                        label=f"📥 Descargar para Plataforma ({len(df_canc_mostrar)} casos - {m_tot_esq:,.0f} Esq)",
                        data=excel_canc_erp,
                        file_name=f"Cancelacion_Material_Vegetal_{date.today()}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="secondary",
                        width='stretch'
                    )
                with col_dc2:
                    if st.button("🔄 Aplicar Cancelaciones a Plan Maestro y Enraizamiento", type="primary", width='stretch'):
                        with st.spinner("Descontando cancelaciones en Plan Detallado y Pedido Maestro..."):
                            from app.services.ocupacion_service import aplicar_cancelaciones_a_planes_maestros
                            res_app_canc = aplicar_cancelaciones_a_planes_maestros(df_canc_mostrar)
                            if res_app_canc.get("status") == "success":
                                st.success(f"✅ ¡Cancelaciones aplicadas! Se descontaron {res_app_canc['camas']} camas ({res_app_canc['esquejes']:,} esquejes).")
                                st.info("🔄 **Sincronización:** 'Plan_Aprobado_Detallado.csv' y 'PedidoConsolidado_master.xlsx' fueron actualizados. El módulo de **Plan de Enraizamiento** ya refleja de inmediato la disminución de bandejas de 112, camas físicas y mano de obra.")
                            else:
                                st.error(f"Error aplicando cancelaciones: {res_app_canc.get('message', 'Desconocido')}")
                with col_dc3:
                    if st.button("🗑️ Limpiar", width='stretch'):
                        del st.session_state['df_cancelacion_raw']
                        st.rerun()
