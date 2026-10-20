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
    st.header("⚙️ Calibración Dinámica de Curvas y Data Lake")
    st.caption("Alineación de curvas biológicas y optimización fenológica multi-ciclo a partir de recepciones reales de Webflowers.")
    
    # Cargar estado de calibración actual
    params_act = cargar_parametros_calibrados()
    if params_act.get('fecha_calibracion'):
        por_fl = params_act.get('por_flor', {})
        st.markdown(f"#### 🎯 Parámetros Óptimos Vigentes (Calibración: {params_act.get('fecha_calibracion')} | Semana S{params_act.get('semana_evaluada', 'N/A')})")
        
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
        "🔄 Recalibración de Curvas (Simulaciones)",
        "🗄️ Data Lake de Ejecuciones (Webflowers)",
        "📈 Tendencias Históricas Multi-Ciclo"
    ])
    
    # Cargar Data Lake compartido
    df_dl = inicializar_o_cargar_datalake(db)
    total_dl_reg = len(df_dl)
    semanas_dl = sorted(df_dl['Semana'].astype(str).unique())
    vars_dl = df_dl['Variedad'].nunique()
    ult_sem = semanas_dl[-1] if semanas_dl else "N/A"
    prim_sem = semanas_dl[0] if semanas_dl else "N/A"

    # =========================================================================
    # TAB 1: RECALIBRACIÓN DINÁMICA DE CURVAS (SIMULACIONES)
    # =========================================================================
    with tab1:
        st.subheader("Simulación y Optimización Segmentada de Curvas")
        st.markdown("""
        Este motor ejecuta una **optimización biológica de alta resolución de 2,000 simulaciones** cruzando las recepciones 
        reales del Data Lake contra el histórico de camas piloto (`Historico_Curvas.csv`), segmentado de manera independiente por:
        * **🌸 Cushion:** 500 simulaciones (25 niveles de $\\alpha$ × 20 ventanas de ciclos $N$).
        * **🌼 Daisy:** 500 simulaciones (25 niveles de $\\alpha$ × 20 ventanas de ciclos $N$).
        * **🌺 Novelty:** 500 simulaciones (25 niveles de $\\alpha$ × 20 ventanas de ciclos $N$).
        * **🌐 Global Finca:** 500 simulaciones consolidadas para variedades sin segmento específico.

        **Adopción Inmediata:** Los parámetros ($\alpha^*_{flor}$, $N^*_{flor}$) guardados gobiernan de forma automática la **Proyección de ForeCast**, 
        las **Curvas Dinámicas** y el **Plan de Enraizamiento**, eliminando cualquier calibración manual a ciegas.
        """)

        with st.container(border=True):
            c_btn1, c_btn2 = st.columns([2.5, 1])
            with c_btn1:
                btn_iterar = st.button(
                    "🚀 EJECUTAR 2,000 ITERACIONES DE RECALIBRACIÓN (SEGMENTADA POR FLOR)",
                    type="primary",
                    width="stretch",
                    help="Ejecuta 2,000 simulaciones en memoria (500 por tipo de flor) y calcula los parámetros óptimos."
                )
            with c_btn2:
                if st.button("🗑️ Restablecer Parámetros Base", width="stretch"):
                    if os.path.exists("parametros_calibrados.json"):
                        os.remove("parametros_calibrados.json")
                    if 'res_opt' in st.session_state:
                        del st.session_state['res_opt']
                    st.toast("Parámetros restablecidos a valores estándar.")
                    st.rerun()

        # Ejecución de optimización
        if btn_iterar:
            with st.spinner("Ejecutando 2,000 simulaciones biológicas segmentadas por flor sobre el Data Lake (~15-25s)..."):
                try:
                    df_target_wf = df_dl[df_dl['Estimado_Proyectado'] > 0]
                    if df_target_wf.empty:
                        df_target_wf = df_dl
                    else:
                        ult_sem_wf = df_target_wf['Semana'].max()
                        df_target_wf = df_target_wf[df_target_wf['Semana'] == ult_sem_wf]

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
                **¡Calibración de 2,000 Iteraciones Guardada!** Los parámetros óptimos biológicos por flor fueron 
                almacenados y ahora gobiernan las curvas de cada variedad en la plataforma.
                """)

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
                st.markdown("#### 📉 Curvas de Convergencia del Error (2,000 Iteraciones)")
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
                        range=['#0070F2', '#059669', '#D97706', '#7C3AED']
                    )),
                    tooltip=['Flor', 'iteracion', 'alpha', 'num_ciclos', 'wape_%', 'bias_%', 'error_tallos']
                ).properties(height=340, title=f"Búsqueda de Parámetros: WAPE vs. Ponderación Alpha ({flor_chart_sel})")

                st.altair_chart(chart_iter, width='stretch')

                # Tabla comparativa Antes vs. Calibrado
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

    # =========================================================================
    # TAB 2: DATA LAKE DE EJECUCIONES (WEBFLOWERS)
    # =========================================================================
    with tab2:
        st.subheader("Data Lake de Ejecuciones y Cumplimientos Poscosecha")
        st.markdown("""
        Este repositorio **acumula y preserva las recepciones reales de poscosecha** provenientes de Webflowers.
        Cada nuevo reporte se integra sumando historia sin sobreescribir semanas previas.
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
            st.markdown("**O sincronizar reporte local detectado:**")
            if os.path.exists(file_default):
                st.caption(f"📁 Detectado: `{file_default}`")
                if st.button("🔄 Sincronizar 'ReporteEstimadosVSRecepcion.xls'", type="secondary", width="stretch"):
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
        st.markdown("#### 🔍 Análisis de Cumplimiento por Semana")
        
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
                color=alt.Color('Tipo:N', scale=alt.Scale(domain=['Real_Recepcionado', 'Estimado_Proyectado'], range=['#059669', '#0070F2'])),
                xOffset='Tipo:N',
                tooltip=['Variedad', 'Tipo', 'Tallos']
            ).properties(height=320, title=f"Top 15 Variedades Semana S{semana_activa}: Real Recepcionado vs. Estimado ForeCast")
            st.altair_chart(chart_sem, width='stretch')

        # Detalle de la semana en el Data Lake
        st.markdown(f"#### 📋 Registros Detallados Semana S{semana_activa}")
        st.dataframe(
            df_sem_view[[
                'Semana', 'Flor', 'Color', 'Variedad', 
                'Real_Recepcionado', 'Estimado_Proyectado', 'Balance_%', 
                'Fuente', 'Fecha_Registro'
            ]],
            width='stretch'
        )

    # =========================================================================
    # TAB 3: TENDENCIAS HISTÓRICAS MULTI-CICLO (COMPARATIVO ENTRE AÑOS)
    # =========================================================================
    with tab3:
        st.subheader("📈 Tendencias Multi-Ciclo Comparativas entre Años")
        st.markdown("""
        Comparativo interanual de la recepción real de tallos semana a semana (semanas ISO 1 a 52). 
        Permite contrastar el comportamiento estacional y picos de cosecha de cada año sobre la misma escala temporal.
        """)

        # Preparación de datos interanuales desde el Data Lake actualizado
        df_dl_trend = df_dl.copy()
        df_dl_trend['Semana_Clean'] = df_dl_trend['Semana'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        df_dl_trend['Año'] = df_dl_trend['Semana_Clean'].str[:4]
        df_dl_trend['Semana_Num'] = pd.to_numeric(df_dl_trend['Semana_Clean'].str[4:], errors='coerce')
        df_dl_trend = df_dl_trend.dropna(subset=['Semana_Num', 'Año'])
        df_dl_trend['Semana_Num'] = df_dl_trend['Semana_Num'].astype(int)
        df_dl_trend = df_dl_trend[(df_dl_trend['Semana_Num'] >= 1) & (df_dl_trend['Semana_Num'] <= 53)]

        anios_detectados = sorted(df_dl_trend['Año'].unique())

        c_t1, c_t2 = st.columns([1.5, 1])
        with c_t1:
            flores_comp = ["Todas (Total Finca)"] + sorted(list(df_dl_trend['Flor'].dropna().unique()))
            flor_sel_comp = st.selectbox("Filtrar Comparativo por Tipo de Flor:", flores_comp, key="sel_flor_comp_tab3")
        with c_t2:
            st.caption(f"📁 **Data Lake Activo:** {len(df_dl):,} registros históricos sincronizados.")
            st.caption(f"📅 **Años en Base:** {', '.join(anios_detectados)} | Última semana: **S{ult_sem}**")

        if flor_sel_comp != "Todas (Total Finca)":
            df_dl_trend = df_dl_trend[df_dl_trend['Flor'] == flor_sel_comp]

        df_trend_comp = df_dl_trend.groupby(['Año', 'Semana_Num'])['Real_Recepcionado'].sum().reset_index()
        df_trend_comp = df_trend_comp.sort_values(by=['Año', 'Semana_Num'])
        df_trend_comp['Semana_Label'] = df_trend_comp['Semana_Num'].apply(lambda w: f"S{w:02d}")

        if not df_trend_comp.empty:
            # Gráfico Multi-Línea Interanual con Altair
            paleta_anios = ['#0070F2', '#E23232', '#059669', '#FF9800', '#9C27B0']
            chart_trend = alt.Chart(df_trend_comp).mark_line(point=True).encode(
                x=alt.X(
                    'Semana_Num:Q', 
                    title='Semana del Año (1 a 52)',
                    scale=alt.Scale(domain=[1, 52]),
                    axis=alt.Axis(tickCount=26, format='d')
                ),
                y=alt.Y(
                    'Real_Recepcionado:Q', 
                    title='Tallos Recepcionados en Poscosecha', 
                    scale=alt.Scale(zero=False)
                ),
                color=alt.Color(
                    'Año:N', 
                    title='Año', 
                    scale=alt.Scale(range=paleta_anios[:len(anios_detectados)])
                ),
                tooltip=[
                    alt.Tooltip('Año:N', title='Año'),
                    alt.Tooltip('Semana_Label:N', title='Semana'),
                    alt.Tooltip('Real_Recepcionado:Q', title='Tallos Recepcionados', format=',.0f')
                ]
            ).properties(
                height=420,
                title=f"Comparativo de Recepción Real por Año: {', '.join(anios_detectados)} ({flor_sel_comp})"
            ).interactive()

            st.altair_chart(chart_trend, width='stretch')

            # Matriz Comparativa Detallada Semana a Semana
            with st.expander("📋 Ver Matriz Comparativa y Variaciones Interanuales Semana a Semana", expanded=False):
                df_pivot_comp = df_trend_comp.pivot(index='Semana_Num', columns='Año', values='Real_Recepcionado').fillna(0)
                
                # Calcular variación si existen al menos 2 años
                if len(anios_detectados) >= 2:
                    a_ult = anios_detectados[-1]
                    a_ant = anios_detectados[-2]
                    df_pivot_comp[f'Dif_{a_ult}_vs_{a_ant}'] = df_pivot_comp[a_ult] - df_pivot_comp[a_ant]
                    df_pivot_comp[f'Var_%_{a_ult}_vs_{a_ant}'] = (
                        (df_pivot_comp[a_ult] - df_pivot_comp[a_ant]) / df_pivot_comp[a_ant].replace(0, pd.NA) * 100
                    ).fillna(0).round(1)

                df_pivot_comp.index = [f"Semana {w:02d}" for w in df_pivot_comp.index]
                formato_cols = {col: "{:,.0f}" for col in df_pivot_comp.columns if not col.startswith('Var_%')}
                for col in df_pivot_comp.columns:
                    if col.startswith('Var_%'):
                        formato_cols[col] = "{:+.1f}%"

                st.dataframe(df_pivot_comp.style.format(formato_cols), width='stretch')
        else:
            st.info("No se encontraron registros de recepciones en el Data Lake para los filtros seleccionados.")
