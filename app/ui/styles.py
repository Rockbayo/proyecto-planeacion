"""

Sistema de Diseño Corporativo e Institucional: SAP Fiori Horizon (Enterprise High-Contrast UI)

Directrices:

- Accesibilidad WCAG AAA, objetivos táctiles mínimos de 44px.

- Arquitectura de Layout en 3 niveles (.sap-shellbar, .sap-page-header, .sap-container).

- Componentes: Tarjetas .cs-card, Botones .cs-btn y .sap-btn-secondary, Pestañas .auth-tabs/.gov-tabs,

  Alertas semánticas y Badges .sap-badge.

- Lenguaje 100% ciudadano e institucional (sin tecnicismos de ingeniería en interfaz).

"""



import streamlit as st

import altair as alt



CSS_SOP_PROFESIONAL = """

<style>

/* ====================================================================

   1. VARIABLES CSS GLOBALES (:root) - SAP FIORI HORIZON HIGH-CONTRAST

   ==================================================================== */

:root {

    --sap-shell-bg: #1D2D3E;          /* Barra superior oscura (Shellbar) */

    --sap-shell-text: #FFFFFF;        /* Texto en barra superior */

    --sap-bg-canvas: #F5F6F7;         /* Fondo general de la aplicación */

    --sap-bg-surface: #FFFFFF;        /* Fondo de tarjetas y encabezados */

    --sap-bg-subtle: #EDF0F2;         /* Fondo secundario / hover suave */

    --sap-text-primary: #131E29;      /* Texto principal de alto contraste */

    --sap-text-secondary: #475569;    /* Subtítulos y metadatos */

    --sap-brand-primary: #0057D2;     /* Azul corporativo primario */

    --sap-brand-hover: #00409C;       /* Azul corporativo en hover */

    --sap-accent-rural: #106333;      /* Verde acento / confirmación */

    --sap-border-strong: #5B738B;     /* Bordes de inputs y botones secundarios */

    --sap-border-subtle: #D5DADD;     /* Bordes de tarjetas y divisores */

    --sap-status-ok-bg: #EBF5ED;

    --sap-status-ok-text: #106333;

    --sap-status-ok-border: #256F3A;

    --sap-status-warn-bg: #FFF8E6;

    --sap-status-warn-text: #7A4100;

    --sap-status-warn-border: #E76500;

    --sap-status-err-bg: #FFEBEB;

    --sap-status-err-text: #A61C1C;

    --sap-status-err-border: #AA0808;

    --sap-focus-ring: #0057D2;

    --sap-shadow-card: 0 1px 4px rgba(19, 30, 41, 0.12), 0 0 1px rgba(19, 30, 41, 0.18);

}



/* ====================================================================

   2. TIPOGRAFÍA Y BASE (WCAG AAA)

   ==================================================================== */

html, body, [data-testid="stAppViewContainer"], .main, .stApp {

    background-color: var(--sap-bg-canvas) !important;

    color: var(--sap-text-primary) !important;

    font-family: '72', 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif !important;

    font-size: 15px !important;

    line-height: 1.5 !important;

    -webkit-font-smoothing: antialiased !important;

}



header[data-testid="stHeader"] {

    background-color: var(--sap-shell-bg) !important;

    border-bottom: 1px solid rgba(255, 255, 255, 0.1) !important;

    height: 3.5rem !important;

}



/* Accesibilidad de foco */

:focus-visible, button:focus-visible, input:focus-visible, select:focus-visible, [tabindex]:focus-visible {

    outline: 2px solid var(--sap-focus-ring) !important;

    outline-offset: 2px !important;

}



/* Encabezados y Jerarquía */

h1, h2, h3, h4, h5, h6, .stHeading, [data-testid="stHeading"] {

    color: var(--sap-text-primary) !important;

    font-family: '72', 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif !important;

    font-weight: 700 !important;

    letter-spacing: -0.015em !important;

}



p, span, label, [data-testid="stMarkdownContainer"] p, [data-testid="stText"] {

    color: var(--sap-text-primary) !important;

    font-size: 15px !important;

    line-height: 1.5 !important;

}



.stCaption, small, [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p, [data-testid="stWidgetLabel"] small {

    color: var(--sap-text-secondary) !important;

    font-size: 0.85rem !important;

    font-weight: 500 !important;

}



/* ====================================================================

   3. ARQUITECTURA DE LAYOUT (3 NIVELES)

   ==================================================================== */



/* Nivel 1: Barra Superior Fija (.sap-shellbar) */

.sap-shellbar {

    background-color: var(--sap-shell-bg) !important;

    color: var(--sap-shell-text) !important;

    position: sticky !important;

    top: 0 !important;

    z-index: 1000 !important;

    display: flex !important;

    align-items: center !important;

    justify-content: space-between !important;

    padding: 0.75rem 1.75rem !important;

    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.15) !important;

    border-bottom: 1px solid rgba(255, 255, 255, 0.1) !important;

    margin-bottom: 0 !important;

    width: 100% !important;

}



.sap-shellbar-left {

    display: flex !important;

    align-items: center !important;

    gap: 12px !important;

}



.sap-shellbar-logo {

    width: 34px !important;

    height: 34px !important;

    background-color: var(--sap-brand-primary) !important;

    border-radius: 6px !important;

    display: flex !important;

    align-items: center !important;

    justify-content: center !important;

    color: #FFFFFF !important;

    font-weight: 800 !important;

    font-size: 1.15rem !important;

    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25) !important;

}



.sap-shellbar-brand {

    display: flex !important;

    flex-direction: column !important;

}



.sap-shellbar-title {

    font-weight: 700 !important;

    font-size: 1.05rem !important;

    color: #FFFFFF !important;

    line-height: 1.2 !important;

    letter-spacing: -0.01em !important;

}



.sap-shellbar-subtitle {

    font-size: 0.80rem !important;

    color: #CBD5E1 !important;

    font-weight: 400 !important;

    line-height: 1.2 !important;

}



.sap-shellbar-center {

    display: flex !important;

    align-items: center !important;

    gap: 8px !important;

}



.sap-nav-item {

    color: #CBD5E1 !important;

    font-size: 0.88rem !important;

    font-weight: 600 !important;

    padding: 0.5rem 1rem !important;

    border-radius: 4px !important;

    text-decoration: none !important;

    min-height: 44px !important;

    display: inline-flex !important;

    align-items: center !important;

    transition: background 0.15s ease, color 0.15s ease !important;

}



.sap-nav-item:hover {

    background-color: rgba(255, 255, 255, 0.08) !important;

    color: #FFFFFF !important;

}



.sap-nav-item.active {

    background-color: rgba(255, 255, 255, 0.14) !important;

    color: #FFFFFF !important;

    border-bottom: 2px solid #60A5FA !important;

}



.sap-shellbar-right {

    display: flex !important;

    align-items: center !important;

    gap: 16px !important;

}



.sap-user-badge {

    display: flex !important;

    flex-direction: column !important;

    align-items: flex-end !important;

}



.sap-user-name {

    font-size: 0.84rem !important;

    font-weight: 700 !important;

    color: #FFFFFF !important;

}



.sap-user-role {

    font-size: 0.72rem !important;

    font-weight: 700 !important;

    color: #93C5FD !important;

    text-transform: uppercase !important;

    letter-spacing: 0.05em !important;

}



.sap-session-btn {

    background: rgba(255, 255, 255, 0.08) !important;

    border: 1px solid rgba(255, 255, 255, 0.2) !important;

    border-radius: 6px !important;

    color: #FFFFFF !important;

    font-size: 0.82rem !important;

    font-weight: 600 !important;

    padding: 0.4rem 0.9rem !important;

    min-height: 44px !important;

    display: inline-flex !important;

    align-items: center !important;

    cursor: pointer !important;

}



/* Nivel 2: Encabezado de Vista (.sap-page-header) */

.sap-page-header {

    background-color: var(--sap-bg-surface) !important;

    border-bottom: 1px solid var(--sap-border-subtle) !important;

    padding: 1.25rem 2rem !important;

    margin-bottom: 1.5rem !important;

    width: 100% !important;

    box-shadow: 0 1px 3px rgba(19, 30, 41, 0.05) !important;

}



.sap-page-header-inner {

    max-width: 1240px !important;

    margin: 0 auto !important;

    display: flex !important;

    justify-content: space-between !important;

    align-items: center !important;

    gap: 1.5rem !important;

}



.sap-page-header-left {

    display: flex !important;

    flex-direction: column !important;

    gap: 2px !important;

}



.sap-breadcrumb {

    font-size: 0.78rem !important;

    font-weight: 700 !important;

    text-transform: uppercase !important;

    color: var(--sap-brand-primary) !important;

    letter-spacing: 0.06em !important;

    margin-bottom: 2px !important;

}



.sap-page-header h1 {

    font-size: 1.50rem !important;

    font-weight: 700 !important;

    color: var(--sap-text-primary) !important;

    margin: 0 !important;

    padding: 0 !important;

    line-height: 1.25 !important;

}



.sap-page-header-subtitle {

    font-size: 0.92rem !important;

    color: var(--sap-text-secondary) !important;

    margin: 4px 0 0 0 !important;

    line-height: 1.4 !important;

}



.sap-page-header-right {

    display: flex !important;

    align-items: center !important;

    gap: 10px !important;

}



/* Nivel 3: Contenedor Principal (.sap-container) */

.sap-container {

    max-width: 1240px !important;

    margin: 0 auto 2.5rem auto !important;

    padding: 0 2rem !important;

}



.sap-grid {

    display: grid !important;

    grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)) !important;

    gap: 1.5rem !important;

}



/* ====================================================================

   4. PATRONES DE COMPONENTES

   ==================================================================== */



/* A. Tarjetas (.cs-card) */

.cs-card {

    background-color: var(--sap-bg-surface) !important;

    border: 1px solid var(--sap-border-subtle) !important;

    border-top: 3px solid var(--sap-brand-primary) !important;

    border-radius: 8px !important;

    padding: 1.5rem !important;

    box-shadow: var(--sap-shadow-card) !important;

    margin-bottom: 1.5rem !important;

}



.panel-head, .card-head {

    display: flex !important;

    justify-content: space-between !important;

    align-items: center !important;

    border-bottom: 1px solid var(--sap-border-subtle) !important;

    padding-bottom: 0.75rem !important;

    margin-bottom: 1rem !important;

}



.panel-head h2, .card-head h2 {

    font-size: 1.12rem !important;

    font-weight: 700 !important;

    color: var(--sap-text-primary) !important;

    margin: 0 !important;

    padding: 0 !important;

}



/* ====================================================================

   SIMETRÍA Y ESTANDARIZACIÓN VISUAL DE TARJETAS (SAP FIORI HORIZON)

   ==================================================================== */



/* Estandarización de filas horizontales para igualar altura en todas las columnas */

div[data-testid="stHorizontalBlock"] {

    display: flex !important;

    align-items: stretch !important;

    gap: 1.25rem !important;

}



div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {

    display: flex !important;

    flex-direction: column !important;

    flex: 1 1 0% !important;

    height: 100% !important;

    min-width: 0 !important;

}



div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] {

    display: flex !important;

    flex-direction: column !important;

    flex: 1 1 auto !important;

    height: 100% !important;

}



/* Tarjetas de Contenedores con Borde (st.container(border=True) / .cs-card) */

div[data-testid="stVerticalBlockBorderWrapper"] {

    background: var(--sap-bg-surface) !important;

    border: 1px solid var(--sap-border-subtle) !important;

    border-top: 3px solid var(--sap-brand-primary) !important;

    border-radius: 8px !important;

    box-shadow: var(--sap-shadow-card) !important;

    padding: 1.25rem !important;

    margin-bottom: 1rem !important;

    box-sizing: border-box !important;

}



div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] div[data-testid="stVerticalBlockBorderWrapper"] {

    display: flex !important;

    flex-direction: column !important;

    flex: 1 1 auto !important;

    height: 100% !important;

    min-height: 100% !important;

    box-sizing: border-box !important;

    justify-content: space-between !important;

}



div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] div[data-testid="stVerticalBlockBorderWrapper"] > div[data-testid="stVerticalBlock"] {

    display: flex !important;

    flex-direction: column !important;

    flex: 1 1 auto !important;

    justify-content: space-between !important;

    height: 100% !important;

}



/* Tarjetas de Métricas / KPI Cards (Medidas 100% Estandarizadas y Simétricas) */

div[data-testid="stMetric"] {

    background: var(--sap-bg-surface) !important;

    border: 1px solid var(--sap-border-subtle) !important;

    border-top: 3px solid var(--sap-brand-primary) !important;

    border-radius: 8px !important;

    padding: 1.25rem 1.5rem !important;

    box-shadow: var(--sap-shadow-card) !important;

    transition: box-shadow 0.15s ease, border-color 0.15s ease !important;

    min-height: 125px !important;

    height: 100% !important;

    display: flex !important;

    flex-direction: column !important;

    justify-content: space-between !important;

    box-sizing: border-box !important;

}



div[data-testid="stMetric"]:hover {

    border-color: var(--sap-brand-primary) !important;

    box-shadow: 0 4px 8px rgba(19, 30, 41, 0.12) !important;

}



div[data-testid="stMetricLabel"] {

    min-height: 24px !important;

    display: flex !important;

    align-items: center !important;

    margin-bottom: 6px !important;

}



div[data-testid="stMetricLabel"] p {

    color: var(--sap-text-secondary) !important;

    font-size: 0.82rem !important;

    font-weight: 700 !important;

    text-transform: uppercase !important;

    letter-spacing: 0.05em !important;

    margin: 0 !important;

    line-height: 1.2 !important;

}



div[data-testid="stMetricValue"] {

    color: var(--sap-text-primary) !important;

    font-weight: 700 !important;

    font-size: 1.85rem !important;

    letter-spacing: -0.02em !important;

    line-height: 1.2 !important;

}



/* B. Botones (min-height: 44px - WCAG AAA) */

.cs-btn,

button[kind="primary"], 

.stButton > button[kind="primary"],

button[data-testid="baseButton-primary"],

div[data-testid="stDownloadButton"] > button[kind="primary"],

div[data-testid="stDownloadButton"] > button[data-testid="baseButton-primary"] {

    background-color: var(--sap-brand-primary) !important;

    color: #FFFFFF !important;

    font-weight: 700 !important;

    font-size: 0.90rem !important;

    border: 1px solid var(--sap-brand-primary) !important;

    border-radius: 6px !important;

    padding: 0.55rem 1.25rem !important;

    min-height: 44px !important;

    display: inline-flex !important;

    align-items: center !important;

    justify-content: center !important;

    box-shadow: 0 1px 3px rgba(0, 87, 210, 0.25) !important;

    cursor: pointer !important;

    transition: all 0.15s ease !important;

}



.cs-btn:hover,

button[kind="primary"]:hover, 

.stButton > button[kind="primary"]:hover,

button[data-testid="baseButton-primary"]:hover {

    background-color: var(--sap-brand-hover) !important;

    border-color: var(--sap-brand-hover) !important;

    box-shadow: 0 2px 5px rgba(0, 64, 156, 0.35) !important;

}



.cs-btn *,

button[kind="primary"] *,

.stButton > button[kind="primary"] *,

div[data-testid="stDownloadButton"] > button[kind="primary"] *,

div[data-testid="stDownloadButton"] > button[data-testid="baseButton-primary"] * {

    color: #FFFFFF !important;

    font-weight: 700 !important;

}



/* Botón Secundario (.sap-btn-secondary) */

.sap-btn-secondary,

button[kind="secondary"], 

.stButton > button:not([kind="primary"]),

button[data-testid="baseButton-secondary"],

button:not([kind="primary"]):not([data-testid="baseButton-primary"]),

div[data-testid="stDownloadButton"] > button:not([kind="primary"]):not([data-testid="baseButton-primary"]) {

    background-color: var(--sap-bg-surface) !important;

    color: var(--sap-text-primary) !important;

    border: 1px solid var(--sap-border-strong) !important;

    border-radius: 6px !important;

    font-weight: 700 !important;

    font-size: 0.90rem !important;

    padding: 0.55rem 1.25rem !important;

    min-height: 44px !important;

    display: inline-flex !important;

    align-items: center !important;

    justify-content: center !important;

    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04) !important;

    cursor: pointer !important;

    transition: all 0.15s ease !important;

}



.sap-btn-secondary:hover,

button[kind="secondary"]:hover, 

.stButton > button:not([kind="primary"]):hover,

button[data-testid="baseButton-secondary"]:hover,

div[data-testid="stDownloadButton"] > button:hover {

    background-color: var(--sap-bg-subtle) !important;

    border-color: var(--sap-brand-primary) !important;

    color: var(--sap-brand-primary) !important;

}



.sap-btn-secondary *,

button[kind="secondary"] *,

.stButton > button:not([kind="primary"]) *,

div[data-testid="stDownloadButton"] > button:not([kind="primary"]):not([data-testid="baseButton-primary"]) * {

    color: var(--sap-text-primary) !important;

    font-weight: 700 !important;

}



.sap-btn-secondary:hover *,

button[kind="secondary"]:hover *,

.stButton > button:not([kind="primary"]):hover * {

    color: var(--sap-brand-primary) !important;

}



/* C. Formularios (.sap-form-label y .sap-input) */

.sap-form-label,

div[data-testid="stWidgetLabel"] label,

div[data-testid="stWidgetLabel"] p {

    color: var(--sap-text-primary) !important;

    font-size: 0.88rem !important;

    font-weight: 700 !important;

    letter-spacing: -0.01em !important;

    margin-bottom: 6px !important;

}



.sap-input,

div[data-baseweb="select"] > div, 

div[data-testid="stTextInput"] input, 

div[data-testid="stNumberInput"] input, 

div[data-testid="stDateInput"] input,

textarea {

    min-height: 44px !important;

    border: 1px solid var(--sap-border-strong) !important;

    border-radius: 4px !important;

    padding: 0.55rem 0.85rem !important;

    background-color: var(--sap-bg-surface) !important;

    color: var(--sap-text-primary) !important;

    font-size: 0.92rem !important;

}



div[data-baseweb="select"] > div:focus-within, 

div[data-testid="stTextInput"] input:focus, 

div[data-testid="stNumberInput"] input:focus,

textarea:focus {

    border-color: var(--sap-brand-primary) !important;

    outline: 2px solid var(--sap-focus-ring) !important;

    outline-offset: 1px !important;

}



/* D. Insignias / Badges (.sap-badge) */

.sap-badge {

    display: inline-flex !important;

    align-items: center !important;

    padding: 0.2rem 0.65rem !important;

    border-radius: 4px !important;

    font-size: 0.78rem !important;

    font-weight: 700 !important;

    text-transform: uppercase !important;

    letter-spacing: 0.03em !important;

    line-height: 1.25 !important;

}



.sap-badge-info {

    background-color: #E8F1FF !important;

    color: var(--sap-brand-primary) !important;

    border: 1px solid #BFDBFE !important;

}



.sap-badge-ok {

    background-color: var(--sap-status-ok-bg) !important;

    color: var(--sap-status-ok-text) !important;

    border: 1px solid var(--sap-status-ok-border) !important;

}



.sap-badge-warn {

    background-color: var(--sap-status-warn-bg) !important;

    color: var(--sap-status-warn-text) !important;

    border: 1px solid var(--sap-status-warn-border) !important;

}



.sap-badge-err {

    background-color: var(--sap-status-err-bg) !important;

    color: var(--sap-status-err-text) !important;

    border: 1px solid var(--sap-status-err-border) !important;

}



/* E. Pestañas (.auth-tabs / .gov-tabs y st.tabs) */

div[data-testid="stTabs"] {

    background: transparent !important;

    margin-top: 14px !important;

    margin-bottom: 22px !important;

}



div[data-baseweb="tab-list"],

.auth-tabs,

.gov-tabs {

    background: var(--sap-bg-surface) !important;

    border: 1px solid var(--sap-border-subtle) !important;

    border-radius: 8px !important;

    padding: 4px 6px !important;

    box-shadow: var(--sap-shadow-card) !important;

    gap: 6px !important;

    display: flex !important;

    align-items: center !important;

    overflow-x: auto !important;

}



button[data-baseweb="tab"],

.auth-tabs button,

.gov-tabs button {

    min-height: 44px !important;

    background-color: var(--sap-bg-surface) !important;

    border: 1px solid var(--sap-border-subtle) !important;

    border-bottom: 3px solid transparent !important;

    border-radius: 6px !important;

    padding: 0.55rem 1.25rem !important;

    font-size: 0.90rem !important;

    font-weight: 600 !important;

    color: var(--sap-text-primary) !important;

    cursor: pointer !important;

    transition: all 0.15s ease-in-out !important;

    white-space: nowrap !important;

    display: inline-flex !important;

    align-items: center !important;

}



button[data-baseweb="tab"] p,

button[data-baseweb="tab"] span,

button[data-baseweb="tab"] div {

    color: var(--sap-text-primary) !important;

    font-weight: 600 !important;

}



button[data-baseweb="tab"]:hover,

.auth-tabs button:hover,

.gov-tabs button:hover {

    background-color: var(--sap-bg-subtle) !important;

    border-color: var(--sap-border-strong) !important;

    color: var(--sap-brand-primary) !important;

}



button[data-baseweb="tab"][aria-selected="true"],

button[data-baseweb="tab"].active,

.auth-tabs button.active,

.gov-tabs button.active {

    background-color: #F8FAFC !important;

    color: var(--sap-brand-primary) !important;

    border: 1px solid var(--sap-border-subtle) !important;

    border-bottom: 3px solid var(--sap-brand-primary) !important;

    box-shadow: 0 1px 3px rgba(0, 87, 210, 0.12) !important;

}



button[data-baseweb="tab"][aria-selected="true"] p,

button[data-baseweb="tab"][aria-selected="true"] span,

button[data-baseweb="tab"][aria-selected="true"] div,

button[data-baseweb="tab"][aria-selected="true"] * {

    color: var(--sap-brand-primary) !important;

    font-weight: 700 !important;

}



div[data-baseweb="tab-highlight"],

div[data-baseweb="tab-border"] {

    display: none !important;

}



/* F. Alertas Semánticas Accesibles */

/* Éxito (Verde) */

.sap-alert-success,

div[data-testid="stAlert"][kind="success"],

div[data-testid="stAlert"]:has(svg[data-testid="stAlertSuccessIcon"]),

div[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]) {

    border-left: 5px solid #15803D !important;

    background-color: #DCFCE7 !important;

    color: #14532D !important;

    padding: 0.9rem 1.2rem !important;

    border-radius: 6px !important;

    font-weight: 700 !important;

    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04) !important;

    border-top: 1px solid #BBF7D0 !important;

    border-right: 1px solid #BBF7D0 !important;

    border-bottom: 1px solid #BBF7D0 !important;

}



.sap-alert-success *,

div[data-testid="stAlert"]:has(svg[data-testid="stAlertSuccessIcon"]) * {

    color: #14532D !important;

    font-weight: 600 !important;

}



/* Error (Rojo) */

.sap-alert-error,

div[data-testid="stAlert"][kind="error"],

div[data-testid="stAlert"]:has(svg[data-testid="stAlertErrorIcon"]),

div[data-testid="stAlert"]:has([data-testid="stAlertContentError"]) {

    border-left: 5px solid #B91C1C !important;

    background-color: #FEE2E2 !important;

    color: #7F1D1D !important;

    padding: 0.9rem 1.2rem !important;

    border-radius: 6px !important;

    font-weight: 700 !important;

    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04) !important;

    border-top: 1px solid #FECACA !important;

    border-right: 1px solid #FECACA !important;

    border-bottom: 1px solid #FECACA !important;

}



.sap-alert-error *,

div[data-testid="stAlert"]:has(svg[data-testid="stAlertErrorIcon"]) * {

    color: #7F1D1D !important;

    font-weight: 600 !important;

}



/* Aviso / Offline (Ámbar) */

.sap-alert-warning,

div[data-testid="stAlert"][kind="warning"],

div[data-testid="stAlert"]:has(svg[data-testid="stAlertWarningIcon"]),

div[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]) {

    border-left: 4px solid #E76500 !important;

    background-color: #FFF8E6 !important;

    color: #7A4100 !important;

    padding: 0.9rem 1.2rem !important;

    border-radius: 6px !important;

    font-weight: 600 !important;

    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04) !important;

    border-top: 1px solid #FED7AA !important;

    border-right: 1px solid #FED7AA !important;

    border-bottom: 1px solid #FED7AA !important;

}



.sap-alert-warning *,

div[data-testid="stAlert"]:has(svg[data-testid="stAlertWarningIcon"]) * {

    color: #7A4100 !important;

    font-weight: 600 !important;

}



/* Informativo (Azul) */

.sap-alert-info,

div[data-testid="stAlert"][kind="info"],

div[data-testid="stAlert"]:has(svg[data-testid="stAlertInfoIcon"]),

div[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) {

    border-left: 4px solid var(--sap-brand-primary) !important;

    background-color: #E8F1FF !important;

    color: var(--sap-text-primary) !important;

    padding: 0.9rem 1.2rem !important;

    border-radius: 6px !important;

    font-weight: 600 !important;

    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04) !important;

    border-top: 1px solid #BFDBFE !important;

    border-right: 1px solid #BFDBFE !important;

    border-bottom: 1px solid #BFDBFE !important;

}



.sap-alert-info *,

div[data-testid="stAlert"]:has(svg[data-testid="stAlertInfoIcon"]) * {

    color: var(--sap-text-primary) !important;

}



/* G. Barra Lateral / Sidebar (Limpio, Sobrio, Accesible 44px) */

section[data-testid="stSidebar"],

section[data-testid="stSidebar"] > div {

    background-color: var(--sap-shell-bg) !important;

    border-right: 1px solid rgba(255, 255, 255, 0.1) !important;

}



section[data-testid="stSidebar"] h1, 

section[data-testid="stSidebar"] h2, 

section[data-testid="stSidebar"] h3 {

    color: #FFFFFF !important;

    font-size: 1.05rem !important;

    font-weight: 700 !important;

    letter-spacing: 0.04em !important;

    text-transform: uppercase !important;

    border-bottom: 1px solid rgba(255, 255, 255, 0.15) !important;

    padding-bottom: 8px !important;

    margin-bottom: 14px !important;

}



section[data-testid="stSidebar"] p,

section[data-testid="stSidebar"] span {

    color: #CBD5E1 !important;

}



section[data-testid="stSidebar"] div[data-testid="stRadio"] label {

    min-height: 44px !important;

    color: #CBD5E1 !important;

    padding: 10px 14px !important;

    border-radius: 6px !important;

    font-size: 0.90rem !important;

    font-weight: 500 !important;

    transition: all 0.15s ease !important;

    margin-bottom: 3px !important;

    cursor: pointer !important;

    display: flex !important;

    align-items: center !important;

}



section[data-testid="stSidebar"] div[data-testid="stRadio"] label:hover {

    background-color: rgba(255, 255, 255, 0.08) !important;

    color: #FFFFFF !important;

}



section[data-testid="stSidebar"] div[data-testid="stRadio"] label:has([aria-checked="true"]) {

    background-color: #23374D !important;

    border-left: 4px solid var(--sap-brand-primary) !important;

}



section[data-testid="stSidebar"] div[data-testid="stRadio"] label:has([aria-checked="true"]) p,

section[data-testid="stSidebar"] div[data-testid="stRadio"] label:has([aria-checked="true"]) span {

    color: #FFFFFF !important;

    font-weight: 700 !important;

}



/* H. Tablas y DataFrames */

div[data-testid="stDataFrame"], div[data-testid="stTable"] {

    background: var(--sap-bg-surface) !important;

    border: 1px solid var(--sap-border-subtle) !important;

    border-radius: 8px !important;

    box-shadow: var(--sap-shadow-card) !important;

}


/* ====================================================================
   SAP FIORI LAUNCHPAD, SPACES, TILES & FLOORPLANS (IBP S&OP)
   ==================================================================== */
.fiori-shellbar {
    background: linear-gradient(90deg, #162330 0%, #1D2D3E 100%) !important;
    color: #FFFFFF !important;
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    padding: 0.65rem 1.4rem !important;
    border-radius: 6px !important;
    box-shadow: 0 2px 6px rgba(19, 30, 41, 0.22) !important;
    margin-bottom: 0.55rem !important;
    border-bottom: 2px solid #0057D2 !important;
}

.fiori-shell-left {
    display: flex !important;
    align-items: center !important;
    gap: 10px !important;
}

.fiori-logo-box {
    background: #0057D2 !important;
    color: #FFFFFF !important;
    font-weight: 800 !important;
    font-size: 0.85rem !important;
    padding: 4px 9px !important;
    border-radius: 4px !important;
    letter-spacing: 0.05em !important;
}

.fiori-brand-divider {
    width: 1px !important;
    height: 24px !important;
    background: rgba(255, 255, 255, 0.24) !important;
}

.fiori-brand-titles {
    display: flex !important;
    flex-direction: column !important;
}

.fiori-brand-main {
    color: #FFFFFF !important;
    font-weight: 700 !important;
    font-size: 0.98rem !important;
    line-height: 1.15 !important;
}

.fiori-brand-sub {
    color: #93C5FD !important;
    font-size: 0.76rem !important;
    font-weight: 600 !important;
}

.fiori-shell-center {
    display: flex !important;
    align-items: center !important;
    gap: 10px !important;
}

.fiori-env-pill {
    background: rgba(255, 255, 255, 0.12) !important;
    color: #F8FAFC !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    padding: 4px 10px !important;
    border-radius: 999px !important;
    border: 1px solid rgba(255, 255, 255, 0.18) !important;
}

.fiori-shell-right {
    display: flex !important;
    align-items: center !important;
    gap: 12px !important;
}

.fiori-me-area {
    display: flex !important;
    align-items: center !important;
    gap: 8px !important;
}

.fiori-avatar {
    width: 30px !important;
    height: 30px !important;
    border-radius: 50% !important;
    background: #106333 !important;
    color: #FFFFFF !important;
    font-size: 0.75rem !important;
    font-weight: 800 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    border: 1.5px solid #FFFFFF !important;
}

.fiori-me-text {
    display: flex !important;
    flex-direction: column !important;
}

.fiori-me-name {
    color: #FFFFFF !important;
    font-size: 0.80rem !important;
    font-weight: 700 !important;
    line-height: 1.1 !important;
}

.fiori-me-role {
    color: #CBD5E1 !important;
    font-size: 0.70rem !important;
}

/* App Header & Variant Management */
.fiori-app-header-box {
    background: #FFFFFF !important;
    border: 1px solid var(--sap-border-subtle) !important;
    border-left: 4px solid #0057D2 !important;
    border-radius: 6px !important;
    padding: 0.85rem 1.25rem !important;
    margin: 0.35rem 0 0.55rem 0 !important;
    box-shadow: var(--sap-shadow-card) !important;
}

.fiori-app-header-top {
    display: flex !important;
    align-items: flex-start !important;
    justify-content: space-between !important;
    gap: 12px !important;
}

.fiori-app-breadcrumb {
    font-size: 0.74rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.04em !important;
    color: #475569 !important;
    margin-bottom: 2px !important;
}

.fiori-fp-tag {
    color: #0057D2 !important;
    background: #EFF6FF !important;
    padding: 2px 7px !important;
    border-radius: 4px !important;
    border: 1px solid #BFDBFE !important;
}

.fiori-app-title {
    font-size: 1.32rem !important;
    font-weight: 800 !important;
    color: #131E29 !important;
    margin: 0 0 2px 0 !important;
}

.fiori-app-subtitle {
    font-size: 0.86rem !important;
    color: #475569 !important;
    margin: 0 !important;
}

/* Launchpad Hero & KPI/Microchart Tiles */
.fiori-launchpad-hero {
    background: linear-gradient(135deg, #FFFFFF 0%, #EFF6FF 100%) !important;
    border: 1px solid #BFDBFE !important;
    border-left: 5px solid #0057D2 !important;
    border-radius: 8px !important;
    padding: 1rem 1.35rem !important;
    margin-bottom: 0.85rem !important;
}

.fiori-hero-kicker {
    font-size: 0.73rem !important;
    font-weight: 800 !important;
    color: #0057D2 !important;
    letter-spacing: 0.05em !important;
}

.fiori-hero-title {
    font-size: 1.25rem !important;
    font-weight: 800 !important;
    color: #131E29 !important;
    margin: 2px 0 4px 0 !important;
}

.fiori-hero-desc {
    font-size: 0.85rem !important;
    color: #475569 !important;
    margin: 0 !important;
}

.fiori-kpi-tile {
    background: #FFFFFF !important;
    border: 1px solid #D5DADD !important;
    border-top: 3px solid #0057D2 !important;
    border-radius: 8px !important;
    padding: 0.75rem 0.85rem !important;
    min-height: 162px !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: space-between !important;
    box-shadow: 0 1px 3px rgba(19, 30, 41, 0.08) !important;
    margin-bottom: 0.3rem !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease !important;
}

.fiori-kpi-tile:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 4px 10px rgba(0, 87, 210, 0.15) !important;
    border-color: #0057D2 !important;
}

.fiori-tile-title {
    font-size: 0.88rem !important;
    font-weight: 700 !important;
    color: #131E29 !important;
    line-height: 1.2 !important;
}

.fiori-tile-subtitle {
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    color: #0057D2 !important;
    margin-top: 2px !important;
}

.fiori-tile-kpi-row {
    display: flex !important;
    align-items: baseline !important;
    gap: 5px !important;
    margin: 6px 0 2px 0 !important;
}

.fiori-tile-kpi-val {
    font-size: 1.38rem !important;
    font-weight: 800 !important;
    color: #131E29 !important;
}

.fiori-tile-kpi-unit {
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    color: #475569 !important;
}

.fiori-tile-microchart {
    margin: 2px 0 !important;
}

.fiori-tile-footer {
    font-size: 0.71rem !important;
    color: #475569 !important;
    border-top: 1px solid #EDF0F2 !important;
    padding-top: 4px !important;
}

/* OVP Cards & List Card */
.fiori-card-hdr {
    border-bottom: 1px solid #EDF0F2 !important;
    padding-bottom: 6px !important;
    margin-bottom: 8px !important;
}

.fiori-card-tag {
    font-size: 0.68rem !important;
    font-weight: 800 !important;
    color: #0057D2 !important;
    background: #EFF6FF !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
}

.fiori-card-title {
    font-size: 0.96rem !important;
    font-weight: 700 !important;
    color: #131E29 !important;
    margin-top: 3px !important;
}

.fiori-card-sub {
    font-size: 0.76rem !important;
    color: #475569 !important;
}

.fiori-list-item {
    padding: 5px 0 !important;
    border-bottom: 1px dashed #E2E8F0 !important;
}

.fiori-list-row-top {
    display: flex !important;
    justify-content: space-between !important;
    font-size: 0.80rem !important;
    margin-bottom: 3px !important;
}

.fiori-list-sku {
    font-weight: 700 !important;
    color: #131E29 !important;
}

.fiori-list-val {
    font-weight: 700 !important;
    color: #0057D2 !important;
}

.fiori-list-bar-bg {
    width: 100% !important;
    height: 6px !important;
    background: #E2E8F0 !important;
    border-radius: 999px !important;
    overflow: hidden !important;
}

.fiori-list-bar-fill {
    height: 100% !important;
    background: linear-gradient(90deg, #0057D2 0%, #106333 100%) !important;
    border-radius: 999px !important;
}

/* Floating Footer Toolbar */
.fiori-footer-banner {
    background: #1D2D3E !important;
    color: #FFFFFF !important;
    padding: 0.5rem 1rem !important;
    border-radius: 6px !important;
    display: flex !important;
    justify-content: space-between !important;
    align-items: center !important;
    margin: 0.75rem 0 0.35rem 0 !important;
    font-size: 0.82rem !important;
}

.fiori-footer-status {
    color: #F8FAFC !important;
}

.fiori-footer-hint {
    color: #93C5FD !important;
    font-size: 0.74rem !important;
    font-weight: 600 !important;
}
</style>


"""



# Configurar Tema Oficial SAP Fiori Horizon en Altair

try:

    @alt.theme.register('sap_horizon', enable=True)

    def _tema_altair_sap_horizon():

        return alt.theme.ThemeConfig({

            'config': {

                'background': '#FFFFFF',

                'view': {

                    'stroke': 'transparent',

                    'fill': '#FFFFFF'

                },

                'title': {

                    'color': '#131E29',

                    'fontSize': 14,

                    'fontWeight': 700,

                    'font': "'72', 'Segoe UI', sans-serif"

                },

                'axis': {

                    'domainColor': '#D5DADD',

                    'gridColor': '#EDF0F2',

                    'labelColor': '#475569',

                    'titleColor': '#131E29',

                    'tickColor': '#D5DADD'

                },

                'legend': {

                    'labelColor': '#131E29',

                    'titleColor': '#131E29'

                },

                'range': {

                    'category': [

                        '#0057D2',  # Demanda / Plan Maestro (Azul SAP)

                        '#106333',  # Oferta de Cosecha / Campo (Verde Acento)

                        '#7A4100',  # Enraizamiento (Ámbar)

                        '#7C3AED',  # Siembras (Púrpura)

                        '#0284C7',  # Capacidad (Celeste)

                        '#A61C1C',  # Techo Físico (Rojo Alerta)

                        '#475569'   # Línea Base Neutra (Gris)

                    ]

                }

            }

        })

except Exception:

    pass



def aplicar_tema_invernadero_industrial():

    """Inyecta el Sistema de Diseño SAP Fiori Horizon en la aplicación Streamlit."""

    st.html(CSS_SOP_PROFESIONAL)



# Alias de compatibilidad

aplicar_tema_sop_ejecutivo = aplicar_tema_invernadero_industrial



def estilizar_figura_plotly(fig):

    """

    Aplica el estándar visual SAP Fiori Horizon a figuras de Plotly:

    alto contraste WCAG AAA, lienzo blanco y paleta oficial.

    """

    fig.update_layout(

        paper_bgcolor='#FFFFFF',

        plot_bgcolor='#FFFFFF',

        font=dict(color='#131E29', family="'72', 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif"),

        colorway=[

            '#0057D2',  # Plan Maestro / Demanda (Azul SAP Horizon)

            '#106333',  # ForeCast / Cosecha Viva (Verde Acento)

            '#7A4100',  # Propagación / Enraizamiento (Ámbar)

            '#7C3AED',  # Siembras en Campo (Púrpura)

            '#0284C7',  # Capacidad (Celeste)

            '#A61C1C',  # Capacidad Máxima / Techo (Rojo)

            '#475569'   # Línea Base Histórica (Gris Pizarra)

        ],

        xaxis=dict(

            gridcolor='#EDF0F2',

            zerolinecolor='#D5DADD',

            tickfont=dict(color='#475569', size=11),

            title_font=dict(color='#131E29', size=12, family="'72', 'Segoe UI', sans-serif")

        ),

        yaxis=dict(

            gridcolor='#EDF0F2',

            zerolinecolor='#D5DADD',

            tickfont=dict(color='#475569', size=11),

            title_font=dict(color='#131E29', size=12, family="'72', 'Segoe UI', sans-serif")

        ),

        legend=dict(

            font=dict(color='#131E29', size=12),

            bgcolor='rgba(255, 255, 255, 0.95)',

            bordercolor='#D5DADD',

            borderwidth=1

        )

    )

    return fig



# Paleta oficial S&OP Profesional SAP Fiori Horizon

PALETA_INVERNADERO = {

    "fondo_app": "#F5F6F7",

    "fondo_panel": "#FFFFFF",

    "borde_metalico": "#D5DADD",

    "plan_demanda": "#0057D2",

    "forecast_oferta": "#106333",

    "enraizamiento": "#7A4100",

    "alerta_techo": "#A61C1C",

    "neutro": "#475569",

    "texto_titulos": "#131E29",

    "texto_cuerpo": "#131E29"

}



PALETA_EJECUTIVA = PALETA_INVERNADERO

PALETA_SAP = PALETA_INVERNADERO



def render_sap_shellbar(active_module: str = "Dashboard General", user_name: str = "Planificador Maestro", user_role: str = "Operaciones"):

    """

    Renderiza la Barra Superior Fija Institucional (Nivel 1: .sap-shellbar).

    """

    html = f"""

    <div class="sap-shellbar">

        <div class="sap-shellbar-left">

            <div class="sap-shellbar-logo">🌸</div>

            <div class="sap-shellbar-brand">

                <div class="sap-shellbar-title">Flores Corporativas S&OP</div>

                <div class="sap-shellbar-subtitle">Planeación Integrada de Suministros</div>

            </div>

        </div>

        <div class="sap-shellbar-center">

            <span class="sap-nav-item active">{active_module}</span>

        </div>

        <div class="sap-shellbar-right">

            <div class="sap-user-badge">

                <span class="sap-user-name">{user_name}</span>

                <span class="sap-user-role">{user_role}</span>

            </div>

            <span class="sap-session-btn">● En Línea</span>

        </div>

    </div>

    """

    st.markdown(html, unsafe_allow_html=True)



def render_sap_page_header(breadcrumb: str, title: str, subtitle: str, actions_html: str = ""):

    """

    Renderiza el Encabezado de Vista Institucional (Nivel 2: .sap-page-header).

    """

    actions_markup = f'<div class="sap-page-header-right">{actions_html}</div>' if actions_html else ''

    html = f"""

    <div class="sap-page-header">

        <div class="sap-page-header-inner">

            <div class="sap-page-header-left">

                <div class="sap-breadcrumb">{breadcrumb}</div>

                <h1>{title}</h1>

                <p class="sap-page-header-subtitle">{subtitle}</p>

            </div>

            {actions_markup}

        </div>

    </div>

    """

    st.markdown(html, unsafe_allow_html=True)



def render_sap_badge(texto: str, tipo: str = "info") -> str:

    """

    Genera el HTML para una insignia institucional (.sap-badge).

    Tipos: 'info' (azul), 'ok' (verde), 'warn' (ámbar), 'err' (rojo).

    """

    t = tipo.lower()

    clases = {

        "info": "sap-badge-info",

        "azul": "sap-badge-info",

        "ok": "sap-badge-ok",

        "verde": "sap-badge-ok",

        "warn": "sap-badge-warn",

        "amarillo": "sap-badge-warn",

        "ambar": "sap-badge-warn",

        "err": "sap-badge-err",

        "rojo": "sap-badge-err"

    }

    cls = clases.get(t, "sap-badge-info")

    return f'<span class="sap-badge {cls}">{texto}</span>'



# Alias de compatibilidad

badge_variedad = lambda nombre, tipo_color="azul": render_sap_badge(nombre, tipo_color)



def render_sap_alert(tipo: str, mensaje: str):

    """

    Renderiza una alerta semántica accesible institucional.

    Tipos: 'success' / 'ok', 'warning' / 'warn', 'error' / 'err', 'info'.

    """

    t = tipo.lower()

    if t in ["success", "ok", "verde"]:

        cls = "sap-alert-success"

        icon = "✓"

    elif t in ["error", "err", "rojo"]:

        cls = "sap-alert-error"

        icon = "✕"

    elif t in ["warning", "warn", "ambar", "amarillo"]:

        cls = "sap-alert-warning"

        icon = "⚠"

    else:

        cls = "sap-alert-info"

        icon = "ℹ"



    html = f"""

    <div class="{cls}" style="margin: 12px 0;">

        <span style="font-weight: 800; margin-right: 6px;">{icon}</span> {mensaje}

    </div>

    """

    st.markdown(html, unsafe_allow_html=True)

