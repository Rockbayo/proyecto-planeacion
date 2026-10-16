"""
Tema Visual: S&OP Ejecutivo Profesional (Estilo SAP Fiori Horizon / SAP IBP)
Arquitectura Visual:
- Canvas Principal: #F5F6F7 (Horizon Light Shell Canvas)
- Superficies y Tarjetas: #FFFFFF (Blanco nítido con micro-borde #DDE2E6 y sombra sutil)
- Command Center Sidebar: #1C2D42 (Deep Shell Navy con acentos en #0070F2)
- Tipografía: '72' / Inter / Segoe UI (Negro pizarra #1C2D42 para títulos, #2F3E4D para lectura, #556B82 para metadata)
- Botones de Acción: #0070F2 (Azul SAP Fiori Horizon, hover #0056B3)
- Paleta S&OP para Curvas:
    * #0070F2 (Demanda Comercial / Plan de Producción Aprobado)
    * #059669 (Oferta de Campo / ForeCast Biológico)
    * #D97706 (Propagación / Enraizamiento)
    * #7C3AED (Suelo Total / Siembras Factibles)
    * #BB0000 (Capacidad Máxima / Techo de Camas)
    * #556B82 (Línea Base Neutra)
- Alertas y Semáforos: Cintas corporativas SAP Fiori Message Strip (Positivo #107E3E, Preventivo #E9730C, Crítico #BB0000, Informativo #0070F2)
"""

import streamlit as st
import altair as alt

CSS_SOP_PROFESIONAL = """
<style>
/* ====================================================================
   S&OP ENTERPRISE EXECUTIVE THEME (SAP FIORI / HORIZON DESIGN SYSTEM)
   ==================================================================== */

/* 1. Fondo Global y Tipografía Corporativa SAP */
html, body, [data-testid="stAppViewContainer"], .main, .stApp {
    background-color: #F5F6F7 !important;
    color: #1C2D42 !important;
    font-family: '72', 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
    -webkit-font-smoothing: antialiased !important;
}

header[data-testid="stHeader"] {
    background-color: #FFFFFF !important;
    border-bottom: 1px solid #E5E7EB !important;
}

/* Encabezados y Jerarquía de Texto SAP Fiori */
h1, h2, h3, h4, h5, h6, .stHeading, [data-testid="stHeading"] {
    color: #1C2D42 !important;
    font-weight: 700 !important;
    letter-spacing: -0.015em !important;
}

p, span, label, [data-testid="stMarkdownContainer"] p, [data-testid="stText"] {
    color: #2F3E4D !important;
    font-size: 0.925rem !important;
    line-height: 1.5 !important;
}

.stCaption, small, [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p, [data-testid="stWidgetLabel"] small {
    color: #556B82 !important;
    font-size: 0.835rem !important;
    font-weight: 500 !important;
}

/* 2. Barra Lateral: SAP Shell Navigation (Deep Shell Navy) */
section[data-testid="stSidebar"],
section[data-testid="stSidebar"] > div {
    background-color: #1C2D42 !important;
    border-right: 1px solid #2B3D52 !important;
}

section[data-testid="stSidebar"] > div:first-child {
    background: transparent !important;
}

/* Encabezados del Sidebar */
section[data-testid="stSidebar"] h1, 
section[data-testid="stSidebar"] h2, 
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] h4,
section[data-testid="stSidebar"] h5,
section[data-testid="stSidebar"] h6 {
    color: #FFFFFF !important;
    font-size: 1.05rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.04em !important;
    text-transform: uppercase !important;
    border-bottom: 1px solid #1E293B !important;
    padding-bottom: 8px !important;
    margin-bottom: 16px !important;
}

/* Párrafos, Spans y Textos Generales en Sidebar - Alto Contraste */
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
section[data-testid="stSidebar"] [data-testid="stText"] {
    color: #F8FAFC !important;
    font-size: 0.92rem !important;
}

/* Captions y Subtítulos en Sidebar */
section[data-testid="stSidebar"] .stCaption,
section[data-testid="stSidebar"] small,
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
    color: #94A3B8 !important;
    font-size: 0.84rem !important;
    font-weight: 500 !important;
}

/* Labels y Textos de Widgets en Sidebar */
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"],
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] span {
    color: #E2E8F0 !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    letter-spacing: 0.02em !important;
}

/* Radios de Navegación en Sidebar */
section[data-testid="stSidebar"] div[data-testid="stRadio"] label {
    color: #CBD5E1 !important;
    padding: 7px 12px !important;
    border-radius: 6px !important;
    font-size: 0.88rem !important;
    font-weight: 500 !important;
    transition: all 0.15s ease !important;
    margin-bottom: 3px !important;
}

section[data-testid="stSidebar"] div[data-testid="stRadio"] label p,
section[data-testid="stSidebar"] div[data-testid="stRadio"] label span {
    color: #CBD5E1 !important;
}

section[data-testid="stSidebar"] div[data-testid="stRadio"] label:hover {
    background-color: rgba(255, 255, 255, 0.08) !important;
    color: #FFFFFF !important;
}

section[data-testid="stSidebar"] div[data-testid="stRadio"] label:hover p,
section[data-testid="stSidebar"] div[data-testid="stRadio"] label:hover span {
    color: #FFFFFF !important;
}

section[data-testid="stSidebar"] div[data-testid="stRadio"] [aria-checked="true"] + div p,
section[data-testid="stSidebar"] div[data-testid="stRadio"] label:has([aria-checked="true"]) p,
section[data-testid="stSidebar"] div[data-testid="stRadio"] label:has([aria-checked="true"]) span {
    color: #FFFFFF !important;
    font-weight: 600 !important;
}

section[data-testid="stSidebar"] div[data-testid="stRadio"] label:has([aria-checked="true"]) {
    background-color: #23374D !important;
    border-left: 4px solid #0070F2 !important;
}

/* 3. Contenedores y Tarjetas de Alto Nivel */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: #FFFFFF !important;
    border: 1px solid #DDE2E6 !important;
    border-radius: 8px !important;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05), 0 1px 2px -1px rgba(0, 0, 0, 0.05) !important;
    padding: 4px !important;
}

div[data-testid="stVerticalBlockBorderWrapper"] > div {
    background: transparent !important;
}

/* Tarjetas de Métricas / KPI Cards Ejecutivas */
div[data-testid="stMetric"] {
    background: #FFFFFF !important;
    border: 1px solid #DDE2E6 !important;
    border-radius: 8px !important;
    padding: 16px 20px !important;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05) !important;
    transition: box-shadow 0.15s ease, border-color 0.15s ease !important;
}

div[data-testid="stMetric"]:hover {
    border-color: #0070F2 !important;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.07) !important;
}

div[data-testid="stMetricLabel"] p {
    color: #556B82 !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
}

div[data-testid="stMetricValue"] {
    color: #1C2D42 !important;
    font-weight: 700 !important;
    font-size: 1.85rem !important;
    letter-spacing: -0.02em !important;
}

/* Expanders */
details[data-testid="stExpander"] {
    background: #FFFFFF !important;
    border: 1px solid #DDE2E6 !important;
    border-radius: 8px !important;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.03) !important;
}

details[data-testid="stExpander"] summary {
    color: #1C2D42 !important;
    font-weight: 600 !important;
    font-size: 0.92rem !important;
    padding: 12px 16px !important;
}

/* Pestañas (Tabs) Estilo Ribbon Corporativo SAP Fiori */
div[data-testid="stTabs"] {
    background: transparent !important;
}

div[data-baseweb="tab-list"] {
    background: #EAEEF2 !important;
    border-radius: 8px !important;
    padding: 4px !important;
    border: 1px solid #DDE2E6 !important;
    gap: 4px !important;
}

button[data-baseweb="tab"] {
    border-radius: 6px !important;
    color: #556B82 !important;
    border: none !important;
    padding: 8px 16px !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    transition: all 0.15s ease !important;
}

button[data-baseweb="tab"]:hover {
    color: #1C2D42 !important;
    background: rgba(255, 255, 255, 0.7) !important;
}

button[data-baseweb="tab"][aria-selected="true"] {
    background: #FFFFFF !important;
    color: #0070F2 !important;
    font-weight: 600 !important;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.08) !important;
    border-bottom: 2.5px solid #0070F2 !important;
}

div[data-baseweb="tab-highlight"] {
    display: none !important;
}

/* 4. Botones y Controles de Acción (Diseño Moderno SAP Fiori Horizon) */

/* Botón Primario (Acción Principal / Énfasis SAP) */
button[kind="primary"], 
.stButton > button[kind="primary"],
button[data-testid="baseButton-primary"] {
    background-color: #0070F2 !important;
    color: #FFFFFF !important;
    border: 1px solid #0056B3 !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    padding: 7px 18px !important;
    box-shadow: 0 1px 2px 0 rgba(0, 112, 242, 0.2) !important;
    transition: all 0.15s ease !important;
}

button[kind="primary"]:hover, 
.stButton > button[kind="primary"]:hover,
button[data-testid="baseButton-primary"]:hover {
    background-color: #0056B3 !important;
    border-color: #004085 !important;
    box-shadow: 0 2px 5px 0 rgba(0, 86, 179, 0.3) !important;
}

button[kind="primary"] *,
button[kind="primary"] p,
button[kind="primary"] span,
button[kind="primary"] div,
.stButton > button[kind="primary"] *,
.stButton > button[kind="primary"] p,
.stButton > button[kind="primary"] span,
button[data-testid="baseButton-primary"] *,
button[data-testid="baseButton-primary"] p,
button[data-testid="baseButton-primary"] span {
    color: #FFFFFF !important;
    font-weight: 600 !important;
}

/* Botón Secundario / Estándar Neutro (SAP Fiori Standard) */
button[kind="secondary"], 
.stButton > button:not([kind="primary"]),
button[data-testid="baseButton-secondary"],
button:not([kind="primary"]):not([data-testid="baseButton-primary"]) {
    background-color: #FFFFFF !important;
    color: #1C2D42 !important;
    border: 1px solid #C4C9D0 !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    padding: 7px 16px !important;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.04) !important;
    transition: all 0.15s ease !important;
}

button[kind="secondary"]:hover, 
.stButton > button:not([kind="primary"]):hover,
button[data-testid="baseButton-secondary"]:hover,
button:not([kind="primary"]):not([data-testid="baseButton-primary"]):hover {
    background-color: #F5F6F7 !important;
    border-color: #0070F2 !important;
    color: #0070F2 !important;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.08) !important;
}

button[kind="secondary"] *,
button[kind="secondary"] p,
button[kind="secondary"] span,
.stButton > button:not([kind="primary"]) *,
.stButton > button:not([kind="primary"]) p,
.stButton > button:not([kind="primary"]) span,
button[data-testid="baseButton-secondary"] *,
button[data-testid="baseButton-secondary"] p,
button[data-testid="baseButton-secondary"] span {
    color: #1C2D42 !important;
    font-weight: 500 !important;
}

button[kind="secondary"]:hover *,
.stButton > button:not([kind="primary"]):hover *,
button[data-testid="baseButton-secondary"]:hover * {
    color: #0070F2 !important;
}

/* Botones de Descarga (SAP Toolbar Action) */
div[data-testid="stDownloadButton"] > button {
    background-color: #FFFFFF !important;
    color: #0070F2 !important;
    border: 1px solid #0070F2 !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    padding: 7px 18px !important;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.04) !important;
    transition: all 0.15s ease !important;
}

div[data-testid="stDownloadButton"] > button:hover {
    background-color: #EBF3FB !important;
    border-color: #0056B3 !important;
    color: #0056B3 !important;
    box-shadow: 0 2px 5px 0 rgba(0, 112, 242, 0.15) !important;
}

div[data-testid="stDownloadButton"] > button * {
    color: #0070F2 !important;
    font-weight: 600 !important;
}

div[data-testid="stDownloadButton"] > button:hover * {
    color: #0056B3 !important;
}

/* 5. Alertas S&OP de Alta Dirección (Estilo SAP Message Strip) */
/* Alerta Error / Retraso Crítico */
div[data-testid="stAlert"]:has(svg[data-testid="stAlertErrorIcon"]),
div[data-testid="stAlert"]:has([data-testid="stAlertContentError"]),
div[data-testid="stAlert"][kind="error"],
.stAlert:has(svg[data-testid="stAlertErrorIcon"]),
.stAlert:has([data-testid="stAlertContentError"]) {
    background-color: #FDF3F2 !important;
    border: 1px solid #F9C6C4 !important;
    border-left: 4px solid #BB0000 !important;
    border-radius: 6px !important;
    color: #BB0000 !important;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.04) !important;
}

div[data-testid="stAlert"]:has(svg[data-testid="stAlertErrorIcon"]) *,
div[data-testid="stAlert"]:has([data-testid="stAlertContentError"]) * {
    color: #BB0000 !important;
}

/* Alerta Warning / Atención Preventiva */
div[data-testid="stAlert"]:has(svg[data-testid="stAlertWarningIcon"]),
div[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]),
div[data-testid="stAlert"][kind="warning"],
.stAlert:has(svg[data-testid="stAlertWarningIcon"]),
.stAlert:has([data-testid="stAlertContentWarning"]) {
    background-color: #FEF7F1 !important;
    border: 1px solid #F8D7B8 !important;
    border-left: 4px solid #E9730C !important;
    border-radius: 6px !important;
    color: #E9730C !important;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.04) !important;
}

div[data-testid="stAlert"]:has(svg[data-testid="stAlertWarningIcon"]) *,
div[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]) * {
    color: #E9730C !important;
}

/* Alerta Success / Cumplimiento Óptimo */
div[data-testid="stAlert"]:has(svg[data-testid="stAlertSuccessIcon"]),
div[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]),
div[data-testid="stAlert"][kind="success"],
.stAlert:has(svg[data-testid="stAlertSuccessIcon"]),
.stAlert:has([data-testid="stAlertContentSuccess"]) {
    background-color: #F1FDF6 !important;
    border: 1px solid #A6E9D5 !important;
    border-left: 4px solid #107E3E !important;
    border-radius: 6px !important;
    color: #107E3E !important;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.04) !important;
}

div[data-testid="stAlert"]:has(svg[data-testid="stAlertSuccessIcon"]) *,
div[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]) * {
    color: #107E3E !important;
}

/* Alerta Info / Informativo de Gobierno */
div[data-testid="stAlert"]:has(svg[data-testid="stAlertInfoIcon"]),
div[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]),
div[data-testid="stAlert"][kind="info"],
.stAlert:has(svg[data-testid="stAlertInfoIcon"]),
.stAlert:has([data-testid="stAlertContentInfo"]) {
    background-color: #EFF6FF !important;
    border: 1px solid #BFDBFE !important;
    border-left: 4px solid #0070F2 !important;
    border-radius: 6px !important;
    color: #0070F2 !important;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.04) !important;
}

div[data-testid="stAlert"]:has(svg[data-testid="stAlertInfoIcon"]) *,
div[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) * {
    color: #0070F2 !important;
}

/* 6. Tablas y DataFrames Ejecutivos */
div[data-testid="stDataFrame"], div[data-testid="stTable"] {
    background: #FFFFFF !important;
    border: 1px solid #DDE2E6 !important;
    border-radius: 8px !important;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.04) !important;
}

/* 7. Inputs, Textareas, Selectboxes y Checkboxes con Estándar SAP */
div[data-baseweb="select"] > div, 
div[data-testid="stTextInput"] input, 
div[data-testid="stNumberInput"] input, 
div[data-testid="stDateInput"] input,
textarea {
    background-color: #FFFFFF !important;
    border: 1.5px solid #C4C9D0 !important;
    color: #1C2D42 !important;
    border-radius: 6px !important;
    font-size: 0.9rem !important;
}

div[data-baseweb="select"] > div:hover, 
div[data-testid="stTextInput"] input:hover, 
div[data-testid="stNumberInput"] input:hover,
textarea:hover {
    border-color: #89919A !important;
}

div[data-baseweb="select"] > div:focus-within, 
div[data-testid="stTextInput"] input:focus, 
div[data-testid="stNumberInput"] input:focus,
textarea:focus {
    border-color: #0070F2 !important;
    box-shadow: 0 0 0 1px #0070F2 !important;
}

/* Casillas de Verificación (Checkboxes) con Contraste y Borde Definido */
div[data-testid="stCheckbox"] label span[role="checkbox"],
div[data-testid="stCheckbox"] [data-baseweb="checkbox"] span {
    border: 1.5px solid #89919A !important;
    border-radius: 4px !important;
    background-color: #FFFFFF !important;
}

div[data-testid="stCheckbox"] label:hover span[role="checkbox"] {
    border-color: #0070F2 !important;
}

/* 8. Badges Ejecutivos Corporativos (Estándar Semántico SAP Fiori) */
.badge-sop-blue {
    background-color: #EFF6FF !important;
    color: #0070F2 !important;
    border: 1px solid #BFDBFE !important;
    padding: 3px 10px !important;
    border-radius: 4px !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    display: inline-block !important;
    letter-spacing: 0.02em !important;
}

.badge-sop-green {
    background-color: #F1FDF6 !important;
    color: #107E3E !important;
    border: 1px solid #A6E9D5 !important;
    padding: 3px 10px !important;
    border-radius: 4px !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    display: inline-block !important;
    letter-spacing: 0.02em !important;
}

.badge-sop-amber {
    background-color: #FEF7F1 !important;
    color: #E9730C !important;
    border: 1px solid #F8D7B8 !important;
    padding: 3px 10px !important;
    border-radius: 4px !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    display: inline-block !important;
    letter-spacing: 0.02em !important;
}

.badge-sop-red {
    background-color: #FDF3F2 !important;
    color: #BB0000 !important;
    border: 1px solid #F9C6C4 !important;
    padding: 3px 10px !important;
    border-radius: 4px !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    display: inline-block !important;
    letter-spacing: 0.02em !important;
}

.badge-sop-slate {
    background-color: #F5F6F7 !important;
    color: #556B82 !important;
    border: 1px solid #DDE2E6 !important;
    padding: 3px 10px !important;
    border-radius: 4px !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    display: inline-block !important;
    letter-spacing: 0.02em !important;
}
</style>
"""

# Configurar Tema Ejecutivo S&OP en Altair
try:
    @alt.theme.register('sop_ejecutivo', enable=True)
    def _tema_altair_sop():
        return alt.theme.ThemeConfig({
            'config': {
                'background': '#FFFFFF',
                'view': {
                    'stroke': 'transparent',
                    'fill': '#FFFFFF'
                },
                'title': {
                    'color': '#1C2D42',
                    'fontSize': 14,
                    'fontWeight': 600
                },
                'axis': {
                    'domainColor': '#DDE2E6',
                    'gridColor': '#F1F5F9',
                    'labelColor': '#556B82',
                    'titleColor': '#1C2D42',
                    'tickColor': '#DDE2E6'
                },
                'legend': {
                    'labelColor': '#2F3E4D',
                    'titleColor': '#1C2D42'
                },
                'range': {
                    'category': [
                        '#0070F2',  # Demanda / Plan Aprobado (Azul SAP Fiori Horizon)
                        '#059669',  # Oferta / ForeCast (Verde Esmeralda)
                        '#D97706',  # Enraizamiento (Ámbar)
                        '#7C3AED',  # Siembras / Especiales (Púrpura)
                        '#0284C7',  # Capacidad (Celeste)
                        '#BB0000',  # Alerta / Techo (Rojo SAP)
                        '#556B82'   # Neutro (Slate SAP)
                    ]
                }
            }
        })
except Exception:
    pass

def aplicar_tema_invernadero_industrial():
    """Inyecta el tema S&OP Ejecutivo Profesional en la aplicación Streamlit."""
    st.html(CSS_SOP_PROFESIONAL)

# Alias para compatibilidad
aplicar_tema_sop_ejecutivo = aplicar_tema_invernadero_industrial

def estilizar_figura_plotly(fig):
    """
    Aplica el estándar visual corporativo SAP Fiori Horizon a cualquier figura de Plotly:
    lienzo blanco inmaculado, cuadrícula tenue, tipografía clara y paleta oficial.
    """
    fig.update_layout(
        paper_bgcolor='#FFFFFF',
        plot_bgcolor='#FFFFFF',
        font=dict(color='#1C2D42', family="'72', Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"),
        colorway=[
            '#0070F2',  # Demanda / Plan Aprobado (Azul SAP Fiori Horizon)
            '#059669',  # ForeCast / Cosecha Viva (Verde Esmeralda)
            '#D97706',  # Proyección Enraizamiento (Ámbar)
            '#7C3AED',  # Suelo Total / Siembras (Púrpura)
            '#0284C7',  # Capacidad (Celeste)
            '#BB0000',  # Techo / Riesgo (Rojo SAP)
            '#556B82'   # Línea Base Neutra (Gris SAP)
        ],
        xaxis=dict(
            gridcolor='#F1F5F9',
            zerolinecolor='#E2E8F0',
            tickfont=dict(color='#556B82', size=11),
            title_font=dict(color='#1C2D42', size=12)
        ),
        yaxis=dict(
            gridcolor='#F1F5F9',
            zerolinecolor='#E2E8F0',
            tickfont=dict(color='#556B82', size=11),
            title_font=dict(color='#1C2D42', size=12)
        ),
        legend=dict(
            font=dict(color='#2F3E4D', size=12),
            bgcolor='rgba(255, 255, 255, 0.95)',
            bordercolor='#DDE2E6',
            borderwidth=1
        )
    )
    return fig

# Paleta oficial S&OP Profesional SAP Fiori Horizon
PALETA_INVERNADERO = {
    "fondo_app": "#F5F6F7",
    "fondo_panel": "#FFFFFF",
    "borde_metalico": "#DDE2E6",
    "plan_demanda": "#0070F2",
    "forecast_oferta": "#059669",
    "enraizamiento": "#D97706",
    "alerta_techo": "#BB0000",
    "neutro": "#556B82",
    "texto_titulos": "#1C2D42",
    "texto_cuerpo": "#2F3E4D"
}

PALETA_EJECUTIVA = PALETA_INVERNADERO
PALETA_SAP = PALETA_INVERNADERO

def badge_variedad(nombre: str, tipo_color: str = "azul") -> str:
    """Genera HTML para un badge corporativo S&OP."""
    clases = {
        "azul": "badge-sop-blue",
        "verde": "badge-sop-green",
        "ambar": "badge-sop-amber",
        "rojo": "badge-sop-red",
        "gris": "badge-sop-slate",
        "fucsia": "badge-sop-blue",
        "amarillo": "badge-sop-amber",
        "morado": "badge-sop-blue"
    }
    cls = clases.get(tipo_color.lower(), "badge-sop-blue")
    return f'<span class="{cls}">{nombre}</span>'
