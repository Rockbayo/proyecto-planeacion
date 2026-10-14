import streamlit as st
import pandas as pd
import os
from datetime import date
import altair as alt
from app.models.models import Variedad
from app.services.forecast_service import generar_forecast_13wk
from app.services.calibracion_service import (
    parse_webflowers_report,
    cargar_parametros_calibrados,
    ejecutar_iteraciones_optimizacion,
    ejecutar_iteraciones_segmentadas_por_flor,
    inicializar_o_cargar_datalake,
    integrar_reporte_al_datalake
)

def render_accuracy_module(db):
    st.header("🎯 Forecast Accuracy & Machine Learning")
    st.markdown("""
    Este módulo gestiona el **Data Lake de Ejecuciones y Cumplimientos Poscosecha**, integrando de forma continua 
    los reportes de **Webflowers** con las ejecuciones históricas acumuladas, y ejecuta **iteraciones automatizadas 
    de Machine Learning** para calibrar los parámetros de suavización ($\alpha$) y ventanas de ciclos ($N$).
    """)
    
    # Cargar estado de calibración actual
    params_act = cargar_parametros_calibrados()
    if params_act.get('fecha_calibracion'):
        por_fl = params_act.get('por_flor', {})
        st.markdown(f"#### 🤖 Motor Calibrado por Machine Learning (Última: {params_act.get('fecha_calibracion')} | Semana S{params_act.get('semana_evaluada', 'N/A')})")
        
        c_m1, c_m2, c_m3, c_m4 = st.columns(4)
        cush = por_fl.get('Cushion', {})
        dais = por_fl.get('Daisy', {})
        nov = por_fl.get('Novelty', {})
        glob = params_act.get('global', {})

        with c_m1:
            st.metric(
                "🌸 Cushion (Óptimo)",
                f"{cush.get('ponderacion_%', 100)}% / {cush.get('num_ciclos', 9)} cic",
                f"WAPE: {cush.get('wape_%', 0):.1f}%" if cush.get('wape_%') is not None else None
            )
        with c_m2:
            st.metric(
                "🌼 Daisy (Óptimo)",
                f"{dais.get('ponderacion_%', 100)}% / {dais.get('num_ciclos', 9)} cic",
                f"WAPE: {dais.get('wape_%', 0):.1f}%" if dais.get('wape_%') is not None else None
            )
        with c_m3:
            st.metric(
                "🌺 Novelty (Óptimo)",
                f"{nov.get('ponderacion_%', 100)}% / {nov.get('num_ciclos', 9)} cic",
                f"WAPE: {nov.get('wape_%', 0):.1f}%" if nov.get('wape_%') is not None else None
            )
        with c_m4:
            st.metric(
                "🌐 Global Finca",
                f"{glob.get('ponderacion_%', 100)}% / {glob.get('num_ciclos', 9)} cic",
                f"WAPE: {glob.get('wape_%', 0):.1f}%" if glob.get('wape_%') is not None else None
            )
        st.caption(f"✨ Calibración segmentada por tipo de flor activa. {params_act.get('total_iteraciones', 2000):,} simulaciones evaluadas.")
    else:
        st.info("ℹ️ Parámetros actuales en valores base (100% ponderación / 9 ciclos). Ejecuta las 2,000 iteraciones de calibración segmentada por flor para optimizar las curvas de la finca.")


    tab1, tab2, tab3 = st.tabs([
        "🗄️ Data Lake de Ejecuciones & Recalibración ML",
        "🔬 Prueba de Concepto ML (XGBoost)",
        "📋 Planificador Óptimo MVA (ML)"
    ])
    
    # =========================================================================
    # TAB 1: DATA LAKE DE EJECUCIONES & RECALIBRACIÓN ML
    # =========================================================================
    with tab1:
        # 1. Cargar o Inicializar Data Lake
        df_dl = inicializar_o_cargar_datalake(db)
        total_dl_reg = len(df_dl)
        semanas_dl = sorted(df_dl['Semana'].astype(str).unique())
        vars_dl = df_dl['Variedad'].nunique()
        ult_sem = semanas_dl[-1] if semanas_dl else "N/A"
        prim_sem = semanas_dl[0] if semanas_dl else "N/A"

        st.subheader("🗄️ Data Lake de Ejecuciones y Cumplimientos")
        st.markdown(f"""
        Al igual que el Data Lake de Curvas, este repositorio **acumula y preserva todas las ejecuciones reales de poscosecha**.
        Cada nuevo reporte de Webflowers se **anexa sin borrar la historia previa**, asegurando que la suavización biológica 
        mantenga la profundidad de los ciclos pasados.
        """)

        dl_c1, dl_c2, dl_c3, dl_c4 = st.columns(4)
        dl_c1.metric("Registros en Data Lake", f"{total_dl_reg:,}")
        dl_c2.metric("Semanas Acumuladas", f"{len(semanas_dl)} sem", f"{prim_sem} a {ult_sem}")
        dl_c3.metric("Variedades Monitoreadas", f"{vars_dl:,}")
        dl_c4.metric("Última Semana en Lake", f"S{ult_sem}")

        # Zona de Carga e Integración Continua al Data Lake
        st.divider()
        st.markdown("#### 📥 Integración Continua de Reportes Webflowers al Data Lake")
        
        file_default = "ReporteEstimadosVSRecepcion.xls"
        col_up1, col_up2 = st.columns([1.5, 1])
        with col_up1:
            archivo_subido = st.file_uploader(
                "Subir Nuevo Reporte de Webflowers (.xls / .xlsx / .csv)",
                type=["xls", "xlsx", "csv"],
                key="uploader_wf_datalake",
                help="Sube un archivo de Webflowers para integrarlo acumulativamente al Data Lake."
            )
        with col_up2:
            st.markdown("**O sincronizar reporte local:**")
            if os.path.exists(file_default):
                st.caption(f"📁 Detectado: `{file_default}`")
                if st.button("🔄 Sincronizar 'ReporteEstimadosVSRecepcion.xls'", type="secondary", use_container_width=True):
                    try:
                        df_wf_raw = parse_webflowers_report(file_default)
                        df_dl, count_new, sem_af = integrar_reporte_al_datalake(df_wf_raw, db)
                        st.success(f"✅ ¡Data Lake actualizado! Se integraron {count_new} registros de la semana {sem_af}. Total histórico: {len(df_dl):,} registros.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error sincronizando archivo: {e}")

        if archivo_subido is not None:
            try:
                df_wf_raw = parse_webflowers_report(archivo_subido)
                df_dl, count_new, sem_af = integrar_reporte_al_datalake(df_wf_raw, db)
                st.success(f"✅ ¡Nuevo archivo integrado al Data Lake! {count_new} registros incorporados para las semanas {sem_af}. Total en Lake: {len(df_dl):,} registros.")
                st.rerun()
            except Exception as e:
                st.error(f"Error procesando e integrando archivo: {e}")

        # Selector de Semana y Nivel de Análisis
        st.divider()
        st.markdown("#### 🔍 Análisis de Ejecución por Semana en el Data Lake")
        
        c_sel1, c_sel2 = st.columns([1.5, 1])
        with c_sel1:
            opciones_semanas = [f"S{s} (Más Reciente)" if s == ult_sem else f"S{s}" for s in reversed(semanas_dl)]
            semana_sel_str = st.selectbox("Selecciona la Semana a Analizar:", opciones_semanas, index=0)
            semana_activa = semana_sel_str.replace(" (Más Reciente)", "").replace("S", "").strip()
        with c_sel2:
            flores_disp = ["Todas"] + sorted(list(df_dl['Flor'].dropna().unique()))
            filtro_flor_dl = st.selectbox("Filtrar por Flor", flores_disp)

        # Filtrar datos de la semana activa
        df_sem_view = df_dl[df_dl['Semana'] == semana_activa].copy()
        if filtro_flor_dl != "Todas":
            df_sem_view = df_sem_view[df_sem_view['Flor'] == filtro_flor_dl]

        # KPIs de la semana activa
        tot_rec_sem = df_sem_view['Real_Recepcionado'].sum()
        tot_est_sem = df_sem_view['Estimado_Proyectado'].sum()
        bal_sem = (tot_rec_sem / tot_est_sem * 100) if tot_est_sem > 0 else 0
        err_sem = (df_sem_view['Real_Recepcionado'] - df_sem_view['Estimado_Proyectado']).abs().sum() if tot_est_sem > 0 else 0
        wape_sem = (err_sem / tot_rec_sem * 100) if tot_rec_sem > 0 else 0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Real Recepcionado", f"{tot_rec_sem:,.0f} tallos", f"Semana S{semana_activa}")
        k2.metric("Estimado Proyectado", f"{tot_est_sem:,.0f} tallos" if tot_est_sem > 0 else "N/D (Histórico PER)")
        k3.metric("Cumplimiento (Balance)", f"{bal_sem:.1f}%" if tot_est_sem > 0 else "Base Real")
        k4.metric("Error WAPE", f"{wape_sem:.1f}%" if tot_est_sem > 0 else "N/A", f"{err_sem:,.0f} tallos err" if tot_est_sem > 0 else None)

        # -----------------------------------------------------------------
        # BOTÓN NOTORIO DE ITERACIONES Y RECALIBRACIÓN ML
        # -----------------------------------------------------------------
        st.divider()
        # -----------------------------------------------------------------
        # BOTÓN NOTORIO DE ITERACIONES Y RECALIBRACIÓN ML (SEGMENTADA POR FLOR)
        # -----------------------------------------------------------------
        st.divider()
        with st.container(border=True):
            st.markdown("### 🔄 Recalibración Dinámica de Curvas Segmentada por Flor (2,000 Iteraciones ML)")
            st.markdown("""
            Este motor ejecuta una **optimización biológica de alta resolución de 2,000 simulaciones** cruzando las ejecuciones 
            reales del Data Lake contra el histórico de camas piloto (`Historico_Curvas.csv`), segmentado de manera independiente por:
            * **🌸 Cushion:** 500 simulaciones (25 niveles de $\\alpha$ × 20 ventanas de ciclos $N$).
            * **🌼 Daisy:** 500 simulaciones (25 niveles de $\\alpha$ × 20 ventanas de ciclos $N$).
            * **🌺 Novelty:** 500 simulaciones (25 niveles de $\\alpha$ × 20 ventanas de ciclos $N$).
            * **🌐 Global Finca:** 500 simulaciones consolidadas para variedades sin segmento específico.

            **Beneficios Clave:**
            1. **Suavización Personalizada por Flor:** Reconoce que la curva de *Daisy* requiere mayor ventana histórica mientras que *Novelty* o *Cushion* tienen dinámicas fenológicas distintas.
            2. **Adopción Inmediata en Toda la Plataforma:** Los parámetros ($\alpha^*_{flor}$, $N^*_{flor}$) se guardan y son adoptados de inmediato por la **Proyección de 52 Semanas**, las **Curvas Dinámicas** y el **Pedido de Esquejes**, eliminando el tanteo manual.
            """)

            c_btn1, c_btn2 = st.columns([2.5, 1])
            with c_btn1:
                btn_iterar = st.button(
                    "🚀 EJECUTAR 2,000 ITERACIONES DE RECALIBRACIÓN (SEGMENTADA POR FLOR)",
                    type="primary",
                    use_container_width=True,
                    help="Ejecuta 2,000 simulaciones ultra-rápidas en memoria (500 por tipo de flor) y calcula los parámetros óptimos."
                )
            with c_btn2:
                if st.button("🗑️ Limpiar Calibración Guardada", use_container_width=True):
                    if os.path.exists("parametros_calibrados.json"):
                        os.remove("parametros_calibrados.json")
                    if 'res_opt' in st.session_state:
                        del st.session_state['res_opt']
                    st.rerun()

        # Ejecución de optimización
        if btn_iterar:
            with st.spinner("🤖 Ejecutando 2,000 simulaciones biológicas segmentadas por flor sobre el Data Lake (~30s)..."):
                try:
                    # Usar la semana seleccionada o la más reciente con estimaciones
                    df_target_wf = df_sem_view[df_sem_view['Estimado_Proyectado'] > 0]
                    if df_target_wf.empty:
                        # Si la semana elegida no tenía estimaciones, buscar la semana más reciente con estimaciones
                        df_target_wf = df_dl[df_dl['Estimado_Proyectado'] > 0]
                        ult_sem_wf = df_target_wf['Semana'].max()
                        df_target_wf = df_target_wf[df_target_wf['Semana'] == ult_sem_wf]

                    # Mapear columnas requeridas por el optimizador
                    df_opt_input = df_target_wf.rename(columns={
                        'Real_Recepcionado': 'Tallos_Recepcionados',
                        'Estimado_Proyectado': 'Tallos_Estimados',
                        'Semana': 'Semana_Estimada'
                    })

                    res_opt = ejecutar_iteraciones_segmentadas_por_flor(db, df_opt_input)
                    st.session_state['res_opt'] = res_opt
                    st.toast("✅ ¡Optimización de 2,000 iteraciones segmentada por flor completada con éxito!")
                    st.rerun()
                except Exception as e:
                    import traceback
                    st.error(f"Error durante las iteraciones de optimización: {e}")
                    st.code(traceback.format_exc())

        # Despliegue de resultados de optimización si existen
        if 'res_opt' in st.session_state:
            res_opt = st.session_state['res_opt']
            info_res = res_opt['resultado']
            df_iteraciones = res_opt['df_iteraciones']
            df_detalle_ml = res_opt['df_detalle']
            por_flor_res = info_res.get('por_flor', {})

            with st.container(border=True):
                st.markdown("### 🏆 Resultados de la Recalibración Óptima Segmentada por Flor")
                st.success(f"""
                **¡Calibración de 2,000 Iteraciones Aplicada!** Los parámetros óptimos biológicos por flor fueron 
                guardados y ahora gobiernan de manera diferenciada las curvas de cada variedad en la plataforma.
                """)

                # 4 Métricas de las 3 flores + Global
                col_cush, col_dais, col_nov, col_glob = st.columns(4)
                
                cush_info = por_flor_res.get('Cushion', {})
                with col_cush:
                    st.markdown("#### 🌸 Cushion")
                    st.metric("Ponderación $\\alpha^*$", f"{cush_info.get('ponderacion_%', 100)}%", f"α = {cush_info.get('alpha', 1.0)}")
                    st.metric("Ciclos $N^*$", f"{cush_info.get('num_ciclos', 9)} periodos")
                    st.metric("Error WAPE*", f"{cush_info.get('wape_%', 0):.2f}%", f"Bias: {cush_info.get('bias_%', 0):.1f}%")

                dais_info = por_flor_res.get('Daisy', {})
                with col_dais:
                    st.markdown("#### 🌼 Daisy")
                    st.metric("Ponderación $\\alpha^*$", f"{dais_info.get('ponderacion_%', 100)}%", f"α = {dais_info.get('alpha', 1.0)}")
                    st.metric("Ciclos $N^*$", f"{dais_info.get('num_ciclos', 9)} periodos")
                    st.metric("Error WAPE*", f"{dais_info.get('wape_%', 0):.2f}%", f"Bias: {dais_info.get('bias_%', 0):.1f}%")

                nov_info = por_flor_res.get('Novelty', {})
                with col_nov:
                    st.markdown("#### 🌺 Novelty")
                    st.metric("Ponderación $\\alpha^*$", f"{nov_info.get('ponderacion_%', 100)}%", f"α = {nov_info.get('alpha', 1.0)}")
                    st.metric("Ciclos $N^*$", f"{nov_info.get('num_ciclos', 9)} periodos")
                    st.metric("Error WAPE*", f"{nov_info.get('wape_%', 0):.2f}%", f"Bias: {nov_info.get('bias_%', 0):.1f}%")

                glob_info = info_res.get('global', {})
                with col_glob:
                    st.markdown("#### 🌐 Global Finca")
                    st.metric("Ponderación $\\alpha^*$", f"{glob_info.get('ponderacion_%', 100)}%", f"α = {glob_info.get('alpha', 1.0)}")
                    st.metric("Ciclos $N^*$", f"{glob_info.get('num_ciclos', 9)} periodos")
                    st.metric("Error WAPE*", f"{glob_info.get('wape_%', 0):.2f}%", f"-{info_res.get('reduccion_error_%', 0):.1f}% vs. base")

                # Selector de Flor para explorar las curvas de convergencia
                st.divider()
                st.markdown("#### 📉 Curvas de Convergencia del Error (2,000 Iteraciones ML)")
                flor_chart_sel = st.radio(
                    "Ver convergencia para:",
                    ["Todas las Flores (Comparativa)", "Cushion", "Daisy", "Novelty", "Global Finca"],
                    horizontal=True
                )

                df_chart_source = df_iteraciones.copy()
                if flor_chart_sel != "Todas las Flores (Comparativa)":
                    fl_filter_name = flor_chart_sel.replace(" Finca", "")
                    df_chart_source = df_chart_source[df_chart_source['Flor'] == fl_filter_name]

                chart_iter = alt.Chart(df_chart_source).mark_circle(size=70).encode(
                    x=alt.X('ponderacion_%:Q', title='Ponderación Alpha (%)'),
                    y=alt.Y('wape_%:Q', title='Error WAPE (%)', scale=alt.Scale(zero=False)),
                    color=alt.Color('Flor:N', title='Tipo de Flor', scale=alt.Scale(
                        domain=['Cushion', 'Daisy', 'Novelty', 'Global'],
                        range=['#e377c2', '#ff7f0e', '#1f77b4', '#2ca02c']
                    )),
                    tooltip=['Flor', 'iteracion', 'alpha', 'num_ciclos', 'wape_%', 'bias_%', 'error_tallos']
                ).properties(height=340, title=f"Búsqueda de Grilla: WAPE vs. Ponderación Alpha ({flor_chart_sel})")

                st.altair_chart(chart_iter, width='stretch')

                # Tabla comparativa Antes vs. Calibrado ML
                st.markdown("#### 🔬 Variedades con Mayor Reducción de Error Biológico")
                df_mejora = df_detalle_ml.sort_values(by='Mejora_Tallos', ascending=False)
                st.dataframe(
                    df_mejora[[
                        'Flor', 'Color', 'Variedad', 'Real_Recepcionado',
                        'Estimado_Anterior', 'Estimado_ML_Calibrado',
                        'Error_Anterior', 'Error_ML', 'Mejora_Tallos',
                        'Precision_Anterior_%', 'Precision_ML_%'
                    ]],
                    width='stretch'
                )


        # Detalle de la semana en el Data Lake
        st.divider()
        st.markdown(f"#### 📋 Registros de la Semana S{semana_activa} en el Data Lake")
        st.dataframe(
            df_sem_view[[
                'Semana', 'Flor', 'Color', 'Variedad', 
                'Real_Recepcionado', 'Estimado_Proyectado', 'Balance_%', 
                'Fuente', 'Fecha_Registro'
            ]],
            width='stretch'
        )

        # Gráfico comparativo de la semana si tiene estimaciones
        if tot_est_sem > 0:
            df_chart_sem = df_sem_view.head(15).melt(
                id_vars=['Variedad'],
                value_vars=['Real_Recepcionado', 'Estimado_Proyectado'],
                var_name='Tipo',
                value_name='Tallos'
            )
            chart_sem = alt.Chart(df_chart_sem).mark_bar().encode(
                x=alt.X('Variedad:N', sort='-y', title='Variedad'),
                y=alt.Y('Tallos:Q', title='Tallos'),
                color=alt.Color('Tipo:N', scale=alt.Scale(domain=['Real_Recepcionado', 'Estimado_Proyectado'], range=['#2ca02c', '#ff7f0e'])),
                xOffset='Tipo:N',
                tooltip=['Variedad', 'Tipo', 'Tallos']
            ).properties(height=320, title=f"Top 15 Variedades Semana S{semana_activa}: Real Recepcionado vs. Estimado ForeCast")
            st.altair_chart(chart_sem, width='stretch')

        # -----------------------------------------------------------------
        # EXPANDER: TENDENCIA TEMPORAL MULTI-CICLO DEL DATA LAKE (93 SEMANAS)
        # -----------------------------------------------------------------
        with st.expander("📈 Serie Temporal Completa del Data Lake (93 Semanas Históricas)", expanded=False):
            st.markdown("Evolución de tallos recepcionados en poscosecha semana a semana:")
            df_trend = df_dl.groupby('Semana')['Real_Recepcionado'].sum().reset_index()
            df_trend['Semana_Num'] = df_trend['Semana'].astype(str)
            df_trend = df_trend.sort_values('Semana_Num')

            chart_trend = alt.Chart(df_trend).mark_line(point=True, color='#1f77b4').encode(
                x=alt.X('Semana_Num:N', title='Semana Operativa', axis=alt.Axis(labelAngle=-45)),
                y=alt.Y('Real_Recepcionado:Q', title='Tallos Recepcionados', scale=alt.Scale(zero=False)),
                tooltip=['Semana_Num', 'Real_Recepcionado']
            ).properties(height=350, title="Histórico de Cosecha Total en Poscosecha (Data Lake)")
            st.altair_chart(chart_trend, width='stretch')

    # =========================================================================
    # TAB 2: PRUEBA DE CONCEPTO ML (XGBOOST)
    # =========================================================================
    with tab2:
        st.subheader("Prueba de Concepto - Motor Machine Learning (XGBoost)")
        st.markdown("""
        El motor actual utiliza un modelo con suavización exponencial calibrada.
        Esta sección permite ejecutar un entrenamiento experimental utilizando modelos no lineales de gradiente (XGBoost)
        para comparar el desempeño contra el modelo base.
        """)
        
        col_ml1, col_ml2 = st.columns([1, 2])
        with col_ml1:
            st.info("💡 **Modelo propuesto:** XGBoost Regressor.\n**Features:**\n- Variedad\n- Lags de siembra (9 a 16 semanas)\n- Estacionalidad operativa")
            if st.button("🚀 Re-Entrenar Modelo (XGBoost)", use_container_width=True):
                st.success("Lanzando proceso de entrenamiento en background...")
                import subprocess
                try:
                    subprocess.Popen(["python", "scripts/train_xgb.py"])
                    st.toast("Proceso ML iniciado.")
                except Exception as e:
                    st.error(f"Error iniciando proceso: {e}")
                
        with col_ml2:
            if os.path.exists('ml_results.md'):
                st.markdown("### Resultados del Último Entrenamiento")
                with open('ml_results.md', 'r', encoding='utf-8') as f:
                    st.markdown(f.read())
            else:
                st.warning("No hay resultados de modelos de Machine Learning todavía.")

    # =========================================================================
    # TAB 3: PLANIFICADOR ÓPTIMO MVA (MACHINE LEARNING)
    # =========================================================================
    with tab3:
        st.subheader("Planificador Óptimo MVA (Machine Learning)")
        st.markdown("""
        **Analytics Prescriptivo:** Carga tu **Plan de Producción Aprobado** (metas de cosecha por semana). 
        El algoritmo utilizará el modelo de Inteligencia Artificial para iterar y encontrar exactamente 
        **cuántos esquejes debes pedir y sembrar** en cada semana para lograr una ejecución casi perfecta de la meta.
        """)
        
        col_btn, col_upload = st.columns([1, 1])
        with col_btn:
            usar_sistema = False
            if os.path.exists("PedidoConsolidado_master.xlsx"):
                st.info("✅ El sistema tiene un Pedido Consolidado MVA (52 semanas) guardado.")
                if st.button("🚀 Usar Pedido Consolidado del Sistema", type="primary", use_container_width=True):
                    usar_sistema = True
                    df_master = pd.read_excel("PedidoConsolidado_master.xlsx")
                    semanas_cols = [c for c in df_master.columns if str(c).startswith('S202')]
                    df_target = df_master.melt(id_vars=['Variedad'], value_vars=semanas_cols, var_name='Semana_Objetivo', value_name='Exportable_Meta')
                    df_target['Semana_Objetivo'] = df_target['Semana_Objetivo'].str.replace('S', '')
            else:
                st.warning("⚠️ No hay un Pedido Consolidado MVA guardado en el sistema.")
                
        with col_upload:
            st.markdown("**O subir un plan alternativo:**")
            plan_archivo = st.file_uploader("📥 Subir Plan (CSV/Excel)", type=["csv", "xlsx"], key="uploader_plan_ml")
            usar_upload = False
            if plan_archivo is not None:
                if st.button("🎯 Ejecutar con Archivo Subido", use_container_width=True):
                    usar_upload = True
                    if plan_archivo.name.endswith('.csv'):
                        df_target = pd.read_csv(plan_archivo)
                    else:
                        df_target = pd.read_excel(plan_archivo)
                        
        if usar_sistema or usar_upload:
            with st.spinner("El motor de ML está iterando simulaciones para encontrar el plan óptimo..."):
                try:
                    df_target.columns = [str(c).strip() for c in df_target.columns]
                    
                    if 'Semana' in df_target.columns and 'Suma de Tallos' in df_target.columns:
                        df_target = df_target.rename(columns={'Semana': 'Semana_Objetivo', 'Suma de Tallos': 'Exportable_Meta'})
                        
                    if 'Variedad' not in df_target.columns or 'Semana_Objetivo' not in df_target.columns or 'Exportable_Meta' not in df_target.columns:
                        st.error(f"El archivo debe contener las columnas: Variedad, Semana_Objetivo, Exportable_Meta. Columnas encontradas: {list(df_target.columns)}")
                    else:
                        from app.services.ml_optimizer_service import optimizar_siembras_con_ml, generar_mva_clasico
                        
                        df_target['Semana_Objetivo'] = df_target['Semana_Objetivo'].apply(lambda x: str(int(float(x))) if pd.notna(x) else "")
                        df_target = df_target[df_target['Semana_Objetivo'] != ""]
                        
                        df_clasico = generar_mva_clasico(db, df_target)
                        df_opt = optimizar_siembras_con_ml(db, df_target)
                        
                        if not df_clasico.empty:
                            st.success("✅ Generación de Planes completada.")
                            tab_clasico, tab_ml = st.tabs(["MVA Clásico (Base)", "MVA Optimizado (Machine Learning)"])
                            import io
                            
                            with tab_clasico:
                                st.dataframe(df_clasico, width='stretch')
                                out_clasico = io.BytesIO()
                                with pd.ExcelWriter(out_clasico, engine='xlsxwriter') as writer:
                                    df_clasico.to_excel(writer, index=False, sheet_name="MVA_Clasico")
                                
                                st.download_button(
                                    label="📥 Descargar Plan MVA Clásico (Excel)",
                                    data=out_clasico.getvalue(),
                                    file_name=f"MVA_Clasico_{date.today()}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    use_container_width=True
                                )
                                
                            with tab_ml:
                                if not df_opt.empty:
                                    st.dataframe(df_opt, width='stretch')
                                    output_mrp = io.BytesIO()
                                    with pd.ExcelWriter(output_mrp, engine='xlsxwriter') as writer:
                                        df_opt.to_excel(writer, index=False, sheet_name="Plan_Optimo_MVA")
                                    
                                    st.download_button(
                                        label="🚀 Descargar Plan MVA Optimizado (Excel)",
                                        data=output_mrp.getvalue(),
                                        file_name=f"MVA_Optimizado_{date.today()}.xlsx",
                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                        type="primary",
                                        use_container_width=True
                                    )
                                else:
                                    st.warning("El modelo ML no pudo generar un plan.")
                        else:
                            st.warning("No se pudo generar un plan (revisa que haya variedades activas y metas > 0).")
                            
                except Exception as e:
                    import traceback
                    st.error(f"Error en el optimizador: {e}")
                    st.code(traceback.format_exc())
