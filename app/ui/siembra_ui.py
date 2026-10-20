import io
import pandas as pd
import streamlit as st
from datetime import date
from sqlalchemy.orm import Session
from app.services.siembra_service import (
    obtener_catalogo_semanas_siembra,
    obtener_semanas_siembra_disponibles,
    generar_plano_siembra_semanal,
    generar_pdf_plano_siembra
)

def render_siembra_module(db: Session):
    """
    Renderiza el Módulo Oficial del Plan de Siembra Semanal en Campo.
    Permite seleccionar cualquier semana de siembra registrada,
    analizar la distribución de camas y bloques, y descargar el plano oficial en PDF (1 página) y Excel.
    """
    st.markdown("### 🌱 Plan Operativo de Siembra Semanal (Campo)")
    st.caption(
        "Programación detallada de la siembra en eras de campo. "
        "Sincroniza las plántulas provenientes de enraizamiento (3 semanas de propagación) "
        "y distribuye los lotes de manera balanceada de Lunes a Sábado para asegurar el pico fenológico a cosecha."
    )

    # 1. Cargar catálogo de semanas de siembra programadas
    semanas_catalogo = obtener_catalogo_semanas_siembra(db)
    if not semanas_catalogo:
        st.warning("⚠️ No se encontraron semanas de siembra programadas en el sistema.")
        return

    # Opciones para el selector:
    # Priorizar la primera semana con ejecución real confirmada, o S2646 si ninguna tiene ejecución aún.
    default_idx = 0
    idx_s2646 = 0
    encontro_con_ejec = False
    for idx, s in enumerate(semanas_catalogo):
        if s['Semana_Siembra'] == '202646':
            idx_s2646 = idx
        if s.get('Tiene_Ejecucion_Real', False) and not encontro_con_ejec:
            default_idx = idx
            encontro_con_ejec = True

    if not encontro_con_ejec:
        default_idx = idx_s2646

    c_sel1, c_sel2 = st.columns([3, 1])
    with c_sel1:
        semana_sel = st.selectbox(
            "Seleccione la Semana de Siembra a consultar:",
            options=semanas_catalogo,
            index=default_idx,
            format_func=lambda s: s['Label'],
            help="Seleccione la semana de siembra a consultar. Requiere ejecución real de clavado ingresada en enraizamiento (3 semanas antes)."
        )
    cod_sem_siembra = semana_sel['Semana_Siembra']

    with c_sel2:
        base_capacidad = st.selectbox(
            "Base de Capacidad de Cama:",
            options=["bloque", "std_5200", "finca"],
            format_func=lambda x: "Física por Bloque" if x == "bloque" else ("Estándar (5,200)" if x == "std_5200" else "Promedio Finca"),
            index=0,
            help="Determina si los requerimientos de esquejes se calculan con el metraje exacto del bloque destino o el estándar comercial."
        )

    # Si la semana seleccionada NO cuenta con ejecución real, bloquear y explicar didácticamente
    if not semana_sel.get('Tiene_Ejecucion_Real', False):
        st.error(
            f"⛔ **La Semana {semana_sel['Semana_Siembra_Label']} ({semana_sel['Semana_Siembra']}) no puede cargarse:**\n\n"
            f"Aún no tiene ingresada la **Ejecución Real de Clavado** en el módulo de enraizamiento para su semana origen (**{semana_sel['Semana_Enraizamiento_Label']}**).\n\n"
            "⚠️ **El sistema no simula que el plan se ejecutó al 100%**, ya que en campo únicamente es agronómicamente viable "
            "programar las plántulas que efectivamente fueron clavadas y enraizadas en propagación con 3 semanas de anticipación."
        )
        with st.container(border=True):
            st.markdown(
                f"#### 🔒 Bloqueo de Trazabilidad Agronómica — Siembra {semana_sel['Semana_Siembra_Label']}\n\n"
                f"- **Semana de Enraizamiento Requerida (W-3):** `{semana_sel['Semana_Enraizamiento_Label']}` (`{semana_sel['Semana_Enraizamiento']}`)\n"
                f"- **Temporada Proyectada:** {semana_sel['Temporada']} (Cosecha estimada: {semana_sel['Semana_Cosecha_Label']})\n"
                f"- **Estado en Propagación:** `🔴 0 bandejas reales registradas (Pendiente de Clavado)`\n\n"
                "---\n\n"
                "##### 🛠️ ¿Cómo habilitar y emitir este Plano de Siembra?\n"
                "1. En el menú de navegación lateral, ingrese a **📋 Plan de Enraizamiento**.\n"
                f"2. Seleccione la semana **{semana_sel['Semana_Enraizamiento_Label']}** en el selector superior.\n"
                "3. Abra la **Pestaña 3: ✅ Registro de Ejecutado Real**.\n"
                "4. Digite las bandejas efectivamente clavadas por variedad y presione **'💾 Guardar Ejecutado'** o **'✅ Aprobar y Descontar de Inventario'**.\n"
                f"5. Regrese a este módulo (**🌱 Plan de Siembra**): la semana **{semana_sel['Semana_Siembra_Label']}** se desbloqueará de inmediato reflejando exactamente las plántulas vivas disponibles para trasplante a campo."
            )
        return

    # 2. Generar Plano Operativo de Siembra
    res_siembra = generar_plano_siembra_semanal(
        db,
        cod_sem_siembra,
        base_capacidad=base_capacidad
    )

    if "error" in res_siembra:
        st.error(res_siembra.get('mensaje', res_siembra['error']))
        return

    kpis = res_siembra['kpis']
    df_detallado = res_siembra['df_plano_detallado']
    df_res_dia = res_siembra['df_resumen_diario']
    df_res_bloques = res_siembra['df_resumen_bloques']
    es_ajustado = res_siembra.get('es_ajustado_enraizamiento', False)

    # Banner Superior de KPIs
    with st.container(border=True):
        st.markdown(
            f"#### 📊 Resumen Ejecutivo — Siembra {res_siembra['semana_siembra_label']} "
            f"(Enraizamiento Origen {res_siembra['semana_enraizamiento_label']} | Cosecha {res_siembra['semana_cosecha_label']} | {res_siembra['temporada']})"
        )
        k1, k2, k3, k4, k5, k6 = st.columns(6)
        k1.metric("Camas Campo", f"{kpis['total_camas']:.1f}", f"{kpis['num_lotes']} lotes")
        k2.metric("Plantas a Sembrar", f"{kpis['total_plantas']:,d}", "Plántulas enraizadas")
        k3.metric("Bandejas (112)", f"{kpis['total_bandejas']:,d}", "Entero más cercano")
        k4.metric("Bloques Campo", f"{len(df_res_bloques)} Bloques", kpis.get('bloques_asignados', ''))
        k5.metric("Tallos Proyectados", f"{kpis['tallos_esperados']:,d}", "A cosecha comercial")
        k6.metric("Temporada Destino", res_siembra['temporada'], f"Cosecha {res_siembra['semana_cosecha_label']}")

    # Botones de Descarga en barra superior
    col_btn1, col_btn2, col_spacer = st.columns([1.8, 1.5, 3])

    # 1. Generar PDF oficial
    pdf_bytes = generar_pdf_plano_siembra(res_siembra)
    with col_btn1:
        st.download_button(
            label=f"📥 Descargar Plano de Siembra en PDF ({res_siembra['semana_siembra_label']})",
            data=pdf_bytes,
            file_name=f"Plano_Siembra_{res_siembra['semana_siembra_label']}.pdf",
            mime="application/pdf",
            help="Descarga el plano oficial de siembra en 1 sola hoja horizontal para entrega al equipo de campo."
        )

    # 2. Generar Excel
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        df_detallado.to_excel(writer, index=False, sheet_name='Plano_Siembra_Detallado')
        df_res_dia.to_excel(writer, index=False, sheet_name='Resumen_Diario')
        df_res_bloques.to_excel(writer, index=False, sheet_name='Resumen_Bloques')
    with col_btn2:
        st.download_button(
            label="📊 Descargar Plano en Excel",
            data=excel_buffer.getvalue(),
            file_name=f"Plano_Siembra_{res_siembra['semana_siembra_label']}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="Descarga el plano detallado de siembra y resúmenes diarios en formato Excel."
        )

    if es_ajustado:
        st.success(
            f"⚡ **Sincronizado con Enraizamiento Ajustado ({res_siembra['semana_enraizamiento_label']}):** "
            "Este plano de siembra refleja las plántulas efectivas enraizadas, incluyendo compensaciones autorizadas y variedades extemporáneas."
        )

    # Pestañas de Navegación
    tab_plano, tab_bloques = st.tabs([
        "📄 Hoja de Ruta de Siembra (Día a Día)",
        "🏢 Distribución por Bloques y Jornada Diaria"
    ])

    with tab_plano:
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

        df_display['Nivelado'] = df_display['Es_Nivelado'].apply(lambda x: "⚡ Nivelado" if x else "🎯 Tentativo")

        columnas_orden = [
            "Dia_Programado", "Flor", "Color", "Variedad", "Camas_Campo", "Plantas_Sembradas",
            "Bandejas_112", "Bloque_Destino", "Semana_Cosecha", "Tallos_Esperados",
            "Ejecutado_Real", "Observaciones", "Nivelado"
        ]
        columnas_orden = [c for c in columnas_orden if c in df_display.columns]

        row_totales = {
            "Dia_Programado": "TOTAL GENERAL",
            "Flor": "-",
            "Color": "-",
            "Variedad": f"{len(df_display)} Variedades",
            "Camas_Campo": round(float(df_display['Camas_Campo'].sum()), 1),
            "Plantas_Sembradas": int(df_display['Plantas_Sembradas'].sum()),
            "Bandejas_112": int(df_display['Bandejas_112'].sum()),
            "Bloque_Destino": f"{df_display['Bloque_Destino'].nunique()} Bloques",
            "Semana_Cosecha": "-",
            "Tallos_Esperados": int(df_display['Tallos_Esperados'].sum()),
            "Ejecutado_Real": "",
            "Observaciones": "",
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
                "Camas_Campo": st.column_config.NumberColumn("Camas Campo", format="%.1f", help="Camas de campo físicas a sembrar"),
                "Plantas_Sembradas": st.column_config.NumberColumn("Plantas a Sembrar", format="%d", help="Total plántulas enraizadas requeridas"),
                "Bandejas_112": st.column_config.NumberColumn("Bandejas (112)", format="%d", help="Bandejas de propagación a trasladar a campo"),
                "Bloque_Destino": st.column_config.TextColumn("Bloque Destino"),
                "Semana_Cosecha": st.column_config.TextColumn("Sem. Cosecha"),
                "Tallos_Esperados": st.column_config.NumberColumn("Tallos Proyectados", format="%d"),
                "Ejecutado_Real": st.column_config.TextColumn("Ejecutado Real", help="Casilla para anotación física de camas sembradas en campo"),
                "Observaciones": st.column_config.TextColumn("Observaciones", help="Espacio para registrar novedades físicas de campo por el operario"),
                "Nivelado": st.column_config.TextColumn("Estado Programación")
            },
            hide_index=True,
            width="stretch"
        )

        st.caption(
            "💡 **Cálculo Técnico de Siembra:** Cada cama estándar aloja ~5,200 plántulas enraizadas "
            "(aproximadamente 46 bandejas de 112 cavidades). La siembra se programa en los días previos para concentrar "
            "la cosecha en el pico de floración de los días jueves."
        )

    with tab_bloques:
        st.markdown("##### 🏢 Asignación de Bloques y Distribución de Jornadas")
        c_b1, c_b2 = st.columns(2)

        with c_b1:
            st.markdown("###### 📊 Camas de Campo por Bloque Receptor")
            st.dataframe(
                df_res_bloques,
                column_config={
                    "Bloque_Destino": st.column_config.TextColumn("Bloque Destino"),
                    "Camas": st.column_config.NumberColumn("Camas a Sembrar", format="%.1f"),
                    "Plantas": st.column_config.NumberColumn("Plantas / Esquejes", format="%d"),
                    "Bandejas": st.column_config.NumberColumn("Bandejas (112)", format="%d"),
                    "Variedades": st.column_config.NumberColumn("Lotes / Variedades", format="%d")
                },
                hide_index=True,
                width="stretch"
            )

        with c_b2:
            st.markdown("###### 📅 Distribución Semanal de la Labor (Lunes a Sábado)")
            st.dataframe(
                df_res_dia,
                column_config={
                    "Día": st.column_config.TextColumn("Día"),
                    "Camas": st.column_config.NumberColumn("Camas", format="%.1f"),
                    "Plantas / Esquejes": st.column_config.NumberColumn("Plantas", format="%d"),
                    "Bandejas (112)": st.column_config.NumberColumn("Bandejas", format="%d"),
                    "% de la Semana": st.column_config.NumberColumn("% Semana", format="%.1f%%"),
                    "Variedades a Sembrar": st.column_config.NumberColumn("Variedades", format="%d")
                },
                hide_index=True,
                width="stretch"
            )

