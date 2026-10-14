import os
import glob
import re
import pandas as pd
from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.models import Ubicacion, Siembra, Variedad, EstadoSiembra, CapacidadBloque
from app.core.database import Base, engine
from app.services.forecast_service import isocalendar_to_string

# Constantes Maestras de la Finca
AREA_PRODUCTIVA_TOTAL_M2 = 61878.0   # Área comercial productiva real
CAMAS_COMERCIALES_TOTALES = 1168.0   # Camas en bloques 01 a 06
CAMAS_INV_TOTALES = 48.0             # Bloque INV (Investigación)
CAMAS_TOTALES_INSTALADAS = 1216.0    # 1,168 comerciales + 48 INV
ANCHO_CAMA_M = 1.20
LARGO_CAMA_M = 30.00
AREA_NETA_CAMA_M2 = ANCHO_CAMA_M * LARGO_CAMA_M  # 36.0 m2

META_TALLOS_M2_ANUAL = 265.0         # Meta de productividad anual (apuntando a mejor aprovechamiento)
PLAN_TALLOS_ANUAL_DEFAULT = 15800000.0 # Plan asignado anual aproximado
CICLOS_ANUALES_PROMEDIO = 3.5        # Rotación promedio anual de la finca

def encontrar_archivo_planos_seccion() -> str:
    """Encuentra el archivo de Planos sección independientemente de la codificación de tildes."""
    candidatos = glob.glob("Planos secci*.csv") + glob.glob("*plano*secci*.csv")
    if candidatos:
        return candidatos[0]
    if os.path.exists("Planos sección.csv"):
        return "Planos sección.csv"
    return "Planos seccion.csv"

def inicializar_o_cargar_capacidad(db: Session) -> pd.DataFrame:
    """
    Inicializa o sincroniza la tabla 'capacidad_bloques' a partir de 'Planos sección.csv'.
    Calcula el área productiva normalizada a 61,878 m2 para los bloques comerciales (01 a 06)
    y separa el bloque INV como Investigación (2,835.02 m2).
    """
    # Asegurar que la tabla exista en la base de datos
    Base.metadata.create_all(bind=engine, tables=[CapacidadBloque.__table__])

    archivo_plano = encontrar_archivo_planos_seccion()
    if not os.path.exists(archivo_plano):
        # Fallback a datos maestros conocidos si el archivo no estuviera en ruta
        datos_default = [
            {"bloque": "INV", "naves": 8, "camas": 48, "area_bruta_m2": 2835.024, "es_comercial": False, "obs": "Investigación / I+D"},
            {"bloque": "01", "naves": 30, "camas": 240, "area_bruta_m2": 14070.0, "es_comercial": True, "obs": "Comercial"},
            {"bloque": "02", "naves": 27, "camas": 160, "area_bruta_m2": 9450.08, "es_comercial": True, "obs": "Comercial"},
            {"bloque": "03", "naves": 25, "camas": 184, "area_bruta_m2": 11154.856, "es_comercial": True, "obs": "Comercial"},
            {"bloque": "04", "naves": 29, "camas": 232, "area_bruta_m2": 12744.456, "es_comercial": True, "obs": "Comercial"},
            {"bloque": "05", "naves": 20, "camas": 160, "area_bruta_m2": 8326.4, "es_comercial": True, "obs": "Comercial"},
            {"bloque": "06", "naves": 24, "camas": 192, "area_bruta_m2": 9902.016, "es_comercial": True, "obs": "Comercial"},
        ]
        df_raw = pd.DataFrame(datos_default)
    else:
        try:
            df_raw = pd.read_csv(archivo_plano, encoding='latin1')
        except Exception:
            df_raw = pd.read_csv(archivo_plano, encoding='utf-8')

        # Limpiar nombres de columnas
        col_map = {}
        for c in df_raw.columns:
            clean = str(c).replace('"', '').strip().lower()
            if 'bloque' in clean:
                col_map[c] = 'bloque'
            elif 'nave' in clean:
                col_map[c] = 'naves'
            elif 'cama' in clean:
                col_map[c] = 'camas'
            elif 'rea' in clean or 'm2' in clean:
                col_map[c] = 'area_bruta_m2'
        df_raw = df_raw.rename(columns=col_map)

    # Limpieza numérica y tipado
    df_raw['bloque'] = df_raw['bloque'].astype(str).str.replace('"', '').str.strip()
    df_raw['naves'] = pd.to_numeric(df_raw['naves'].astype(str).str.replace('"', ''), errors='coerce').fillna(0).astype(int)
    df_raw['camas'] = pd.to_numeric(df_raw['camas'].astype(str).str.replace('"', ''), errors='coerce').fillna(0).astype(int)
    df_raw['area_bruta_m2'] = pd.to_numeric(df_raw['area_bruta_m2'].astype(str).str.replace('"', ''), errors='coerce').fillna(0.0)

    # Normalización del área productiva
    # Bloques comerciales 01 a 06 deben totalizar exactamente AREA_PRODUCTIVA_TOTAL_M2 (61,878 m2)
    mask_comercial = df_raw['bloque'].str.upper() != 'INV'
    tot_bruta_comercial = df_raw.loc[mask_comercial, 'area_bruta_m2'].sum()
    if tot_bruta_comercial > 0:
        factor_prod = AREA_PRODUCTIVA_TOTAL_M2 / tot_bruta_comercial
    else:
        factor_prod = 1.0

    records_to_db = []
    for _, row in df_raw.iterrows():
        b_name = row['bloque']
        es_com = (b_name.upper() != 'INV')
        bruta = float(row['area_bruta_m2'])
        if es_com:
            prod = round(bruta * factor_prod, 2)
            obs = "Bloque Comercial"
        else:
            prod = round(bruta, 2)
            obs = "Bloque de Investigación (I+D / Pruebas / Madres)"

        records_to_db.append({
            'bloque': b_name,
            'naves': int(row['naves']),
            'camas': int(row['camas']),
            'area_bruta_m2': bruta,
            'area_productiva_m2': prod,
            'es_comercial': es_com,
            'observaciones': obs
        })

    # Guardar / Actualizar en DB
    for r in records_to_db:
        cb = db.query(CapacidadBloque).filter(CapacidadBloque.bloque == r['bloque']).first()
        if not cb:
            cb = CapacidadBloque(
                sede="CH",
                bloque=r['bloque'],
                naves=r['naves'],
                camas=r['camas'],
                area_bruta_m2=r['area_bruta_m2'],
                area_productiva_m2=r['area_productiva_m2'],
                es_comercial=r['es_comercial'],
                observaciones=r['observaciones']
            )
            db.add(cb)
        else:
            cb.naves = r['naves']
            cb.camas = r['camas']
            cb.area_bruta_m2 = r['area_bruta_m2']
            cb.area_productiva_m2 = r['area_productiva_m2']
            cb.es_comercial = r['es_comercial']
            cb.observaciones = r['observaciones']

    db.commit()
    return pd.DataFrame(records_to_db)

def obtener_estado_ocupacion_actual(db: Session) -> pd.DataFrame:
    """
    Compara las siembras vivas actuales (en producción) contra la capacidad física
    de cada bloque, identificando camas ocupadas y camas libres hoy.
    """
    inicializar_o_cargar_capacidad(db)
    bloques_cap = db.query(CapacidadBloque).order_by(CapacidadBloque.bloque).all()

    # Contar siembras vivas actuales por bloque
    # Normalizar códigos de bloque (ej. '1.0' -> '01')
    siembras_vivas = db.query(Siembra).filter(Siembra.estado == EstadoSiembra.EN_PRODUCCION).all()
    conteo_vivas = {}
    area_vivas = {}

    for s in siembras_vivas:
        b_raw = str(s.ubicacion.bloque if s.ubicacion else '').replace('.0', '').strip()
        if len(b_raw) == 1 and b_raw.isdigit():
            b_norm = f"0{b_raw}"
        else:
            b_norm = b_raw.upper()

        conteo_vivas[b_norm] = conteo_vivas.get(b_norm, 0) + 1
        area_vivas[b_norm] = area_vivas.get(b_norm, 0.0) + (s.area_m2 if s.area_m2 else 0.0)

    rows = []
    for b in bloques_cap:
        b_key = b.bloque
        camas_cap = b.camas
        vivas_cnt = conteo_vivas.get(b_key, 0)
        libres_cnt = max(0, camas_cap - vivas_cnt)
        pct_occ = (vivas_cnt / camas_cap * 100.0) if camas_cap > 0 else 0.0

        area_prod = b.area_productiva_m2
        area_occ = round((area_prod / camas_cap * vivas_cnt), 2) if camas_cap > 0 else 0.0
        area_lib = round(max(0.0, area_prod - area_occ), 2)

        rows.append({
            "Bloque": b_key,
            "Uso": "Comercial" if b.es_comercial else "Investigación",
            "Naves": b.naves,
            "Camas_Capacidad": camas_cap,
            "Camas_Ocupadas_Hoy": vivas_cnt,
            "Camas_Libres_Hoy": libres_cnt,
            "Ocupacion_%": round(pct_occ, 1),
            "Area_Productiva_m2": area_prod,
            "Area_Ocupada_m2": area_occ,
            "Area_Libre_m2": area_lib
        })

    return pd.DataFrame(rows)

def calcular_ocupacion_semanal_52w(db: Session, start_date: date = None) -> tuple:
    """
    Calcula la curva dinámica de ocupación semana a semana para las 52 semanas.
    Integra:
    1. Inventario vivo en campo (semanas de vegetativo, cosecha y 1 semana de descanso post-corte).
    2. Siembras futuras requeridas por el Plan de Producción MVA.
    
    Retorna:
    - df_semanal: DataFrame con semanas, camas ocupadas, área ocupada, % ocupación y estado.
    - df_bloques_semanal: Detalle de ocupación desglosado por Bloque semana a semana.
    """
    if not start_date:
        start_date = date.today()

    semana_actual = isocalendar_to_string(start_date)

    # 1. Calendario de las 52 semanas
    semanas_lista = []
    d_iter = start_date - timedelta(weeks=2) # Incluir 2 semanas hacia atrás
    for _ in range(54):
        semanas_lista.append(isocalendar_to_string(d_iter))
        d_iter += timedelta(days=7)

    # 2. Rastrear permanencia en cama del inventario vivo
    # Cada cama viva permanece ocupada: fecha_siembra hasta (fecha_siembra + dia_inicio + 14 dias corte + 7 dias preparacion)
    siembras_vivas = db.query(Siembra).filter(Siembra.estado == EstadoSiembra.EN_PRODUCCION).all()
    ocupacion_matrix = {s: {'total_camas': 0, 'total_area': 0.0, 'por_bloque': {}} for s in semanas_lista}

    for b_code in ['01', '02', '03', '04', '05', '06', 'INV']:
        for s in semanas_lista:
            ocupacion_matrix[s]['por_bloque'][b_code] = 0

    m2_por_cama_prom = AREA_PRODUCTIVA_TOTAL_M2 / CAMAS_COMERCIALES_TOTALES # ~52.98 m2

    for siembra in siembras_vivas:
        var = siembra.variedad
        ubi = siembra.ubicacion
        dia_ini = var.dia_inicio if (var and var.dia_inicio and var.dia_inicio > 0) else 84
        
        # Duración: días a inicio + 14 días de cosecha + 7 días (1 semana) de rotación/descanso de suelo
        dias_permanencia = dia_ini + 21
        f_siem = siembra.fecha_siembra
        f_fin_rotacion = f_siem + timedelta(days=dias_permanencia)

        b_raw = str(ubi.bloque if ubi else '').replace('.0', '').strip()
        b_norm = f"0{b_raw}" if (len(b_raw) == 1 and b_raw.isdigit()) else b_raw.upper()
        if not b_norm or b_norm not in ocupacion_matrix[semanas_lista[0]]['por_bloque']:
            b_norm = '01'

        # Marcar semanas ocupadas
        f_check = f_siem
        while f_check <= f_fin_rotacion:
            sem_str = isocalendar_to_string(f_check)
            if sem_str in ocupacion_matrix:
                ocupacion_matrix[sem_str]['total_camas'] += 1
                ocupacion_matrix[sem_str]['total_area'] += (siembra.area_m2 if siembra.area_m2 else m2_por_cama_prom)
                ocupacion_matrix[sem_str]['por_bloque'][b_norm] += 1
            f_check += timedelta(days=7)

    # 3. Integrar las siembras futuras requeridas por el Plan MVA / Temporadas
    # Cargar Plan Consolidado si existe
    archivo_plan = "Plan_Aprobado.csv"
    if not os.path.exists(archivo_plan):
        archivo_plan = "Consolidado_Plan_MVA.xlsx"

    df_plan_futuro = pd.DataFrame()
    if os.path.exists(archivo_plan):
        try:
            if archivo_plan.endswith('.csv'):
                df_plan_futuro = pd.read_csv(archivo_plan)
            else:
                df_plan_futuro = pd.read_excel(archivo_plan)
        except Exception:
            pass

    # Si hay plan futuro, mapear la ocupación generada por las siembras futuras
    # Para cosechar en semana_cosecha, la cama debió sembrarse 12 semanas antes y permanece 13 semanas
    if not df_plan_futuro.empty:
        col_sem = [c for c in df_plan_futuro.columns if 'semana' in str(c).lower()]
        col_tallos = [c for c in df_plan_futuro.columns if any(k in str(c).lower() for k in ['suma', 'tallos pedidos', 'capacidad', 'tallos'])]
        
        if col_sem and col_tallos:
            cs = col_sem[0]
            ct = col_tallos[0]
            df_plan_clean = df_plan_futuro.dropna(subset=[cs, ct]).copy()
            df_plan_clean['Sem_Str'] = df_plan_clean[cs].astype(str).str.replace('.0', '', regex=False).str.strip()
            df_plan_clean['Tallos_Num'] = pd.to_numeric(df_plan_clean[ct], errors='coerce').fillna(0)

            # Agrupar tallos por semana de cosecha futura
            plan_by_sem = df_plan_clean.groupby('Sem_Str')['Tallos_Num'].sum().to_dict()

            # Estimar camas requeridas por semana de siembra
            # ~3,950 tallos exportables por cama
            for sem_cos, tallos in plan_by_sem.items():
                if sem_cos > semana_actual and tallos > 0:
                    camas_req = round(tallos / 3950.0)
                    
                    # Convertir semana de cosecha a fecha aproximada para restar semanas de siembra
                    try:
                        y_c = int(sem_cos[:4])
                        w_c = int(sem_cos[4:])
                        f_pico = date.fromisocalendar(y_c, w_c, 4)
                        f_siem_futura = f_pico - timedelta(weeks=12)
                        f_fin_futura = f_siem_futura + timedelta(weeks=13)

                        f_chk = f_siem_futura
                        while f_chk <= f_fin_futura:
                            sem_s = isocalendar_to_string(f_chk)
                            if sem_s in ocupacion_matrix and sem_s > semana_actual:
                                # Solo sumamos si el inventario vivo ya se está liberando para no duplicar
                                camas_vivas_en_sem = ocupacion_matrix[sem_s]['total_camas']
                                if camas_vivas_en_sem < CAMAS_COMERCIALES_TOTALES:
                                    camas_a_sumar = min(camas_req, int(CAMAS_COMERCIALES_TOTALES - camas_vivas_en_sem))
                                    ocupacion_matrix[sem_s]['total_camas'] += camas_a_sumar
                                    ocupacion_matrix[sem_s]['total_area'] += (camas_a_sumar * m2_por_cama_prom)
                            f_chk += timedelta(days=7)
                    except Exception:
                        pass

    # 4. Formatear resultados finales
    res_semanal = []
    bloques_detalle = []

    def clasificar_temporada(sem_int):
        if 202640 <= sem_int <= 202646:
            return "Fall 2026"
        elif 202647 <= sem_int <= 202653:
            return "Navidad 2026"
        elif 202701 <= sem_int <= 202705:
            return "San Valentín 2027 (Pico)"
        elif 202706 <= sem_int <= 202714:
            return "Pascua / Post-Valentin"
        elif 202715 <= sem_int <= 202718:
            return "Madres 2027 (Pico)"
        elif 202719 <= sem_int <= 202735:
            return "Summer 2027 (Valle Baja Demanda)"
        elif sem_int >= 202736:
            return "Fall / Invierno 2027"
        return "Regular"

    for sem in sorted(semanas_lista):
        info = ocupacion_matrix[sem]
        c_occ = min(int(CAMAS_COMERCIALES_TOTALES), info['total_camas'])
        c_lib = max(0, int(CAMAS_COMERCIALES_TOTALES) - c_occ)
        pct_occ = round((c_occ / CAMAS_COMERCIALES_TOTALES) * 100.0, 1)

        area_occ = round(c_occ * m2_por_cama_prom, 1)
        area_lib = round(max(0.0, AREA_PRODUCTIVA_TOTAL_M2 - area_occ), 1)

        sem_int = int(sem) if sem.isdigit() else 202640
        temp = clasificar_temporada(sem_int)

        if pct_occ >= 98.0:
            estado = "🔴 SATURACIÓN / SOBRECUPO"
        elif pct_occ >= 85.0:
            estado = "🟢 ÓPTIMO (85%-95%)"
        else:
            estado = "🟡 VALLE / SUBOCUPADO"

        res_semanal.append({
            "Semana": sem,
            "Semana_Num": sem,
            "Temporada": temp,
            "Camas_Ocupadas": c_occ,
            "Camas_Libres": c_lib,
            "Ocupacion_%": pct_occ,
            "Area_Ocupada_m2": area_occ,
            "Area_Libre_m2": area_lib,
            "Estado_Capacidad": estado
        })

        # Detalle por bloques
        for b_code, b_camas in info['por_bloque'].items():
            bloques_detalle.append({
                "Semana": sem,
                "Bloque": b_code,
                "Camas_Ocupadas": b_camas
            })

    return pd.DataFrame(res_semanal), pd.DataFrame(bloques_detalle)

def calcular_balanceo_estacional(df_semanal: pd.DataFrame, meta_tallos_m2: float = META_TALLOS_M2_ANUAL) -> dict:
    """
    Analiza el desempeño estacional de la finca frente a la meta de 265 tallos/m2 (16.4M tallos)
    y genera las recomendaciones de optimización para picos (Madres/Valentín) y valles (Summer).
    """
    res_por_temporada = []
    
    # Agrupar por temporada
    for temp, grp in df_semanal.groupby("Temporada"):
        sems_cnt = len(grp)
        prom_occ_camas = grp["Camas_Ocupadas"].mean()
        prom_occ_pct = grp["Ocupacion_%"].mean()
        prom_area_occ = grp["Area_Ocupada_m2"].mean()
        prom_area_lib = grp["Area_Libre_m2"].mean()
        camas_libres_prom = grp["Camas_Libres"].mean()

        # Tallos estimados producidos en la temporada a 3.5 ciclos y meta 265 tallos/m2
        tallos_temp_est = (prom_area_occ * meta_tallos_m2 * (sems_cnt / 52.0))

        res_por_temporada.append({
            "Temporada": temp,
            "Semanas_Duracion": sems_cnt,
            "Camas_Ocupadas_Prom": round(prom_occ_camas, 1),
            "Camas_Libres_Prom": round(camas_libres_prom, 1),
            "Ocupacion_%": round(prom_occ_pct, 1),
            "Area_Ocupada_m2": round(prom_area_occ, 1),
            "Area_Libre_m2": round(prom_area_lib, 1),
            "Tallos_Proyectados": int(round(tallos_temp_est))
        })

    df_temp_summary = pd.DataFrame(res_por_temporada).sort_values(by="Temporada")

    # Diagnóstico de Picos y Summer
    recomendaciones = []
    
    # Summer
    row_summer = df_temp_summary[df_temp_summary['Temporada'].str.contains('Summer', case=False, na=False)]
    if not row_summer.empty:
        camas_lib_summer = row_summer['Camas_Libres_Prom'].iloc[0]
        area_lib_summer = row_summer['Area_Libre_m2'].iloc[0]
        recomendaciones.append({
            "Tipo": "Estrategia Summer (Valle de Baja Demanda)",
            "Diagnostico": f"Durante las 17 semanas de Summer se liberan en promedio {camas_lib_summer:.0f} camas (~{area_lib_summer:,.0f} m² desocupados).",
            "Accion_Optima": "Concentrar siembras en Bloques 01, 02 y 05 al 100%, y PROGRAMAR PARADA TOTAL de los Bloques 03 y 04 para solarización profunda del suelo y mantenimiento mayor de riego, ahorrando costos de iluminación nocturna y jornales."
        })

    # San Valentín y Madres
    recomendaciones.append({
        "Tipo": "Estrategia Picos (San Valentín y Madres)",
        "Diagnostico": "La demanda de las semanas pico supera la capacidad instantánea si se concentra en 3 semanas.",
        "Accion_Optima": "Aplicar Suavizado de Siembras (Planting Smoothing): Escalonar un 20% de las siembras de pico hacia semanas previas (S-1 y S-2) utilizando variedades con mayor vida en florero y almacenamiento en frío para cosechar sin superar las 1,168 camas comerciales."
    })

    return {
        "df_temporadas": df_temp_summary,
        "recomendaciones": recomendaciones,
        "kpis_maestros": {
            "area_productiva_m2": AREA_PRODUCTIVA_TOTAL_M2,
            "camas_comerciales": int(CAMAS_COMERCIALES_TOTALES),
            "camas_inv": int(CAMAS_INV_TOTALES),
            "meta_tallos_m2": META_TALLOS_M2_ANUAL,
            "meta_tallos_anual": int(AREA_PRODUCTIVA_TOTAL_M2 * META_TALLOS_M2_ANUAL),
            "ciclos_anuales": CICLOS_ANUALES_PROMEDIO,
            "dimensiones_cama": f"{ANCHO_CAMA_M} m x {LARGO_CAMA_M} m ({AREA_NETA_CAMA_M2} m² netos)"
        }
    }
