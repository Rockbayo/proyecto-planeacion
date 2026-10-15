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
    st.markdown("""
    Este módulo genera el **plano operativo oficial de enraizamiento** para entrega directa a la jefatura de propagación.
    Alinea los pedidos comerciales con la ventana fenológica óptima (**cosecha en pico los jueves**),
    estandariza a **bandejas de 112 cavidades**, asigna el **bloque de campo tentativo** de destino,
    nivela la carga de trabajo diaria (Lunes a Sábado, 44.5h legales) y modela la **cuadrilla de mano de obra**.
    """)

    # Selector de Escenario de Planificación
    with st.container(border=True):
        st.markdown("#### 🎯 Escenario Operativo y Capacidad de Proceso")
        col_esc, col_opt = st.columns([1.6, 1.2])
        with col_esc:
            escenario_sel = st.radio(
                "Seleccione el modelo operativo de enraizamiento:",
                options=[
                    "⭐ Plan Balanceado S&OP (3 Semanas al Techo Operativo: 381 Camas SV | 372 Camas Madres)",
                    "⚡ Pico Concentrado (50% en Pico S2643: 190 Camas | 988k Esq)",
                    "📋 Base Histórica Plataforma (Valores Originales Sin Ajuste)"
                ],
                index=0,
                help="El Plan Balanceado distribuye el volumen en las 3 semanas de la temporada respetando la capacidad de clavado, siembra y poscosecha sin ahogar la finca."
            )

        modo_plan = "aprobado"
        factor_expansion = 1.0
        modo_concentracion = "base"

        if "Plan Balanceado S&OP" in escenario_sel:
            modo_plan = "aprobado"
            modo_concentracion = "base"
            factor_expansion = 1.0
            with col_opt:
                st.success(
                    "🌿 **Plan Balanceado (Máximo Techo Operativo Sostenible):**\n\n"
                    "• **S2642 (SV 1):** 106.0 camas (551,200 esq) ➔ Cuadrilla base 6 op.\n\n"
                    "• **S2643 (Pico):** 148.0 camas (769,600 esq) ➔ 9 op. (Techo de clavado)\n\n"
                    "• **S2644 (SV 3):** 127.0 camas (660,400 esq) ➔ 7.5 op.\n\n"
                    "**Suma 3 Semanas San Valentín:** **381 camas** (1,981,200 esquejes).\n\n"
                    "**Suma 3 Semanas Madres:** **372 camas** (1,934,400 esquejes: 138-143-91 cam).\n\n"
                    "✅ **Protección:** Ocupación en S48 al 100% de 1,068 camas (0 déficit)."
                )
        elif "Pico Concentrado" in escenario_sel:
            modo_plan = "aprobado"
            modo_concentracion = "pico_50"
            factor_expansion = 1.0
            with col_opt:
                st.warning(
                    "⚡ **Concentración Forzada al 50% en Pico S2643:**\n\n"
                    "• **S2642:** 85.0 camas (442,000 esq)\n\n"
                    "• **S2643 (Pico):** 190.0 camas (988,000 esq ➔ Requiere 11 op. clavado)\n\n"
                    "• **S2644:** 106.0 camas (551,200 esq)\n\n"
                    "⚠️ *Nota operativa:* Exige refuerzo extraordinario de clavado y satura mesas de poscosecha en semana 04."
                )
        else:
            modo_plan = "plataforma_base"
            factor_expansion = 1.0
            modo_concentracion = "base"
            with col_opt:
                st.info("📋 Mostrando las órdenes históricas sin actualizar al pedido aprobado.")

    # 1. Cargar semanas disponibles en el Pedido Aprobado según el modo seleccionado
    semanas_disp = obtener_semanas_enraizamiento_disponibles(
        modo_plan=modo_plan,
        factor_expansion=factor_expansion,
        modo_concentracion=modo_concentracion
    )
    if not semanas_disp:
        st.warning("⚠️ No se encontraron órdenes de siembra en el archivo de pedidos consolidado maestro.")
        return

    # Buscar semana por defecto: pico de San Valentín (ej. 202643) o la primera
    default_idx = 0
    for idx, s in enumerate(semanas_disp):
        if s.get("Semana_Enraizamiento") == "202643":
            default_idx = idx
            break

    # Selector de Semana y Parámetros
    with st.container(border=True):
        st.markdown("#### 📅 Selección de Semana y Objetivos de Temporada")
        
        def format_semana(opt):
            cam_txt = f" | {opt.get('Total_Camas', 0):.0f} cam." if opt.get('Total_Camas') else ""
            return (
                f"{opt['Semana_Enraizamiento_Label']} "
                f"(Siembra {opt['Semana_Siembra_Label']} ➔ Cosecha {opt.get('Semana_Cosecha_Label', '')} | {opt['Temporada']}) — "
                f"{opt['Total_Esquejes']:,d} esq. ({opt['Total_Bandejas_112']:,d} bandejas 112{cam_txt})"
            )

        col_sem, col_info = st.columns([2, 1])
        with col_sem:
            semana_sel = st.selectbox(
                "Semana de enraizamiento a programar:",
                options=semanas_disp,
                index=default_idx,
                format_func=format_semana,
                help="Seleccione la semana en la que ingresa el material vegetal a las camas de nebulización en propagación."
            )

        with col_info:
            if semana_sel:
                st.caption(f"**Temporada Objetivo:** {semana_sel['Temporada']}")
                st.caption(f"**Desfase a Siembra:** -{SEMANAS_ENRAIZAMIENTO} semanas ({DIAS_PERMANENCIA_BANCO} días en banco)")
                st.caption(f"**Variedades en Lote:** {semana_sel['Num_Variedades']} variedades")

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
            num_refuerzo = st.number_input(
                "Cantidad de refuerzos:",
                min_value=0, max_value=50, value=0, step=1,
                help="Personal de apoyo temporal contratado para temporada."
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
        modo_concentracion=modo_concentracion
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
            f"Base: 44.5h legal"
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
        "📈 Proyección Plataforma vs Pedido y Rotación de Camas",
        "🌿 Ventana Fenológica y Parámetros"
    ])

    # -------------------------------------------------------------
    # TAB 1: PLANO OPERATIVO SEMANAL
    # -------------------------------------------------------------
    with tab_plano:
        st.markdown("##### 📄 Hoja de Ruta de Clavado por Lote y Variedad")
        st.caption(
            "Este plano contiene la programación día a día de enraizamiento. Los días están nivelados para respetar "
            "las jornadas legales y concentrar la cosecha en el pico objetivo de los jueves. "
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
            "Consolida las horas de labor demandadas por el volumen total de enraizamiento contra la capacidad "
            "efectiva de la cuadrilla asignada para la semana completa (base legal 44.5h)."
        )

        # 1. Tabla de Operarios Requeridos Consolidada por Semana
        bal = mano_obra.get("balance_semanal_operarios", 0)
        estado_sem = "🟢 CUBIERTA" if bal >= 0 else ("🟡 AJUSTADA" if bal >= -1.0 else f"🔴 SOBRECARGA (+{abs(bal):.0f} ref.)")
        df_resumen_semanal = pd.DataFrame([{
            "Semana": res_plano['semana_enraizamiento_label'],
            "Jornada Legal": "44.5 h",
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
                "Jornada Legal": st.column_config.TextColumn("Jornada Legal"),
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
                    "Jornada (Horas)": st.column_config.NumberColumn("Jornada Legal", format="%.1f h"),
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
            chart_esq = alt.Chart(df_res_dia).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, color="#2e7d32").encode(
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
                color=alt.Color('Tipo:N', scale=alt.Scale(domain=['Horas Requeridas', 'Horas Disponibles'], range=['#d32f2f', '#1976d2'])),
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
    # TAB 3: PROYECCIÓN PLATAFORMA VS PEDIDO Y ROTACIÓN DE CAMAS
    # -------------------------------------------------------------
    with tab_comparativa:
        st.markdown("##### 📈 Comportamiento de Enraizamiento: Plataforma vs Pedido Programado")
        st.caption(
            "Compara la curva semanal de enraizamiento calculada por la plataforma contra la lógica oficial del pedido "
            "programado (Excel de Analítica S&OP) para cumplir con el pico de 1,410,000 tallos de San Valentín (S03-S05)."
        )

        datos_comp = obtener_datos_comparativos_enraizamiento_y_camas(
            db,
            modo_plan=modo_plan,
            factor_expansion=factor_expansion,
            modo_concentracion=modo_concentracion
        )
        df_comp = datos_comp['df_comp_enraizamiento']
        df_lib = datos_comp['df_liberacion_camas']

        # Gráfico 1: Comparativa de Esquejes por Semana
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
            color=alt.Color('Fuente:N', scale=alt.Scale(domain=['Plataforma S&OP', 'Pedido Programado (Analítica)'], range=['#2e7d32', '#1565c0'])),
            xOffset='Fuente:N',
            tooltip=['Semana_Enraizamiento_Label', 'Fuente', alt.Tooltip('Esquejes:Q', format=',d'), 'Temporada']
        ).properties(height=340)

        st.altair_chart(chart_comp, width="stretch")

        with st.expander("📋 Ver Tabla Comparativa Numérica por Semana", expanded=False):
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
                    "Tallos_Esperados_Cosecha": st.column_config.NumberColumn("Tallos Cosecha (~80% Aprov)", format="%d")
                },
                hide_index=True,
                width="stretch"
            )

        st.markdown("---")
        st.markdown("##### 🚜 Análisis de Liberación de Camas Vivas en Campo (Ajuste de Suelo: 3 vs 7 Días)")
        st.caption(
            "Evalúa la disponibilidad física de camas en campo provenientes del inventario vivo actual a medida que se "
            "cosechan y liberan, comparando la preparación de suelo estándar (7 días) contra el ajuste acelerado a 3 días."
        )

        c_pico_3d = int(df_lib[df_lib['Semana_Siembra'] == '202646']['Camas_Liberadas_3d'].values[0])
        c_gain_pico = int(df_lib[df_lib['Semana_Siembra'] == '202646']['Ganancia_Camas_Anticipadas'].values[0])
        demanda_tot_sv = int(df_lib['Camas_Requeridas_Semana'].sum())
        balance_sv = int(df_lib[df_lib['Semana_Siembra'] == '202647']['Balance_Disponibilidad_3d'].values[0])

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Camas Liberadas al Pico (S2646)", f"{c_pico_3d} camas", f"+{c_gain_pico} camas con 3 días")
        col_m2.metric("Demanda San Valentín", f"{demanda_tot_sv} camas", "S2645 a S2647 (3 semanas)")
        col_m3.metric("Superávit de Espacio", f"+{balance_sv} camas libres", "Holgura positiva garantizada")
        col_m4.metric("Días de Preparación", "3 Días", "-4 días de descanso")

        # Gráfico 2: Liberación de Camas vs Demanda
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
            'Camas_Requeridas_Acumuladas': 'Demanda Camas San Valentín Acumulada'
        })

        chart_lib = alt.Chart(df_melt_lib).mark_line(point=True).encode(
            x=alt.X('Semana_Siembra_Label:N', title="Semana de Siembra en Campo"),
            y=alt.Y('Camas:Q', title="Camas Físicas Acumuladas"),
            color=alt.Color('Concepto:N', scale=alt.Scale(
                domain=['Liberación Estándar (7 días suelo)', 'Liberación Acelerada (3 días suelo)', 'Demanda Camas San Valentín Acumulada'],
                range=['#757575', '#2e7d32', '#d32f2f']
            )),
            strokeDash=alt.condition(
                alt.datum.Concepto == 'Demanda Camas San Valentín Acumulada',
                alt.value([5, 5]),
                alt.value([0])
            ),
            tooltip=['Semana_Siembra_Label', 'Concepto', alt.Tooltip('Camas:Q', format='.1f')]
        ).properties(height=320)

        st.altair_chart(chart_lib, width="stretch")

        st.success(
            f"✅ **Conclusión Agronómica de Espacio:** Reduciendo la preparación de suelo a **3 días**, se liberan "
            f"**{c_pico_3d} camas** para la semana pico S2646 (ganando **+{c_gain_pico} camas de anticipación**). "
            f"La demanda acumulada de las 3 semanas de San Valentín ({demanda_tot_sv} camas) queda holgadamente "
            f"cubierta con un saldo a favor de **+{balance_sv} camas libres**."
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
           - **Camas estimadas:** A razón de ~5,000 plantas por cama estándar.
        
        3. **Floración y Cosecha Comercial ({res_plano.get('semana_cosecha_label', '')} | {res_plano['temporada']}):**
           - **Ciclo vegetativo:** Entre 68 y 84 días según la respuesta lumínica y fenológica de la variedad.
           - **Meta de calidad:** Concentrar el pico de corte los **jueves** de las semanas oficiales de temporada.
        """)

        st.markdown("##### 🕒 Horarios de Jornada Laboral Legal Vigente")
        jornadas_data = [
            {"Día": d, "Horas Laborales": f"{h:.1f} h", "Detalle": "Jornada estándar legal (6:00 am - 2:00 pm)" if h == 8.0 else ("Jornada recortada (6:00 am - 1:30 pm)" if h == 7.5 else "Media jornada de sábado (6:00 am - 11:00 am)")}
            for d, h in HORAS_JORNADA.items() if h > 0
        ]
        st.table(pd.DataFrame(jornadas_data))
        st.caption(f"**Total Jornada Semanal Legal:** {TOTAL_HORAS_SEMANA_ESTANDAR:.1f} horas / operario.")

