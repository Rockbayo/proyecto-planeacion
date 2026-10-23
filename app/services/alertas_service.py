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
    con simetría milimétrica utilizando st.html y CSS Grid nativo (SAP Fiori Horizon).
    Garantiza que las 3 tarjetas tengan exactamente la misma altura física en pantalla.
    """
    alertas = obtener_alertas_sop()
    
    st.markdown("### 🧭 Calendario de Gobernanza y Alertas S&OP")
    
    a1 = alertas["regla_13wk"]
    a2 = alertas["regla_52wk"]
    a3 = alertas["regla_pedido"]
    
    def get_alert_props(status):
        if status == 'success':
            return 'sap-alert-success', '✓', 'sap-badge-ok', 'Al Día'
        elif status == 'warning':
            return 'sap-alert-warning', '⚠', 'sap-badge-warn', 'Atención'
        elif status == 'error':
            return 'sap-alert-error', '✕', 'sap-badge-err', 'Vencido'
        else:
            return 'sap-alert-info', 'ℹ', 'sap-badge-info', 'Informativo'

    cls1, ic1, bg_cls1, bg_txt1 = get_alert_props(a1['status'])
    cls2, ic2, bg_cls2, bg_txt2 = get_alert_props(a2['status'])
    cls3, ic3, bg_cls3, bg_txt3 = get_alert_props(a3['status'])
    
    ins = a1['insumos']
    status_ped_txt = '🟢 Ventana Activa' if a3.get('activo') else '⚪ Ventana Regular Cerrada'
    
    html = (
        '<div style="display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1.25rem; margin-top: 10px; margin-bottom: 24px; align-items: stretch;">'
        '<!-- Tarjeta 1 -->'
        '<div class="cs-card" style="margin-bottom: 0; display: flex; flex-direction: column; justify-content: space-between; height: 100%; min-height: 240px; box-sizing: border-box; padding: 1.25rem 1.5rem;">'
        '<div>'
        f'<div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--sap-border-subtle); padding-bottom: 8px; margin-bottom: 10px;"><span style="font-weight: 700; font-size: 0.95rem; color: var(--sap-text-primary);">{a1["icono"]} {a1["titulo"]}</span><span class="sap-badge {bg_cls1}">{bg_txt1}</span></div>'
        f'<div style="font-size: 0.82rem; color: var(--sap-text-secondary); margin-bottom: 10px; font-weight: 500; min-height: 20px;">⏰ <b>Plazo:</b> {a1["deadline"]}</div>'
        f'<div class="{cls1}" style="min-height: 68px; display: flex; align-items: center; padding: 0.75rem 1rem; border-radius: 6px; font-size: 0.84rem; line-height: 1.35; margin-bottom: 12px; box-sizing: border-box;"><span><b>{ic1}</b> {a1["mensaje"]}</span></div>'
        '</div>'
        f'<div style="border-top: 1px solid var(--sap-border-subtle); padding-top: 10px; font-size: 0.80rem; color: var(--sap-text-secondary); line-height: 1.5; min-height: 42px; display: flex; flex-direction: column; justify-content: center;">• Plano Siembras: {ins["plano_siembras"]}<br>• Curvas Piloto: {ins["curvas_piloto"]}</div>'
        '</div>'
        '<!-- Tarjeta 2 -->'
        '<div class="cs-card" style="margin-bottom: 0; display: flex; flex-direction: column; justify-content: space-between; height: 100%; min-height: 240px; box-sizing: border-box; padding: 1.25rem 1.5rem;">'
        '<div>'
        f'<div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--sap-border-subtle); padding-bottom: 8px; margin-bottom: 10px;"><span style="font-weight: 700; font-size: 0.95rem; color: var(--sap-text-primary);">{a2["icono"]} {a2["titulo"]}</span><span class="sap-badge {bg_cls2}">{bg_txt2}</span></div>'
        f'<div style="font-size: 0.82rem; color: var(--sap-text-secondary); margin-bottom: 10px; font-weight: 500; min-height: 20px;">📅 <b>Plazo:</b> {a2["deadline"]}</div>'
        f'<div class="{cls2}" style="min-height: 68px; display: flex; align-items: center; padding: 0.75rem 1rem; border-radius: 6px; font-size: 0.84rem; line-height: 1.35; margin-bottom: 12px; box-sizing: border-box;"><span><b>{ic2}</b> {a2["mensaje"]}</span></div>'
        '</div>'
        '<div style="border-top: 1px solid var(--sap-border-subtle); padding-top: 10px; font-size: 0.80rem; color: var(--sap-text-secondary); line-height: 1.5; min-height: 42px; display: flex; flex-direction: column; justify-content: center;">• Ciclo Anual: 4º Jueves de cada mes<br>• Estado: Matriz de 52 semanas activa</div>'
        '</div>'
        '<!-- Tarjeta 3 -->'
        '<div class="cs-card" style="margin-bottom: 0; display: flex; flex-direction: column; justify-content: space-between; height: 100%; min-height: 240px; box-sizing: border-box; padding: 1.25rem 1.5rem;">'
        '<div>'
        f'<div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--sap-border-subtle); padding-bottom: 8px; margin-bottom: 10px;"><span style="font-weight: 700; font-size: 0.95rem; color: var(--sap-text-primary);">{a3["icono"]} {a3["titulo"]}</span><span class="sap-badge {bg_cls3}">{bg_txt3}</span></div>'
        f'<div style="font-size: 0.82rem; color: var(--sap-text-secondary); margin-bottom: 10px; font-weight: 500; min-height: 20px;">📦 <b>Plazo:</b> {a3["deadline"]}</div>'
        f'<div class="{cls3}" style="min-height: 68px; display: flex; align-items: center; padding: 0.75rem 1rem; border-radius: 6px; font-size: 0.84rem; line-height: 1.35; margin-bottom: 12px; box-sizing: border-box;"><span><b>{ic3}</b> {a3["mensaje"]}</span></div>'
        '</div>'
        f'<div style="border-top: 1px solid var(--sap-border-subtle); padding-top: 10px; font-size: 0.80rem; color: var(--sap-text-secondary); line-height: 1.5; min-height: 42px; display: flex; flex-direction: column; justify-content: center;">• Ventana Mensual: Días 1 al 7 de cada mes<br>• Estado: {status_ped_txt}</div>'
        '</div>'
        '</div>'
    )
    st.html(html)
