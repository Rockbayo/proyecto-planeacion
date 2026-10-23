"""
Componentes Visuales de la Plataforma de Planeación (Estructura SAP Fiori en Lenguaje Ciudadano).
Incluye:
1. Barra Superior Global (Buscador General, Selector de Escenarios, Centro de Avisos, Ayuda Rápida y Perfil) y Navegación por Áreas de Trabajo.
2. Cabecera de Sección (Selector de Vistas Guardadas, Botones de Descarga/Actualización y Barra Inferior de Navegación).
3. Vistas Modulares:
   - Portada Principal con Tarjetas de Resumen y Mini-gráficas.
   - Tarjetas Ejecutivas del Cultivo (Gráfica por flor, Las 5 variedades con más/menos plantas y Tabla resumen).
   - Lista de Avisos y Fechas Clave con acciones rápidas.
   - Barra de Filtros Rápidos con Mini-gráficas y selector de vista (Gráfica y Tabla / Solo Gráfica / Solo Tabla).
4. Herramientas Interactivas de Planeación:
   - Tabla Dinámica y Simulador de Cantidades (con reparto automático al cambiar totales).
   - Mapa del Recorrido del Cultivo (Proveedores -> Cuarto Frío -> Vivero -> Bloques de Campo 01-06 -> Cosecha).
"""

import os
import json
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import date


# ==============================================================================
# ESTRUCTURA DE ÁREAS DE TRABAJO Y SECCIONES (EN LENGUAJE CIUDADANO)
# ==============================================================================
FIORI_SPACES = {
    "🏠 Inicio y Resumen": {
        "id": "space_home",
        "description": "Portada principal con el resumen general de la finca, avisos importantes y acceso rápido a todas las secciones.",
        "pages": ["Launchpad S&OP (Portada)", "Dashboard General"]
    },
    "📈 Ventas y Cosecha": {
        "id": "space_demand",
        "description": "Comparación entre la flor que esperamos cosechar, los pedidos de ventas y el reparto de corte diario.",
        "pages": ["ForeCast y Exportación", "Programación Diaria y Temporadas"]
    },
    "🌱 Planeación y Esquejes": {
        "id": "space_supply",
        "description": "Acuerdos de producción, control del espacio disponible en los invernaderos y pedidos de esquejes a proveedores.",
        "pages": ["Plan de Producción (MVA)", "Ocupación de Área y Capacidad", "Pedido Material Vegetal"]
    },
    "🚜 Vivero y Siembra": {
        "id": "space_execution",
        "description": "Programación semanal de bandejas en los bancos de enraizamiento y trasplante de plantas a suelo.",
        "pages": ["Plan de Enraizamiento", "Plan de Siembra"]
    },
    "🔬 Datos de Campo": {
        "id": "space_empirical",
        "description": "Consulta del rendimiento histórico real de cada variedad en campo y ajuste fino de las proyecciones.",
        "pages": ["Curvas e Índices (Campo)", "Calibración de Curvas"]
    }
}

PAGE_FRIENDLY_LABELS = {
    "Launchpad S&OP (Portada)": "Portada Principal",
    "Dashboard General": "Tablero General",
    "ForeCast y Exportación": "Proyección de Cosecha y Descargas",
    "Programación Diaria y Temporadas": "Corte Diario y Temporadas",
    "Plan de Producción (MVA)": "Plan Maestro de Producción",
    "Ocupación de Área y Capacidad": "Espacio en Invernaderos (Camas)",
    "Pedido Material Vegetal": "Pedido de Esquejes",
    "Plan de Enraizamiento": "Plan de Vivero (Enraizamiento)",
    "Plan de Siembra": "Plan de Siembra en Campo",
    "Curvas e Índices (Campo)": "Rendimiento e Histórico en Campo",
    "Calibración de Curvas": "Ajuste y Precisión de Curvas"
}

MODULE_TO_SPACE = {}
for sp_name, sp_data in FIORI_SPACES.items():
    for pg in sp_data["pages"]:
        MODULE_TO_SPACE[pg] = sp_name


def init_fiori_state():
    """Inicializa las variables de sesión de la plataforma."""
    if "fiori_active_module" not in st.session_state:
        st.session_state["fiori_active_module"] = "Dashboard General"
    if "fiori_active_space" not in st.session_state:
        st.session_state["fiori_active_space"] = "🏠 Inicio y Resumen"
    if "fiori_scenario" not in st.session_state:
        st.session_state["fiori_scenario"] = "Plan Base (Oficial)"
    if "fiori_scenario_factor" not in st.session_state:
        st.session_state["fiori_scenario_factor"] = 1.0
    if "fiori_resolved_alerts" not in st.session_state:
        st.session_state["fiori_resolved_alerts"] = set()
    if "fiori_ignored_alerts" not in st.session_state:
        st.session_state["fiori_ignored_alerts"] = set()
    if "fiori_saved_variants" not in st.session_state:
        st.session_state["fiori_saved_variants"] = {
            "Default": "Vista Estándar (Predeterminada)",
            "SV2027": "Enfoque San Valentín 2027 (S2703-S2705)",
            "Madres2027": "Enfoque Día de la Madre 2027 (S2716-S2718)",
            "CortoPlazo": "Enfoque Próximas 13 Semanas"
        }


def navigate_to_module(module_name: str):
    """Cambia a la sección seleccionada y actualiza su área de trabajo."""
    if module_name == "🏠 SAP Fiori Launchpad":
        module_name = "Launchpad S&OP (Portada)"
    st.session_state["fiori_active_module"] = module_name
    if module_name in MODULE_TO_SPACE:
        st.session_state["fiori_active_space"] = MODULE_TO_SPACE[module_name]


# ==============================================================================
# 1. BARRA SUPERIOR GLOBAL Y NAVEGACIÓN POR ÁREAS DE TRABAJO
# ==============================================================================
def render_fiori_shellbar_and_navigation(db, engine, alertas_sop: dict) -> str:
    """
    Muestra la barra superior global (Logo, Buscador General, Selector de Escenario,
    Avisos, Ayuda Rápida y Perfil) y las pestañas de navegación por áreas de trabajo.
    Retorna el nombre del módulo activo.
    """
    init_fiori_state()

    # Contar avisos activos
    alert_items = []
    for k, v in (alertas_sop or {}).items():
        if isinstance(v, dict) and v.get("titulo"):
            aid = f"alert_{k}"
            if aid not in st.session_state["fiori_resolved_alerts"] and aid not in st.session_state["fiori_ignored_alerts"]:
                alert_items.append((aid, v))
    n_alerts = len(alert_items)

    current_mod = st.session_state["fiori_active_module"]
    if current_mod not in MODULE_TO_SPACE:
        current_mod = "Dashboard General"
        st.session_state["fiori_active_module"] = current_mod
    current_space = MODULE_TO_SPACE.get(current_mod, "🏠 Inicio y Resumen")
    friendly_mod = PAGE_FRIENDLY_LABELS.get(current_mod, current_mod)
    scen_label = st.session_state.get("fiori_scenario", "Plan Base (Oficial)")

    shell_html = f"""
    <div class="fiori-shellbar">
        <div class="fiori-shell-left">
            <div class="fiori-logo-box">🌸</div>
            <div class="fiori-brand-divider"></div>
            <div class="fiori-brand-titles">
                <span class="fiori-brand-main">Planeación Agrícola &bull; Gestión de Cultivo y Cosecha</span>
                <span class="fiori-brand-sub">{current_space} &rsaquo; {friendly_mod}</span>
            </div>
        </div>
        <div class="fiori-shell-center">
            <span class="fiori-env-pill">🟢 Vista: {scen_label}</span>
            <span class="fiori-env-pill">🔔 {n_alerts} Avisos Pendientes</span>
        </div>
        <div class="fiori-shell-right">
            <div class="fiori-me-area">
                <div class="fiori-avatar">CP</div>
                <div class="fiori-me-text">
                    <span class="fiori-me-name">Equipo de Planeación</span>
                    <span class="fiori-me-role">Producción y Ventas</span>
                </div>
            </div>
        </div>
    </div>
    """
    st.markdown(shell_html, unsafe_allow_html=True)

    # Barra Interactiva: Botón Inicio | Buscador General | Escenario | Avisos | Ayuda | Perfil
    with st.container():
        c_home, c_search, c_scen, c_notif, c_assist, c_me = st.columns([1.05, 2.5, 1.45, 0.95, 0.95, 0.95])

        with c_home:
            if st.button("🏠 Portada", key="btn_fiori_home_top", width="stretch", help="Ir a la Portada Principal con el resumen de todas las secciones"):
                navigate_to_module("Launchpad S&OP (Portada)")
                st.rerun()

        with c_search:
            search_q = st.text_input(
                "Buscador General",
                placeholder="🔍 Buscar en toda la plataforma: escribe una variedad, tipo de flor, color o sección...",
                label_visibility="collapsed",
                key="fiori_enterprise_search_input"
            )

        with c_scen:
            scenarios = ["Plan Base (Oficial)", "Escenario Optimista (+5%)", "Escenario Prudente (-5%)"]
            if st.session_state["fiori_scenario"] not in scenarios:
                st.session_state["fiori_scenario"] = "Plan Base (Oficial)"
            idx_sc = scenarios.index(st.session_state["fiori_scenario"])
            sel_sc = st.selectbox(
                "Escenario de consulta",
                scenarios,
                index=idx_sc,
                label_visibility="collapsed",
                key="fiori_scenario_select",
                help="Cambia entre el plan oficial o haz una prueba rápida subiendo o bajando un 5% la proyección."
            )
            if sel_sc != st.session_state["fiori_scenario"]:
                st.session_state["fiori_scenario"] = sel_sc
                st.session_state["fiori_scenario_factor"] = 1.05 if "+5%" in sel_sc else (0.95 if "-5%" in sel_sc else 1.0)
                st.rerun()

        with c_notif:
            with st.popover(f"🔔 Avisos ({n_alerts})", width="stretch"):
                st.markdown("##### 🔔 Avisos y Recordatorios")
                if not alert_items:
                    st.success("¡Todo al día! No tienes avisos pendientes.")
                else:
                    for aid, ainfo in alert_items:
                        st.markdown(f"**{ainfo.get('icono', '⚠️')} {ainfo.get('titulo', 'Aviso')}**")
                        st.caption(f"{ainfo.get('mensaje', '')} — *{ainfo.get('meta', '')}*")
                        ca1, ca2 = st.columns(2)
                        if ca1.button("✓ Listo", key=f"pop_res_{aid}", width="stretch"):
                            st.session_state["fiori_resolved_alerts"].add(aid)
                            st.rerun()
                        if ca2.button("Ocultar", key=f"pop_ign_{aid}", width="stretch"):
                            st.session_state["fiori_ignored_alerts"].add(aid)
                            st.rerun()
                        st.divider()

        with c_assist:
            with st.popover("✨ Ayuda", width="stretch"):
                st.markdown("##### ✨ Guía Rápida de la Plataforma")
                st.caption("Respuestas claras a las dudas más frecuentes sobre cómo calculamos la cosecha y la siembra.")
                st.info(
                    "📌 **Resumen del Cultivo Hoy:**\n"
                    "• **Proyección en 3 Etapas:** Semanas 1 a 10 (plantas ya sembradas en suelo) | Semanas 11 a 13 (bandejas reales en vivero) | Semana 14 en adelante (pedidos planeados).\n"
                    "• **Capacidad de la Finca:** Máximo 1,120 camas ocupadas al mismo tiempo.\n"
                    "• **Vivero Semana 42:** 466,193 esquejes reales registrados."
                )
                q_ask = st.selectbox(
                    "¿Sobre qué tema quieres consultar?",
                    [
                        "¿Cómo se calcula la flor que vamos a cosechar?",
                        "¿Cómo estamos preparados para San Valentín 2027?",
                        "¿Cómo funciona el reemplazo de esquejes en cuarto frío?"
                    ],
                    key="joule_quick_q"
                )
                if "cosechar" in q_ask:
                    st.markdown("**Respuesta:** Se arma uniendo 3 etapas sin duplicar datos: **1)** De la semana 1 a la 10 usamos lo que ya está sembrado en tierra; **2)** De la semana 11 a la 13 usamos los esquejes reales que ya están enraizando en vivero; **3)** De la semana 14 en adelante usamos el pedido de esquejes planeado.")
                elif "Valentín" in q_ask:
                    st.markdown("**Respuesta:** Para la semana pico de San Valentín (`202704`) esperamos cosechar **588,987 tallos** frente a una meta de ventas de **495,210 tallos** (118.9% de cumplimiento), respetando el límite físico de 1,120 camas.")
                else:
                    st.markdown("**Respuesta:** Si falta una variedad en cuarto frío, el sistema busca reemplazo en 3 pasos: **1)** Misma flor y mismo color, **2)** Otra flor del mismo color, o **3)** Mover a la semana siguiente, siempre asegurando al menos media cama (2,500 esquejes o 23 bandejas).")

        with c_me:
            with st.popover("👤 Perfil", width="stretch"):
                st.markdown("##### 👤 Mi Perfil y Preferencias")
                st.markdown("**Equipo:** Planeación y Operaciones")
                st.markdown("**Vista actual:** Diseño claro de alto contraste")
                if st.button("🔄 Volver a mostrar todos los avisos", width="stretch", key="btn_reset_alerts_me"):
                    st.session_state["fiori_resolved_alerts"] = set()
                    st.session_state["fiori_ignored_alerts"] = set()
                    st.rerun()

    # Resultados instantáneos del Buscador General
    if search_q and len(search_q.strip()) >= 2:
        q_clean = search_q.strip()
        with st.container(border=True):
            st.markdown(f"##### 🔍 Resultados de búsqueda para: `{q_clean}`")
            mod_matches = [
                m for sp in FIORI_SPACES.values() for m in sp["pages"]
                if q_clean.lower() in m.lower() or q_clean.lower() in PAGE_FRIENDLY_LABELS.get(m, "").lower()
            ]
            if mod_matches:
                st.markdown("**Secciones de la plataforma encontradas:**")
                cols_m = st.columns(min(4, len(mod_matches)))
                for idx_m, m_match in enumerate(mod_matches[:4]):
                    lbl_m = PAGE_FRIENDLY_LABELS.get(m_match, m_match)
                    if cols_m[idx_m].button(f"🚀 Ir a {lbl_m}", key=f"es_mod_{idx_m}", width="stretch"):
                        navigate_to_module(m_match)
                        st.rerun()

            try:
                q_like = f"%{q_clean.lower()}%"
                df_es_var = pd.read_sql(
                    """
                    SELECT v.nombre as "Variedad",
                           v.flor as "Tipo de Flor",
                           v.color as "Color",
                           ROUND(v.aprov_pp * 100, 1) as "Aprovechamiento (%)",
                           v.dia_inicio as "Día Inicio Cosecha",
                           v.dia_pico as "Día Pico Cosecha",
                           COUNT(s.id) as "Lotes en Suelo",
                           COALESCE(SUM(s.plantas_sembradas), 0) as "Plantas Sembradas"
                    FROM variedades v
                    LEFT JOIN siembras s ON s.variedad_id = v.id
                    WHERE LOWER(v.nombre) LIKE :q
                       OR LOWER(v.flor) LIKE :q
                       OR LOWER(v.color) LIKE :q
                    GROUP BY v.id
                    ORDER BY "Plantas Sembradas" DESC
                    LIMIT 15
                    """,
                    engine,
                    params={"q": q_like}
                )
                if not df_es_var.empty:
                    st.markdown("**Variedades encontradas en el catálogo y en campo:**")
                    st.dataframe(df_es_var, width="stretch", hide_index=True)
                else:
                    st.caption("No se encontraron variedades con ese nombre, flor o color.")
            except Exception as e_es:
                st.caption(f"No fue posible completar la búsqueda en este momento: {e_es}")

    # ==========================================================================
    # NAVEGACIÓN POR ÁREAS DE TRABAJO (PESTAÑAS SUPERIORES + MENÚ LATERAL)
    # ==========================================================================
    space_names = list(FIORI_SPACES.keys())
    active_mod = st.session_state["fiori_active_module"]
    active_sp = MODULE_TO_SPACE.get(active_mod, st.session_state.get("fiori_active_space", space_names[0]))
    if active_sp not in FIORI_SPACES:
        active_sp = space_names[0]

    st.markdown('<div class="fiori-spaces-bar">', unsafe_allow_html=True)
    cols_sp = st.columns(len(space_names))
    for i, sp_label in enumerate(space_names):
        is_active_sp = (sp_label == active_sp)
        btn_type = "primary" if is_active_sp else "secondary"
        if cols_sp[i].button(sp_label, key=f"fiori_sp_btn_{i}", type=btn_type, width="stretch"):
            first_page = FIORI_SPACES[sp_label]["pages"][0]
            navigate_to_module(first_page)
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # Sub-barra de secciones dentro del área activa
    pages_in_space = FIORI_SPACES[active_sp]["pages"]
    if len(pages_in_space) > 1:
        cols_pg = st.columns([1.3] * len(pages_in_space) + [max(0.4, 6 - len(pages_in_space) * 1.3)])
        for j, pg_name in enumerate(pages_in_space):
            is_act_pg = (pg_name == active_mod)
            pg_prefix = "● " if is_act_pg else "○ "
            pg_disp = PAGE_FRIENDLY_LABELS.get(pg_name, pg_name)
            if cols_pg[j].button(f"{pg_prefix}{pg_disp}", key=f"fiori_pg_btn_{j}", type="primary" if is_act_pg else "secondary", width="stretch"):
                navigate_to_module(pg_name)
                st.rerun()

    # Menú lateral sincronizado
    with st.sidebar:
        st.markdown("### 🧭 Menú de Secciones")
        st.caption("Selecciona directamente la herramienta que deseas abrir:")
        all_pages = [
            "Launchpad S&OP (Portada)",
            "Dashboard General",
            "ForeCast y Exportación",
            "Programación Diaria y Temporadas",
            "Plan de Producción (MVA)",
            "Ocupación de Área y Capacidad",
            "Pedido Material Vegetal",
            "Plan de Enraizamiento",
            "Plan de Siembra",
            "Curvas e Índices (Campo)",
            "Calibración de Curvas"
        ]
        idx_curr = all_pages.index(active_mod) if active_mod in all_pages else 1
        st.session_state["fiori_sidebar_radio_sync"] = all_pages[idx_curr]

        def _on_sidebar_nav():
            sel = st.session_state.get("fiori_sidebar_radio_sync")
            if sel:
                navigate_to_module(sel)

        st.radio(
            "Ir a la sección:",
            all_pages,
            format_func=lambda x: PAGE_FRIENDLY_LABELS.get(x, x),
            key="fiori_sidebar_radio_sync",
            on_change=_on_sidebar_nav
        )

        st.divider()
        st.markdown("#### 🎛️ Resumen de tu Vista")
        st.caption(f"**Área actual:** {active_sp}")
        st.caption(f"**Escenario:** {st.session_state['fiori_scenario']}")
        if st.session_state['fiori_scenario_factor'] != 1.0:
            st.caption(f"**Ajuste aplicado:** {st.session_state['fiori_scenario_factor']:.2f}x")

    return st.session_state["fiori_active_module"]


# ==============================================================================
# 2. CABECERA DE SECCIÓN, SELECTOR DE VISTAS Y BARRA INFERIOR
# ==============================================================================
def render_fiori_app_header(
    breadcrumb: str,
    title: str,
    subtitle: str,
    floorplan_badge: str = "Vista General",
    status_badge: str = "Activo",
    status_type: str = "ok",
    module_key: str = "default",
    export_df: pd.DataFrame = None,
    export_filename: str = "Reporte_Planeacion.csv"
) -> str:
    """
    Muestra la cabecera clara de cada sección:
    - Ruta de ubicación y título explicativo
    - Selector para cambiar o guardar vistas favoritas
    - Botones rápidos para actualizar o descargar datos
    """
    init_fiori_state()
    variants_dict = st.session_state["fiori_saved_variants"]
    variant_names = list(variants_dict.values())

    badge_cls = {
        "ok": "sap-badge-ok",
        "info": "sap-badge-info",
        "warn": "sap-badge-warn",
        "err": "sap-badge-err"
    }.get(status_type, "sap-badge-info")

    header_html = f"""
    <div class="fiori-app-header-box">
        <div class="fiori-app-header-top">
            <div>
                <div class="fiori-app-breadcrumb">{breadcrumb} &bull; <span class="fiori-fp-tag">{floorplan_badge}</span></div>
                <h1 class="fiori-app-title">{title}</h1>
                <p class="fiori-app-subtitle">{subtitle}</p>
            </div>
            <div class="fiori-app-badges">
                <span class="sap-badge {badge_cls}">{status_badge}</span>
            </div>
        </div>
    </div>
    """
    st.markdown(header_html, unsafe_allow_html=True)

    c_var, c_save_var, c_act1, c_act2 = st.columns([2.2, 0.9, 1.0, 1.0])
    with c_var:
        sel_var = st.selectbox(
            "Vistas guardadas:",
            variant_names,
            index=0,
            label_visibility="collapsed",
            key=f"fiori_var_sel_{module_key}",
            help="Elige un enfoque predefinido o una vista que hayas guardado."
        )
    with c_save_var:
        with st.popover("💾 Guardar Vista", width="stretch"):
            st.markdown("##### Guardar filtro o vista favorita")
            new_v_name = st.text_input("Nombre para recordar esta vista:", placeholder="Ej. Revisión de los lunes", key=f"inp_var_{module_key}")
            if st.button("Guardar en mi lista", type="primary", width="stretch", key=f"btn_sv_var_{module_key}"):
                if new_v_name.strip():
                    st.session_state["fiori_saved_variants"][new_v_name.strip()] = f"★ {new_v_name.strip()}"
                    st.toast(f"✅ Vista '{new_v_name.strip()}' guardada correctamente.")
                    st.rerun()

    with c_act1:
        if export_df is not None and not export_df.empty:
            csv_bytes = export_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "📤 Descargar Tabla",
                data=csv_bytes,
                file_name=export_filename,
                mime="text/csv",
                key=f"fiori_glob_exp_{module_key}",
                width="stretch"
            )
        else:
            if st.button("🔄 Actualizar Datos", key=f"fiori_glob_sync_{module_key}", width="stretch"):
                st.toast("🔄 Información actualizada con los últimos datos guardados.")
                st.rerun()

    with c_act2:
        with st.popover("⚙️ Pantalla", width="stretch"):
            st.markdown("##### Preferencias de visualización")
            st.checkbox("Tablas compactas (ver más filas)", value=True, key=f"chk_compact_{module_key}")
            st.checkbox("Resaltar alertas con colores", value=True, key=f"chk_dev_{module_key}")
            st.caption(f"Vista seleccionada: **{sel_var}**")

    return sel_var


def render_fiori_footer_toolbar(
    module_key: str = "default",
    primary_label: str = "🔄 Actualizar Vista",
    secondary_label: str = "🏠 Ir a la Portada",
    cancel_label: str = "⬆️ Subir al Inicio",
    status_text: str = "Datos conectados y actualizados",
    key_prefix: str = None
) -> tuple[bool, bool, bool]:
    """
    Muestra la barra inferior de apoyo con el estado actual y botones de acceso rápido.
    Acepta tanto `module_key` como `key_prefix` para total compatibilidad.
    """
    eff_key = key_prefix if key_prefix else module_key
    st.markdown(
        f"""
        <div class="fiori-footer-banner">
            <span class="fiori-footer-status">🟢 <b>Estado del Sistema:</b> {status_text}</span>
            <span class="fiori-footer-hint">Datos sincronizados en tiempo real</span>
        </div>
        """,
        unsafe_allow_html=True
    )
    c_info, c_canc, c_sec, c_pri = st.columns([2.5, 1.0, 1.2, 1.4])
    with c_info:
        st.caption(f"⚡ Escenario en pantalla: **{st.session_state.get('fiori_scenario', 'Plan Base (Oficial)')}**")
    with c_canc:
        b_canc = st.button(cancel_label, key=f"fiori_ft_canc_{eff_key}", width="stretch")
    with c_sec:
        b_sec = st.button(secondary_label, key=f"fiori_ft_sec_{eff_key}", width="stretch")
    with c_pri:
        b_pri = st.button(primary_label, key=f"fiori_ft_pri_{eff_key}", type="primary", width="stretch")
    return b_pri, b_sec, b_canc


# ==============================================================================
# 3. PORTADA PRINCIPAL: TARJETAS CON INDICADORES Y MINI-GRÁFICAS
# ==============================================================================
def render_fiori_launchpad_home(db, engine, alertas_sop: dict, key_suffix: str = "home"):
    """
    Muestra la portada principal con tarjetas fáciles de leer, cifras al día
    y acceso en un clic a cada sección de la plataforma.
    """
    df_m = pd.read_sql(
        """
        SELECT count(distinct s.variedad_id) as vars_activas,
               count(s.id) as camas,
               sum(s.plantas_sembradas) as plantas,
               sum(s.area_m2) as area_ocupada
        FROM siembras s
        """,
        engine
    )
    vars_act = int(df_m["vars_activas"].iloc[0] or 0) if not df_m.empty else 0
    camas_act = int(df_m["camas"].iloc[0] or 0) if not df_m.empty else 0
    plantas_act = int(df_m["plantas"].iloc[0] or 0) if not df_m.empty else 0
    area_act = float(df_m["area_ocupada"].iloc[0] or 0.0) if not df_m.empty else 0.0

    st.markdown(
        """
        <div class="fiori-launchpad-hero">
            <div>
                <div class="fiori-hero-kicker">PORTADA PRINCIPAL &bull; PLANEACIÓN DE CULTIVO Y COMERCIALIZACIÓN</div>
                <h2 class="fiori-hero-title">Centro de Control de la Finca</h2>
                <p class="fiori-hero-desc">Aquí tienes el resumen al día de cada etapa del proceso. Haz clic en cualquier tarjeta para entrar directamente a esa sección.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("#### 📊 Acceso Rápido a las Secciones e Indicadores del Día")

    tiles_data = [
        {
            "title": "Tablero General",
            "subtitle": "Resumen de la finca y carga de archivos",
            "module": "Dashboard General",
            "kpi": f"{camas_act:,}",
            "unit": "Lotes en Suelo",
            "footer": f"{plantas_act:,.0f} plantas en {area_act:,.0f} m²",
            "status": "ok",
            "svg": """<svg viewBox="0 0 120 32" width="100%" height="32"><polyline fill="none" stroke="#106333" stroke-width="2.5" points="4,24 26,20 48,22 70,14 92,16 116,8"/><circle cx="116" cy="8" r="3.5" fill="#106333"/></svg>"""
        },
        {
            "title": "Proyección de Cosecha",
            "subtitle": "Comparativo Cosecha vs. Ventas",
            "module": "ForeCast y Exportación",
            "kpi": "102.7%",
            "unit": "Cumplimiento Anual",
            "footer": "En suelo (S1-10) + Vivero (S11-13) + Pedido (S14+)",
            "status": "ok",
            "svg": """<svg viewBox="0 0 120 32" width="100%" height="32"><rect x="6" y="14" width="12" height="16" rx="2" fill="#059669"/><rect x="24" y="10" width="12" height="20" rx="2" fill="#059669"/><rect x="42" y="16" width="12" height="14" rx="2" fill="#D97706"/><rect x="60" y="12" width="12" height="18" rx="2" fill="#D97706"/><rect x="78" y="6" width="12" height="24" rx="2" fill="#7C3AED"/><rect x="96" y="8" width="12" height="22" rx="2" fill="#7C3AED"/></svg>"""
        },
        {
            "title": "Plan Maestro de Producción",
            "subtitle": "Acuerdos entre ventas y cultivo",
            "module": "Plan de Producción (MVA)",
            "kpi": "16.05M",
            "unit": "Tallos Meta (52 sem)",
            "footer": "Revisión de pedidos y mezcla de variedades",
            "status": "info",
            "svg": """<svg viewBox="0 0 120 32" width="100%" height="32"><line x1="4" y1="26" x2="116" y2="26" stroke="#CBD5E1" stroke-width="2"/><polyline fill="none" stroke="#0057D2" stroke-width="2.5" points="6,22 30,18 54,8 78,19 102,12 114,14"/></svg>"""
        },
        {
            "title": "Espacio en Invernaderos",
            "subtitle": "Ocupación de camas por bloque",
            "module": "Ocupación de Área y Capacidad",
            "kpi": "1,120",
            "unit": "Máximo de Camas",
            "footer": "Sin sobrecupo • Alistamiento 7 y 3 días",
            "status": "ok",
            "svg": """<svg viewBox="0 0 120 32" width="100%" height="32"><rect x="4" y="10" width="112" height="12" rx="6" fill="#E2E8F0"/><rect x="4" y="10" width="94" height="12" rx="6" fill="#0284C7"/><line x1="106" y1="6" x2="106" y2="26" stroke="#A61C1C" stroke-width="2.5"/></svg>"""
        },
        {
            "title": "Plan de Vivero (Enraizamiento)",
            "subtitle": "Bandejas, cuarto frío y clavado",
            "module": "Plan de Enraizamiento",
            "kpi": "466.2k",
            "unit": "Esquejes Sem. 42",
            "footer": "Inventario en frío, reemplazos y PDF",
            "status": "warn",
            "svg": """<svg viewBox="0 0 120 32" width="100%" height="32"><rect x="8" y="18" width="16" height="12" rx="2" fill="#D97706"/><rect x="32" y="14" width="16" height="16" rx="2" fill="#D97706"/><rect x="56" y="9" width="16" height="21" rx="2" fill="#106333"/><rect x="80" y="5" width="16" height="25" rx="2" fill="#0057D2"/></svg>"""
        },
        {
            "title": "Pedido de Esquejes",
            "subtitle": "Solicitud a proveedores",
            "module": "Pedido Material Vegetal",
            "kpi": "28.45M",
            "unit": "Esquejes al Año",
            "footer": "Control de las 24 semanas y cambios a tiempo",
            "status": "info",
            "svg": """<svg viewBox="0 0 120 32" width="100%" height="32"><polyline fill="none" stroke="#7C3AED" stroke-width="2.5" points="6,20 28,19 50,7 72,15 94,10 114,16"/></svg>"""
        },
        {
            "title": "Plan de Siembra en Campo",
            "subtitle": "Trasplante semanal a camas",
            "module": "Plan de Siembra",
            "kpi": "40/30/30",
            "unit": "Reparto S45-S47",
            "footer": "Asignación de bloques, desbotone y PDF",
            "status": "ok",
            "svg": """<svg viewBox="0 0 120 32" width="100%" height="32"><circle cx="20" cy="16" r="6" fill="#106333"/><line x1="26" y1="16" x2="54" y2="16" stroke="#106333" stroke-width="2"/><circle cx="60" cy="16" r="6" fill="#0057D2"/><line x1="66" y1="16" x2="94" y2="16" stroke="#0057D2" stroke-width="2"/><circle cx="100" cy="16" r="6" fill="#7C3AED"/></svg>"""
        },
        {
            "title": "Corte Diario y Temporadas",
            "subtitle": "Reparto de lunes a sábado",
            "module": "Programación Diaria y Temporadas",
            "kpi": "42.0h",
            "unit": "Jornada Semanal",
            "footer": "Tallos por día y seguimiento a San Valentín",
            "status": "info",
            "svg": """<svg viewBox="0 0 120 32" width="100%" height="32"><rect x="6" y="12" width="12" height="18" fill="#0057D2"/><rect x="22" y="12" width="12" height="18" fill="#0057D2"/><rect x="38" y="14" width="12" height="16" fill="#0284C7"/><rect x="54" y="6" width="12" height="24" fill="#106333"/><rect x="70" y="12" width="12" height="18" fill="#0057D2"/><rect x="86" y="18" width="12" height="12" fill="#64748B"/></svg>"""
        },
        {
            "title": "Rendimiento en Campo",
            "subtitle": "Curvas de cosecha por variedad",
            "module": "Curvas e Índices (Campo)",
            "kpi": "83",
            "unit": "Curvas Reales",
            "footer": f"{vars_act} variedades sembradas actualmente",
            "status": "ok",
            "svg": """<svg viewBox="0 0 120 32" width="100%" height="32"><path d="M 6 28 Q 45 26 60 6 T 114 28" fill="none" stroke="#059669" stroke-width="2.8"/></svg>"""
        },
        {
            "title": "Ajuste y Precisión de Curvas",
            "subtitle": "Comparativo proyectado vs. real",
            "module": "Calibración de Curvas",
            "kpi": "99.2%",
            "unit": "Nivel de Acierto",
            "footer": "Mejora continua de los cálculos de cosecha",
            "status": "info",
            "svg": """<svg viewBox="0 0 120 32" width="100%" height="32"><polyline fill="none" stroke="#0057D2" stroke-width="2" points="6,24 35,14 65,10 95,18 114,12"/><polyline fill="none" stroke="#106333" stroke-width="2" stroke-dasharray="3,3" points="6,22 35,15 65,12 95,16 114,11"/></svg>"""
        }
    ]

    for row_start in range(0, len(tiles_data), 5):
        row_items = tiles_data[row_start:row_start + 5]
        cols_t = st.columns(5)
        for idx_t, t in enumerate(row_items):
            with cols_t[idx_t]:
                tile_html = f"""
                <div class="fiori-kpi-tile">
                    <div class="fiori-tile-header">
                        <div class="fiori-tile-title">{t['title']}</div>
                        <div class="fiori-tile-subtitle">{t['subtitle']}</div>
                    </div>
                    <div class="fiori-tile-body">
                        <div class="fiori-tile-kpi-row">
                            <span class="fiori-tile-kpi-val">{t['kpi']}</span>
                            <span class="fiori-tile-kpi-unit">{t['unit']}</span>
                        </div>
                        <div class="fiori-tile-microchart">{t['svg']}</div>
                    </div>
                    <div class="fiori-tile-footer">{t['footer']}</div>
                </div>
                """
                st.markdown(tile_html, unsafe_allow_html=True)
                if st.button(f"Abrir {t['title'][:18]}", key=f"btn_launch_tile_{key_suffix}_{row_start+idx_t}", width="stretch"):
                    navigate_to_module(t["module"])
                    st.rerun()


# ==============================================================================
# 4. TARJETAS DE RESUMEN DEL CULTIVO, LISTA DE AVISOS Y FILTROS VISUALES
# ==============================================================================
def render_fiori_ovp_cards(engine, db, key_suffix: str = "ovp"):
    """
    Muestra 3 tarjetas claras de resumen en el Tablero General:
    1. Gráfica de barras con las plantas sembradas por tipo de flor.
    2. Las 5 variedades con más o con menos plantas en suelo.
    3. Tabla consolidada de variedades, lotes, plantas y área por tipo de flor.
    """
    st.markdown("#### 🧩 Resumen Visual del Cultivo Actual en Tierra")
    c_ovp1, c_ovp2, c_ovp3 = st.columns([1.35, 1.15, 1.3])

    df_flor = pd.read_sql(
        """
        SELECT v.flor as "Flor",
               count(distinct v.id) as "Variedades",
               count(s.id) as "Lotes",
               sum(s.plantas_sembradas) as "Plantas",
               round(sum(s.area_m2), 1) as "Area_m2"
        FROM siembras s
        JOIN variedades v ON s.variedad_id = v.id
        GROUP BY v.flor
        ORDER BY "Plantas" DESC
        """,
        engine
    )

    df_top_vars = pd.read_sql(
        """
        SELECT v.nombre as "Variedad",
               v.flor as "Flor",
               v.color as "Color",
               count(s.id) as "Camas",
               sum(s.plantas_sembradas) as "Plantas",
               round(v.aprov_pp * 100, 1) as "Aprov_Pct"
        FROM siembras s
        JOIN variedades v ON s.variedad_id = v.id
        GROUP BY v.id
        ORDER BY "Plantas" DESC
        """,
        engine
    )

    # TARJETA 1: GRÁFICA POR TIPO DE FLOR
    with c_ovp1:
        with st.container(border=True):
            st.markdown(
                """
                <div class="fiori-card-hdr">
                    <span class="fiori-card-tag">GRÁFICA COMPARATIVA</span>
                    <div class="fiori-card-title">Plantas Sembradas por Tipo de Flor</div>
                    <div class="fiori-card-sub">Cantidad actual de plantas vivas en suelo</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if not df_flor.empty:
                fig_ovp = go.Figure(go.Bar(
                    x=df_flor["Plantas"],
                    y=df_flor["Flor"],
                    orientation="h",
                    marker=dict(color=["#0057D2", "#106333", "#D97706", "#7C3AED", "#0284C7", "#475569"][:len(df_flor)]),
                    text=[f"{v:,.0f}" for v in df_flor["Plantas"]],
                    textposition="auto"
                ))
                fig_ovp.update_layout(
                    height=255,
                    margin=dict(l=10, r=10, t=10, b=10),
                    paper_bgcolor="#FFFFFF",
                    plot_bgcolor="#FFFFFF",
                    xaxis=dict(showgrid=True, gridcolor="#EDF0F2", title="Plantas en Suelo"),
                    yaxis=dict(autorange="reversed")
                )
                st.plotly_chart(fig_ovp, width="stretch", key=f"ovp_bar_chart_{key_suffix}")

    # TARJETA 2: LAS 5 VARIEDADES CON MÁS / MENOS PLANTAS
    with c_ovp2:
        with st.container(border=True):
            st.markdown(
                """
                <div class="fiori-card-hdr">
                    <span class="fiori-card-tag">LISTADO DESTACADO</span>
                    <div class="fiori-card-title">Variedades con Mayor y Menor Siembra</div>
                    <div class="fiori-card-sub">Consulta rápida de las 5 principales o las 5 más pequeñas</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            mode_list = st.segmented_control(
                "Filtro de variedades",
                ["5 con Más Plantas", "5 con Menos Plantas"],
                default="5 con Más Plantas",
                label_visibility="collapsed",
                key=f"ovp_list_card_toggle_{key_suffix}"
            )
            if not df_top_vars.empty:
                sub_v = df_top_vars.head(5) if mode_list == "5 con Más Plantas" else df_top_vars.tail(5).sort_values("Plantas", ascending=True)
                max_p = max(1, df_top_vars["Plantas"].max())
                list_html = '<div class="fiori-list-card-items">'
                for _, rv in sub_v.iterrows():
                    pct_w = min(100, max(6, int(rv["Plantas"] / max_p * 100)))
                    list_html += f"""
                    <div class="fiori-list-item">
                        <div class="fiori-list-row-top">
                            <span class="fiori-list-sku">{rv['Variedad']} <small>({rv['Flor']} - {rv['Color']})</small></span>
                            <span class="fiori-list-val">{int(rv['Plantas']):,} pl ({int(rv['Camas'])} lotes)</span>
                        </div>
                        <div class="fiori-list-bar-bg">
                            <div class="fiori-list-bar-fill" style="width:{pct_w}%;"></div>
                        </div>
                    </div>
                    """
                list_html += "</div>"
                st.markdown(list_html, unsafe_allow_html=True)

    # TARJETA 3: TABLA RESUMEN
    with c_ovp3:
        with st.container(border=True):
            st.markdown(
                """
                <div class="fiori-card-hdr">
                    <span class="fiori-card-tag">TABLA RESUMEN</span>
                    <div class="fiori-card-title">Consolidado por Tipo de Flor</div>
                    <div class="fiori-card-sub">Variedades activas, lotes sembrados, plantas y área</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if not df_flor.empty:
                st.dataframe(
                    df_flor.style.format({
                        "Variedades": "{:,.0f}",
                        "Lotes": "{:,.0f}",
                        "Plantas": "{:,.0f}",
                        "Area_m2": "{:,.1f} m²"
                    }),
                    width="stretch",
                    hide_index=True,
                    height=255
                )


def render_fiori_worklist_alertas(alertas_sop: dict, key_suffix: str = "wl"):
    """
    Muestra la lista interactiva de avisos importantes y compromisos de la semana,
    permitiendo abrir la sección correspondiente o marcar un aviso como listo.
    """
    init_fiori_state()
    st.markdown("#### ⚡ Avisos Importantes y Fechas de Corte")

    rows = []
    module_map = {
        "regla_13wk": "ForeCast y Exportación",
        "regla_52wk": "ForeCast y Exportación",
        "regla_piedra_24wk": "Pedido Material Vegetal",
        "regla_enraizamiento": "Plan de Enraizamiento"
    }
    for k, v in (alertas_sop or {}).items():
        if isinstance(v, dict) and v.get("titulo"):
            aid = f"alert_{k}"
            estado_actual = (
                "✅ Revisado" if aid in st.session_state["fiori_resolved_alerts"]
                else ("⚪ Oculto" if aid in st.session_state["fiori_ignored_alerts"] else "🟠 Pendiente por revisar")
            )
            mod_dest = module_map.get(k, "Dashboard General")
            rows.append({
                "id": aid,
                "Aviso / Compromiso": f"{v.get('icono', '📌')} {v.get('titulo', '')}",
                "Estado": v.get("badge_texto", "Activo"),
                "¿Qué debemos tener en cuenta?": v.get("mensaje", ""),
                "Fecha / Meta": v.get("meta", ""),
                "Sección Relacionada": PAGE_FRIENDLY_LABELS.get(mod_dest, mod_dest),
                "_mod_raw": mod_dest,
                "Seguimiento": estado_actual
            })

    if not rows:
        st.info("No hay avisos pendientes en este momento.")
        return

    df_wl = pd.DataFrame(rows)
    with st.container(border=True):
        c_wl_top1, c_wl_top2, c_wl_top3 = st.columns([2.2, 1.3, 1.2])
        with c_wl_top1:
            filtro_est = st.segmented_control(
                "Filtrar avisos:",
                ["Todos", "Pendientes", "Revisados"],
                default="Todos",
                label_visibility="collapsed",
                key=f"wl_seg_filter_{key_suffix}"
            )
        with c_wl_top2:
            sel_rule_action = st.selectbox(
                "Elige un aviso para ir a su sección o marcarlo como revisado:",
                df_wl["Aviso / Compromiso"].tolist(),
                label_visibility="collapsed",
                key=f"wl_sel_inline_rule_{key_suffix}"
            )
        with c_wl_top3:
            b_go, b_ok = st.columns(2)
            row_sel = df_wl[df_wl["Aviso / Compromiso"] == sel_rule_action].iloc[0]
            if b_go.button("🚀 Ir allá", key=f"wl_btn_open_mod_{key_suffix}", width="stretch", help=f"Ir a {row_sel['Sección Relacionada']}"):
                navigate_to_module(row_sel["_mod_raw"])
                st.rerun()
            if b_ok.button("✓ Ya revisé", key=f"wl_btn_resolve_inline_{key_suffix}", width="stretch"):
                st.session_state["fiori_resolved_alerts"].add(row_sel["id"])
                st.toast(f"✅ Aviso '{sel_rule_action}' marcado como revisado.")
                st.rerun()

        if filtro_est == "Pendientes":
            df_wl_disp = df_wl[df_wl["Seguimiento"] == "🟠 Pendiente por revisar"]
        elif filtro_est == "Revisados":
            df_wl_disp = df_wl[df_wl["Seguimiento"] == "✅ Revisado"]
        else:
            df_wl_disp = df_wl

        st.dataframe(
            df_wl_disp[["Aviso / Compromiso", "Estado", "¿Qué debemos tener en cuenta?", "Fecha / Meta", "Sección Relacionada", "Seguimiento"]],
            width="stretch",
            hide_index=True
        )


def render_fiori_visual_filter_bar(
    df_forecast: pd.DataFrame,
    semanas_futuras: list[str],
    plan_series_cap: pd.Series,
    module_key: str = "alp_fc"
) -> dict:
    """
    Muestra 3 mini-gráficas en la parte superior para filtrar fácilmente por tipo de flor,
    ver el peso de cada etapa del cultivo y elegir si se desea ver Gráfica y Tabla, Solo Gráfica o Solo Tabla.
    """
    st.markdown("##### 📊 Filtros Rápidos con Mini-Gráficas")
    c_vf1, c_vf2, c_vf3 = st.columns([1.35, 1.35, 1.3])

    flores_all = sorted(df_forecast["Flor"].dropna().unique().tolist()) if "Flor" in df_forecast.columns else []
    flor_totals = df_forecast.groupby("Flor")[semanas_futuras].sum().sum(axis=1).sort_values(ascending=False) if flores_all and semanas_futuras else pd.Series(dtype=float)

    with c_vf1:
        with st.container(border=True):
            st.caption("**1. Filtrar por Tipo de Flor (Tallos Esperados)**")
            if not flor_totals.empty:
                fig_vf1 = go.Figure(go.Bar(
                    x=flor_totals.index.tolist(),
                    y=flor_totals.values.tolist(),
                    marker_color="#0057D2",
                    text=[f"{v/1e3:.0f}k" for v in flor_totals.values],
                    textposition="outside"
                ))
                fig_vf1.update_layout(
                    height=115,
                    margin=dict(l=4, r=4, t=14, b=4),
                    paper_bgcolor="#FFFFFF",
                    plot_bgcolor="#FFFFFF",
                    xaxis=dict(tickfont=dict(size=10)),
                    yaxis=dict(visible=False)
                )
                st.plotly_chart(fig_vf1, width="stretch", key=f"vf1_chart_{module_key}")
            sel_flor_vf = st.multiselect(
                "Filtrar por flor:",
                flores_all,
                default=[],
                placeholder="Todas las flores (haz clic para elegir una o varias)",
                label_visibility="collapsed",
                key=f"vf_sel_flor_{module_key}"
            )

    with c_vf2:
        with st.container(border=True):
            st.caption("**2. Volumen por Etapa del Cultivo**")
            s_t1 = semanas_futuras[:min(10, len(semanas_futuras))]
            s_t2 = semanas_futuras[10:min(13, len(semanas_futuras))] if len(semanas_futuras) > 10 else []
            s_t3 = semanas_futuras[13:] if len(semanas_futuras) > 13 else []
            v_t1 = float(df_forecast[s_t1].sum().sum()) if s_t1 else 0.0
            v_t2 = float(df_forecast[s_t2].sum().sum()) if s_t2 else 0.0
            v_t3 = float(df_forecast[s_t3].sum().sum()) if s_t3 else 0.0

            fig_vf2 = go.Figure(go.Bar(
                x=["1. En Suelo", "2. En Vivero", "3. Por Pedir"],
                y=[v_t1, v_t2, v_t3],
                marker_color=["#059669", "#D97706", "#7C3AED"],
                text=[f"{v/1e3:.0f}k" for v in [v_t1, v_t2, v_t3]],
                textposition="outside"
            ))
            fig_vf2.update_layout(
                height=115,
                margin=dict(l=4, r=4, t=14, b=4),
                paper_bgcolor="#FFFFFF",
                plot_bgcolor="#FFFFFF",
                xaxis=dict(tickfont=dict(size=10)),
                yaxis=dict(visible=False)
            )
            st.plotly_chart(fig_vf2, width="stretch", key=f"vf2_chart_{module_key}")
            sel_tramo_vf = st.selectbox(
                "Etapa a revisar:",
                [
                    "Todas las Etapas (Vista Completa)",
                    "Etapa 1: Plantas en Suelo (Semanas 1 a 10)",
                    "Etapa 2: Bandejas Reales en Vivero (Semanas 11 a 13)",
                    "Etapa 3: Pedido de Esquejes Planeado (Semana 14+)"
                ],
                index=0,
                label_visibility="collapsed",
                key=f"vf_sel_tramo_{module_key}"
            )

    with c_vf3:
        with st.container(border=True):
            st.caption("**3. ¿Cómo prefieres ver la información?**")
            tot_of_vf = v_t1 + v_t2 + v_t3
            tot_de_vf = float(plan_series_cap.sum()) if plan_series_cap is not None else 0.0
            fig_vf3 = go.Figure(go.Bar(
                x=["Cosecha Esperada", "Meta Comercial"],
                y=[tot_of_vf, tot_de_vf],
                marker_color=["#106333", "#0070F2"],
                text=[f"{tot_of_vf/1e3:.0f}k", f"{tot_de_vf/1e3:.0f}k"],
                textposition="outside"
            ))
            fig_vf3.update_layout(
                height=115,
                margin=dict(l=4, r=4, t=14, b=4),
                paper_bgcolor="#FFFFFF",
                plot_bgcolor="#FFFFFF",
                xaxis=dict(tickfont=dict(size=10)),
                yaxis=dict(visible=False)
            )
            st.plotly_chart(fig_vf3, width="stretch", key=f"vf3_chart_{module_key}")
            alp_view_mode = st.segmented_control(
                "Modo de visualización:",
                ["📊 Híbrida", "📈 Gráfica", "📋 Tabla"],
                default="📊 Híbrida",
                label_visibility="collapsed",
                key=f"vf_alp_mode_{module_key}"
            )

    return {
        "flores": sel_flor_vf,
        "tramo": sel_tramo_vf,
        "alp_mode": alp_view_mode or "📊 Híbrida"
    }


# ==============================================================================
# 5. TABLA DINÁMICA Y SIMULADOR DE CANTIDADES (CON REPARTO AUTOMÁTICO)
# ==============================================================================
def render_fiori_ibp_planning_grid(
    df_forecast: pd.DataFrame,
    semanas_futuras: list[str],
    df_plan_app: pd.DataFrame = None,
    module_key: str = "fc_ibp_grid"
):
    """
    Tabla Dinámica tipo Excel para explorar y simular números fácilmente:
    - Filas: Por Tipo de Flor | Por Flor y Color | Por Flor, Color y Variedad
    - Columnas: Por Semanas | Por Meses (bloques de 4 semanas)
    - Dato a mostrar: Tallos Esperados | Camas Necesarias | Esquejes Necesarios
    - Modo de prueba: Permite cambiar celdas o cambiar el total para que se reparta automáticamente.
    """
    st.markdown("#### 🧮 Tabla Dinámica y Simulador de Cantidades")
    st.caption("Agrupa los datos como te resulte más cómodo (por flor, color o variedad), míralos por semanas o por meses, o activa el modo de prueba para simular cambios en los totales.")

    with st.container(border=True):
        c_pg1, c_pg2, c_pg3, c_pg4 = st.columns([1.3, 1.2, 1.3, 1.1])
        with c_pg1:
            y_axis_dim = st.selectbox(
                "Agrupar filas por:",
                ["Tipo de Flor", "Flor y Color", "Flor, Color y Variedad"],
                index=0,
                key=f"ibp_yaxis_{module_key}"
            )
        with c_pg2:
            x_axis_bucket = st.selectbox(
                "Agrupar tiempo por:",
                ["Semanas", "Meses (Bloques de 4 Semanas)"],
                index=0,
                key=f"ibp_xaxis_{module_key}"
            )
        with c_pg3:
            key_figure = st.selectbox(
                "Dato que deseas ver:",
                ["Tallos Esperados", "Camas Necesarias (aprox. ÷5,200)", "Esquejes Necesarios (÷0.835)"],
                index=0,
                key=f"ibp_kf_{module_key}"
            )
        with c_pg4:
            edit_mode = st.toggle("✏️ Modo de Prueba (Editar)", value=False, key=f"ibp_edit_toggle_{module_key}")

        scen_factor = st.session_state.get("fiori_scenario_factor", 1.0)
        df_work = df_forecast.copy()
        for s in semanas_futuras:
            if s in df_work.columns:
                df_work[s] = df_work[s] * scen_factor
                if "Camas" in key_figure:
                    df_work[s] = df_work[s] / 5200.0
                elif "Esquejes" in key_figure:
                    df_work[s] = df_work[s] / 0.835

        if y_axis_dim == "Tipo de Flor":
            grp_cols = ["Flor"]
        elif y_axis_dim == "Flor y Color":
            grp_cols = ["Flor", "Color"]
        else:
            grp_cols = ["Flor", "Color", "Variedad"]

        grp_cols = [c for c in grp_cols if c in df_work.columns]
        df_piv = df_work.groupby(grp_cols, as_index=False)[semanas_futuras].sum()

        time_cols = semanas_futuras
        if x_axis_bucket == "Meses (Bloques de 4 Semanas)":
            bucket_cols = []
            for idx_b in range(0, len(semanas_futuras), 4):
                chunk = semanas_futuras[idx_b:idx_b + 4]
                b_name = f"Mes {(idx_b//4)+1} ({chunk[0]}-{chunk[-1][-2:]})"
                df_piv[b_name] = df_piv[chunk].sum(axis=1)
                bucket_cols.append(b_name)
            df_piv = df_piv[grp_cols + bucket_cols]
            time_cols = bucket_cols

        df_piv["TOTAL PERIODO"] = df_piv[time_cols].sum(axis=1)
        df_piv = df_piv[df_piv["TOTAL PERIODO"] > 0].reset_index(drop=True)

        fmt_str = "{:,.1f}" if "Camas" in key_figure else "{:,.0f}"

        if not edit_mode:
            tot_row = {c: "" for c in grp_cols}
            tot_row[grp_cols[0]] = "TOTAL GENERAL"
            for tc in time_cols + ["TOTAL PERIODO"]:
                tot_row[tc] = df_piv[tc].sum()
            df_disp_grid = pd.concat([df_piv, pd.DataFrame([tot_row])], ignore_index=True)

            st.dataframe(
                df_disp_grid.style.format({tc: fmt_str for tc in time_cols + ["TOTAL PERIODO"]}),
                width="stretch",
                hide_index=True
            )
        else:
            st.info(
                "✏️ **Modo de Prueba Activo:** Haz doble clic sobre cualquier número para cambiarlo. "
                "Si cambias la columna `TOTAL PERIODO` de una fila, el sistema repartirá automáticamente esa nueva cantidad entre todas las semanas."
            )
            edited_df = st.data_editor(
                df_piv,
                width="stretch",
                hide_index=True,
                disabled=grp_cols,
                key=f"ibp_data_editor_{module_key}"
            )
            disagg_rows = 0
            for idx_r in range(len(edited_df)):
                orig_tot = float(df_piv.loc[idx_r, "TOTAL PERIODO"])
                new_tot = float(edited_df.loc[idx_r, "TOTAL PERIODO"])
                sum_periods = float(edited_df.loc[idx_r, time_cols].sum())
                if abs(new_tot - orig_tot) > 1.0 and abs(sum_periods - orig_tot) < 1.0 and orig_tot > 0:
                    ratio_disagg = new_tot / orig_tot
                    for tc in time_cols:
                        edited_df.loc[idx_r, tc] = round(edited_df.loc[idx_r, tc] * ratio_disagg, 1 if "Camas" in key_figure else 0)
                    disagg_rows += 1
                else:
                    edited_df.loc[idx_r, "TOTAL PERIODO"] = sum_periods

            if disagg_rows > 0:
                st.success(f"⚡ **Reparto Automático Aplicado:** Se ajustaron proporcionalmente las semanas en {disagg_rows} fila(s) según el nuevo total ingresado.")
                st.dataframe(
                    edited_df.style.format({tc: fmt_str for tc in time_cols + ["TOTAL PERIODO"]}),
                    width="stretch",
                    hide_index=True
                )


# ==============================================================================
# 6. MAPA DEL RECORRIDO DEL CULTIVO (DEL PROVEEDOR A LA COSECHA)
# ==============================================================================
def render_fiori_supply_chain_canvas(engine, key_suffix: str = "canvas"):
    """
    Muestra un mapa visual paso a paso de cómo avanza la planta por la finca:
    Proveedores -> Cuarto Frío -> Bancos de Vivero -> Bloques de Campo 01 a 06 -> Cosecha y Despacho.
    """
    st.markdown("#### 🕸️ Recorrido del Cultivo: Del Proveedor a la Cosecha")
    st.caption("Mapa visual paso a paso: Proveedores de Esquejes ➔ Cuarto Frío ➔ Vivero (3 semanas) ➔ Bloques de Campo (01 al 06) ➔ Cosecha y Ventas.")

    with st.container(border=True):
        nodes = [
            {"id": "prov", "x": 0.05, "y": 0.50, "label": "1. Proveedores de Esquejes\n(Pedidos con 24 sem. de anticipación)\n28.4M Esquejes/Año", "color": "#7C3AED", "size": 34},
            {"id": "frio", "x": 0.25, "y": 0.50, "label": "2. Cuarto Frío (Recepción)\n(Reemplazos en 3 pasos)\nMínimo media cama (2,500 esq.)", "color": "#0284C7", "size": 36},
            {"id": "prop", "x": 0.46, "y": 0.50, "label": "3. Vivero (Enraizamiento)\n(21 días en banco / 3 semanas)\nSem. 42: 466,193 Esquejes", "color": "#D97706", "size": 40},
            {"id": "b01", "x": 0.70, "y": 0.88, "label": "Bloque 01 (192 Camas)\n5,081 plantas/cama", "color": "#106333", "size": 26},
            {"id": "b02", "x": 0.70, "y": 0.73, "label": "Bloque 02 (192 Camas)\n5,119 plantas/cama", "color": "#106333", "size": 26},
            {"id": "b03", "x": 0.70, "y": 0.58, "label": "Bloque 03 (192 Camas)\n5,254 plantas/cama", "color": "#106333", "size": 26},
            {"id": "b04", "x": 0.70, "y": 0.42, "label": "Bloque 04 (192 Camas)\n4,761 plantas/cama", "color": "#106333", "size": 26},
            {"id": "b05", "x": 0.70, "y": 0.27, "label": "Bloque 05 (192 Camas)\n4,511 plantas/cama", "color": "#106333", "size": 26},
            {"id": "b06", "x": 0.70, "y": 0.12, "label": "Bloque 06 (216 Camas)\n4,470 plantas/cama", "color": "#106333", "size": 26},
            {"id": "cos", "x": 0.94, "y": 0.50, "label": "5. Cosecha y Despacho\n(Máximo 1,120 camas activas)\n16.47M Tallos (102.7% Meta)", "color": "#0057D2", "size": 42}
        ]
        node_map = {n["id"]: n for n in nodes}
        edges = [
            ("prov", "frio"),
            ("frio", "prop"),
            ("prop", "b01"), ("prop", "b02"), ("prop", "b03"), ("prop", "b04"), ("prop", "b05"), ("prop", "b06"),
            ("b01", "cos"), ("b02", "cos"), ("b03", "cos"), ("b04", "cos"), ("b05", "cos"), ("b06", "cos")
        ]

        edge_x, edge_y = [], []
        for u, v in edges:
            edge_x.extend([node_map[u]["x"], node_map[v]["x"], None])
            edge_y.extend([node_map[u]["y"], node_map[v]["y"], None])

        fig_net = go.Figure()
        fig_net.add_trace(go.Scatter(
            x=edge_x, y=edge_y,
            mode="lines",
            line=dict(width=2.2, color="#94A3B8"),
            hoverinfo="none",
            showlegend=False
        ))
        fig_net.add_trace(go.Scatter(
            x=[n["x"] for n in nodes],
            y=[n["y"] for n in nodes],
            mode="markers+text",
            marker=dict(
                size=[n["size"] for n in nodes],
                color=[n["color"] for n in nodes],
                line=dict(width=2.5, color="#FFFFFF")
            ),
            text=[n["label"] for n in nodes],
            textposition="bottom center",
            textfont=dict(size=10.5, color="#131E29", family="'72', 'Segoe UI', sans-serif"),
            hovertemplate="<b>%{text}</b><extra></extra>",
            showlegend=False
        ))
        fig_net.update_layout(
            height=380,
            margin=dict(l=20, r=20, t=20, b=35),
            paper_bgcolor="#F8FAFC",
            plot_bgcolor="#F8FAFC",
            xaxis=dict(visible=False, range=[-0.04, 1.04]),
            yaxis=dict(visible=False, range=[-0.05, 1.02])
        )
        st.plotly_chart(fig_net, width="stretch", key=f"sc_canvas_plot_{key_suffix}")
