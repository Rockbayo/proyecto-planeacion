import streamlit as st
import pandas as pd
import io
import math
from datetime import date
import altair as alt

from app.models.models import Variedad
from app.services.enraizamiento_service import (
    obtener_semanas_enraizamiento_disponibles,
    generar_plano_enraizamiento_semanal,
    generar_pdf_plano_enraizamiento,
    obtener_datos_comparativos_enraizamiento_y_camas,
    calcular_bandejas_redondeadas,
    cargar_inventario_recepcion,
    guardar_inventario_recepcion,
    cargar_inventario_lunes,
    guardar_inventario_lunes,
    precargar_inventario_desde_plano,
    ejecutar_compensacion_inventario,
    aprobar_ejecucion_y_descontar_inventario,
    cargar_ejecucion_real,
    guardar_ejecucion_real,
    precargar_ejecucion_desde_plano,
    CAVIDADES_POR_BANDEJA,
    DIAS_PERMANENCIA_BANCO,
    SEMANAS_ENRAIZAMIENTO,
    HORAS_JORNADA,
    TOTAL_HORAS_SEMANA_ESTANDAR,
    RENDIMIENTO_NORMAL,
    RENDIMIENTO_REFUERZO,
    RENDIMIENTO_APRENDIZAJE,
    UMBRAL_DIFERENCIA_DESPRECIABLE,
    MINIMO_COMPENSACION_ESQUEJES,
    ESQUEJES_MEDIA_CAMA,
    ESQUEJES_POR_CAMA_ESTANDAR,
    calcular_esquejes_efectivos_clavar,
    calcular_estado_disponibilidad,
    generar_resumen_excedentes_flor_color,
    calcular_semana_siembra_desde_enraizamiento,
    absorber_excedentes_inventario_a_campo
)
from app.services.ocupacion_service import consultar_camas_disponibles_campo

def render_enraizamiento_module(db):
    st.header("🌱 Plan y Plano Operativo de Enraizamiento")
    st.markdown(f"""
    Genera el **plano operativo oficial de enraizamiento** para entrega directa a la jefatura de propagación.
    Alinea los requerimientos de siembra con el día óptimo (**cosecha en pico los jueves**),
    estandariza a **bandejas de 112 cavidades**, asigna el **bloque de campo tentativo** de destino,
    nivela la jornada laboral semanal (**{TOTAL_HORAS_SEMANA_ESTANDAR:.1f}h efectivas**, deduciendo 30 min de almuerzo L-V) y proyecta la **cosecha resultante**.
    """)

    # Cargar catálogo oficial de variedades desde la base de datos (514 registros)
    catalogo_vars_db = []
    mapa_variedad_db = {}
    lista_nombres_db = []
    if db is not None:
        try:
            catalogo_vars_db = db.query(Variedad).order_by(Variedad.nombre).all()
            for v in catalogo_vars_db:
                if v.nombre and str(v.nombre).strip():
                    nom = str(v.nombre).strip()
                    lista_nombres_db.append(nom)
                    mapa_variedad_db[nom.lower()] = (
                        str(v.flor).strip() if v.flor else "Estándar",
                        str(v.color).strip() if v.color else "Mix"
                    )
            lista_nombres_db = sorted(list(set(lista_nombres_db)))
        except Exception as e:
            print(f"Error al consultar catálogo de variedades: {e}")

    # 1. Cargar semanas disponibles en el Pedido Aprobado
    modo_plan = "aprobado"
    factor_expansion = 1.0
    correr_variedades = True

    semanas_disp = obtener_semanas_enraizamiento_disponibles(
        modo_plan=modo_plan,
        factor_expansion=factor_expansion,
        correr_variedades=correr_variedades,
        db=db
    )
    if not semanas_disp:
        st.warning("⚠️ No se encontraron órdenes de siembra en el archivo de pedidos consolidado maestro.")
        return

    # Buscar semana por defecto: S202643 o la primera
    default_idx = 0
    for idx, s in enumerate(semanas_disp):
        if s.get("Semana_Enraizamiento") == "202643":
            default_idx = idx
            break

    # Selector de Semana y Parámetros Operativos
    with st.container(border=True):
        st.markdown("#### 📅 Selección de Semana y Programa Operativo")
        
        def format_semana(opt):
            cam_txt = f" | {opt.get('Total_Camas', 0):.0f} cam." if opt.get('Total_Camas') else ""
            tot_tll = opt.get('Total_Tallos', 0)
            tll_txt = f" ➔ {tot_tll:,d} tallos" if tot_tll > 0 else ""
            return (
                f"{opt['Semana_Enraizamiento_Label']} "
                f"(Siembra {opt['Semana_Siembra_Label']} ➔ Cosecha {opt.get('Semana_Cosecha_Label', '')} | {opt['Temporada']}) — "
                f"{opt['Total_Esquejes']:,d} esq.{tll_txt} ({opt['Total_Bandejas_112']:,d} bandejas 112{cam_txt})"
            )

        col_sem, col_mod, col_cap = st.columns([1.8, 1.0, 1.2])
        with col_sem:
            semana_sel = st.selectbox(
                "Semana de enraizamiento a programar:",
                options=semanas_disp,
                index=default_idx,
                format_func=format_semana,
                help="Seleccione la semana en la que ingresa el material vegetal a las camas de nebulización en propagación."
            )
        with col_mod:
            modelo_sel = st.selectbox(
                "Modelo operativo:",
                options=["⭐ Plan Operativo Aprobado S&OP", "📋 Base Histórica Plataforma"],
                index=0,
                help="El Plan Operativo Aprobado sincroniza directamente con el pedido aprobado de S&OP y curvas reales de extracción."
            )
            if "Base Histórica" in modelo_sel:
                modo_plan = "plataforma_base"

        with col_cap:
            base_cap_sel = st.selectbox(
                "Capacidad Camas Enraizamiento:",
                options=[
                    "🏗️ Capacidad Física por Bloque (m² y Densidad)",
                    "🚜 Promedio Ponderado Finca (4,867 esq/cama)",
                    "📦 Estándar Comercial Fijo (5,200 esq/cama)"
                ],
                index=0,
                help="Ajusta el enraizamiento y bandejas a la capacidad física del bloque estimado de campo (m² de era x densidad agronómica) respetando la unidad comercial de 5,200 del pedido."
            )
            if "Capacidad Física" in base_cap_sel:
                base_capacidad = "bloque"
            elif "Promedio Ponderado" in base_cap_sel:
                base_capacidad = "finca"
            else:
                base_capacidad = "std_5200"

        # Resumen Dinámico Adaptado a la Semana Seleccionada (sin textos defensivos)
        if semana_sel:
            tot_tll_sel = semana_sel.get('Total_Tallos', 0)
            tll_info = f" ➔ **{tot_tll_sel:,d} tallos esperados a cosecha**" if tot_tll_sel > 0 else ""
            st.info(
                f"📋 **Programa Operativo Semana {semana_sel['Semana_Enraizamiento_Label']}:** "
                f"Siembra en Campo: **{semana_sel['Semana_Siembra_Label']}** (Desfase: -{SEMANAS_ENRAIZAMIENTO} sem en banco) | "
                f"Cosecha Estimada: **{semana_sel.get('Semana_Cosecha_Label', '')}** | "
                f"Temporada: **{semana_sel['Temporada']}** | "
                f"Volumen Pedido: **{semana_sel['Total_Esquejes']:,d} esquejes**{tll_info} ({semana_sel['Total_Camas']:.1f} camas, {semana_sel['Total_Bandejas_112']:,d} bandejas 112, {semana_sel['Num_Variedades']} variedades)."
            )

    # Configuración de Mano de Obra y Rendimientos (Personalizable)
    with st.expander("👥 Configuración de Cuadrilla y Rendimientos de Clavado", expanded=False):
        st.markdown("""
        Configure la composición de la cuadrilla y las tasas de rendimiento para calcular con precisión
        las horas requeridas y el balance de capacidad operativa semanal.
        """)
        c_op1, c_op2, c_op3 = st.columns(3)
        
        with c_op1:
            st.markdown("**Operarios Rendimiento Normal**")
            num_normal = st.number_input(
                "Cantidad de operarios normales:",
                min_value=0, max_value=50, value=6, step=1,
                help="Personal estándar con experiencia consolidada."
            )
            rend_normal = st.number_input(
                "Rendimiento normal (esquejes/hora):",
                min_value=500.0, max_value=3000.0, value=float(RENDIMIENTO_NORMAL), step=50.0,
                help="Equivale a ~18 bandejas/hora (1 bandeja de 112 cada 3.33 min)."
            )

        with c_op2:
            st.markdown("**Operarios de Refuerzo / Temporada**")
            default_ref = 3 if (semana_sel and semana_sel.get('Semana_Enraizamiento') == '202643') else (2 if (semana_sel and semana_sel.get('Semana_Enraizamiento') == '202644') else 0)
            num_refuerzo = st.number_input(
                "Cantidad de refuerzos:",
                min_value=0, max_value=50, value=default_ref, step=1,
                help="Personal de apoyo temporal contratado para temporada (sugerido 3 para S2643 pico 148 camas, 2 para S2644)."
            )
            rend_refuerzo = st.number_input(
                "Rendimiento refuerzo (esquejes/hora):",
                min_value=500.0, max_value=3000.0, value=float(RENDIMIENTO_REFUERZO), step=50.0,
                help="Equivale a ~15.2 bandejas/hora (1 bandeja de 112 cada 3.95 min)."
            )

        with c_op3:
            st.markdown("**Operarios en Curva de Aprendizaje**")
            num_aprendizaje = st.number_input(
                "Cantidad en aprendizaje:",
                min_value=0, max_value=50, value=0, step=1,
                help="Personal nuevo en inducción o primeros días de labor."
            )
            rend_aprendizaje = st.number_input(
                "Rendimiento aprendizaje (esquejes/hora):",
                min_value=300.0, max_value=2000.0, value=float(RENDIMIENTO_APRENDIZAJE), step=50.0,
                help="Equivale a ~8.9 bandejas/hora (1 bandeja de 112 cada 6.72 min)."
            )

    config_cuadrilla = {
        "num_normal": num_normal,
        "num_refuerzo": num_refuerzo,
        "num_aprendizaje": num_aprendizaje,
        "rend_normal": rend_normal,
        "rend_refuerzo": rend_refuerzo,
        "rend_aprendizaje": rend_aprendizaje
    }

    # 1. Recuperar inventario disponible / ajustado de la semana (si existe en memoria o disco)
    cod_sem = semana_sel['Semana_Enraizamiento']
    session_key_inv = f"df_inv_recepcion_{cod_sem}"
    version_inv_key = f"ver_inv_{cod_sem}"
    adv_comp_key = f"adv_comp_{cod_sem}"

    if version_inv_key not in st.session_state:
        st.session_state[version_inv_key] = 0

    df_inv_ajustado = None
    if session_key_inv in st.session_state:
        df_inv_ajustado = st.session_state[session_key_inv]
    else:
        df_guardado = cargar_inventario_recepcion(cod_sem)
        if df_guardado is not None and not df_guardado.empty:
            st.session_state[session_key_inv] = df_guardado
            df_inv_ajustado = df_guardado

    if df_inv_ajustado is not None and not df_inv_ajustado.empty:
        df_inv_ajustado['Esquejes_Efectivos_Clavar'] = df_inv_ajustado.apply(calcular_esquejes_efectivos_clavar, axis=1)
        st.session_state[session_key_inv] = df_inv_ajustado

    # Generar Plano Operativo Semanal sincronizado con inventario real y compensaciones
    res_plano = generar_plano_enraizamiento_semanal(
        db, 
        cod_sem, 
        config_cuadrilla=config_cuadrilla,
        modo_plan=modo_plan,
        factor_expansion=factor_expansion,
        correr_variedades=correr_variedades,
        base_capacidad=base_capacidad,
        df_inventario_ajustado=df_inv_ajustado
    )

    if "error" in res_plano:
        st.error(f"❌ {res_plano['error']}")
        return

    kpis = res_plano['kpis']
    mano_obra = res_plano['resumen_mano_obra']
    df_detallado = res_plano['df_plano_detallado']
    df_res_dia = res_plano['df_resumen_diario']

    # Banner Superior de KPIs
    with st.container(border=True):
        st.markdown(
            f"#### 📊 Resumen Ejecutivo — Semana Enraizamiento {res_plano['semana_enraizamiento_label']} "
            f"(Siembra {res_plano['semana_siembra_label']} | Cosecha {res_plano.get('semana_cosecha_label', '')} | {res_plano['temporada']})"
        )
        k1, k2, k3, k4, k5, k6 = st.columns(6)
        
        tot_pedido = kpis.get('total_esquejes_pedido', kpis['total_esquejes'])
        dif_ped = kpis['total_esquejes'] - tot_pedido
        k1.metric(
            "Esquejes Enraizamiento", 
            f"{kpis['total_esquejes']:,d}", 
            f"Pedido: {tot_pedido:,d} ({dif_ped:+,d})" if dif_ped != 0 else f"{kpis['num_lotes']} lotes"
        )
        k2.metric(
            "Bandejas (112 alv.)", 
            f"{kpis['total_bandejas']:,d}", 
            f"Entero más cercano"
        )
        k3.metric(
            "Horas Requeridas", 
            f"{kpis['horas_requeridas']:.1f} h", 
            f"Rend. {kpis['rendimiento_ponderado']:,.0f} esq/h"
        )
        
        tot_op_fijos = mano_obra['total_operarios_fijos']
        op_req_prom = mano_obra['promedio_operarios_requeridos']
        bal_op = mano_obra['balance_semanal_operarios']
        bal_color = "normal" if bal_op >= 0 else "inverse"
        
        k4.metric(
            "Operarios Requeridos", 
            f"{op_req_prom:.1f}", 
            f"Base: {TOTAL_HORAS_SEMANA_ESTANDAR:.1f}h efectiva"
        )
        k5.metric(
            "Balance Cuadrilla", 
            f"{bal_op:+.1f} op.", 
            f"Asignados: {tot_op_fijos}",
            delta_color=bal_color
        )
        aprov_prom = (kpis['tallos_esperados'] / kpis['total_esquejes'] * 100.0) if kpis['total_esquejes'] > 0 else 80.6
        k6.metric(
            "Tallos Proyectados Cosecha", 
            f"{kpis['tallos_esperados']:,d}", 
            f"Aprov. ponderado: {aprov_prom:.1f}%"
        )

    # Pestañas de Trabajo
    tab_plano, tab_inventario, tab_ejecutado, tab_mano_obra, tab_comparativa, tab_fenologia = st.tabs([
        "📋 Plano Operativo Semanal",
        "📦 Inventario de Esquejes (Lunes)",
        "✅ Registro de Ejecutado Real",
        "⏱️ Distribución Diaria y Cuadrilla",
        "📈 Proyección de Cosecha, ForeCast y Camas",
        "🌿 Ventana Fenológica y Parámetros"
    ])

    # -------------------------------------------------------------
    # TAB 1: PLANO OPERATIVO SEMANAL
    # -------------------------------------------------------------
    with tab_plano:
        st.markdown("##### 📄 Hoja de Ruta de Clavado por Lote y Variedad")
        st.caption(
            "Este plano contiene la programación día a día de enraizamiento. Los días están nivelados para respetar "
            "las jornadas laborales efectivas y concentrar la cosecha en el pico objetivo de los jueves. "
            "El archivo PDF exportado cuenta con casillas de ejecución real y firmas para control físico en invernadero."
        )

        es_plano_ajustado = res_plano.get('es_ajustado_inventario', False)
        if es_plano_ajustado:
            st.success(
                "⚡ **Plano Operativo Nivelado con Inventario Real de Cuarto Frío:** "
                "Este plano y el PDF de impresión reflejan los esquejes efectivos a clavar, compensaciones por flor-color "
                "(regla agronómica universal ≥0.5 camas) y extemporáneos. Los lotes reprogramados (+1w) figuran en 0 esquejes para esta semana."
            )

        # Botones de Descarga en barra superior
        col_btn1, col_btn2, col_spacer = st.columns([1.5, 1.5, 3])
        
        # 1. Generar PDF oficial
        pdf_bytes = generar_pdf_plano_enraizamiento(res_plano)
        label_pdf = "📥 Descargar Plano en PDF (Ajustado con Inventario)" if es_plano_ajustado else "📥 Descargar Plano en PDF (Listo para Operación)"
        with col_btn1:
            st.download_button(
                label=label_pdf,
                data=pdf_bytes,
                file_name=f"Plano_Enraizamiento_{res_plano['semana_enraizamiento_label']}{'_Ajustado' if es_plano_ajustado else ''}.pdf",
                mime="application/pdf",
                help="Descarga el plano en formato horizontal con firmas y casillas de control para entregar a propagación."
            )

        # 2. Generar Excel
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df_detallado.to_excel(writer, index=False, sheet_name='Plano_Enraizamiento')
            df_res_dia.to_excel(writer, index=False, sheet_name='Resumen_Diario')
        with col_btn2:
            st.download_button(
                label="📊 Descargar Plano en Excel",
                data=excel_buffer.getvalue(),
                file_name=f"Plano_Enraizamiento_{res_plano['semana_enraizamiento_label']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="Descarga la data detallada y resumen diario en formato Excel."
            )

        # Filtros de visualización
        c_f1, c_f2 = st.columns(2)
        with c_f1:
            flores_disp = sorted(df_detallado['Flor'].unique())
            filtro_flor = st.multiselect(
                "Filtrar por tipo de flor:",
                options=flores_disp,
                default=[],
                placeholder="Todas las flores"
            )
        with c_f2:
            dias_disp = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
            filtro_dias = st.multiselect(
                "Filtrar por día programado:",
                options=dias_disp,
                default=[],
                placeholder="Todos los días de la semana"
            )

        df_display = df_detallado.copy()
        if filtro_flor:
            df_display = df_display[df_display['Flor'].isin(filtro_flor)]
        if filtro_dias:
            df_display = df_display[df_display['Dia_Programado'].isin(filtro_dias)]

        # Preparar columnas amigables
        df_display['Nivelado'] = df_display['Es_Nivelado'].apply(lambda x: "⚡ Nivelado" if x else "🎯 Tentativo")
        if 'Capacidad_Cama_Bloque' in df_display.columns:
            df_display['Capacidad_Cama_Bloque'] = df_display['Capacidad_Cama_Bloque'].apply(lambda x: f"{int(float(x)):,d}" if pd.notnull(x) and str(x).replace('.','',1).isdigit() else str(x))
        
        if es_plano_ajustado:
            columnas_orden = [
                "Dia_Programado", "Flor", "Color", "Variedad", "Esquejes_Pedido", "Compensacion_Volumen",
                "Esquejes", "Bandejas_112", "Camas_Campo", "Bloque_Destino", "Semana_Siembra", "Semana_Cosecha",
                "Estado_Disponibilidad", "Observaciones", "Nivelado"
            ]
        else:
            columnas_orden = [
                "Dia_Programado", "Flor", "Color", "Variedad", "Esquejes_Pedido", "Esquejes", 
                "Bandejas_112", "Camas_Campo", "Bloque_Destino", "Capacidad_Cama_Bloque",
                "Semana_Siembra", "Semana_Cosecha", "Tallos_Esperados", "Observaciones", "Nivelado"
            ]
        columnas_orden = [c for c in columnas_orden if c in df_display.columns]

        # Fila de Totales
        row_totales = {
            "Dia_Programado": "TOTAL GENERAL",
            "Flor": "-",
            "Color": "-",
            "Variedad": f"{len(df_display)} Variedades",
            "Esquejes_Pedido": int(df_display['Esquejes_Pedido'].sum()) if 'Esquejes_Pedido' in df_display.columns else int(df_display['Esquejes'].sum()),
            "Compensacion_Volumen": int(df_display['Compensacion_Volumen'].sum()) if 'Compensacion_Volumen' in df_display.columns else 0,
            "Esquejes": int(df_display['Esquejes'].sum()),
            "Bandejas_112": int(df_display['Bandejas_112'].sum()),
            "Camas_Campo": round(float(df_display['Camas_Campo'].sum()), 1),
            "Bloque_Destino": "-",
            "Capacidad_Cama_Bloque": "-",
            "Semana_Siembra": "-",
            "Semana_Cosecha": "-",
            "Tallos_Esperados": int(df_display['Tallos_Esperados'].sum()) if 'Tallos_Esperados' in df_display.columns else 0,
            "Estado_Disponibilidad": "-",
            "Observaciones": "-",
            "Nivelado": "-"
        }
        df_display_con_totales = pd.concat([df_display[columnas_orden], pd.DataFrame([row_totales])], ignore_index=True)

        st.dataframe(
            df_display_con_totales,
            column_config={
                "Dia_Programado": st.column_config.TextColumn("Día Programado"),
                "Flor": st.column_config.TextColumn("Flor"),
                "Color": st.column_config.TextColumn("Color"),
                "Variedad": st.column_config.TextColumn("Variedad"),
                "Esquejes_Pedido": st.column_config.NumberColumn("Esquejes Pedido (5,200)", format="%d", help="Esquejes del pedido comercial estándar"),
                "Compensacion_Volumen": st.column_config.NumberColumn("Compensación (+/-)", format="%+d", help="Ajuste de volumen por compensación agronómica (≥0.5 camas)"),
                "Esquejes": st.column_config.NumberColumn("Esquejes Enraizamiento", format="%d", help="Esquejes requeridos ajustados a capacidad física de cama del bloque"),
                "Bandejas_112": st.column_config.NumberColumn("Bandejas (112)", format="%d", help="Bandejas de 112 cavidades ajustadas al entero más cercano (ej. 46.4 -> 46)"),
                "Camas_Campo": st.column_config.NumberColumn("Camas Campo Eq.", format="%.1f"),
                "Bloque_Destino": st.column_config.TextColumn("Bloque Destino"),
                "Capacidad_Cama_Bloque": st.column_config.TextColumn("Cap. Cama Bloque"),
                "Semana_Siembra": st.column_config.TextColumn("Sem. Siembra"),
                "Semana_Cosecha": st.column_config.TextColumn("Sem. Cosecha"),
                "Tallos_Esperados": st.column_config.NumberColumn("Tallos Esperados", format="%d"),
                "Estado_Disponibilidad": st.column_config.TextColumn("Estado Inventario", help="Diagnóstico de inventario y ejecución de la variedad"),
                "Observaciones": st.column_config.TextColumn("Observaciones", help="Espacio para registrar novedades de campo durante el proceso de enraizamiento"),
                "Nivelado": st.column_config.TextColumn("Estado Programación")
            },
            hide_index=True,
            width="stretch"
        )

        st.caption(
            "💡 **Cálculo Técnico:** El pedido comercial se realiza a razón estándar de 5,200 esquejes/cama. "
            "Para enraizamiento operativo, los esquejes y bandejas se calculan sobre la **capacidad física instalada del bloque de destino** "
            "(m² de era × densidad agronómica + margen de seguridad) y las bandejas de 112 cavidades se redondean **al entero más cercano** "
            "(`round`, ej. 46.4 bandejas $\\to$ 46 bandejas, no 47), protegiendo la ocupación de banco sin sobrantes innecesarios."
        )

    # -------------------------------------------------------------
    # -------------------------------------------------------------
    # TAB 2: RECEPCIÓN DE ESQUEJES Y DISPONIBILIDAD EN CUARTO FRÍO
    # -------------------------------------------------------------
    with tab_inventario:
        st.markdown("##### 📦 Recepción de Material Vegetal y Disponibilidad en Cuarto Frío")
        st.caption(
            "Cruce integral de requerimientos del plano frente al material vegetal recibido en recepción (semana previa) "
            "y las existencias en cuarto frío. Permite conocer con total precisión el inventario real disponible, "
            "compensar faltantes por compatibilidad y asegurar el cumplimiento del volumen programado."
        )

        session_key_inv = f"df_inv_recepcion_{cod_sem}"
        version_inv_key = f"ver_inv_{cod_sem}"
        adv_comp_key = f"adv_comp_{cod_sem}"

        if version_inv_key not in st.session_state:
            st.session_state[version_inv_key] = 0

        if session_key_inv not in st.session_state:
            df_guardado = cargar_inventario_recepcion(cod_sem)
            if df_guardado is not None and not df_guardado.empty:
                st.session_state[session_key_inv] = df_guardado
            else:
                st.session_state[session_key_inv] = precargar_inventario_desde_plano(res_plano)

        df_inv_current = st.session_state[session_key_inv]

        # Garantizar eliminación de columnas secundarias que saturan la interfaz
        for c_drop in ["Proveedor", "Breeder"]:
            if c_drop in df_inv_current.columns:
                df_inv_current = df_inv_current.drop(columns=[c_drop])

        # Sanitizar columnas y tipos de datos
        cols_inv_str = ["Semana_Enraizamiento", "Fecha_Ingreso", "Flor", "Color", "Variedad", "Estado_Disponibilidad", "Estado_Aprobacion", "Observaciones"]
        for c in cols_inv_str:
            if c in df_inv_current.columns:
                df_inv_current[c] = df_inv_current[c].fillna("").astype(str)

        cols_inv_int = [
            "Stock_Cuarto_Frio", "Esquejes_Recepcion", "Esquejes_Recibidos", "Bajas_Descartes",
            "Total_Disponible", "Esquejes_Requeridos", "Diferencia_Recepcion", "Compensacion_Volumen",
            "Reprogramado_Siguiente_Semana", "Esquejes_Efectivos_Clavar", "Diferencia_Saldo",
            "Bandejas_112_Disponibles", "Esquejes_Clavados_Reales", "Remanente_Final"
        ]
        for c in cols_inv_int:
            if c not in df_inv_current.columns:
                df_inv_current[c] = 0
            df_inv_current[c] = pd.to_numeric(df_inv_current[c], errors='coerce').fillna(0).astype(int)

        # Recálculo exacto de totales y diferencias
        df_inv_current['Esquejes_Recibidos'] = df_inv_current['Esquejes_Recepcion']
        df_inv_current['Total_Disponible'] = df_inv_current['Stock_Cuarto_Frio'] + df_inv_current['Esquejes_Recepcion'] - df_inv_current['Bajas_Descartes']
        df_inv_current['Diferencia_Recepcion'] = df_inv_current['Esquejes_Recepcion'] - df_inv_current['Esquejes_Requeridos']
        df_inv_current['Esquejes_Efectivos_Clavar'] = df_inv_current.apply(calcular_esquejes_efectivos_clavar, axis=1)
        df_inv_current['Diferencia_Saldo'] = df_inv_current['Total_Disponible'] - df_inv_current['Esquejes_Efectivos_Clavar']
        df_inv_current['Remanente_Final'] = df_inv_current['Diferencia_Saldo'].apply(lambda x: max(0, x))
        df_inv_current['Bandejas_112_Disponibles'] = df_inv_current['Esquejes_Efectivos_Clavar'].apply(calcular_bandejas_redondeadas)

        df_inv_current['Estado_Disponibilidad'] = df_inv_current.apply(calcular_estado_disponibilidad, axis=1)

        # Totales para métricas
        tot_req = int(df_inv_current['Esquejes_Requeridos'].sum())
        tot_stk = int(df_inv_current['Stock_Cuarto_Frio'].sum())
        tot_rec = int(df_inv_current['Esquejes_Recepcion'].sum())
        tot_baj = int(df_inv_current['Bajas_Descartes'].sum())
        tot_disp = int(df_inv_current['Total_Disponible'].sum())
        tot_clavar = int(df_inv_current['Esquejes_Efectivos_Clavar'].sum())
        tot_reprog = int(df_inv_current['Reprogramado_Siguiente_Semana'].sum())
        dif_saldo = tot_disp - tot_clavar
        cob_disp_pct = (tot_disp / tot_req * 100.0) if tot_req > 0 else 100.0
        tot_ban_clavar = int(df_inv_current['Bandejas_112_Disponibles'].sum())
        tot_ban_req = sum([calcular_bandejas_redondeadas(x) for x in df_inv_current['Esquejes_Requeridos']])

        # Banner de 5 Tarjetas KPIs
        m_i1, m_i2, m_i3, m_i4, m_i5 = st.columns(5)
        m_i1.metric("Requerido Plano", f"{tot_req:,d}", f"{tot_ban_req:,d} bandejas")
        m_i2.metric("Stock Cuarto Frío", f"{tot_stk:,d}", "Remanente semana previa")
        m_i3.metric("Recepción Esquejes", f"{tot_rec:,d}", f"Bajas: -{tot_baj:,d}" if tot_baj > 0 else "Sin bajas")
        m_i4.metric("Total Disponible Físico", f"{tot_disp:,d}", f"{cob_disp_pct:.1f}% cobertura")
        m_i5.metric("Esquejes a Clavar", f"{tot_clavar:,d}", f"{tot_ban_clavar:,d} bandejas (112)")

        # Capacidad de Campo en Semana de Siembra (S+3)
        sem_siem_iso = calcular_semana_siembra_desde_enraizamiento(cod_sem)
        disp_campo_info = consultar_camas_disponibles_campo(sem_siem_iso, db=db)
        c_lib_campo = disp_campo_info.get('camas_libres', 0.0)
        c_ocup_campo = disp_campo_info.get('camas_ocupadas', 0.0)
        techo_campo = disp_campo_info.get('capacidad_techo', 1120.0)
        pct_campo = disp_campo_info.get('porcentaje_ocupacion', 0.0)

        if c_lib_campo >= 0.5:
            st.markdown(f"""
            <div style="background-color: #f0fdf4; border-left: 4px solid #16a34a; padding: 10px 14px; border-radius: 6px; margin: 10px 0 14px 0; font-size: 13.5px;">
                <span style="font-weight: 700; color: #15803d;">🌱 Capacidad de Campo en Siembra (Sem S{sem_siem_iso[2:]}):</span> 
                <b>{c_ocup_campo:.0f} / {techo_campo:.0f} camas ocupadas ({pct_campo:.1f}%)</b> — 
                <span style="color: #16a34a; font-weight: 600;">🟢 {c_lib_campo:.1f} camas libres disponibles para absorber excedentes a campo</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="background-color: #fef2f2; border-left: 4px solid #dc2626; padding: 10px 14px; border-radius: 6px; margin: 10px 0 14px 0; font-size: 13.5px;">
                <span style="font-weight: 700; color: #b91c1c;">🌱 Capacidad de Campo en Siembra (Sem S{sem_siem_iso[2:]}):</span> 
                <b>{c_ocup_campo:.0f} / {techo_campo:.0f} camas ocupadas ({pct_campo:.1f}%)</b> — 
                <span style="color: #dc2626; font-weight: 600;">🔴 Pico al 100% de capacidad: Excedentes se resguardan en frío para evitar sobrecupo</span>
            </div>
            """, unsafe_allow_html=True)

        # Diagnóstico y Alertas de Compensación Jerárquica
        advertencias_previas = st.session_state.get(adv_comp_key, [])
        if advertencias_previas:
            with st.expander("📋 **Detalle de Compensaciones y Ajustes Aplicados**", expanded=True):
                for adv in advertencias_previas:
                    t = adv.get('Tipo', 'info')
                    m = adv.get('Mensaje', '')
                    if t == 'success':
                        st.success(m)
                    elif t == 'warning':
                        st.warning(m)
                    elif t == 'error':
                        st.error(m)
                    else:
                        st.info(m)

        # Regla de Negocio: Alertar diferencias críticas > 500 esquejes (diferencias <= 500 son despreciables)
        df_def_criticos = df_inv_current[
            ((df_inv_current['Esquejes_Requeridos'] - df_inv_current['Total_Disponible']) > UMBRAL_DIFERENCIA_DESPRECIABLE) & 
            (df_inv_current['Compensacion_Volumen'] == 0) & 
            (df_inv_current['Reprogramado_Siguiente_Semana'] == 0)
        ]
        df_dif_menores = df_inv_current[
            (df_inv_current['Esquejes_Requeridos'] > df_inv_current['Total_Disponible']) &
            ((df_inv_current['Esquejes_Requeridos'] - df_inv_current['Total_Disponible']) <= UMBRAL_DIFERENCIA_DESPRECIABLE)
        ]

        if not df_def_criticos.empty:
            st.error(
                f"⚠️ **Atención:** Existen {len(df_def_criticos)} lote(s) con faltante crítico (>500 esquejes) frente al plano. "
                "Haga clic en **🔄 Compensar Faltantes (Flor-Color / Color)** para nivelar el volumen con excedentes compatibles "
                "(incluyendo variedades extemporáneas) o reprogramar el saldo no cubierto para la siguiente semana."
            )
        elif not df_dif_menores.empty:
            st.info(
                f"ℹ️ **Inventario en Rango Operativo:** {len(df_dif_menores)} lote(s) presentan variaciones menores (≤500 esquejes), "
                "las cuales son despreciables y absorbidas por el margen de seguridad de la cama."
            )
        elif tot_reprog > UMBRAL_DIFERENCIA_DESPRECIABLE:
            st.warning(
                f"ℹ️ **Volumen Nivelado con Reprogramación:** Se reprogramaron **{tot_reprog:,d} esquejes** críticos para el plan de la siguiente semana (+1w). "
                f"Las camas de esta semana se clavarán con **{tot_clavar:,d} esquejes ({tot_ban_clavar:,d} bandejas)**."
            )
        else:
            st.success(
                f"✅ **Inventario 100% Cubierto y Nivelado:** Se cuenta con material suficiente para ejecutar el programa operativo "
                f"(**{tot_ban_clavar:,d} bandejas a clavar**)."
            )

        # Editor Interactivo Fluido con Catálogo Oficial en Lista Desplegable (SelectboxColumn)
        ver_inv = st.session_state[version_inv_key]
        editor_inv_key = f"editor_inv_{cod_sem}_{ver_inv}"

        cols_orden_editor_inv = [
            "Semana_Enraizamiento", "Fecha_Ingreso", "Flor", "Color", "Variedad",
            "Stock_Cuarto_Frio", "Esquejes_Recepcion", "Bajas_Descartes",
            "Total_Disponible", "Esquejes_Requeridos", "Compensacion_Volumen",
            "Esquejes_Efectivos_Clavar", "Reprogramado_Siguiente_Semana",
            "Diferencia_Saldo", "Bandejas_112_Disponibles",
            "Estado_Disponibilidad", "Observaciones"
        ]

        # Consolidar opciones oficiales para lista desplegable
        nombres_existentes_inv = set(df_inv_current['Variedad'].dropna().astype(str).str.strip())
        lista_opciones_inv = sorted(list(set(lista_nombres_db) | {n for n in nombres_existentes_inv if n}))

        df_inv_current = df_inv_current.reset_index(drop=True)
        df_inv_editado = st.data_editor(
            df_inv_current,
            key=editor_inv_key,
            column_order=cols_orden_editor_inv,
            num_rows="dynamic",
            width="stretch",
            column_config={
                "Semana_Enraizamiento": st.column_config.TextColumn("Semana", disabled=True),
                "Fecha_Ingreso": st.column_config.TextColumn("Fecha"),
                "Flor": st.column_config.TextColumn("Flor", disabled=True, help="Autocompletado automáticamente según el catálogo"),
                "Color": st.column_config.TextColumn("Color", disabled=True, help="Autocompletado automáticamente según el catálogo"),
                "Variedad": st.column_config.SelectboxColumn("Variedad", options=lista_opciones_inv, required=True, help="Seleccione variedad del catálogo oficial de base de datos (514 variedades)"),
                "Stock_Cuarto_Frio": st.column_config.NumberColumn("Stock Cuarto Frío", min_value=0, step=100, format="%d", help="Existencias remanentes en cámara fría"),
                "Esquejes_Recepcion": st.column_config.NumberColumn("Recepción Esquejes", min_value=0, step=100, format="%d", help="Material recibido en recepción de la semana previa (o pedido extemporáneo)"),
                "Bajas_Descartes": st.column_config.NumberColumn("Bajas / Descartes", min_value=0, step=50, format="%d", help="Mermas, pérdidas de frío o descartes sanitarios"),
                "Total_Disponible": st.column_config.NumberColumn("Total Disponible", disabled=True, format="%d", help="Stock Frío + Recepción - Bajas"),
                "Esquejes_Requeridos": st.column_config.NumberColumn("Requerido Plano", disabled=True, format="%d", help="Demanda original del plano operativo (0 para extemporáneos)"),
                "Compensacion_Volumen": st.column_config.NumberColumn("Compensación (+/-)", disabled=True, format="%+d", help="Volumen ajustado por compatibilidad de flor/color (mínimo media cama ≥2,500)"),
                "Esquejes_Efectivos_Clavar": st.column_config.NumberColumn("Esquejes a Clavar", disabled=True, format="%d", help="Volumen final neto a clavar en banco"),
                "Reprogramado_Siguiente_Semana": st.column_config.NumberColumn("Reprog. Sig. Sem.", disabled=True, format="%d", help="Faltante que no alcanza media cama o crítico no compensable que pasa al plan siguiente"),
                "Diferencia_Saldo": st.column_config.NumberColumn("Saldo Remanente", disabled=True, format="%+d", help="Saldo final que queda en cuarto frío"),
                "Bandejas_112_Disponibles": st.column_config.NumberColumn("Bandejas (112)", disabled=True, format="%d", help="Bandejas de 112 cavidades a clavar"),
                "Estado_Disponibilidad": st.column_config.TextColumn("Estado / Diagnóstico", disabled=True),
                "Observaciones": st.column_config.TextColumn("Observaciones / Novedad")
            },
            hide_index=True
        )

        # Función de procesamiento consolidado al terminar de digitar
        def procesar_calculo_inventario(df_edit, sem_actual):
            df = df_edit.copy()
            today_str = date.today().strftime('%Y-%m-%d')
            if 'Semana_Enraizamiento' in df.columns:
                df['Semana_Enraizamiento'] = df['Semana_Enraizamiento'].fillna(str(sem_actual)).replace('', str(sem_actual))
            else:
                df['Semana_Enraizamiento'] = str(sem_actual)

            if 'Fecha_Ingreso' in df.columns:
                df['Fecha_Ingreso'] = df['Fecha_Ingreso'].fillna(today_str).replace('', today_str)

            if 'Variedad' in df.columns:
                df['Variedad'] = df['Variedad'].fillna("").astype(str)
                df = df[df['Variedad'].str.strip() != ''].copy()

            # Autocompletar Flor y Color desde el catálogo oficial de variedades
            for idx in df.index:
                v_nom = str(df.loc[idx, 'Variedad']).strip()
                v_low = v_nom.lower()
                if v_low in mapa_variedad_db:
                    c_flor, c_col = mapa_variedad_db[v_low]
                    df.loc[idx, 'Flor'] = c_flor
                    df.loc[idx, 'Color'] = c_col
                else:
                    if not str(df.loc[idx, 'Flor']).strip():
                        df.loc[idx, 'Flor'] = "Estándar"
                    if not str(df.loc[idx, 'Color']).strip():
                        df.loc[idx, 'Color'] = "Mix"

            for cn in ["Stock_Cuarto_Frio", "Esquejes_Recepcion", "Bajas_Descartes", "Esquejes_Requeridos", "Compensacion_Volumen", "Reprogramado_Siguiente_Semana"]:
                if cn not in df.columns:
                    df[cn] = 0
                df[cn] = pd.to_numeric(df[cn], errors='coerce').fillna(0).astype(int)

            df['Total_Disponible'] = df['Stock_Cuarto_Frio'] + df['Esquejes_Recepcion'] - df['Bajas_Descartes']
            df['Diferencia_Recepcion'] = df['Esquejes_Recepcion'] - df['Esquejes_Requeridos']
            df['Esquejes_Efectivos_Clavar'] = df.apply(calcular_esquejes_efectivos_clavar, axis=1)
            df['Diferencia_Saldo'] = df['Total_Disponible'] - df['Esquejes_Efectivos_Clavar']
            df['Remanente_Final'] = df['Diferencia_Saldo'].apply(lambda x: max(0, x))
            df['Bandejas_112_Disponibles'] = df['Esquejes_Efectivos_Clavar'].apply(calcular_bandejas_redondeadas)
            df['Estado_Disponibilidad'] = df.apply(calcular_estado_disponibilidad, axis=1)
            return df

        # Barra de botones debajo del editor: los cálculos se realizan solo al presionar las acciones
        b_col1, b_col2, b_col3, b_col4, b_col5 = st.columns([2.5, 2.8, 2.0, 1.8, 1.6])
        with b_col1:
            if st.button("🧮 Calcular Balances y Validar", key=f"btn_calc_inv_{cod_sem}", type="primary", help="Ejecuta el recálculo consolidado de disponibilidad, diferencias y bandejas de todas las filas ingresadas (incluyendo extemporáneos)."):
                df_calc = procesar_calculo_inventario(df_inv_editado, cod_sem)
                st.session_state[session_key_inv] = df_calc
                st.session_state[version_inv_key] = ver_inv + 1
                st.success("✅ Balances calculados exitosamente con autocompletado de catálogo.")
                st.rerun()

        with b_col2:
            if st.button("🔄 Compensar y Aprovechar Excedentes", key=f"btn_comp_inv_{cod_sem}", help="1) Compensa faltantes jerárquicamente (Flor-Color / Color), 2) Si hay espacio en campo (≤1,120 camas), absorbe excedentes físicos viables a siembra dentro del +10% de mercado."):
                df_calc = procesar_calculo_inventario(df_inv_editado, cod_sem)
                df_comp, advertencias = ejecutar_compensacion_inventario(df_calc, semana_enraizamiento=cod_sem, absorber_excedentes_a_campo=True, db=db)
                st.session_state[session_key_inv] = df_comp
                st.session_state[adv_comp_key] = advertencias
                guardar_inventario_recepcion(df_comp, semana_enraizamiento=cod_sem)
                st.session_state[version_inv_key] = ver_inv + 1
                st.success("✅ Compensación jerárquica y absorción de excedentes a campo ejecutada y sincronizada.")
                st.rerun()

        with b_col3:
            if st.button("💾 Guardar Inventario", key=f"btn_guardar_inv_{cod_sem}", help="Calcula y guarda permanentemente este inventario en Recepcion_Inventario_Esquejes.csv"):
                df_calc = procesar_calculo_inventario(df_inv_editado, cod_sem)
                exito = guardar_inventario_recepcion(df_calc, semana_enraizamiento=cod_sem)
                if exito:
                    st.session_state[session_key_inv] = df_calc
                    st.session_state[version_inv_key] = ver_inv + 1
                    st.success("✅ Inventario calculado y guardado exitosamente.")
                    st.rerun()
                else:
                    st.error("❌ Error al guardar el inventario.")

        with b_col4:
            if st.button("📥 Resetear desde Plano", key=f"btn_precargar_inv_{cod_sem}", help="Reinicia la planilla con los requerimientos exactos del plano operativo de la semana."):
                df_nuevo = precargar_inventario_desde_plano(res_plano)
                st.session_state[session_key_inv] = df_nuevo
                if adv_comp_key in st.session_state:
                    del st.session_state[adv_comp_key]
                st.session_state[version_inv_key] = ver_inv + 1
                st.rerun()

        with b_col5:
            excel_inv = io.BytesIO()
            with pd.ExcelWriter(excel_inv, engine='openpyxl') as writer:
                df_inv_editado.to_excel(writer, index=False, sheet_name='Recepcion_Inventario')
            st.download_button(
                label="📊 Excel",
                data=excel_inv.getvalue(),
                file_name=f"Recepcion_e_Inventario_{res_plano['semana_enraizamiento_label']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"dl_inv_{cod_sem}"
            )

        # ----------------------------------------------------------------------
        # CUADRO RESUMEN: DISPONIBILIDAD DE EXCEDENTES POR FLOR-COLOR
        # ----------------------------------------------------------------------
        df_resumen_exc = generar_resumen_excedentes_flor_color(df_inv_current)

        st.markdown("---")
        st.markdown("##### 🌸 Cuadro Resumen: Disponibilidad de Excedentes por Flor-Color")
        st.caption(
            "Consolida las combinaciones de Flor y Color que presentan excedente físico o saldo remanente. "
            "Aplica la **regla agronómica de media cama (≥0.5 camas / ≥2,500 esquejes / ≥23 bandejas)** tanto para "
            "determinar el material viable para compensación o siembra, como para resguardar saldos menores en cuarto frío "
            "sin fraccionar camas con micro-lotes en campo."
        )

        if df_resumen_exc.empty:
            st.info("ℹ️ No se registran excedentes físicos ni saldos remanentes en esta semana; el inventario se encuentra en equilibrio o con faltantes en seguimiento.")
        else:
            tot_exc_esq = int(df_resumen_exc['Excedente_Total'].sum())
            tot_exc_ban = int(df_resumen_exc['Bandejas_112_Excedente'].sum())
            tot_rem_esq = int(df_resumen_exc['Remanente_Cuarto_Frio'].sum())
            tot_rem_ban = int(df_resumen_exc['Bandejas_112_Remanente'].sum())
            tot_comp_don = int(df_resumen_exc['Compensado_Donado'].sum())

            num_viables = len(df_resumen_exc[df_resumen_exc['Remanente_Cuarto_Frio'] >= MINIMO_COMPENSACION_ESQUEJES])
            num_resguardo = len(df_resumen_exc[(df_resumen_exc['Remanente_Cuarto_Frio'] > UMBRAL_DIFERENCIA_DESPRECIABLE) & (df_resumen_exc['Remanente_Cuarto_Frio'] < MINIMO_COMPENSACION_ESQUEJES)])

            # 4 Tarjetas de Control de Excedentes
            rx1, rx2, rx3, rx4 = st.columns(4)
            rx1.metric(
                "Flor-Colores con Excedente",
                f"{len(df_resumen_exc)} combinaciones",
                f"{num_viables} viables (≥0.5 cam) | {num_resguardo} en frío (<0.5)"
            )
            rx2.metric(
                "Excedente Físico Total",
                f"{tot_exc_esq:,d} esquejes",
                f"{tot_exc_ban:,d} bandejas (112) eq."
            )
            rx3.metric(
                "Volumen Donado / Compensado",
                f"{tot_comp_don:,d} esquejes",
                "Asumido para cubrir faltantes"
            )
            rx4.metric(
                "Remanente en Cuarto Frío",
                f"{tot_rem_esq:,d} esquejes",
                f"{tot_rem_ban:,d} bandejas ({tot_rem_esq/5200.0:.1f} camas eq.)",
                delta_color="normal"
            )

            # Preparar tabla para visualización limpia
            cols_resumen_visibles = [
                "Flor", "Color", "Num_Variedades", "Variedades_Aportantes",
                "Esquejes_Requeridos", "Total_Disponible", "Excedente_Total",
                "Bandejas_112_Excedente", "Camas_Eq_Excedente",
                "Compensado_Donado", "Remanente_Cuarto_Frio",
                "Bandejas_112_Remanente", "Camas_Eq_Remanente",
                "Clasificacion_Agronomica", "Accion_Sugerida"
            ]

            st.dataframe(
                df_resumen_exc[cols_resumen_visibles],
                column_config={
                    "Flor": st.column_config.TextColumn("Tipo Flor"),
                    "Color": st.column_config.TextColumn("Color"),
                    "Num_Variedades": st.column_config.NumberColumn("N° Vars", format="%d"),
                    "Variedades_Aportantes": st.column_config.TextColumn("Variedades con Excedente", help="Variedades específicas que aportan este excedente o saldo"),
                    "Esquejes_Requeridos": st.column_config.NumberColumn("Req. Plano", format="%d"),
                    "Total_Disponible": st.column_config.NumberColumn("Total Disp.", format="%d"),
                    "Excedente_Total": st.column_config.NumberColumn("Excedente Bruto", format="%d", help="Total disponible menos requerimiento original"),
                    "Bandejas_112_Excedente": st.column_config.NumberColumn("Bandejas Exc.", format="%d"),
                    "Camas_Eq_Excedente": st.column_config.NumberColumn("Camas Exc. Eq.", format="%.1f"),
                    "Compensado_Donado": st.column_config.NumberColumn("Donado Comp.", format="%d", help="Volumen transferido para cubrir déficits compatibles"),
                    "Remanente_Cuarto_Frio": st.column_config.NumberColumn("Remanente en Frío", format="%d", help="Saldo final protegido en cuarto frío"),
                    "Bandejas_112_Remanente": st.column_config.NumberColumn("Bandejas Frío (112)", format="%d"),
                    "Camas_Eq_Remanente": st.column_config.NumberColumn("Camas Frío Eq.", format="%.1f"),
                    "Clasificacion_Agronomica": st.column_config.TextColumn("Clasificación Agronómica"),
                    "Accion_Sugerida": st.column_config.TextColumn("Destino / Acción Agronómica")
                },
                hide_index=True,
                width="stretch"
            )

            # Botón de descarga de este resumen a Excel
            excel_exc_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_exc_buffer, engine='openpyxl') as writer:
                df_resumen_exc.to_excel(writer, index=False, sheet_name='Excedentes_Flor_Color')
            st.download_button(
                label="📊 Descargar Resumen de Excedentes en Excel",
                data=excel_exc_buffer.getvalue(),
                file_name=f"Resumen_Excedentes_FlorColor_{res_plano['semana_enraizamiento_label']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"dl_exc_fc_{cod_sem}"
            )

    # -------------------------------------------------------------
    # TAB 3: REGISTRO DE EJECUTADO REAL Y DESCUENTO DE INVENTARIO
    # -------------------------------------------------------------
    with tab_ejecutado:
        st.markdown("##### ✅ Registro de Ejecutado Real de Enraizamiento (Clavado)")
        st.caption(
            "Captura el enraizamiento efectivamente clavado por lote y mesa. "
            "**Flujo Oficial:** Al aprobar la ejecución de la semana, el sistema descuenta automáticamente los esquejes "
            "reales del inventario disponible y transfiere el remanente de cuarto frío al inventario inicial de la siguiente semana."
        )

        session_key_ejec = f"df_ejec_real_{cod_sem}"
        version_ejec_key = f"ver_ejec_{cod_sem}"
        if version_ejec_key not in st.session_state:
            st.session_state[version_ejec_key] = 0

        if session_key_ejec not in st.session_state:
            df_ejec_guardado = cargar_ejecucion_real(cod_sem)
            if df_ejec_guardado is not None and not df_ejec_guardado.empty:
                st.session_state[session_key_ejec] = df_ejec_guardado
            else:
                st.session_state[session_key_ejec] = precargar_ejecucion_desde_plano(res_plano)

        df_ejec_current = st.session_state[session_key_ejec]

        # Garantizar eliminación de columnas secundarias que saturan la interfaz
        for c_drop in ["Operario", "Cuadrilla", "Cuadrilla_Clavado"]:
            if c_drop in df_ejec_current.columns:
                df_ejec_current = df_ejec_current.drop(columns=[c_drop])

        # Sanitizar tipos de datos para st.data_editor (sin operario para evitar saturar)
        cols_ejec_str = ["Semana_Enraizamiento", "Dia_Clavado", "Fecha_Clavado", "Flor", "Color", "Variedad", "Bloque_Destino", "Semana_Siembra_Proyectada", "Estado", "Observaciones"]
        for c in cols_ejec_str:
            if c in df_ejec_current.columns:
                df_ejec_current[c] = df_ejec_current[c].fillna("").astype(str)
        cols_ejec_int = ["Bandejas_Programadas", "Esquejes_Programados", "Bandejas_Reales", "Esquejes_Reales"]
        for c in cols_ejec_int:
            if c in df_ejec_current.columns:
                df_ejec_current[c] = pd.to_numeric(df_ejec_current[c], errors='coerce').fillna(0).astype(int)
        cols_ejec_flt = ["Camas_Reales", "Cumplimiento_Pct"]
        for c in cols_ejec_flt:
            if c in df_ejec_current.columns:
                df_ejec_current[c] = pd.to_numeric(df_ejec_current[c], errors='coerce').fillna(0.0).astype(float)

        # Recálculo derivado en df_ejec_current
        df_ejec_current['Esquejes_Reales'] = df_ejec_current['Bandejas_Reales'] * CAVIDADES_POR_BANDEJA
        def calc_cumpl_cur(row):
            prog = row.get('Esquejes_Programados', 0)
            real = row.get('Esquejes_Reales', 0)
            return round((real / prog * 100.0), 1) if prog > 0 else 100.0
        df_ejec_current['Cumplimiento_Pct'] = df_ejec_current.apply(calc_cumpl_cur, axis=1)

        # KPIs de Ejecutado Real
        tot_ban_prog = int(df_ejec_current['Bandejas_Programadas'].sum()) if not df_ejec_current.empty and 'Bandejas_Programadas' in df_ejec_current.columns else 0
        tot_ban_real = int(df_ejec_current['Bandejas_Reales'].sum()) if not df_ejec_current.empty and 'Bandejas_Reales' in df_ejec_current.columns else 0
        tot_esq_prog = int(df_ejec_current['Esquejes_Programados'].sum()) if not df_ejec_current.empty and 'Esquejes_Programados' in df_ejec_current.columns else 0
        tot_esq_real = int(df_ejec_current['Esquejes_Reales'].sum()) if not df_ejec_current.empty and 'Esquejes_Reales' in df_ejec_current.columns else 0
        tot_camas_real = float(df_ejec_current['Camas_Reales'].sum()) if not df_ejec_current.empty and 'Camas_Reales' in df_ejec_current.columns else 0.0
        cumpl_global = (tot_esq_real / tot_esq_prog * 100.0) if tot_esq_prog > 0 else 100.0

        me_1, me_2, me_3, me_4 = st.columns(4)
        me_1.metric("Bandejas Reales Clavadas", f"{tot_ban_real:,d}", f"Prog: {tot_ban_prog:,d} ({tot_ban_real - tot_ban_prog:+,d})")
        me_2.metric("Esquejes Reales Clavados", f"{tot_esq_real:,d}", f"{tot_esq_real - tot_esq_prog:+,d} vs prog", delta_color="normal" if tot_esq_real >= tot_esq_prog else "inverse")
        me_3.metric("% Cumplimiento Clavado", f"{cumpl_global:.1f}%", "Meta: 100%")
        me_4.metric("Camas para Siembra Campo", f"{tot_camas_real:.1f} cam.", f"Siembra {res_plano['semana_siembra_label']}")

        # Editor Interactivo Reactivo (Limpio, sin columna Operario/Cuadrilla)
        ver_ejec = st.session_state[version_ejec_key]
        editor_ejec_key = f"editor_ejec_{cod_sem}_{ver_ejec}"

        # Definir orden estricto de columnas visibles (sin Operario / Cuadrilla)
        cols_orden_editor_ejec = [
            "Semana_Enraizamiento", "Dia_Clavado", "Fecha_Clavado", "Flor", "Color",
            "Variedad", "Bloque_Destino", "Bandejas_Programadas", "Esquejes_Programados",
            "Bandejas_Reales", "Esquejes_Reales", "Camas_Reales", "Cumplimiento_Pct",
            "Semana_Siembra_Proyectada", "Estado", "Observaciones"
        ]

        # Consolidar opciones oficiales de variedades para lista desplegable en ejecutado
        nombres_existentes_ejec = set(df_ejec_current['Variedad'].dropna().astype(str).str.strip())
        lista_opciones_ejec = sorted(list(set(lista_nombres_db) | {n for n in nombres_existentes_ejec if n}))

        df_ejec_current = df_ejec_current.reset_index(drop=True)
        df_ejec_editado = st.data_editor(
            df_ejec_current,
            key=editor_ejec_key,
            column_order=cols_orden_editor_ejec,
            num_rows="dynamic",
            width="stretch",
            column_config={
                "Semana_Enraizamiento": st.column_config.TextColumn("Sem. Enr.", disabled=True),
                "Dia_Clavado": st.column_config.SelectboxColumn("Día Clavado", options=["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"], required=True),
                "Fecha_Clavado": st.column_config.TextColumn("Fecha"),
                "Flor": st.column_config.TextColumn("Flor", disabled=True, help="Autocompletado automáticamente según el catálogo"),
                "Color": st.column_config.TextColumn("Color", disabled=True, help="Autocompletado automáticamente según el catálogo"),
                "Variedad": st.column_config.SelectboxColumn("Variedad", options=lista_opciones_ejec, required=True, help="Seleccione variedad del catálogo oficial (514 variedades)"),
                "Bloque_Destino": st.column_config.TextColumn("Bloque Destino"),
                "Bandejas_Programadas": st.column_config.NumberColumn("Bandejas Prog.", disabled=True, format="%d"),
                "Esquejes_Programados": st.column_config.NumberColumn("Esquejes Prog.", disabled=True, format="%d"),
                "Bandejas_Reales": st.column_config.NumberColumn("Bandejas Reales", min_value=0, step=1, format="%d", help="Bandejas de 112 cavidades clavadas realmente. Al modificar, ajusta esquejes reales automáticamente."),
                "Esquejes_Reales": st.column_config.NumberColumn("Esquejes Reales", min_value=0, step=112, format="%d", help="Esquejes clavados realmente. Se recalcula automáticamente a partir de bandejas reales."),
                "Camas_Reales": st.column_config.NumberColumn("Camas Siembra Eq.", format="%.2f", disabled=True),
                "Cumplimiento_Pct": st.column_config.NumberColumn("% Cumpl.", disabled=True, format="%.1f%%"),
                "Semana_Siembra_Proyectada": st.column_config.TextColumn("Sem. Siembra (+3w)", disabled=True),
                "Estado": st.column_config.SelectboxColumn("Estado", options=["🟢 Clavado OK", "🟡 Parcial", "🔴 Pendiente", "⚪ Descartado"]),
                "Observaciones": st.column_config.TextColumn("Observaciones / Descarte")
            },
            hide_index=True
        )

        # Función de procesamiento consolidado de clavado real
        def procesar_calculo_ejecucion(df_edit, sem_actual):
            df = df_edit.copy()
            today_str = date.today().strftime('%Y-%m-%d')
            if 'Semana_Enraizamiento' in df.columns:
                df['Semana_Enraizamiento'] = df['Semana_Enraizamiento'].fillna(str(sem_actual)).replace('', str(sem_actual))
            else:
                df['Semana_Enraizamiento'] = str(sem_actual)

            if 'Fecha_Clavado' in df.columns:
                df['Fecha_Clavado'] = df['Fecha_Clavado'].fillna(today_str).replace('', today_str)
            if 'Dia_Clavado' in df.columns:
                df['Dia_Clavado'] = df['Dia_Clavado'].fillna("Lunes").replace('', "Lunes")

            if 'Variedad' in df.columns:
                df['Variedad'] = df['Variedad'].fillna("").astype(str)
                df = df[df['Variedad'].str.strip() != ''].copy()

            # Autocompletar Flor y Color desde el catálogo oficial
            for idx in df.index:
                v_nom = str(df.loc[idx, 'Variedad']).strip()
                v_low = v_nom.lower()
                if v_low in mapa_variedad_db:
                    c_flor, c_col = mapa_variedad_db[v_low]
                    df.loc[idx, 'Flor'] = c_flor
                    df.loc[idx, 'Color'] = c_col
                else:
                    if not str(df.loc[idx, 'Flor']).strip():
                        df.loc[idx, 'Flor'] = "Estándar"
                    if not str(df.loc[idx, 'Color']).strip():
                        df.loc[idx, 'Color'] = "Mix"

            df['Bandejas_Reales'] = pd.to_numeric(df.get('Bandejas_Reales', 0), errors='coerce').fillna(0).astype(int)
            df['Esquejes_Reales'] = df['Bandejas_Reales'] * CAVIDADES_POR_BANDEJA
            df['Bandejas_Programadas'] = pd.to_numeric(df.get('Bandejas_Programadas', 0), errors='coerce').fillna(0).astype(int)
            df['Esquejes_Programados'] = pd.to_numeric(df.get('Esquejes_Programados', 0), errors='coerce').fillna(0).astype(int)

            def calc_cumpl_r(row):
                prog = row.get('Esquejes_Programados', 0)
                real = row.get('Esquejes_Reales', 0)
                return round((real / prog * 100.0), 1) if prog > 0 else 100.0

            df['Cumplimiento_Pct'] = df.apply(calc_cumpl_r, axis=1)
            df['Camas_Reales'] = (df['Esquejes_Reales'] / 5081.0).round(2)

            def calc_estado_auto(row):
                c = row.get('Cumplimiento_Pct', 100.0)
                est = str(row.get('Estado', ''))
                if est in ["⚪ Descartado", "🔴 Pendiente"]:
                    return est
                if c >= 98.0:
                    return "🟢 Clavado OK"
                elif c > 0:
                    return "🟡 Parcial"
                else:
                    return "🔴 Pendiente"
            df['Estado'] = df.apply(calc_estado_auto, axis=1)
            return df

        # Botones de Acción debajo del editor: cálculo bajo demanda
        be_col1, be_col2, be_col3, be_col4, be_col5 = st.columns([2.2, 2.8, 1.8, 1.8, 1.6])
        with be_col1:
            if st.button("🧮 Calcular Cumplimiento", key=f"btn_calc_ejec_{cod_sem}", help="Recalcula esquejes reales, % de cumplimiento y camas para todas las filas."):
                df_calc_ej = procesar_calculo_ejecucion(df_ejec_editado, cod_sem)
                st.session_state[session_key_ejec] = df_calc_ej
                st.session_state[version_ejec_key] = ver_ejec + 1
                st.success("✅ Cumplimiento recalculado exitosamente.")
                st.rerun()

        with be_col2:
            if st.button("✅ Aprobar y Descontar de Inventario", key=f"btn_aprobar_ejec_{cod_sem}", type="primary", help="Aprueba formalmente la ejecución, descuenta los esquejes clavados del inventario y transfiere el remanente a la siguiente semana."):
                df_calc_ej = procesar_calculo_ejecucion(df_ejec_editado, cod_sem)
                res_aprob = aprobar_ejecucion_y_descontar_inventario(
                    semana_enraizamiento=cod_sem,
                    df_ejecucion_semana=df_calc_ej,
                    df_inventario_semana=st.session_state.get(session_key_inv, df_inv_current)
                )
                if res_aprob.get("exito"):
                    st.session_state[session_key_inv] = res_aprob["df_inv_actualizado"]
                    st.session_state[session_key_ejec] = df_calc_ej
                    st.session_state[version_inv_key] = st.session_state.get(version_inv_key, 0) + 1
                    st.session_state[version_ejec_key] = ver_ejec + 1
                    st.success(
                        f"🎉 **¡Ejecución Aprobada y Descontada!** Se descontaron **{res_aprob['total_clavado']:,d} esquejes** del inventario. "
                        f"Saldo remanente final: **{res_aprob['total_remanente']:,d} esquejes** transferidos automáticamente como stock inicial de cuarto frío para la **Semana S{res_aprob['semana_siguiente'][2:]}**."
                    )
                    st.rerun()
                else:
                    st.error(f"❌ Error al aprobar: {res_aprob.get('mensaje')}")

        with be_col3:
            if st.button("💾 Guardar Ejecutado", key=f"btn_guardar_ejec_{cod_sem}", help="Calcula y guarda los registros de clavado en Ejecucion_Real_Enraizamiento.csv."):
                df_calc_ej = procesar_calculo_ejecucion(df_ejec_editado, cod_sem)
                exito_ej = guardar_ejecucion_real(df_calc_ej, semana_enraizamiento=cod_sem)
                if exito_ej:
                    st.session_state[session_key_ejec] = df_calc_ej
                    st.session_state[version_ejec_key] = ver_ejec + 1
                    st.success("✅ Ejecutado real guardado.")
                    st.rerun()
                else:
                    st.error("❌ Error al guardar el ejecutado real.")

        with be_col4:
            if st.button("📥 Resetear Lotes", key=f"btn_precargar_ejec_{cod_sem}", help="Reinicia la planilla con los lotes programados de la semana."):
                df_nuevo_ej = precargar_ejecucion_desde_plano(res_plano)
                st.session_state[session_key_ejec] = df_nuevo_ej
                st.session_state[version_ejec_key] = ver_ejec + 1
                st.rerun()

        with be_col5:
            excel_ej = io.BytesIO()
            with pd.ExcelWriter(excel_ej, engine='openpyxl') as writer:
                df_ejec_editado.to_excel(writer, index=False, sheet_name='Ejecutado_Real')
            st.download_button(
                label="📊 Excel",
                data=excel_ej.getvalue(),
                file_name=f"Ejecutado_Real_{res_plano['semana_enraizamiento_label']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"dl_ejec_{cod_sem}"
            )

        st.info(
            f"ℹ️ **Vínculo con el Módulo de Siembras:** Este registro alimenta directamente la disponibilidad de material vegetal vivo para la semana **{res_plano['semana_siembra_label']}** (fecha de trasplante a campo). "
            f"Al ingresar al próximo Módulo de Siembras, el plano de campo tomará estas **{tot_ban_real:,d} bandejas ({tot_esq_real:,d} esquejes)** reales."
        )

    # -------------------------------------------------------------
    # TAB 2: DISTRIBUCIÓN DIARIA Y CUADRILLA
    # -------------------------------------------------------------
    with tab_mano_obra:
        st.markdown("##### ⏱️ Balance de Capacidad y Mano de Obra Semanal")
        st.caption(
            f"Consolida las horas de labor demandadas por el volumen total de enraizamiento contra la capacidad "
            f"efectiva de la cuadrilla asignada para la semana completa (base laboral {TOTAL_HORAS_SEMANA_ESTANDAR:.1f}h efectivas, deduciendo 30 min de almuerzo L-V)."
        )

        # 1. Tabla de Operarios Requeridos Consolidada por Semana
        bal = mano_obra.get("balance_semanal_operarios", 0)
        estado_sem = "🟢 CUBIERTA" if bal >= 0 else ("🟡 AJUSTADA" if bal >= -1.0 else f"🔴 SOBRECARGA (+{abs(bal):.0f} ref.)")
        df_resumen_semanal = pd.DataFrame([{
            "Semana": res_plano['semana_enraizamiento_label'],
            "Jornada Efectiva": f"{TOTAL_HORAS_SEMANA_ESTANDAR:.1f} h",
            "Total Esquejes": kpis['total_esquejes'],
            "Bandejas (112)": kpis['total_bandejas'],
            "Rendimiento Ponderado": f"{kpis['rendimiento_ponderado']:,.0f} esq/h",
            "Horas Requeridas": kpis['horas_requeridas'],
            "Operarios Requeridos": mano_obra['promedio_operarios_requeridos'],
            "Operarios Asignados": tot_op_fijos,
            "Balance Semanal": bal,
            "Estado Capacidad": estado_sem
        }])

        st.dataframe(
            df_resumen_semanal,
            column_config={
                "Semana": st.column_config.TextColumn("Semana"),
                "Jornada Efectiva": st.column_config.TextColumn("Jornada Efectiva"),
                "Total Esquejes": st.column_config.NumberColumn("Total Esquejes", format="%d"),
                "Bandejas (112)": st.column_config.NumberColumn("Bandejas (112)", format="%d"),
                "Rendimiento Ponderado": st.column_config.TextColumn("Rend. Ponderado"),
                "Horas Requeridas": st.column_config.NumberColumn("Horas Requeridas", format="%.1f h"),
                "Operarios Requeridos": st.column_config.NumberColumn("Op. Requeridos", format="%.1f"),
                "Operarios Asignados": st.column_config.NumberColumn("Op. Asignados", format="%d"),
                "Balance Semanal": st.column_config.NumberColumn("Balance Semanal", format="%+.1f"),
                "Estado Capacidad": st.column_config.TextColumn("Estado de Capacidad")
            },
            hide_index=True,
            width="stretch"
        )

        # 2. Desglose y Gráficos por Día
        with st.expander("🔍 Ver Distribución Diaria y Balance por Día (Detalle de Jornada)", expanded=True):
            st.dataframe(
                df_res_dia,
                column_config={
                    "Día": st.column_config.TextColumn("Día"),
                    "Jornada (Horas)": st.column_config.NumberColumn("Jornada Efectiva", format="%.1f h"),
                    "Esquejes": st.column_config.NumberColumn("Esquejes", format="%d"),
                    "Bandejas (112)": st.column_config.NumberColumn("Bandejas (112)", format="%d"),
                    "% Semana": st.column_config.NumberColumn("% Semana", format="%.1f %%"),
                    "Horas Requeridas": st.column_config.NumberColumn("Horas Requeridas", format="%.1f h"),
                    "Operarios Requeridos": st.column_config.NumberColumn("Operarios Req.", format="%.1f"),
                    "Operarios Asignados": st.column_config.NumberColumn("Operarios Asignados", format="%d"),
                    "Balance Operarios": st.column_config.NumberColumn("Balance", format="%+.1f"),
                    "Estado": st.column_config.TextColumn("Estado de Capacidad")
                },
                hide_index=True,
                width="stretch"
            )

        # Gráficos Visuales de Distribución y Horas
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            st.markdown("###### 📊 Volumen de Esquejes por Día")
            chart_esq = alt.Chart(df_res_dia).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, color="#0070F2").encode(
                x=alt.X('Día:N', sort=["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"], title="Día de la Semana"),
                y=alt.Y('Esquejes:Q', title="Esquejes Programados"),
                tooltip=['Día', 'Esquejes', 'Bandejas (112)', '% Semana']
            ).properties(height=300)
            st.altair_chart(chart_esq, width="stretch")

        with col_g2:
            st.markdown("###### ⏱️ Horas Requeridas vs Horas Disponibles Cuadrilla")
            
            # Calcular horas disponibles por día
            df_chart_h = df_res_dia.copy()
            df_chart_h['Horas Disponibles'] = df_chart_h['Jornada (Horas)'] * tot_op_fijos
            
            df_melted = pd.melt(
                df_chart_h, 
                id_vars=['Día'], 
                value_vars=['Horas Requeridas', 'Horas Disponibles'],
                var_name='Tipo', 
                value_name='Horas'
            )
            
            chart_h = alt.Chart(df_melted).mark_bar(opacity=0.85).encode(
                x=alt.X('Día:N', sort=["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"], title="Día"),
                y=alt.Y('Horas:Q', title="Horas de Mano de Obra"),
                color=alt.Color('Tipo:N', scale=alt.Scale(domain=['Horas Requeridas', 'Horas Disponibles'], range=['#BB0000', '#0070F2'])),
                xOffset='Tipo:N',
                tooltip=['Día', 'Tipo', alt.Tooltip('Horas:Q', format='.1f')]
            ).properties(height=300)
            st.altair_chart(chart_h, width="stretch")

        # Alertas o Recomendaciones Operativas
        dias_sobrecargados = df_res_dia[df_res_dia['Balance Operarios'] < -1.0]
        if not dias_sobrecargados.empty:
            dias_str = ", ".join(dias_sobrecargados['Día'].tolist())
            max_def = abs(dias_sobrecargados['Balance Operarios'].min())
            st.error(
                f"🚨 **Déficit de Mano de Obra en los siguientes días:** {dias_str}. "
                f"Se requiere reforzar la cuadrilla con al menos **+{max_def:.0f} operarios de apoyo** "
                f"o autorizar horas extras en esos días para garantizar el cumplimiento del plan."
            )
        else:
            st.success("✅ **La capacidad de la cuadrilla cubre holgadamente la demanda de enraizamiento de esta semana.**")

    # -------------------------------------------------------------
    # TAB 3: PROYECCIÓN DE COSECHA, FORECAST Y CAMAS
    # -------------------------------------------------------------
    with tab_comparativa:
        datos_comp = obtener_datos_comparativos_enraizamiento_y_camas(
            db,
            modo_plan=modo_plan,
            factor_expansion=factor_expansion,
            correr_variedades=correr_variedades
        )
        df_comp = datos_comp.get('df_comp_enraizamiento', pd.DataFrame())
        df_lib = datos_comp.get('df_liberacion_camas', pd.DataFrame())
        df_cvp = datos_comp.get('df_cosecha_vs_plan', pd.DataFrame())
        df_proy_c = res_plano.get('df_proyeccion_cosecha', pd.DataFrame())

        # ---------------------------------------------------------
        # 1. Proyección Biológica de Cosecha del Plano Seleccionado
        # ---------------------------------------------------------
        st.markdown(f"##### 🌿 Proyección Biológica de Cosecha — Enraizamiento {res_plano['semana_enraizamiento_label']} (Siembra {res_plano['semana_siembra_label']})")
        st.caption(
            f"Distribución de cosecha resultante calculada lote a lote aplicando las curvas fenológicas dinámicas "
            f"de cada variedad (días inicio, días pico y perfil c₁ a c₁₅). Temporada objetivo: **{res_plano['temporada']}**."
        )

        if not df_proy_c.empty:
            tot_proy_sem = int(df_proy_c['Tallos_Proyectados'].sum())
            row_pico_c = df_proy_c.loc[df_proy_c['Tallos_Proyectados'].idxmax()]
            sem_pico_lbl = str(row_pico_c['Semana_Cosecha_Label'])
            tallos_pico_val = int(row_pico_c['Tallos_Proyectados'])
            pct_pico = float(row_pico_c['% del Total Lote'])
            ventana_c = f"{df_proy_c['Semana_Cosecha_Label'].iloc[0]} a {df_proy_c['Semana_Cosecha_Label'].iloc[-1]} ({len(df_proy_c)} semanas)"

            col_pc1, col_pc2, col_pc3, col_pc4 = st.columns(4)
            col_pc1.metric("Tallos Proyectados Cosecha", f"{tot_proy_sem:,d}", f"Aprovechamiento biológico")
            col_pc2.metric("Semana Pico de Corte", f"{sem_pico_lbl}", f"{tallos_pico_val:,d} tallos")
            col_pc3.metric("Concentración en Pico", f"{pct_pico:.1f} %", "Volumen en semana pico")
            col_pc4.metric("Ventana de Corte", ventana_c, f"{res_plano['temporada']}")

            # Gráfico de Proyección de Cosecha Semanal
            chart_proy_c = alt.Chart(df_proy_c).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, color="#059669").encode(
                x=alt.X('Semana_Cosecha_Label:N', sort=df_proy_c['Semana_Cosecha_Label'].tolist(), title="Semana de Cosecha"),
                y=alt.Y('Tallos_Proyectados:Q', title="Tallos Proyectados a Cosecha"),
                tooltip=['Semana_Cosecha_Label', 'Temporada', alt.Tooltip('Tallos_Proyectados:Q', format=',d'), alt.Tooltip('% del Total Lote:Q', format='.1f')]
            ).properties(height=260)
            st.altair_chart(chart_proy_c, width="stretch")

            with st.expander(f"📋 Ver Detalle Numérico de Cosecha para {res_plano['semana_enraizamiento_label']}", expanded=False):
                st.dataframe(
                    df_proy_c[['Semana_Cosecha_Label', 'Temporada', 'Tallos_Proyectados', '% del Total Lote']],
                    column_config={
                        "Semana_Cosecha_Label": st.column_config.TextColumn("Semana Cosecha"),
                        "Temporada": st.column_config.TextColumn("Temporada"),
                        "Tallos_Proyectados": st.column_config.NumberColumn("Tallos Proyectados", format="%d"),
                        "% del Total Lote": st.column_config.NumberColumn("% Distribución", format="%.1f %%")
                    },
                    hide_index=True,
                    width="stretch"
                )
        else:
            st.info("No se registran curvas de cosecha para la selección actual.")

        st.markdown("---")

        # ---------------------------------------------------------
        # 2. Alineación de Cosecha vs Plan de Producción (ForeCast)
        # ---------------------------------------------------------
        st.markdown("##### 🎯 Alineación Cosecha vs Plan de Producción (ForeCast)")
        st.caption(
            "Compara la curva consolidada de cosecha que arroja la ejecución del plan de enraizamiento contra las metas semanales "
            "aprobadas en el módulo de Plan de Producción / ForeCast, garantizando sincronía entre propagación y corte comercial."
        )

        if not df_cvp.empty:
            temporadas_cvp = ["Todas las Semanas"] + [t for t in df_cvp['Temporada'].dropna().unique().tolist() if t]
            idx_temp_def = 0
            for idx_t, t_nom in enumerate(temporadas_cvp):
                if res_plano['temporada'].lower() in t_nom.lower() or t_nom.lower() in res_plano['temporada'].lower():
                    idx_temp_def = idx_t
                    break

            col_sel_f, col_spacer_f = st.columns([2, 3])
            with col_sel_f:
                filtro_temp = st.selectbox(
                    "Filtrar ventana de comparación:",
                    options=temporadas_cvp,
                    index=idx_temp_def,
                    help="Filtra la comparativa para la temporada de la semana seleccionada o visualiza todas las semanas del horizonte."
                )

            df_cvp_disp = df_cvp.copy()
            if filtro_temp != "Todas las Semanas":
                df_cvp_disp = df_cvp_disp[df_cvp_disp['Temporada'] == filtro_temp]

            tot_enr_cvp = int(df_cvp_disp['Tallos_Enraizamiento'].sum())
            tot_plan_cvp = int(df_cvp_disp['Tallos_Plan_Produccion'].sum())
            cumpl_glob = (tot_enr_cvp / tot_plan_cvp * 100.0) if tot_plan_cvp > 0 else 0.0
            diff_glob = tot_enr_cvp - tot_plan_cvp

            col_cp1, col_cp2, col_cp3, col_cp4 = st.columns(4)
            col_cp1.metric("Cosecha Enraizamiento", f"{tot_enr_cvp:,d}", "Curvas fenológicas")
            col_cp2.metric("Meta Plan Producción", f"{tot_plan_cvp:,d}", "Plan ForeCast Aprobado")
            col_cp3.metric(
                "Alineación Global", 
                f"{cumpl_glob:.1f} %", 
                f"{diff_glob:+,d} tallos",
                delta_color="normal" if cumpl_glob >= 95.0 else "inverse"
            )
            sem_pico_cvp = df_cvp_disp.loc[df_cvp_disp['Tallos_Enraizamiento'].idxmax()]['Semana_Cosecha_Label'] if not df_cvp_disp.empty else "-"
            col_cp4.metric("Semana Pico Enraizamiento", f"{sem_pico_cvp}", f"Ventana: {filtro_temp}")

            # Gráfico Comparativo: Enraizamiento Cosecha vs Plan de Producción
            df_melt_cvp = pd.melt(
                df_cvp_disp,
                id_vars=['Semana_Cosecha_Label', 'Temporada'],
                value_vars=['Tallos_Enraizamiento', 'Tallos_Plan_Produccion'],
                var_name='Fuente',
                value_name='Tallos'
            )
            df_melt_cvp['Fuente'] = df_melt_cvp['Fuente'].map({
                'Tallos_Enraizamiento': 'Cosecha Proyectada Enraizamiento',
                'Tallos_Plan_Produccion': 'Meta Plan Producción (ForeCast)'
            })

            chart_cvp = alt.Chart(df_melt_cvp).mark_bar(opacity=0.85).encode(
                x=alt.X('Semana_Cosecha_Label:N', sort=df_cvp_disp['Semana_Cosecha_Label'].tolist(), title="Semana de Cosecha"),
                y=alt.Y('Tallos:Q', title="Tallos Semanales"),
                color=alt.Color('Fuente:N', scale=alt.Scale(
                    domain=['Cosecha Proyectada Enraizamiento', 'Meta Plan Producción (ForeCast)'],
                    range=['#059669', '#0070F2']
                )),
                xOffset='Fuente:N',
                tooltip=['Semana_Cosecha_Label', 'Fuente', alt.Tooltip('Tallos:Q', format=',d'), 'Temporada']
            ).properties(height=320)

            st.altair_chart(chart_cvp, width="stretch")

            with st.expander("📋 Ver Tabla Comparativa Numérica: Cosecha Enraizamiento vs Plan Producción", expanded=False):
                st.dataframe(
                    df_cvp_disp[['Semana_Cosecha_Label', 'Temporada', 'Tallos_Enraizamiento', 'Tallos_Plan_Produccion', 'Diferencia', 'Cumplimiento_%']],
                    column_config={
                        "Semana_Cosecha_Label": st.column_config.TextColumn("Semana Cosecha"),
                        "Temporada": st.column_config.TextColumn("Temporada"),
                        "Tallos_Enraizamiento": st.column_config.NumberColumn("Cosecha Enraizamiento", format="%d"),
                        "Tallos_Plan_Produccion": st.column_config.NumberColumn("Meta Producción (ForeCast)", format="%d"),
                        "Diferencia": st.column_config.NumberColumn("Diferencia (Tallos)", format="%+d"),
                        "Cumplimiento_%": st.column_config.NumberColumn("Alineación %", format="%.1f %%")
                    },
                    hide_index=True,
                    width="stretch"
                )

        st.markdown("---")

        # ---------------------------------------------------------
        # 3. Comparativa de Esquejes por Semana (Plataforma vs Pedido)
        # ---------------------------------------------------------
        st.markdown("##### 📊 Comportamiento de Enraizamiento: Plataforma S&OP vs Pedido Programado")
        st.caption(
            f"Compara el volumen semanal de esquejes a ingresar en propagación entre la plataforma y el pedido programado "
            f"para el ciclo productivo ({res_plano['temporada']})."
        )

        dif_total_comp = int(df_comp['Diferencia_Esquejes'].abs().sum()) if not df_comp.empty and 'Diferencia_Esquejes' in df_comp.columns else 0
        if dif_total_comp == 0 and not df_comp.empty:
            st.info(
                "💡 **Alineación 100% con Plataforma S&OP:** Ambas series coinciden exactamente semana a semana porque el pedido consolidado "
                "de la plataforma (`PedidoConsolidado_master.xlsx`) ya fue actualizado mensualmente acorde a las curvas fenológicas de la finca. "
                "La analítica confirma sincronía total entre lo aprobado en plataforma comercial y el requerimiento operativo de propagación."
            )

        if not df_comp.empty:
            df_melt_enr = pd.melt(
                df_comp,
                id_vars=['Semana_Enraizamiento_Label', 'Temporada'],
                value_vars=['Enraizamiento_Plataforma', 'Enraizamiento_Analitica'],
                var_name='Fuente',
                value_name='Esquejes'
            )
            df_melt_enr['Fuente'] = df_melt_enr['Fuente'].map({
                'Enraizamiento_Plataforma': 'Plataforma S&OP',
                'Enraizamiento_Analitica': 'Pedido Programado (Analítica)'
            })

            chart_comp = alt.Chart(df_melt_enr).mark_bar(opacity=0.85).encode(
                x=alt.X('Semana_Enraizamiento_Label:N', title="Semana de Enraizamiento"),
                y=alt.Y('Esquejes:Q', title="Esquejes a Enraizar"),
                color=alt.Color('Fuente:N', scale=alt.Scale(domain=['Plataforma S&OP', 'Pedido Programado (Analítica)'], range=['#0070F2', '#D97706'])),
                xOffset='Fuente:N',
                tooltip=['Semana_Enraizamiento_Label', 'Fuente', alt.Tooltip('Esquejes:Q', format=',d'), 'Temporada']
            ).properties(height=320)

            st.altair_chart(chart_comp, width="stretch")

            with st.expander("📋 Ver Tabla Comparativa Numérica por Semana de Enraizamiento", expanded=False):
                st.dataframe(
                    df_comp[['Semana_Enraizamiento_Label', 'Semana_Siembra_Label', 'Semana_Cosecha_Label', 'Temporada', 'Enraizamiento_Plataforma', 'Enraizamiento_Analitica', 'Diferencia_Esquejes', 'Tallos_Esperados_Cosecha']],
                    column_config={
                        "Semana_Enraizamiento_Label": st.column_config.TextColumn("Sem. Enraiz."),
                        "Semana_Siembra_Label": st.column_config.TextColumn("Sem. Siembra"),
                        "Semana_Cosecha_Label": st.column_config.TextColumn("Sem. Cosecha"),
                        "Temporada": st.column_config.TextColumn("Temporada Objetivo"),
                        "Enraizamiento_Plataforma": st.column_config.NumberColumn("Plataforma (Esq)", format="%d"),
                        "Enraizamiento_Analitica": st.column_config.NumberColumn("Pedido Analítica (Esq)", format="%d"),
                        "Diferencia_Esquejes": st.column_config.NumberColumn("Diferencia", format="%+d"),
                        "Tallos_Esperados_Cosecha": st.column_config.NumberColumn("Tallos Cosecha", format="%d")
                    },
                    hide_index=True,
                    width="stretch"
                )

        st.markdown("---")

        # ---------------------------------------------------------
        # 4. Disponibilidad y Rotación de Camas Vivas en Campo
        # ---------------------------------------------------------
        st.markdown("##### 🚜 Análisis de Liberación y Rotación de Camas en Campo (Ajuste de Suelo: 3 vs 7 Días)")
        st.caption(
            "Evalúa la disponibilidad física de camas en campo provenientes del inventario vivo actual a medida que se "
            "cosechan y liberan, comparando la preparación de suelo estándar (7 días) contra el ajuste acelerado a 3 días."
        )

        if not df_lib.empty:
            sem_s_act = str(res_plano['semana_siembra'])
            row_act = df_lib[df_lib['Semana_Siembra'] == sem_s_act]
            if row_act.empty:
                row_act = df_lib.iloc[-1:]

            c_lib_3d = int(row_act['Camas_Liberadas_3d'].values[0])
            c_lib_7d = int(row_act['Camas_Liberadas_7d'].values[0])
            c_gain = int(row_act['Ganancia_Camas_Anticipadas'].values[0])
            c_req_sem = float(row_act['Camas_Requeridas_Semana'].values[0])
            c_req_acum = float(row_act['Camas_Requeridas_Acumuladas'].values[0])
            bal_disp = float(row_act['Balance_Disponibilidad_3d'].values[0])
            sem_lbl = str(row_act['Semana_Siembra_Label'].values[0])

            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            col_m1.metric(f"Camas Liberadas ({sem_lbl})", f"{c_lib_3d} camas", f"+{c_gain} camas con 3 días")
            col_m2.metric(f"Demanda Camas {sem_lbl}", f"{c_req_sem:.1f} camas", f"Acumulada: {c_req_acum:.1f} camas")
            col_m3.metric(
                "Superávit de Espacio", 
                f"{bal_disp:+.1f} camas", 
                "Holgura positiva garantizada" if bal_disp >= 0 else "Déficit de espacio",
                delta_color="normal" if bal_disp >= 0 else "inverse"
            )
            col_m4.metric("Días de Suelo", "3 Días", "-4 días vs estándar 7d")

            # Gráfico de Liberación de Camas vs Demanda
            df_melt_lib = pd.melt(
                df_lib,
                id_vars=['Semana_Siembra_Label'],
                value_vars=['Camas_Liberadas_7d', 'Camas_Liberadas_3d', 'Camas_Requeridas_Acumuladas'],
                var_name='Concepto',
                value_name='Camas'
            )
            df_melt_lib['Concepto'] = df_melt_lib['Concepto'].map({
                'Camas_Liberadas_7d': 'Liberación Estándar (7 días suelo)',
                'Camas_Liberadas_3d': 'Liberación Acelerada (3 días suelo)',
                'Camas_Requeridas_Acumuladas': 'Demanda de Camas Acumulada'
            })

            chart_lib = alt.Chart(df_melt_lib).mark_line(point=True).encode(
                x=alt.X('Semana_Siembra_Label:N', title="Semana de Siembra en Campo"),
                y=alt.Y('Camas:Q', title="Camas Físicas Acumuladas"),
                color=alt.Color('Concepto:N', scale=alt.Scale(
                    domain=['Liberación Estándar (7 días suelo)', 'Liberación Acelerada (3 días suelo)', 'Demanda de Camas Acumulada'],
                    range=['#64748B', '#059669', '#DC2626']
                )),
                strokeDash=alt.condition(
                    alt.datum.Concepto == 'Demanda de Camas Acumulada',
                    alt.value([5, 5]),
                    alt.value([0])
                ),
                tooltip=['Semana_Siembra_Label', 'Concepto', alt.Tooltip('Camas:Q', format='.1f')]
            ).properties(height=320)

            st.altair_chart(chart_lib, width="stretch")

            st.success(
                f"✅ **Evaluación de Espacio en Campo:** Reduciendo la preparación de suelo a **3 días**, se disponen de "
                f"**{c_lib_3d} camas liberadas** para la siembra en **{sem_lbl}** (ganando **+{c_gain} camas de anticipación**). "
                f"El balance acumulado arroja un saldo favorable de **{bal_disp:+.1f} camas libres**, garantizando holgura de área."
            )

    # -------------------------------------------------------------
    # TAB 4: VENTANA FENOLÓGICA Y PARÁMETROS
    # -------------------------------------------------------------
    with tab_fenologia:
        st.markdown("##### 🌿 Cadena Biológica y Fenología de Propagación")
        st.markdown(f"""
        1. **Enraizamiento en Banco ({res_plano['semana_enraizamiento_label']}):**
           - **Duración estándar:** {DIAS_PERMANENCIA_BANCO} días (3 semanas exactas) bajo niebla intermitente (*mist*).
           - **Contenedor:** Bandejas plásticas rígidas de **{CAVIDADES_POR_BANDEJA} cavidades**.
           - **Labor:** Clavado manual con desinfección preventiva y enraizador hormonal.
        
        2. **Trasplante a Suelo / Campo ({res_plano['semana_siembra_label']}):**
           - Desfase temporal: `Semana_Siembra = Semana_Enraizamiento + {SEMANAS_ENRAIZAMIENTO} semanas`.
           - **Pico de siembra:** Tradicionalmente programado los **jueves** para acoplar el fotoperiodo de iluminación nocturna.
           - **Camas estimadas:** A razón de ~5,200 plantas por cama estándar.
        
        3. **Floración y Cosecha Comercial ({res_plano.get('semana_cosecha_label', '')} | {res_plano['temporada']}):**
           - **Ciclo vegetativo:** Entre 68 y 84 días según la respuesta lumínica y fenológica de la variedad.
           - **Meta de calidad:** Concentrar el pico de corte los **jueves** de las semanas oficiales de temporada.
        """)

        st.markdown(f"##### 🕒 Horarios y Jornada Laboral Efectiva ({TOTAL_HORAS_SEMANA_ESTANDAR:.1f}h / Operario)")
        st.caption("A todos los días de lunes a viernes se les deduce 30 minutos (0.5 h) de almuerzo. El sábado no tiene deducción de almuerzo.")
        jornadas_data = [
            {"Día": "Lunes", "Horario Bruto": "6:00 am - 2:00 pm (8.0 h)", "Almuerzo Deducido": "30 min (0.5 h)", "Jornada Efectiva": "7.5 h", "Observación": "Jornada ordinaria completa"},
            {"Día": "Martes", "Horario Bruto": "6:00 am - 2:00 pm (8.0 h)", "Almuerzo Deducido": "30 min (0.5 h)", "Jornada Efectiva": "7.5 h", "Observación": "Jornada ordinaria completa"},
            {"Día": "Miércoles", "Horario Bruto": "6:00 am - 1:30 pm (7.5 h)", "Almuerzo Deducido": "30 min (0.5 h)", "Jornada Efectiva": "7.0 h", "Observación": "Jornada ordinaria recortada"},
            {"Día": "Jueves", "Horario Bruto": "6:00 am - 2:00 pm (8.0 h)", "Almuerzo Deducido": "30 min (0.5 h)", "Jornada Efectiva": "7.5 h", "Observación": "Pico de clavado de variedades"},
            {"Día": "Viernes", "Horario Bruto": "6:00 am - 2:00 pm (8.0 h)", "Almuerzo Deducido": "30 min (0.5 h)", "Jornada Efectiva": "7.5 h", "Observación": "Jornada ordinaria completa"},
            {"Día": "Sábado", "Horario Bruto": "6:00 am - 11:00 am (5.0 h)", "Almuerzo Deducido": "0 min (Sin deducción)", "Jornada Efectiva": "5.0 h", "Observación": "Media jornada sin almuerzo"},
        ]
        df_jornadas = pd.DataFrame(jornadas_data)
        st.table(df_jornadas)
        st.caption(f"**Total Jornada Semanal Efectiva:** {TOTAL_HORAS_SEMANA_ESTANDAR:.1f} horas / operario.")

