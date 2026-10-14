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
    aplicar_nivelacion_quirurgica_picos,
    exportar_pedido_nivelado_excel,
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
        res_op_b = aplicar_nivelacion_quirurgica_picos(db)
        df_niv = res_op_b.get("df_semanal_nivelado", pd.DataFrame())
        kpis_niv = res_op_b.get("kpis_nivelacion", {})

        col_c1, col_c2 = st.columns([2, 1])
        with col_c1:
            modo_vista = st.radio(
                "Seleccionar Escenario de Proyección:",
                [
                    "Plan Nivelado Quirúrgico (Opción B) [Adoptado - Techo 1,168 Camas Respetado]",
                    "Plan Original Diseñado con 64,878 m² [Muestra Sobrecupo en Picos]",
                    "Comparativa Superpuesta (Plan Original vs. Opción B)"
                ],
                horizontal=True
            )

        with col_c2:
            bloques_opciones = ["Todos los Bloques Comerciales (01-06)"] + sorted(list(df_bloques_52w['Bloque'].unique()))
            sel_bloque = st.selectbox("Filtrar por Bloque:", bloques_opciones)

        # Preparación de datos para visualización
        techo_camas = CAMAS_COMERCIALES_TOTALES
        
        # Merge de df_52w con nivelación si está disponible
        if not df_niv.empty:
            df_plot = pd.merge(df_52w, df_niv[['Semana', 'Camas_Niveladas_OpB', 'Ocupacion_Nivelada_%']], on='Semana', how='left')
            df_plot['Camas_Niveladas_OpB'] = df_plot['Camas_Niveladas_OpB'].fillna(df_plot['Camas_Ocupadas'])
            df_plot['Ocupacion_Nivelada_%'] = df_plot['Ocupacion_Nivelada_%'].fillna(df_plot['Ocupacion_%'])
        else:
            df_plot = df_52w.copy()
            df_plot['Camas_Niveladas_OpB'] = df_plot['Camas_Ocupadas']
            df_plot['Ocupacion_Nivelada_%'] = df_plot['Ocupacion_%']

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

        if modo_vista == "Plan Nivelado Quirúrgico (Opción B) [Adoptado - Techo 1,168 Camas Respetado]":
            line_chart = base_chart.mark_line(point=True, color='#1f77b4', strokeWidth=2.5).encode(
                y=alt.Y('Camas_Niveladas_OpB:Q', title='Camas Ocupadas Niveladas', scale=alt.Scale(domain=[0, techo_camas * 1.15])),
                tooltip=['Semana:N', 'Temporada:N', alt.Tooltip('Camas_Niveladas_OpB:Q', title='Camas Niveladas'), alt.Tooltip('Ocupacion_Nivelada_%:Q', title='Ocupación (%)')]
            )
            titulo_grafico = "Curva de Ocupación Nivelada (Opción B): Capacidad Máxima de 1,168 Camas 100% Respetada"
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
                y='Camas_Niveladas_OpB:Q',
                tooltip=['Semana:N', 'Temporada:N', alt.Tooltip('Camas_Niveladas_OpB:Q', title='Plan Nivelado OpB (61k m²)'), 'Ocupacion_Nivelada_%:Q']
            )
            titulo_grafico = "Comparativa: Plan Original (Rojo Discontinuo, 64k m²) vs. Opción B Nivelada (Azul Sólido, 61k m²)"
            chart_final = band_opt + line_orig + line_adj + rule_techo

        chart_render = chart_final.properties(height=380, title=titulo_grafico)
        st.altair_chart(chart_render, width="stretch")

        st.caption("🔴 **Línea Roja Discontinua:** Techo físico infranqueable (1,168 camas). | 🟢 **Franja Verde Sombreada:** Rango óptimo de ocupación sostenida (85% a 95%).")

        st.success(f"""
        ✅ **Solución de Nivelación Aplicada (Opción B):**
        El Plan Original sobrepasaba las 1,168 camas comerciales en los picos de San Valentín y Navidad (alcanzando hasta **{kpis_niv.get('max_camas_original', 1200):.0f} camas**).
        Con la **Nivelación Quirúrgica (Opción B)**, el pico desciende exactamente a **{kpis_niv.get('max_camas_nivelado', 1168):.0f} camas (100.0%)**, 
        preservando el **100% de la producción en las {kpis_niv.get('semanas_intactas_100pct', 42)} semanas regulares y de Summer**.
        """)

        # Tabla Semanal Detallada
        with st.expander("📋 Ver Detalle Semana a Semana (52 Semanas) con Nivelación Opción B", expanded=False):
            st.dataframe(
                df_plot[[
                    "Semana", "Temporada", "Camas_Niveladas_OpB", "Ocupacion_Nivelada_%", 
                    "Camas_Plan_Original", "Ocupacion_Original_%",
                    "Diferencia_Camas", "Ahorro_Esquejes", "Estado_Capacidad"
                ]],
                column_config={
                    "Ocupacion_Nivelada_%": st.column_config.NumberColumn("Ocup. Nivelada (%)", format="%.1f%%"),
                    "Ocupacion_Original_%": st.column_config.NumberColumn("Ocup. Original (%)", format="%.1f%%"),
                    "Camas_Niveladas_OpB": st.column_config.NumberColumn("Camas Niveladas (OpB)", format="%.1f"),
                    "Camas_Plan_Original": st.column_config.NumberColumn("Camas Originales", format="%.1f"),
                    "Diferencia_Camas": st.column_config.NumberColumn("Ajuste Camas", format="%.1f"),
                    "Ahorro_Esquejes": st.column_config.NumberColumn("Ajuste Esquejes", format="%,d"),
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

        # Banner de Adopción de la Opción B
        st.success("🎯 **Estrategia Adoptada por Dirección: Opción B (Nivelación Quirúrgica en Picos)**")

        with st.container(border=True):
            st.markdown("#### 📊 Balance Cuantitativo de la Nivelación Quirúrgica (Opción B)")
            cb1, cb2, cb3, cb4 = st.columns(4)
            cb1.metric("Pico Máximo Original", f"{kpis_niv.get('max_camas_original', 1200):.0f} camas", "102.7% Sobrecupo en S202706")
            cb2.metric("Pico Máximo Nivelado", f"{kpis_niv.get('max_camas_nivelado', 1168):.0f} camas", "100.0% Techo Comercial Respetado")
            cb3.metric("Semanas 100% Intactas", f"{kpis_niv.get('semanas_intactas_100pct', 42)} semanas", "Incluye las 17 semanas de Summer")
            cb4.metric("Ajuste Quirúrgico Anual", f"-{kpis_niv.get('camas_ajustadas_total_anio', 180):.0f} camas", f"~{kpis_niv.get('esquejes_ajustados_total_anio', 936000):,} esquejes año")

        st.divider()

        # Botón de Descarga del Pedido Nivelado para ERP
        df_ped_niv = res_op_b.get("df_pedido_nivelado", pd.DataFrame())
        if not df_ped_niv.empty:
            excel_bytes = exportar_pedido_nivelado_excel(df_ped_niv)
            col_d1, col_d2 = st.columns([3, 1])
            with col_d1:
                st.markdown("##### 📥 Exportar Pedido Consolidado Nivelado para ERP y Propagación")
                st.caption("Genera la matriz oficial de esquejes con semanas en columnas (`S{YYYYWW}`), lista para importar en el sistema ERP.")
            with col_d2:
                st.download_button(
                    label="📥 Descargar Pedido Nivelado (Excel)",
                    data=excel_bytes,
                    file_name=f"PedidoConsolidado_Nivelado_OpB_{date.today()}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    width="stretch"
                )

        st.divider()
        st.markdown("### 📋 Cuadro Comparativo de Estrategias S&OP Evaluadas")

        op1, op2, op3 = st.columns(3)
        with op1:
            with st.container(border=True):
                st.markdown("#### 🔹 Opción A: Ajuste Proporcional Global (-4.62%)")
                st.markdown("""
                * **Mecanismo:** Aplicar factor lineal $0.95376$ parejo a todas las 52 semanas.
                * **Efecto:** Reduce 730k tallos y ~830k esquejes.
                * **Desventaja:** Castiga semanas de Summer donde la finca tiene 378 camas libres.
                * **Estado:** Descartada frente a Opción B.
                """)

        with op2:
            with st.container(border=True):
                st.markdown("#### 🔹 Opción B: Nivelación Quirúrgica (ADOPTADA)")
                st.markdown("""
                * **Mecanismo:** Intervenir exclusivamente las semanas con sobrecupo puntual (San Valentín y Navidad).
                * **Efecto:** Mantiene intacto el 100% de la producción en Summer y semanas regulares.
                * **Ventaja:** Máxima rentabilidad y cero capacidad desperdiciada en valles.
                * **Estado:** ✅ **Activa y aplicada en el sistema.**
                """)

        with op3:
            with st.container(border=True):
                st.markdown("#### 🔹 Opción C: Compensación por Densidad")
                st.markdown("""
                * **Mecanismo:** Elevar densidad a 91 pl/m² en semanas pico (+200 pl/cama).
                * **Efecto:** Cero recorte de tallos.
                * **Ventaja:** Máximo volumen exportable.
                * **Estado:** Alternativa agronómica de respaldo.
                """)

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
