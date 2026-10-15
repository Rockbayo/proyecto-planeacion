"""
Tema Visual: Invernadero Industrial (Acero, Vidrio y Luces LED Agrícolas)
Paleta Oficial:
- Fondo Principal: #181A1F (Gris acero oscuro)
- Paneles, Tarjetas y Navegación: rgba(40, 43, 48, 0.8) con glassmorphism (backdrop-filter: blur(12px)) y borde 1px solid rgba(255, 255, 255, 0.15)
- Acción Principal / Saludable: #2E8B57 (Verde clorofila)
- Series de Gráficas y Badges de Variedades: #E03C8A (Fucsia), #FFD700 (Amarillo), #8A2BE2 (Morado)
- Alertas y Estados Críticos (Efecto Grow Light LED): box-shadow exterior e interior en magenta (#E03C8A) y naranja eléctrico (#FF8C00)
- Tipografía: Principal blanca (#FFFFFF) y secundaria gris claro (#A6ACB3)
"""

import streamlit as st
import altair as alt

# CSS Invernadero Industrial
CSS_INVERNADERO_INDUSTRIAL = """
<style>
/* ====================================================================
   TEMA VISUAL: INVERNADERO INDUSTRIAL (ACERO, VIDRIO Y LUCES GROW LED)
   ==================================================================== */

/* 1. Fondo Principal Acero Oscuro y Tipografía Global */
html, body, [data-testid="stAppViewContainer"], .main, .stApp {
    background-color: #181A1F !important;
    color: #FFFFFF !important;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
}

header[data-testid="stHeader"] {
    background-color: rgba(24, 26, 31, 0.85) !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border-bottom: 1px solid rgba(255, 255, 255, 0.12) !important;
}

/* Encabezados y Textos */
h1, h2, h3, h4, h5, h6, .stHeading, [data-testid="stHeading"] {
    color: #FFFFFF !important;
    font-weight: 600 !important;
    letter-spacing: -0.02em !important;
}

p, span, label, [data-testid="stMarkdownContainer"] p, [data-testid="stText"] {
    color: #FFFFFF !important;
}

.stCaption, small, [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p, [data-testid="stWidgetLabel"] small {
    color: #A6ACB3 !important;
}

/* 2. Barra Lateral (Sidebar) Efecto Acero Pulido y Vidrio */
section[data-testid="stSidebar"] {
    background-color: rgba(24, 26, 31, 0.95) !important;
    backdrop-filter: blur(14px) !important;
    -webkit-backdrop-filter: blur(14px) !important;
    border-right: 1px solid rgba(255, 255, 255, 0.15) !important;
}

section[data-testid="stSidebar"] > div:first-child {
    background: transparent !important;
}

section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3 {
    color: #2E8B57 !important;
    text-shadow: 0 0 10px rgba(46, 139, 87, 0.3);
}

/* 3. Tarjetas, Paneles y Contenedores con Efecto Glassmorphism */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: rgba(40, 43, 48, 0.8) !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
    border-radius: 12px !important;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.35) !important;
}

div[data-testid="stVerticalBlockBorderWrapper"] > div {
    background: transparent !important;
}

/* Tarjetas de Métricas / KPI Cards */
div[data-testid="stMetric"] {
    background: rgba(40, 43, 48, 0.8) !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
    border-radius: 12px !important;
    padding: 16px 20px !important;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3) !important;
}

div[data-testid="stMetricLabel"] p {
    color: #A6ACB3 !important;
    font-size: 0.85rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
}

div[data-testid="stMetricValue"] {
    color: #FFFFFF !important;
    font-weight: 700 !important;
    font-size: 1.8rem !important;
}

/* Expanders */
details[data-testid="stExpander"] {
    background: rgba(40, 43, 48, 0.8) !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
    border-radius: 12px !important;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25) !important;
}

details[data-testid="stExpander"] summary {
    color: #FFFFFF !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
}

/* Pestañas (Tabs) */
div[data-testid="stTabs"] {
    background: transparent !important;
}

div[data-baseweb="tab-list"] {
    background: rgba(40, 43, 48, 0.6) !important;
    backdrop-filter: blur(8px) !important;
    -webkit-backdrop-filter: blur(8px) !important;
    border: 1px solid rgba(255, 255, 255, 0.12) !important;
    border-radius: 10px !important;
    padding: 4px !important;
    gap: 6px !important;
}

button[data-baseweb="tab"] {
    border-radius: 8px !important;
    color: #A6ACB3 !important;
    border: none !important;
    padding: 8px 16px !important;
    font-weight: 500 !important;
    transition: all 0.2s ease !important;
}

button[data-baseweb="tab"][aria-selected="true"] {
    background: rgba(46, 139, 87, 0.25) !important;
    color: #2E8B57 !important;
    border: 1px solid rgba(46, 139, 87, 0.5) !important;
    font-weight: 700 !important;
    box-shadow: 0 0 10px rgba(46, 139, 87, 0.3) !important;
}

div[data-baseweb="tab-highlight"] {
    background-color: #2E8B57 !important;
}

/* 4. Botones y Acciones (Verde Clorofila #2E8B57) */
button[kind="primary"], .stButton > button[kind="primary"] {
    background-color: #2E8B57 !important;
    color: #FFFFFF !important;
    border: 1px solid rgba(255, 255, 255, 0.25) !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    box-shadow: 0 0 14px rgba(46, 139, 87, 0.5) !important;
    transition: all 0.25s ease-in-out !important;
}

button[kind="primary"]:hover, .stButton > button[kind="primary"]:hover {
    background-color: #38a169 !important;
    box-shadow: 0 0 24px rgba(46, 139, 87, 0.8), 0 0 8px #2E8B57 !important;
    transform: translateY(-1px) !important;
}

button[kind="secondary"], .stButton > button:not([kind="primary"]) {
    background: rgba(40, 43, 48, 0.85) !important;
    color: #FFFFFF !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
    border-radius: 8px !important;
    backdrop-filter: blur(8px) !important;
    -webkit-backdrop-filter: blur(8px) !important;
    transition: all 0.25s ease !important;
}

button[kind="secondary"]:hover, .stButton > button:not([kind="primary"]):hover {
    border-color: #2E8B57 !important;
    color: #2E8B57 !important;
    box-shadow: 0 0 12px rgba(46, 139, 87, 0.35) !important;
}

/* 5. Alertas y Estados Críticos (Efecto Grow Light LED Agrícola) */
/* Error / Retrasos Críticos -> Grow Light LED Magenta (#E03C8A) */
div[data-testid="stAlert"]:has(svg[data-testid="stAlertErrorIcon"]),
div[data-testid="stAlert"]:has([data-testid="stAlertContentError"]),
div[data-testid="stAlert"][kind="error"],
.stAlert:has(svg[data-testid="stAlertErrorIcon"]),
.stAlert:has([data-testid="stAlertContentError"]) {
    background: rgba(35, 18, 30, 0.88) !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border: 1px solid #E03C8A !important;
    border-radius: 12px !important;
    box-shadow: 0 0 28px rgba(224, 60, 138, 0.65), inset 0 0 14px rgba(224, 60, 138, 0.25) !important;
    color: #FFD6EA !important;
}

div[data-testid="stAlert"]:has(svg[data-testid="stAlertErrorIcon"]) *,
div[data-testid="stAlert"]:has([data-testid="stAlertContentError"]) * {
    color: #FFD6EA !important;
}

div[data-testid="stAlert"]:has(svg[data-testid="stAlertErrorIcon"]) svg,
div[data-testid="stAlert"]:has([data-testid="stAlertContentError"]) svg {
    fill: #E03C8A !important;
    color: #E03C8A !important;
    filter: drop-shadow(0 0 6px #E03C8A);
}

/* Advertencias Preventivas -> Grow Light LED Naranja Eléctrico (#FF8C00) */
div[data-testid="stAlert"]:has(svg[data-testid="stAlertWarningIcon"]),
div[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]),
div[data-testid="stAlert"][kind="warning"],
.stAlert:has(svg[data-testid="stAlertWarningIcon"]),
.stAlert:has([data-testid="stAlertContentWarning"]) {
    background: rgba(40, 25, 12, 0.88) !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border: 1px solid #FF8C00 !important;
    border-radius: 12px !important;
    box-shadow: 0 0 28px rgba(255, 140, 0, 0.65), inset 0 0 14px rgba(255, 140, 0, 0.25) !important;
    color: #FFE6CC !important;
}

div[data-testid="stAlert"]:has(svg[data-testid="stAlertWarningIcon"]) *,
div[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]) * {
    color: #FFE6CC !important;
}

div[data-testid="stAlert"]:has(svg[data-testid="stAlertWarningIcon"]) svg,
div[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]) svg {
    fill: #FF8C00 !important;
    color: #FF8C00 !important;
    filter: drop-shadow(0 0 6px #FF8C00);
}

/* Éxito / Estado Saludable -> Grow Light LED Verde Clorofila (#2E8B57) */
div[data-testid="stAlert"]:has(svg[data-testid="stAlertSuccessIcon"]),
div[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]),
div[data-testid="stAlert"][kind="success"],
.stAlert:has(svg[data-testid="stAlertSuccessIcon"]),
.stAlert:has([data-testid="stAlertContentSuccess"]) {
    background: rgba(18, 35, 25, 0.88) !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border: 1px solid #2E8B57 !important;
    border-radius: 12px !important;
    box-shadow: 0 0 28px rgba(46, 139, 87, 0.65), inset 0 0 14px rgba(46, 139, 87, 0.25) !important;
    color: #D4EDDA !important;
}

div[data-testid="stAlert"]:has(svg[data-testid="stAlertSuccessIcon"]) *,
div[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]) * {
    color: #D4EDDA !important;
}

div[data-testid="stAlert"]:has(svg[data-testid="stAlertSuccessIcon"]) svg,
div[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]) svg {
    fill: #2E8B57 !important;
    color: #2E8B57 !important;
    filter: drop-shadow(0 0 6px #2E8B57);
}

/* Info -> Acero y Azul Neón */
div[data-testid="stAlert"]:has(svg[data-testid="stAlertInfoIcon"]),
div[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]),
div[data-testid="stAlert"][kind="info"],
.stAlert:has(svg[data-testid="stAlertInfoIcon"]),
.stAlert:has([data-testid="stAlertContentInfo"]) {
    background: rgba(20, 30, 45, 0.88) !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(0, 191, 255, 0.6) !important;
    border-radius: 12px !important;
    box-shadow: 0 0 28px rgba(0, 191, 255, 0.45), inset 0 0 14px rgba(0, 191, 255, 0.15) !important;
    color: #D9F2FF !important;
}

div[data-testid="stAlert"]:has(svg[data-testid="stAlertInfoIcon"]) *,
div[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) * {
    color: #D9F2FF !important;
}

/* 6. Tablas y DataFrames con Estilo Acero y Vidrio */
div[data-testid="stDataFrame"], div[data-testid="stTable"] {
    background: rgba(40, 43, 48, 0.75) !important;
    backdrop-filter: blur(8px) !important;
    -webkit-backdrop-filter: blur(8px) !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
    border-radius: 10px !important;
}

/* 7. Inputs, Textareas, Selectboxes */
div[data-baseweb="select"] > div, input, textarea {
    background-color: rgba(30, 33, 38, 0.9) !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
    color: #FFFFFF !important;
    border-radius: 8px !important;
}

div[data-baseweb="popover"], div[data-baseweb="menu"] {
    background-color: #202328 !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
}

/* Badges de Variedades de Flores de Alto Contraste */
.badge-fucsia {
    background-color: rgba(224, 60, 138, 0.22) !important;
    color: #E03C8A !important;
    border: 1px solid #E03C8A !important;
    padding: 3px 10px !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
    box-shadow: 0 0 8px rgba(224, 60, 138, 0.4) !important;
    display: inline-block !important;
}

.badge-amarillo {
    background-color: rgba(255, 215, 0, 0.22) !important;
    color: #FFD700 !important;
    border: 1px solid #FFD700 !important;
    padding: 3px 10px !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
    box-shadow: 0 0 8px rgba(255, 215, 0, 0.4) !important;
    display: inline-block !important;
}

.badge-morado {
    background-color: rgba(138, 43, 226, 0.22) !important;
    color: #BA68C8 !important;
    border: 1px solid #8A2BE2 !important;
    padding: 3px 10px !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
    box-shadow: 0 0 8px rgba(138, 43, 226, 0.4) !important;
    display: inline-block !important;
}

.badge-verde {
    background-color: rgba(46, 139, 87, 0.22) !important;
    color: #2E8B57 !important;
    border: 1px solid #2E8B57 !important;
    padding: 3px 10px !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
    box-shadow: 0 0 8px rgba(46, 139, 87, 0.4) !important;
    display: inline-block !important;
}
</style>
"""

# Configurar Tema Invernadero Industrial en Altair
try:
    @alt.theme.register('invernadero_industrial', enable=True)
    def _tema_altair_invernadero():
        return alt.theme.ThemeConfig({
            'config': {
                'background': 'rgba(40, 43, 48, 0.8)',
                'view': {
                    'stroke': 'transparent',
                    'fill': 'rgba(24, 26, 31, 0.6)'
                },
                'title': {
                    'color': '#FFFFFF',
                    'fontSize': 14,
                    'fontWeight': 600
                },
                'axis': {
                    'domainColor': 'rgba(255, 255, 255, 0.18)',
                    'gridColor': 'rgba(255, 255, 255, 0.08)',
                    'labelColor': '#A6ACB3',
                    'titleColor': '#FFFFFF',
                    'tickColor': 'rgba(255, 255, 255, 0.18)'
                },
                'legend': {
                    'labelColor': '#FFFFFF',
                    'titleColor': '#FFFFFF'
                },
                'range': {
                    'category': ['#E03C8A', '#FFD700', '#8A2BE2', '#2E8B57', '#00E5FF', '#FF8C00']
                }
            }
        })
except Exception:
    pass

def aplicar_tema_invernadero_industrial():
    """Inyecta el tema Invernadero Industrial en la aplicación Streamlit."""
    st.html(CSS_INVERNADERO_INDUSTRIAL)

def estilizar_figura_plotly(fig):
    """
    Aplica el tema visual Invernadero Industrial (Acero, Vidrio, Alto Contraste)
    a una figura de Plotly para integración perfecta con el tema oscuro.
    """
    fig.update_layout(
        paper_bgcolor='rgba(40, 43, 48, 0.7)',
        plot_bgcolor='rgba(24, 26, 31, 0.7)',
        font=dict(color='#FFFFFF', family='-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'),
        colorway=["#E03C8A", "#FFD700", "#8A2BE2", "#2E8B57", "#00E5FF", "#FF8C00"],
        xaxis=dict(
            gridcolor='rgba(255, 255, 255, 0.10)',
            zerolinecolor='rgba(255, 255, 255, 0.18)',
            tickfont=dict(color='#A6ACB3'),
            title_font=dict(color='#FFFFFF')
        ),
        yaxis=dict(
            gridcolor='rgba(255, 255, 255, 0.10)',
            zerolinecolor='rgba(255, 255, 255, 0.18)',
            tickfont=dict(color='#A6ACB3'),
            title_font=dict(color='#FFFFFF')
        ),
        legend=dict(
            font=dict(color='#FFFFFF'),
            bgcolor='rgba(30, 33, 38, 0.65)',
            bordercolor='rgba(255, 255, 255, 0.15)'
        )
    )
    return fig

# Paleta oficial Invernadero Industrial
PALETA_INVERNADERO = {
    "fondo_app": "#181A1F",
    "fondo_panel": "rgba(40, 43, 48, 0.8)",
    "borde_metalico": "rgba(255, 255, 255, 0.15)",
    "verde_clorofila": "#2E8B57",
    "fucsia": "#E03C8A",
    "amarillo": "#FFD700",
    "morado": "#8A2BE2",
    "texto_blanco": "#FFFFFF",
    "texto_gris": "#A6ACB3",
    "grow_light_magenta": "rgba(224, 60, 138, 0.65)",
    "grow_light_orange": "rgba(255, 140, 0, 0.65)"
}

def badge_variedad(nombre: str, tipo_color: str = "fucsia") -> str:
    """Genera HTML para un badge de variedad en la paleta de alto contraste."""
    clases = {
        "fucsia": "badge-fucsia",
        "amarillo": "badge-amarillo",
        "morado": "badge-morado",
        "verde": "badge-verde"
    }
    cls = clases.get(tipo_color.lower(), "badge-fucsia")
    return f'<span class="{cls}">{nombre}</span>'
