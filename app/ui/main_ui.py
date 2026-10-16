import sys
import os
import json
import streamlit as st
import pandas as pd
from datetime import date
import plotly.graph_objects as go

# Añadir el directorio raíz al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from app.core.database import SessionLocal, engine
from app.models.models import Variedad
from app.services.forecast_service import generar_forecast_13wk, generar_forecast_ml_live, isocalendar_to_string
from app.services.alertas_service import render_panel_alertas_sop, obtener_alertas_sop
from app.ui.styles import aplicar_tema_invernadero_industrial, estilizar_figura_plotly, PALETA_INVERNADERO

st.set_page_config(page_title="S&OP Enterprise | Planeación Florícola", layout="wide", page_icon="📊")
aplicar_tema_invernadero_industrial()

st.title("S&OP Master Planning Platform")
st.caption("Sistema Integrado de Planeación y Sincronización Operativa: Demanda Comercial, Oferta de Cosecha y Propagación")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db = next(get_db())

st.sidebar.markdown("### 🏢 S&OP Command Center")
st.sidebar.caption("Planeación Integrada de Suministros")
modulo = st.sidebar.radio("Módulos del Sistema:", [
    "Dashboard General", 
    "Curvas e Índices (Campo)", 
    "Calibración de Curvas",
    "ForeCast y Exportación", 
    "Programación Diaria y Temporadas", 
    "Plan de Producción (MVA)", 
    "Ocupación de Área y Capacidad",
    "Pedido Material Vegetal", 
    "Plan de Enraizamiento"
])

from app.ui.curvas_ui import render_curvas_module
from app.ui.accuracy_ui import render_accuracy_module
from app.ui.actas_ui import render_actas_module
from app.ui.ocupacion_ui import render_ocupacion_module

if modulo == "Dashboard General":
    st.header("📊 Dashboard General")
    
    # KPIs básicos del Plano de Siembra Actual (Inventario Vivo en Campo)
    col1, col2, col3, col4 = st.columns(4)
    
    # Calcular métricas exclusivas del plano de siembra actual
    df_metrics = pd.read_sql("""
        SELECT 
            count(distinct s.variedad_id) as vars_activas,
            count(s.id) as camas, 
            sum(s.plantas_sembradas) as plantas, 
            sum(s.area_m2) as area_ocupada 
        FROM siembras s
    """, engine)
    
    total_vars_activas = df_metrics['vars_activas'].iloc[0] if not df_metrics.empty and pd.notnull(df_metrics['vars_activas'].iloc[0]) else 0
    total_camas_sembradas = df_metrics['camas'].iloc[0] if not df_metrics.empty and pd.notnull(df_metrics['camas'].iloc[0]) else 0
    total_plantas_sembradas = df_metrics['plantas'].iloc[0] if not df_metrics.empty and pd.notnull(df_metrics['plantas'].iloc[0]) else 0
    area_ocupada = df_metrics['area_ocupada'].iloc[0] if not df_metrics.empty and pd.notnull(df_metrics['area_ocupada'].iloc[0]) else 0
    total_catalog = db.query(Variedad).count()
    
    col1.metric("Variedades en Campo", f"{total_vars_activas:,.0f}", help=f"{total_vars_activas} variedades sembradas en el plano actual (de {total_catalog:,} registradas en el catálogo maestro)")
    col2.metric("Área Ocupada (m²)", f"{area_ocupada:,.2f}")
    col3.metric("Lotes Sembrados", f"{total_camas_sembradas:,.0f}")
    col4.metric("Plantas Sembradas", f"{total_plantas_sembradas:,.0f}")
    
    if total_vars_activas > 0:
        with st.expander("📋 Ver Distribución del Plano de Siembra Actual por Tipo de Flor", expanded=False):
            df_flor_plano = pd.read_sql("""
                SELECT 
                    v.flor as "Tipo de Flor",
                    count(distinct v.id) as "Variedades en Campo",
                    count(s.id) as "Lotes Sembrados",
                    sum(s.plantas_sembradas) as "Plantas Sembradas",
                    round(sum(s.area_m2), 2) as "Área Ocupada (m²)"
                FROM siembras s
                JOIN variedades v ON s.variedad_id = v.id
                GROUP BY v.flor
                ORDER BY "Plantas Sembradas" DESC
            """, engine)
            
            total_dict = {
                "Tipo de Flor": "TOTAL GENERAL",
                "Variedades en Campo": total_vars_activas,
                "Lotes Sembrados": total_camas_sembradas,
                "Plantas Sembradas": total_plantas_sembradas,
                "Área Ocupada (m²)": round(area_ocupada, 2)
            }
            df_flor_plano = pd.concat([df_flor_plano, pd.DataFrame([total_dict])], ignore_index=True)
            
            st.dataframe(
                df_flor_plano.style.format({
                    "Variedades en Campo": "{:,.0f}",
                    "Lotes Sembrados": "{:,.0f}",
                    "Plantas Sembradas": "{:,.0f}",
                    "Área Ocupada (m²)": "{:,.2f}"
                }),
                width='stretch'
            )
            
    # Panel de Gobernanza y Alertas S&OP
    st.markdown("")
    render_panel_alertas_sop()
    
    st.divider()
    
    st.subheader("Carga de Insumos Maestros")
    st.markdown("Sube aquí los archivos base. Una vez cargados, todos los módulos del sistema los usarán automáticamente.")
    
    col_ins1, col_ins2, col_ins3 = st.columns(3)
    
    with col_ins1:
        st.markdown("**1. Catálogo de Variedades (Maestro)**")
        total_catalog = db.query(Variedad).count()
        flores_count = pd.read_sql("SELECT flor, count(*) as cant FROM variedades GROUP BY flor", engine)
        flores_str = ", ".join([f"{r['flor']}: {r['cant']}" for _, r in flores_count.iterrows()]) if not flores_count.empty else "Ninguna"
        
        if total_catalog > 0:
            st.info(f"**Registradas:** {total_catalog:,} variedades\n\n*{flores_str}*")
        else:
            st.warning("⚠️ No hay catálogo de variedades registrado.")
            
        uploaded_vars = st.file_uploader("Cargar Listado(s) de Variedades", type=["xlsx", "xls"], accept_multiple_files=True, key="upload_vars")
        if uploaded_vars:
            if st.button("Procesar Catálogo de Variedades"):
                with st.spinner("Procesando listados de variedades..."):
                    from app.services.variedad_service import procesar_archivos_variedades
                    res = procesar_archivos_variedades(uploaded_vars, db)
                    st.success(f"Catálogo actualizado con éxito: {res.get('total_en_db', 0)} variedades en total ({res.get('insertadas', 0)} nuevas, {res.get('actualizadas', 0)} actualizadas).")
                    st.rerun()
                    
    with col_ins2:
        st.markdown("**2. Plano de Siembra (Inventario Vivo)**")
        if os.path.exists("last_dataset_name.txt"):
            with open("last_dataset_name.txt", "r") as f:
                last_file = f.read().strip()
        else:
            last_file = "Ninguno"
            
        st.info(f"**Cargado:** {last_file}")
        
        uploaded_file = st.file_uploader("Cargar nuevo dataset de Siembras", type=["xlsx", "xls"], key="upload_siembras")
        if uploaded_file is not None:
            if st.button("Procesar Siembras"):
                with st.spinner("Procesando dataset de siembras..."):
                    file_path = "Siembra Actual (16).xlsx"
                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    
                    with open("last_dataset_name.txt", "w") as f:
                        f.write(uploaded_file.name)
                    
                    from scripts.ingestar_siembra import ingestar_siembra_actual
                    ingestar_siembra_actual()
                    
                    st.success("Datos de siembra actualizados.")
                    st.rerun()
                    
    with col_ins3:
        st.markdown("**3. Pedido Consolidado (MVA)**")
        if os.path.exists("PedidoConsolidado_master.xlsx"):
            st.info("✅ Pedido Consolidado disponible en el sistema.")
        else:
            st.warning("⚠️ No hay Pedido Consolidado cargado.")
            
        uploaded_pedido = st.file_uploader("Cargar nuevo Pedido Consolidado", type=["xlsx", "xls"], key="upload_pedido")
        if uploaded_pedido is not None:
            if st.button("Guardar Pedido MVA"):
                with open("PedidoConsolidado_master.xlsx", "wb") as f:
                    f.write(uploaded_pedido.getbuffer())
                st.success("Pedido guardado. Se usará automáticamente en las proyecciones.")
                st.rerun()
                
    st.divider()

elif modulo == "Curvas e Índices (Campo)":
    render_curvas_module(db)

elif modulo == "Calibración de Curvas":
    render_accuracy_module(db)

elif modulo == "ForeCast y Exportación":
    st.header("📈 ForeCast y Exportación (S&OP)")
    st.markdown("Proyección de cosecha consolidada y exportación de plantillas (Webflowers / 52 Semanas).")
    
    # Selector de horizonte (Presets y Personalizado)
    from datetime import date
    from app.services.forecast_service import isocalendar_to_string
    from app.services.enraizamiento_service import sumar_semanas_iso

    semana_actual = isocalendar_to_string(date.today())
    semanas_disponibles = [sumar_semanas_iso(semana_actual, i) for i in range(53)]

    col_hzt1, col_hzt2 = st.columns([2, 2])
    with col_hzt1:
        vista = st.radio(
            "Selecciona el horizonte de proyección:", 
            ["13 Semanas Móviles (Actual + 13)", "52 Semanas (Año Completo)", "Personalizado"], 
            horizontal=True,
            key="fc_vista_horizonte"
        )
    
    sem_desde = semana_actual
    sem_hasta = sumar_semanas_iso(semana_actual, 13 if "13" in vista else 51)
    
    with col_hzt2:
        if vista == "Personalizado":
            col_p1, col_p2 = st.columns(2)
            sem_desde = col_p1.selectbox("Semana Desde:", semanas_disponibles, index=0)
            opciones_hasta = [s for s in semanas_disponibles if s >= sem_desde]
            idx_default = min(13, len(opciones_hasta) - 1)
            sem_hasta = col_p2.selectbox("Semana Hasta:", opciones_hasta, index=idx_default)
    
    # Alertas y Contexto S&OP por horizonte
    alertas_sop = obtener_alertas_sop()
    if "13" in vista:
        a13 = alertas_sop.get("regla_13wk", {})
        st.caption(f"{a13.get('icono', '⏰')} **Regla 1 S&OP (13 Semanas / Webflowers):** Cierre los Miércoles antes de las 12:00 m. {a13.get('mensaje', '')}")
    elif "52" in vista:
        a52 = alertas_sop.get("regla_52wk", {})
        st.caption(f"{a52.get('icono', '📅')} **Regla 2 S&OP (52 Semanas / Anual):** Carga los 4º Jueves de cada mes. {a52.get('mensaje', '')}")
    else:
        st.caption(f"🎯 **Horizonte Personalizado:** Visualizando rango operativo desde la semana **{sem_desde}** hasta la semana **{sem_hasta}**.")
    
    # Parámetros visuales de suavización y calibración (dentro de ForeCast, sin saturar la barra lateral)
    from app.services.calibracion_service import cargar_parametros_calibrados
    params_cal = cargar_parametros_calibrados()
    default_pond = int(params_cal.get('ponderacion_%', 100))
    default_ciclos = int(params_cal.get('num_ciclos', 9))

    with st.expander("⚙️ Calibración de Curvas y Parámetros de Suavización por Flor", expanded=False):
        col_c1, col_c2 = st.columns([2, 1])
        with col_c1:
            if params_cal.get('fecha_calibracion'):
                por_fl = params_cal.get('por_flor', {})
                c_p = por_fl.get('Cushion', {})
                d_p = por_fl.get('Daisy', {})
                n_p = por_fl.get('Novelty', {})
                st.markdown(f"""**Parámetros Óptimos Calibrados por Flor:**
* 🌸 **Cushion:** {c_p.get('ponderacion_%', default_pond)}% ponderación ({c_p.get('num_ciclos', default_ciclos)} ciclos)
* 🌼 **Daisy:** {d_p.get('ponderacion_%', default_pond)}% ponderación ({d_p.get('num_ciclos', default_ciclos)} ciclos)
* 🌺 **Novelty:** {n_p.get('ponderacion_%', default_pond)}% ponderación ({n_p.get('num_ciclos', default_ciclos)} ciclos)
*Última calibración: {params_cal.get('fecha_calibracion')}*""")
                usar_calibrado_flor = st.checkbox("Aplicar Calibración Segmentada por Flor", value=True, help="Usa automáticamente la ponderación y ciclos óptimos de Cushion, Daisy y Novelty.")
            else:
                usar_calibrado_flor = False
                st.info("ℹ️ Parámetros en valores base estándar (100% ponderación / 9 ciclos).")

        with col_c2:
            if not usar_calibrado_flor:
                ponderacion = st.slider("Ponderación Global (%)", 0, 100, default_pond)
                periodos = st.number_input("Ciclos Globales (Periodos)", min_value=1, value=default_ciclos)
                alpha_fc = ponderacion / 100.0
                ciclos_fc = periodos
                params_flor_fc = None
            else:
                alpha_fc = None
                ciclos_fc = None
                params_flor_fc = params_cal.get('por_flor')
    
    with st.spinner(f"Generando balance S&OP y matriz de pronóstico ({vista})..."):
        # 1. Proyección de Inventario Vivo en Suelo (Corto Plazo: primeras 10 semanas)
        df_forecast_vivo = generar_forecast_13wk(db, alpha=alpha_fc, num_ciclos=ciclos_fc, params_por_flor=params_flor_fc)

        # 2. Proyección Biológica de Cosecha desde Pedido / Siembras Programadas (Mediano Plazo: Semana 11+)
        import os
        from app.services.mva_service import generar_plan_mva, proyectar_cosecha_desde_mva, combinar_proyecciones_52_semanas, llenar_plantilla_52_semanas
        file_path = "PedidoConsolidado_master.xlsx"
        
        df_mrp = pd.DataFrame()
        df_proyeccion_mva = pd.DataFrame()
        fuente_plan_mva = ""
        
        if os.path.exists("Plan_Aprobado_Detallado.csv"):
            try:
                df_det = pd.read_csv("Plan_Aprobado_Detallado.csv")
                if 'Esquejes' in df_det.columns and not df_det.empty:
                    df_det['Esquejes_Para_Siembra (Final)'] = df_det['Esquejes']
                    df_proyeccion_mva = proyectar_cosecha_desde_mva(df_det, db)
                    fuente_plan_mva = "Plan Detallado Aprobado (Curvas Biológicas de Corte)"
            except Exception:
                df_proyeccion_mva = pd.DataFrame()
                
        if df_proyeccion_mva.empty and os.path.exists(file_path):
            try:
                df_mrp = generar_plan_mva(file_path, week_is="Pedido")
                df_proyeccion_mva = proyectar_cosecha_desde_mva(df_mrp, db)
                fuente_plan_mva = "Pedido Consolidado de Material Vegetal (Curvas Biológicas 24 Semanas)"
            except Exception:
                df_proyeccion_mva = pd.DataFrame()
                
        if not df_proyeccion_mva.empty:
            df_forecast = combinar_proyecciones_52_semanas(df_forecast_vivo, df_proyeccion_mva)
        else:
            df_forecast = df_forecast_vivo.copy()
            fuente_plan_mva = "Inventario Vivo Exclusivo"

        st.info(
            f"💡 **Arquitectura de Suministro S&OP:** "
            f"🟢 **Inventario Vivo (Verde Esmeralda):** Semanas 1 a 10 provienen al 100% del **Inventario Vivo** en suelo. | "
            f"🟣 **Siembras Proyectadas del Pedido (Púrpura Amatista SAP):** Semana 11 en adelante proyecta la cosecha biológica real ({fuente_plan_mva}). | "
            f"🟦 **Demanda Comercial Aprobada (Azul SAP Fiori Discontinuo):** Meta acordada en el Plan Maestro de Producción."
        )
        
    if df_forecast.empty:
        st.warning("No hay datos suficientes para generar el forecast.")
    else:
        semanas_cols = sorted([col for col in df_forecast.columns if str(col).startswith('202')])
        
        if "13" in vista:
            semanas_futuras = [s for s in semanas_cols if s >= semana_actual][:14]
        elif "52" in vista:
            semanas_futuras = [s for s in semanas_cols if s >= semana_actual][:52]
        else: # Personalizado
            semanas_futuras = [s for s in semanas_cols if sem_desde <= s <= sem_hasta]
            
        # Resaltar la semana actual
        if semana_actual in df_forecast.columns:
            nombre_actual = f"{semana_actual} (Actual)"
            df_forecast = df_forecast.rename(columns={semana_actual: nombre_actual})
            semanas_futuras = [nombre_actual if s == semana_actual else s for s in semanas_futuras]
            
        # Cargar Plan de Producción Aprobado (Demanda Comercial)
        plan_aprobado_path = "Plan_Aprobado.csv"
        plan_series_cap = pd.Series(0.0, index=semanas_futuras)
        df_plan_app = pd.DataFrame()
        
        if os.path.exists(plan_aprobado_path):
            try:
                df_plan_app = pd.read_csv(plan_aprobado_path)
                col_capacidad = 'Tallos a Producir (Capacidad)' if 'Tallos a Producir (Capacidad)' in df_plan_app.columns else 'Suma de Tallos'
                
                if 'Semana' in df_plan_app.columns:
                    def clean_semana(val):
                        if pd.isna(val): return ""
                        try: return str(int(float(val)))
                        except: return str(val).strip()
                            
                    df_plan_app['Semana'] = df_plan_app['Semana'].apply(clean_semana)
                    
                    if col_capacidad in df_plan_app.columns:
                        df_plan_grp_cap = df_plan_app.groupby('Semana')[col_capacidad].sum()
                        for sem_fut in semanas_futuras:
                            sem_clean = sem_fut.split(" ")[0]
                            if sem_clean in df_plan_grp_cap.index:
                                plan_series_cap[sem_fut] = df_plan_grp_cap[sem_clean]
            except Exception as e:
                st.warning(f"No se pudo leer el Plan Aprobado: {e}")

        # 4 PESTAÑAS ESTRUCTURALES DEL MÓDULO FORECAST (ESTÁNDAR SAP FIORI HORIZON)
        tab_bal, tab_gap, tab_matriz, tab_wf = st.tabs([
            "📈 Proyección y Balance Semanal",
            "🔍 Diagnóstico de Brechas (Flor / Variedad)",
            "📋 Matriz de Producción (52 Semanas)",
            "📤 Exportación a Plataformas"
        ])

        # =====================================================================
        # PESTAÑA 1: PROYECCIÓN Y BALANCE SEMANAL S&OP
        # =====================================================================
        with tab_bal:
            if semanas_futuras:
                fc_agrupado = df_forecast[semanas_futuras].sum()
                tot_fc = fc_agrupado.sum()
                tot_plan = plan_series_cap.sum()
                brecha_tot = tot_fc - tot_plan
                cumpl_global = (tot_fc / tot_plan * 100) if tot_plan > 0 else 100.0

                col_k1, col_k2, col_k3, col_k4 = st.columns(4)
                col_k1.metric("Oferta ForeCast Biológico", f"{tot_fc:,.0f}", f"{len(semanas_futuras)} semanas evaluadas")
                col_k2.metric("Demanda Plan Aprobado", f"{tot_plan:,.0f}", "Meta Comercial")
                col_k3.metric("Brecha / Gap Neto S&OP", f"{brecha_tot:+,.0f}", "Superávit (+)" if brecha_tot >= 0 else "Déficit (-)", delta_color="normal")
                col_k4.metric("Cumplimiento Global", f"{cumpl_global:.1f}%", "Alineación Plan vs Oferta")

                st.markdown("")

                # Gráfico Plotly: Demanda Comercial vs Oferta Biológica
                fig_fc = go.Figure()
                limite_corto_plazo = 10
                y_fc = [fc_agrupado.get(s, 0) for s in semanas_futuras]

                if len(semanas_futuras) <= limite_corto_plazo:
                    fig_fc.add_trace(go.Scatter(
                        x=semanas_futuras,
                        y=y_fc,
                        mode='lines+markers',
                        name="1. Inventario Vivo en Suelo (Corto Plazo: S1-S10)",
                        line=dict(color='#059669', width=3.2),
                        marker=dict(size=7, symbol='circle'),
                        hovertemplate="<b>Semana %{x}</b><br>🟢 Inventario Vivo (Suelo): %{y:,.0f} tallos<extra></extra>"
                    ))
                else:
                    sems_vivo = semanas_futuras[:limite_corto_plazo]
                    y_vivo = y_fc[:limite_corto_plazo]
                    fig_fc.add_trace(go.Scatter(
                        x=sems_vivo,
                        y=y_vivo,
                        mode='lines+markers',
                        name="1. Inventario Vivo en Campo (Corto Plazo: S1-S10)",
                        line=dict(color='#059669', width=3.2),
                        marker=dict(size=7, symbol='circle'),
                        hovertemplate="<b>Semana %{x}</b><br>🟢 Inventario Vivo: %{y:,.0f} tallos<extra></extra>"
                    ))

                    sems_plan = semanas_futuras[limite_corto_plazo - 1:]
                    y_plan = y_fc[limite_corto_plazo - 1:]
                    fig_fc.add_trace(go.Scatter(
                        x=sems_plan,
                        y=y_plan,
                        mode='lines+markers',
                        name="2. Siembras Programadas Pedido (Mediano Plazo: S11+)",
                        line=dict(color='#7C3AED', width=3.2, dash='solid'),
                        marker=dict(size=8, symbol='diamond'),
                        hovertemplate="<b>Semana %{x}</b><br>🟣 Proyección Pedido: %{y:,.0f} tallos<extra></extra>"
                    ))

                # Trazo 3: Demanda Comercial Aprobada (Azul SAP Fiori #0070F2 dash)
                fig_fc.add_trace(go.Scatter(
                    x=semanas_futuras,
                    y=plan_series_cap,
                    mode='lines+markers',
                    name="Demanda Comercial (Plan Aprobado)",
                    line=dict(color='#0070F2', width=2.8, dash='dash'),
                    marker=dict(size=6, symbol='square'),
                    hovertemplate="<b>Semana %{x}</b><br>🟦 Demanda Aprobada: %{y:,.0f} tallos<extra></extra>"
                ))

                fig_fc.update_layout(
                    title=dict(text=f"Balance S&OP: Proyección de Oferta vs Demanda Comercial ({vista})", font=dict(size=15, color="#1C2D42", family="'72', Inter, sans-serif")),
                    xaxis=dict(
                        type='category',
                        categoryorder='array',
                        categoryarray=semanas_futuras,
                        title="Semana Operativa",
                        tickangle=-45,
                        fixedrange=True
                    ),
                    yaxis=dict(
                        title="Tallos Proyectados",
                        tickformat=",.0f",
                        fixedrange=True
                    ),
                    hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    margin=dict(l=40, r=40, t=60, b=40)
                )
                estilizar_figura_plotly(fig_fc)
                st.plotly_chart(fig_fc, width='stretch', config={'scrollZoom': False, 'displayModeBar': False})

                # TABLA SEMANAL S&OP TRANSPUESTA INMEDIATAMENTE DEBAJO DEL GRÁFICO (SIN HORIZONTE)
                st.markdown("#### 📋 Balance Semanal S&OP: Oferta vs Demanda")
                
                conceptos = [
                    'ForeCast Biológico (Oferta)',
                    'Demanda Comercial (Plan)',
                    'Brecha / Gap (Tallos)',
                    '% Cumplimiento',
                    'Estado S&OP'
                ]
                
                cols_semanas_tbl = semanas_futuras + ['TOTAL']
                df_trans = pd.DataFrame(index=conceptos, columns=cols_semanas_tbl)

                for s in semanas_futuras:
                    fc_val = fc_agrupado.get(s, 0.0)
                    plan_val = plan_series_cap.get(s, 0.0)
                    gap_val = fc_val - plan_val
                    pct_val = (fc_val / plan_val * 100.0) if plan_val > 0 else 100.0
                    
                    if plan_val == 0:
                        est = '⚪ Sin Meta'
                    elif pct_val < 90:
                        est = '🔴 Déficit'
                    elif pct_val <= 110:
                        est = '🟢 Balanceado'
                    else:
                        est = '🔵 Superávit'
                        
                    df_trans.loc['ForeCast Biológico (Oferta)', s] = f"{fc_val:,.0f}"
                    df_trans.loc['Demanda Comercial (Plan)', s] = f"{plan_val:,.0f}"
                    df_trans.loc['Brecha / Gap (Tallos)', s] = f"{gap_val:+,.0f}"
                    df_trans.loc['% Cumplimiento', s] = f"{pct_val:.1f}%"
                    df_trans.loc['Estado S&OP', s] = est

                # Columna de Totales
                tot_est = '🟢 Balanceado' if 90 <= cumpl_global <= 110 else ('🔴 Déficit' if cumpl_global < 90 else '🔵 Superávit')
                df_trans.loc['ForeCast Biológico (Oferta)', 'TOTAL'] = f"{tot_fc:,.0f}"
                df_trans.loc['Demanda Comercial (Plan)', 'TOTAL'] = f"{tot_plan:,.0f}"
                df_trans.loc['Brecha / Gap (Tallos)', 'TOTAL'] = f"{brecha_tot:+,.0f}"
                df_trans.loc['% Cumplimiento', 'TOTAL'] = f"{cumpl_global:.1f}%"
                df_trans.loc['Estado S&OP', 'TOTAL'] = tot_est

                df_trans_display = df_trans.reset_index().rename(columns={'index': 'Concepto S&OP'})

                st.dataframe(
                    df_trans_display,
                    width='stretch',
                    hide_index=True
                )

                col_dl_bal, _ = st.columns([1, 2])
                with col_dl_bal:
                    csv_trans = df_trans_display.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="⬇️ Descargar Balance Semanal Transpuesto (CSV)",
                        data=csv_trans,
                        file_name=f"Balance_Semanal_SOP_{vista.replace(' ', '_')}.csv",
                        mime="text/csv",
                        key="dl_balance_semanal_transpuesto_csv"
                    )

        # =====================================================================
        # PESTAÑA 2: DIAGNÓSTICO DE BRECHAS (FLOR / COLOR / VARIEDAD)
        # =====================================================================
        with tab_gap:
            st.subheader("🔍 Diagnóstico Detallado de Brechas por Flor, Color y Variedad")
            st.markdown("Auditoría a nivel de SKU para identificar qué variedades presentan déficit o superávit frente a la demanda comercial aprobada.")

            col_g1, col_g2 = st.columns(2)
            with col_g1:
                opc_sem_gap = ["Consolidado Horizonte Completo"] + semanas_futuras
                sel_sem_gap = st.selectbox("Semana Operativa a Auditar:", opc_sem_gap, key="sel_sem_gap")
            with col_g2:
                flores_disp_gap = ["Todas"] + sorted(list(df_forecast['Flor'].dropna().unique()))
                sel_flor_gap = st.selectbox("Filtrar por Flor:", flores_disp_gap, key="sel_flor_gap")

            # Construir tabla de brechas por SKU
            meta_cols = [c for c in ['Flor', 'Color', 'Variedad'] if c in df_forecast.columns]
            
            if sel_sem_gap == "Consolidado Horizonte Completo":
                sems_evaluar = semanas_futuras
                df_fc_sku = df_forecast.groupby(meta_cols)[sems_evaluar].sum().sum(axis=1).reset_index(name='ForeCast Biológico (Oferta)')
            else:
                sems_evaluar = [sel_sem_gap]
                df_fc_sku = df_forecast.groupby(meta_cols)[sel_sem_gap].sum().reset_index(name='ForeCast Biológico (Oferta)')

            # Plan comercial por SKU
            if not df_plan_app.empty and 'Variedad' in df_plan_app.columns:
                col_cap = 'Tallos a Producir (Capacidad)' if 'Tallos a Producir (Capacidad)' in df_plan_app.columns else 'Suma de Tallos'
                sems_clean_set = set([s.split(' ')[0] for s in sems_evaluar])
                df_plan_filtrado = df_plan_app[df_plan_app['Semana'].isin(sems_clean_set)].copy()
                df_plan_sku = df_plan_filtrado.groupby(['Flor', 'Color', 'Variedad'])[col_cap].sum().reset_index(name='Demanda Comercial (Plan)')
            else:
                df_plan_sku = pd.DataFrame(columns=['Flor', 'Color', 'Variedad', 'Demanda Comercial (Plan)'])

            # Merge por SKU
            df_gap_sku = pd.merge(df_fc_sku, df_plan_sku, on=['Flor', 'Color', 'Variedad'], how='outer').fillna(0.0)

            if sel_flor_gap != "Todas":
                df_gap_sku = df_gap_sku[df_gap_sku['Flor'] == sel_flor_gap]

            # Filtrar filas sin actividad en oferta ni demanda
            df_gap_sku = df_gap_sku[(df_gap_sku['ForeCast Biológico (Oferta)'] > 0) | (df_gap_sku['Demanda Comercial (Plan)'] > 0)].copy()

            df_gap_sku['Brecha / Gap (Tallos)'] = df_gap_sku['ForeCast Biológico (Oferta)'] - df_gap_sku['Demanda Comercial (Plan)']
            df_gap_sku['% Cumplimiento'] = df_gap_sku.apply(
                lambda r: (r['ForeCast Biológico (Oferta)'] / r['Demanda Comercial (Plan)'] * 100) if r['Demanda Comercial (Plan)'] > 0 else (100.0 if r['ForeCast Biológico (Oferta)'] > 0 else 0.0),
                axis=1
            )

            def _diag_sku(r):
                p = r['Demanda Comercial (Plan)']
                fc = r['ForeCast Biológico (Oferta)']
                if p == 0:
                    return '🔵 Solo Oferta'
                if fc == 0:
                    return '🔴 Sin Oferta (Déficit Total)'
                pct = (fc / p) * 100
                if pct < 85:
                    return '🔴 Déficit Crítico'
                elif pct < 95:
                    return '🟡 Déficit Menor'
                elif pct <= 105:
                    return '🟢 Balanceado'
                else:
                    return '🔵 Superávit'

            df_gap_sku['Diagnóstico S&OP'] = df_gap_sku.apply(_diag_sku, axis=1)
            df_gap_sku = df_gap_sku.sort_values(by=['Brecha / Gap (Tallos)', 'Flor', 'Variedad'], ascending=[True, True, True])

            # Métricas resumen del diagnóstico
            tot_skus = len(df_gap_sku)
            skus_def = (df_gap_sku['Brecha / Gap (Tallos)'] < -500).sum()
            skus_bal = ((df_gap_sku['Brecha / Gap (Tallos)'] >= -500) & (df_gap_sku['Brecha / Gap (Tallos)'] <= 500)).sum()
            skus_sup = (df_gap_sku['Brecha / Gap (Tallos)'] > 500).sum()

            cd1, cd2, cd3, cd4 = st.columns(4)
            cd1.metric("SKUs Evaluados", f"{tot_skus:,}")
            cd2.metric("En Déficit Crítico", f"{skus_def:,}", f"{(skus_def/tot_skus*100 if tot_skus>0 else 0):.1f}% del mix", delta_color="inverse")
            cd3.metric("Balanceados / En Meta", f"{skus_bal:,}", f"{(skus_bal/tot_skus*100 if tot_skus>0 else 0):.1f}% del mix")
            cd4.metric("En Superávit", f"{skus_sup:,}", f"{(skus_sup/tot_skus*100 if tot_skus>0 else 0):.1f}% del mix")

            st.markdown("")
            st.dataframe(
                df_gap_sku.style.format({
                    'ForeCast Biológico (Oferta)': '{:,.0f}',
                    'Demanda Comercial (Plan)': '{:,.0f}',
                    'Brecha / Gap (Tallos)': '{:+,.0f}',
                    '% Cumplimiento': '{:.1f}%'
                }),
                width='stretch',
                hide_index=True
            )

            col_dl_gap, _ = st.columns([1, 2])
            with col_dl_gap:
                csv_gap = df_gap_sku.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="⬇️ Descargar Diagnóstico de Brechas (CSV)",
                    data=csv_gap,
                    file_name=f"Diagnostico_Brechas_SKU_{sel_sem_gap.replace(' ', '_')}.csv",
                    mime="text/csv",
                    key="dl_gap_sku_csv"
                )

        # =====================================================================
        # PESTAÑA 3: MATRIZ DE PRODUCCIÓN (52 SEMANAS)
        # =====================================================================
        with tab_matriz:
            df_fc_matrix = df_forecast.copy()
            df_fc_matrix['TOTAL'] = df_fc_matrix[semanas_futuras].sum(axis=1) if semanas_futuras else 0
            df_fc_matrix = df_fc_matrix[df_fc_matrix['TOTAL'] > 0]
            
            st.subheader("Resumen Total por Flor")
            if semanas_futuras:
                resumen_flor = df_fc_matrix.groupby('Flor')[semanas_futuras + ['TOTAL']].sum()
                total_row_flor = pd.DataFrame(resumen_flor.sum()).T
                total_row_flor.index = ['TOTAL GENERAL']
                resumen_flor = pd.concat([resumen_flor, total_row_flor])
                st.dataframe(resumen_flor.style.format("{:,.0f}"), width='stretch')

            st.markdown("")
            st.subheader("Matriz ForeCast Detallada")
            if semanas_futuras:
                cols_num = semanas_futuras + ['TOTAL']
                total_row = pd.DataFrame(df_fc_matrix[cols_num].sum()).T
                for col in ['Sede', 'Flor', 'Color', 'Variedad']:
                    if col in df_fc_matrix.columns:
                        total_row[col] = ""
                total_row['Variedad'] = 'TOTAL GENERAL'
                meta_cols = [c for c in ['Sede', 'Flor', 'Color', 'Variedad'] if c in df_fc_matrix.columns]
                df_fc_display = df_fc_matrix[meta_cols + cols_num].copy()
                df_fc_display = pd.concat([df_fc_display, total_row], ignore_index=True)
                st.dataframe(df_fc_display.style.format(formatter={col: "{:,.0f}" for col in cols_num}), width='stretch')

                col_dl_mat, _ = st.columns([1, 2])
                with col_dl_mat:
                    csv_matriz = df_fc_display.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="⬇️ Descargar Matriz ForeCast Completa (CSV)",
                        data=csv_matriz,
                        file_name=f"Matriz_ForeCast_{vista.replace(' ', '_')}.csv",
                        mime="text/csv",
                        key="dl_matriz_fc_csv"
                    )

        # =====================================================================
        # PESTAÑA 4: EXPORTACIÓN A PLATAFORMAS (WEBFLOWERS & 52 SEMANAS)
        # =====================================================================
        with tab_wf:
            st.subheader("📤 Exportación de Proyecciones a Plataformas")
            st.markdown("Generación de archivos oficiales para Webflowers (13 semanas móviles) y proyecciones de largo plazo (52 semanas).")

            tab_exp_13, tab_exp_52 = st.tabs(["Exportación Webflowers (13 Semanas)", "Exportación Anual (52 Semanas)"])
            
            with tab_exp_13:
                st.markdown("#### Exportación Webflowers (13 Semanas)")
                st.info("💡 **Regla S&OP Webflowers (13 Semanas):** Proyección a partir de la siguiente semana operativa conformada por exactamente **9 semanas de Inventario Vivo en suelo** + **4 semanas de Plan Maestro Factible**, manteniendo la rigurosidad de la capacidad instalada y sin inflar cifras.")
                
                col_up1, col_up2 = st.columns([1.5, 1])
                with col_up1:
                    uploaded_templates = st.file_uploader("📥 Subir Plantillas Webflowers Vacías (Excel)", type=["xlsx", "xls"], accept_multiple_files=True, key="uploader_wf_13")
                with col_up2:
                    st.caption("Carga los archivos base descargados de Webflowers. El sistema conservará la estructura y formatos originales inyectando los valores correspondientes.")

                if uploaded_templates:
                    if st.button("Procesar y Llenar Plantillas 13 Wk", type="primary", key="btn_procesar_wf13"):
                        with st.spinner("Generando proyecciones e inyectando datos en las plantillas..."):
                            df_plan = None
                            if os.path.exists("Plan_Aprobado.csv"):
                                try:
                                    df_p_raw = pd.read_csv("Plan_Aprobado.csv")
                                    col_t = 'Tallos a Producir (Capacidad)' if 'Tallos a Producir (Capacidad)' in df_p_raw.columns else 'Suma de Tallos'
                                    df_p_raw['Semana'] = df_p_raw['Semana'].apply(lambda v: str(int(float(v))) if pd.notna(v) and str(v).replace('.','',1).isdigit() else str(v).strip())
                                    df_plan = df_p_raw.pivot_table(index='Variedad', columns='Semana', values=col_t, aggfunc='sum', fill_value=0)
                                    df_plan.index = df_plan.index.astype(str).str.strip().str.lower()
                                except Exception:
                                    df_plan = None
                            elif not df_mrp.empty:
                                df_proyeccion_mva = proyectar_cosecha_desde_mva(df_mrp, db)
                                if not df_proyeccion_mva.empty:
                                    df_plan = df_proyeccion_mva.copy()
                                    df_plan['Variedad_norm'] = df_plan['Variedad'].astype(str).str.strip().str.lower()
                                    cols_num_mva = [c for c in df_plan.columns if str(c).startswith('202')]
                                    df_plan = df_plan.groupby('Variedad_norm')[cols_num_mva].sum()
                                    
                            from scripts.export_plataforma import procesar_plantillas_plataforma
                            
                            templates_dict = {f.name: f.getvalue() for f in uploaded_templates}
                            resultados = procesar_plantillas_plataforma(templates_dict, df_forecast_vivo, df_plan)
                            
                            if resultados:
                                st.success(f"✅ Se procesaron {len(resultados)} de {len(uploaded_templates)} plantillas exitosamente.")
                            
                            faltantes = [name for name in templates_dict if name not in resultados]
                            if faltantes:
                                st.warning(f"⚠️ Las siguientes plantillas no pudieron procesarse: {', '.join(faltantes)}")
                            
                            import base64
                            import streamlit.components.v1 as components
                            
                            files_data = []
                            for filename, filebytes in resultados.items():
                                b64 = base64.b64encode(filebytes).decode("utf-8")
                                files_data.append({"filename": filename, "b64": b64})
                            
                            if len(resultados) == 1:
                                fname, fbytes = next(iter(resultados.items()))
                                st.download_button(
                                    label=f"⬇️ Descargar {fname}",
                                    data=fbytes,
                                    file_name=fname,
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    type="primary",
                                    key="dl_single_wf13"
                                )
                            elif len(resultados) > 1:
                                js_code = f"""
                                <script>
                                function downloadAll() {{
                                    const files = {json.dumps(files_data)};
                                    files.forEach((file, index) => {{
                                        setTimeout(() => {{
                                            const link = document.createElement("a");
                                            link.href = "data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64," + file.b64;
                                            link.download = file.filename;
                                            document.body.appendChild(link);
                                            link.click();
                                            document.body.removeChild(link);
                                        }}, index * 500); 
                                    }});
                                }}
                                </script>
                                <button onclick="downloadAll()" style="background-color: #0070F2; border: 1px solid #0056B3; color: white; padding: 9px 20px; text-align: center; text-decoration: none; display: inline-block; font-size: 14px; margin: 4px 2px; cursor: pointer; border-radius: 6px; font-family: '72', Inter, -apple-system, sans-serif; font-weight: 600; box-shadow: 0 1px 2px rgba(0,112,242,0.2);">
                                    ⬇️ Descargar Todos los Archivos (1 Clic)
                                </button>
                                """
                                components.html(js_code, height=60)
                                
                                with st.expander("Descargas Individuales", expanded=False):
                                    for filename, filebytes in resultados.items():
                                        st.download_button(
                                            label=f"⬇️ {filename}",
                                            data=filebytes,
                                            file_name=filename,
                                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                            key=f"dl_13_{filename}"
                                        )

            with tab_exp_52:
                st.markdown("#### Exportación Anual (52 Semanas)")
                st.info("🕒 **Línea de Tiempo Operativa**: Pedido Confirmado / Recepción (Semana **S**) ➔ 3 Semanas Enraizamiento ➔ Siembra a Campo (Semana **S+4**).")
                
                uploaded_templates_52 = st.file_uploader(
                    "📋 Cargar Plantilla(s) Vacía(s) 52 Semanas (Excel)", 
                    type=["xlsx", "xls"], 
                    accept_multiple_files=True,
                    key="uploader_wf_52"
                )
                
                if uploaded_templates_52:
                    if st.button("Procesar y Llenar Plantilla(s) 52 Semanas", type="primary", key="btn_procesar_wf52"):
                        with st.spinner("Procesando archivos para proyección 52 semanas..."):
                            import io
                            import base64
                            import streamlit.components.v1 as components
                            
                            output_mrp = io.BytesIO()
                            if not df_mrp.empty:
                                with pd.ExcelWriter(output_mrp, engine='xlsxwriter') as writer:
                                    df_mrp.to_excel(writer, index=False, sheet_name="Explosion_MVA")
                                
                            df_proy_mva = proyectar_cosecha_desde_mva(df_mrp, db) if not df_mrp.empty else pd.DataFrame()
                            df_52_semanas = combinar_proyecciones_52_semanas(df_forecast_vivo, df_proy_mva)
                            
                            resultados_52 = {}
                            errores_52 = {}
                            for f in uploaded_templates_52:
                                try:
                                    filled_template_bytes = llenar_plantilla_52_semanas(f.getvalue(), df_52_semanas)
                                    resultados_52[f.name] = filled_template_bytes
                                except Exception as e:
                                    errores_52[f.name] = str(e)
                        
                            if resultados_52:
                                st.success(f"✅ Se procesaron {len(resultados_52)} de {len(uploaded_templates_52)} plantillas exitosamente.")
                            
                            if errores_52:
                                for fname, err in errores_52.items():
                                    st.error(f"❌ Error procesando {fname}: {err}")
                        
                            col_dl1, col_dl2 = st.columns(2)
                            if not df_mrp.empty:
                                col_dl1.download_button(
                                    label="⬇️ Descargar Plan de Siembras (MVA)",
                                    data=output_mrp.getvalue(),
                                    file_name="Plan_Siembras_Proyectadas.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    key="dl_mva_plan_52"
                                )
                            
                            if len(resultados_52) == 1:
                                fname, fbytes = next(iter(resultados_52.items()))
                                col_dl2.download_button(
                                    label=f"⬇️ Descargar {fname}",
                                    data=fbytes,
                                    file_name=fname,
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    type="primary",
                                    key="dl_single_wf52"
                                )
                            elif len(resultados_52) > 1:
                                files_data_52 = []
                                for filename, filebytes in resultados_52.items():
                                    b64 = base64.b64encode(filebytes).decode("utf-8")
                                    files_data_52.append({"filename": filename, "b64": b64})
                                
                                js_code_52 = f"""
                                <script>
                                function downloadAll52() {{
                                    const files = {json.dumps(files_data_52)};
                                    files.forEach((file, index) => {{
                                        setTimeout(() => {{
                                            const link = document.createElement("a");
                                            link.href = "data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64," + file.b64;
                                            link.download = file.filename;
                                            document.body.appendChild(link);
                                            link.click();
                                            document.body.removeChild(link);
                                        }}, index * 500); 
                                    }});
                                }}
                                </script>
                                <button onclick="downloadAll52()" style="background-color: #0070F2; border: 1px solid #0056B3; color: white; padding: 9px 20px; text-align: center; text-decoration: none; display: inline-block; font-size: 14px; margin: 4px 2px; cursor: pointer; border-radius: 6px; font-family: '72', Inter, -apple-system, sans-serif; font-weight: 600; box-shadow: 0 1px 2px rgba(0,112,242,0.2);">
                                    ⬇️ Descargar Todos los Archivos 52 Wk (1 Clic)
                                </button>
                                """
                                with col_dl2:
                                    components.html(js_code_52, height=60)
                                
                                with st.expander("Descargas Individuales (52 Semanas)", expanded=False):
                                    for fname, fbytes in resultados_52.items():
                                        st.download_button(
                                            label=f"⬇️ {fname}",
                                            data=fbytes,
                                            file_name=fname,
                                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                            key=f"dl_52_{fname}"
                                        )

elif modulo == "Programación Diaria y Temporadas":
    st.header("📅 Programación Diaria y Gestión de Temporadas")
    st.markdown("Configura la distribución diaria de cortes y haz seguimiento al volumen de las temporadas críticas.")
    
    def ajustar_porcentajes_enteros(pct_dict):
        """
        Ajusta una distribución de porcentajes a números enteros de modo que
        la suma sea EXACTAMENTE 100%, utilizando el método del residuo mayor (Hamilton/Hare).
        Garantiza que la aproximación nunca supere ni quede por debajo del 100%.
        """
        import math
        dias_activos = [d for d, v in pct_dict.items() if v > 0]
        if not dias_activos:
            return {d: 0 for d in pct_dict}
            
        floors = {d: int(math.floor(pct_dict[d])) for d in dias_activos}
        remainders = {d: pct_dict[d] - floors[d] for d in dias_activos}
        
        suma_floors = sum(floors.values())
        faltante = 100 - suma_floors
        
        # Ordenar los días activos según su residuo decimal de mayor a menor
        dias_ordenados = sorted(dias_activos, key=lambda d: remainders[d], reverse=True)
        
        resultado = {d: 0 for d in pct_dict}
        for d in dias_activos:
            resultado[d] = floors[d]
            
        for i in range(faltante):
            d = dias_ordenados[i % len(dias_ordenados)]
            resultado[d] += 1
            
        return resultado
    
    tab1, tab2 = st.tabs(["Distribución de Corte Diario", "Seguimiento de Temporadas"])
    
    with tab1:
        st.subheader("Porcentajes de Corte Diario por Flor")
        st.markdown("Asigna cómo se distribuye el volumen proyectado de la semana entre los días de corte.")
        
        flores_db = sorted(list(set([v.flor for v in db.query(Variedad).all() if v.flor])))
        
        from app.services.enraizamiento_service import (
            HORAS_JORNADA, 
            TOTAL_HORAS_SEMANA_ESTANDAR,
            HORAS_JORNADA_TEMPORADA,
            TOTAL_HORAS_SEMANA_TEMPORADA
        )
        
        # Horarios base efectivos (con deducción de 30 min de almuerzo L-V; Sábado continuo):
        # Lunes, Martes, Jueves, Viernes: 7.5h | Miércoles: 7.0h | Sábado: 5.0h | Domingo: 0.0h
        # Total normal = 7.5 + 7.5 + 7.0 + 7.5 + 7.5 + 5.0 = 42.0h efectivas
        horas = HORAS_JORNADA.copy()
        total_horas = TOTAL_HORAS_SEMANA_ESTANDAR
        
        pct_base_raw = {dia: (h / total_horas) * 100.0 for dia, h in horas.items()}
        pct_base_int = ajustar_porcentajes_enteros(pct_base_raw)
        
        config_diario = {}
        for flor in flores_db:
            c = pct_base_int.copy()
            c["Total"] = sum(pct_base_int.values())
            config_diario[flor] = c
        
        df_config = pd.DataFrame(config_diario).T.reset_index().rename(columns={"index": "Flor"})
        
        col_ed1, col_ed2 = st.columns([2, 1])
        with col_ed1:
            dias_cols = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo", "Total"]
            format_config = {d: "{:.0f}%" for d in dias_cols}
            st.dataframe(df_config.style.format(format_config), width='stretch', hide_index=True)
            
        with col_ed2:
            st.info(f"💡 **Nota de Capacidad**: Estos porcentajes reflejan la jornada laboral efectiva con deducción de 30 min de almuerzo de lunes a viernes (Lun, Mar, Jue, Vie: 7.5h | Mié: 7.0h | Sáb: 5.0h = **{TOTAL_HORAS_SEMANA_ESTANDAR:.1f}h efectivas/semana**).")
            st.info(f"🔥 **Temporadas**: Los Domingos solo se activarán automáticamente si la semana a desagregar pertenece a las temporadas de 'San valentin' o 'madres' (+5.0h domingo = **{TOTAL_HORAS_SEMANA_TEMPORADA:.1f}h efectivas**).")
            
        st.divider()
        st.subheader("Generar Plan de Corte Diario")
        col_gen1, col_gen2 = st.columns(2)
        semana_target = col_gen1.text_input("Semana a desagregar (ej. 202640):")
        lunes_festivo = col_gen2.checkbox("¿La semana seleccionada tiene Lunes Festivo?")
        
        if st.button("Calcular Corte Diario"):
            if not semana_target:
                st.warning("Por favor ingresa una semana válida.")
            else:
                with st.spinner("Desagregando proyección..."):
                    df_forecast_vivo = generar_forecast_13wk(db)
                    
                    from app.services.mva_service import generar_plan_mva, proyectar_cosecha_desde_mva, combinar_proyecciones_52_semanas
                    file_path = "PedidoConsolidado_master.xlsx"
                    if os.path.exists(file_path):
                        df_mrp = generar_plan_mva(file_path, week_is="Pedido")
                        df_proyeccion_mva = proyectar_cosecha_desde_mva(df_mrp, db)
                        df_52 = combinar_proyecciones_52_semanas(df_forecast_vivo, df_proyeccion_mva)
                    else:
                        df_52 = df_forecast_vivo
                        
                    if semana_target not in df_52.columns:
                        st.error(f"La semana {semana_target} no tiene proyecciones disponibles.")
                    else:
                        df_week = df_52[['Flor', 'Color', 'Variedad', semana_target]].copy()
                        df_week = df_week[df_week[semana_target] > 0]
                        
                        # Determinar si la semana objetivo está en temporada de domingos
                        es_temporada_domingo = False
                        seasons_file = "config_temporadas.json"
                        if os.path.exists(seasons_file):
                            with open(seasons_file, "r", encoding="utf-8") as f:
                                saved_seasons = json.load(f)
                        else:
                            saved_seasons = [
                                {"Temporada": "Fall", "Semana Inicio": 202632, "Semana Fin": 202646},
                                {"Temporada": "Navidad", "Semana Inicio": 202647, "Semana Fin": 202650},
                                {"Temporada": "San valentin", "Semana Inicio": 202703, "Semana Fin": 202705},
                                {"Temporada": "Madres", "Semana Inicio": 202716, "Semana Fin": 202718},
                                {"Temporada": "Summer", "Semana Inicio": 202719, "Semana Fin": 202731}
                            ]
                        
                        try:
                            sem_target_int = int(semana_target)
                            for s in saved_seasons:
                                name_lower = str(s.get("Temporada", "")).lower()
                                import unicodedata
                                name_lower = ''.join(c for c in unicodedata.normalize('NFD', name_lower) if unicodedata.category(c) != 'Mn')
                                if name_lower in ["san valentin", "madres"]:
                                    ini = s.get("Semana Inicio", 0)
                                    fin = s.get("Semana Fin", 0)
                                    w_ini = ini % 100 if ini > 100 else ini
                                    w_fin = fin % 100 if fin > 100 else fin
                                    week_target = sem_target_int % 100
                                    
                                    if w_ini <= w_fin:
                                        in_season = (w_ini <= week_target <= w_fin)
                                    else:
                                        in_season = (week_target >= w_ini or week_target <= w_fin)
                                        
                                    if in_season:
                                        es_temporada_domingo = True
                                        break
                        except ValueError:
                            pass

                        records_diarios = []
                        records_pcts = []
                        dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
                        
                        for _, row in df_week.iterrows():
                            flor = row['Flor']
                            vol_semanal = int(round(row[semana_target]))
                            
                            if es_temporada_domingo:
                                # Temporada con domingo activo: 7.5h L,M,J,V, 7.0h Mie, 5.0h Sab, 5.0h Dom = 47.0h efectivas
                                h_temp = HORAS_JORNADA_TEMPORADA.copy()
                                tot_temp = TOTAL_HORAS_SEMANA_TEMPORADA
                                pcts_float = {d: (h_temp[d] / tot_temp) * 100.0 for d in dias}
                            else:
                                pcts_float = {d: (horas[d] / total_horas) * 100.0 for d in dias}
                            
                            if lunes_festivo and pcts_float["Lunes"] > 0:
                                pct_a_repartir = pcts_float["Lunes"]
                                pcts_float["Lunes"] = 0.0
                                # Repartir proporcionalmente entre los días activos
                                dias_activos = [d for d in dias if d != "Lunes" and pcts_float[d] > 0]
                                if dias_activos:
                                    extra_por_dia = pct_a_repartir / len(dias_activos)
                                    for d in dias_activos:
                                        pcts_float[d] += extra_por_dia
                                        
                            # 1. Ajuste matemático a enteros garantizando que sumen EXACTAMENTE 100%
                            pcts_enteros = ajustar_porcentajes_enteros(pcts_float)
                            
                            # 2. Calcular tallos a partir de los porcentajes enteros exactos
                            tallos_diarios = {d: int(round(vol_semanal * (pcts_enteros[d] / 100.0))) for d in dias}
                            
                            # Ajuste por redondeo para que los tallos sumen exactamente el volumen semanal
                            suma_calc = sum(tallos_diarios.values())
                            diff = vol_semanal - suma_calc
                            if diff != 0:
                                dias_con_corte = [d for d in dias if pcts_enteros[d] > 0]
                                dia_max = max(dias_con_corte, key=lambda d: tallos_diarios[d])
                                tallos_diarios[dia_max] += diff
                                
                            rec = {
                                "Flor": flor,
                                "Color": row['Color'],
                                "Variedad": row['Variedad'],
                                "Vol. Semanal": vol_semanal
                            }
                            rec.update(tallos_diarios)
                            rec["Total Tallos"] = sum(tallos_diarios.values())
                            records_diarios.append(rec)
                            
                            rec_pct = {
                                "Flor": flor,
                                "Color": row['Color'],
                                "Variedad": row['Variedad']
                            }
                            rec_pct.update({d: pcts_enteros[d] for d in dias})
                            rec_pct["Total %"] = sum(pcts_enteros[d] for d in dias)
                            records_pcts.append(rec_pct)
                            
                        if records_diarios:
                            df_pcts = pd.DataFrame(records_pcts)
                            df_diario = pd.DataFrame(records_diarios)
                            
                            st.success(f"Distribución generada para {len(df_diario)} variedades en la semana {semana_target}.")
                            
                            st.markdown("#### Distribución en Porcentajes (Enteros exactos al 100%)")
                            cols_pct = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo", "Total %"]
                            format_dict = {d: "{:.0f}%" for d in cols_pct}
                            st.dataframe(df_pcts.style.format(format_dict), width='stretch')
                            
                            st.markdown("#### Distribución en Tallos Diarios")
                            cols_tallos = ["Vol. Semanal", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo", "Total Tallos"]
                            format_tallos = {col: "{:,.0f}" for col in cols_tallos}
                            st.dataframe(df_diario.style.format(format_tallos), width='stretch')
                            
                            import io
                            output = io.BytesIO()
                            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                                df_diario.to_excel(writer, index=False, sheet_name=f"Corte_{semana_target}")
                            
                            st.download_button(
                                label="⬇️ Descargar Distribución Diaria (Excel)",
                                data=output.getvalue(),
                                file_name=f"Distribucion_Corte_{semana_target}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                type="primary"
                            )
                        else:
                            st.info("No hay proyecciones para desagregar en esta semana.")

    with tab2:
        st.subheader("Configuración de Temporadas")
        st.markdown("Define las semanas que componen cada temporada. **Nota:** Puedes agregar nuevas temporadas en la tabla usando el botón '+' al final (ej. Easter o San Patricio). 'Every Day' se calcula automáticamente como el restante.")
        
        seasons_file = "config_temporadas.json"
        if os.path.exists(seasons_file):
            with open(seasons_file, "r", encoding="utf-8") as f:
                seasons = json.load(f)
        else:
            seasons = [
                {"Temporada": "Fall", "Semana Inicio": 202632, "Semana Fin": 202646},
                {"Temporada": "Navidad", "Semana Inicio": 202647, "Semana Fin": 202650},
                {"Temporada": "San valentin", "Semana Inicio": 202703, "Semana Fin": 202705},
                {"Temporada": "Madres", "Semana Inicio": 202716, "Semana Fin": 202718},
                {"Temporada": "Summer", "Semana Inicio": 202719, "Semana Fin": 202731}
            ]
            
        df_seasons = pd.DataFrame(seasons)
        df_seasons_edited = st.data_editor(df_seasons, num_rows="dynamic", width='stretch')
        
        if st.button("Guardar Temporadas"):
            with open(seasons_file, "w", encoding="utf-8") as f:
                json.dump(df_seasons_edited.to_dict(orient="records"), f, indent=4)
            st.success("Temporadas actualizadas.")
            
        st.divider()
        st.subheader("Seguimiento de Temporadas")
        st.markdown("Volumen total proyectado (Inventario Vivo + Pedido Consolidado MVA) para cada temporada.")
        
        with st.spinner("Analizando comportamiento de temporadas..."):
            df_forecast_vivo = generar_forecast_13wk(db)
            from app.services.mva_service import generar_plan_mva, proyectar_cosecha_desde_mva, combinar_proyecciones_52_semanas
            file_path = "PedidoConsolidado_master.xlsx"
            if os.path.exists(file_path):
                df_mrp = generar_plan_mva(file_path, week_is="Pedido")
                df_proyeccion_mva = proyectar_cosecha_desde_mva(df_mrp, db)
                df_52 = combinar_proyecciones_52_semanas(df_forecast_vivo, df_proyeccion_mva)
            else:
                df_52 = df_forecast_vivo
                
            results = []
            cols = [c for c in df_52.columns if str(c).startswith('202')]
            used_cols = set()
            
            for _, s in df_seasons_edited.iterrows():
                name = str(s.get("Temporada", ""))
                start = str(int(s["Semana Inicio"])) if pd.notna(s.get("Semana Inicio")) else ""
                end = str(int(s["Semana Fin"])) if pd.notna(s.get("Semana Fin")) else ""
                try:
                    ini = int(float(s.get("Semana Inicio", 0)))
                    fin = int(float(s.get("Semana Fin", 0)))
                except:
                    ini = 0
                    fin = 0
                
                w_ini = ini % 100 if ini > 100 else ini
                w_fin = fin % 100 if fin > 100 else fin
                
                valid_cols = []
                for c in cols:
                    try:
                        w_c = int(str(c)) % 100
                        if w_ini <= w_fin:
                            if w_ini <= w_c <= w_fin:
                                valid_cols.append(c)
                        else:
                            if w_c >= w_ini or w_c <= w_fin:
                                valid_cols.append(c)
                    except:
                        pass
                
                used_cols.update(valid_cols)
                
                total_vol = df_52[valid_cols].sum().sum() if valid_cols else 0
                    
                results.append({
                    "Temporada": name, 
                    "Rango": f"{start} - {end}", 
                    "Semanas Activas": len(valid_cols), 
                    "Tallos Proyectados": total_vol,
                    "_sort": start if start else "999999"
                })
                
            # Calculamos Every Day con el restante
            valid_cols = [c for c in cols if c not in used_cols]
            total_vol = df_52[valid_cols].sum().sum() if valid_cols else 0
                
            results.append({
                "Temporada": "Every Day", 
                "Rango": "Semanas restantes", 
                "Semanas Activas": len(valid_cols), 
                "Tallos Proyectados": total_vol,
                "_sort": "999999" # Every Day al final
            })
                
            df_res_seasons = pd.DataFrame(results)
            if not df_res_seasons.empty:
                df_res_seasons = df_res_seasons.sort_values(by="_sort").drop(columns=["_sort"]).reset_index(drop=True)
                
                # Crear dataframe para visualización con fila de totales
                df_res_seasons_display = df_res_seasons.copy()
                total_semanas = df_res_seasons_display["Semanas Activas"].sum()
                total_tallos = df_res_seasons_display["Tallos Proyectados"].sum()
                
                total_row = pd.DataFrame([{
                    "Temporada": "TOTAL",
                    "Rango": "-",
                    "Semanas Activas": total_semanas,
                    "Tallos Proyectados": total_tallos
                }])
                df_res_seasons_display = pd.concat([df_res_seasons_display, total_row], ignore_index=True)
            else:
                df_res_seasons_display = df_res_seasons.copy()
            
            col_chart1, col_chart2 = st.columns([1, 2])
            with col_chart1:
                st.dataframe(df_res_seasons_display.style.format({"Tallos Proyectados": "{:,.0f}"}), width='stretch')
            with col_chart2:
                if not df_res_seasons.empty and df_res_seasons["Tallos Proyectados"].sum() > 0:
                    import altair as alt
                    chart = alt.Chart(df_res_seasons).mark_bar(color='#0070F2', cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                        x=alt.X('Temporada:N', sort=list(df_res_seasons['Temporada']), title='Temporada', axis=alt.Axis(labelAngle=-45)),
                        y=alt.Y('Tallos Proyectados:Q', title='Tallos'),
                        tooltip=['Temporada', 'Tallos Proyectados']
                    ).properties(height=350)
                    st.altair_chart(chart, width='stretch')
                else:
                    st.info("Las proyecciones actuales no alcanzan las semanas de las temporadas configuradas.")

elif modulo == "Plan de Producción (MVA)":
    st.header("📈 Plan de Producción (MVA y Reglas de Negocio)")
    tab_plan, tab_actas = st.tabs(["Planificación y Contrapropuesta", "Gestión MVA"])
    
    with tab_actas:
        render_actas_module(db)
        
    with tab_plan:
        from app.services.produccion_service import obtener_resumen_plan_vigente, sincronizar_plan_maestro_y_detallado
        resumen_vigente = obtener_resumen_plan_vigente(db=db)
        
        # 1. Visor Permanente del Plan Maestro Aprobado Vigente
        if resumen_vigente.get("activo"):
            with st.container(border=True):
                st.markdown("#### 📋 Plan Maestro de Producción Vigente en Plataforma")
                st.caption(
                    f"Plan oficial consolidado y guardado permanentemente en el sistema. "
                    f"Última actualización: **{resumen_vigente['fecha_actualizacion']}** | "
                    f"Horizonte: **{resumen_vigente['num_semanas']} semanas** ({resumen_vigente['semana_min']} a {resumen_vigente['semana_max']})."
                )
                
                c_p1, c_p2, c_p3, c_p4, c_p5 = st.columns(5)
                c_p1.metric("Semanas en Plan", f"{resumen_vigente['num_semanas']}", f"{resumen_vigente['semana_min']} a {resumen_vigente['semana_max']}")
                c_p2.metric("Demanda Pedidos", f"{resumen_vigente['total_pedidos']:,.0f}", "Tallos solicitados")
                c_p3.metric("Capacidad Aprobada", f"{resumen_vigente['total_capacidad']:,.0f}", "Tallos a producir")
                var_color = "normal" if resumen_vigente['variacion'] >= 0 else "inverse"
                c_p4.metric("Variación Global", f"{resumen_vigente['variacion']:+,.0f}", delta_color=var_color)
                
                # San Valentín
                c_p5.metric(
                    "San Valentín (S2703-S2705)", 
                    f"{resumen_vigente['sv_pedidos']:,.0f}", 
                    f"Capacidad: {resumen_vigente['sv_capacidad']:,.0f}"
                )

                with st.expander("🔍 Explorar Plan Aprobado Vigente por Semana y Variedad", expanded=False):
                    df_vig_disp = resumen_vigente['df_plan']
                    sems_disp = ["Todas las Semanas"] + resumen_vigente['semanas']
                    col_f1, col_f2 = st.columns(2)
                    with col_f1:
                        sem_filter = st.selectbox("Filtrar por semana de cosecha:", sems_disp, index=0)
                    with col_f2:
                        flores_disp = ["Todas las Flores"] + sorted(df_vig_disp['Flor'].dropna().unique().tolist()) if 'Flor' in df_vig_disp.columns else []
                        flor_filter = st.selectbox("Filtrar por tipo de flor:", flores_disp, index=0)
                        
                    df_filt = df_vig_disp.copy()
                    if sem_filter != "Todas las Semanas":
                        df_filt = df_filt[df_filt['Semana'] == sem_filter]
                    if flor_filter != "Todas las Flores":
                        df_filt = df_filt[df_filt['Flor'] == flor_filter]
                        
                    st.dataframe(df_filt, width='stretch', hide_index=True)
                    
                    col_dla, col_dlb = st.columns(2)
                    with col_dla:
                        with open("Plan_Aprobado.csv", "rb") as f_a:
                            st.download_button(
                                "📥 Descargar Plan_Aprobado.csv (Maestro)", 
                                f_a.read(), 
                                file_name="Plan_Aprobado.csv", 
                                mime="text/csv", 
                                width="stretch"
                            )
                    with col_dlb:
                        if os.path.exists("Plan_Aprobado_Detallado.csv"):
                            with open("Plan_Aprobado_Detallado.csv", "rb") as f_b:
                                st.download_button(
                                    "📥 Descargar Plan_Aprobado_Detallado.csv (Siembra / Enraizamiento)", 
                                    f_b.read(), 
                                    file_name="Plan_Aprobado_Detallado.csv", 
                                    mime="text/csv", 
                                    width="stretch"
                                )

            st.markdown("---")
        else:
            st.info("💡 Aún no hay un Plan Maestro de Producción consolidado. Sube el primer archivo de plan a continuación.")

        # 2. Sección de Cargue y Actualización de Planes
        st.markdown("#### 📤 Cargar o Consolidar Nuevo Archivo de Plan Semanal")
        st.caption(
            "Sube el archivo de plan semanal (Ej: `CH-ValentinesDay-Easter...xlsx`). "
            "El sistema aplica la distribución MVA, la regla de 2,000 tallos mínimos, el cálculo de camas completas (4,800 plantas), "
            "y ejecuta **Backward Scheduling** automático para calcular siembra y enraizamiento."
        )
        
        plan_file = st.file_uploader("Subir Archivo de Plan Semanal (Excel)", type=["xlsx", "xls"], key="uploader_plan_produccion")
        if plan_file is not None:
            # Si cambiamos de archivo, limpiamos el estado
            if "plan_file_name" in st.session_state and st.session_state["plan_file_name"] != plan_file.name:
                if "df_contra" in st.session_state:
                    del st.session_state["df_contra"]
                if "df_prod" in st.session_state:
                    del st.session_state["df_prod"]
                if "df_backwards" in st.session_state:
                    del st.session_state["df_backwards"]
                
            if "df_contra" not in st.session_state:
                if st.button("Procesar Plan", type="primary"):
                    with st.spinner("Procesando archivo, aplicando MVA y Backward Scheduling..."):
                        try:
                            from app.services.produccion_service import process_plan_produccion
                            df_produccion, df_contrapropuesta, df_backwards = process_plan_produccion(plan_file.getvalue(), db)
                        
                            if df_produccion.empty:
                                st.warning("No se generaron registros. Verifica que el archivo tenga datos válidos.")
                            else:
                                st.session_state["df_contra"] = df_contrapropuesta
                                st.session_state["df_prod"] = df_produccion
                                st.session_state["df_backwards"] = df_backwards
                                st.session_state["plan_file_name"] = plan_file.name
                                st.rerun()
                        except Exception as e:
                            import traceback
                            st.error(f"Error procesando el plan: {e}")
                            st.text(traceback.format_exc())
                        
            if "df_contra" in st.session_state:
                df_contrapropuesta = st.session_state["df_contra"]
                df_produccion = st.session_state["df_prod"]
                df_backwards = st.session_state.get("df_backwards")
            
                st.success("¡Contrapropuesta generada exitosamente!")
                st.subheader("Contrapropuesta (Ajuste a Capacidad y Aprovechamiento)")
            
                columnas_ui = list(df_contrapropuesta.columns)
                df_contra_display = df_contrapropuesta[columnas_ui].copy()
                if not df_contra_display.empty:
                    total_dict = {}
                    for col in columnas_ui:
                        if col in ['Tallos Solicitados (Plan)', 'Suma de Tallos', 'Variacion']:
                            total_dict[col] = df_contra_display[col].sum()
                        elif col == 'Flower':
                            total_dict[col] = "TOTAL"
                        else:
                            total_dict[col] = ""
                
                    total_contra = pd.DataFrame([total_dict])
                    df_contra_display = pd.concat([df_contra_display, total_contra], ignore_index=True)
            
                st.dataframe(
                    df_contra_display.style.format({
                        "Tallos Solicitados (Plan)": "{:,.0f}",
                        "Suma de Tallos": "{:,.0f}",
                        "Variacion": "{:,.0f}"
                    }),
                    width='stretch'
                )
            
                st.divider()
            
                col_save, col_dl1, col_dl2 = st.columns([2, 1, 1])
            
                with col_save:
                    if st.button("💾 Guardar Contrapropuesta como Plan Aprobado", type="primary", width="stretch"):
                        with st.spinner("Consolidando y sincronizando plan maestro y detallado..."):
                            try:
                                res_sync = sincronizar_plan_maestro_y_detallado(
                                    df_produccion, 
                                    df_backwards=df_backwards, 
                                    db=db
                                )
                                num_nuevas = len(res_sync['nuevas_semanas'])
                                s_min = min(res_sync['nuevas_semanas']) if num_nuevas > 0 else "-"
                                s_max = max(res_sync['nuevas_semanas']) if num_nuevas > 0 else "-"
                                st.success(f"✅ ¡Plan consolidado y guardado permanentemente! Se actualizaron {num_nuevas} semanas ({s_min} a {s_max}).")
                                st.info("🔄 Sincronización completa: 'Plan_Aprobado.csv' y 'Plan_Aprobado_Detallado.csv' quedaron 100% alineados. Los módulos de ForeCast, Pedido y Enraizamiento se actualizaron automáticamente.")
                                
                                # Limpiar estado temporal y refrescar
                                if "df_contra" in st.session_state: del st.session_state["df_contra"]
                                if "df_prod" in st.session_state: del st.session_state["df_prod"]
                                if "df_backwards" in st.session_state: del st.session_state["df_backwards"]
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error al sincronizar el plan maestro: {e}")
            
                import io
                # Generar Excel para Contrapropuesta
                output_contra = io.BytesIO()
                with pd.ExcelWriter(output_contra, engine='xlsxwriter') as writer:
                    df_contrapropuesta.to_excel(writer, index=False, sheet_name='Contrapropuesta')
                output_contra.seek(0)
            
                with col_dl1:
                    st.download_button(
                        label="📥 Descargar Contrapropuesta",
                        data=output_contra.getvalue(),
                        file_name=f"Contrapropuesta_{date.today()}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        width="stretch"
                    )
                
                # Generar Excel para Descargar Plan Detallado
                output_plan = io.BytesIO()
                with pd.ExcelWriter(output_plan, engine='xlsxwriter') as writer:
                    df_produccion.to_excel(writer, index=False, sheet_name='Plan_Detallado')
                output_plan.seek(0)
            
                with col_dl2:
                    st.download_button(
                        label="📥 Descargar Plan Detallado (Flor/Color/Variedad)",
                        data=output_plan.getvalue(),
                        file_name=f"Plan_Detallado_MVA_{date.today()}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        width="stretch"
                    )

elif modulo == "Ocupación de Área y Capacidad":
    render_ocupacion_module(db)

elif modulo == "Pedido Material Vegetal":
    from app.ui.pedido_ui import render_pedido_module
    render_pedido_module(db)

elif modulo == "Plan de Enraizamiento":
    from app.ui.enraizamiento_ui import render_enraizamiento_module
    render_enraizamiento_module(db)


