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

    generar_grilla_calibracion,

    inicializar_o_cargar_datalake,

    integrar_reporte_al_datalake

)



def render_accuracy_module(db):

    

    # Cargar estado de calibración actual

    params_act = cargar_parametros_calibrados()

    if params_act.get('fecha_calibracion'):

        por_fl = params_act.get('por_flor', {})

        st.markdown(f"#### 🎯 Parámetros de Ajuste Vigentes (Última calibración: {params_act.get('fecha_calibracion')} | Semana S{params_act.get('semana_evaluada', 'N/A')})")

        

        c_m1, c_m2, c_m3, c_m4 = st.columns(4)

        cush = por_fl.get('Cushion', {})

        dais = por_fl.get('Daisy', {})

        nov = por_fl.get('Novelty', {})

        glob = params_act.get('global', {})



        with c_m1:

            st.metric(

                "🌸 Cushion (Ajuste Óptimo)",

                f"{cush.get('ponderacion_%', 100)}% recientes / {cush.get('num_ciclos', 9)} lotes",

                f"Desviación: {cush.get('wape_%', 0):.1f}%" if cush.get('wape_%') is not None else None

            )

        with c_m2:

            st.metric(

                "🌼 Daisy (Ajuste Óptimo)",

                f"{dais.get('ponderacion_%', 100)}% recientes / {dais.get('num_ciclos', 9)} lotes",

                f"Desviación: {dais.get('wape_%', 0):.1f}%" if dais.get('wape_%') is not None else None

            )

        with c_m3:

            st.metric(

                "🌺 Novelty (Ajuste Óptimo)",

                f"{nov.get('ponderacion_%', 100)}% recientes / {nov.get('num_ciclos', 9)} lotes",

                f"Desviación: {nov.get('wape_%', 0):.1f}%" if nov.get('wape_%') is not None else None

            )

        with c_m4:

            st.metric(

                "🌐 Toda la Finca",

                f"{glob.get('ponderacion_%', 100)}% recientes / {glob.get('num_ciclos', 9)} lotes",

                f"Desviación: {glob.get('wape_%', 0):.1f}%" if glob.get('wape_%') is not None else None

            )

        st.caption(f"✨ Ajuste diferenciado por flor activo en la plataforma. Basado en {params_act.get('total_iteraciones', 2000):,} pruebas históricas analizadas.")

    else:

        st.info("ℹ️ Parámetros en valores estándar de inicio (100% peso reciente / 9 lotes históricos). Ejecuta las pruebas de calibración para afinar las curvas a la realidad productiva de la finca.")



    tab1, tab2, tab3 = st.tabs([

        "🔄 Calibración y Ajuste de Curvas",

        "🗄️ Historial de Recepciones Poscosecha (PER4)",

        "📈 Comparativo Histórico entre Años"

    ])

    

    # Cargar Data Lake compartido

    df_dl = inicializar_o_cargar_datalake(db)

    total_dl_reg = len(df_dl)

    semanas_dl = sorted(df_dl['Semana'].astype(str).unique())

    vars_dl = df_dl['Variedad'].nunique()

    ult_sem = semanas_dl[-1] if semanas_dl else "N/A"

    prim_sem = semanas_dl[0] if semanas_dl else "N/A"



    # =========================================================================

    # TAB 1: CALIBRACIÓN Y AJUSTE DE CURVAS

    # =========================================================================

    with tab1:

        st.subheader("Calibración y Ajuste de Curvas de Floración")

        st.markdown("""

        Este proceso compara automáticamente lo que realmente llegó a poscosecha frente a lo proyectado en campo, 

        probando múltiples combinaciones para encontrar la fórmula más exacta y confiable para cada flor:

        * **🌸 Cushion:** Evalúa qué tanto influyen los lotes recientes frente a la historia general de la variedad.

        * **🌼 Daisy:** Ajusta el ritmo y la velocidad de apertura específica para margaritas.

        * **🌺 Novelty:** Calibra de forma independiente las variedades especiales y novedosas.

        * **🌐 Toda la Finca:** Aplica un balance global confiable para el resto de variedades de la finca.



        **Resultado inmediato:** Las proyecciones semanales, las curvas de corte y el plan de enraizamiento 

        adoptarán estos ajustes automáticamente, reduciendo diferencias entre la flor ofrecida comercialmente y la realmente cosechada.

        """)



        with st.container(border=True):

            st.markdown("##### ⚙️ Parámetros de la Búsqueda")

            col_iter1, col_iter2 = st.columns([2, 1.2])

            with col_iter1:

                num_iter = st.slider(

                    "Cantidad de pruebas automáticas a evaluar:",

                    min_value=2000,

                    max_value=6000,

                    value=2000,

                    step=500,

                    help="Mínimo 2,000 pruebas. Aumentar las pruebas en múltiplos de 500 afina la precisión al analizar más combinaciones históricas."

                )

            with col_iter2:

                pruebas_por_flor = num_iter // 4

                st.caption(f"📊 **Distribución de Pruebas:**\n• **{num_iter:,} pruebas** en total.\n• **{pruebas_por_flor:,} pruebas** por cada tipo de flor.")



            c_btn1, c_btn2 = st.columns([2.5, 1])

            with c_btn1:

                btn_iterar = st.button(

                    f"🚀 Ejecutar {num_iter:,} Pruebas de Calibración",

                    type="primary",

                    width="stretch",

                    help=f"Evalúa {num_iter:,} combinaciones históricas ({pruebas_por_flor:,} por tipo de flor) para afinar las curvas."

                )

            with c_btn2:

                if st.button("🗑️ Restablecer Valores de Fábrica", width="stretch"):

                    if os.path.exists("parametros_calibrados.json"):

                        os.remove("parametros_calibrados.json")

                    if 'res_opt' in st.session_state:

                        del st.session_state['res_opt']

                    st.toast("Parámetros restablecidos a los valores iniciales.")

                    st.rerun()



        # Ejecución de calibración

        if btn_iterar:

            with st.spinner(f"Analizando {num_iter:,} combinaciones históricas segmentadas por flor sobre los datos de poscosecha..."):

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



                    alphas_grid, ciclos_grid = generar_grilla_calibracion(num_iter)

                    res_opt = ejecutar_iteraciones_segmentadas_por_flor(

                        db, 

                        df_opt_input, 

                        grid_alphas=alphas_grid, 

                        grid_ciclos=ciclos_grid

                    )

                    st.session_state['res_opt'] = res_opt

                    st.toast(f"✅ ¡Calibración de {num_iter:,} pruebas completada con éxito!")

                    st.rerun()

                except Exception as e:

                    import traceback

                    st.error(f"Error durante las pruebas de calibración: {e}")

                    st.code(traceback.format_exc())



        # Despliegue de resultados de calibración si existen

        if 'res_opt' in st.session_state:

            res_opt = st.session_state['res_opt']

            info_res = res_opt['resultado']

            df_iteraciones = res_opt['df_iteraciones']

            df_detalle_ml = res_opt['df_detalle']

            por_flor_res = info_res.get('por_flor', {})

            tot_iter_ejecutada = info_res.get('total_iteraciones', num_iter)



            with st.container(border=True):

                st.markdown("### 🏆 Resultados del Mejor Ajuste por Tipo de Flor")

                st.success(f"""

                **¡Ajuste de {tot_iter_ejecutada:,} Pruebas Guardado con Éxito!** Las fórmulas más exactas 

                fueron almacenadas y ahora gobiernan de manera automática todas las proyecciones de la plataforma.

                """)



                col_cush, col_dais, col_nov, col_glob = st.columns(4)

                cush_info = por_flor_res.get('Cushion', {})

                with col_cush:

                    st.markdown("#### 🌸 Cushion")

                    st.metric("Peso Lotes Recientes", f"{cush_info.get('ponderacion_%', 100)}%")

                    st.metric("Lotes Analizados", f"{cush_info.get('num_ciclos', 9)} lotes")

                    st.metric("Margen de Desviación", f"{cush_info.get('wape_%', 0):.2f}%")



                dais_info = por_flor_res.get('Daisy', {})

                with col_dais:

                    st.markdown("#### 🌼 Daisy")

                    st.metric("Peso Lotes Recientes", f"{dais_info.get('ponderacion_%', 100)}%")

                    st.metric("Lotes Analizados", f"{dais_info.get('num_ciclos', 9)} lotes")

                    st.metric("Margen de Desviación", f"{dais_info.get('wape_%', 0):.2f}%")



                nov_info = por_flor_res.get('Novelty', {})

                with col_nov:

                    st.markdown("#### 🌺 Novelty")

                    st.metric("Peso Lotes Recientes", f"{nov_info.get('ponderacion_%', 100)}%")

                    st.metric("Lotes Analizados", f"{nov_info.get('num_ciclos', 9)} lotes")

                    st.metric("Margen de Desviación", f"{nov_info.get('wape_%', 0):.2f}%")



                glob_info = info_res.get('global', {})

                with col_glob:

                    st.markdown("#### 🌐 Toda la Finca")

                    st.metric("Peso Lotes Recientes", f"{glob_info.get('ponderacion_%', 100)}%")

                    st.metric("Lotes Analizados", f"{glob_info.get('num_ciclos', 9)} lotes")

                    red_err = info_res.get('reduccion_error_%', 0)

                    st.metric("Margen de Desviación", f"{glob_info.get('wape_%', 0):.2f}%", f"-{red_err:.1f}% mejora frente al base")



                # Selector de Flor para explorar las curvas de convergencia

                st.divider()

                st.markdown(f"#### 📉 Evaluación del Ajuste Histórico ({tot_iter_ejecutada:,} Pruebas)")

                flor_chart_sel = st.radio(

                    "Ver comportamiento para:",

                    ["Todas las Flores (Comparativa)", "Cushion", "Daisy", "Novelty", "Toda la Finca"],

                    horizontal=True

                )



                df_chart_source = df_iteraciones.copy()

                if flor_chart_sel != "Todas las Flores (Comparativa)":

                    fl_filter_name = "Global" if flor_chart_sel == "Toda la Finca" else flor_chart_sel

                    df_chart_source = df_chart_source[df_chart_source['Flor'] == fl_filter_name]



                chart_iter = alt.Chart(df_chart_source).mark_circle(size=70).encode(

                    x=alt.X('ponderacion_%:Q', title='Peso de Lotes Recientes (%)'),

                    y=alt.Y('wape_%:Q', title='Margen de Desviación (%)', scale=alt.Scale(zero=False)),

                    color=alt.Color('Flor:N', title='Tipo de Flor', scale=alt.Scale(

                        domain=['Cushion', 'Daisy', 'Novelty', 'Global'],

                        range=['#0070F2', '#059669', '#D97706', '#7C3AED']

                    )),

                    tooltip=['Flor', 'iteracion', 'num_ciclos', 'ponderacion_%', 'wape_%', 'error_tallos']

                ).properties(height=340, title=f"Búsqueda del Menor Margen de Desviación ({flor_chart_sel})")



                st.altair_chart(chart_iter, width='stretch')



                # Tabla comparativa de variedades

                st.markdown("#### 🌿 Variedades con Mayor Ganancia en Precisión de Cosecha")

                df_mejora = df_detalle_ml.sort_values(by='Mejora_Tallos', ascending=False).copy()

                df_display_mejora = df_mejora.rename(columns={

                    'Real_Recepcionado': 'Flor Real Poscosecha',

                    'Estimado_Anterior': 'Proyección Anterior',

                    'Estimado_ML_Calibrado': 'Proyección Ajustada',

                    'Error_Anterior': 'Diferencia Anterior',

                    'Error_ML': 'Diferencia Ajustada',

                    'Mejora_Tallos': 'Tallos Ganados en Exactitud',

                    'Precision_Anterior_%': 'Certeza Anterior (%)',

                    'Precision_ML_%': 'Certeza Ajustada (%)'

                })

                st.dataframe(

                    df_display_mejora[[

                        'Flor', 'Color', 'Variedad', 'Flor Real Poscosecha',

                        'Proyección Anterior', 'Proyección Ajustada',

                        'Diferencia Anterior', 'Diferencia Ajustada', 'Tallos Ganados en Exactitud',

                        'Certeza Anterior (%)', 'Certeza Ajustada (%)'

                    ]],

                    width='stretch'

                )



    # =========================================================================

    # TAB 2: DATA LAKE DE EJECUCIONES (WEBFLOWERS PER4)

    # =========================================================================

    with tab2:

        st.subheader("Historial Central de Recepciones Poscosecha (PER4 - Webflowers)")

        st.markdown("""

        Este repositorio **acumula y preserva las recepciones reales de flor en poscosecha** registradas en Webflowers (Reporte PER4).

        Cada nuevo reporte de semana se integra sumando historia sin alterar las semanas previas.

        """)



        dl_c1, dl_c2, dl_c3, dl_c4 = st.columns(4)

        dl_c1.metric("Registros Históricos", f"{total_dl_reg:,}")

        dl_c2.metric("Semanas Acumuladas", f"{len(semanas_dl)} sem", f"{prim_sem} a {ult_sem}")

        dl_c3.metric("Variedades Monitoreadas", f"{vars_dl:,}")

        dl_c4.metric("Última Semana Cargada", f"S{ult_sem}")



        # Zona de Carga e Integración Continua al Data Lake

        st.divider()

        st.markdown("#### 📥 Integración Continua de Reportes Webflowers al Data Lake (PER4)")

        st.caption("Carga oficial de reportes PER4 (Estimados vs. Recepción) para mantener el historial permanentemente sincronizado.")

        

        file_default = "ReporteEstimadosVSRecepcion.xls"

        if "ver_uploader_wf_lake" not in st.session_state:

            st.session_state["ver_uploader_wf_lake"] = 0

        if "flash_lake_success" in st.session_state:

            st.success(st.session_state.pop("flash_lake_success"))



        col_up1, col_up2 = st.columns([1.5, 1])

        with col_up1:

            archivo_subido = st.file_uploader(

                "Subir Nuevo Reporte PER4 de Webflowers (.xls / .xlsx / .csv)",

                type=["xls", "xlsx", "csv"],

                key=f"uploader_wf_datalake_{st.session_state['ver_uploader_wf_lake']}",

                help="Sube el archivo PER4 descargado de Webflowers para integrarlo acumulativamente al histórico central."

            )

        with col_up2:

            st.markdown("**O sincronizar reporte local detectado:**")

            if os.path.exists(file_default):

                st.caption(f"📁 Detectado: `{file_default}`")

                if st.button("🔄 Sincronizar reporte PER4 local ('ReporteEstimadosVSRecepcion.xls')", type="secondary", width="stretch"):

                    try:

                        df_wf_raw = parse_webflowers_report(file_default)

                        df_dl, count_new, sem_af = integrar_reporte_al_datalake(df_wf_raw, db)

                        st.session_state["flash_lake_success"] = f"✅ ¡Historial PER4 actualizado! Se integraron {count_new} registros de la semana {sem_af}. Total en base: {len(df_dl):,} registros."

                        st.toast("✅ Reporte PER4 integrado con éxito.")

                        st.rerun()

                    except Exception as e:

                        st.error(f"Error sincronizando archivo: {e}")



        if archivo_subido is not None:

            try:

                df_wf_raw = parse_webflowers_report(archivo_subido)

                df_dl, count_new, sem_af = integrar_reporte_al_datalake(df_wf_raw, db)

                st.session_state["ver_uploader_wf_lake"] += 1

                st.session_state["flash_lake_success"] = f"✅ ¡Nuevo archivo PER4 integrado con éxito! {count_new} registros incorporados para las semanas {sem_af}. Total histórico: {len(df_dl):,} registros."

                st.toast("✅ Reporte PER4 integrado al Data Lake.")

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

        k1.metric("Flor Real Poscosecha", f"{tot_rec_sem:,.0f} tallos", f"Semana S{semana_activa}")

        k2.metric("Proyección Estimada", f"{tot_est_sem:,.0f} tallos" if tot_est_sem > 0 else "N/D (Histórico PER4)")

        k3.metric("Cumplimiento de Entrega", f"{bal_sem:.1f}%" if tot_est_sem > 0 else "Base Real")

        k4.metric("Diferencia Promedio", f"{wape_sem:.1f}%" if tot_est_sem > 0 else "N/A", f"{err_sem:,.0f} tallos diferencia" if tot_est_sem > 0 else None)



        # Gráfico comparativo de la semana si tiene estimaciones

        if tot_est_sem > 0:

            df_chart_sem = df_sem_view.head(15).melt(

                id_vars=['Variedad'],

                value_vars=['Real_Recepcionado', 'Estimado_Proyectado'],

                var_name='Tipo',

                value_name='Tallos'

            )

            df_chart_sem['Tipo_Label'] = df_chart_sem['Tipo'].map({

                'Real_Recepcionado': 'Flor Real Poscosecha',

                'Estimado_Proyectado': 'Proyección Estimada'

            })

            chart_sem = alt.Chart(df_chart_sem).mark_bar().encode(

                x=alt.X('Variedad:N', sort='-y', title='Variedad'),

                y=alt.Y('Tallos:Q', title='Tallos'),

                color=alt.Color('Tipo_Label:N', title='Categoría', scale=alt.Scale(

                    domain=['Flor Real Poscosecha', 'Proyección Estimada'], 

                    range=['#059669', '#0070F2']

                )),

                xOffset='Tipo_Label:N',

                tooltip=['Variedad', 'Tipo_Label', 'Tallos']

            ).properties(height=320, title=f"Top 15 Variedades Semana S{semana_activa}: Flor Real Poscosecha vs. Proyección Estimada")

            st.altair_chart(chart_sem, width='stretch')



        # Detalle de la semana en el Data Lake

        st.markdown(f"#### 📋 Registros Detallados Semana S{semana_activa}")

        df_sem_display = df_sem_view.rename(columns={

            'Real_Recepcionado': 'Flor Real Poscosecha',

            'Estimado_Proyectado': 'Proyección Estimada',

            'Balance_%': 'Cumplimiento (%)',

            'Fecha_Registro': 'Fecha de Carga'

        })

        st.dataframe(

            df_sem_display[[

                'Semana', 'Flor', 'Color', 'Variedad', 

                'Flor Real Poscosecha', 'Proyección Estimada', 'Cumplimiento (%)', 

                'Fuente', 'Fecha de Carga'

            ]],

            width='stretch'

        )



    # =========================================================================

    # TAB 3: TENDENCIAS HISTÓRICAS MULTI-CICLO (COMPARATIVO ENTRE AÑOS)

    # =========================================================================

    with tab3:

        st.subheader("📈 Comparativo Histórico de Recepciones entre Años")

        st.markdown("""

        Comparación de la flor real recibida en poscosecha semana a semana (semanas ISO 1 a 52) entre distintos años. 

        Permite identificar picos de producción, temporadas altas y patrones de volumen anual.

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

            st.caption(f"📁 **Historial PER4 Activo:** {len(df_dl):,} registros acumulados.")

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

                    title='Tallos Recibidos en Poscosecha', 

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

                    alt.Tooltip('Real_Recepcionado:Q', title='Tallos en Poscosecha', format=',.0f')

                ]

            ).properties(

                height=420,

                title=f"Comparativo de Recepción Real por Año: {', '.join(anios_detectados)} ({flor_sel_comp})"

            )



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

