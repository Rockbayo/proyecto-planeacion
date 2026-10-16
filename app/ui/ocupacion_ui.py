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
    SEMANA_CORTE_REDUCCION_AREA,
    AREA_PRODUCTIVA_ACTUAL_M2,
    AREA_PRODUCTIVA_REDUCIDA_M2,
    AREA_PRODUCTIVA_TOTAL_M2,
    AREA_PRODUCTIVA_ANTERIOR_M2,
    FACTOR_AJUSTE_AREA,
    CAMAS_COMERCIALES_TOTALES,
    CAMAS_INV_TOTALES,
    CAMAS_TOTALES_INSTALADAS,
    CAPACIDAD_BLOQUES,
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
    Permite auditar la capacidad real por bloque, proyectar la utilización de camas en temporadas clave (**San Valentín** y **Madres**) y 
    monitorear el cronograma de transición de área a **61,878 m²**.
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
        st.markdown("#### 🎯 Parámetros Físicos Maestros y Cronograma de Capacidad")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Área Real Vigente Hoy", f"{AREA_PRODUCTIVA_ACTUAL_M2:,.0f} m²", f"61,878 m² a partir de S{SEMANA_CORTE_REDUCCION_AREA}")
        c2.metric("Camas Comerciales", f"{camas_com_tot:,} camas", f"{AREA_PRODUCTIVA_ACTUAL_M2/camas_com_tot:.2f} m²/cama hoy")
        c3.metric("Meta Finca (Aprov.)", f"{META_TALLOS_M2_ANUAL:.0f} tallos/m²", f"~{AREA_PRODUCTIVA_ACTUAL_M2 * META_TALLOS_M2_ANUAL / 1e6:.2f}M tallos/año")
        c4.metric("Rotación Promedio", f"{CICLOS_ANUALES_PROMEDIO:.1f} ciclos/año", "~14.9 sem / ciclo completo")

        st.caption(f"📏 **Cronograma de Transición:** En este momento el área es de **64,878 m²**; a partir de la **Semana 2648** se reduce a **61,878 m²** (-3,000 m², -4.62%). | Camas de 51.57 m² a 60.62 m² brutos. | Bloque **INV (Investigación):** 48 camas (2,835 m²) exclusivas para I+D (excluidas del plan comercial).")

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
        💡 **Capacidad Física y Disponibilidad Operativa:**
        1. **Distribución de Ocupación por Bloque:** Los bloques **01, 02 y 05** se encuentran al 100% de ocupación en suelo, y el **Bloque 06** al 99% (190 de 192 camas).
        2. **Camas Multivariedad:** Existen **82 camas** compartidas que albergan 2 o más variedades simultáneas optimizando el área productiva.
        3. **Variabilidad de Eras:** El área promedio de cama varía entre **51.57 m²** (Bloque 06) y **60.62 m²** (Bloque 03) según los planos oficiales de la finca.
        4. **Disponibilidad Inmediata:** La finca cuenta hoy con **249 camas libres** disponibles para programación de siembras, concentradas en el **Bloque 03 (134 camas)** y **Bloque 04 (113 camas)**.
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
        res_op_b = aplicar_nivelacion_quirurgica_picos(db, df_52w=df_52w)
        df_niv = res_op_b.get("df_semanal_nivelado", pd.DataFrame())
        kpis_niv = res_op_b.get("kpis_nivelacion", {})

        col_c1, col_c2 = st.columns([2, 1])
        with col_c1:
            modo_vista = st.radio(
                "Seleccionar Escenario de Proyección:",
                [
                    "Plan Operativo Vigente",
                    "Plan Base (Referencia)",
                    "Comparativa de Planes"
                ],
                horizontal=True
            )

        with col_c2:
            bloques_disponibles = sorted([b for b in df_bloques_52w['Bloque'].unique() if b != 'INV'])
            bloques_opciones = ["Todos los Bloques Comerciales (01-06)"] + bloques_disponibles + ["INV"]
            sel_bloque = st.selectbox("Filtrar por Bloque:", bloques_opciones)

        # Preparación de datos para visualización
        es_todos = sel_bloque.startswith("Todos")
        
        if es_todos:
            # Vista Global de Finca
            techo_camas = CAMAS_COMERCIALES_TOTALES
            techo_reducido = CAMAS_COMERCIALES_TOTALES - 100.0  # ~1,068 camas
            bloque_subtitulo = "Toda la Finca (1,168 Camas Comerciales)"

            # Merge de df_52w con nivelación si está disponible
            if not df_niv.empty:
                df_plot = pd.merge(df_52w, df_niv[['Semana', 'Camas_Niveladas_OpB', 'Ocupacion_Nivelada_%']], on='Semana', how='left')
                df_plot['Camas_Niveladas_OpB'] = df_plot['Camas_Niveladas_OpB'].fillna(df_plot['Camas_Ocupadas'])
                df_plot['Camas_Niveladas_OpB'] = df_plot[['Camas_Ocupadas', 'Camas_Niveladas_OpB']].max(axis=1)
                df_plot['Ocupacion_Nivelada_%'] = ((df_plot['Camas_Niveladas_OpB'] / CAMAS_COMERCIALES_TOTALES) * 100.0).round(1)
            else:
                df_plot = df_52w.copy()
                df_plot['Camas_Niveladas_OpB'] = df_plot['Camas_Ocupadas']
                df_plot['Ocupacion_Nivelada_%'] = df_plot['Ocupacion_%']
        else:
            # Vista Filtrada por Bloque Específico
            cap_b = CAPACIDAD_BLOQUES.get(sel_bloque, 240.0)
            techo_camas = cap_b
            if sel_bloque == 'INV':
                techo_reducido = cap_b
            else:
                techo_reducido = round(cap_b * ((CAMAS_COMERCIALES_TOTALES - 100.0) / CAMAS_COMERCIALES_TOTALES), 1)
            bloque_subtitulo = f"Bloque {sel_bloque} (Capacidad: {int(techo_camas)} Camas)"

            df_plot = df_bloques_52w[df_bloques_52w['Bloque'] == sel_bloque].copy()

        if 'Semana_Label' not in df_plot.columns:
            df_plot['Semana_Label'] = df_plot['Semana'].apply(lambda s: f"S{str(s)[2:]}")

        orden_cronologico = list(df_plot['Semana_Label'].unique())

        # 1. Techo Físico Instalado (Línea Roja Corporativa Discontinua)
        df_rule_inst = pd.DataFrame([{'Techo_Instalado': techo_camas}])
        rule_techo_inst = alt.Chart(df_rule_inst).mark_rule(
            color='#DC2626', 
            strokeDash=[6, 4], 
            strokeWidth=2.2
        ).encode(
            y='Techo_Instalado:Q',
            tooltip=[alt.Tooltip('Techo_Instalado:Q', title=f'Capacidad Instalada ({int(techo_camas)} Camas)')]
        )

        # 2. Techo Post-Reducción de Área (Línea Naranja Corporativa Discontinua: ~100 camas descontadas)
        df_rule_red = pd.DataFrame([{'Techo_Reducido': techo_reducido}])
        rule_techo_red = alt.Chart(df_rule_red).mark_rule(
            color='#EA580C', 
            strokeDash=[4, 4], 
            strokeWidth=2
        ).encode(
            y='Techo_Reducido:Q',
            tooltip=[alt.Tooltip('Techo_Reducido:Q', title=f'Capacidad Post-Reducción ({techo_reducido:.1f} Camas, -100 Camas Finca)')]
        )

        # 3. Franja Óptima (85% a 95% - Verde Esmeralda S&OP)
        df_band = pd.DataFrame([{
            'min_opt': techo_camas * 0.85,
            'max_opt': techo_camas * 0.95
        }])
        band_opt = alt.Chart(df_band).mark_rect(opacity=0.15, color='#059669').encode(
            y='min_opt:Q',
            y2='max_opt:Q'
        )

        base_chart = alt.Chart(df_plot).encode(
            x=alt.X('Semana_Label:N', sort=orden_cronologico, title='Semana Operativa (Cronológica)', axis=alt.Axis(labelAngle=-45))
        )

        if modo_vista == "Plan Operativo Vigente":
            # Checkbox opcional para incluir Ocupación Total en Suelo
            mostrar_total = st.checkbox("Mostrar además curva de Ocupación Total en Suelo (Vivo + Siembras)", value=False, key="chk_occ_total")
            
            lineas_a_graficar = ['Camas_Inventario_Vivo', 'Camas_Siembras_Futuras']
            mapa_nombres = {
                'Camas_Inventario_Vivo': '1. Inventario Vivo en Suelo (Lotes Actuales)',
                'Camas_Siembras_Futuras': '2. Siembras Proyectadas (Enraizamiento / Pedido)'
            }
            mapa_colores = {
                '1. Inventario Vivo en Suelo (Lotes Actuales)': '#059669',  # Verde Esmeralda
                '2. Siembras Proyectadas (Enraizamiento / Pedido)': '#0070F2'   # Azul SAP Fiori Horizon
            }

            if mostrar_total:
                lineas_a_graficar.append('Camas_Niveladas_OpB')
                mapa_nombres['Camas_Niveladas_OpB'] = '3. Ocupación Total en Suelo (Vivo + Siembras)'
                mapa_colores['3. Ocupación Total en Suelo (Vivo + Siembras)'] = '#7C3AED'  # Púrpura Amatista

            cols_id = ['Semana', 'Semana_Label', 'Temporada', 'Camas_Siembra', 'Esquejes_Siembra', 'Ocupacion_Nivelada_%']
            cols_id_limpias = [c for c in cols_id if c in df_plot.columns and c not in lineas_a_graficar]
            
            df_melt = pd.melt(
                df_plot,
                id_vars=cols_id_limpias,
                value_vars=lineas_a_graficar,
                var_name='Tipo_Curva',
                value_name='Camas'
            )
            df_melt['Tipo_Curva'] = df_melt['Tipo_Curva'].map(mapa_nombres)

            domain_colores = list(mapa_colores.keys())
            range_colores = [mapa_colores[k] for k in domain_colores]

            line_chart = alt.Chart(df_melt).mark_line(point=True, strokeWidth=2.6).encode(
                x=alt.X('Semana_Label:N', sort=orden_cronologico, title='Semana Operativa (Cronológica)', axis=alt.Axis(labelAngle=-45)),
                y=alt.Y('Camas:Q', title='Camas Ocupadas en Suelo', scale=alt.Scale(domain=[0, techo_camas * 1.15])),
                color=alt.Color(
                    'Tipo_Curva:N',
                    scale=alt.Scale(domain=domain_colores, range=range_colores),
                    legend=alt.Legend(title='Curvas de Capacidad', orient='top', labelFontSize=12, symbolSize=100)
                ),
                tooltip=[
                    'Semana_Label:N', 'Semana:N', 'Temporada:N', 'Tipo_Curva:N',
                    alt.Tooltip('Camas:Q', title='Camas en Curva', format='.1f'),
                    alt.Tooltip('Camas_Siembra:Q', title='Siembras Semanales (Camas)', format='.1f'),
                    alt.Tooltip('Esquejes_Siembra:Q', title='Siembras Semanales (Esquejes)', format=',d'),
                    alt.Tooltip('Ocupacion_Nivelada_%:Q', title='Ocupación Total (%)', format='.1f')
                ]
            )
            titulo_grafico = f"Curvas de Ocupación: Inventario Vivo vs. Siembras de Enraizamiento [{bloque_subtitulo}]"
            chart_final = band_opt + line_chart + rule_techo_inst + rule_techo_red

        elif modo_vista == "Plan Base (Referencia)":
            line_chart = base_chart.mark_line(point=True, color='#94A3B8', strokeWidth=2.5).encode(
                y=alt.Y('Camas_Plan_Original:Q', title='Camas Requeridas (Plan Base)', scale=alt.Scale(domain=[0, techo_camas * 1.15])),
                tooltip=[
                    'Semana_Label:N', 'Semana:N', 'Temporada:N',
                    alt.Tooltip('Camas_Siembra:Q', title='Siembras Semanales (Camas)', format='.1f'),
                    alt.Tooltip('Esquejes_Siembra:Q', title='Siembras Semanales (Esquejes)', format=',d'),
                    alt.Tooltip('Camas_Plan_Original:Q', title='Camas Requeridas (Base)', format='.1f'),
                    alt.Tooltip('Ocupacion_Original_%:Q', title='Ocupación Base (%)', format='.1f'),
                    'Estado_Capacidad:N'
                ]
            )
            titulo_grafico = f"Curva de Ocupación - Plan Base (Referencia) [{bloque_subtitulo}]"
            chart_final = band_opt + line_chart + rule_techo_inst + rule_techo_red

        else: # Comparativa de Planes
            line_orig = base_chart.mark_line(point=False, color='#94A3B8', strokeDash=[4, 3], strokeWidth=2.0).encode(
                y=alt.Y('Camas_Plan_Original:Q', title='Camas Requeridas', scale=alt.Scale(domain=[0, techo_camas * 1.15])),
                tooltip=['Semana_Label:N', 'Semana:N', 'Temporada:N', alt.Tooltip('Camas_Siembra:Q', title='Siembra (Camas)', format='.1f'), alt.Tooltip('Camas_Plan_Original:Q', title='Plan Base (Camas)', format='.1f'), alt.Tooltip('Ocupacion_Original_%:Q', title='Ocupación Base (%)', format='.1f')]
            )
            line_adj = base_chart.mark_line(point=True, color='#0070F2', strokeWidth=2.8).encode(
                y='Camas_Niveladas_OpB:Q',
                tooltip=['Semana_Label:N', 'Semana:N', 'Temporada:N', alt.Tooltip('Camas_Siembra:Q', title='Siembra (Camas)', format='.1f'), alt.Tooltip('Camas_Niveladas_OpB:Q', title='Plan Vigente (Camas)', format='.1f'), alt.Tooltip('Ocupacion_Nivelada_%:Q', title='Ocupación Vigente (%)', format='.1f')]
            )
            titulo_grafico = f"Comparativa: Plan Base (Gris Pizarra) vs. Plan Vigente (Azul SAP Fiori) [{bloque_subtitulo}]"
            chart_final = band_opt + line_orig + line_adj + rule_techo_inst + rule_techo_red

        chart_render = chart_final.properties(height=380, title=titulo_grafico)
        st.altair_chart(chart_render, width="stretch")

        st.caption(f"🔴 **Línea Roja Discontinua:** Capacidad física instalada ({int(techo_camas)} camas). | 🟠 **Línea Naranja Discontinua:** Capacidad post-reducción de área (~{int(techo_reducido)} camas / ~100 camas descontadas a partir de S{SEMANA_CORTE_REDUCCION_AREA}). | 🟢 **Franja Verde Esmeralda:** Rango operativo óptimo (85% a 95%).")

        st.info("""
        💡 **Distinción Clave entre Inventario Vivo, Siembras de Enraizamiento y Cosecha San Valentín:**
        * 🟢 **Línea Verde (Inventario Vivo en Suelo):** Muestra el decaimiento natural del cultivo actual a medida que se cosechan los lotes en campo (baja de ~918 camas en S2642 hasta 0 camas en S2703).
        * 🔵 **Línea Azul (Siembras Proyectadas de Enraizamiento):** Demuestra cómo el material vegetal ingresado a partir de S2643 va ocupando las camas liberadas. Frente a la capacidad post-reducción (**1,068 camas comerciales** desde S2648), la ocupación alcanza **1,053 camas (98.6%)** en el pico de San Valentín (S2704).
        * 🤝 **Coexistencia y Relevo:** Durante las semanas de siembra de San Valentín (S2643-S2647), las nuevas siembras coexisten con el cultivo saliente garantizando que la finca no quede desocupada ni sobrepase el límite físico.
        """)

        # Tabla Semanal Detallada
        with st.expander(f"📋 Ver Detalle Semana a Semana (52 Semanas) - {bloque_subtitulo}", expanded=False):
            df_plot_tbl = df_plot.copy()
            df_plot_tbl['Diferencia_Camas'] = (df_plot_tbl['Camas_Plan_Original'] - df_plot_tbl['Camas_Niveladas_OpB']).clip(lower=0).round(1)
            df_plot_tbl['Ahorro_Esquejes'] = (df_plot_tbl['Diferencia_Camas'] * 5200).round().astype(int)
            cols_para_mostrar = [
                "Semana", "Semana_Label", "Temporada", 
                "Camas_Siembra", "Esquejes_Siembra",
                "Camas_Inventario_Vivo", "Camas_Siembras_Futuras",
                "Camas_Niveladas_OpB", "Ocupacion_Nivelada_%", 
                "Camas_Plan_Original", "Ocupacion_Original_%",
                "Diferencia_Camas", "Ahorro_Esquejes", "Estado_Capacidad"
            ]
            cols_existentes = [c for c in cols_para_mostrar if c in df_plot_tbl.columns]
            st.dataframe(
                df_plot_tbl[cols_existentes],
                column_config={
                    "Semana_Label": st.column_config.TextColumn("Semana Ops"),
                    "Temporada": st.column_config.TextColumn("Temporada / Etapa"),
                    "Camas_Siembra": st.column_config.NumberColumn("Siembra (Camas)", format="%.1f"),
                    "Esquejes_Siembra": st.column_config.NumberColumn("Siembra (Esquejes)", format="%,d"),
                    "Camas_Inventario_Vivo": st.column_config.NumberColumn("Camas Vivo en Suelo", format="%.1f"),
                    "Camas_Siembras_Futuras": st.column_config.NumberColumn("Camas Siembras Proy.", format="%.1f"),
                    "Ocupacion_Nivelada_%": st.column_config.NumberColumn("Ocup. Vigente (%)", format="%.1f%%"),
                    "Ocupacion_Original_%": st.column_config.NumberColumn("Ocup. Base (%)", format="%.1f%%"),
                    "Camas_Niveladas_OpB": st.column_config.NumberColumn("Camas Total en Suelo", format="%.1f"),
                    "Camas_Plan_Original": st.column_config.NumberColumn("Camas Plan Base", format="%.1f"),
                    "Diferencia_Camas": st.column_config.NumberColumn("Diferencia Camas", format="%.1f"),
                    "Ahorro_Esquejes": st.column_config.NumberColumn("Diferencia Esquejes", format="%,d"),
                },
                width="stretch",
                hide_index=True
            )

    # =========================================================================
    # TAB 3: BALANCEO ESTACIONAL & PLAN DE AJUSTE DE ÁREA
    # =========================================================================
    with tab3:
        st.subheader("Balance Operativo Estacional y Transición de Capacidad")
        st.markdown("""
        Parámetros operativos de balance estacional, cronograma de reducción de área física 
        (**64,878 m² → 61,878 m²**) y programación de paradas y descansos de bloques.
        """)

        bal_info = calcular_balanceo_estacional(df_52w)
        kpis = bal_info['kpis_maestros']

        with st.container(border=True):
            st.markdown("#### 📊 Parámetros de Ocupación y Capacidad de Finca")
            cb1, cb2, cb3, cb4 = st.columns(4)
            cb1.metric("Capacidad Máxima Vigente", f"{CAMAS_COMERCIALES_TOTALES:.0f} camas", "1,168 camas comerciales")
            cb2.metric("Pico Máximo Proyectado", f"{kpis_niv.get('max_camas_nivelado', 1168):.0f} camas", "100.0% de utilización")
            cb3.metric("Semanas con Ocupación Plena", f"{kpis_niv.get('semanas_intactas_100pct', 42)} semanas", "Plan regular y Summer")
            cb4.metric("Capacidad Post-Reducción", "1,068 camas", f"-100 camas desde S{SEMANA_CORTE_REDUCCION_AREA}")

        st.divider()

        # Gobernanza S&OP: Cronograma y Ventana Congelada (24 Semanas)
        with st.container(border=True):
            st.markdown("#### 🏛️ Gobernanza S&OP: Cronograma de Transición y Ventana Congelada (24 Semanas)")
            st.markdown(f"""
            * **Cronograma de Transición de Área Física:**
              - **Vigente Hoy (hasta S2647):** Área comercial de **64,878 m²**.
              - **A partir de Semana 2648:** Reducción física a **61,878 m²** ($-3,000 \\text{{ m}}^2$, $-4.62\\%$ / $\\approx 100$ camas descontadas).
            * **Alcance del Módulo de Ocupación:** Este módulo establece los techos físicos de capacidad (**1,168 camas comerciales** hoy, **1,068 camas** régimen post-reducción), 
              monitorea la ocupación en picos estacionales (San Valentín y Navidad) y programa descansos y paradas de bloques en Summer.
            * **Programación en Material Vegetal:** Los pedidos de la ventana ejecutable se calibran al régimen de área y destino por bloque en el módulo 
              **[🌱 Pedido de Material Vegetal](?nav=pedido)** para asegurar sincronía entre material vegetal recibido y camas físicas disponibles.
            * **Regla Inmutable de Ventana Congelada (24 Semanas):** Los pedidos regulares en firme aplican a partir de **+24 semanas** 
              totalmente calibrados bajo el régimen de capacidad física y dimensionados por bloque de destino.
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
            x=alt.X('Semana_Label:N', title='Semana Operativa', axis=alt.Axis(labelAngle=-45)),
            y=alt.Y('Bloque:N', title='Bloque de la Finca', sort=['INV', '01', '02', '03', '04', '05', '06']),
            color=alt.Color('Ocupacion_%:Q', title='Ocupación (%)', scale=alt.Scale(
                scheme='greens',
                domain=[0, 100]
            )),
            tooltip=['Bloque:N', 'Semana_Label:N', 'Semana:N', 'Camas_Ocupadas:Q', 'Ocupacion_%:Q']
        ).properties(
            height=320,
            title="Matriz de Ocupación Espacial: Bloques vs. Semanas"
        )

        st.altair_chart(heat_chart, width="stretch")
        st.caption("Verde oscuro = Bloque con alta ocupación (85-100%). Verde claro = Bloque con camas libres disponibles para nuevas siembras.")
