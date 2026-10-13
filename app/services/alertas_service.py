import os
import calendar
from datetime import datetime, date, timedelta
import pandas as pd
import streamlit as st

def obtener_alertas_sop():
    """
    Calcula el estado del semáforo y las alertas operativas S&OP
    según las reglas de negocio de la florícola:
    1. Proyección 13 Semanas (Webflowers): Miércoles antes de las 12:00 m.
    2. Proyección 52 Semanas: 4º Jueves de cada mes.
    3. Pedido de Material Vegetal: 1ª semana de cada mes (días 1 al 7).
    """
    now = datetime.now()
    hoy = now.date()
    
    # Archivos clave de insumos
    archivo_siembras = "Siembra Actual (16).xlsx"
    archivo_curvas = "Historico_Curvas.csv"
    
    mtime_siembra = os.path.getmtime(archivo_siembras) if os.path.exists(archivo_siembras) else 0
    mtime_curvas = os.path.getmtime(archivo_curvas) if os.path.exists(archivo_curvas) else 0
    
    dt_siembra = datetime.fromtimestamp(mtime_siembra) if mtime_siembra > 0 else None
    dt_curvas = datetime.fromtimestamp(mtime_curvas) if mtime_curvas > 0 else None
    
    # 1. Alerta 13 Semanas: Miércoles antes de las 12:00 m
    # weekday: 0=Lunes, 1=Martes, 2=Miércoles, 3=Jueves, 4=Viernes, 5=Sábado, 6=Domingo
    dia_sem = hoy.weekday()
    hora_float = now.hour + now.minute / 60.0
    
    # Calcular días transcurridos desde el último lunes (inicio de semana operativa)
    dias_desde_lunes = dia_sem
    lunes_esta_semana = hoy - timedelta(days=dias_desde_lunes)
    
    siembras_esta_semana = dt_siembra and dt_siembra.date() >= lunes_esta_semana
    curvas_esta_semana = dt_curvas and dt_curvas.date() >= lunes_esta_semana
    flujo_completo = siembras_esta_semana and curvas_esta_semana
    
    if dia_sem < 2:  # Lunes o Martes
        if flujo_completo:
            status_13 = "success"
            icon_13 = "🟢"
            msg_13 = "Flujo semanal (Plano + Curvas) ya actualizado. Listo para el cierre del Miércoles."
        else:
            status_13 = "info"
            icon_13 = "🟡"
            msg_13 = "En preparación para el cierre semanal. Plazo límite: Este Miércoles antes de las 12:00 m."
    elif dia_sem == 2 and hora_float < 12.0:  # Miércoles en la mañana
        if flujo_completo:
            status_13 = "success"
            icon_13 = "🟢"
            msg_13 = "✅ Flujo completo cargado a tiempo. Cierre semanal asegurado."
        else:
            status_13 = "warning"
            icon_13 = "⚠️"
            msg_13 = "¡Hoy es día de cierre semanal! Recuerda completar el flujo (Planos + Curvas) antes de las 12:00 m."
    elif dia_sem == 2 and hora_float >= 12.0:  # Miércoles después de mediodía
        if flujo_completo:
            status_13 = "success"
            icon_13 = "🟢"
            msg_13 = "✅ Cierre semanal completado a tiempo con insumos actualizados."
        else:
            status_13 = "error"
            icon_13 = "🔴"
            msg_13 = "Cierre semanal vencido: El plazo límite era hoy a las 12:00 m y faltan insumos por actualizar."
    else:  # Jueves a Domingo
        if flujo_completo:
            status_13 = "success"
            icon_13 = "🟢"
            msg_13 = "Flujo semanal al día. Próximo cierre: Miércoles próximo antes de las 12:00 m."
        else:
            status_13 = "warning"
            icon_13 = "🟡"
            msg_13 = "Pendiente actualizar insumos (Planos/Curvas) para el próximo ciclo semanal."
            
    # 2. Alerta 52 Semanas: 4º Jueves de cada mes
    year, month = hoy.year, hoy.month
    c = calendar.monthcalendar(year, month)
    jueves_mes = [sem[calendar.THURSDAY] for sem in c if sem[calendar.THURSDAY] != 0]
    cuarto_jueves_dia = jueves_mes[3] if len(jueves_mes) >= 4 else jueves_mes[-1]
    fecha_cuarto_jueves = date(year, month, cuarto_jueves_dia)
    diff_dias_52 = (fecha_cuarto_jueves - hoy).days
    
    if diff_dias_52 > 7:
        status_52 = "info"
        icon_52 = "📅"
        msg_52 = f"Próxima entrega anual: 4º Jueves del mes ({fecha_cuarto_jueves.strftime('%d/%m/%Y')}). Faltan {diff_dias_52} días."
    elif 0 < diff_dias_52 <= 7:
        status_52 = "warning"
        icon_52 = "⚠️"
        msg_52 = f"¡Semana de cierre anual! La carga de la matriz de 52 semanas se vence este Jueves {fecha_cuarto_jueves.strftime('%d/%m/%Y')}."
    elif diff_dias_52 == 0:
        status_52 = "warning"
        icon_52 = "🚨"
        msg_52 = f"¡Hoy es el 4º Jueves del mes! Cierre y carga en plataforma de la proyección de 52 Semanas requerida hoy."
    else:
        # Calcular el 4º jueves del mes siguiente
        next_m = month + 1 if month < 12 else 1
        next_y = year if month < 12 else year + 1
        c_next = calendar.monthcalendar(next_y, next_m)
        j_next = [sem[calendar.THURSDAY] for sem in c_next if sem[calendar.THURSDAY] != 0]
        f_next = date(next_y, next_m, j_next[3] if len(j_next) >= 4 else j_next[-1])
        status_52 = "success"
        icon_52 = "✅"
        msg_52 = f"Cierre del 4º jueves del mes superado. Próximo ciclo anual: Jueves {f_next.strftime('%d/%m/%Y')}."
        
    # 3. Alerta Pedido Material Vegetal: 1ª semana de cada mes (días 1 al 7)
    if hoy.day <= 7:
        status_ped = "warning"
        icon_ped = "📦"
        msg_ped = f"¡Ventana de Pedido Activa! Primera semana del mes en curso. Generar y exportar el pedido consolidado a propagación (+24 semanas)."
    else:
        # Próxima primera semana
        next_m_p = month + 1 if month < 12 else 1
        next_y_p = year if month < 12 else year + 1
        meses_es = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        nombre_mes_prox = meses_es[next_m_p - 1]
        status_ped = "info"
        icon_ped = "🗓️"
        msg_ped = f"Ventana de pedido mensual regular cerrada. Próxima emisión regular: Primera semana de {nombre_mes_prox}."

    return {
        "regla_13wk": {
            "titulo": "1. Proyección 13 Semanas (Webflowers)",
            "deadline": "Miércoles antes de las 12:00 m",
            "status": status_13,
            "icono": icon_13,
            "mensaje": msg_13,
            "insumos": {
                "plano_siembras": f"Última carga: {dt_siembra.strftime('%d/%m %H:%M')}" if dt_siembra else "No registrado",
                "curvas_piloto": f"Última carga: {dt_curvas.strftime('%d/%m %H:%M')}" if dt_curvas else "No registrado",
                "completo": flujo_completo
            }
        },
        "regla_52wk": {
            "titulo": "2. Proyección 52 Semanas (Largo Plazo)",
            "deadline": f"4º Jueves del mes ({fecha_cuarto_jueves.strftime('%d/%m/%Y')})",
            "status": status_52,
            "icono": icon_52,
            "mensaje": msg_52,
            "dias_restantes": diff_dias_52
        },
        "regla_pedido": {
            "titulo": "3. Pedido Material Vegetal (Propagación)",
            "deadline": "1ª Semana de cada mes (Días 1 a 7)",
            "status": status_ped,
            "icono": icon_ped,
            "mensaje": msg_ped,
            "activo": hoy.day <= 7
        }
    }

def render_panel_alertas_sop():
    """
    Renderiza el panel visual del Semáforo y Alertas Operativas S&OP
    en la interfaz de Streamlit.
    """
    alertas = obtener_alertas_sop()
    
    st.markdown("### 🧭 Calendario de Gobernanza y Alertas S&OP")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        a = alertas["regla_13wk"]
        with st.container(border=True):
            st.markdown(f"**{a['icono']} {a['titulo']}**")
            st.caption(f"⏰ **Plazo:** {a['deadline']}")
            if a['status'] == 'success':
                st.success(a['mensaje'])
            elif a['status'] == 'warning':
                st.warning(a['mensaje'])
            elif a['status'] == 'error':
                st.error(a['mensaje'])
            else:
                st.info(a['mensaje'])
                
            ins = a['insumos']
            st.markdown(f"<small>🌱 Plano Siembras: {ins['plano_siembras']}<br>📈 Curvas Piloto: {ins['curvas_piloto']}</small>", unsafe_allow_html=True)
            
    with col2:
        a = alertas["regla_52wk"]
        with st.container(border=True):
            st.markdown(f"**{a['icono']} {a['titulo']}**")
            st.caption(f"📅 **Plazo:** {a['deadline']}")
            if a['status'] == 'success':
                st.success(a['mensaje'])
            elif a['status'] == 'warning':
                st.warning(a['mensaje'])
            else:
                st.info(a['mensaje'])
                
            st.markdown("<small>Matriz anual consolidada de inventario vivo + MVA</small>", unsafe_allow_html=True)
            
    with col3:
        a = alertas["regla_pedido"]
        with st.container(border=True):
            st.markdown(f"**{a['icono']} {a['titulo']}**")
            st.caption(f"📦 **Plazo:** {a['deadline']}")
            if a['status'] == 'warning':
                st.warning(a['mensaje'])
            elif a['status'] == 'success':
                st.success(a['mensaje'])
            else:
                st.info(a['mensaje'])
                
            st.markdown("<small>Generación del pedido en piedra a propagación (+24 sem)</small>", unsafe_allow_html=True)
