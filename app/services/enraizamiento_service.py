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
    Diseñado para consolidarse en UNA SOLA HOJA:
    - Resumen de mano de obra consolidado por semana (no desglosado por día).
    - Columnas depuradas (sin 'Pico Cosecha' ni 'Firma / Obs.').
    - Casilla de verificación '[    ]' para control de ejecución real.
    """
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    import io

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=20,
        rightMargin=20,
        topMargin=15,
        bottomMargin=15
    )

    styles = getSampleStyleSheet()
    
    # Estilos Tipográficos Optimizados para 1 Página
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=12.5,
        textColor=colors.HexColor('#1b5e20')
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor('#333333'),
        alignment=2
    )

    meta_style = ParagraphStyle(
        'MetaStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.2,
        leading=9.0,
        textColor=colors.HexColor('#222222')
    )

    meta_style_right = ParagraphStyle(
        'MetaStyleRight',
        parent=meta_style,
        alignment=2
    )

    th_style = ParagraphStyle(
        'THeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=6.8,
        leading=8.2,
        textColor=colors.white,
        alignment=1
    )

    # Ajuste dinámico de escala según la cantidad de lotes para garantizar 1 página
    n_rows = len(res_plano.get('df_plano_detallado', []))
    fs = 6.0 if n_rows > 26 else 6.8
    ld = 7.2 if n_rows > 26 else 8.2
    pad = 0.8 if n_rows > 26 else 1.3

    tc_style = ParagraphStyle(
        'TCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=fs,
        leading=ld,
        textColor=colors.HexColor('#222222')
    )

    tc_bold = ParagraphStyle(
        'TCellBold',
        parent=tc_style,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#111111')
    )

    tc_center = ParagraphStyle(
        'TCellCenter',
        parent=tc_style,
        alignment=1
    )

    tc_center_bold = ParagraphStyle(
        'TCellCenterBold',
        parent=tc_bold,
        alignment=1
    )

    elements = []

    sem_e = res_plano.get("semana_enraizamiento_label", "S2643")
    sem_s = res_plano.get("semana_siembra_label", "S2646")
    sem_c = res_plano.get("semana_cosecha_label", "S2704")
    temp = res_plano.get("temporada", "San Valentín")
    kpis = res_plano.get("kpis", {})
    mano = res_plano.get("resumen_mano_obra", {})
    tot_esq = kpis.get("total_esquejes", 0)
    tot_band = kpis.get("total_bandejas", 0)
    today_str = date.today().strftime('%d/%m/%Y')

    # 1. Encabezado Institucional Compacto
    header_data = [
        [
            Paragraph("<b>JARDINES DE CHÍA S.A.S. — PLANO OPERATIVO DE ENRAIZAMIENTO</b>", title_style),
            Paragraph(f"<b>EMISIÓN S&OP</b> | Fecha: {today_str}", subtitle_style)
        ],
        [
            Paragraph(
                f"<b>Semana Enraizamiento:</b> {sem_e} &nbsp;|&nbsp; "
                f"<b>Siembra (+3 sem):</b> {sem_s} &nbsp;|&nbsp; "
                f"<b>Cosecha (+11 sem):</b> {sem_c} &nbsp;|&nbsp; "
                f"<b>Temporada:</b> {temp}",
                meta_style
            ),
            Paragraph(
                f"<b>Total Esquejes:</b> {tot_esq:,d} &nbsp;|&nbsp; "
                f"<b>Bandejas (112):</b> {tot_band:,d}",
                meta_style_right
            )
        ]
    ]
    t_header = Table(header_data, colWidths=[520, 232])
    t_header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
    ]))
    elements.append(t_header)
    elements.append(Spacer(1, 3))

    # 2. Resumen de Mano de Obra Consolidado por SEMANA (sin desglose diario)
    bal = mano.get("balance_semanal_operarios", 0)
    estado_sem = "🟢 CUBIERTA" if bal >= 0 else ("🟡 AJUSTADA" if bal >= -1.0 else f"🔴 SOBRECARGA (+{abs(bal):.0f} ref.)")
    labor_headers = [
        "Semana", "Jornada Legal", "Total Esquejes", "Bandejas 112", 
        "Rend. Ponderado", "Horas Req.", "Op. Req.", "Op. Asignados", "Balance Semanal", "Estado Capacidad"
    ]
    labor_data = [
        [Paragraph(f"<b>{h}</b>", th_style) for h in labor_headers],
        [
            Paragraph(sem_e, tc_center),
            Paragraph("44.5 h", tc_center),
            Paragraph(f"{tot_esq:,d}", tc_center),
            Paragraph(f"{tot_band:,d}", tc_center),
            Paragraph(f"{kpis.get('rendimiento_ponderado', 2016):,.0f} esq/h", tc_center),
            Paragraph(f"{kpis.get('horas_requeridas', 0):.1f} h", tc_center),
            Paragraph(f"{kpis.get('operarios_promedio', 0):.1f}", tc_center),
            Paragraph(f"{mano.get('total_operarios_fijos', 6)}", tc_center),
            Paragraph(f"{bal:+.1f} op.", tc_center),
            Paragraph(estado_sem, tc_center),
        ]
    ]
    t_labor = Table(labor_data, colWidths=[55, 60, 75, 70, 85, 65, 65, 70, 70, 137])
    t_labor.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2e7d32')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#b0bec5')),
        ('TOPPADDING', (0, 0), (-1, -1), 1.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f1f8e9')),
    ]))
    elements.append(t_labor)
    elements.append(Spacer(1, 3))

    # 3. Plano Detallado de Enraizamiento (Depurado: Sin Pico Cosecha ni Firma/Obs)
    df_det = res_plano.get("df_plano_detallado", pd.DataFrame())
    if not df_det.empty:
        det_cols = [
            "Día Prog.", "Flor", "Color", "Variedad", 
            "Esquejes", "Bandejas (112)", "Bloque Campo", 
            "Sem. Siembra", "Ejecutado Real"
        ]
        table_data = [[Paragraph(f"<b>{c}</b>", th_style) for c in det_cols]]

        for _, r in df_det.iterrows():
            dia_txt = str(r['Dia_Programado'])
            if r.get('Es_Nivelado', False):
                dia_txt += " *"

            table_data.append([
                Paragraph(dia_txt, tc_style),
                Paragraph(str(r['Flor']), tc_style),
                Paragraph(str(r['Color']), tc_style),
                Paragraph(f"<b>{r['Variedad']}</b>", tc_bold),
                Paragraph(f"{r['Esquejes']:,d}", tc_center),
                Paragraph(f"{r['Bandejas_112']:,d}", tc_center),
                Paragraph(str(r.get('Bloque_Destino', 'Bloque 01')), tc_center),
                Paragraph(f"S{str(r['Semana_Siembra'])[2:]}", tc_center),
                Paragraph("[ &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; ]", tc_center),
            ])

        # Fila de Totales
        tot_esq_det = int(df_det['Esquejes'].sum())
        tot_ban_det = int(df_det['Bandejas_112'].sum())
        table_data.append([
            Paragraph("<b>TOTAL GENERAL</b>", tc_bold),
            Paragraph("-", tc_center),
            Paragraph("-", tc_center),
            Paragraph(f"<b>{len(df_det)} Variedades</b>", tc_bold),
            Paragraph(f"<b>{tot_esq_det:,d}</b>", tc_center_bold),
            Paragraph(f"<b>{tot_ban_det:,d}</b>", tc_center_bold),
            Paragraph("-", tc_center),
            Paragraph("-", tc_center),
            Paragraph("[ &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; ]", tc_center),
        ])

        t_det = Table(table_data, colWidths=[65, 60, 60, 195, 70, 75, 75, 72, 80], repeatRows=1)
        t_det.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1b5e20')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cfd8dc')),
            ('TOPPADDING', (0, 0), (-1, -1), pad),
            ('BOTTOMPADDING', (0, 0), (-1, -1), pad),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f9fbe7')]),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8f5e9')),
            ('LINEABOVE', (0, -1), (-1, -1), 1.0, colors.HexColor('#1b5e20')),
        ]))
        elements.append(t_det)
        elements.append(Spacer(1, 3))

    # 4. Pie de Control y Firmas de Aprobación Compacto
    sig_data = [
        [
            Paragraph("<b>Elaboró (Planeación S&OP):</b> ______________________ Firma", meta_style),
            Paragraph("<b>Recibió (Líder Propagación):</b> ______________________ Firma", meta_style),
            Paragraph("<b>Validó (Jefatura Producción):</b> ______________________ Firma", meta_style),
        ]
    ]
    t_sig = Table(sig_data, colWidths=[250, 250, 252])
    t_sig.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
    ]))
    elements.append(t_sig)

    doc.build(elements)
    return buffer.getvalue()
