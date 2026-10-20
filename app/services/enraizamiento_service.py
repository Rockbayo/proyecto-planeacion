import os
import glob
import json
import math
from datetime import date, timedelta
import pandas as pd
from sqlalchemy.orm import Session
from app.models.models import Variedad, Siembra, EstadoSiembra
from app.services.forecast_service import isocalendar_to_string, calcular_curvas_dinamicas
from app.services.mva_service import (
    generar_plan_mva,
    sincronizar_plan_detallado_desde_pedido_master
)
from app.services.ocupacion_service import (
    resolver_bloque_tentativo, 
    calcular_ocupacion_semanal_52w,
    consultar_camas_disponibles_campo,
    CAMAS_COMERCIALES_TOTALES,
    CAMAS_COMERCIALES_REDUCIDAS,
    SEMANA_CORTE_REDUCCION_AREA,
    obtener_dimensiones_camas_bloques
)

def asegurar_sincronizacion_pedido_y_plan_detallado(db: Session = None, archivo_pedido: str = "PedidoConsolidado_master.xlsx") -> None:
    """
    Verifica si el archivo maestro de pedidos ha sido actualizado o si el plan detallado no existe,
    y ejecuta la sincronización automática de tallos y esquejes sin cifras estáticas.
    """
    detailed_file = "Plan_Aprobado_Detallado.csv"
    if archivo_pedido and os.path.exists(archivo_pedido):
        necesita_sync = False
        if not os.path.exists(detailed_file):
            necesita_sync = True
        else:
            try:
                if os.path.getmtime(archivo_pedido) > os.path.getmtime(detailed_file):
                    necesita_sync = True
            except Exception:
                necesita_sync = True
                
        if necesita_sync:
            try:
                sincronizar_plan_detallado_desde_pedido_master(
                    master_filepath=archivo_pedido,
                    detailed_filepath=detailed_file,
                    db=db
                )
            except Exception:
                pass


# Constantes Maestras de Enraizamiento y Propagación
CAVIDADES_POR_BANDEJA = 112             # Bandeja estándar de propagación (112 alvéolos)
DIAS_PERMANENCIA_BANCO = 21            # 3 semanas exactas bajo cámara de nebulización
SEMANAS_ENRAIZAMIENTO = 3              # Desfase temporal hacia atrás: Sem_Siembra - 3
ARCHIVO_INVENTARIO_RECEPCION = "Recepcion_Inventario_Esquejes.csv"
ARCHIVO_INVENTARIO_LUNES = "Inventario_Esquejes_Lunes.csv"
ARCHIVO_EJECUCION_REAL = "Ejecucion_Real_Enraizamiento.csv"
ARCHIVO_CIERRE_ENRAIZAMIENTO = "Cierre_Semanal_Enraizamiento.csv"

def calcular_bandejas_redondeadas(esquejes: float) -> int:
    """
    Calcula el número de bandejas de 112 cavidades redondeando al entero más cercano (round).
    Ejemplo de negocio: 46.4 bandejas -> 46 bandejas (no 47).
    Si esquejes <= 0, retorna 0. Si esquejes > 0, garantiza al menos 1 bandeja.
    """
    if not esquejes or float(esquejes) <= 0:
        return 0
    return max(1, int(round(float(esquejes) / CAVIDADES_POR_BANDEJA)))

# Jornadas Laborales Efectivas (con deducción de 30 min de almuerzo Lunes a Viernes)
HORAS_JORNADA = {
    "Lunes": 7.5,       # 6:00 am - 2:00 pm (8.0h brutas - 0.5h almuerzo = 7.5h)
    "Martes": 7.5,      # 6:00 am - 2:00 pm (8.0h brutas - 0.5h almuerzo = 7.5h)
    "Miércoles": 7.0,   # 6:00 am - 1:30 pm (7.5h brutas - 0.5h almuerzo = 7.0h)
    "Jueves": 7.5,      # 6:00 am - 2:00 pm (8.0h brutas - 0.5h almuerzo = 7.5h) - Clavado clave
    "Viernes": 7.5,     # 6:00 am - 2:00 pm (8.0h brutas - 0.5h almuerzo = 7.5h)
    "Sábado": 5.0,      # 6:00 am - 11:00 am (5.0h sin almuerzo = 5.0h)
    "Domingo": 0.0      # 0h estándar (descanso protegido)
}
TOTAL_HORAS_SEMANA_ESTANDAR = sum(HORAS_JORNADA.values()) # 42.0 horas efectivas

# Jornada en Temporada Pico (Domingo activo)
HORAS_JORNADA_TEMPORADA = {
    "Lunes": 7.5,
    "Martes": 7.5,
    "Miércoles": 7.0,
    "Jueves": 7.5,
    "Viernes": 7.5,
    "Sábado": 5.0,
    "Domingo": 5.0      # 5.0h activas en temporadas pico (San Valentín / Madres)
}
TOTAL_HORAS_SEMANA_TEMPORADA = sum(HORAS_JORNADA_TEMPORADA.values()) # 47.0 horas efectivas

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

def aplicar_corrimiento_fenologico_a_plan(df_det: pd.DataFrame, db: Session = None) -> pd.DataFrame:
    """
    Enriquece el plan aprobado con parámetros fenológicos y biológicos dinámicos:
    - Semana_Enraizamiento = restar_semanas_iso(Semana_Siembra, 3).
    - Semana_Pedido_MV = restar_semanas_iso(Semana_Siembra, 4).
    - Asigna dia_pico, dia_inicio y aprovechamiento biológico individual por variedad.
    - Semana_Cosecha biológica real = sumar_semanas_iso(Semana_Siembra, round(dia_pico / 7.0)).
    - Asigna el día tentativo de clavado (Lunes a Sábado) para que el pico de corte coincida
      con el JUEVES de la semana de cosecha objetivo (calcular_dia_tentativo_enraizamiento).
    - Proyecta los tallos comerciales esperados según el aprovechamiento biológico de cada variedad.
    """
    if df_det.empty:
        return df_det

    vars_db = {}
    curvas_dyn = {}
    if db is not None:
        try:
            vars_db = {v.nombre.strip().lower(): v for v in db.query(Variedad).all()}
            curvas_dyn = calcular_curvas_dinamicas(db=db)
        except Exception:
            pass

    records = []
    for _, r in df_det.iterrows():
        v_name = str(r['Variedad']).strip()
        v_norm = v_name.lower()
        esq = int(r['Esquejes'])
        sem_s_orig = int(r['Semana_Siembra'])
        sem_s = str(sem_s_orig)
        sem_e = restar_semanas_iso(sem_s, SEMANAS_ENRAIZAMIENTO)
        sem_p = restar_semanas_iso(sem_s, 4)

        dp = 77
        aprov = 0.806
        dia_ini = 70
        if v_name in curvas_dyn:
            dp = int(curvas_dyn[v_name].get('dia_pico', 77))
            aprov = float(curvas_dyn[v_name].get('aprov', 0.806))
            dia_ini = int(curvas_dyn[v_name].get('dia_inicio', 70))
        elif v_norm in vars_db:
            vo = vars_db[v_norm]
            dp = int(vo.dia_pico) if vo.dia_pico else 77
            aprov = float(vo.aprov_pp) if vo.aprov_pp else 0.806
            dia_ini = int(vo.dia_inicio) if vo.dia_inicio else 70

        # Semana de cosecha biológica esperada
        sem_c = sumar_semanas_iso(sem_s, int(round(dp / 7.0)))

        camas = round(esq / 5200.0, 1)
        bandejas = calcular_bandejas_redondeadas(esq)
        tallos_esp = int(round(esq * aprov))
        dia_tentativo = calcular_dia_tentativo_enraizamiento(dp)

        records.append({
            "Flor": r.get('Flor', 'Standard'),
            "Color": r.get('Color', 'Mix'),
            "Variedad": v_name,
            "Esquejes": esq,
            "Camas": camas,
            "Bandejas_112": bandejas,
            "Dia_Inicio": dia_ini,
            "Dia_Pico": dp,
            "Dia_Tentativo": dia_tentativo,
            "Aprov_PP": aprov,
            "Tallos_Esperados": tallos_esp,
            "Semana_Siembra_Original": sem_s_orig,
            "Semana_Siembra": sem_s,
            "Semana_Enraizamiento": sem_e,
            "Semana_Pedido_MV": sem_p,
            "Semana_Cosecha": sem_c,
            "Es_Corrimiento": False
        })

    return pd.DataFrame(records)

def obtener_semanas_enraizamiento_disponibles(
    archivo_pedido: str = "PedidoConsolidado_master.xlsx",
    modo_plan: str = "aprobado",
    factor_expansion: float = 1.0,
    correr_variedades: bool = True,
    db: Session = None
) -> list[dict]:
    """
    Retorna la lista de todas las semanas de enraizamiento disponibles en el Pedido Aprobado,
    con su volumen total de esquejes, tallos esperados a cosecha, bandejas de 112, número de variedades y temporada objetivo.
    Soporta los modos:
    - 'aprobado': Lee desde Plan_Aprobado_Detallado.csv sincronizado con PedidoConsolidado_master.xlsx.
      Si correr_variedades=True, aplica corrimiento biológico dinámico según dia_pico de cada variedad.
    - 'plataforma_base': Lee desde PedidoConsolidado_master.xlsx (plan base histórico sin curvas dinámicas).
    """
    asegurar_sincronizacion_pedido_y_plan_detallado(db=db, archivo_pedido=archivo_pedido)

    if modo_plan in ["aprobado", "max_capacidad"] and os.path.exists("Plan_Aprobado_Detallado.csv"):
        try:
            df_det = pd.read_csv("Plan_Aprobado_Detallado.csv")
            
            if correr_variedades:
                df_det = aplicar_corrimiento_fenologico_a_plan(df_det, db=db)
                grouped = df_det.groupby('Semana_Enraizamiento').agg(
                    total_esquejes=('Esquejes', 'sum'),
                    total_tallos=('Tallos_Esperados', 'sum') if 'Tallos_Esperados' in df_det.columns else ('Esquejes', 'sum'),
                    total_camas=('Camas', 'sum'),
                    num_variedades=('Variedad', 'nunique'),
                    sem_siembra=('Semana_Siembra', 'first'),
                    sem_cosecha=('Semana_Cosecha', 'first')
                ).reset_index()

                res = []
                for _, row in grouped.iterrows():
                    sem_e = str(row['Semana_Enraizamiento'])
                    sem_s = str(row['sem_siembra'])
                    sem_c = str(row['sem_cosecha'])
                    base_esq = int(row['total_esquejes'])
                    esq = int(round(base_esq * factor_expansion))
                    base_tallos = int(row.get('total_tallos', esq * 0.835))
                    tallos = int(round(base_tallos * factor_expansion))
                    bandejas = calcular_bandejas_redondeadas(esq)
                    camas = round(esq / 5200.0, 1)
                    temp = clasificar_temporada_semana(int(sem_c) if str(sem_c).isdigit() else 202704)

                    res.append({
                        "Semana_Enraizamiento": sem_e,
                        "Semana_Enraizamiento_Label": f"S{sem_e[2:]}",
                        "Semana_Siembra": sem_s,
                        "Semana_Siembra_Label": f"S{sem_s[2:]}",
                        "Semana_Cosecha": sem_c,
                        "Semana_Cosecha_Label": f"S{sem_c[2:]}",
                        "Temporada": temp,
                        "Total_Esquejes": esq,
                        "Total_Tallos": tallos,
                        "Total_Bandejas_112": bandejas,
                        "Total_Camas": camas,
                        "Num_Variedades": int(row['num_variedades'])
                    })

                res = sorted(res, key=lambda x: x['Semana_Enraizamiento'])
                return res
            else:
                grouped = df_det.groupby('Semana_Siembra').agg(
                    total_esquejes=('Esquejes', 'sum'),
                    total_tallos=('Tallos_Esperados', 'sum') if 'Tallos_Esperados' in df_det.columns else ('Esquejes', 'sum'),
                    num_variedades=('Variedad', 'nunique')
                ).reset_index()

                res = []
                for _, row in grouped.iterrows():
                    sem_s = str(int(float(row['Semana_Siembra'])))
                    sem_e = restar_semanas_iso(sem_s, SEMANAS_ENRAIZAMIENTO)
                    base_esq = int(row['total_esquejes'])
                    esq = int(round(base_esq * factor_expansion))
                    base_tallos = int(row.get('total_tallos', esq * 0.835))
                    tallos = int(round(base_tallos * factor_expansion))
                    bandejas = calcular_bandejas_redondeadas(esq)
                    camas = round(esq / 5200.0, 1)

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
                        "Total_Tallos": tallos,
                        "Total_Bandejas_112": bandejas,
                        "Total_Camas": camas,
                        "Num_Variedades": int(row['num_variedades'])
                    })

                res = sorted(res, key=lambda x: x['Semana_Enraizamiento'])
                return res
        except Exception:
            pass

    # Modo plataforma base o fallback
    if not os.path.exists(archivo_pedido):
        candidatos = glob.glob("PedidoConsolidado*.xlsx") + glob.glob("*pedido*.xlsx")
        archivo_pedido = candidatos[0] if candidatos else None

    if not archivo_pedido or not os.path.exists(archivo_pedido):
        return []

    try:
        df_mrp = generar_plan_mva(archivo_pedido, week_is="Pedido")
        if df_mrp.empty or 'Semana_Siembra' not in df_mrp.columns:
            return []

        grouped = df_mrp.groupby('Semana_Siembra').agg(
            total_esquejes=('Esquejes_Para_Siembra (Final)', 'sum'),
            num_variedades=('Variedad', 'nunique')
        ).reset_index()

        res = []
        for _, row in grouped.iterrows():
            sem_s = str(row['Semana_Siembra'])
            sem_e = restar_semanas_iso(sem_s, SEMANAS_ENRAIZAMIENTO)
            esq = int(round(row['total_esquejes']))
            bandejas = calcular_bandejas_redondeadas(esq)
            camas = round(esq / 5200.0, 1)

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
                "Total_Camas": camas,
                "Num_Variedades": int(row['num_variedades'])
            })

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

    total_horas = sum(horas_jornada.values()) or TOTAL_HORAS_SEMANA_ESTANDAR
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
        h_jornada = HORAS_JORNADA.get(d, 7.5)
        bandejas_por_dia[d] = calcular_bandejas_redondeadas(esq_d)

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
    config_cuadrilla: dict = None,
    modo_plan: str = "aprobado",
    factor_expansion: float = 1.0,
    correr_variedades: bool = True,
    base_capacidad: str = "bloque",
    df_inventario_ajustado: pd.DataFrame = None
) -> dict:
    """
    Genera el Plano Operativo de Enraizamiento para la semana especificada:
    - Cruza el Pedido Aprobado (desfasado fenológicamente a siembra y cosecha jueves).
    - Desagrega por Variedad, Color, Flor y Bandejas de 112 cavidades (redondeadas al entero más cercano).
    - Si se pasa df_inventario_ajustado (o existe inventario/compensación registrada), sincroniza los
      esquejes efectivos a clavar, compensaciones de volumen, reprogramaciones y variedades extemporáneas,
      asegurando que el plano físico y el PDF descargado reflejen la realidad operativa ajustada.
    - Asigna día tentativo (pico jueves) y nivela la jornada semanal (Lunes a Sábado).
    - Asigna bloque de campo estimado de destino (01 a 06).
    - Modela el cálculo de mano de obra y horas-hombre requeridas.
    """
    sem_siembra = sumar_semanas_iso(semana_enraizamiento, SEMANAS_ENRAIZAMIENTO)
    asegurar_sincronizacion_pedido_y_plan_detallado(db=db, archivo_pedido=archivo_pedido)
    df_sem = pd.DataFrame()

    if modo_plan in ["aprobado", "max_capacidad"] and os.path.exists("Plan_Aprobado_Detallado.csv"):
        try:
            df_all = pd.read_csv("Plan_Aprobado_Detallado.csv")
            if correr_variedades:
                df_all_sh = aplicar_corrimiento_fenologico_a_plan(df_all, db=db)
                df_sem = df_all_sh[df_all_sh['Semana_Enraizamiento'] == str(semana_enraizamiento)].copy()
                if not df_sem.empty:
                    df_sem['Esquejes_Para_Siembra (Final)'] = (df_sem['Esquejes'] * factor_expansion).round().astype(int)
            else:
                sem_s_int = int(float(sem_siembra)) if str(sem_siembra).isdigit() else 202640
                df_sem = df_all[df_all['Semana_Siembra'].astype(str) == str(sem_s_int)].copy()
                if not df_sem.empty:
                    df_sem['Esquejes_Para_Siembra (Final)'] = (df_sem['Esquejes'] * factor_expansion).round().astype(int)
        except Exception:
            pass

    if df_sem.empty:
        if not os.path.exists(archivo_pedido):
            candidatos = glob.glob("PedidoConsolidado*.xlsx") + glob.glob("*pedido*.xlsx")
            archivo_pedido = candidatos[0] if candidatos else None

        if not archivo_pedido or not os.path.exists(archivo_pedido):
            return {"error": "Archivo de Pedido Consolidado no encontrado."}

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
    
    # Cargar dimensionamiento físico de camas por bloque
    try:
        dict_dimensiones = obtener_dimensiones_camas_bloques(db=db)
    except Exception:
        dict_dimensiones = {}

    # Cargar proyección de bloques para asignación espacial tentativa
    try:
        _, df_bloques_52w = calcular_ocupacion_semanal_52w(db)
    except Exception:
        df_bloques_52w = pd.DataFrame()

    lotes_raw = []
    # Cosecha comercial estimada (~11 semanas post-siembra como default)
    sem_c_global = sumar_semanas_iso(sem_siembra, 11)
    temporada_cosecha = clasificar_temporada_semana(int(sem_c_global) if sem_c_global.isdigit() else 202704)

    for _, row in df_sem.iterrows():
        v_nom = str(row['Variedad']).strip()
        v_obj = variedades_db.get(v_nom.lower())
        
        flor = row.get('Flor') or (v_obj.flor if v_obj else 'Desconocida')
        color = row.get('Color') or (v_obj.color if v_obj else 'N/A')
        
        # Pedido comercial base (5,200 esquejes / cama estándar aprobada)
        esq_pedido = int(round(row['Esquejes_Para_Siembra (Final)']))
        camas_campo = round(esq_pedido / 5200.0, 1)
        
        dia_inicio = int(row.get('Dia_Inicio') or (v_obj.dia_inicio if (v_obj and v_obj.dia_inicio) else 84))
        dia_pico = int(row.get('Dia_Pico') or (v_obj.dia_pico if (v_obj and v_obj.dia_pico) else 77))
        aprov_pp = float(row.get('Aprov_PP') or (v_obj.aprov_pp if (v_obj and v_obj.aprov_pp and v_obj.aprov_pp > 0) else 0.806))

        # Semanas de siembra y cosecha específicas del lote
        sem_siembra_row = str(row.get('Semana_Siembra') or sem_siembra)
        sem_cosecha_var = str(row.get('Semana_Cosecha') or sumar_semanas_iso(sem_siembra_row, int(round(dia_pico / 7.0))))
        temp_cosecha_var = clasificar_temporada_semana(int(sem_cosecha_var) if sem_cosecha_var.isdigit() else 202704)

        # Bloque de destino tentativo en campo
        bloque_dest_res = resolver_bloque_tentativo(sem_siembra_row, df_bloques_52w=df_bloques_52w, dict_dimensiones=dict_dimensiones)
        if isinstance(bloque_dest_res, tuple):
            b_code = str(bloque_dest_res[0])
            b_info = bloque_dest_res[1]
        else:
            b_code = str(bloque_dest_res)
            b_info = dict_dimensiones.get(b_code, {})

        bloque_dest = f"Bloque {b_code}" if not b_code.startswith("Bloque") else b_code

        # Determinar capacidad física instalada de la cama según base_capacidad
        if base_capacidad == "bloque" and b_info:
            esq_cama_instalada = int(b_info.get('esquejes_cama', 5200))
            m2_cama = float(b_info.get('m2_cama', 52.98))
        elif base_capacidad == "finca":
            finca_info = dict_dimensiones.get('FINCA', {})
            esq_cama_instalada = int(finca_info.get('esquejes_cama', 4867))
            m2_cama = float(finca_info.get('m2_cama', 52.98))
        else: # std_5200
            esq_cama_instalada = 5200
            m2_cama = 56.71

        # Requerimiento de esquejes para enraizamiento basado en la capacidad física real de las camas
        if esq_cama_instalada > 0 and camas_campo > 0:
            esq_enraizamiento = int(round(camas_campo * esq_cama_instalada))
        else:
            esq_enraizamiento = esq_pedido

        # Bandejas estándar 112 cavidades redondeadas al entero más cercano (ej. 46.4 -> 46)
        bandejas = calcular_bandejas_redondeadas(esq_enraizamiento)
        esq_bandejas = bandejas * CAVIDADES_POR_BANDEJA

        # Proyección de tallos esperados a cosecha
        tallos_esperados = int(round(esq_enraizamiento * aprov_pp))

        # Día tentativo fenológico (Pico Jueves)
        dia_tentativo = calcular_dia_tentativo_enraizamiento(dia_pico)

        lotes_raw.append({
            "Flor": flor,
            "Color": color,
            "Variedad": v_nom,
            "Esquejes_Pedido": esq_pedido,
            "Esquejes": esq_enraizamiento,
            "Bandejas_112": bandejas,
            "Esquejes_Bandejas": esq_bandejas,
            "Camas_Campo": camas_campo,
            "Bloque_Destino": bloque_dest,
            "Capacidad_Cama_Bloque": esq_cama_instalada,
            "M2_Cama_Bloque": m2_cama,
            "Dia_Tentativo": dia_tentativo,
            "Dia_Inicio": dia_inicio,
            "Dia_Pico": dia_pico,
            "Aprov_PP": aprov_pp,
            "Tallos_Esperados": tallos_esperados,
            "Semana_Siembra": sem_siembra_row,
            "Semana_Enraizamiento": semana_enraizamiento,
            "Semana_Cosecha": sem_cosecha_var,
            "Temporada": temp_cosecha_var,
            "Es_Extemporaneo": False,
            "Observaciones": ""
        })

    # Sincronización dinámica con Ajustes de Inventario y Compensaciones (si existen)
    es_ajustado = False
    if df_inventario_ajustado is not None and not df_inventario_ajustado.empty:
        df_inv_sem = df_inventario_ajustado.copy()
        if 'Semana_Enraizamiento' in df_inv_sem.columns:
            df_match = df_inv_sem[df_inv_sem['Semana_Enraizamiento'].astype(str) == str(semana_enraizamiento)]
            if not df_match.empty:
                df_inv_sem = df_match

        if not df_inv_sem.empty and 'Variedad' in df_inv_sem.columns:
            mapa_inv = {str(r['Variedad']).strip().lower(): r for _, r in df_inv_sem.iterrows()}
            variedades_procesadas = set()

            for lote in lotes_raw:
                v_low = lote['Variedad'].strip().lower()
                if v_low in mapa_inv:
                    r_inv = mapa_inv[v_low]
                    variedades_procesadas.add(v_low)
                    esq_efect = int(pd.to_numeric(r_inv.get('Esquejes_Efectivos_Clavar', lote['Esquejes']), errors='coerce') or 0)
                    comp = int(pd.to_numeric(r_inv.get('Compensacion_Volumen', 0), errors='coerce') or 0)
                    reprog = int(pd.to_numeric(r_inv.get('Reprogramado_Siguiente_Semana', 0), errors='coerce') or 0)

                    hubo_cambio = (comp != 0) or (reprog != 0) or (esq_efect != lote['Esquejes'])
                    lote['Esquejes_Originales'] = lote['Esquejes']
                    lote['Esquejes'] = esq_efect
                    lote['Bandejas_112'] = calcular_bandejas_redondeadas(esq_efect)
                    lote['Esquejes_Bandejas'] = lote['Bandejas_112'] * CAVIDADES_POR_BANDEJA
                    lote['Camas_Campo'] = round(esq_efect / 5200.0, 1)
                    lote['Tallos_Esperados'] = int(round(esq_efect * lote['Aprov_PP']))
                    lote['Compensacion_Volumen'] = comp
                    lote['Reprogramado_Siguiente_Semana'] = reprog
                    lote['Estado_Disponibilidad'] = str(r_inv.get('Estado_Disponibilidad', ''))
                    lote['Es_Ajustado_Inventario'] = hubo_cambio
                    lote['Es_Extemporaneo'] = False
                    lote['Observaciones'] = ""
                    
                    if hubo_cambio:
                        es_ajustado = True

            # Incorporar variedades extemporáneas con volumen efectivo > 0
            for v_low, r_inv in mapa_inv.items():
                if v_low not in variedades_procesadas:
                    esq_efect = int(pd.to_numeric(r_inv.get('Esquejes_Efectivos_Clavar', 0), errors='coerce') or 0)
                    if esq_efect <= 0:
                        # Si no se calculó previamente, los extemporáneos clavan su total disponible físico
                        esq_efect = int(pd.to_numeric(r_inv.get('Total_Disponible', 0), errors='coerce') or 0)

                    if esq_efect > 0:
                        v_obj = variedades_db.get(v_low)
                        dp = int(v_obj.dia_pico if (v_obj and v_obj.dia_pico) else 77)
                        di = int(v_obj.dia_inicio if (v_obj and v_obj.dia_inicio) else 70)
                        aprov = float(v_obj.aprov_pp if (v_obj and v_obj.aprov_pp) else 0.806)
                        band = calcular_bandejas_redondeadas(esq_efect)
                        bloque_dest_ext = resolver_bloque_tentativo(sem_siembra, df_bloques_52w=df_bloques_52w, dict_dimensiones=dict_dimensiones)
                        b_code_ext = str(bloque_dest_ext[0] if isinstance(bloque_dest_ext, tuple) else bloque_dest_ext)
                        b_str_ext = f"Bloque {b_code_ext}" if not b_code_ext.startswith("Bloque") else b_code_ext

                        nom_real = str(r_inv.get('Variedad') or (v_obj.nombre if v_obj else v_low.capitalize())).strip()
                        comp_ext = int(pd.to_numeric(r_inv.get('Compensacion_Volumen', 0), errors='coerce') or 0)

                        lotes_raw.append({
                            "Flor": str(r_inv.get('Flor') or (v_obj.flor if v_obj else 'Estándar')),
                            "Color": str(r_inv.get('Color') or (v_obj.color if v_obj else 'Mix')),
                            "Variedad": nom_real,
                            "Esquejes_Pedido": 0,
                            "Esquejes_Originales": 0,
                            "Esquejes": esq_efect,
                            "Bandejas_112": band,
                            "Esquejes_Bandejas": band * CAVIDADES_POR_BANDEJA,
                            "Camas_Campo": round(esq_efect / 5200.0, 1),
                            "Bloque_Destino": b_str_ext,
                            "Capacidad_Cama_Bloque": 5200,
                            "M2_Cama_Bloque": 56.71,
                            "Dia_Tentativo": calcular_dia_tentativo_enraizamiento(dp),
                            "Dia_Inicio": di,
                            "Dia_Pico": dp,
                            "Aprov_PP": aprov,
                            "Tallos_Esperados": int(round(esq_efect * aprov)),
                            "Semana_Siembra": sem_siembra,
                            "Semana_Enraizamiento": semana_enraizamiento,
                            "Semana_Cosecha": sem_c_global,
                            "Temporada": temporada_cosecha,
                            "Compensacion_Volumen": comp_ext,
                            "Reprogramado_Siguiente_Semana": 0,
                            "Estado_Disponibilidad": str(r_inv.get('Estado_Disponibilidad', f"🟣 Extemporáneo ({esq_efect:,d} a clavar)")),
                            "Es_Ajustado_Inventario": True,
                            "Es_Extemporaneo": True,
                            "Observaciones": ""
                        })
                        es_ajustado = True

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
            "Jornada (Horas)": HORAS_JORNADA.get(d, 7.5),
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

    # Proyección Biológica de Cosecha Semanal a partir de este plano
    try:
        curvas_dyn = calcular_curvas_dinamicas(db=db)
    except Exception:
        curvas_dyn = {}

    recs_cosecha = []
    for l in lotes_nivelados:
        v_nom = l['Variedad']
        v_norm = v_nom.lower().strip()
        esq = l['Esquejes']
        sem_s_lote = str(l['Semana_Siembra'])

        if v_nom in curvas_dyn:
            dyn = curvas_dyn[v_nom]
            dp = int(dyn['dia_pico'])
            di = int(dyn['dia_inicio'])
            c_p = [dyn[f'c{i}'] for i in range(1, 16)]
        elif v_norm in variedades_db:
            vo = variedades_db[v_norm]
            dp = int(vo.dia_pico) if vo.dia_pico else 77
            di = int(vo.dia_inicio) if vo.dia_inicio else 70
            c_p = [getattr(vo, f'c{i}') or 0.0 for i in range(1, 16)]
        else:
            dp, di, c_p = 77, 70, [0.806] + [0.0] * 14

        y_s, w_s = int(sem_s_lote[:4]), int(sem_s_lote[4:])
        dt_s = date.fromisocalendar(y_s, w_s, 1)
        for d in range(1, 8):
            dt_test = date.fromisocalendar(y_s, w_s, d)
            if (dt_test + timedelta(days=dp)).isoweekday() == 4:
                dt_s = dt_test
                break

        dt_ini = dt_s + timedelta(days=di)
        for i_dia, pct in enumerate(c_p):
            if pct and pct > 0:
                dt_c = dt_ini + timedelta(days=i_dia)
                sem_c = isocalendar_to_string(dt_c)
                recs_cosecha.append({
                    "Flor": l['Flor'],
                    "Color": l['Color'],
                    "Variedad": v_nom,
                    "Semana_Cosecha": sem_c,
                    "Semana_Cosecha_Label": f"S{sem_c[2:]}",
                    "Tallos": esq * pct
                })

    df_proyeccion_cosecha = pd.DataFrame()
    if recs_cosecha:
        df_rc = pd.DataFrame(recs_cosecha)
        grp_c = df_rc.groupby(['Semana_Cosecha', 'Semana_Cosecha_Label'])['Tallos'].sum().reset_index()
        grp_c['Tallos_Proyectados'] = grp_c['Tallos'].round().astype(int)
        tot_tallos_c = grp_c['Tallos_Proyectados'].sum()
        grp_c['% del Total Lote'] = ((grp_c['Tallos_Proyectados'] / tot_tallos_c) * 100.0).round(1) if tot_tallos_c > 0 else 0.0
        grp_c['Temporada'] = grp_c['Semana_Cosecha'].apply(lambda x: clasificar_temporada_semana(int(x) if str(x).isdigit() else 202704))
        df_proyeccion_cosecha = grp_c.sort_values('Semana_Cosecha')

    # Ordenar lotes detallados por Día de Programación y luego por Variedad
    dia_order_map = {d: i for i, d in enumerate(dias_orden)}
    lotes_nivelados = sorted(
        lotes_nivelados, 
        key=lambda x: (dia_order_map.get(x['Dia_Programado'], 9), x['Flor'], x['Variedad'])
    )
    df_plano_detallado = pd.DataFrame(lotes_nivelados)
    if not df_plano_detallado.empty:
        if 'Es_Extemporaneo' in df_plano_detallado.columns:
            df_plano_detallado['Es_Extemporaneo'] = df_plano_detallado['Es_Extemporaneo'].fillna(False).astype(bool)
        else:
            df_plano_detallado['Es_Extemporaneo'] = False
        if 'Observaciones' in df_plano_detallado.columns:
            df_plano_detallado['Observaciones'] = df_plano_detallado['Observaciones'].fillna("").astype(str)
        else:
            df_plano_detallado['Observaciones'] = ""

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
        "df_proyeccion_cosecha": df_proyeccion_cosecha,
        "resumen_mano_obra": res_mano_obra,
        "kpis": {
            "total_esquejes": tot_esq_sem,
            "total_esquejes_pedido": sum(l.get('Esquejes_Pedido', l['Esquejes']) for l in lotes_nivelados),
            "total_bandejas": res_mano_obra['total_bandejas'],
            "total_camas": round(sum(l['Camas_Campo'] for l in lotes_nivelados), 1),
            "num_lotes": len(lotes_nivelados),
            "horas_requeridas": res_mano_obra['total_horas_requeridas'],
            "operarios_promedio": res_mano_obra['promedio_operarios_requeridos'],
            "rendimiento_ponderado": res_mano_obra['rendimiento_ponderado'],
            "tallos_esperados": sum(l['Tallos_Esperados'] for l in lotes_nivelados),
            "base_capacidad": base_capacidad
        },
        "es_ajustado_inventario": es_ajustado
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
    es_ajust = res_plano.get("es_ajustado_inventario", False)
    header_data = [
        [
            Paragraph("<b>JARDINES DE CHÍA S.A.S. — PLANO OPERATIVO DE ENRAIZAMIENTO (AJUSTADO)</b>" if es_ajust else "<b>JARDINES DE CHÍA S.A.S. — PLANO OPERATIVO DE ENRAIZAMIENTO</b>", title_style),
            Paragraph(f"<b>EMISIÓN OPERATIVA AJUSTADA</b> | Fecha: {today_str}" if es_ajust else f"<b>EMISIÓN S&OP</b> | Fecha: {today_str}", subtitle_style)
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
        "Semana", "Jornada Efectiva", "Total Esquejes", "Bandejas 112", 
        "Rend. Ponderado", "Horas Req.", "Op. Req.", "Op. Asignados", "Balance Semanal", "Estado Capacidad"
    ]
    labor_data = [
        [Paragraph(f"<b>{h}</b>", th_style) for h in labor_headers],
        [
            Paragraph(sem_e, tc_center),
            Paragraph(f"{TOTAL_HORAS_SEMANA_ESTANDAR:.1f} h", tc_center),
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

    # 3. Plano Detallado de Enraizamiento con Columna de Observaciones
    df_det = res_plano.get("df_plano_detallado", pd.DataFrame())
    if not df_det.empty:
        det_cols = [
            "Día Prog.", "Flor", "Color", "Variedad", 
            "Esquejes", "Bandejas (112)", "Bloque Campo", 
            "Sem. Siembra", "Ejecutado Real", "Observaciones"
        ]
        table_data = [[Paragraph(f"<b>{c}</b>", th_style) for c in det_cols]]

        for _, r in df_det.iterrows():
            dia_txt = str(r['Dia_Programado'])
            if r.get('Es_Nivelado', False):
                dia_txt += " *"

            esq_val = int(r['Esquejes'])
            ban_val = int(r['Bandejas_112'])

            if esq_val == 0:
                est_raw = str(r.get('Estado_Disponibilidad', 'REPROGRAMADO')).replace('🔴 ', '').replace('🟢 ', '').replace('🟡 ', '')
                if 'REPROG' in est_raw.upper():
                    ejec_box = Paragraph("<font color='#c62828'><b>REPROG. +1W</b></font>", tc_center)
                else:
                    ejec_box = Paragraph("<font color='#2e7d32'><b>COMPENSADO</b></font>", tc_center)
            else:
                ejec_box = Paragraph("", tc_center)

            var_txt = str(r['Variedad'])
            comp_val = int(pd.to_numeric(r.get('Compensacion_Volumen', 0), errors='coerce') or 0)
            es_ext = r.get('Es_Extemporaneo', False)
            is_extemporaneo = (
                pd.notnull(es_ext)
                and (es_ext is True or es_ext == 1 or str(es_ext).strip().lower() == 'true')
                and int(pd.to_numeric(r.get('Esquejes_Pedido', 1), errors='coerce') or 0) == 0
            )
            if is_extemporaneo:
                var_txt += " <i>(Extemp.)</i>"
            elif comp_val > 0:
                var_txt += f" <i>(+{comp_val:,d} comp.)</i>"
            elif esq_val == 0:
                var_txt += " <i>(Reprog. +1w)</i>"

            # Celda de Observaciones limpia para diligenciamiento manual de novedades en campo
            obs_cell = Paragraph("", tc_style)

            table_data.append([
                Paragraph(dia_txt, tc_style),
                Paragraph(str(r['Flor']), tc_style),
                Paragraph(str(r['Color']), tc_style),
                Paragraph(f"<b>{var_txt}</b>", tc_bold),
                Paragraph(f"{esq_val:,d}", tc_center),
                Paragraph(f"{ban_val:,d}", tc_center),
                Paragraph(str(r.get('Bloque_Destino', 'Bloque 01')), tc_center),
                Paragraph(f"S{str(r['Semana_Siembra'])[2:]}", tc_center),
                ejec_box,
                obs_cell,
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
            Paragraph("", tc_center),
            Paragraph("", tc_center),
        ])

        t_det = Table(table_data, colWidths=[50, 46, 46, 138, 54, 52, 58, 50, 74, 184], repeatRows=1)
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

    # Nota Operativa si el plano fue ajustado con inventario
    if es_ajust:
        nota_style = ParagraphStyle(
            'NotaAjust',
            parent=meta_style,
            fontName='Helvetica-Oblique',
            fontSize=6.5,
            leading=8.0,
            textColor=colors.HexColor('#1b5e20')
        )
        nota_ajust = Paragraph(
            "<b>* NOTA OPERATIVA:</b> Este plano incorpora los ajustes de inventario de cuarto frío, compensaciones por flor-color "
            "(regla agronómica >= 0.5 camas) y extemporáneos. Los lotes marcados como <b>REPROG. +1W</b> corresponden a faltantes no cubiertos "
            "que se reprograman al plan de la siguiente semana.",
            nota_style
        )
        elements.append(nota_ajust)
        elements.append(Spacer(1, 2))

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

def obtener_datos_comparativos_enraizamiento_y_camas(
    db: Session,
    modo_plan: str = "aprobado",
    factor_expansion: float = 1.0,
    correr_variedades: bool = True
) -> dict:
    """
    Calcula los datos para:
    1. Gráfico comparativo de la Proyección de Enraizamiento:
       - Proyección entregada por la plataforma base
       - Lógica de Proyección de Pedido Aprobado con o sin corrimiento fenológico dinámico
       - Objetivo de Tallos a Cosecha calculado con aprovechamientos biológicos reales de cada variedad
    2. Análisis de Liberación de Camas Vivas en Campo:
       - Rotación estándar con 7 días de descanso
       - Rotación acelerada con 3 días de descanso (ajuste de espacio requerido)
       - Demanda de camas de siembra de San Valentín
    """
    asegurar_sincronizacion_pedido_y_plan_detallado(db=db)

    # 1. Proyección de Enraizamiento Plataforma Base
    semanas_base = obtener_semanas_enraizamiento_disponibles(modo_plan="plataforma_base")
    dict_plat = {s['Semana_Enraizamiento']: s['Total_Esquejes'] for s in semanas_base}

    # Proyección Plan Aprobado / Dinámico
    dict_ana = {}
    dict_camas_siembra = {}
    dict_tallos_cosecha = {}

    if os.path.exists("Plan_Aprobado_Detallado.csv"):
        try:
            df_det = pd.read_csv("Plan_Aprobado_Detallado.csv")
            if correr_variedades:
                df_det_calc = aplicar_corrimiento_fenologico_a_plan(df_det, db=db)
                grp_enr = df_det_calc.groupby('Semana_Enraizamiento').agg(
                    total_esq=('Esquejes', 'sum'),
                    total_tallos=('Tallos_Esperados', 'sum'),
                    total_camas=('Camas', 'sum')
                )
                for sem_k, r in grp_enr.iterrows():
                    dict_ana[str(sem_k)] = int(round(r['total_esq'] * factor_expansion))
                    dict_tallos_cosecha[str(sem_k)] = int(round(r['total_tallos'] * factor_expansion))
                    dict_camas_siembra[str(sem_k)] = round(r['total_camas'] * factor_expansion, 1)
            else:
                grp_siem = df_det.groupby('Semana_Siembra').agg(
                    total_esq=('Esquejes', 'sum'),
                    total_tallos=('Tallos_Esperados', 'sum') if 'Tallos_Esperados' in df_det.columns else ('Esquejes', 'sum'),
                    total_camas=('Camas', 'sum')
                )
                for sem_s_k, r in grp_siem.iterrows():
                    sem_e_k = restar_semanas_iso(str(int(float(sem_s_k))), SEMANAS_ENRAIZAMIENTO)
                    esq_k = int(round(r['total_esq'] * factor_expansion))
                    tall_k = int(round(r.get('total_tallos', esq_k * 0.835) * factor_expansion))
                    dict_ana[sem_e_k] = esq_k
                    dict_tallos_cosecha[sem_e_k] = tall_k
                    dict_camas_siembra[sem_e_k] = round(r['total_camas'] * factor_expansion, 1)
        except Exception:
            pass

    # Ventana dinámica de todas las semanas presentes en el pedido
    semanas_all = sorted(list(set(list(dict_plat.keys()) + list(dict_ana.keys()))))
    semanas_foco = [s for s in semanas_all if str(s).isdigit() and len(str(s)) == 6]
    if not semanas_foco:
        semanas_foco = [f"2026{w:02d}" for w in range(35, 53)]

    rows_comp = []

    for sem_e in semanas_foco:
        sem_s = sumar_semanas_iso(sem_e, 3)
        sem_c = sumar_semanas_iso(sem_s, 11)
        val_plat = dict_plat.get(sem_e, 0)
        val_ana = dict_ana.get(sem_e, val_plat)
        tallos_cosecha = dict_tallos_cosecha.get(sem_e, int(round(val_ana * 0.835)))
        camas_siembra = dict_camas_siembra.get(sem_e, round(val_ana / 5200.0, 1))
        temp_foco = clasificar_temporada_semana(int(sem_c) if str(sem_c).isdigit() else 202704)

        rows_comp.append({
            "Semana_Enraizamiento": sem_e,
            "Semana_Enraizamiento_Label": f"S{sem_e[2:]}",
            "Semana_Siembra": sem_s,
            "Semana_Siembra_Label": f"S{sem_s[2:]}",
            "Semana_Cosecha": sem_c,
            "Semana_Cosecha_Label": f"S{sem_c[2:]}",
            "Enraizamiento_Plataforma": val_plat,
            "Enraizamiento_Analitica": val_ana,
            "Diferencia_Esquejes": val_ana - val_plat,
            "Camas_Siembra": camas_siembra,
            "Tallos_Esperados_Cosecha": tallos_cosecha,
            "Temporada": temp_foco
        })

    df_comp_enraizamiento = pd.DataFrame(rows_comp)

    # 2. Análisis de Liberación de Camas Vivas en Campo
    siembras = db.query(Siembra).filter(Siembra.estado == EstadoSiembra.EN_PRODUCCION).all() if db else []
    records_7d = []
    records_3d = []

    for s in siembras:
        var = s.variedad
        dia_ini = var.dia_inicio if (var and var.dia_inicio and var.dia_inicio > 0) else 84
        
        # Fecha de liberación con 7 días de descanso
        f_lib_7d = s.fecha_siembra + timedelta(days=dia_ini + 14 + 7)
        sem_lib_7d = isocalendar_to_string(f_lib_7d)
        
        # Fecha de liberación con 3 días de descanso (ajuste de espacio)
        f_lib_3d = s.fecha_siembra + timedelta(days=dia_ini + 14 + 3)
        sem_lib_3d = isocalendar_to_string(f_lib_3d)
        
        records_7d.append(sem_lib_7d)
        records_3d.append(sem_lib_3d)

    # Evaluar la liberación semana a semana dinámicamente según lotes vivos en campo
    semanas_eval_cands = sorted(list(set(records_7d + records_3d)))
    semanas_eval = [s for s in semanas_eval_cands if str(s).isdigit() and len(str(s)) == 6]
    if not semanas_eval:
        semanas_eval = [f"2026{w:02d}" for w in range(40, 53)]
    rows_lib = []

    demanda_acum = 0.0

    for sem_s in semanas_eval:
        lib_7d = sum(1 for sem in records_7d if sem <= sem_s)
        lib_3d = sum(1 for sem in records_3d if sem <= sem_s)
        diff_ganancia = lib_3d - lib_7d
        
        # Encontrar demanda de camas correspondiente a esta semana de siembra
        sem_e_equiv = restar_semanas_iso(sem_s, 3)
        camas_req_sem = dict_camas_siembra.get(sem_e_equiv, round(dict_ana.get(sem_e_equiv, 0) / 5200.0, 1))
        demanda_acum += camas_req_sem

        rows_lib.append({
            "Semana_Siembra": sem_s,
            "Semana_Siembra_Label": f"S{sem_s[2:]}",
            "Camas_Liberadas_7d": lib_7d,
            "Camas_Liberadas_3d": lib_3d,
            "Ganancia_Camas_Anticipadas": diff_ganancia,
            "Camas_Requeridas_Semana": camas_req_sem,
            "Camas_Requeridas_Acumuladas": round(demanda_acum, 1),
            "Balance_Disponibilidad_3d": round(lib_3d - demanda_acum, 1)
        })

    df_liberacion_camas = pd.DataFrame(rows_lib)

    # 3. Proyección Biológica de Cosecha del Plan de Enraizamiento vs Plan de Producción (ForeCast)
    df_cosecha_vs_plan = pd.DataFrame()
    if os.path.exists("Plan_Aprobado_Detallado.csv") and db is not None:
        try:
            from app.services.mva_service import proyectar_cosecha_desde_mva
            df_det_all = pd.read_csv("Plan_Aprobado_Detallado.csv")
            df_det_all['Esquejes_Para_Siembra (Final)'] = df_det_all['Esquejes']
            df_proj_all = proyectar_cosecha_desde_mva(df_det_all, db)

            cols_sem_c = sorted([c for c in df_proj_all.columns if str(c).startswith('202')])
            tot_cosecha_sem = df_proj_all[cols_sem_c].sum()

            plan_prod_dict = {}
            if os.path.exists("Plan_Aprobado.csv"):
                df_pa = pd.read_csv("Plan_Aprobado.csv")
                col_cap = 'Tallos a Producir (Capacidad)' if 'Tallos a Producir (Capacidad)' in df_pa.columns else 'Suma de Tallos'
                if 'Semana' in df_pa.columns:
                    for s_raw, val in df_pa.groupby('Semana')[col_cap].sum().items():
                        try:
                            s_clean = str(int(float(s_raw)))
                            plan_prod_dict[s_clean] = int(round(val))
                        except Exception:
                            pass

            rows_cvp = []
            for sc in cols_sem_c:
                tallos_enr = int(round(tot_cosecha_sem[sc]))
                tallos_plan = plan_prod_dict.get(sc, 0)
                diff = tallos_enr - tallos_plan
                cumpl = (tallos_enr / tallos_plan * 100.0) if tallos_plan > 0 else 0.0
                temp_c = clasificar_temporada_semana(int(sc) if sc.isdigit() else 202704)

                rows_cvp.append({
                    "Semana_Cosecha": sc,
                    "Semana_Cosecha_Label": f"S{sc[2:]}",
                    "Temporada": temp_c,
                    "Tallos_Enraizamiento": tallos_enr,
                    "Tallos_Plan_Produccion": tallos_plan,
                    "Diferencia": diff,
                    "Cumplimiento_%": round(cumpl, 1)
                })
            df_cosecha_vs_plan = pd.DataFrame(rows_cvp)
        except Exception:
            pass

    return {
        "df_comp_enraizamiento": df_comp_enraizamiento,
        "df_liberacion_camas": df_liberacion_camas,
        "df_cosecha_vs_plan": df_cosecha_vs_plan
    }


# ==============================================================================
# MÓDULOS DE PERSISTENCIA: RECEPCIÓN, INVENTARIO Y EJECUCIÓN REAL DE ENRAIZAMIENTO
# ==============================================================================

# Constantes agronómicas y umbrales de negocio (esquejes y camas)
ESQUEJES_POR_CAMA_ESTANDAR = 5200
BANDEJAS_POR_CAMA_ESTANDAR = 46       # 46 bandejas de 112 cavidades = 5,152 esquejes
BANDEJAS_POR_MEDIA_CAMA = 23         # 23 bandejas de 112 cavidades = 2,576 esquejes
ESQUEJES_MEDIA_CAMA = 2600           # Media cama agronómica estándar (5,200 / 2)
MINIMO_COMPENSACION_ESQUEJES = 2500  # Umbral mínimo agronómico (≥0.5 camas) para viabilizar compensación
UMBRAL_DIFERENCIA_DESPRECIABLE = 500 # Diferencias ≤ 500 esquejes son despreciables (absorbidas en campo)

def calcular_transferencia_compensacion(needed: int, surplus_val: int) -> int:
    """
    Calcula el volumen exacto de esquejes a transferir respetando las reglas agronómicas:
    1. Umbral mínimo de media cama (≥0.5 camas / ≥2,500 esquejes / ≥23 bandejas):
       Tanto el déficit como el excedente disponible deben ser al menos media cama.
       Si es menor, NO se compensa para evitar fraccionar camas con micro-lotes ("llenar camas de mil variedades").
    2. Respeto estricto de capacidad de camas y cantidades reales de siembra:
       La transferencia se modula en múltiplos de media cama (0.5 camas = 2,600 esquejes)
       o cama completa (1.0 cama = 5,200 esquejes), sin sobrepasar el déficit necesario
       ni el excedente del donante.
    """
    if needed < MINIMO_COMPENSACION_ESQUEJES or surplus_val < MINIMO_COMPENSACION_ESQUEJES:
        return 0
    
    max_posible = min(needed, surplus_val)
    if max_posible < MINIMO_COMPENSACION_ESQUEJES:
        return 0
    
    # Modular en medias camas (2,600 esquejes = 23 bandejas de 112 cavidades)
    num_medias_camas = int(max_posible / ESQUEJES_MEDIA_CAMA)
    
    # Si max_posible está entre 2,500 y 2,599 esquejes, equivale a 1 media cama agronómica
    if num_medias_camas == 0 and max_posible >= MINIMO_COMPENSACION_ESQUEJES:
        return max_posible
    
    volumen_modulado = num_medias_camas * ESQUEJES_MEDIA_CAMA
    if volumen_modulado > max_posible:
        volumen_modulado = (num_medias_camas - 1) * ESQUEJES_MEDIA_CAMA
    
    if volumen_modulado < MINIMO_COMPENSACION_ESQUEJES and max_posible >= MINIMO_COMPENSACION_ESQUEJES:
        return max_posible
        
    return volumen_modulado

def calcular_esquejes_efectivos_clavar(row: dict | pd.Series) -> int:
    """
    Calcula los esquejes efectivos a clavar en banco:
    - Para variedades del plano maestro (Esquejes_Requeridos > 0):
      Requerido + Compensacion_Volumen - Reprogramado_Siguiente_Semana.
    - Para variedades extemporáneas (Esquejes_Requeridos == 0):
      Si asumió compensación (Compensacion_Volumen > 0): clava al menos ese volumen compensado.
      Si no compensó a nadie (Compensacion_Volumen == 0): clava el Total_Disponible físico que llegó/existe.
    """
    req = int(pd.to_numeric(row.get('Esquejes_Requeridos', 0), errors='coerce') or 0)
    comp = int(pd.to_numeric(row.get('Compensacion_Volumen', 0), errors='coerce') or 0)
    rep = int(pd.to_numeric(row.get('Reprogramado_Siguiente_Semana', 0), errors='coerce') or 0)
    disp = int(pd.to_numeric(row.get('Total_Disponible', 0), errors='coerce') or 0)

    if req > 0:
        return max(0, req + comp - rep)
    else:
        # Variedad Extemporánea
        if comp > 0:
            return max(0, min(disp, comp)) if disp > 0 else max(0, comp)
        else:
            return max(0, disp)

def calcular_estado_disponibilidad(row: dict | pd.Series) -> str:
    """
    Clasifica el estado del inventario aplicando la regla de negocio:
    - Si la variedad es extemporánea (Esquejes_Requeridos == 0): distintivo morado 🟣 con volumen a clavar o aportado.
    - Diferencias de volumen <= 500 esquejes son DESPRECIABLES y se consideran en tolerancia 🟢.
    - Solo se alertan como faltante crítico 🔴 si el déficit supera los 500 esquejes.
    """
    rep = int(pd.to_numeric(row.get('Reprogramado_Siguiente_Semana', 0), errors='coerce') or 0)
    comp = int(pd.to_numeric(row.get('Compensacion_Volumen', 0), errors='coerce') or 0)
    dif = int(pd.to_numeric(row.get('Diferencia_Saldo', 0), errors='coerce') or 0)
    req = int(pd.to_numeric(row.get('Esquejes_Requeridos', 0), errors='coerce') or 0)
    clavar = int(pd.to_numeric(row.get('Esquejes_Efectivos_Clavar', 0), errors='coerce') or 0)

    curr_est = str(row.get('Estado_Disponibilidad', ''))
    if "Excedente Aprovechado" in curr_est:
        return curr_est
    if "Excedente en Frío" in curr_est:
        return curr_est

    # Variedad extemporánea (no estaba en el plano maestro semanal, req == 0)
    if req == 0:
        if comp > 0:
            return f"🟣 Extemporáneo (Compensó {comp:,d})"
        elif clavar > 0:
            return f"🟣 Extemporáneo ({clavar:,d} a clavar)"
        elif dif > 0:
            return f"🟣 Extemporáneo (+{dif:,d} en frío)"
        else:
            return "🟣 Extemporáneo (0)"

    if rep > UMBRAL_DIFERENCIA_DESPRECIABLE:
        return f"🔴 Reprog. Sig. Sem. (-{rep:,d})"
    elif comp > 0:
        return f"🟡 Asume Compensación (+{comp:,d})"
    elif comp < 0:
        return f"🟢 Déficit Cubierto ({comp:,d})"
    elif abs(dif) <= UMBRAL_DIFERENCIA_DESPRECIABLE:
        if dif == 0:
            return "🟢 Completo (100%)"
        elif dif > 0:
            return f"🟢 En Tolerancia (+{dif:,d})"
        else:
            return f"🟢 En Tolerancia ({dif:,d})"
    elif dif > UMBRAL_DIFERENCIA_DESPRECIABLE:
        if dif < MINIMO_COMPENSACION_ESQUEJES:
            return f"🔵 Remanente Frío (<0.5 cam, +{dif:,d})"
        else:
            return f"🔵 Excedente Viable (≥0.5 cam, +{dif:,d})"
    else: # dif < -500
        if abs(dif) < MINIMO_COMPENSACION_ESQUEJES:
            return f"🔴 Faltante (<0.5 cam, {dif:,d})"
        else:
            return f"🔴 Faltante Crítico ({dif:,d})"

def cargar_inventario_recepcion(semana_enraizamiento: str = None) -> pd.DataFrame:
    """
    Carga el inventario de esquejes disponible (Cuarto Frío + Recepción de la semana previa - Bajas)
    desde Recepcion_Inventario_Esquejes.csv (o Inventario_Esquejes_Lunes.csv por retrocompatibilidad).
    Si se especifica semana_enraizamiento, filtra por esa semana y sanea tipos de datos.
    Si la semana no existe, arrastra el remanente de cuarto frío de la semana anterior.
    """
    cols_str = ["Semana_Enraizamiento", "Fecha_Ingreso", "Flor", "Color", "Variedad", "Estado_Disponibilidad", "Estado_Aprobacion", "Observaciones"]
    cols_int = [
        "Stock_Cuarto_Frio", "Esquejes_Recepcion", "Esquejes_Recibidos", "Bajas_Descartes",
        "Total_Disponible", "Esquejes_Requeridos", "Diferencia_Recepcion", "Compensacion_Volumen",
        "Reprogramado_Siguiente_Semana", "Esquejes_Efectivos_Clavar", "Diferencia_Saldo",
        "Bandejas_112_Disponibles", "Esquejes_Clavados_Reales", "Remanente_Final"
    ]

    archivo_fuente = ARCHIVO_INVENTARIO_RECEPCION if os.path.exists(ARCHIVO_INVENTARIO_RECEPCION) else ARCHIVO_INVENTARIO_LUNES

    if os.path.exists(archivo_fuente):
        try:
            df = pd.read_csv(archivo_fuente)
            if df is not None and not df.empty:
                df['Semana_Enraizamiento'] = df['Semana_Enraizamiento'].astype(str)
                if semana_enraizamiento:
                    df = df[df['Semana_Enraizamiento'] == str(semana_enraizamiento)].copy()

                if not df.empty:
                    # Sincronización de nombres Recepción / Recibidos
                    if 'Esquejes_Recepcion' not in df.columns and 'Esquejes_Recibidos' in df.columns:
                        df['Esquejes_Recepcion'] = df['Esquejes_Recibidos']
                    elif 'Esquejes_Recibidos' not in df.columns and 'Esquejes_Recepcion' in df.columns:
                        df['Esquejes_Recibidos'] = df['Esquejes_Recepcion']
                    elif 'Esquejes_Recepcion' not in df.columns and 'Esquejes_Recibidos' not in df.columns:
                        df['Esquejes_Recepcion'] = 0
                        df['Esquejes_Recibidos'] = 0

                    # Retrocompatibilidad de columnas
                    if 'Stock_Cuarto_Frio' not in df.columns:
                        df['Stock_Cuarto_Frio'] = 0
                    if 'Bajas_Descartes' not in df.columns:
                        df['Bajas_Descartes'] = 0
                    if 'Compensacion_Volumen' not in df.columns:
                        df['Compensacion_Volumen'] = 0
                    if 'Reprogramado_Siguiente_Semana' not in df.columns:
                        df['Reprogramado_Siguiente_Semana'] = 0
                    if 'Esquejes_Clavados_Reales' not in df.columns:
                        df['Esquejes_Clavados_Reales'] = 0
                    if 'Estado_Aprobacion' not in df.columns:
                        df['Estado_Aprobacion'] = "Pendiente Aprobación"

                    for c in cols_int:
                        if c not in df.columns:
                            df[c] = 0
                        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)

                    # Cálculos automáticos de diferencias y totales
                    df['Esquejes_Recibidos'] = df['Esquejes_Recepcion']
                    df['Total_Disponible'] = df['Stock_Cuarto_Frio'] + df['Esquejes_Recepcion'] - df['Bajas_Descartes']
                    df['Diferencia_Recepcion'] = df['Esquejes_Recepcion'] - df['Esquejes_Requeridos']
                    df['Esquejes_Efectivos_Clavar'] = df.apply(calcular_esquejes_efectivos_clavar, axis=1)
                    df['Diferencia_Saldo'] = df['Total_Disponible'] - df['Esquejes_Efectivos_Clavar']
                    df['Remanente_Final'] = df['Diferencia_Saldo'].apply(lambda x: max(0, x))
                    df['Bandejas_112_Disponibles'] = df['Esquejes_Efectivos_Clavar'].apply(calcular_bandejas_redondeadas)
                    df['Estado_Disponibilidad'] = df.apply(calcular_estado_disponibilidad, axis=1)

                    for c in cols_str:
                        if c in df.columns:
                            df[c] = df[c].fillna("").astype(str)

                    cols_order = [
                        "Semana_Enraizamiento", "Fecha_Ingreso", "Flor", "Color", "Variedad",
                        "Stock_Cuarto_Frio", "Esquejes_Recepcion", "Bajas_Descartes",
                        "Total_Disponible", "Esquejes_Requeridos", "Diferencia_Recepcion",
                        "Compensacion_Volumen", "Reprogramado_Siguiente_Semana", "Esquejes_Efectivos_Clavar",
                        "Diferencia_Saldo", "Bandejas_112_Disponibles", "Remanente_Final",
                        "Estado_Disponibilidad", "Estado_Aprobacion", "Observaciones"
                    ]
                    cols_final = [c for c in cols_order if c in df.columns]
                    return df[cols_final]
        except Exception:
            pass

    return pd.DataFrame(columns=[
        "Semana_Enraizamiento", "Fecha_Ingreso", "Flor", "Color", "Variedad",
        "Stock_Cuarto_Frio", "Esquejes_Recepcion", "Bajas_Descartes",
        "Total_Disponible", "Esquejes_Requeridos", "Diferencia_Recepcion",
        "Compensacion_Volumen", "Reprogramado_Siguiente_Semana", "Esquejes_Efectivos_Clavar",
        "Diferencia_Saldo", "Bandejas_112_Disponibles", "Remanente_Final",
        "Estado_Disponibilidad", "Estado_Aprobacion", "Observaciones"
    ])

# Alias para compatibilidad con código existente
cargar_inventario_lunes = cargar_inventario_recepcion


def guardar_inventario_recepcion(df_inventario_semana: pd.DataFrame, semana_enraizamiento: str = None) -> bool:
    """
    Guarda o actualiza los registros de inventario (Cuarto Frío + Recepción - Bajas + Compensación)
    en Recepcion_Inventario_Esquejes.csv y sincroniza Inventario_Esquejes_Lunes.csv.
    """
    if df_inventario_semana is None or df_inventario_semana.empty:
        return False
    try:
        df_copy = df_inventario_semana.copy()
        sem = str(semana_enraizamiento) if semana_enraizamiento else str(df_copy['Semana_Enraizamiento'].iloc[0])
        df_copy['Semana_Enraizamiento'] = sem

        # Normalizar nombres Recepción / Recibidos
        if 'Esquejes_Recepcion' not in df_copy.columns and 'Esquejes_Recibidos' in df_copy.columns:
            df_copy['Esquejes_Recepcion'] = df_copy['Esquejes_Recibidos']
        elif 'Esquejes_Recibidos' not in df_copy.columns and 'Esquejes_Recepcion' in df_copy.columns:
            df_copy['Esquejes_Recibidos'] = df_copy['Esquejes_Recepcion']
        
        # Conversión y recálculo de campos numéricos
        cols_num = [
            "Stock_Cuarto_Frio", "Esquejes_Recepcion", "Esquejes_Recibidos", "Bajas_Descartes",
            "Total_Disponible", "Esquejes_Requeridos", "Diferencia_Recepcion", "Compensacion_Volumen",
            "Reprogramado_Siguiente_Semana", "Esquejes_Efectivos_Clavar", "Diferencia_Saldo",
            "Bandejas_112_Disponibles", "Esquejes_Clavados_Reales", "Remanente_Final"
        ]
        for cn in cols_num:
            if cn not in df_copy.columns:
                df_copy[cn] = 0
            df_copy[cn] = pd.to_numeric(df_copy[cn], errors='coerce').fillna(0).astype(int)

        df_copy['Esquejes_Recibidos'] = df_copy['Esquejes_Recepcion']
        df_copy['Total_Disponible'] = df_copy['Stock_Cuarto_Frio'] + df_copy['Esquejes_Recepcion'] - df_copy['Bajas_Descartes']
        df_copy['Diferencia_Recepcion'] = df_copy['Esquejes_Recepcion'] - df_copy['Esquejes_Requeridos']
        df_copy['Esquejes_Efectivos_Clavar'] = df_copy.apply(calcular_esquejes_efectivos_clavar, axis=1)
        df_copy['Diferencia_Saldo'] = df_copy['Total_Disponible'] - df_copy['Esquejes_Efectivos_Clavar']
        df_copy['Remanente_Final'] = df_copy['Diferencia_Saldo'].apply(lambda x: max(0, x))
        df_copy['Bandejas_112_Disponibles'] = df_copy['Esquejes_Efectivos_Clavar'].apply(calcular_bandejas_redondeadas)
        df_copy['Estado_Disponibilidad'] = df_copy.apply(calcular_estado_disponibilidad, axis=1)

        cols_str = ["Semana_Enraizamiento", "Fecha_Ingreso", "Flor", "Color", "Variedad", "Estado_Disponibilidad", "Estado_Aprobacion", "Observaciones"]
        for c in cols_str:
            if c in df_copy.columns:
                df_copy[c] = df_copy[c].fillna("").astype(str)

        cols_order = [
            "Semana_Enraizamiento", "Fecha_Ingreso", "Flor", "Color", "Variedad",
            "Stock_Cuarto_Frio", "Esquejes_Recepcion", "Bajas_Descartes",
            "Total_Disponible", "Esquejes_Requeridos", "Diferencia_Recepcion",
            "Compensacion_Volumen", "Reprogramado_Siguiente_Semana", "Esquejes_Efectivos_Clavar",
            "Diferencia_Saldo", "Bandejas_112_Disponibles", "Remanente_Final",
            "Estado_Disponibilidad", "Estado_Aprobacion", "Observaciones"
        ]
        cols_final = [c for c in cols_order if c in df_copy.columns]
        df_to_save = df_copy[cols_final]

        for arch in [ARCHIVO_INVENTARIO_RECEPCION, ARCHIVO_INVENTARIO_LUNES]:
            if os.path.exists(arch):
                try:
                    df_existente = pd.read_csv(arch)
                    df_existente['Semana_Enraizamiento'] = df_existente['Semana_Enraizamiento'].astype(str)
                    df_otras = df_existente[df_existente['Semana_Enraizamiento'] != sem]
                    df_final = pd.concat([df_otras, df_to_save], ignore_index=True)
                except Exception:
                    df_final = df_to_save
            else:
                df_final = df_to_save
            df_final.to_csv(arch, index=False, encoding='utf-8')

        # Sincronizar automáticamente con Plan_Aprobado_Detallado.csv para mantener alineada la proyección de 52 semanas
        try:
            sincronizar_plan_detallado_con_inventario_ajustado(sem, df_to_save)
        except Exception:
            pass

        return True
    except Exception as e:
        print(f"Error al guardar inventario recepción: {e}")
        return False

# Alias para compatibilidad con código existente
guardar_inventario_lunes = guardar_inventario_recepcion


def precargar_inventario_desde_plano(res_plano: dict) -> pd.DataFrame:
    """
    Genera la plantilla base de inventario disponible (Cuarto Frío + Recepción - Bajas),
    a partir de las variedades y requerimientos calculados en el plano operativo de la semana.
    Arrastra automáticamente el saldo remanente de cuarto frío de la semana anterior si existe,
    e incorpora faltantes que hayan sido reprogramados de semanas anteriores.
    """
    df_det = res_plano.get('df_plano_detallado', pd.DataFrame())
    if df_det.empty:
        return pd.DataFrame()
    
    sem_e = str(res_plano.get('semana_enraizamiento', '202643'))
    today_str = date.today().strftime('%Y-%m-%d')

    grp = df_det.groupby(['Flor', 'Color', 'Variedad']).agg(
        Esquejes_Requeridos=('Esquejes', 'sum')
    ).reset_index()

    grp['Semana_Enraizamiento'] = sem_e
    grp['Fecha_Ingreso'] = today_str

    # Arrastrar remanente de la semana previa automáticamente
    sem_ant = restar_semanas_iso(sem_e, 1)
    remanentes_previos = {}
    reprogramados_previos = {}
    for arch in [ARCHIVO_INVENTARIO_RECEPCION, ARCHIVO_CIERRE_ENRAIZAMIENTO, ARCHIVO_INVENTARIO_LUNES]:
        if os.path.exists(arch):
            try:
                df_hist = pd.read_csv(arch)
                df_ant = df_hist[df_hist['Semana_Enraizamiento'].astype(str) == str(sem_ant)]
                if not df_ant.empty:
                    for _, r_a in df_ant.iterrows():
                        v = str(r_a.get('Variedad', '')).strip()
                        rem = int(pd.to_numeric(r_a.get('Remanente_Final', r_a.get('Diferencia_Saldo', 0)), errors='coerce') or 0)
                        rep = int(pd.to_numeric(r_a.get('Reprogramado_Siguiente_Semana', 0), errors='coerce') or 0)
                        if rem > 0:
                            remanentes_previos[v] = max(remanentes_previos.get(v, 0), rem)
                        if rep > 0:
                            reprogramados_previos[v] = max(reprogramados_previos.get(v, 0), rep)
                    break
            except Exception:
                pass

    grp['Stock_Cuarto_Frio'] = grp['Variedad'].apply(lambda v: remanentes_previos.get(str(v).strip(), 0))
    # Incorporar reprogramaciones de la semana anterior a la demanda
    reprog_prev = grp['Variedad'].apply(lambda v: reprogramados_previos.get(str(v).strip(), 0))
    grp['Esquejes_Requeridos'] = grp['Esquejes_Requeridos'] + reprog_prev

    grp['Esquejes_Recepcion'] = grp['Esquejes_Requeridos']
    grp['Esquejes_Recibidos'] = grp['Esquejes_Recepcion']
    grp['Bajas_Descartes'] = 0
    grp['Total_Disponible'] = grp['Stock_Cuarto_Frio'] + grp['Esquejes_Recepcion'] - grp['Bajas_Descartes']
    grp['Diferencia_Recepcion'] = 0
    grp['Compensacion_Volumen'] = 0
    grp['Reprogramado_Siguiente_Semana'] = 0
    grp['Esquejes_Efectivos_Clavar'] = grp['Esquejes_Requeridos']
    grp['Diferencia_Saldo'] = grp['Total_Disponible'] - grp['Esquejes_Efectivos_Clavar']
    grp['Remanente_Final'] = grp['Diferencia_Saldo'].apply(lambda x: max(0, x))
    grp['Bandejas_112_Disponibles'] = grp['Esquejes_Efectivos_Clavar'].apply(calcular_bandejas_redondeadas)
    grp['Esquejes_Clavados_Reales'] = 0
    grp['Estado_Disponibilidad'] = "🟢 Completo (100%)"
    grp['Estado_Aprobacion'] = "Pendiente Aprobación"
    grp['Observaciones'] = "Ingreso lote estándar"

    cols_order = [
        "Semana_Enraizamiento", "Fecha_Ingreso", "Flor", "Color", "Variedad",
        "Stock_Cuarto_Frio", "Esquejes_Recepcion", "Bajas_Descartes",
        "Total_Disponible", "Esquejes_Requeridos", "Diferencia_Recepcion",
        "Compensacion_Volumen", "Reprogramado_Siguiente_Semana", "Esquejes_Efectivos_Clavar",
        "Diferencia_Saldo", "Bandejas_112_Disponibles", "Remanente_Final",
        "Estado_Disponibilidad", "Estado_Aprobacion", "Observaciones"
    ]
    return grp[cols_order]


def calcular_semana_siembra_desde_enraizamiento(sem_enraizamiento_str: str) -> str:
    """
    Calcula la semana ISO de siembra a campo a partir de la semana de enraizamiento.
    Regla agronómica: 3 semanas bajo cámara de nebulización / bancos (Sem_Siembra = Sem_Enraizamiento + 3).
    """
    try:
        s_clean = str(sem_enraizamiento_str).replace('S', '').strip()
        y = int(s_clean[:4])
        w = int(s_clean[4:])
        dt = date.fromisocalendar(y, w, 1) + timedelta(weeks=3)
        return isocalendar_to_string(dt)
    except Exception:
        return str(sem_enraizamiento_str)


def absorber_excedentes_inventario_a_campo(
    df_inventario: pd.DataFrame,
    semana_enraizamiento: str,
    db: Session = None,
    max_exceso_pct: float = 0.10
) -> tuple[pd.DataFrame, list[dict]]:
    """
    Evalúa los excedentes de inventario físico disponibles en cuarto frío / recepción.
    Si alcanzan el mínimo agronómico de media cama (≥2,500 esquejes / ≥23 bandejas de 112)
    y existe espacio libre en campo en la semana de siembra (S+3) sin sobrepasar el techo de
    1,120 camas comerciales post-reducción (ni exceder el límite de mercado de +10% sobre el plan aprobado),
    incorpora ese excedente al plan de enraizamiento para ser sembrado y cosechado.
    """
    if df_inventario is None or df_inventario.empty:
        return df_inventario, []

    df = df_inventario.copy()
    advertencias = []

    sem_siembra = calcular_semana_siembra_desde_enraizamiento(semana_enraizamiento)
    disp_campo = consultar_camas_disponibles_campo(sem_siembra, db=db)
    camas_libres_disponibles = float(disp_campo.get('camas_libres', 0.0))
    cap_techo = float(disp_campo.get('capacidad_techo', 1120.0))
    camas_ocupadas = float(disp_campo.get('camas_ocupadas', 0.0))
    es_pico_saturado = bool(disp_campo.get('es_pico_saturado', False))

    for idx in df.index:
        var = str(df.loc[idx, 'Variedad']).strip()
        disp = int(pd.to_numeric(df.loc[idx, 'Total_Disponible'], errors='coerce') or 0)
        efect = int(pd.to_numeric(df.loc[idx, 'Esquejes_Efectivos_Clavar'], errors='coerce') or 0)
        req = int(pd.to_numeric(df.loc[idx, 'Esquejes_Requeridos'], errors='coerce') or 0)

        saldo_remanente = disp - efect
        if saldo_remanente < MINIMO_COMPENSACION_ESQUEJES:
            continue

        # Si el campo está saturado al 100% en pico
        if es_pico_saturado or camas_libres_disponibles < 0.5:
            advertencias.append({
                'Nivel': '🔵 Excedente en Frío (Campo al 100%)',
                'Tipo': 'info',
                'Mensaje': (
                    f"[{var}] tiene +{saldo_remanente:,d} esquejes de excedente ({saldo_remanente/5200.0:.1f} camas), "
                    f"pero el campo en Sem {sem_siembra} está al 100% de capacidad ({camas_ocupadas:.0f}/{cap_techo:.0f} camas). "
                    f"Se resguarda en cuarto frío para proteger el techo de la finca y evitar sobrecupo."
                )
            })
            continue

        # Verificar límite de mercado (+10% del requerimiento comercial)
        if req > 0:
            tope_mercado = int(round(req * max_exceso_pct))
            tope_adicional = max(2600, tope_mercado)
        else:
            tope_adicional = 5200  # Variedad extemporánea: 1 cama completa si hay espacio

        absorbible = min(saldo_remanente, tope_adicional)
        if absorbible >= 5200:
            absorbible = (absorbible // 5200) * 5200
        elif absorbible >= 2600:
            absorbible = 2600
        else:
            absorbible = 0

        if absorbible >= MINIMO_COMPENSACION_ESQUEJES:
            camas_add = round(absorbible / 5200.0, 1)
            if camas_add <= camas_libres_disponibles:
                # Absorber a siembra efectiva
                df.loc[idx, 'Compensacion_Volumen'] = int(df.loc[idx, 'Compensacion_Volumen']) + absorbible
                df.loc[idx, 'Esquejes_Efectivos_Clavar'] = efect + absorbible
                df.loc[idx, 'Bandejas_112_Disponibles'] = calcular_bandejas_redondeadas(df.loc[idx, 'Esquejes_Efectivos_Clavar'])
                df.loc[idx, 'Diferencia_Saldo'] = df.loc[idx, 'Total_Disponible'] - df.loc[idx, 'Esquejes_Efectivos_Clavar']
                df.loc[idx, 'Remanente_Final'] = max(0, df.loc[idx, 'Diferencia_Saldo'])
                df.loc[idx, 'Estado_Disponibilidad'] = f"🟢 Excedente Aprovechado (+{absorbible:,d} esq / {camas_add:.1f} cam)"

                camas_libres_disponibles = max(0.0, round(camas_libres_disponibles - camas_add, 1))
                advertencias.append({
                    'Nivel': '🟢 Excedente Aprovechado',
                    'Tipo': 'success',
                    'Mensaje': (
                        f"Excedente de inventario de {absorbible:,d} esquejes ({camas_add:.1f} camas / {calcular_bandejas_redondeadas(absorbible):,d} bandejas) "
                        f"en [{var}] agregado al plan de enraizamiento para siembra en Sem {sem_siembra}. "
                        f"Espacio libre restante en campo: {camas_libres_disponibles:.1f} camas (Techo: {cap_techo:.0f} camas)."
                    )
                })

    return df, advertencias


def sincronizar_plan_detallado_con_inventario_ajustado(
    semana_enraizamiento: str,
    df_inventario: pd.DataFrame,
    detailed_file: str = "Plan_Aprobado_Detallado.csv",
    db = None
) -> bool:
    """
    Sincroniza Plan_Aprobado_Detallado.csv con los esquejes efectivos a clavar y camas
    resultantes del ajuste de inventario y absorción de excedentes para esa semana.
    Asegura que los módulos de Siembras, ForeCast a 52 semanas y Ocupación operen
    con la información 100% viva y unificada.
    """
    if df_inventario is None or df_inventario.empty or not os.path.exists(detailed_file):
        return False
    try:
        sem_e = str(semana_enraizamiento).strip().replace("S", "")
        df_det = pd.read_csv(detailed_file)
        if 'Semana_Enraizamiento' not in df_det.columns or 'Variedad' not in df_det.columns:
            return False

        df_det['Sem_Enr_Clean'] = df_det['Semana_Enraizamiento'].astype(str).str.replace('S', '').str.strip()
        df_det['Var_Norm'] = df_det['Variedad'].astype(str).str.strip().str.lower()

        for _, row in df_inventario.iterrows():
            var_norm = str(row['Variedad']).strip().lower()
            esq_efect = int(pd.to_numeric(row.get('Esquejes_Efectivos_Clavar', 0), errors='coerce') or 0)
            if esq_efect <= 0:
                continue

            camas_calc = round(esq_efect / 5200.0, 1)
            mask = (df_det['Sem_Enr_Clean'] == sem_e) & (df_det['Var_Norm'] == var_norm)
            if mask.any():
                idx = df_det[mask].index[0]
                aprov = float(df_det.at[idx, 'Aprov_PP']) if 'Aprov_PP' in df_det.columns and pd.notna(df_det.at[idx, 'Aprov_PP']) else 0.835
                df_det.at[idx, 'Esquejes'] = esq_efect
                df_det.at[idx, 'Camas'] = camas_calc
                if 'Tallos_Esperados' in df_det.columns:
                    df_det.at[idx, 'Tallos_Esperados'] = int(round(esq_efect * aprov))

        df_det = df_det.drop(columns=['Sem_Enr_Clean', 'Var_Norm'], errors='ignore')
        df_det.to_csv(detailed_file, index=False)
        return True
    except Exception as e:
        print(f"Error sincronizando Plan_Aprobado_Detallado con inventario: {e}")
        return False


def ejecutar_compensacion_inventario(
    df_inventario: pd.DataFrame,
    semana_enraizamiento: str = None,
    absorber_excedentes_a_campo: bool = True,
    db: Session = None
) -> tuple[pd.DataFrame, list[dict]]:
    """
    Aplica la regla de compensación jerárquica agronómica de la empresa:
    1. Regla Agronómica de Mínimo Media Cama (≥0.5 camas / ≥2,500 esquejes / ≥23 bandejas):
       - Si la compensación entre dos variedades no es de al menos media cama (≥2,500 esquejes), NO SE COMPENSA.
       - No se permite fraccionar camas con micro-lotes ("llenar las camas de mil variedades").
       - El volumen transferido se modula en múltiplos de media cama (0.5 camas = 2,600 esquejes) o cama completa (1.0 cama = 5,200),
         evitando sobrepasar la capacidad de las camas o generar cantidades irreales de siembra en campo.
    2. Jerarquía de compensación:
       - Nivel 1 (Flor-Color): Buscar variedades donantes con excedente ≥ media cama que compartan MISMO TIPO DE FLOR y MISMO COLOR.
       - Nivel 2 (Color): Si aún queda déficit ≥ media cama, buscar variedades donantes con excedente ≥ media cama que compartan
         MISMO COLOR (independiente de la flor).
       - Nivel 3 (Reprogramación):
         * Si déficit > 500 esquejes pero < 2,500 esquejes: No alcanza media cama; se reprograma para el plan de la siguiente semana (+1w)
           sin partir camas.
         * Si déficit ≥ 2,500 esquejes y no hubo donante viable: Se reprograma para el plan de la siguiente semana (+1w).
         * Si déficit ≤ 500 esquejes: Es despreciable (absorbido por variación de densidad en campo y buffer).
    Retorna el DataFrame con compensaciones calculadas y una lista estructurada de advertencias operativas.
    """
    if df_inventario is None or df_inventario.empty:
        return df_inventario, []

    df = df_inventario.copy()

    # Asegurar tipos numéricos
    cols_num = ["Stock_Cuarto_Frio", "Esquejes_Recepcion", "Bajas_Descartes", "Esquejes_Requeridos"]
    for c in cols_num:
        if c not in df.columns:
            df[c] = 0
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)

    df['Total_Disponible'] = df['Stock_Cuarto_Frio'] + df['Esquejes_Recepcion'] - df['Bajas_Descartes']
    df['Saldo_Preliminar'] = df['Total_Disponible'] - df['Esquejes_Requeridos']
    df['Compensacion_Volumen'] = 0
    df['Reprogramado_Siguiente_Semana'] = 0

    # Variedades con excedente disponible (incluye variedades programadas y extemporáneas con saldo > 0)
    surplus = {idx: int(val) for idx, val in df[df['Saldo_Preliminar'] > 0]['Saldo_Preliminar'].items()}
    # Variedades con déficit (Saldo_Preliminar < 0)
    deficits = {idx: abs(int(val)) for idx, val in df[df['Saldo_Preliminar'] < 0]['Saldo_Preliminar'].items()}

    advertencias = []

    # Nivel 1: Mismo Flor y Mismo Color (Solo si needed >= MINIMO_COMPENSACION_ESQUEJES)
    for d_idx, needed in list(deficits.items()):
        if needed < MINIMO_COMPENSACION_ESQUEJES:
            continue
        f_d = str(df.loc[d_idx, 'Flor']).strip()
        c_d = str(df.loc[d_idx, 'Color']).strip()
        var_d = str(df.loc[d_idx, 'Variedad']).strip()

        for s_idx, sur_val in list(surplus.items()):
            if sur_val < MINIMO_COMPENSACION_ESQUEJES or s_idx == d_idx:
                continue
            f_s = str(df.loc[s_idx, 'Flor']).strip()
            c_s = str(df.loc[s_idx, 'Color']).strip()

            if f_s.lower() == f_d.lower() and c_s.lower() == c_d.lower():
                var_s = str(df.loc[s_idx, 'Variedad']).strip()
                transfer = calcular_transferencia_compensacion(needed, sur_val)
                if transfer < MINIMO_COMPENSACION_ESQUEJES:
                    continue

                surplus[s_idx] -= transfer
                needed -= transfer
                df.loc[d_idx, 'Compensacion_Volumen'] -= transfer
                df.loc[s_idx, 'Compensacion_Volumen'] += transfer

                es_extemp = int(df.loc[s_idx, 'Esquejes_Requeridos']) == 0
                tag_extemp = " (Variedad Extemporánea / No Programada)" if es_extemp else ""
                camas_eq = transfer / float(ESQUEJES_POR_CAMA_ESTANDAR)
                ban_eq = calcular_bandejas_redondeadas(transfer)

                advertencias.append({
                    'Nivel': '🟢 Flor-Color',
                    'Tipo': 'success',
                    'Mensaje': (
                        f"Déficit de {transfer:,d} esquejes ({camas_eq:.1f} camas / {ban_eq:,d} bandejas) en [{var_d}] "
                        f"compensado aumentando volumen de [{var_s}]{tag_extemp} ({f_d} - {c_d}). "
                        f"Cumple regla de mínimo media cama."
                    )
                })
                if needed < MINIMO_COMPENSACION_ESQUEJES:
                    break
        deficits[d_idx] = needed

    # Nivel 2: Mismo Color (diferente flor si aún queda déficit >= MINIMO_COMPENSACION_ESQUEJES)
    for d_idx, needed in list(deficits.items()):
        if needed < MINIMO_COMPENSACION_ESQUEJES:
            continue
        c_d = str(df.loc[d_idx, 'Color']).strip()
        var_d = str(df.loc[d_idx, 'Variedad']).strip()

        for s_idx, sur_val in list(surplus.items()):
            if sur_val < MINIMO_COMPENSACION_ESQUEJES or s_idx == d_idx:
                continue
            c_s = str(df.loc[s_idx, 'Color']).strip()

            if c_s.lower() == c_d.lower():
                var_s = str(df.loc[s_idx, 'Variedad']).strip()
                f_s = str(df.loc[s_idx, 'Flor']).strip()
                transfer = calcular_transferencia_compensacion(needed, sur_val)
                if transfer < MINIMO_COMPENSACION_ESQUEJES:
                    continue

                surplus[s_idx] -= transfer
                needed -= transfer
                df.loc[d_idx, 'Compensacion_Volumen'] -= transfer
                df.loc[s_idx, 'Compensacion_Volumen'] += transfer

                es_extemp = int(df.loc[s_idx, 'Esquejes_Requeridos']) == 0
                tag_extemp = " (Variedad Extemporánea / Suple Color)" if es_extemp else ""
                camas_eq = transfer / float(ESQUEJES_POR_CAMA_ESTANDAR)
                ban_eq = calcular_bandejas_redondeadas(transfer)

                advertencias.append({
                    'Nivel': '🟡 Mismo Color',
                    'Tipo': 'warning',
                    'Mensaje': (
                        f"Déficit de {transfer:,d} esquejes ({camas_eq:.1f} camas / {ban_eq:,d} bandejas) en [{var_d}] "
                        f"compensado aumentando volumen de [{var_s}]{tag_extemp} (Mismo Color: {c_d}, Flor: {f_s}). "
                        f"Cumple regla de mínimo media cama."
                    )
                })
                if needed < MINIMO_COMPENSACION_ESQUEJES:
                    break
        deficits[d_idx] = needed

    # Nivel 3: Reprogramación para la siguiente semana (+1w) y Tratamiento de Diferencias Menores
    # REGLAS DEL NEGOCIO:
    # 1. Si needed > UMBRAL_DIFERENCIA_DESPRECIABLE (500):
    #    - Si needed < MINIMO_COMPENSACION_ESQUEJES (2,500): No alcanza media cama; no se fracciona cama y pasa a siguiente semana.
    #    - Si needed >= MINIMO_COMPENSACION_ESQUEJES (2,500): Déficit crítico no compensado; pasa a siguiente semana.
    # 2. Si 0 < needed <= 500: Es despreciable (absorbido por margen de densidad).
    for d_idx, needed in list(deficits.items()):
        var_d = str(df.loc[d_idx, 'Variedad']).strip()
        if needed > UMBRAL_DIFERENCIA_DESPRECIABLE:
            df.loc[d_idx, 'Reprogramado_Siguiente_Semana'] = needed
            camas_reprog = needed / float(ESQUEJES_POR_CAMA_ESTANDAR)
            ban_reprog = calcular_bandejas_redondeadas(needed)

            if needed < MINIMO_COMPENSACION_ESQUEJES:
                advertencias.append({
                    'Nivel': '🔴 Reprogramado (+1w)',
                    'Tipo': 'error',
                    'Mensaje': (
                        f"Faltante de {needed:,d} esquejes ({camas_reprog:.2f} camas / {ban_reprog:,d} bandejas) en [{var_d}] "
                        f"no alcanza el mínimo agronómico de media cama (≥2,500 esquejes). No se compensa para evitar fraccionar "
                        f"camas con micro-lotes ('llenar las camas de mil variedades'); se reprograma para el plan de la siguiente semana."
                    )
                })
            else:
                advertencias.append({
                    'Nivel': '🔴 Reprogramado (+1w)',
                    'Tipo': 'error',
                    'Mensaje': (
                        f"Faltante crítico de {needed:,d} esquejes ({camas_reprog:.1f} camas / {ban_reprog:,d} bandejas) en [{var_d}] "
                        f"(≥media cama) no encontró excedentes compatibles viables (≥2,500 esquejes). Se reprograma para el plan de la siguiente semana."
                    )
                })
        elif needed > 0:
            advertencias.append({
                'Nivel': '⚪ En Tolerancia (≤500)',
                'Tipo': 'info',
                'Mensaje': (
                    f"Diferencia de {needed:,d} esquejes en [{var_d}] (≤500 esquejes) es despreciable "
                    f"y se absorbe por el margen de densidad de siembra en campo."
                )
            })

    # Recalcular valores preliminares
    df['Esquejes_Efectivos_Clavar'] = df.apply(calcular_esquejes_efectivos_clavar, axis=1)
    df['Diferencia_Saldo'] = df['Total_Disponible'] - df['Esquejes_Efectivos_Clavar']
    df['Remanente_Final'] = df['Diferencia_Saldo'].apply(lambda x: max(0, x))
    df['Bandejas_112_Disponibles'] = df['Esquejes_Efectivos_Clavar'].apply(calcular_bandejas_redondeadas)
    df['Estado_Disponibilidad'] = df.apply(calcular_estado_disponibilidad, axis=1)

    # Nivel 4: Absorción Productiva de Excedentes Restantes a Campo si hay espacio físico (<1,120 camas)
    if absorber_excedentes_a_campo and semana_enraizamiento:
        df, adv_abs = absorber_excedentes_inventario_a_campo(df, semana_enraizamiento, db=db)
        advertencias.extend(adv_abs)

    return df, advertencias


def generar_resumen_excedentes_flor_color(df_inventario: pd.DataFrame) -> pd.DataFrame:
    """
    Genera el cuadro resumen consolidado de excedentes agrupado por Flor y Color.
    Aplica la regla agronómica de media cama (≥ 2,500 esquejes / 23 bandejas de 112):
    - Excedentes ≥ 2,500 esquejes (≥0.5 camas): Viables para compensar faltantes o sembrar en campo.
    - Excedentes < 2,500 esquejes (<0.5 camas): Remanente que permanece resguardado en cuarto frío
      para evitar fraccionar camas con micro-lotes ("no podemos llenar las camas de mil variedades").
    """
    if df_inventario is None or df_inventario.empty:
        return pd.DataFrame()

    df = df_inventario.copy()

    # Asegurar columnas numéricas
    for c in ["Total_Disponible", "Esquejes_Requeridos", "Compensacion_Volumen", "Reprogramado_Siguiente_Semana", "Remanente_Final", "Diferencia_Saldo"]:
        if c not in df.columns:
            df[c] = 0
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)

    # Identificar excedente físico por fila y donaciones
    df['Excedente_Fisico'] = (df['Total_Disponible'] - df['Esquejes_Requeridos']).apply(lambda x: max(0, x))
    df['Donado_Compensacion'] = df['Compensacion_Volumen'].apply(lambda x: max(0, x))

    # Filtrar únicamente filas que tengan algún excedente físico, donación o remanente
    df_exc = df[(df['Excedente_Fisico'] > 0) | (df['Donado_Compensacion'] > 0) | (df['Remanente_Final'] > 0)].copy()
    if df_exc.empty:
        return pd.DataFrame(columns=[
            "Flor", "Color", "Flor_Color", "Num_Variedades", "Variedades_Aportantes",
            "Esquejes_Requeridos", "Total_Disponible", "Excedente_Total",
            "Bandejas_112_Excedente", "Camas_Eq_Excedente",
            "Compensado_Donado", "Remanente_Cuarto_Frio", "Bandejas_112_Remanente", "Camas_Eq_Remanente",
            "Clasificacion_Agronomica", "Accion_Sugerida"
        ])

    rows = []
    for (flor, color), g in df_exc.groupby(['Flor', 'Color']):
        flor_str = str(flor).strip()
        color_str = str(color).strip()
        flor_color_label = f"{flor_str} - {color_str}"

        req_tot = int(g['Esquejes_Requeridos'].sum())
        disp_tot = int(g['Total_Disponible'].sum())
        exc_tot = int(g['Excedente_Fisico'].sum())
        comp_tot = int(g['Donado_Compensacion'].sum())
        rem_tot = int(g['Remanente_Final'].sum())

        ban_exc = calcular_bandejas_redondeadas(exc_tot)
        cam_exc = round(exc_tot / float(ESQUEJES_POR_CAMA_ESTANDAR), 1)

        ban_rem = calcular_bandejas_redondeadas(rem_tot)
        cam_rem = round(rem_tot / float(ESQUEJES_POR_CAMA_ESTANDAR), 1)

        # Variedades aportantes formateadas con su volumen
        vars_info = []
        for _, r in g.iterrows():
            v_name = str(r['Variedad']).strip()
            v_exc = int(r['Excedente_Fisico'])
            v_rem = int(r['Remanente_Final'])
            v_comp = int(r['Donado_Compensacion'])
            if v_rem > 0:
                vars_info.append(f"{v_name} (Saldo: +{v_rem:,d})")
            elif v_comp > 0:
                vars_info.append(f"{v_name} (Aportó: {v_comp:,d})")
            elif v_exc > 0:
                vars_info.append(f"{v_name} (+{v_exc:,d})")

        var_desc = ", ".join(vars_info) if vars_info else str(len(g))

        # Clasificación agronómica según regla de media cama
        if rem_tot >= MINIMO_COMPENSACION_ESQUEJES:
            clasif = "🟢 Excedente Viable (≥0.5 cam)"
            accion = "Disponible para compensar faltantes de color o programar cama adicional"
        elif rem_tot > UMBRAL_DIFERENCIA_DESPRECIABLE:
            clasif = "🔵 Remanente Frío (<0.5 cam)"
            accion = "Resguardar en cuarto frío como inventario (no parte camas)"
        elif rem_tot > 0:
            clasif = "⚪ En Tolerancia (≤500)"
            accion = "Absorbido por variación de densidad en campo"
        elif comp_tot > 0:
            clasif = "🟡 100% Compensado"
            accion = "Volumen donado para compensar faltantes compatibles"
        else:
            clasif = "🟢 Nivelado (100%)"
            accion = "Volumen en equilibrio"

        rows.append({
            "Flor": flor_str,
            "Color": color_str,
            "Flor_Color": flor_color_label,
            "Num_Variedades": len(g),
            "Variedades_Aportantes": var_desc,
            "Esquejes_Requeridos": req_tot,
            "Total_Disponible": disp_tot,
            "Excedente_Total": exc_tot,
            "Bandejas_112_Excedente": ban_exc,
            "Camas_Eq_Excedente": cam_exc,
            "Compensado_Donado": comp_tot,
            "Remanente_Cuarto_Frio": rem_tot,
            "Bandejas_112_Remanente": ban_rem,
            "Camas_Eq_Remanente": cam_rem,
            "Clasificacion_Agronomica": clasif,
            "Accion_Sugerida": accion
        })

    df_resumen = pd.DataFrame(rows)
    if not df_resumen.empty:
        df_resumen = df_resumen.sort_values(by=["Remanente_Cuarto_Frio", "Excedente_Total"], ascending=False).reset_index(drop=True)
    return df_resumen


def aprobar_ejecucion_y_descontar_inventario(
    semana_enraizamiento: str,
    df_ejecucion_semana: pd.DataFrame,
    df_inventario_semana: pd.DataFrame
) -> dict:
    """
    Aprueba la ejecución real de clavado y descuenta automáticamente los esquejes reales
    del inventario disponible de la semana. Guarda el Remanente_Final y lo transfiere
    automáticamente como Stock_Cuarto_Frio de la siguiente semana (+1w).
    """
    if df_inventario_semana is None or df_inventario_semana.empty:
        return {"exito": False, "mensaje": "Inventario vacío"}
    
    try:
        sem = str(semana_enraizamiento)
        sem_sig = sumar_semanas_iso(sem, 1)

        df_inv = df_inventario_semana.copy()
        df_ej = df_ejecucion_semana.copy() if df_ejecucion_semana is not None else pd.DataFrame()

        # Calcular esquejes reales clavados por variedad
        ejec_por_var = {}
        if not df_ej.empty and 'Variedad' in df_ej.columns and 'Esquejes_Reales' in df_ej.columns:
            ejec_por_var = df_ej.groupby('Variedad')['Esquejes_Reales'].sum().to_dict()

        for idx in df_inv.index:
            var = str(df_inv.loc[idx, 'Variedad']).strip()
            clavados = int(ejec_por_var.get(var, df_inv.loc[idx, 'Esquejes_Efectivos_Clavar']))
            tot_disp = int(df_inv.loc[idx, 'Total_Disponible'])
            rem_final = max(0, tot_disp - clavados)
            df_inv.loc[idx, 'Esquejes_Clavados_Reales'] = clavados
            df_inv.loc[idx, 'Remanente_Final'] = rem_final
            df_inv.loc[idx, 'Estado_Aprobacion'] = "✅ Aprobado y Descontado"

        # Guardar en archivo de inventario y cierre
        guardar_inventario_recepcion(df_inv, semana_enraizamiento=sem)
        
        # Guardar en Cierre_Semanal_Enraizamiento.csv
        if os.path.exists(ARCHIVO_CIERRE_ENRAIZAMIENTO):
            try:
                df_cierre = pd.read_csv(ARCHIVO_CIERRE_ENRAIZAMIENTO)
                df_cierre['Semana_Enraizamiento'] = df_cierre['Semana_Enraizamiento'].astype(str)
                df_otras = df_cierre[df_cierre['Semana_Enraizamiento'] != sem]
                df_cierre_final = pd.concat([df_otras, df_inv], ignore_index=True)
            except Exception:
                df_cierre_final = df_inv
        else:
            df_cierre_final = df_inv
        df_cierre_final.to_csv(ARCHIVO_CIERRE_ENRAIZAMIENTO, index=False, encoding='utf-8')

        # Rollover a la siguiente semana: Si ya existe en Recepcion_Inventario_Esquejes.csv, actualizar Stock_Cuarto_Frio
        if os.path.exists(ARCHIVO_INVENTARIO_RECEPCION):
            try:
                df_rec = pd.read_csv(ARCHIVO_INVENTARIO_RECEPCION)
                df_rec['Semana_Enraizamiento'] = df_rec['Semana_Enraizamiento'].astype(str)
                mask_sig = df_rec['Semana_Enraizamiento'] == str(sem_sig)
                if mask_sig.any():
                    remanentes_dict = df_inv.set_index('Variedad')['Remanente_Final'].to_dict()
                    for idx_r in df_rec[mask_sig].index:
                        v = str(df_rec.loc[idx_r, 'Variedad']).strip()
                        if v in remanentes_dict:
                            df_rec.loc[idx_r, 'Stock_Cuarto_Frio'] = remanentes_dict[v]
                            df_rec.loc[idx_r, 'Total_Disponible'] = df_rec.loc[idx_r, 'Stock_Cuarto_Frio'] + df_rec.loc[idx_r, 'Esquejes_Recepcion'] - df_rec.loc[idx_r, 'Bajas_Descartes']
                    df_rec.to_csv(ARCHIVO_INVENTARIO_RECEPCION, index=False, encoding='utf-8')
            except Exception:
                pass

        tot_clav = int(df_inv['Esquejes_Clavados_Reales'].sum())
        tot_rem = int(df_inv['Remanente_Final'].sum())
        return {
            "exito": True,
            "total_clavado": tot_clav,
            "total_remanente": tot_rem,
            "semana_siguiente": sem_sig,
            "df_inv_actualizado": df_inv
        }
    except Exception as e:
        return {"exito": False, "mensaje": str(e)}


def cargar_ejecucion_real(semana_enraizamiento: str = None) -> pd.DataFrame:
    """
    Carga los registros de ejecución real de clavado/enraizamiento desde Ejecucion_Real_Enraizamiento.csv.
    Si se especifica semana_enraizamiento, filtra por esa semana y sanea tipos de datos.
    """
    cols_str = ["Semana_Enraizamiento", "Dia_Clavado", "Fecha_Clavado", "Flor", "Color", "Variedad", "Bloque_Destino", "Semana_Siembra_Proyectada", "Estado", "Observaciones"]
    cols_int = ["Bandejas_Programadas", "Esquejes_Programados", "Bandejas_Reales", "Esquejes_Reales"]
    cols_float = ["Camas_Reales", "Cumplimiento_Pct"]

    if os.path.exists(ARCHIVO_EJECUCION_REAL):
        try:
            df = pd.read_csv(ARCHIVO_EJECUCION_REAL)
            if df is not None and not df.empty:
                df['Semana_Enraizamiento'] = df['Semana_Enraizamiento'].astype(str)
                if semana_enraizamiento:
                    df = df[df['Semana_Enraizamiento'] == str(semana_enraizamiento)].copy()
                for c in cols_str:
                    if c in df.columns:
                        df[c] = df[c].fillna("").astype(str)
                for c in cols_int:
                    if c in df.columns:
                        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
                for c in cols_float:
                    if c in df.columns:
                        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0).astype(float)
                return df
        except Exception:
            pass
    return pd.DataFrame(columns=[
        "Semana_Enraizamiento", "Dia_Clavado", "Fecha_Clavado", "Flor", "Color",
        "Variedad", "Bloque_Destino", "Bandejas_Programadas", "Esquejes_Programados",
        "Bandejas_Reales", "Esquejes_Reales", "Camas_Reales",
        "Cumplimiento_Pct", "Semana_Siembra_Proyectada", "Estado", "Observaciones"
    ])


def guardar_ejecucion_real(df_ejecucion_semana: pd.DataFrame, semana_enraizamiento: str = None) -> bool:
    """
    Guarda o actualiza la ejecución real de enraizamiento en Ejecucion_Real_Enraizamiento.csv.
    Mantiene intactos los registros de las demás semanas.
    """
    if df_ejecucion_semana is None or df_ejecucion_semana.empty:
        return False
    try:
        df_copy = df_ejecucion_semana.copy()
        sem = str(semana_enraizamiento) if semana_enraizamiento else str(df_copy['Semana_Enraizamiento'].iloc[0])
        df_copy['Semana_Enraizamiento'] = sem
        
        if 'Bandejas_Reales' in df_copy.columns:
            df_copy['Bandejas_Reales'] = pd.to_numeric(df_copy['Bandejas_Reales'], errors='coerce').fillna(0).astype(int)
            df_copy['Esquejes_Reales'] = df_copy['Bandejas_Reales'] * CAVIDADES_POR_BANDEJA
            
        if 'Bandejas_Programadas' in df_copy.columns:
            df_copy['Bandejas_Programadas'] = pd.to_numeric(df_copy['Bandejas_Programadas'], errors='coerce').fillna(0).astype(int)

        if 'Esquejes_Programados' in df_copy.columns and 'Esquejes_Reales' in df_copy.columns:
            df_copy['Esquejes_Programados'] = pd.to_numeric(df_copy['Esquejes_Programados'], errors='coerce').fillna(0).astype(int)
            def calc_cumpl(row):
                prog = row.get('Esquejes_Programados', 0)
                real = row.get('Esquejes_Reales', 0)
                return round((real / prog * 100.0), 1) if prog > 0 else 100.0
            df_copy['Cumplimiento_Pct'] = df_copy.apply(calc_cumpl, axis=1)

        if 'Semana_Siembra_Proyectada' not in df_copy.columns or df_copy['Semana_Siembra_Proyectada'].isna().any():
            df_copy['Semana_Siembra_Proyectada'] = sumar_semanas_iso(sem, SEMANAS_ENRAIZAMIENTO)

        if os.path.exists(ARCHIVO_EJECUCION_REAL):
            try:
                df_existente = pd.read_csv(ARCHIVO_EJECUCION_REAL)
                df_existente['Semana_Enraizamiento'] = df_existente['Semana_Enraizamiento'].astype(str)
                df_otras = df_existente[df_existente['Semana_Enraizamiento'] != sem]
                df_final = pd.concat([df_otras, df_copy], ignore_index=True)
            except Exception:
                df_final = df_copy
        else:
            df_final = df_copy
            
        df_final.to_csv(ARCHIVO_EJECUCION_REAL, index=False, encoding='utf-8')
        return True
    except Exception as e:
        print(f"Error al guardar ejecucion real: {e}")
        return False


def precargar_ejecucion_desde_plano(res_plano: dict) -> pd.DataFrame:
    """
    Genera la planilla base para captura del ejecutado real,
    precargando los lotes programados desde el plano operativo semanal.
    """
    df_det = res_plano.get('df_plano_detallado', pd.DataFrame())
    if df_det.empty:
        return pd.DataFrame()

    sem_e = str(res_plano.get('semana_enraizamiento', '202643'))
    sem_s = str(res_plano.get('semana_siembra', sumar_semanas_iso(sem_e, SEMANAS_ENRAIZAMIENTO)))
    today_str = date.today().strftime('%Y-%m-%d')

    rows = []
    for _, r in df_det.iterrows():
        b_prog = int(r.get('Bandejas_112', 0))
        e_prog = int(r.get('Esquejes', 0))
        c_campo = float(r.get('Camas_Campo', 1.0))
        
        rows.append({
            "Semana_Enraizamiento": sem_e,
            "Dia_Clavado": str(r.get('Dia_Programado', 'Lunes')),
            "Fecha_Clavado": today_str,
            "Flor": str(r.get('Flor', 'Standard')),
            "Color": str(r.get('Color', 'Mix')),
            "Variedad": str(r.get('Variedad', '')),
            "Bloque_Destino": str(r.get('Bloque_Destino', 'Bloque 01')),
            "Bandejas_Programadas": b_prog,
            "Esquejes_Programados": e_prog,
            "Bandejas_Reales": 0,
            "Esquejes_Reales": 0,
            "Camas_Reales": 0.0,
            "Cumplimiento_Pct": 0.0,
            "Semana_Siembra_Proyectada": str(r.get('Semana_Siembra', sem_s)),
            "Estado": "🔴 Pendiente",
            "Observaciones": ""
        })
    return pd.DataFrame(rows)
