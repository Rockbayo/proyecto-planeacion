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
    AREA_PRODUCTIVA_ANTERIOR_M2,
    FACTOR_AJUSTE_AREA,
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
    cruzando el plano de naves y camas (`Planos sección.csv`) contra el inventario vivo actual y el **Pedido Consolidado de Material Vegetal**.
    Permite auditar la capacidad real por bloque, nivelar picos estacionales (**San Valentín** y **Madres**) y resolver el desfase 
    por la reducción del área comercial de **64,878 m²** a **61,878 m²**.
    """)

    # 1. Cargar o Inicializar Datos de Capacidad
    inicializar_o_cargar_capacidad(db)
    df_estado_actual = obtener_estado_ocupacion_actual(db)

    # Métricas Globales
    df_comercial = df_estado_actual[df_estado_actual['Uso'] == 'Comercial']
    camas_com_tot = int(df_comercial['Camas_Capacidad'].sum())
    camas_com_occ = int(df_comercial['Camas_Ocupadas_Hoy'].sum())
    camas_com_lib = int(df_comercial['Camas_Libres_Hoy'].sum())
    lotes_com_tot = int(df_comercial['Lotes_Sembrados'].sum())
    camas_compartidas_tot = int(df_comercial['Camas_Compartidas'].sum())
    pct_com_occ = (camas_com_occ / camas_com_tot * 100.0) if camas_com_tot > 0 else 0.0

    area_com_tot = df_comercial['Area_Productiva_m2'].sum()
    area_com_occ = df_comercial['Area_Ocupada_m2'].sum()
    area_com_lib = df_comercial['Area_Libre_m2'].sum()

    # Banner Superior de Parámetros Maestros
    with st.container(border=True):
        st.markdown("#### 🎯 Parámetros Físicos Maestros y Capacidad Instalada")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Área Real Actual", f"{AREA_PRODUCTIVA_TOTAL_M2:,.0f} m²", f"-3,000 m² (-4.62%) vs {AREA_PRODUCTIVA_ANTERIOR_M2:,.0f} m²")
        c2.metric("Camas Comerciales", f"{camas_com_tot:,} camas", f"{AREA_PRODUCTIVA_TOTAL_M2/camas_com_tot:.2f} m²/cama bruta prom.")
        c3.metric("Meta Finca (Aprov.)", f"{META_TALLOS_M2_ANUAL:.0f} tallos/m²", f"~{AREA_PRODUCTIVA_TOTAL_M2 * META_TALLOS_M2_ANUAL / 1e6:.2f}M tallos/año")
        c4.metric("Rotación Promedio", f"{CICLOS_ANUALES_PROMEDIO:.1f} ciclos/año", "~14.9 sem / ciclo completo")

        st.caption(f"📏 **Dimensiones Cama según Planos:** Rango de **51.57 m² a 60.62 m² brutos/cama** (media {AREA_PRODUCTIVA_TOTAL_M2/camas_com_tot:.1f} m²). Era neta cultivable $\approx {AREA_NETA_CAMA_M2:.1f} \text{{ m}}^2$ ({ANCHO_CAMA_M:.2f} m $\\times$ {LARGO_CAMA_M:.1f} m). | Bloque **INV (Investigación):** 48 camas (2,835 m²) exclusivas para I+D y pruebas (excluidas del plan comercial).")

    # Pestañas del Módulo
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Diagnóstico Físico Actual de Bloques",
        "📈 Curva de Ocupación 52 Semanas (Cruzada con Pedido)",
        "⚖️ Balanceo Estacional & Plan de Ajuste de Área",
        "🗺️ Heatmap Espacial de Finca"
    ])

    # =========================================================================
    # TAB 1: DIAGNÓSTICO ACTUAL DE BLOQUES
    # =========================================================================
    with tab1:
        st.subheader("Estado Físico Actual de la Finca (Hoy)")
        st.markdown("""
        Evaluación de las **camas físicas reales** y área ocupada en campo por el inventario vivo actual frente a la capacidad instalada.
        La ocupación de camas físicas tiene un **tope estricto del 100%**, diferenciando entre camas físicas únicas y lotes sembrados (camas multivariedad).
        """)

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Camas Físicas Ocupadas", f"{camas_com_occ:,} camas", f"{pct_com_occ:.1f}% Ocupación Global")
        k2.metric("Camas Libres Disponibles", f"{camas_com_lib:,} camas", f"{(camas_com_lib/camas_com_tot*100):.1f}% Capacidad Libre Inmediata")
        k3.metric("Lotes Sembrados en Campo", f"{lotes_com_tot:,} lotes", f"{camas_compartidas_tot} camas multivariedad")
        k4.metric("Área Disponible Inmediata", f"{area_com_lib:,.0f} m²", "En Bloques 03 y 04")

        st.divider()
        st.markdown("#### 📋 Desglose Físico por Bloque (Planos Sección vs. Inventario Vivo)")

        df_show_blocks = df_estado_actual.copy()
        st.dataframe(
            df_show_blocks[[
                "Bloque", "Uso", "Naves", "Camas_Capacidad", 
                "Camas_Ocupadas_Hoy", "Camas_Libres_Hoy", "Ocupacion_%",
                "Lotes_Sembrados", "Camas_Compartidas",
                "m2_Por_Cama_Planos", "Area_Productiva_m2", "Area_Ocupada_m2", "Densidad_pl_m2"
            ]],
            column_config={
                "Ocupacion_%": st.column_config.ProgressColumn(
                    "Ocupación Física (%)",
                    format="%.1f%%",
                    min_value=0,
                    max_value=100
                ),
                "Camas_Capacidad": st.column_config.NumberColumn("Capacidad (Camas)", format="%d"),
                "Camas_Ocupadas_Hoy": st.column_config.NumberColumn("Camas Ocupadas", format="%d"),
                "Camas_Libres_Hoy": st.column_config.NumberColumn("Camas Libres", format="%d"),
                "Lotes_Sembrados": st.column_config.NumberColumn("Lotes Sembrados", format="%d", help="Cantidad de variedades/fracciones sembradas"),
                "Camas_Compartidas": st.column_config.NumberColumn("Camas Multivariedad", format="%d", help="Camas que albergan más de una variedad"),
                "m2_Por_Cama_Planos": st.column_config.NumberColumn("Área Cama Planos", format="%.2f m²", help="Área bruta física por cama según Planos sección"),
                "Area_Productiva_m2": st.column_config.NumberColumn("Área Bloque (m²)", format="%,.1f m²"),
                "Area_Ocupada_m2": st.column_config.NumberColumn("Área Ocupada (m²)", format="%,.1f m²"),
                "Densidad_pl_m2": st.column_config.NumberColumn("Densidad Real", format="%.1f pl/m²", help="Plantas sembradas por m² de era"),
            },
            width="stretch",
            hide_index=True
        )

        st.info("""
        💡 **Hallazgos Clave de Capacidad Física:**
        1. **Ningún bloque supera el 100% de ocupación física:** Los bloques **01, 02 y 05 están al 100%** (completamente sembrados) y el **Bloque 06 al 99%** (190 de 192 camas).
        2. **Camas Multivariedad (Diferencia entre Lotes y Camas):** Existen **82 camas** que albergan 2 o más variedades simultáneas (ej. en Bloque 01 hay 260 lotes en 240 camas físicas, con 20 camas compartidas). Esto explica por qué el conteo de lotes parecía superar las camas.
        3. **Variabilidad Real de Eras:** El área de cada cama varía entre **51.57 m²** (Bloque 06) y **60.62 m²** (Bloque 03) según los planos de la finca.
        4. **Disponibilidad Inmediata:** La finca cuenta hoy con **249 camas libres** disponibles para programar siembras, concentradas en el **Bloque 03 (134 camas)** y **Bloque 04 (113 camas)**.
        """)

    # =========================================================================
    # TAB 2: CURVA DE OCUPACIÓN 52 SEMANAS (CRUZADA CON PEDIDO)
    # =========================================================================
    with tab2:
        st.subheader("Proyección Dinámica de Ocupación a 52 Semanas")
        st.markdown("""
        Esta curva proyecta la ocupación temporal de camas semana a semana cruzando el **inventario vivo en campo** 
        (cosecha según curvas dinámicas + 1 semana de descanso post-corte) contra el **Pedido Consolidado de Material Vegetal**.
        """)

        df_52w, df_bloques_52w = calcular_ocupacion_semanal_52w(db)

        col_c1, col_c2 = st.columns([2, 1])
        with col_c1:
            modo_vista = st.radio(
                "Seleccionar Escenario de Proyección:",
                [
                    "Plan Ajustado a Capacidad Real (61,878 m²) [Recomendado - Dentro de Techo]",
                    "Plan Original Diseñado con 64,878 m² [Muestra Sobrecupo en Picos]",
                    "Comparativa Ambos Planes (Overlaid)"
                ],
                horizontal=True
            )

        with col_c2:
            bloques_opciones = ["Todos los Bloques Comerciales (01-06)"] + sorted(list(df_bloques_52w['Bloque'].unique()))
            sel_bloque = st.selectbox("Filtrar por Bloque:", bloques_opciones)

        # Preparación de datos para visualización
        techo_camas = CAMAS_COMERCIALES_TOTALES
        df_plot = df_52w.copy()

        # Techo Físico (Línea Roja)
        df_rule = pd.DataFrame([{'Techo': techo_camas}])
        rule_techo = alt.Chart(df_rule).mark_rule(color='#d62728', strokeDash=[6, 4], strokeWidth=2).encode(
            y='Techo:Q',
            tooltip=[alt.Tooltip('Techo:Q', title='Capacidad Máxima Comercial (1,168 Camas)')]
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

        base_chart = alt.Chart(df_plot).encode(
            x=alt.X('Semana_Num:N', title='Semana Operativa', axis=alt.Axis(labelAngle=-45))
        )

        if modo_vista == "Plan Ajustado a Capacidad Real (61,878 m²) [Recomendado - Dentro de Techo]":
            line_chart = base_chart.mark_line(point=True, color='#2ca02c', strokeWidth=2.5).encode(
                y=alt.Y('Camas_Ocupadas:Q', title='Camas Ocupadas (Plan Ajustado)', scale=alt.Scale(domain=[0, techo_camas * 1.15])),
                tooltip=['Semana:N', 'Temporada:N', 'Camas_Ocupadas:Q', 'Ocupacion_%:Q', 'Estado_Capacidad:N']
            )
            titulo_grafico = "Curva de Ocupación con Plan Ajustado a Capacidad Real (61,878 m² | 1,168 Camas)"
            chart_final = band_opt + line_chart + rule_techo

        elif modo_vista == "Plan Original Diseñado con 64,878 m² [Muestra Sobrecupo en Picos]":
            line_chart = base_chart.mark_line(point=True, color='#d62728', strokeWidth=2.5).encode(
                y=alt.Y('Camas_Plan_Original:Q', title='Camas Requeridas (Plan Original)', scale=alt.Scale(domain=[0, techo_camas * 1.15])),
                tooltip=['Semana:N', 'Temporada:N', 'Camas_Plan_Original:Q', 'Ocupacion_Original_%:Q', 'Estado_Capacidad:N']
            )
            titulo_grafico = "Curva de Ocupación con Plan Original (Base 64,878 m² - Evidencia Sobrecupo en Picos)"
            chart_final = band_opt + line_chart + rule_techo

        else: # Comparativa Ambos Planes
            line_orig = base_chart.mark_line(point=False, color='#d62728', strokeDash=[4, 3], strokeWidth=2.0).encode(
                y=alt.Y('Camas_Plan_Original:Q', title='Camas Requeridas', scale=alt.Scale(domain=[0, techo_camas * 1.15])),
                tooltip=['Semana:N', 'Temporada:N', alt.Tooltip('Camas_Plan_Original:Q', title='Plan Original (64k m²)'), 'Ocupacion_Original_%:Q']
            )
            line_adj = base_chart.mark_line(point=True, color='#1f77b4', strokeWidth=2.5).encode(
                y='Camas_Ocupadas:Q',
                tooltip=['Semana:N', 'Temporada:N', alt.Tooltip('Camas_Ocupadas:Q', title='Plan Ajustado (61k m²)'), 'Ocupacion_%:Q', 'Diferencia_Camas:Q']
            )
            titulo_grafico = "Comparativa: Plan Original (Rojo Discontinuo, 64k m²) vs. Plan Ajustado (Azul Sólido, 61k m²)"
            chart_final = band_opt + line_orig + line_adj + rule_techo

        chart_render = chart_final.properties(height=380, title=titulo_grafico)
        st.altair_chart(chart_render, width="stretch")

        st.caption("🔴 **Línea Roja Discontinua:** Techo físico infranqueable (1,168 camas). | 🟢 **Franja Verde Sombreada:** Rango óptimo de ocupación sostenida (85% a 95%).")

        # Alerta de Sobrecupo del Plan Original
        sems_sobrecupo = df_52w[df_52w['Ocupacion_Original_%'] > 100.0]
        if not sems_sobrecupo.empty:
            max_c_orig = sems_sobrecupo['Camas_Plan_Original'].max()
            max_pct_orig = sems_sobrecupo['Ocupacion_Original_%'].max()
            st.warning(f"""
            ⚠️ **Diagnóstico S&OP de Sobrecupo en Plan Anterior:**
            El Plan Original (formulado con **64,878 m²**) sobrepasa la capacidad física instalada en **{len(sems_sobrecupo)} semanas del año**, 
            alcanzando un pico máximo de **{max_c_orig:.0f} camas ({max_pct_orig:.1f}% de ocupación)** en la semana **S202706**.
            Al aplicar el factor de ajuste $\\times {FACTOR_AJUSTE_AREA:.5f}$ a los **61,878 m²**, el pico desciende exactamente a **{max_c_orig * FACTOR_AJUSTE_AREA:.0f} camas (97.9%)**, 
            eliminando por completo el sobrecupo y respetando las 1,168 camas comerciales.
            """)

        # Tabla Semanal Detallada
        with st.expander("📋 Ver Detalle Semana a Semana (52 Semanas) con Ajuste de Pedido", expanded=False):
            st.dataframe(
                df_52w[[
                    "Semana", "Temporada", "Camas_Ocupadas", "Ocupacion_%", 
                    "Camas_Plan_Original", "Ocupacion_Original_%",
                    "Diferencia_Camas", "Ahorro_Esquejes", "Estado_Capacidad"
                ]],
                column_config={
                    "Ocupacion_%": st.column_config.NumberColumn("Ocup. Ajustada (%)", format="%.1f%%"),
                    "Ocupacion_Original_%": st.column_config.NumberColumn("Ocup. Original (%)", format="%.1f%%"),
                    "Camas_Ocupadas": st.column_config.NumberColumn("Camas Ajustadas", format="%.1f"),
                    "Camas_Plan_Original": st.column_config.NumberColumn("Camas Originales", format="%.1f"),
                    "Diferencia_Camas": st.column_config.NumberColumn("Ajuste Camas", format="%.1f"),
                    "Ahorro_Esquejes": st.column_config.NumberColumn("Ajuste Esquejes Pedido", format="%,d"),
                },
                width="stretch",
                hide_index=True
            )

    # =========================================================================
    # TAB 3: BALANCEO ESTACIONAL & PLAN DE AJUSTE DE ÁREA
    # =========================================================================
    with tab3:
        st.subheader("Balanceo Estacional y Plan de Ajuste de Área (64,878 m² → 61,878 m²)")
        st.markdown("""
        Análisis de la utilización de la finca por temporada y hoja de ruta para **ajustar la producción que podemos entregar**, 
        alineando el Plan de Producción y el Pedido de Esquejes con el área real disponible.
        """)

        bal_info = calcular_balanceo_estacional(df_52w)
        kpis = bal_info['kpis_maestros']

        # Banner de Ajuste de Área
        with st.container(border=True):
            st.markdown("#### 📐 Impacto Matemático de la Disminución de Área")
            ca1, ca2, ca3, ca4 = st.columns(4)
            ca1.metric("Área Anterior vs Actual", f"{kpis['area_productiva_m2']:,.0f} m²", f"-3,000 m² (-{kpis['reduccion_pct']}%)")
            ca2.metric("Factor de Escalamiento", f"{kpis['factor_ajuste']:.5f}", "Multiplicador de corrección")
            ca3.metric("Ajuste Meta Finca (265 t/m²)", f"-{kpis['diferencia_tallos_meta']:,} tallos", f"de {kpis['meta_tallos_anual_anterior']/1e6:.2f}M a {kpis['meta_tallos_anual']/1e6:.2f}M")
            ca4.metric("Ajuste en Plan Asignado", f"-{kpis['diferencia_tallos_plan']:,} tallos", f"~150 a 170 camas menos año")

        st.divider()
        st.markdown("### 🛠️ Estrategias S&OP: ¿Cómo Ajustamos la Producción?")
        
        st.markdown("""
        Dado que el plan anterior fue formulado para 64,878 m², tenemos **3 alternativas operativas** para calzar la oferta con la capacidad real:
        """)

        op1, op2, op3 = st.columns(3)
        with op1:
            with st.container(border=True):
                st.markdown("#### 🔹 Opción A: Ajuste Proporcional Global (-4.62%)")
                st.markdown("""
                * **Mecanismo:** Aplicar el factor lineal **0.95376** sobre todas las semanas del pedido de esquejes y del plan de producción.
                * **Efecto:** Reduce exactamente **730,000 tallos** y **~830,000 esquejes** en el año.
                * **Ventaja:** Preserva el mix porcentual de variedades y colores (MVA) de los comités.
                * **Desventaja:** Recorta volumen en Summer donde ya hay camas vacías.
                """)
                st.button("Adoptar Opción A (Escalamiento Lineal)", key="btn_op_a", help="Aplica 0.95376 a todas las semanas")

        with op2:
            with st.container(border=True):
                st.markdown("#### 🔹 Opción B: Nivelación Quirúrgica en Picos (Recomendada)")
                st.markdown("""
                * **Mecanismo:** Mantener el plan intacto en semanas regulares y Summer, recortando o escalonando **únicamente en las semanas que superen el 95% de capacidad** (S202706 y S202750-52).
                * **Efecto:** Solo se ajustan **~50 a 80 camas** en semanas de picos.
                * **Ventaja:** No se pierde producción ni ingresos en semanas de valle donde sobra capacidad instalada.
                """)
                st.button("Adoptar Opción B (Ajuste Exclusivo en Picos)", key="btn_op_b")

        with op3:
            with st.container(border=True):
                st.markdown("#### 🔹 Opción C: Compensación por Densidad en Picos")
                st.markdown("""
                * **Mecanismo:** En vez de recortar tallos exportables, aumentar temporalmente la densidad de siembra en las camas de pico de **87 pl/m² a 91 pl/m²** (sumando ~200 plantas por cama).
                * **Efecto:** Se entrega el 100% de los tallos pedidos sin necesitar más camas físicas.
                * **Ventaja:** Cero pérdida de volumen comercial. Requiere monitoreo agronómico de calibre.
                """)
                st.button("Adoptar Opción C (Ajuste Vía Densidad)", key="btn_op_c")

        st.divider()
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
            * **Total Activo:** 752 camas (cubre el 95% del plan de verano con máxima eficiencia operativa).
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

        df_heat = df_bloques_52w.copy()
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
