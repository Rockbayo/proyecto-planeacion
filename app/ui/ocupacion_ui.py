import streamlit as st
import pandas as pd
import os
import altair as alt
from datetime import date
from app.services.ocupacion_service import (
    inicializar_o_cargar_capacidad,
    obtener_estado_ocupacion_actual,
    calcular_ocupacion_semanal_52w,
    calcular_balanceo_estacional,
    AREA_PRODUCTIVA_TOTAL_M2,
    CAMAS_COMERCIALES_TOTALES,
    CAMAS_INV_TOTALES,
    CAMAS_TOTALES_INSTALADAS,
    META_TALLOS_M2_ANUAL,
    CICLOS_ANUALES_PROMEDIO,
    ANCHO_CAMA_M,
    LARGO_CAMA_M,
    AREA_NETA_CAMA_M2
)

def render_ocupacion_module(db):
    st.header("🏢 Ocupación de Área y Capacidad de Finca (S&OP)")
    st.markdown("""
    Este módulo modela la **capacidad física instalada y la ocupación temporal de la finca** a lo largo de las 52 semanas del año,
    cruzando el plano de naves y camas (`Planos sección.csv`) contra el inventario vivo y los planes de temporada. 
    Permite nivelar picos estacionales (**San Valentín** y **Madres**) y optimizar costos en valles de baja demanda (**Summer**).
    """)

    # 1. Cargar o Inicializar Datos de Capacidad
    inicializar_o_cargar_capacidad(db)
    df_estado_actual = obtener_estado_ocupacion_actual(db)

    # Métricas Globales
    df_comercial = df_estado_actual[df_estado_actual['Uso'] == 'Comercial']
    camas_com_tot = df_comercial['Camas_Capacidad'].sum()
    camas_com_occ = df_comercial['Camas_Ocupadas_Hoy'].sum()
    camas_com_lib = df_comercial['Camas_Libres_Hoy'].sum()
    pct_com_occ = (camas_com_occ / camas_com_tot * 100.0) if camas_com_tot > 0 else 0.0

    area_com_tot = df_comercial['Area_Productiva_m2'].sum()
    area_com_occ = df_comercial['Area_Ocupada_m2'].sum()
    area_com_lib = df_comercial['Area_Libre_m2'].sum()

    # Banner Superior de Parámetros Maestros
    with st.container(border=True):
        st.markdown("#### 🎯 Parámetros Maestros de Productividad y Capacidad de la Finca")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Área Real Productiva", f"{area_com_tot:,.0f} m²", "Bloques 01 al 06")
        c2.metric("Camas Comerciales", f"{camas_com_tot:,} camas", f"{area_com_tot/camas_com_tot:.1f} m²/cama bruta")
        c3.metric("Meta Finca (Aprov.)", f"{META_TALLOS_M2_ANUAL:.0f} tallos/m²", f"~{area_com_tot * META_TALLOS_M2_ANUAL / 1e6:.1f}M tallos/año")
        c4.metric("Rotación Promedio", f"{CICLOS_ANUALES_PROMEDIO:.1f} ciclos/año", "~14.9 sem / ciclo completo")

        st.caption(f"📏 **Dimensiones Cama Promedio:** {ANCHO_CAMA_M:.2f} m (ancho) x {LARGO_CAMA_M:.1f} m (largo) = **{AREA_NETA_CAMA_M2:.1f} m² netos de era**. | Bloque **INV (Investigación):** 48 camas (2,835 m²) exclusivas para I+D y pruebas.")

    # Pestañas del Módulo
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Diagnóstico Actual de Bloques",
        "📈 Curva de Ocupación 52 Semanas",
        "⚖️ Balanceo Estacional & Optimización (Summer vs Picos)",
        "🗺️ Heatmap Espacial de Finca"
    ])

    # =========================================================================
    # TAB 1: DIAGNÓSTICO ACTUAL DE BLOQUES
    # =========================================================================
    with tab1:
        st.subheader("Estado Físico Actual de la Finca (Hoy)")
        st.markdown("""
        Comparación de las camas y área física ocupadas hoy en campo por el inventario vivo actual frente a la capacidad instalada de cada bloque.
        """)

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Camas Ocupadas Hoy", f"{camas_com_occ:,} camas", f"{pct_com_occ:.1f}% Ocupación")
        k2.metric("Camas Libres Disponibles", f"{camas_com_lib:,} camas", f"{(camas_com_lib/camas_com_tot*100):.1f}% Capacidad Libre")
        k3.metric("Área Ocupada Hoy", f"{area_com_occ:,.0f} m²", f"de {area_com_tot:,.0f} m²")
        k4.metric("Área Libre Disponible", f"{area_com_lib:,.0f} m²", "Lista para siembra")

        st.divider()
        st.markdown("#### 📋 Desglose Físico por Bloque (Capacidad vs. Ocupación Real)")

        df_show_blocks = df_estado_actual.copy()
        st.dataframe(
            df_show_blocks[[
                "Bloque", "Uso", "Naves", "Camas_Capacidad", 
                "Camas_Ocupadas_Hoy", "Camas_Libres_Hoy", "Ocupacion_%",
                "Area_Productiva_m2", "Area_Ocupada_m2", "Area_Libre_m2"
            ]],
            column_config={
                "Ocupacion_%": st.column_config.ProgressColumn(
                    "Ocupación (%)",
                    format="%.1f%%",
                    min_value=0,
                    max_value=100
                ),
                "Area_Productiva_m2": st.column_config.NumberColumn("Área Productiva (m²)", format="%,.1f m²"),
                "Area_Ocupada_m2": st.column_config.NumberColumn("Área Ocupada (m²)", format="%,.1f m²"),
                "Area_Libre_m2": st.column_config.NumberColumn("Área Libre (m²)", format="%,.1f m²"),
            },
            width="stretch",
            hide_index=True
        )

        st.info("💡 **Disponibilidad Inmediata:** Los bloques **01, 02, 05 y 06 están al 100% de ocupación**. La disponibilidad inmediata para programar nuevas siembras se concentra en los **Bloques 03 y 04**.")

    # =========================================================================
    # TAB 2: CURVA DE OCUPACIÓN 52 SEMANAS
    # =========================================================================
    with tab2:
        st.subheader("Proyección Dinámica de Ocupación a 52 Semanas")
        st.markdown("""
        Esta curva proyecta la ocupación de camas semana a semana a medida que el inventario vivo se cosecha (y descansa 1 semana) 
        y se incorporan las siembras futuras requeridas por el Plan de Producción.
        """)

        df_52w, df_bloques_52w = calcular_ocupacion_semanal_52w(db)

        col_f1, col_f2 = st.columns([2, 1])
        with col_f1:
            bloques_opciones = ["Todos los Bloques Comerciales (01-06)"] + sorted(list(df_bloques_52w['Bloque'].unique()))
            sel_bloque = st.selectbox("Filtrar Curva por Bloque:", bloques_opciones)

        # Gráfico de Camas Ocupadas vs Techo Físico
        if sel_bloque == "Todos los Bloques Comerciales (01-06)":
            df_plot_52 = df_52w.copy()
            techo_camas = CAMAS_COMERCIALES_TOTALES
            titulo_grafico = "Ocupación Total Finca Comercial: Camas Ocupadas vs. Techo Máximo (1,168 Camas)"
        else:
            df_sub_b = df_bloques_52w[df_bloques_52w['Bloque'] == sel_bloque]
            df_plot_52 = pd.merge(df_52w[['Semana', 'Temporada', 'Semana_Num']], df_sub_b, on='Semana')
            cap_b = df_estado_actual[df_estado_actual['Bloque'] == sel_bloque]['Camas_Capacidad'].values[0]
            techo_camas = float(cap_b)
            titulo_grafico = f"Ocupación Bloque {sel_bloque}: Camas Ocupadas vs. Capacidad ({techo_camas:.0f} Camas)"

        # Línea de Camas Ocupadas
        base_chart = alt.Chart(df_plot_52).encode(
            x=alt.X('Semana_Num:N', title='Semana Operativa', axis=alt.Axis(labelAngle=-45))
        )

        line_occ = base_chart.mark_line(point=True, color='#1f77b4', strokeWidth=2.5).encode(
            y=alt.Y('Camas_Ocupadas:Q', title='Camas Ocupadas', scale=alt.Scale(domain=[0, techo_camas * 1.15])),
            tooltip=['Semana:N', 'Temporada:N', 'Camas_Ocupadas:Q']
        )

        # Línea de Techo Físico (Capacidad Máxima)
        df_rule = pd.DataFrame([{'Techo': techo_camas}])
        rule_techo = alt.Chart(df_rule).mark_rule(color='#d62728', strokeDash=[6, 4], strokeWidth=2).encode(
            y='Techo:Q',
            tooltip=[alt.Tooltip('Techo:Q', title='Capacidad Máxima Física')]
        )

        # Franja Óptima (85% a 95%)
        df_band = pd.DataFrame([{
            'min_opt': techo_camas * 0.85,
            'max_opt': techo_camas * 0.95
        }])
        band_opt = alt.Chart(df_band).mark_rect(opacity=0.15, color='#2ca02c').encode(
            y='min_opt:Q',
            y2='max_opt:Q'
        )

        chart_final = (band_opt + line_occ + rule_techo).properties(
            height=380,
            title=titulo_grafico
        )
        st.altair_chart(chart_final, width="stretch")

        st.caption("🔴 **Línea Roja Discontinua:** Techo físico infranqueable (100% capacidad). | 🟢 **Franja Verde Sombreada:** Rango óptimo de ocupación sostenida (85% a 95%).")

        # Tabla Semanal
        with st.expander("📋 Ver Detalle Semana a Semana (52 Semanas)", expanded=False):
            st.dataframe(
                df_52w[[
                    "Semana", "Temporada", "Camas_Ocupadas", "Camas_Libres", 
                    "Ocupacion_%", "Area_Ocupada_m2", "Area_Libre_m2", "Estado_Capacidad"
                ]],
                width="stretch",
                hide_index=True
            )

    # =========================================================================
    # TAB 3: BALANCEO ESTACIONAL & OPTIMIZACIÓN (SUMMER VS PICOS)
    # =========================================================================
    with tab3:
        st.subheader("Balanceo Estacional y Diagnóstico de Temporadas")
        st.markdown("""
        Análisis comparativo de la utilización de la finca por temporada. Permite identificar los **picos de sobrecupo** 
        (San Valentín y Madres) y gestionar el **valle de baja demanda** de Summer.
        """)

        bal_info = calcular_balanceo_estacional(df_52w)
        df_temp = bal_info['df_temporadas']

        st.markdown("#### 📊 Desempeño y Ocupación por Temporada")
        st.dataframe(
            df_temp[[
                "Temporada", "Semanas_Duracion", "Camas_Ocupadas_Prom", 
                "Camas_Libres_Prom", "Ocupacion_%", "Area_Ocupada_m2", "Area_Libre_m2"
            ]],
            column_config={
                "Ocupacion_%": st.column_config.ProgressColumn(
                    "Ocupación Media (%)",
                    format="%.1f%%",
                    min_value=0,
                    max_value=100
                ),
                "Area_Ocupada_m2": st.column_config.NumberColumn("Área Ocupada Promedio", format="%,.0f m²"),
                "Area_Libre_m2": st.column_config.NumberColumn("Área Libre Promedio", format="%,.0f m²"),
            },
            width="stretch",
            hide_index=True
        )

        st.divider()
        st.markdown("### 🛠️ Estrategias de Optimización Recomendadas")

        recs = bal_info['recomendaciones']
        for r in recs:
            with st.container(border=True):
                st.markdown(f"#### 📌 {r['Tipo']}")
                st.markdown(f"**Diagnóstico:** {r['Diagnostico']}")
                st.success(f"**Acción Óptima S&OP:** {r['Accion_Optima']}")

        with st.container(border=True):
            st.markdown("#### 💡 Simulación de Parada Programada de Bloques en Summer (Ahorro Operativo)")
            st.markdown("""
            Durante las 17 semanas de Summer, la demanda requiere solo **~750 a 790 camas ocupadas** de las 1,168 comerciales.
            En vez de tener 378 camas vacías salpicadas en los 6 bloques, la configuración óptima es:
            """)
            c_s1, c_s2 = st.columns(2)
            with c_s1:
                st.success("""
                **Bloques Activos al 100% en Summer (752 Camas):**
                * Bloque 01: 240 camas
                * Bloque 02: 160 camas
                * Bloque 05: 160 camas
                * Bloque 06: 192 camas
                * **Total Activo:** 752 camas (cubre el 95% del plan de verano).
                """)
            with c_s2:
                st.info("""
                **Bloques en Parada y Mantenimiento Mayor (416 Camas):**
                * Bloque 03: 184 camas (11,155 m²)
                * Bloque 04: 232 camas (12,744 m²)
                * **Total en Descanso:** 416 camas (~23,899 m²).
                * **Ahorro:** Apagado de iluminación fotoperíodo, ahorro de agua y ventana para solarización profunda de suelos.
                """)

    # =========================================================================
    # TAB 4: HEATMAP ESPACIAL DE FINCA
    # =========================================================================
    with tab4:
        st.subheader("Mapa Espacial de Ocupación por Bloque (Matriz Gantt de Finca)")
        st.markdown("""
        Visualiza el nivel de ocupación de cada bloque a lo largo de las semanas para programar exactamente 
        en qué bloque y nave se ubicará cada ciclo de siembra.
        """)

        # Heatmap con Altair
        df_heat = df_bloques_52w.copy()
        
        # Merge con capacidad de cada bloque para sacar porcentaje
        cap_dict = {r['Bloque']: r['Camas_Capacidad'] for _, r in df_estado_actual.iterrows()}
        df_heat['Capacidad'] = df_heat['Bloque'].map(cap_dict).fillna(1)
        df_heat['Ocupacion_%'] = (df_heat['Camas_Ocupadas'] / df_heat['Capacidad'] * 100.0).round(1)

        heat_chart = alt.Chart(df_heat).mark_rect().encode(
            x=alt.X('Semana:N', title='Semana Operativa', axis=alt.Axis(labelAngle=-45)),
            y=alt.Y('Bloque:N', title='Bloque de la Finca', sort=['INV', '01', '02', '03', '04', '05', '06']),
            color=alt.Color('Ocupacion_%:Q', title='Ocupación (%)', scale=alt.Scale(
                scheme='greens',
                domain=[0, 100]
            )),
            tooltip=['Bloque:N', 'Semana:N', 'Camas_Ocupadas:Q', 'Ocupacion_%:Q']
        ).properties(
            height=320,
            title="Matriz de Ocupación Espacial: Bloques vs. Semanas"
        )

        st.altair_chart(heat_chart, width="stretch")
        st.caption("Verde oscuro = Bloque con alta ocupación (85-100%). Verde claro = Bloque con camas libres disponibles para nuevas siembras.")
