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

from app.ui.styles import (

    aplicar_tema_invernadero_industrial,

    estilizar_figura_plotly,

    PALETA_INVERNADERO,

    render_sap_shellbar,

    render_sap_page_header,

    render_sap_badge,

    render_sap_alert

)



st.set_page_config(page_title="Flores Corporativas S&OP | Planeación Integrada", layout="wide", page_icon="🌸")

aplicar_tema_invernadero_industrial()



def get_db():

    db = SessionLocal()

    try:

        yield db

    finally:

        db.close()



db = next(get_db())



from app.ui.fiori_components import (
    render_fiori_shellbar_and_navigation,
    render_fiori_app_header,
    render_fiori_launchpad_home,
    render_fiori_ovp_cards,
    render_fiori_worklist_alertas,
    render_fiori_visual_filter_bar,
    render_fiori_ibp_planning_grid,
    render_fiori_supply_chain_canvas,
    render_fiori_footer_toolbar,
    navigate_to_module
)

# Catálogo de secciones con títulos claros y en lenguaje ciudadano
MODULE_METADATA = {
    "Launchpad S&OP (Portada)": {
        "breadcrumb": "INICIO Y RESUMEN > PORTADA PRINCIPAL",
        "title": "Portada Principal de Planeación y Operaciones",
        "subtitle": "Tarjetas con el resumen al día de la finca, avisos importantes y acceso directo a todas las secciones.",
        "floorplan": "Vista: Portada de Accesos Rápidos",
        "badge": "10 Secciones Activas",
        "badge_type": "ok"
    },
    "Dashboard General": {
        "breadcrumb": "INICIO Y RESUMEN > TABLERO GENERAL",
        "title": "Tablero General de la Finca",
        "subtitle": "Resumen de plantas sembradas hoy en campo, gráficas por tipo de flor, avisos pendientes y carga de archivos base.",
        "floorplan": "Vista: Resumen General y Avisos",
        "badge": "Sistema al Día",
        "badge_type": "ok"
    },
    "Curvas e Índices (Campo)": {
        "breadcrumb": "DATOS DE CAMPO > RENDIMIENTO E HISTÓRICO",
        "title": "Curvas de Cosecha y Rendimiento en Campo",
        "subtitle": "Consulta cuántos días tarda en producir cada variedad, cuándo alcanza su pico y cuántos tallos da por planta.",
        "floorplan": "Vista: Consulta y Detalle por Variedad",
        "badge": "83 Curvas Validadas",
        "badge_type": "info"
    },
    "Calibración de Curvas": {
        "breadcrumb": "DATOS DE CAMPO > AJUSTE Y PRECISIÓN",
        "title": "Ajuste y Calibración de Cosechas",
        "subtitle": "Compara la flor que habíamos proyectado contra lo que realmente se cosechó para afinar los próximos cálculos.",
        "floorplan": "Vista: Comparativo Proyectado vs. Real",
        "badge": "Cálculo Ajustado",
        "badge_type": "info"
    },
    "ForeCast y Exportación": {
        "breadcrumb": "VENTAS Y COSECHA > PROYECCIÓN Y DESCARGAS",
        "title": "Proyección de Cosecha y Descarga de Formatos",
        "subtitle": "Unión clara de lo sembrado en tierra, lo que está en vivero y los pedidos futuros, comparada contra la meta de ventas.",
        "floorplan": "Vista: Análisis de Cosecha y Tabla Dinámica",
        "badge": "Cumplimiento 102.7%",
        "badge_type": "ok"
    },
    "Programación Diaria y Temporadas": {
        "breadcrumb": "VENTAS Y COSECHA > CORTE DIARIO Y TEMPORADAS",
        "title": "Programación Diaria de Corte y Temporadas Clave",
        "subtitle": "Reparto de tallos a cortar de lunes a sábado según las horas de trabajo y preparación para San Valentín y Madres.",
        "floorplan": "Vista: Reparto Diario y Temporadas",
        "badge": "San Valentín 2027",
        "badge_type": "warn"
    },
    "Plan de Producción (MVA)": {
        "breadcrumb": "PLANEACIÓN Y ESQUEJES > PLAN MAESTRO",
        "title": "Plan Maestro de Producción y Acuerdos con Ventas",
        "subtitle": "Revisión de pedidos comerciales frente a lo que realmente cabe y produce la finca.",
        "floorplan": "Vista: Acuerdos y Mezcla de Variedades",
        "badge": "Plan Aprobado",
        "badge_type": "ok"
    },
    "Ocupación de Área y Capacidad": {
        "breadcrumb": "PLANEACIÓN Y ESQUEJES > ESPACIO EN INVERNADEROS",
        "title": "Ocupación de Camas y Espacio en Invernaderos",
        "subtitle": "Control del espacio usado y libre en cada bloque para no sobrepasar las 1,120 camas disponibles.",
        "floorplan": "Vista: Capacidad Física y Recorrido del Cultivo",
        "badge": "Máximo 1,120 Camas",
        "badge_type": "info"
    },
    "Pedido Material Vegetal": {
        "breadcrumb": "PLANEACIÓN Y ESQUEJES > PEDIDO DE ESQUEJES",
        "title": "Solicitud y Seguimiento de Pedido de Esquejes",
        "subtitle": "Control de pedidos a proveedores con 24 semanas de anticipación, cambios a tiempo y variedades que salen.",
        "floorplan": "Vista: Control de Pedidos a Proveedores",
        "badge": "Pedido al Día",
        "badge_type": "ok"
    },
    "Plan de Enraizamiento": {
        "breadcrumb": "VIVERO Y SIEMBRA > PLAN DE VIVERO",
        "title": "Plan Semanal de Vivero (Enraizamiento)",
        "subtitle": "Organización diaria de bandejas de 112 cavidades, control de cuarto frío, reemplazos sugeridos y registro de lo clavado.",
        "floorplan": "Vista: Trabajo Semanal en Vivero",
        "badge": "Semana 42: 466k",
        "badge_type": "ok"
    },
    "Plan de Siembra": {
        "breadcrumb": "VIVERO Y SIEMBRA > PLAN DE SIEMBRA EN CAMPO",
        "title": "Plan Semanal de Siembra en Campo",
        "subtitle": "Programación de trasplante a camas definitivas usando únicamente las bandejas que ya enraizaron en vivero.",
        "floorplan": "Vista: Trabajo Semanal en Campo",
        "badge": "Operación Activa",
        "badge_type": "info"
    }
}

alertas_sop_global = obtener_alertas_sop()

# Nivel 1: Barra Superior Global y Navegación por Áreas de Trabajo
modulo = render_fiori_shellbar_and_navigation(db, engine, alertas_sop_global)

meta = MODULE_METADATA.get(modulo, {
    "breadcrumb": f"PLANEACIÓN > {modulo.upper()}",
    "title": modulo,
    "subtitle": "Sección operativa de planeación agrícola.",
    "floorplan": "Vista Operativa",
    "badge": "Activo",
    "badge_type": "info"
})

# Nivel 2: Cabecera de Sección
if modulo != "Launchpad S&OP (Portada)":
    render_fiori_app_header(
        breadcrumb=meta["breadcrumb"],
        title=meta["title"],
        subtitle=meta["subtitle"],
        floorplan_badge=meta.get("floorplan", "Vista General"),
        status_badge=meta["badge"],
        status_type=meta["badge_type"],
        module_key=modulo.replace(" ", "_").lower()
    )

from app.ui.curvas_ui import render_curvas_module
from app.ui.accuracy_ui import render_accuracy_module
from app.ui.actas_ui import render_actas_module
from app.ui.ocupacion_ui import render_ocupacion_module

if modulo == "Launchpad S&OP (Portada)":
    render_fiori_launchpad_home(db, engine, alertas_sop_global, key_suffix="portada")
    st.divider()
    render_fiori_worklist_alertas(alertas_sop_global, key_suffix="portada")
    st.divider()
    render_fiori_supply_chain_canvas(engine, key_suffix="portada")

elif modulo == "Dashboard General":
    with st.expander("🚀 Ver Tarjetas de Acceso Rápido a Todas las Secciones", expanded=False):
        render_fiori_launchpad_home(db, engine, alertas_sop_global, key_suffix="dash")

    

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

    

    col1.metric("Variedades en Campo", f"{total_vars_activas:,.0f}")

    col2.metric("Área Ocupada (m²)", f"{area_ocupada:,.2f}")

    col3.metric("Lotes Sembrados", f"{total_camas_sembradas:,.0f}")

    col4.metric("Plantas Sembradas", f"{total_plantas_sembradas:,.0f}")

    

    st.caption(f"ℹ️ **Inventario Vivo en Campo:** {total_vars_activas:,.0f} variedades activas en el plano actual (de {total_catalog:,} variedades registradas en el catálogo maestro).")

    

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

            

    # Tarjetas Modulares de Resumen del Cultivo
    st.markdown("")
    render_fiori_ovp_cards(engine, db, key_suffix="dash")

    # Lista de Avisos Importantes y Fechas de Corte
    st.markdown("")
    render_fiori_worklist_alertas(alertas_sop_global, key_suffix="dash")

    with st.expander("🕸️ Ver Mapa del Recorrido del Cultivo (Del Proveedor a la Cosecha)", expanded=False):
        render_fiori_supply_chain_canvas(engine, key_suffix="dash")

    # Panel de Gobernanza y Alertas S&OP
    st.markdown("")
    render_panel_alertas_sop()

    

    st.divider()

    

    st.subheader("Carga de Insumos Maestros")

    st.caption("Archivos base y catálogos de sincronización institucional para toda la plataforma.")

    

    col_ins1, col_ins2, col_ins3 = st.columns(3)

    

    with col_ins1:

        with st.container(border=True):

            st.markdown("#### 📖 Catálogo de Variedades")

            st.caption("Maestro oficial de especies, colores y variedades.")

            total_catalog = db.query(Variedad).count()

            flores_count = pd.read_sql("SELECT flor, count(*) as cant FROM variedades GROUP BY flor", engine)

            flores_str = ", ".join([f"{r['flor']}: {r['cant']}" for _, r in flores_count.iterrows()]) if not flores_count.empty else "Ninguna"

            

            if total_catalog > 0:

                st.info(f"**Registradas:** {total_catalog:,} variedades\n\n*{flores_str}*")

            else:

                st.warning("⚠️ No hay catálogo de variedades registrado.")

                

            if "ver_upload_vars" not in st.session_state:

                st.session_state["ver_upload_vars"] = 0

            if "flash_vars_success" in st.session_state:

                st.success(st.session_state.pop("flash_vars_success"))

                

            uploaded_vars = st.file_uploader(

                "Cargar Listado(s) de Variedades", 

                type=["xlsx", "xls"], 

                accept_multiple_files=True, 

                key=f"upload_vars_{st.session_state['ver_upload_vars']}"

            )

            if uploaded_vars:

                if st.button("Procesar Catálogo de Variedades", width="stretch", key="btn_proc_vars"):

                    with st.spinner("Procesando listados de variedades..."):

                        from app.services.variedad_service import procesar_archivos_variedades

                        res = procesar_archivos_variedades(uploaded_vars, db)

                        st.session_state["ver_upload_vars"] += 1

                        st.session_state["flash_vars_success"] = f"✅ Catálogo actualizado con éxito: {res.get('total_en_db', 0)} variedades en total ({res.get('insertadas', 0)} nuevas, {res.get('actualizadas', 0)} actualizadas)."

                        st.toast("✅ Catálogo de Variedades actualizado exitosamente.")

                        st.rerun()

                    

    with col_ins2:

        with st.container(border=True):

            st.markdown("#### 🚜 Plano de Siembra")

            st.caption("Inventario vivo actual en camas de cultivo.")

            if os.path.exists("last_dataset_name.txt"):

                with open("last_dataset_name.txt", "r") as f:

                    last_file = f.read().strip()

            else:

                last_file = "Ninguno"

                

            st.info(f"**Archivo en Uso:** {last_file}\n\n*Base oficial de camas sembradas*")

            

            if "ver_upload_siembras" not in st.session_state:

                st.session_state["ver_upload_siembras"] = 0

            if "flash_siembras_success" in st.session_state:

                st.success(st.session_state.pop("flash_siembras_success"))

                

            uploaded_file = st.file_uploader(

                "Cargar nuevo archivo de Siembras", 

                type=["xlsx", "xls"], 

                key=f"upload_siembras_{st.session_state['ver_upload_siembras']}"

            )

            if uploaded_file is not None:

                if st.button("Procesar Siembras", width="stretch", key="btn_proc_siembras"):

                    with st.spinner("Procesando archivo de siembras..."):

                        file_path = "Siembra Actual (16).xlsx"

                        with open(file_path, "wb") as f:

                            f.write(uploaded_file.getbuffer())

                        

                        with open("last_dataset_name.txt", "w") as f:

                            f.write(uploaded_file.name)

                        

                        from scripts.ingestar_siembra import ingestar_siembra_actual

                        ingestar_siembra_actual()

                        

                        st.session_state["ver_upload_siembras"] += 1

                        st.session_state["flash_siembras_success"] = f"✅ Datos de siembra actualizados desde '{uploaded_file.name}'."

                        st.toast("✅ Archivo de siembras actualizado exitosamente.")

                        st.rerun()

                    

    with col_ins3:

        with st.container(border=True):

            st.markdown("#### 📦 Pedido Consolidado")

            st.caption("Compromisos de entrega y horizonte MVA.")

            if os.path.exists("PedidoConsolidado_master.xlsx"):

                st.info("✅ **Pedido Vigente:** Disponible en plataforma.\n\n*Horizonte comercial S&OP*")

            else:

                st.warning("⚠️ No hay Pedido Consolidado cargado.")

                

            if "ver_upload_pedido" not in st.session_state:

                st.session_state["ver_upload_pedido"] = 0

            if "flash_pedido_success" in st.session_state:

                st.success(st.session_state.pop("flash_pedido_success"))

                

            uploaded_pedido = st.file_uploader(

                "Cargar nuevo Pedido Consolidado", 

                type=["xlsx", "xls"], 

                key=f"upload_pedido_{st.session_state['ver_upload_pedido']}"

            )

            if uploaded_pedido is not None:

                st.caption("ℹ️ **Lógica S&OP:** Actualiza semanas y conserva histórico.")

                if st.button("Procesar y Sincronizar Pedido", type="primary", width="stretch", key="btn_proc_pedido"):

                    with st.spinner("Sincronizando pedido y preservando semanas históricas..."):

                        from app.services.mva_service import sincronizar_pedido_consolidado_master

                        res_sync = sincronizar_pedido_consolidado_master(uploaded_pedido)

                        if res_sync.get("status") == "success":

                            n_act = len(res_sync['semanas_actualizadas'])

                            n_hist = len(res_sync['semanas_historicas_preservadas'])

                            s_min = res_sync['semana_min']

                            s_max = res_sync['semana_max']

                            st.session_state["ver_upload_pedido"] += 1

                            st.session_state["flash_pedido_success"] = f"✅ Pedido sincronizado: {n_act} semanas actualizadas y {n_hist} semanas históricas conservadas (Total: {s_min} a {s_max}, {res_sync['total_variedades']} variedades)."

                            st.toast("✅ Pedido Consolidado sincronizado con éxito.")

                            st.rerun()

                        else:

                            st.error(f"Error procesando pedido: {res_sync.get('message', 'Desconocido')}")

                

    st.divider()



elif modulo == "Curvas e Índices (Campo)":

    render_curvas_module(db)



elif modulo == "Calibración de Curvas":

    render_accuracy_module(db)



elif modulo == "ForeCast y Exportación":
    
    # Selector de horizonte (13 Semanas PER13, 52 Semanas PER52, Personalizado)
    from datetime import date
    from app.services.forecast_service import isocalendar_to_string
    from app.services.enraizamiento_service import sumar_semanas_iso

    semana_actual = isocalendar_to_string(date.today())
    semanas_disponibles = [sumar_semanas_iso(semana_actual, i) for i in range(53)]

    col_hzt1, col_hzt2 = st.columns([2, 2])
    with col_hzt1:
        vista = st.radio(
            "Selecciona el horizonte de proyección:", 
            ["13 Semanas (PER13)", "52 Semanas (PER52)", "Personalizado"], 
            index=0,
            horizontal=True,
            key="fc_vista_horizonte"
        )
    
    sem_desde = semana_actual
    if "13" in vista or "PER13" in vista:
        sem_hasta = sumar_semanas_iso(semana_actual, 13)
        lim_hz = 14
    elif "52" in vista or "PER52" in vista:
        sem_hasta = sumar_semanas_iso(semana_actual, 51)
        lim_hz = 52
    else: # Personalizado
        with col_hzt2:
            col_p1, col_p2 = st.columns(2)
            sem_desde = col_p1.selectbox("Semana Desde:", semanas_disponibles, index=0)
            opciones_hasta = [s for s in semanas_disponibles if s >= sem_desde]
            idx_default = min(13, len(opciones_hasta) - 1)
            sem_hasta = col_p2.selectbox("Semana Hasta:", opciones_hasta, index=idx_default)
        lim_hz = 52
    
    # Alertas y Contexto S&OP por horizonte
    alertas_sop = obtener_alertas_sop()
    if "13" in vista or "PER13" in vista:
        a13 = alertas_sop.get("regla_13wk", {})
        st.caption(f"{a13.get('icono', '⏰')} **Regla 1 S&OP (13 Semanas / Webflowers PER13):** Cierre los Miércoles antes de las 12:00 m. {a13.get('mensaje', '')}")
    elif "52" in vista or "PER52" in vista:
        a52 = alertas_sop.get("regla_52wk", {})
        st.caption(f"{a52.get('icono', '📅')} **Regla 2 S&OP (52 Semanas / Anual PER52):** Carga los 4º Jueves de cada mes. {a52.get('mensaje', '')}")
    else:
        st.caption(f"🎯 **Horizonte Personalizado:** Visualizando rango operativo desde la semana **{sem_desde}** hasta la semana **{sem_hasta}**.")
    
    # Cargar parámetros biológicos calculados automáticamente
    from app.services.calibracion_service import cargar_parametros_calibrados
    params_cal = cargar_parametros_calibrados()
    params_flor_fc = params_cal.get('por_flor') if params_cal.get('fecha_calibracion') else None
    alpha_fc = None
    ciclos_fc = None
    
    with st.spinner(f"Construyendo balance S&OP en 3 tramos ({vista})..."):
        from app.services.mva_service import generar_forecast_3_tramos, llenar_plantilla_52_semanas
        from app.services.forecast_service import generar_forecast_13wk
        
        # 1. Base Vivo en Suelo (para exportación y consistencia)
        df_forecast_vivo = generar_forecast_13wk(db, alpha=alpha_fc, num_ciclos=ciclos_fc, params_por_flor=params_flor_fc)

        # 2. Generar ForeCast Oficial en 3 Tramos
        df_forecast = generar_forecast_3_tramos(
            db, 
            alpha=alpha_fc, 
            num_ciclos=ciclos_fc, 
            params_por_flor=params_flor_fc, 
            horizonte_semanas=lim_hz
        )

        st.info("💡 **Arquitectura S&OP Oficial en 3 Tramos:** "
                "🟢 **Tramo 1 (Semanas 1 a 10):** Inventario Vivo en Suelo (plano actual). | "
                "🟠 **Tramo 2 (Semanas 11 a 13):** Proyección del Enraizamiento Ejecutado en Plataforma. | "
                "🟣 **Tramo 3 (Semana 14+):** Proyección del Enraizamiento del Material Vegetal Planificado (MVA).")
        
    if df_forecast.empty:
        st.warning("No hay datos suficientes para generar el forecast.")
    else:
        semanas_cols = sorted([col for col in df_forecast.columns if str(col).startswith('202')])
        
        if "13" in vista or "PER13" in vista:
            semanas_futuras = [s for s in semanas_cols if s >= semana_actual][:14]
        elif "52" in vista or "PER52" in vista:
            semanas_futuras = [s for s in semanas_cols if s >= semana_actual][:52]
        else: # Personalizado
            semanas_futuras = [s for s in semanas_cols if sem_desde <= s <= sem_hasta]
            
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

        # 2 PESTAÑAS ESTRUCTURALES ENFOCADAS
        tab_unificada, tab_gap = st.tabs([
            "📈 Balance S&OP, Matriz y Exportación Oficial",
            "🔍 Diagnóstico de Brechas (Flor / Variedad)"
        ])

        # =====================================================================
        # PESTAÑA 1: BALANCE S&OP, MATRIZ Y EXPORTACIÓN OFICIAL (UNIFICADA)
        # =====================================================================
        with tab_unificada:
            if semanas_futuras:
                # Barra de Filtros Visuales SAP Fiori (Analytical List Page - ALP)
                alp_cfg = render_fiori_visual_filter_bar(
                    df_forecast=df_forecast,
                    semanas_futuras=semanas_futuras,
                    plan_series_cap=plan_series_cap,
                    module_key="fc_alp"
                )
                df_fc_active_view = (
                    df_forecast[df_forecast['Flor'].isin(alp_cfg['flores'])].copy()
                    if alp_cfg.get('flores') else df_forecast
                )
                scen_mult = st.session_state.get("fiori_scenario_factor", 1.0)
                fc_agrupado = df_fc_active_view[semanas_futuras].sum() * scen_mult
                tot_fc = fc_agrupado.sum()
                tot_plan = plan_series_cap.sum()
                brecha_tot = tot_fc - tot_plan
                cumpl_global = (tot_fc / tot_plan * 100) if tot_plan > 0 else 100.0

                # Tarjetas KPI S&OP
                col_k1, col_k2, col_k3, col_k4 = st.columns(4)
                col_k1.metric("Oferta ForeCast Biológico", f"{tot_fc:,.0f}", f"{len(semanas_futuras)} semanas evaluadas")
                col_k2.metric("Demanda Plan Aprobado", f"{tot_plan:,.0f}", "Meta Comercial")
                col_k3.metric("Brecha / Gap Neto S&OP", f"{brecha_tot:+,.0f}", "Superávit (+)" if brecha_tot >= 0 else "Déficit (-)", delta_color="normal")
                col_k4.metric("Cumplimiento Global Estimado", f"{cumpl_global:.1f}%", "Alineación Plan vs Oferta")

                st.markdown("")

                # Gráfica de Balance S&OP en 3 Tramos continuos sin duplicaciones
                fig_fc = go.Figure()
                y_fc = [fc_agrupado.get(s, 0) for s in semanas_futuras]
                num_sems = len(semanas_futuras)

                # Segmentación de tramos
                # Tramo 1: Semanas 0 a 9 (S1 a S10)
                lim1 = min(10, num_sems)
                sems_t1 = semanas_futuras[:lim1]
                y_t1 = y_fc[:lim1]

                fig_fc.add_trace(go.Scatter(
                    x=sems_t1,
                    y=y_t1,
                    mode='lines+markers',
                    name="1. Inventario Vivo en Suelo (S1 a S10)",
                    line=dict(color='#059669', width=3.2),
                    marker=dict(size=7, symbol='circle'),
                    hovertemplate="<b>Semana %{x}</b><br>🟢 Inventario Vivo (Suelo): %{y:,.0f} tallos<extra></extra>"
                ))

                # Tramo 2: Semanas 10 a 12 (S11 a S13)
                if num_sems > 10:
                    lim2 = min(13, num_sems)
                    # Conectar desde el final del tramo 1 (índice 9) para continuidad visual
                    sems_t2 = semanas_futuras[9:lim2]
                    y_t2 = y_fc[9:lim2]
                    fig_fc.add_trace(go.Scatter(
                        x=sems_t2,
                        y=y_t2,
                        mode='lines+markers',
                        name="2. Enraizamiento Ejecutado en Plataforma (S11 a S13)",
                        line=dict(color='#D97706', width=3.2),
                        marker=dict(size=7, symbol='square'),
                        hovertemplate="<b>Semana %{x}</b><br>🟠 Enraizamiento Ejecutado: %{y:,.0f} tallos<extra></extra>"
                    ))

                # Tramo 3: Semana 13 en adelante (S14+)
                if num_sems > 13:
                    # Conectar desde el final del tramo 2 (índice 12) para continuidad visual
                    sems_t3 = semanas_futuras[12:]
                    y_t3 = y_fc[12:]
                    fig_fc.add_trace(go.Scatter(
                        x=sems_t3,
                        y=y_t3,
                        mode='lines+markers',
                        name="3. Material Vegetal Planificado Pedido (S14+)",
                        line=dict(color='#7C3AED', width=3.2, dash='solid'),
                        marker=dict(size=7, symbol='diamond'),
                        hovertemplate="<b>Semana %{x}</b><br>🟣 Material Vegetal Pedido (MVA): %{y:,.0f} tallos<extra></extra>"
                    ))

                # Trazo 4: Demanda Comercial Aprobada (Azul SAP Fiori #0070F2 dash)
                fig_fc.add_trace(go.Scatter(
                    x=semanas_futuras,
                    y=plan_series_cap,
                    mode='lines+markers',
                    name="Demanda Comercial (Plan Aprobado)",
                    line=dict(color='#0070F2', width=2.8, dash='dash'),
                    marker=dict(size=6, symbol='triangle-up'),
                    hovertemplate="<b>Semana %{x}</b><br>🟦 Demanda Comercial Aprobada: %{y:,.0f} tallos<extra></extra>"
                ))

                fig_fc.update_layout(
                    title=f"Balance S&OP: Oferta de Cosecha vs. Demanda Comercial ({vista})",
                    hovermode="x unified",
                    height=460,
                    margin=dict(l=20, r=20, t=50, b=20),
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1,
                        bgcolor="rgba(255,255,255,0.85)"
                    )
                )
                fig_fc = estilizar_figura_plotly(fig_fc)
                # Escala de semanas corregida como categórica exacta (evita miles '202k' o saltos de año)
                fig_fc.update_xaxes(
                    type='category', 
                    categoryorder='array', 
                    categoryarray=semanas_futuras,
                    title="Semana Operativa",
                    tickangle=-45
                )
                fig_fc.update_yaxes(title="Volumen de Tallos Proyectados")
                alp_mode = alp_cfg.get("alp_mode", "📊 Híbrida")
                if alp_mode in ("📊 Híbrida", "📈 Gráfica"):
                    st.plotly_chart(fig_fc, width='stretch')

                # Matriz de Balance Semanal Directa (Sin Transposición)
                if alp_mode in ("📊 Híbrida", "📋 Tabla"):
                    st.markdown("#### 📋 Matriz de Balance Semanal")
                    df_balance_sem = pd.DataFrame({
                        "Semana": semanas_futuras,
                        "Oferta Biológica (ForeCast)": [fc_agrupado.get(s, 0) for s in semanas_futuras],
                        "Demanda Comercial (Plan)": [plan_series_cap.get(s, 0) for s in semanas_futuras]
                    })
                    df_balance_sem["Brecha / Gap (Tallos)"] = df_balance_sem["Oferta Biológica (ForeCast)"] - df_balance_sem["Demanda Comercial (Plan)"]
                    df_balance_sem["% Cumplimiento"] = df_balance_sem.apply(
                        lambda r: (r["Oferta Biológica (ForeCast)"] / r["Demanda Comercial (Plan)"] * 100) if r["Demanda Comercial (Plan)"] > 0 else (100.0 if r["Oferta Biológica (ForeCast)"] > 0 else 0.0),
                        axis=1
                    )
                    
                    def color_brecha(val):
                        if val < -1000:
                            return 'color: #D32F2F; font-weight: bold;'
                        elif val > 1000:
                            return 'color: #1976D2; font-weight: bold;'
                        else:
                            return 'color: #388E3C; font-weight: bold;'
                    
                    st.dataframe(
                        df_balance_sem.style.format({
                            "Oferta Biológica (ForeCast)": "{:,.0f}",
                            "Demanda Comercial (Plan)": "{:,.0f}",
                            "Brecha / Gap (Tallos)": "{:+,.0f}",
                            "% Cumplimiento": "{:.1f}%"
                        }).map(color_brecha, subset=['Brecha / Gap (Tallos)']),
                        width='stretch',
                        hide_index=True
                    )

                    csv_bal = df_balance_sem.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="⬇️ Descargar Balance Semanal (CSV)",
                        data=csv_bal,
                        file_name=f"Balance_Semanal_SOP_{vista.replace(' ', '_')}.csv",
                        mime="text/csv",
                        key="dl_balance_semanal_csv"
                    )

                # Componente Específico S&OP: SAP IBP Planning Grid (Pivotante & Celdas Editables con Disgregación)
                st.markdown("---")
                render_fiori_ibp_planning_grid(
                    df_forecast=df_fc_active_view,
                    semanas_futuras=semanas_futuras,
                    df_plan_app=df_plan_app,
                    module_key="fc_main_ibp"
                )

                # Matriz de Producción Semanal Integrada
                st.markdown("---")
                st.subheader("📋 Matriz de Producción")
                
                df_fc_matrix = df_forecast.copy()
                df_fc_matrix['TOTAL'] = df_fc_matrix[semanas_futuras].sum(axis=1) if semanas_futuras else 0
                df_fc_matrix = df_fc_matrix[df_fc_matrix['TOTAL'] > 0]
                
                st.markdown("##### Resumen Total por Flor")
                if semanas_futuras:
                    resumen_flor = df_fc_matrix.groupby('Flor')[semanas_futuras + ['TOTAL']].sum()
                    total_row_flor = pd.DataFrame(resumen_flor.sum()).T
                    total_row_flor.index = ['TOTAL GENERAL']
                    resumen_flor = pd.concat([resumen_flor, total_row_flor])
                    st.dataframe(resumen_flor.style.format("{:,.0f}"), width='stretch')

                st.markdown("##### Matriz ForeCast Detallada por Variedad")
                if semanas_futuras:
                    cols_num = semanas_futuras + ['TOTAL']
                    total_row = pd.DataFrame(df_fc_matrix[cols_num].sum()).T
                    for col in ['Sede', 'Flor', 'Color', 'Variedad']:
                        if col in df_fc_matrix.columns:
                            total_row[col] = 'TOTAL'
                    
                    df_fc_display = pd.concat([df_fc_matrix, total_row], ignore_index=True)
                    cols_order = [c for c in ['Flor', 'Color', 'Variedad'] if c in df_fc_display.columns] + cols_num
                    
                    format_dict = {col: "{:,.0f}" for col in cols_num}
                    st.dataframe(
                        df_fc_display[cols_order].style.format(format_dict),
                        width='stretch',
                        hide_index=True
                    )

                    csv_matriz = df_fc_display[cols_order].to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="⬇️ Descargar Matriz ForeCast Completa (CSV)",
                        data=csv_matriz,
                        file_name=f"Matriz_ForeCast_{vista.replace(' ', '_')}.csv",
                        mime="text/csv",
                        key="dl_matriz_fc_csv"
                    )

                # Exportación a Plataformas Integrada directamente al final de la página
                st.markdown("---")
                st.subheader("📤 Exportación a Plataformas")
                st.markdown("Carga y diligenciamiento oficial de plantillas para Webflowers (PER13) y Proyecciones Anuales (PER52).")

                sub_exp1, sub_exp2 = st.tabs([
                    "Exportación Webflowers (13 Semanas - PER13)", 
                    "Exportación Anual (52 Semanas - PER52)"
                ])
                
                with sub_exp1:
                    st.markdown("##### Exportación Webflowers (13 Semanas - PER13)")
                    st.info("💡 **Regla S&OP Webflowers (13 Semanas / PER13):** Proyección conformada exactamente por **9 semanas de Inventario Vivo en suelo** + **4 semanas de Plan Maestro Factible**, manteniendo la rigurosidad de la capacidad instalada y sin inflar cifras.")
                    
                    if "ver_uploader_wf_13" not in st.session_state:
                        st.session_state["ver_uploader_wf_13"] = 0
                    if "res_wf13_data" not in st.session_state:
                        st.session_state["res_wf13_data"] = None

                    col_up1, col_up2 = st.columns([1.5, 1])
                    with col_up1:
                        uploaded_templates = st.file_uploader(
                            "📥 Subir Plantillas Webflowers Vacías (Excel)", 
                            type=["xlsx", "xls"], 
                            accept_multiple_files=True, 
                            key=f"uploader_wf_13_{st.session_state['ver_uploader_wf_13']}"
                        )
                    with col_up2:
                        st.caption("Carga los archivos base descargados de Webflowers. El sistema conservará la estructura y formatos originales inyectando los valores calculados.")

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
                                        
                                from scripts.export_plataforma import procesar_plantillas_plataforma
                                
                                templates_dict = {f.name: f.getvalue() for f in uploaded_templates}
                                resultados = procesar_plantillas_plataforma(templates_dict, df_forecast_vivo, df_plan)
                                
                                st.session_state["res_wf13_data"] = resultados
                                st.session_state["ver_uploader_wf_13"] += 1
                                st.rerun()

                    if st.session_state.get("res_wf13_data"):
                        resultados = st.session_state["res_wf13_data"]
                        st.success(f"✅ Se procesaron {len(resultados)} plantillas exitosamente.")
                        
                        c_btn_dl, c_btn_rst = st.columns([3, 1])
                        with c_btn_rst:
                            if st.button("🔄 Nueva Plantilla / Limpiar", key="btn_reset_wf13"):
                                st.session_state["res_wf13_data"] = None
                                st.rerun()

                        for filename, filebytes in resultados.items():
                            st.download_button(
                                label=f"⬇️ Descargar {filename} (Diligenciada)",
                                data=filebytes,
                                file_name=filename,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                type="primary",
                                key=f"dl_13_{filename}"
                            )

                with sub_exp2:
                    st.markdown("##### Exportación Anual (52 Semanas - PER52)")
                    st.caption("📌 **Cadena Agronómica S&OP:** Recepción en Frío (Semana S-4) ➔ Enclavado en Bancos (Semana S-3, 21 días) ➔ Trasplante a Suelo (Semana S).")
                    
                    if "ver_uploader_wf_52" not in st.session_state:
                        st.session_state["ver_uploader_wf_52"] = 0
                    if "res_wf52_data" not in st.session_state:
                        st.session_state["res_wf52_data"] = None
                    if "res_wf52_mrp" not in st.session_state:
                        st.session_state["res_wf52_mrp"] = None

                    uploaded_templates_52 = st.file_uploader(
                        "📋 Cargar Plantilla(s) Vacía(s) 52 Semanas (Excel)", 
                        type=["xlsx", "xls"], 
                        accept_multiple_files=True, 
                        key=f"uploader_wf_52_{st.session_state['ver_uploader_wf_52']}"
                    )
                    
                    if uploaded_templates_52:
                        if st.button("Procesar y Llenar Plantilla(s) 52 Semanas", type="primary", key="btn_procesar_wf52"):
                            with st.spinner("Procesando archivos para proyección 52 semanas..."):
                                resultados_52 = {}
                                errores_52 = {}
                                for f in uploaded_templates_52:
                                    try:
                                        filled_template_bytes = llenar_plantilla_52_semanas(f.getvalue(), df_forecast)
                                        resultados_52[f.name] = filled_template_bytes
                                    except Exception as e:
                                        errores_52[f.name] = str(e)
                            
                                st.session_state["res_wf52_data"] = resultados_52
                                st.session_state["ver_uploader_wf_52"] += 1
                                st.rerun()

                    if st.session_state.get("res_wf52_data"):
                        resultados_52 = st.session_state["res_wf52_data"]
                        st.success(f"✅ Se procesaron {len(resultados_52)} plantillas anuales exitosamente.")
                        
                        c_btn_dl52, c_btn_rst52 = st.columns([3, 1])
                        with c_btn_rst52:
                            if st.button("🔄 Nueva Plantilla / Limpiar", key="btn_reset_wf52"):
                                st.session_state["res_wf52_data"] = None
                                st.rerun()

                        for fname, fbytes in resultados_52.items():
                            st.download_button(
                                label=f"⬇️ Descargar {fname} (Diligenciada)",
                                data=fbytes,
                                file_name=fname,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                type="primary",
                                key=f"dl_52_{fname}"
                            )

        # =====================================================================
        # PESTAÑA 2: DIAGNÓSTICO DE BRECHAS (FLOR / VARIADAD)
        # =====================================================================
        with tab_gap:
            st.subheader("🔍 Diagnóstico Detallado de Brechas por Flor, Color y Variedad")
            st.markdown("Auditoría jerárquica (de lo macro a lo micro) para identificar desviaciones y balance comercial por flor, color y variedad.")

            # Filtros combinados: Semana, Flor y Color
            col_g1, col_g2, col_g3 = st.columns([1.5, 1.2, 1.2])
            with col_g1:
                opc_sem_gap = ["Consolidado Horizonte Completo"] + semanas_futuras
                sel_sem_gap = st.selectbox("Semana Operativa:", opc_sem_gap, key="sel_sem_gap")
            
            flores_disp_gap = sorted(list(df_forecast['Flor'].dropna().unique()))
            with col_g2:
                sel_flores = st.multiselect("Filtrar por Flor (Macro):", flores_disp_gap, default=[], placeholder="Todas las flores", key="sel_flores_gap_multi")
            
            if sel_flores:
                df_for_colores = df_forecast[df_forecast['Flor'].isin(sel_flores)]
            else:
                df_for_colores = df_forecast
            colores_disp_gap = sorted(list(df_for_colores['Color'].dropna().unique()))
            
            with col_g3:
                sel_colores = st.multiselect("Filtrar por Color:", colores_disp_gap, default=[], placeholder="Todos los colores", key="sel_colores_gap_multi")

            # Construir tabla de brechas base por SKU
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

            df_gap_base = pd.merge(df_fc_sku, df_plan_sku, on=['Flor', 'Color', 'Variedad'], how='outer').fillna(0.0)

            # Aplicar filtros seleccionados
            if sel_flores:
                df_gap_base = df_gap_base[df_gap_base['Flor'].isin(sel_flores)]
            if sel_colores:
                df_gap_base = df_gap_base[df_gap_base['Color'].isin(sel_colores)]

            df_gap_base = df_gap_base[(df_gap_base['ForeCast Biológico (Oferta)'] > 0) | (df_gap_base['Demanda Comercial (Plan)'] > 0)].copy()

            # Granularidad adaptativa de lo macro a lo micro
            c_gran1, c_gran2 = st.columns([2.2, 1])
            with c_gran1:
                nivel_gran = st.radio(
                    "Nivel de Granularidad (Macro ➔ Micro):",
                    ["Por Flor (Macro)", "Por Flor y Color (Intermedio)", "Por Variedad / SKU (Micro)"],
                    index=0 if (not sel_flores and not sel_colores) else (1 if not sel_colores else 2),
                    horizontal=True,
                    key="radio_gran_gap"
                )

            if nivel_gran == "Por Flor (Macro)":
                df_gap_sku = df_gap_base.groupby('Flor')[['ForeCast Biológico (Oferta)', 'Demanda Comercial (Plan)']].sum().reset_index()
            elif nivel_gran == "Por Flor y Color (Intermedio)":
                df_gap_sku = df_gap_base.groupby(['Flor', 'Color'])[['ForeCast Biológico (Oferta)', 'Demanda Comercial (Plan)']].sum().reset_index()
            else:
                df_gap_sku = df_gap_base.groupby(['Flor', 'Color', 'Variedad'])[['ForeCast Biológico (Oferta)', 'Demanda Comercial (Plan)']].sum().reset_index()

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
            sort_cols = [c for c in ['Brecha / Gap (Tallos)', 'Flor', 'Color', 'Variedad'] if c in df_gap_sku.columns]
            df_gap_sku = df_gap_sku.sort_values(by=sort_cols, ascending=[True] + [True]*(len(sort_cols)-1))

            tot_skus = len(df_gap_sku)
            skus_def = (df_gap_sku['Brecha / Gap (Tallos)'] < -500).sum()
            skus_bal = ((df_gap_sku['Brecha / Gap (Tallos)'] >= -500) & (df_gap_sku['Brecha / Gap (Tallos)'] <= 500)).sum()
            skus_sup = (df_gap_sku['Brecha / Gap (Tallos)'] > 500).sum()

            cd1, cd2, cd3, cd4 = st.columns(4)
            cd1.metric("Segmentos Evaluados", f"{tot_skus:,}", f"{nivel_gran.split(' ')[1]}")
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
                    file_name=f"Diagnostico_Brechas_{sel_sem_gap.replace(' ', '_')}.csv",
                    mime="text/csv",
                    key="dl_gap_sku_csv"
                )


elif modulo == "Programación Diaria y Temporadas":

    

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

            st.markdown(f"""

            <div style="background: #FFFFFF; border: 1px solid #CBD5E1; border-left: 4px solid #1D4ED8; border-radius: 8px; padding: 12px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-top: 4px;">

                <div style="font-weight: 600; color: #1E293B; margin-bottom: 4px; font-size: 0.88rem;">⚖️ Parámetros de Capacidad Laboral</div>

                <div style="color: #475569; font-size: 0.82rem; line-height: 1.45;">

                    • <b>Jornada Estándar:</b> {TOTAL_HORAS_SEMANA_ESTANDAR:.1f}h efectivas/semana (con deducción reglamentaria de 30 min almuerzo).<br/>

                    • <b>Temporadas Pico (SV/Madres):</b> Domingos activos (+5.0h = {TOTAL_HORAS_SEMANA_TEMPORADA:.1f}h efectivas).

                </div>

            </div>

            """, unsafe_allow_html=True)

            

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

        st.markdown("Comparativo de la **Demanda Comercial Aprobada (Plan Maestro)** y volumen biológico proyectado para cada temporada.")

        

        with st.spinner("Analizando comportamiento de temporadas y consolidando Plan Aprobado..."):

            df_forecast_vivo = generar_forecast_13wk(db)

            from app.services.mva_service import generar_plan_mva, proyectar_cosecha_desde_mva, combinar_proyecciones_52_semanas

            file_path = "PedidoConsolidado_master.xlsx"

            if os.path.exists(file_path):

                df_mrp = generar_plan_mva(file_path, week_is="Pedido")

                df_proyeccion_mva = proyectar_cosecha_desde_mva(df_mrp, db)

                df_52 = combinar_proyecciones_52_semanas(df_forecast_vivo, df_proyeccion_mva)

            else:

                df_52 = df_forecast_vivo



            # Cargar Plan Aprobado (Demanda Comercial y Capacidad Aprobada)

            df_plan_temp = pd.DataFrame()

            plan_file = "Plan_Aprobado.csv"

            col_plan = None

            if os.path.exists(plan_file):

                try:

                    df_plan_temp = pd.read_csv(plan_file)

                    df_plan_temp['Semana_Clean'] = pd.to_numeric(

                        df_plan_temp['Semana'].astype(str).str.split('.').str[0], errors='coerce'

                    ).fillna(0).astype(int)

                    if 'Tallos Pedidos (Plan)' in df_plan_temp.columns:

                        col_plan = 'Tallos Pedidos (Plan)'

                    elif 'Tallos a Producir (Capacidad)' in df_plan_temp.columns:

                        col_plan = 'Tallos a Producir (Capacidad)'

                    elif 'Suma de Tallos' in df_plan_temp.columns:

                        col_plan = 'Suma de Tallos'

                except Exception:

                    df_plan_temp = pd.DataFrame()

                

            results = []

            cols = [c for c in df_52.columns if str(c).startswith('202')]

            cols_clean = [int(str(c).split('.')[0].strip()) for c in cols if str(c).split('.')[0].strip().isdigit()]

            df_plan_horizon = df_plan_temp[df_plan_temp['Semana_Clean'].isin(cols_clean)].copy() if not df_plan_temp.empty else pd.DataFrame()

            used_cols = set()

            used_plan_sems = set()

            

            for _, s in df_seasons_edited.iterrows():

                name = str(s.get("Temporada", ""))

                start = str(int(s["Semana Inicio"])) if pd.notna(s.get("Semana Inicio")) else ""

                end = str(int(s["Semana Fin"])) if pd.notna(s.get("Semana Fin")) else ""

                try:

                    ini = int(float(s.get("Semana Inicio", 0)))

                    fin = int(float(s.get("Semana Fin", 0)))

                except Exception:

                    ini = 0

                    fin = 0

                

                w_ini = ini % 100 if ini > 100 else ini

                w_fin = fin % 100 if fin > 100 else fin

                

                # Semanas proyectadas

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

                    except Exception:

                        pass

                

                used_cols.update(valid_cols)

                total_proj = float(df_52[valid_cols].sum().sum()) if valid_cols else 0.0



                # Volumen del Plan Aprobado para esta temporada (en las 52 semanas del horizonte)

                vol_plan = 0.0

                if not df_plan_horizon.empty and col_plan:

                    if ini > 100 and fin > 100:

                        sub_plan = df_plan_horizon[(df_plan_horizon['Semana_Clean'] >= ini) & (df_plan_horizon['Semana_Clean'] <= fin)]

                    else:

                        sub_plan = df_plan_horizon[(df_plan_horizon['Semana_Clean'] % 100 >= w_ini) & (df_plan_horizon['Semana_Clean'] % 100 <= w_fin)]

                    vol_plan = float(sub_plan[col_plan].sum())

                    used_plan_sems.update(sub_plan['Semana_Clean'].unique())



                cob_pct = (total_proj / vol_plan * 100.0) if vol_plan > 0 else 0.0

                    

                results.append({

                    "Temporada": name, 

                    "Rango": f"{start} - {end}", 

                    "Semanas Activas": len(valid_cols), 

                    "Tallos Plan": vol_plan,

                    "Tallos Proyectados": total_proj,

                    "Cobertura_%": round(cob_pct, 1),

                    "_sort": start if start else "999999"

                })

                

            # Every Day con las semanas restantes dentro del horizonte de 52 semanas

            valid_cols_ed = [c for c in cols if c not in used_cols]

            total_proj_ed = float(df_52[valid_cols_ed].sum().sum()) if valid_cols_ed else 0.0

            vol_plan_ed = 0.0

            if not df_plan_horizon.empty and col_plan:

                sub_plan_ed = df_plan_horizon[~df_plan_horizon['Semana_Clean'].isin(used_plan_sems)]

                vol_plan_ed = float(sub_plan_ed[col_plan].sum())

            cob_pct_ed = (total_proj_ed / vol_plan_ed * 100.0) if vol_plan_ed > 0 else 0.0

                

            results.append({

                "Temporada": "Every Day", 

                "Rango": "Semanas restantes", 

                "Semanas Activas": len(valid_cols_ed), 

                "Tallos Plan": vol_plan_ed,

                "Tallos Proyectados": total_proj_ed,

                "Cobertura_%": round(cob_pct_ed, 1),

                "_sort": "999999" # Every Day al final

            })

                

            df_res_seasons = pd.DataFrame(results)

            if not df_res_seasons.empty:

                df_res_seasons = df_res_seasons.sort_values(by="_sort").drop(columns=["_sort"]).reset_index(drop=True)

                

                # Crear dataframe para visualización con fila de totales

                df_res_seasons_display = df_res_seasons.copy()

                total_semanas = int(df_res_seasons_display["Semanas Activas"].sum())

                total_plan = float(df_res_seasons_display["Tallos Plan"].sum())

                total_proj = float(df_res_seasons_display["Tallos Proyectados"].sum())

                total_cob = (total_proj / total_plan * 100.0) if total_plan > 0 else 0.0

                

                total_row = pd.DataFrame([{

                    "Temporada": "TOTAL",

                    "Rango": "-",

                    "Semanas Activas": total_semanas,

                    "Tallos Plan": total_plan,

                    "Tallos Proyectados": total_proj,

                    "Cobertura_%": round(total_cob, 1)

                }])

                df_res_seasons_display = pd.concat([df_res_seasons_display, total_row], ignore_index=True)

            else:

                df_res_seasons_display = df_res_seasons.copy()

            

            col_chart1, col_chart2 = st.columns([1.1, 1.9])

            with col_chart1:

                st.dataframe(

                    df_res_seasons_display.style.format({

                        "Tallos Plan": "{:,.0f}",

                        "Tallos Proyectados": "{:,.0f}",

                        "Cobertura_%": "{:.1f}%"

                    }), 

                    width='stretch'

                )

            with col_chart2:

                if not df_res_seasons.empty and df_res_seasons["Tallos Plan"].sum() > 0:

                    import altair as alt

                    chart = alt.Chart(df_res_seasons).mark_bar(

                        color='#0070F2', 

                        cornerRadiusTopLeft=4, 

                        cornerRadiusTopRight=4

                    ).encode(

                        x=alt.X('Temporada:N', sort=list(df_res_seasons['Temporada']), title='Temporada', axis=alt.Axis(labelAngle=-45)),

                        y=alt.Y('Tallos Plan:Q', title='Tallos Plan Aprobado'),

                        tooltip=[

                            alt.Tooltip('Temporada:N', title='Temporada'),

                            alt.Tooltip('Tallos Plan:Q', title='Plan Aprobado', format=',.0f'),

                            alt.Tooltip('Tallos Proyectados:Q', title='Tallos Proyectados', format=',.0f'),

                            alt.Tooltip('Cobertura_%:Q', title='Cobertura (%)', format='.1f')

                        ]

                    ).properties(height=350, title="Demanda Comercial Aprobada por Temporada (Plan Maestro)")

                    st.altair_chart(chart, width='stretch')

                elif not df_res_seasons.empty and df_res_seasons["Tallos Proyectados"].sum() > 0:

                    import altair as alt

                    chart = alt.Chart(df_res_seasons).mark_bar(

                        color='#059669', 

                        cornerRadiusTopLeft=4, 

                        cornerRadiusTopRight=4

                    ).encode(

                        x=alt.X('Temporada:N', sort=list(df_res_seasons['Temporada']), title='Temporada', axis=alt.Axis(labelAngle=-45)),

                        y=alt.Y('Tallos Proyectados:Q', title='Tallos Proyectados'),

                        tooltip=['Temporada', 'Tallos Proyectados']

                    ).properties(height=350, title="Tallos Proyectados por Temporada")

                    st.altair_chart(chart, width='stretch')

                else:

                    st.info("No se dispone de datos de plan o proyecciones para las temporadas configuradas.")



            if not df_plan_temp.empty and len(df_plan_temp['Semana_Clean'].unique()) > len(cols_clean):

                tot_maestro = float(df_plan_temp[col_plan].sum()) if col_plan else 0.0

                st.caption(

                    f"ℹ️ **Horizonte de Evaluación:** Comparativo calculado sobre las **52 semanas operativas vigentes** (de S{cols[0]} a S{cols[-1]}: {total_plan:,.0f} tallos Plan vs {total_proj:,.0f} tallos Proyectados, cobertura {total_cob:.1f}%). "

                    f"El archivo maestro completo (`Plan_Aprobado.csv`) contiene {df_plan_temp['Semana_Clean'].nunique()} semanas ({tot_maestro:,.0f} tallos acumulados), "

                    f"incluyendo semanas históricas pasadas previas a S{cols[0]} y semanas posteriores al horizonte rodante de 52 semanas."

                )



elif modulo == "Plan de Producción (MVA)":

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

            "y calcula automáticamente hacia atrás las fechas exactas de siembra y enraizamiento."

        )

        

        if "ver_uploader_plan" not in st.session_state:

            st.session_state["ver_uploader_plan"] = 0

        if "flash_plan_save_success" in st.session_state:

            st.success(st.session_state.pop("flash_plan_save_success"))



        plan_file = st.file_uploader("Subir Archivo de Plan Semanal (Excel)", type=["xlsx", "xls"], key=f"uploader_plan_produccion_{st.session_state['ver_uploader_plan']}")

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

                    with st.spinner("Procesando archivo y calculando fechas de siembra y vivero..."):

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

                                st.session_state["ver_uploader_plan"] = st.session_state.get("ver_uploader_plan", 0) + 1

                                st.session_state["flash_plan_save_success"] = f"✅ ¡Plan consolidado y guardado permanentemente! Se actualizaron {num_nuevas} semanas ({s_min} a {s_max})."

                                st.toast("✅ Plan Maestro consolidado y guardado permanentemente.")

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
    with st.expander("🕸️ Mapa del Recorrido del Cultivo (Proveedores ➔ Cuarto Frío ➔ Vivero ➔ Bloques 01 al 06 ➔ Cosecha)", expanded=True):
        render_fiori_supply_chain_canvas(engine, key_suffix="ocup")
    render_ocupacion_module(db)



elif modulo == "Pedido Material Vegetal":

    from app.ui.pedido_ui import render_pedido_module

    render_pedido_module(db)



elif modulo == "Plan de Enraizamiento":

    from app.ui.enraizamiento_ui import render_enraizamiento_module

    render_enraizamiento_module(db)



elif modulo == "Plan de Siembra":

    from app.ui.siembra_ui import render_siembra_module

    render_siembra_module(db)

# Barra Inferior de Apoyo y Navegación Rápida
if modulo != "Launchpad S&OP (Portada)":
    scen_lbl = st.session_state.get("fiori_scenario", "Plan Base (Oficial)")
    b_pri, b_sec, _ = render_fiori_footer_toolbar(
        module_key=f"ft_{modulo.replace(' ', '_').lower()}",
        status_text=f"Trabajando en: {modulo} • Vista activa: {scen_lbl}",
        primary_label="🔄 Actualizar Datos",
        secondary_label="🏠 Ir a la Portada"
    )
    if b_sec:
        navigate_to_module("Launchpad S&OP (Portada)")
        st.rerun()
    if b_pri:
        st.toast("✅ Datos actualizados correctamente.")
        st.rerun()






