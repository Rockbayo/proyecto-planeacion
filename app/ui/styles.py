"""
Tema Visual: S&OP Ejecutivo Profesional (Estilo SAP IBP / Kinaxis RapidResponse / o9 Solutions)
Arquitectura Visual:
- Canvas Principal: #F8FAFC (Slate-50 de alta legibilidad y confort visual)
- Superficies y Tarjetas: #FFFFFF (Blanco nítido con micro-borde #E2E8F0 y sombra sutil)
- Command Center Sidebar: #0F172A (Navy Slate Corporativo con acentos en #3B82F6)
- Tipografía: Inter / Segoe UI (Negro pizarra #0F172A para títulos, #334155 para lectura, #64748B para metadata)
- Botones de Acción: #1D4ED8 (Azul Zafiro Corporativo, hover #1E40AF)
- Paleta S&OP para Curvas:
    * #1D4ED8 (Plan de Producción / Demanda Comercial)
    * #059669 (ForeCast Biológico / Oferta de Cosecha)
    * #D97706 (Pedido Propagación / Enraizamiento)
    * #DC2626 (Capacidad Máxima / Restricciones / Sobrecupos)
    * #94A3B8 (Línea Base Histórica)
- Alertas y Semáforos: Cintas corporativas limpias (Verde #F0FDF4, Ámbar #FFFBEB, Rojo #FEF2F2, Azul #EFF6FF)
"""

import streamlit as st
import altair as alt

CSS_SOP_PROFESIONAL = """
<style>
/* ====================================================================
   S&OP ENTERPRISE EXECUTIVE THEME (SAP IBP / KINAXIS STYLE)
   ==================================================================== */

/* 1. Fondo Global y Tipografía Corporativa */
html, body, [data-testid="stAppViewContainer"], .main, .stApp {
    background-color: #F8FAFC !important;
    color: #1E293B !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
    -webkit-font-smoothing: antialiased !important;
}

header[data-testid="stHeader"] {
    background-color: #FFFFFF !important;
    border-bottom: 1px solid #E2E8F0 !important;
}

/* Encabezados y Jerarquía de Texto */
h1, h2, h3, h4, h5, h6, .stHeading, [data-testid="stHeading"] {
    color: #0F172A !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
}

p, span, label, [data-testid="stMarkdownContainer"] p, [data-testid="stText"] {
    color: #334155 !important;
    font-size: 0.925rem !important;
    line-height: 1.5 !important;
}

.stCaption, small, [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p, [data-testid="stWidgetLabel"] small {
    color: #475569 !important;
    font-size: 0.835rem !important;
    font-weight: 500 !important;
}

/* 2. Barra Lateral: Command Center Ejecutivo (Navy Slate) de Alto Contraste */
section[data-testid="stSidebar"],
section[data-testid="stSidebar"] > div {
    background-color: #0F172A !important;
    border-right: 1px solid #1E293B !important;
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
    background-color: #1E293B !important;
    border-left: 3.5px solid #3B82F6 !important;
}

/* 3. Contenedores y Tarjetas de Alto Nivel */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
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
    border: 1px solid #E2E8F0 !important;
    border-radius: 8px !important;
    padding: 16px 20px !important;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05) !important;
    transition: box-shadow 0.15s ease, border-color 0.15s ease !important;
}

div[data-testid="stMetric"]:hover {
    border-color: #CBD5E1 !important;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.07) !important;
}

div[data-testid="stMetricLabel"] p {
    color: #64748B !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
}

div[data-testid="stMetricValue"] {
    color: #0F172A !important;
    font-weight: 700 !important;
    font-size: 1.85rem !important;
    letter-spacing: -0.02em !important;
}

/* Expanders */
details[data-testid="stExpander"] {
    background: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 8px !important;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.03) !important;
}

details[data-testid="stExpander"] summary {
    color: #0F172A !important;
    font-weight: 600 !important;
    font-size: 0.92rem !important;
    padding: 12px 16px !important;
}

/* Pestañas (Tabs) Estilo Ribbon Corporativo */
div[data-testid="stTabs"] {
    background: transparent !important;
}

div[data-baseweb="tab-list"] {
    background: #F1F5F9 !important;
    border-radius: 8px !important;
    padding: 4px !important;
    border: 1px solid #E2E8F0 !important;
    gap: 4px !important;
}

button[data-baseweb="tab"] {
    border-radius: 6px !important;
    color: #64748B !important;
    border: none !important;
    padding: 8px 16px !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    transition: all 0.15s ease !important;
}

button[data-baseweb="tab"]:hover {
    color: #0F172A !important;
    background: rgba(255, 255, 255, 0.6) !important;
}

button[data-baseweb="tab"][aria-selected="true"] {
    background: #FFFFFF !important;
    color: #1D4ED8 !important;
    font-weight: 600 !important;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1) !important;
}

div[data-baseweb="tab-highlight"] {
    display: none !important;
}

/* 4. Botones y Controles de Acción Estandarizados (Formato S&OP Consolidado) */
button,
button[kind="primary"],
button[kind="secondary"],
.stButton > button,
button[data-testid^="baseButton-"],
div[data-testid="stDownloadButton"] > button {
    background-color: #1D4ED8 !important;
    color: #FFFFFF !important;
    border: 1px solid #1E40AF !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    font-size: 0.90rem !important;
    padding: 8px 18px !important;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05) !important;
    transition: background-color 0.15s ease, box-shadow 0.15s ease !important;
}

button:hover,
button[kind="primary"]:hover,
button[kind="secondary"]:hover,
.stButton > button:hover,
button[data-testid^="baseButton-"]:hover,
div[data-testid="stDownloadButton"] > button:hover {
    background-color: #1E40AF !important;
    box-shadow: 0 2px 4px 0 rgba(0, 0, 0, 0.12) !important;
    border-color: #172554 !important;
}

/* Forzar Texto Blanco Nítido en TODOS los Hijos y Elementos Internos de Botón */
button *,
button p,
button span,
button div,
.stButton > button *,
.stButton > button p,
.stButton > button span,
button[data-testid^="baseButton-"] *,
button[data-testid^="baseButton-"] p,
button[data-testid^="baseButton-"] span,
div[data-testid="stDownloadButton"] > button *,
div[data-testid="stDownloadButton"] > button p,
div[data-testid="stDownloadButton"] > button span {
    color: #FFFFFF !important;
    font-weight: 600 !important;
}

/* 5. Alertas S&OP de Alta Dirección (Cintas Corporativas sin Neón) */
/* Alerta Error / Retraso Crítico */
div[data-testid="stAlert"]:has(svg[data-testid="stAlertErrorIcon"]),
div[data-testid="stAlert"]:has([data-testid="stAlertContentError"]),
div[data-testid="stAlert"][kind="error"],
.stAlert:has(svg[data-testid="stAlertErrorIcon"]),
.stAlert:has([data-testid="stAlertContentError"]) {
    background-color: #FEF2F2 !important;
    border: 1px solid #FECACA !important;
    border-left: 4px solid #DC2626 !important;
    border-radius: 6px !important;
    color: #991B1B !important;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.04) !important;
}

div[data-testid="stAlert"]:has(svg[data-testid="stAlertErrorIcon"]) *,
div[data-testid="stAlert"]:has([data-testid="stAlertContentError"]) * {
    color: #991B1B !important;
}

/* Alerta Warning / Atención Preventiva */
div[data-testid="stAlert"]:has(svg[data-testid="stAlertWarningIcon"]),
div[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]),
div[data-testid="stAlert"][kind="warning"],
.stAlert:has(svg[data-testid="stAlertWarningIcon"]),
.stAlert:has([data-testid="stAlertContentWarning"]) {
    background-color: #FFFBEB !important;
    border: 1px solid #FDE68A !important;
    border-left: 4px solid #D97706 !important;
    border-radius: 6px !important;
    color: #92400E !important;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.04) !important;
}

div[data-testid="stAlert"]:has(svg[data-testid="stAlertWarningIcon"]) *,
div[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]) * {
    color: #92400E !important;
}

/* Alerta Success / Cumplimiento Óptimo */
div[data-testid="stAlert"]:has(svg[data-testid="stAlertSuccessIcon"]),
div[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]),
div[data-testid="stAlert"][kind="success"],
.stAlert:has(svg[data-testid="stAlertSuccessIcon"]),
.stAlert:has([data-testid="stAlertContentSuccess"]) {
    background-color: #F0FDF4 !important;
    border: 1px solid #BBF7D0 !important;
    border-left: 4px solid #16A34A !important;
    border-radius: 6px !important;
    color: #166534 !important;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.04) !important;
}

div[data-testid="stAlert"]:has(svg[data-testid="stAlertSuccessIcon"]) *,
div[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]) * {
    color: #166534 !important;
}

/* Alerta Info / Informativo de Gobierno */
div[data-testid="stAlert"]:has(svg[data-testid="stAlertInfoIcon"]),
div[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]),
div[data-testid="stAlert"][kind="info"],
.stAlert:has(svg[data-testid="stAlertInfoIcon"]),
.stAlert:has([data-testid="stAlertContentInfo"]) {
    background-color: #EFF6FF !important;
    border: 1px solid #BFDBFE !important;
    border-left: 4px solid #1D4ED8 !important;
    border-radius: 6px !important;
    color: #1E40AF !important;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.04) !important;
}

div[data-testid="stAlert"]:has(svg[data-testid="stAlertInfoIcon"]) *,
div[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) * {
    color: #1E40AF !important;
}

/* 6. Tablas y DataFrames Ejecutivos */
div[data-testid="stDataFrame"], div[data-testid="stTable"] {
    background: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 8px !important;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.04) !important;
}

/* 7. Inputs, Textareas, Selectboxes y Checkboxes con Borde Nítido */
div[data-baseweb="select"] > div, 
div[data-testid="stTextInput"] input, 
div[data-testid="stNumberInput"] input, 
div[data-testid="stDateInput"] input,
textarea {
    background-color: #FFFFFF !important;
    border: 1.5px solid #94A3B8 !important;
    color: #0F172A !important;
    border-radius: 6px !important;
    font-size: 0.9rem !important;
}

div[data-baseweb="select"] > div:hover, 
div[data-testid="stTextInput"] input:hover, 
div[data-testid="stNumberInput"] input:hover,
textarea:hover {
    border-color: #475569 !important;
}

div[data-baseweb="select"] > div:focus-within, 
div[data-testid="stTextInput"] input:focus, 
div[data-testid="stNumberInput"] input:focus,
textarea:focus {
    border-color: #1D4ED8 !important;
    box-shadow: 0 0 0 1px #1D4ED8 !important;
}

/* Casillas de Verificación (Checkboxes) con Contraste y Borde Definido */
div[data-testid="stCheckbox"] label span[role="checkbox"],
div[data-testid="stCheckbox"] [data-baseweb="checkbox"] span {
    border: 1.5px solid #64748B !important;
    border-radius: 4px !important;
    background-color: #FFFFFF !important;
}

div[data-testid="stCheckbox"] label:hover span[role="checkbox"] {
    border-color: #1D4ED8 !important;
}

/* 8. Badges Ejecutivos Corporativos */
.badge-sop-blue {
    background-color: #EFF6FF !important;
    color: #1D4ED8 !important;
    border: 1px solid #BFDBFE !important;
    padding: 3px 10px !important;
    border-radius: 4px !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    display: inline-block !important;
    letter-spacing: 0.02em !important;
}

.badge-sop-green {
    background-color: #F0FDF4 !important;
    color: #166534 !important;
    border: 1px solid #BBF7D0 !important;
    padding: 3px 10px !important;
    border-radius: 4px !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    display: inline-block !important;
    letter-spacing: 0.02em !important;
}

.badge-sop-amber {
    background-color: #FFFBEB !important;
    color: #92400E !important;
    border: 1px solid #FDE68A !important;
    padding: 3px 10px !important;
    border-radius: 4px !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    display: inline-block !important;
    letter-spacing: 0.02em !important;
}

.badge-sop-red {
    background-color: #FEF2F2 !important;
    color: #991B1B !important;
    border: 1px solid #FECACA !important;
    padding: 3px 10px !important;
    border-radius: 4px !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    display: inline-block !important;
    letter-spacing: 0.02em !important;
}

.badge-sop-slate {
    background-color: #F1F5F9 !important;
    color: #475569 !important;
    border: 1px solid #CBD5E1 !important;
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
                    'color': '#0F172A',
                    'fontSize': 14,
                    'fontWeight': 600
                },
                'axis': {
                    'domainColor': '#CBD5E1',
                    'gridColor': '#F1F5F9',
                    'labelColor': '#64748B',
                    'titleColor': '#0F172A',
                    'tickColor': '#CBD5E1'
                },
                'legend': {
                    'labelColor': '#334155',
                    'titleColor': '#0F172A'
                },
                'range': {
                    'category': [
                        '#1D4ED8',  # Demanda / Plan
                        '#059669',  # Oferta / ForeCast
                        '#D97706',  # Enraizamiento
                        '#7C3AED',  # Especiales
                        '#0284C7',  # Ajustado
                        '#DC2626',  # Alerta
                        '#64748B'   # Neutro
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
    Aplica el estándar visual corporativo S&OP a cualquier figura de Plotly:
    lienzo blanco inmaculado, cuadrícula tenue, tipografía clara y paleta oficial.
    """
    fig.update_layout(
        paper_bgcolor='#FFFFFF',
        plot_bgcolor='#FFFFFF',
        font=dict(color='#0F172A', family='Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'),
        colorway=[
            '#1D4ED8',  # Demanda / Plan Aprobado (Azul Zafiro)
            '#059669',  # ForeCast / Cosecha Viva (Verde Esmeralda)
            '#D97706',  # Proyección Enraizamiento (Ámbar)
            '#7C3AED',  # Fast Track
            '#0284C7',  # Capacidad
            '#DC2626',  # Techo / Riesgo
            '#64748B'   # Línea Base
        ],
        xaxis=dict(
            gridcolor='#F1F5F9',
            zerolinecolor='#E2E8F0',
            tickfont=dict(color='#64748B', size=11),
            title_font=dict(color='#0F172A', size=12)
        ),
        yaxis=dict(
            gridcolor='#F1F5F9',
            zerolinecolor='#E2E8F0',
            tickfont=dict(color='#64748B', size=11),
            title_font=dict(color='#0F172A', size=12)
        ),
        legend=dict(
            font=dict(color='#334155', size=12),
            bgcolor='rgba(255, 255, 255, 0.95)',
            bordercolor='#E2E8F0',
            borderwidth=1
        )
    )
    return fig

# Paleta oficial S&OP Profesional
PALETA_INVERNADERO = {
    "fondo_app": "#F8FAFC",
    "fondo_panel": "#FFFFFF",
    "borde_metalico": "#E2E8F0",
    "plan_demanda": "#1D4ED8",
    "forecast_oferta": "#059669",
    "enraizamiento": "#D97706",
    "alerta_techo": "#DC2626",
    "neutro": "#64748B",
    "texto_titulos": "#0F172A",
    "texto_cuerpo": "#334155"
}

PALETA_EJECUTIVA = PALETA_INVERNADERO

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
