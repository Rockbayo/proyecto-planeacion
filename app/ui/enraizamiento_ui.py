import streamlit as st
import pandas as pd
import io
import math
from datetime import date
import altair as alt

from app.services.enraizamiento_service import (
    obtener_semanas_enraizamiento_disponibles,
    generar_plano_enraizamiento_semanal,
    generar_pdf_plano_enraizamiento,
    obtener_datos_comparativos_enraizamiento_y_camas,
    CAVIDADES_POR_BANDEJA,
    DIAS_PERMANENCIA_BANCO,
    SEMANAS_ENRAIZAMIENTO,
    HORAS_JORNADA,
    TOTAL_HORAS_SEMANA_ESTANDAR,
    RENDIMIENTO_NORMAL,
    RENDIMIENTO_REFUERZO,
    RENDIMIENTO_APRENDIZAJE
)

def render_enraizamiento_module(db):
    st.header("🌱 Plan y Plano Operativo de Enraizamiento")
    st.markdown(f"""
    Genera el **plano operativo oficial de enraizamiento** para entrega directa a la jefatura de propagación.
    Alinea los requerimientos de siembra con el día óptimo (**cosecha en pico los jueves**),
    estandariza a **bandejas de 112 cavidades**, asigna el **bloque de campo tentativo** de destino,
    nivela la jornada laboral semanal (**{TOTAL_HORAS_SEMANA_ESTANDAR:.1f}h efectivas**, deduciendo 30 min de almuerzo L-V) y proyecta la **cosecha resultante**.
    """)

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
            return (
                f"{opt['Semana_Enraizamiento_Label']} "
                f"(Siembra {opt['Semana_Siembra_Label']} ➔ Cosecha {opt.get('Semana_Cosecha_Label', '')} | {opt['Temporada']}) — "
                f"{opt['Total_Esquejes']:,d} esq. ({opt['Total_Bandejas_112']:,d} bandejas 112{cam_txt})"
            )

        col_sem, col_mod = st.columns([2.2, 1.0])
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

        # Resumen Dinámico Adaptado a la Semana Seleccionada (sin textos defensivos)
        if semana_sel:
            st.info(
                f"📋 **Programa Operativo Semana {semana_sel['Semana_Enraizamiento_Label']}:** "
                f"Siembra en Campo: **{semana_sel['Semana_Siembra_Label']}** (Desfase: -{SEMANAS_ENRAIZAMIENTO} sem en banco) | "
                f"Cosecha Estimada: **{semana_sel.get('Semana_Cosecha_Label', '')}** | "
                f"Temporada: **{semana_sel['Temporada']}** | "
                f"Volumen: **{semana_sel['Total_Esquejes']:,d} esquejes** ({semana_sel['Total_Camas']:.1f} camas, {semana_sel['Total_Bandejas_112']:,d} bandejas 112, {semana_sel['Num_Variedades']} variedades)."
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

    # Generar Plano Operativo Semanal
    cod_sem = semana_sel['Semana_Enraizamiento']
    res_plano = generar_plano_enraizamiento_semanal(
        db, 
        cod_sem, 
        config_cuadrilla=config_cuadrilla,
        modo_plan=modo_plan,
        factor_expansion=factor_expansion,
        correr_variedades=correr_variedades
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
        
        k1.metric(
            "Total Esquejes", 
            f"{kpis['total_esquejes']:,d}", 
            f"{kpis['num_lotes']} lotes"
        )
        k2.metric(
            "Bandejas (112 alv.)", 
            f"{kpis['total_bandejas']:,d}", 
            f"112 cavidades"
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
        k6.metric(
            "Tallos a Cosecha", 
            f"{kpis['tallos_esperados']:,d}", 
            f"Aprov. ponderado"
        )

    # Pestañas de Trabajo
    tab_plano, tab_mano_obra, tab_comparativa, tab_fenologia = st.tabs([
        "📋 Plano Operativo Semanal (Detalle por Lote)",
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

        # Botones de Descarga en barra superior
        col_btn1, col_btn2, col_spacer = st.columns([1.5, 1.5, 3])
        
        # 1. Generar PDF oficial
        pdf_bytes = generar_pdf_plano_enraizamiento(res_plano)
        with col_btn1:
            st.download_button(
                label="📥 Descargar Plano en PDF (Listo para Operación)",
                data=pdf_bytes,
                file_name=f"Plano_Enraizamiento_{res_plano['semana_enraizamiento_label']}.pdf",
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
        
        columnas_orden = [
            "Dia_Programado", "Flor", "Color", "Variedad", "Esquejes", 
            "Bandejas_112", "Camas_Campo", "Bloque_Destino", 
            "Semana_Siembra", "Semana_Cosecha", "Tallos_Esperados", "Nivelado"
        ]
        columnas_orden = [c for c in columnas_orden if c in df_display.columns]

        # Fila de Totales
        row_totales = {
            "Dia_Programado": "TOTAL GENERAL",
            "Flor": "-",
            "Color": "-",
            "Variedad": f"{len(df_display)} Variedades",
            "Esquejes": int(df_display['Esquejes'].sum()),
            "Bandejas_112": int(df_display['Bandejas_112'].sum()),
            "Camas_Campo": round(float(df_display['Camas_Campo'].sum()), 1),
            "Bloque_Destino": "-",
            "Semana_Siembra": "-",
            "Semana_Cosecha": "-",
            "Tallos_Esperados": int(df_display['Tallos_Esperados'].sum()),
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
                "Esquejes": st.column_config.NumberColumn("Esquejes", format="%d"),
                "Bandejas_112": st.column_config.NumberColumn("Bandejas (112)", format="%d"),
                "Camas_Campo": st.column_config.NumberColumn("Camas Campo Eq.", format="%.1f"),
                "Bloque_Destino": st.column_config.TextColumn("Bloque Destino"),
                "Semana_Siembra": st.column_config.TextColumn("Sem. Siembra"),
                "Semana_Cosecha": st.column_config.TextColumn("Sem. Cosecha"),
                "Tallos_Esperados": st.column_config.NumberColumn("Tallos Esperados", format="%d"),
                "Nivelado": st.column_config.TextColumn("Estado Programación")
            },
            hide_index=True,
            width="stretch"
        )

        st.caption(
            "💡 *Nota:* Los lotes marcados como **⚡ Nivelado** fueron redistribuidos inteligentemente desde su día tentativo "
            "hacia días adyacentes para balancear la carga física diaria y evitar horas extras excesivas o cuellos de botella en nebulización."
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

