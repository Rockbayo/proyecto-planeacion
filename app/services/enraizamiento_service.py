import os
import glob
import json
import math
from datetime import date, timedelta
import pandas as pd
from sqlalchemy.orm import Session
from app.models.models import Variedad
from app.services.forecast_service import isocalendar_to_string
from app.services.mva_service import generar_plan_mva
from app.services.ocupacion_service import (
    resolver_bloque_tentativo, 
    calcular_ocupacion_semanal_52w,
    CAMAS_COMERCIALES_TOTALES
)

# Constantes Maestras de Enraizamiento y Propagación
CAVIDADES_POR_BANDEJA = 112             # Bandeja estándar de propagación (112 alvéolos)
DIAS_PERMANENCIA_BANCO = 21            # 3 semanas exactas bajo cámara de nebulización
SEMANAS_ENRAIZAMIENTO = 3              # Desfase temporal hacia atrás: Sem_Siembra - 3

# Jornadas Laborales Estándar (según Módulo de Programación Diaria)
HORAS_JORNADA = {
    "Lunes": 8.0,       # 6:00 am - 2:00 pm (8h)
    "Martes": 8.0,      # 6:00 am - 2:00 pm (8h)
    "Miércoles": 7.5,   # 6:00 am - 1:30 pm (7.5h)
    "Jueves": 8.0,      # 6:00 am - 2:00 pm (8h) - Pico de siembra en campo
    "Viernes": 8.0,     # 6:00 am - 2:00 pm (8h)
    "Sábado": 5.0,      # 6:00 am - 11:00 am (5h)
    "Domingo": 0.0      # 0h estándar (activo sólo en contingencia pico)
}
TOTAL_HORAS_SEMANA_ESTANDAR = sum(HORAS_JORNADA.values()) # 44.5 horas

# Rendimientos Estándar de Mano de Obra (Esquejes / Hora)
RENDIMIENTO_NORMAL = 2016.0         # 18 bandejas/hora (1 cada 3.33 min)
RENDIMIENTO_REFUERZO = 1700.0       # 15.2 bandejas/hora (1 cada 3.95 min)
RENDIMIENTO_APRENDIZAJE = 1000.0    # 8.9 bandejas/hora (1 cada 6.72 min)

def restar_semanas_iso(sem_str: str, n_semanas: int = 3) -> str:
    """Resta n semanas de calendario ISO manejando transiciones de año."""
    s = str(sem_str).strip()
    y = int(s[:4])
    w = int(s[4:])
    dt = date.fromisocalendar(y, w, 1) - timedelta(weeks=n_semanas)
    iso = dt.isocalendar()
    return f"{iso.year}{iso.week:02d}"

def sumar_semanas_iso(sem_str: str, n_semanas: int = 3) -> str:
    """Suma n semanas de calendario ISO manejando transiciones de año."""
    s = str(sem_str).strip()
    y = int(s[:4])
    w = int(s[4:])
    dt = date.fromisocalendar(y, w, 1) + timedelta(weeks=n_semanas)
    iso = dt.isocalendar()
    return f"{iso.year}{iso.week:02d}"

def cargar_temporadas_config() -> list[dict]:
    """Carga las ventanas oficiales de temporada definidas en config_temporadas.json."""
    seasons_file = "config_temporadas.json"
    if os.path.exists(seasons_file):
        try:
            with open(seasons_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return [
        {"Temporada": "Fall", "Semana Inicio": 202632, "Semana Fin": 202646},
        {"Temporada": "Navidad", "Semana Inicio": 202648, "Semana Fin": 202650},
        {"Temporada": "San valentin", "Semana Inicio": 202703, "Semana Fin": 202705},
        {"Temporada": "Madres", "Semana Inicio": 202716, "Semana Fin": 202718},
        {"Temporada": "Summer", "Semana Inicio": 202719, "Semana Fin": 202731}
    ]

def clasificar_temporada_semana(sem_int: int) -> str:
    """Asigna la temporada comercial según las ventanas oficiales de la empresa."""
    seasons = cargar_temporadas_config()
    for s in seasons:
        ini = s.get("Semana Inicio", 0)
        fin = s.get("Semana Fin", 0)
        if ini <= sem_int <= fin:
            return s.get("Temporada", "Regular")
        
        # Validación de módulo 100 por año
        w_ini = ini % 100 if ini > 100 else ini
        w_fin = fin % 100 if fin > 100 else fin
        w_curr = sem_int % 100
        if w_ini <= w_fin and w_ini <= w_curr <= w_fin:
            return s.get("Temporada", "Regular")
        elif w_ini > w_fin and (w_curr >= w_ini or w_curr <= w_fin):
            return s.get("Temporada", "Regular")

    return "Every Day / Regular"

def obtener_semanas_enraizamiento_disponibles(archivo_pedido: str = "PedidoConsolidado_master.xlsx") -> list[dict]:
    """
    Retorna la lista de todas las semanas de enraizamiento disponibles en el Pedido Aprobado,
    con su volumen total, bandejas de 112, número de variedades y temporada objetivo.
    """
    if not os.path.exists(archivo_pedido):
        candidatos = glob.glob("PedidoConsolidado*.xlsx") + glob.glob("*pedido*.xlsx")
        archivo_pedido = candidatos[0] if candidatos else None

    if not archivo_pedido or not os.path.exists(archivo_pedido):
        return []

    try:
        df_mrp = generar_plan_mva(archivo_pedido, week_is="Pedido")
        if df_mrp.empty or 'Semana_Siembra' not in df_mrp.columns:
            return []

        # Agrupar por Semana_Siembra
        grouped = df_mrp.groupby('Semana_Siembra').agg(
            total_esquejes=('Esquejes_Para_Siembra (Final)', 'sum'),
            num_variedades=('Variedad', 'nunique')
        ).reset_index()

        res = []
        for _, row in grouped.iterrows():
            sem_s = str(row['Semana_Siembra'])
            sem_e = restar_semanas_iso(sem_s, SEMANAS_ENRAIZAMIENTO)
            esq = int(round(row['total_esquejes']))
            bandejas = int(math.ceil(esq / CAVIDADES_POR_BANDEJA))
            
            sem_s_int = int(sem_s) if sem_s.isdigit() else 202640
            # Ventana objetivo de floración y cosecha comercial (~11 semanas post-siembra)
            sem_c = sumar_semanas_iso(sem_s, 11)
            sem_c_int = int(sem_c) if sem_c.isdigit() else 202704
            temp = clasificar_temporada_semana(sem_c_int)

            res.append({
                "Semana_Enraizamiento": sem_e,
                "Semana_Enraizamiento_Label": f"S{sem_e[2:]}",
                "Semana_Siembra": sem_s,
                "Semana_Siembra_Label": f"S{sem_s[2:]}",
                "Semana_Cosecha": sem_c,
                "Semana_Cosecha_Label": f"S{sem_c[2:]}",
                "Temporada": temp,
                "Total_Esquejes": esq,
                "Total_Bandejas_112": bandejas,
                "Num_Variedades": int(row['num_variedades'])
            })

        # Ordenar cronológicamente por Semana de Enraizamiento
        res = sorted(res, key=lambda x: x['Semana_Enraizamiento'])
        return res
    except Exception:
        return []

def calcular_dia_tentativo_enraizamiento(dia_pico: int = 0) -> str:
    """
    Calcula el día tentativo de enraizamiento para que el pico de cosecha ocurra los JUEVES.
    Formula adaptada del libro legacy: fecha base jueves - dia_pico modulo 7.
    Si cae en domingo, se traslada a lunes.
    """
    # 8 de enero de 2026 fue Jueves (referencia ISO estándar de la empresa)
    dia_base_jueves = 3  # Lunes=0, Martes=1, Miércoles=2, Jueves=3, Viernes=4, Sábado=5, Domingo=6
    offset = (dia_pico or 0) % 7
    dia_num = (dia_base_jueves - offset) % 7
    dias_nombres = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    dia_nombre = dias_nombres[dia_num]
    if dia_nombre == "Domingo":
        dia_nombre = "Lunes"
    return dia_nombre

def nivelar_distribucion_diaria(lotes: list[dict], horas_jornada: dict = None) -> list[dict]:
    """
    Nivela los lotes de enraizamiento a lo largo de la semana (Lunes a Sábado).
    Si un día está sobrecargado respecto a sus horas disponibles, redistribuye lotes completos
    hacia los días con capacidad disponible, manteniendo la integridad del lote de variedad.
    """
    if not horas_jornada:
        horas_jornada = HORAS_JORNADA.copy()

    total_horas = sum(horas_jornada.values()) or 44.5
    total_esquejes = sum(l['Esquejes'] for l in lotes)
    
    if total_esquejes == 0:
        return lotes

    # Capacidad objetivo en esquejes por día según su jornada laboral
    target_por_dia = {
        d: (h / total_horas) * total_esquejes for d, h in horas_jornada.items() if h > 0
    }
    
    # Capacidad máxima con 20% de tolerancia antes de forzar desborde
    max_por_dia = {d: target_por_dia[d] * 1.20 for d in target_por_dia}
    carga_actual = {d: 0 for d in target_por_dia}

    lotes_ordenados = sorted(lotes, key=lambda x: x['Esquejes'], reverse=True)
    dias_activos = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]

    for lote in lotes_ordenados:
        dia_tentativo = lote.get('Dia_Tentativo', 'Jueves')
        if dia_tentativo not in carga_actual or dia_tentativo == 'Domingo':
            dia_tentativo = 'Jueves'

        # Si cabe dentro del día tentativo sin superar el techo máximo
        if (carga_actual[dia_tentativo] + lote['Esquejes']) <= max_por_dia[dia_tentativo]:
            lote['Dia_Programado'] = dia_tentativo
            carga_actual[dia_tentativo] += lote['Esquejes']
        else:
            # Buscar el día con mayor holgura relativa (Menor % de ocupación vs target)
            dias_candidatos = sorted(
                dias_activos,
                key=lambda d: (carga_actual[d] / target_por_dia[d]) if target_por_dia[d] > 0 else 999
            )
            dia_elegido = dias_candidatos[0]
            lote['Dia_Programado'] = dia_elegido
            carga_actual[dia_elegido] += lote['Esquejes']

        lote['Es_Nivelado'] = (lote['Dia_Programado'] != lote['Dia_Tentativo'])

    return lotes

def calcular_mano_obra_enraizamiento(esquejes_por_dia: dict, config_cuadrilla: dict = None) -> dict:
    """
    Calcula las horas-hombre y operarios requeridos por día y por semana,
    según la composición de la cuadrilla y sus rendimientos estándar.
    """
    if not config_cuadrilla:
        config_cuadrilla = {
            "num_normal": 6,
            "num_refuerzo": 0,
            "num_aprendizaje": 0,
            "rend_normal": RENDIMIENTO_NORMAL,
            "rend_refuerzo": RENDIMIENTO_REFUERZO,
            "rend_aprendizaje": RENDIMIENTO_APRENDIZAJE
        }

    n_norm = int(config_cuadrilla.get("num_normal", 6))
    n_ref = int(config_cuadrilla.get("num_refuerzo", 0))
    n_apr = int(config_cuadrilla.get("num_aprendizaje", 0))
    total_operarios_fijos = n_norm + n_ref + n_apr

    r_norm = float(config_cuadrilla.get("rend_normal", RENDIMIENTO_NORMAL))
    r_ref = float(config_cuadrilla.get("rend_refuerzo", RENDIMIENTO_REFUERZO))
    r_apr = float(config_cuadrilla.get("rend_aprendizaje", RENDIMIENTO_APRENDIZAJE))

    if total_operarios_fijos > 0:
        rendimiento_ponderado = (
            (n_norm * r_norm) + (n_ref * r_ref) + (n_apr * r_apr)
        ) / total_operarios_fijos
    else:
        rendimiento_ponderado = r_norm

    horas_requeridas_por_dia = {}
    operarios_requeridos_por_dia = {}
    balance_operarios_por_dia = {}
    bandejas_por_dia = {}
    estados_por_dia = {}

    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]

    for d in dias:
        esq_d = esquejes_por_dia.get(d, 0)
        h_jornada = HORAS_JORNADA.get(d, 8.0)
        bandejas_por_dia[d] = int(math.ceil(esq_d / CAVIDADES_POR_BANDEJA))

        h_req = round(esq_d / rendimiento_ponderado, 2) if rendimiento_ponderado > 0 else 0.0
        horas_requeridas_por_dia[d] = h_req

        # Operarios requeridos para cumplir la meta en la jornada legal del día
        op_req = round(h_req / h_jornada, 1) if h_jornada > 0 else 0.0
        operarios_requeridos_por_dia[d] = op_req

        # Balance vs cuadrilla disponible
        balance = round(total_operarios_fijos - op_req, 1)
        balance_operarios_por_dia[d] = balance

        if op_req == 0:
            estados_por_dia[d] = "⚪ SIN CLAVADO"
        elif balance >= 0:
            estados_por_dia[d] = "🟢 CAPACIDAD CUBIERTA"
        elif balance >= -1.0:
            estados_por_dia[d] = "🟡 AJUSTADO (Posible H. Extra)"
        else:
            estados_por_dia[d] = f"🔴 SOBRECARGA (+{abs(balance):.0f} refuerzos necesarios)"

    total_esquejes_sem = sum(esquejes_por_dia.get(d, 0) for d in dias)
    total_horas_req_sem = sum(horas_requeridas_por_dia.values())
    total_bandejas_sem = sum(bandejas_por_dia.values())
    prom_operarios_req = (
        round(total_horas_req_sem / TOTAL_HORAS_SEMANA_ESTANDAR, 1)
        if TOTAL_HORAS_SEMANA_ESTANDAR > 0 else 0.0
    )

    return {
        "rendimiento_ponderado": round(rendimiento_ponderado, 1),
        "total_operarios_fijos": total_operarios_fijos,
        "total_esquejes": total_esquejes_sem,
        "total_bandejas": total_bandejas_sem,
        "total_horas_requeridas": round(total_horas_req_sem, 1),
        "promedio_operarios_requeridos": prom_operarios_req,
        "balance_semanal_operarios": round(total_operarios_fijos - prom_operarios_req, 1),
        "horas_requeridas_por_dia": horas_requeridas_por_dia,
        "operarios_requeridos_por_dia": operarios_requeridos_por_dia,
        "balance_operarios_por_dia": balance_operarios_por_dia,
        "bandejas_por_dia": bandejas_por_dia,
        "estados_por_dia": estados_por_dia
    }

def generar_plano_enraizamiento_semanal(
    db: Session, 
    semana_enraizamiento: str, 
    archivo_pedido: str = "PedidoConsolidado_master.xlsx",
    config_cuadrilla: dict = None
) -> dict:
    """
    Genera el Plano Operativo de Enraizamiento para la semana especificada:
    - Cruza el Pedido Aprobado (+3 semanas para siembra en campo).
    - Desagrega por Variedad, Color, Flor y Bandejas de 112 cavidades.
    - Asigna día tentativo (pico jueves) y nivela la jornada semanal (Lunes a Sábado).
    - Asigna bloque de campo estimado de destino (01 a 06).
    - Modela el cálculo de mano de obra y horas-hombre requeridas.
    """
    if not os.path.exists(archivo_pedido):
        candidatos = glob.glob("PedidoConsolidado*.xlsx") + glob.glob("*pedido*.xlsx")
        archivo_pedido = candidatos[0] if candidatos else None

    if not archivo_pedido or not os.path.exists(archivo_pedido):
        return {"error": "Archivo de Pedido Consolidado no encontrado."}

    sem_siembra = sumar_semanas_iso(semana_enraizamiento, SEMANAS_ENRAIZAMIENTO)
    df_mrp = generar_plan_mva(archivo_pedido, week_is="Pedido")
    
    if df_mrp.empty or 'Semana_Siembra' not in df_mrp.columns:
        return {"error": "El pedido no contiene órdenes de siembra válidas."}

    df_sem = df_mrp[df_mrp['Semana_Siembra'] == str(sem_siembra)].copy()
    if df_sem.empty:
        return {
            "error": f"No hay órdenes de siembra para la semana {sem_siembra} (Enraizamiento: {semana_enraizamiento}).",
            "semana_enraizamiento": semana_enraizamiento,
            "semana_siembra": sem_siembra
        }

    # Cargar catálogo de variedades desde la base de datos
    variedades_db = {v.nombre.lower().strip(): v for v in db.query(Variedad).all()}
    
    # Cargar proyección de bloques para asignación espacial tentativa
    try:
        _, df_bloques_52w = calcular_ocupacion_semanal_52w(db)
    except Exception:
        df_bloques_52w = pd.DataFrame()

    lotes_raw = []
    sem_s_int = int(sem_siembra) if sem_siembra.isdigit() else 202640
    # Cosecha comercial estimada (~11 semanas post-siembra)
    sem_c_global = sumar_semanas_iso(sem_siembra, 11)
    temporada_cosecha = clasificar_temporada_semana(int(sem_c_global) if sem_c_global.isdigit() else 202704)

    for _, row in df_sem.iterrows():
        v_nom = str(row['Variedad']).strip()
        v_obj = variedades_db.get(v_nom.lower())
        
        flor = row.get('Flor') or (v_obj.flor if v_obj else 'Desconocida')
        color = row.get('Color') or (v_obj.color if v_obj else 'N/A')
        esq = int(round(row['Esquejes_Para_Siembra (Final)']))
        
        dia_inicio = v_obj.dia_inicio if (v_obj and v_obj.dia_inicio) else 84
        dia_pico = v_obj.dia_pico if (v_obj and v_obj.dia_pico) else 14
        aprov_pp = v_obj.aprov_pp if (v_obj and v_obj.aprov_pp and v_obj.aprov_pp > 0) else 0.95

        # Día tentativo fenológico (Pico Jueves)
        dia_tentativo = calcular_dia_tentativo_enraizamiento(dia_pico)
        
        # Bandejas estándar 112 cavidades
        bandejas = int(math.ceil(esq / CAVIDADES_POR_BANDEJA))

        # Camas de campo equivalentes (a ~5,000 plantas/cama real)
        camas_campo = round(esq / 5000.0, 1)

        # Proyección de tallos esperados a cosecha
        tallos_esperados = int(round(esq * aprov_pp))

        # Bloque de destino tentativo en campo
        bloque_dest_res = resolver_bloque_tentativo(sem_siembra, df_bloques_52w=df_bloques_52w)
        if isinstance(bloque_dest_res, tuple):
            b_code = str(bloque_dest_res[0])
        else:
            b_code = str(bloque_dest_res)
        bloque_dest = f"Bloque {b_code}" if not b_code.startswith("Bloque") else b_code

        # Cálculo de semana estimada de cosecha por fenología de la variedad
        dias_a_cosecha = dia_pico if dia_pico > 30 else 77
        sem_cosecha_var = sumar_semanas_iso(sem_siembra, int(round(dias_a_cosecha / 7.0)))
        temp_cosecha_var = clasificar_temporada_semana(int(sem_cosecha_var) if sem_cosecha_var.isdigit() else 202704)

        lotes_raw.append({
            "Flor": flor,
            "Color": color,
            "Variedad": v_nom,
            "Esquejes": esq,
            "Bandejas_112": bandejas,
            "Camas_Campo": camas_campo,
            "Bloque_Destino": bloque_dest,
            "Dia_Tentativo": dia_tentativo,
            "Dia_Inicio": dia_inicio,
            "Dia_Pico": dia_pico,
            "Aprov_PP": aprov_pp,
            "Tallos_Esperados": tallos_esperados,
            "Semana_Siembra": sem_siembra,
            "Semana_Enraizamiento": semana_enraizamiento,
            "Semana_Cosecha": sem_cosecha_var,
            "Temporada": temp_cosecha_var
        })

    # Nivelar distribución a lo largo de la semana (Lunes a Sábado)
    lotes_nivelados = nivelar_distribucion_diaria(lotes_raw)

    # Agrupar esquejes por día definitivo de programación
    dias_orden = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
    esquejes_por_dia = {d: 0 for d in dias_orden}
    for l in lotes_nivelados:
        d_prog = l.get('Dia_Programado', 'Jueves')
        if d_prog in esquejes_por_dia:
            esquejes_por_dia[d_prog] += l['Esquejes']

    # Cálculo de Mano de Obra
    res_mano_obra = calcular_mano_obra_enraizamiento(esquejes_por_dia, config_cuadrilla=config_cuadrilla)

    # Construir DataFrame de Resumen Diario
    resumen_diario_rows = []
    tot_esq_sem = res_mano_obra['total_esquejes']
    
    for d in dias_orden:
        esq_d = esquejes_por_dia[d]
        pct_sem = (esq_d / tot_esq_sem * 100.0) if tot_esq_sem > 0 else 0.0
        resumen_diario_rows.append({
            "Día": d,
            "Jornada (Horas)": HORAS_JORNADA.get(d, 8.0),
            "Esquejes": esq_d,
            "Bandejas (112)": res_mano_obra['bandejas_por_dia'][d],
            "% Semana": round(pct_sem, 1),
            "Horas Requeridas": res_mano_obra['horas_requeridas_por_dia'][d],
            "Operarios Requeridos": res_mano_obra['operarios_requeridos_por_dia'][d],
            "Operarios Asignados": res_mano_obra['total_operarios_fijos'],
            "Balance Operarios": res_mano_obra['balance_operarios_por_dia'][d],
            "Estado": res_mano_obra['estados_por_dia'][d]
        })
    df_resumen_diario = pd.DataFrame(resumen_diario_rows)

    # Ordenar lotes detallados por Día de Programación y luego por Variedad
    dia_order_map = {d: i for i, d in enumerate(dias_orden)}
    lotes_nivelados = sorted(
        lotes_nivelados, 
        key=lambda x: (dia_order_map.get(x['Dia_Programado'], 9), x['Flor'], x['Variedad'])
    )
    df_plano_detallado = pd.DataFrame(lotes_nivelados)

    return {
        "semana_enraizamiento": semana_enraizamiento,
        "semana_enraizamiento_label": f"S{semana_enraizamiento[2:]}",
        "semana_siembra": sem_siembra,
        "semana_siembra_label": f"S{sem_siembra[2:]}",
        "semana_cosecha": sem_c_global,
        "semana_cosecha_label": f"S{sem_c_global[2:]}",
        "temporada": temporada_cosecha,
        "df_plano_detallado": df_plano_detallado,
        "df_resumen_diario": df_resumen_diario,
        "resumen_mano_obra": res_mano_obra,
        "kpis": {
            "total_esquejes": tot_esq_sem,
            "total_bandejas": res_mano_obra['total_bandejas'],
            "num_lotes": len(lotes_nivelados),
            "horas_requeridas": res_mano_obra['total_horas_requeridas'],
            "operarios_promedio": res_mano_obra['promedio_operarios_requeridos'],
            "rendimiento_ponderado": res_mano_obra['rendimiento_ponderado'],
            "tallos_esperados": sum(l['Tallos_Esperados'] for l in lotes_nivelados)
        }
    }

def generar_pdf_plano_enraizamiento(res_plano: dict) -> bytes:
    """
    Genera un documento PDF profesional en orientación Horizontal (Landscape)
    con el Plano Operativo de Enraizamiento para entrega directa al proceso.
    """
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    import io

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=25,
        rightMargin=25,
        topMargin=25,
        bottomMargin=25
    )

    styles = getSampleStyleSheet()
    
    # Estilos Tipográficos Personalizados
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=18,
        textColor=colors.HexColor('#1b5e20')
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#333333')
    )

    meta_style = ParagraphStyle(
        'MetaStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#222222')
    )

    table_header_style = ParagraphStyle(
        'THeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9,
        textColor=colors.white,
        alignment=1
    )

    table_cell_style = ParagraphStyle(
        'TCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.0,
        leading=8.5,
        textColor=colors.HexColor('#222222')
    )

    table_cell_center = ParagraphStyle(
        'TCellCenter',
        parent=table_cell_style,
        alignment=1
    )

    elements = []

    sem_e = res_plano.get("semana_enraizamiento_label", "S2643")
    sem_s = res_plano.get("semana_siembra_label", "S2646")
    temp = res_plano.get("temporada", "San Valentín 2027")
    kpis = res_plano.get("kpis", {})

    # 1. Encabezado Institucional
    header_data = [
        [
            Paragraph("<b>JARDINES DE CHÍA S.A.S. — PLANO OPERATIVO DE ENRAIZAMIENTO</b>", title_style),
            Paragraph(f"<b>EMISIÓN S&OP</b><br/>Fecha: {date.today().strftime('%d/%m/%Y')}", subtitle_style)
        ],
        [
            Paragraph(
                f"<b>Semana Enraizamiento:</b> {sem_e} &nbsp;|&nbsp; "
                f"<b>Semana Siembra Campo (+3 sem):</b> {sem_s} &nbsp;|&nbsp; "
                f"<b>Cosecha Estimada (+11 sem):</b> {res_plano.get('semana_cosecha_label', 'S2704')} &nbsp;|&nbsp; "
                f"<b>Temporada Objetivo:</b> {temp}",
                meta_style
            ),
            Paragraph(
                f"<b>Total Esquejes:</b> {kpis.get('total_esquejes', 0):,d} &nbsp;|&nbsp; "
                f"<b>Bandejas (112):</b> {kpis.get('total_bandejas', 0):,d}",
                meta_style
            )
        ]
    ]
    t_header = Table(header_data, colWidths=[480, 240])
    t_header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(t_header)
    elements.append(Spacer(1, 8))

    # 2. Resumen Ejecutivo de Mano de Obra y Jornadas
    df_res_dia = res_plano.get("df_resumen_diario", pd.DataFrame())
    if not df_res_dia.empty:
        summary_headers = ["Día", "Jornada", "Esquejes", "Bandejas (112)", "% Sem.", "Horas Req.", "Op. Req.", "Op. Asignados", "Estado Capacidad"]
        summary_data = [[Paragraph(f"<b>{h}</b>", table_header_style) for h in summary_headers]]
        
        for _, r in df_res_dia.iterrows():
            summary_data.append([
                Paragraph(str(r['Día']), table_cell_style),
                Paragraph(f"{r['Jornada (Horas)']:.1f}h", table_cell_center),
                Paragraph(f"{r['Esquejes']:,d}", table_cell_center),
                Paragraph(f"{r['Bandejas (112)']:,d}", table_cell_center),
                Paragraph(f"{r['% Semana']:.1f}%", table_cell_center),
                Paragraph(f"{r['Horas Requeridas']:.1f}h", table_cell_center),
                Paragraph(f"{r['Operarios Requeridos']:.1f}", table_cell_center),
                Paragraph(f"{r['Operarios Asignados']}", table_cell_center),
                Paragraph(str(r['Estado']), table_cell_style),
            ])

        t_summary = Table(summary_data, colWidths=[65, 55, 75, 75, 50, 65, 65, 75, 195])
        t_summary.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2e7d32')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#b0bec5')),
            ('TOPPADDING', (0, 0), (-1, -1), 2.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f1f8e9')]),
        ]))
        elements.append(t_summary)
        elements.append(Spacer(1, 10))

    # 3. Plano Detallado de Enraizamiento (Hoja de Ruta Operativa)
    df_det = res_plano.get("df_plano_detallado", pd.DataFrame())
    if not df_det.empty:
        table_cols = [
            "Día Prog.", "Flor", "Color", "Variedad", 
            "Esquejes", "Bandejas (112)", "Bloque Campo", 
            "Sem. Siembra", "Pico Cosecha", "Ejecutado Real", "Firma / Obs."
        ]
        det_data = [[Paragraph(f"<b>{c}</b>", table_header_style) for c in table_cols]]

        for _, r in df_det.iterrows():
            dia_txt = str(r['Dia_Programado'])
            if r.get('Es_Nivelado', False):
                dia_txt += " *"

            d_pico = int(r.get('Dia_Pico', 14))
            pico_txt = f"+{d_pico}d"

            det_data.append([
                Paragraph(dia_txt, table_cell_style),
                Paragraph(str(r['Flor']), table_cell_style),
                Paragraph(str(r['Color']), table_cell_style),
                Paragraph(f"<b>{r['Variedad']}</b>", table_cell_style),
                Paragraph(f"{r['Esquejes']:,d}", table_cell_center),
                Paragraph(f"{r['Bandejas_112']:,d}", table_cell_center),
                Paragraph(str(r.get('Bloque_Destino', 'Bloque 01')), table_cell_center),
                Paragraph(f"S{str(r['Semana_Siembra'])[2:]}", table_cell_center),
                Paragraph(pico_txt, table_cell_center),
                Paragraph("[ &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; ]", table_cell_center),
                Paragraph("___________________", table_cell_center),
            ])

        t_det = Table(det_data, colWidths=[65, 55, 55, 110, 65, 65, 75, 60, 50, 60, 60], repeatRows=1)
        t_det.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1b5e20')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cfd8dc')),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fbe7')]),
        ]))
        elements.append(t_det)
        elements.append(Spacer(1, 10))

    # 4. Pie de Control y Firmas de Aprobación
    signatures_data = [
        [
            Paragraph("<b>Elaboró (Planeación S&OP):</b><br/><br/>__________________________________<br/>Firma y Fecha", meta_style),
            Paragraph("<b>Recibió (Líder Propagación):</b><br/><br/>__________________________________<br/>Firma y Fecha", meta_style),
            Paragraph("<b>Validó (Jefatura de Producción):</b><br/><br/>__________________________________<br/>Firma y Fecha", meta_style)
        ]
    ]
    t_sig = Table(signatures_data, colWidths=[240, 240, 240])
    t_sig.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(KeepTogether([t_sig]))

    doc.build(elements)
    return buffer.getvalue()
