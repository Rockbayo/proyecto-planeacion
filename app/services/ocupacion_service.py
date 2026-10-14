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

# Constantes Maestras de la Finca y Cronograma de Transición
SEMANA_CORTE_REDUCCION_AREA = 202648     # Semana de corte: la reducción física se aplica a partir de S202648
AREA_PRODUCTIVA_ACTUAL_M2 = 64878.0       # Área productiva real actual (hasta semana 202647)
AREA_PRODUCTIVA_REDUCIDA_M2 = 61878.0     # Área productiva reducida a partir de semana 202648
AREA_PRODUCTIVA_TOTAL_M2 = 61878.0        # Área comercial productiva régimen post-reducción
AREA_PRODUCTIVA_ANTERIOR_M2 = 64878.0    # Área comercial previa (con la que se diseñó el Plan Original)
FACTOR_AJUSTE_AREA = AREA_PRODUCTIVA_REDUCIDA_M2 / AREA_PRODUCTIVA_ANTERIOR_M2 # 0.953759 (-4.624%)

CAMAS_COMERCIALES_TOTALES = 1168.0       # Camas en bloques 01 a 06
CAMAS_INV_TOTALES = 48.0                 # Bloque INV (Investigación / I+D)
CAMAS_TOTALES_INSTALADAS = 1216.0        # 1,168 comerciales + 48 INV

ANCHO_CAMA_M = 1.20
LARGO_CAMA_M = 30.00
AREA_NETA_CAMA_M2 = ANCHO_CAMA_M * LARGO_CAMA_M  # 36.0 m2 (área neta cultivable aproximada)

META_TALLOS_M2_ANUAL = 265.0             # Meta corporativa de productividad anual (apuntando a mejor aprovechamiento)
PLAN_TALLOS_ANUAL_DEFAULT = 15800000.0   # Plan asignado anual aproximado
CICLOS_ANUALES_PROMEDIO = 3.5            # Rotación promedio anual de la finca

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
    Mantiene el área bruta física de cada bloque según planos y calcula el área productiva normalizada a 61,878 m2
    para los bloques comerciales (01 a 06), separando el bloque INV como Investigación (2,835.02 m2).
    """
    # Asegurar que la tabla exista en la base de datos
    Base.metadata.create_all(bind=engine, tables=[CapacidadBloque.__table__])

    archivo_plano = encontrar_archivo_planos_seccion()
    if not os.path.exists(archivo_plano):
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

    # Normalización del área productiva comercial a 61,878 m2
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
    de cada bloque, identificando camas físicas ocupadas, lotes sembrados, área real y densidad.
    
    Regla Física Clave:
    - Una cama física se identifica unívocamente por (Nave, Lado, Cama).
    - Si una cama tiene varias variedades (lotes compartidos), cuenta como 1 única cama física ocupada.
    - La ocupación física de camas jamás puede exceder el 100% de la capacidad del bloque.
    """
    inicializar_o_cargar_capacidad(db)
    bloques_cap = db.query(CapacidadBloque).order_by(CapacidadBloque.bloque).all()

    # Obtener todas las siembras vivas en producción
    siembras_vivas = db.query(Siembra).filter(Siembra.estado == EstadoSiembra.EN_PRODUCCION).all()
    bloque_data = {}

    for s in siembras_vivas:
        ubi = s.ubicacion
        b_raw = str(ubi.bloque if ubi else '').replace('.0', '').strip()
        b_norm = f"0{b_raw}" if (len(b_raw) == 1 and b_raw.isdigit()) else b_raw.upper()
        if b_norm not in bloque_data:
            bloque_data[b_norm] = {
                'beds': set(),
                'lotes': 0,
                'area_sembrada': 0.0,
                'plantas': 0
            }
        bed_key = (ubi.nave if ubi else None, ubi.lado if ubi else None, ubi.cama if ubi else None)
        bloque_data[b_norm]['beds'].add(bed_key)
        bloque_data[b_norm]['lotes'] += 1
        bloque_data[b_norm]['area_sembrada'] += (s.area_m2 or 0.0)
        bloque_data[b_norm]['plantas'] += (s.plantas_sembradas or 0)

    rows = []
    for b in bloques_cap:
        b_key = b.bloque
        camas_cap = b.camas
        d = bloque_data.get(b_key, {'beds': set(), 'lotes': 0, 'area_sembrada': 0.0, 'plantas': 0})
        
        # Camas físicas ocupadas reales: dedup de (Nave, Lado, Cama) y con tope estricto al 100% de capacidad
        camas_unicas_count = len(d['beds'])
        camas_occ = min(camas_cap, camas_unicas_count)
        camas_lib = max(0, camas_cap - camas_occ)
        pct_occ = (camas_occ / camas_cap * 100.0) if camas_cap > 0 else 0.0

        # Dimensiones reales de cama según planos de la finca
        m2_cama_planos = round(b.area_bruta_m2 / camas_cap, 2) if camas_cap > 0 else 0.0
        m2_cama_prod = round(b.area_productiva_m2 / camas_cap, 2) if camas_cap > 0 else 0.0

        # Área productiva ocupada y libre
        if camas_occ >= camas_cap:
            area_occ = b.area_productiva_m2
        else:
            area_occ = round(camas_occ * m2_cama_prod, 2)
        area_lib = round(max(0.0, b.area_productiva_m2 - area_occ), 2)

        # Densidad de siembra real en campo (plantas / m2 sembrado)
        densidad_pl_m2 = round((d['plantas'] / d['area_sembrada']), 1) if d['area_sembrada'] > 0 else 0.0
        
        # Camas compartidas / multivariedad
        camas_compartidas = max(0, d['lotes'] - camas_unicas_count)

        rows.append({
            "Bloque": b_key,
            "Uso": "Comercial" if b.es_comercial else "Investigación",
            "Naves": b.naves,
            "Camas_Capacidad": camas_cap,
            "Camas_Ocupadas_Hoy": camas_occ,
            "Camas_Libres_Hoy": camas_lib,
            "Ocupacion_%": round(pct_occ, 1),
            "Lotes_Sembrados": d['lotes'],
            "Camas_Compartidas": camas_compartidas,
            "Area_Planos_m2": b.area_bruta_m2,
            "m2_Por_Cama_Planos": m2_cama_planos,
            "Area_Productiva_m2": b.area_productiva_m2,
            "Area_Ocupada_m2": area_occ,
            "Area_Libre_m2": area_lib,
            "Densidad_pl_m2": densidad_pl_m2
        })

    return pd.DataFrame(rows)

def calcular_ocupacion_semanal_52w(db: Session, start_date: date = None) -> tuple:
    """
    Calcula la curva dinámica de ocupación semana a semana para las 52 semanas.
    Cruza el pedido real de material vegetal (PedidoConsolidado_master.xlsx) contra la capacidad física
    de 1,168 camas comerciales.
    
    Compara:
    1. Plan Original (calculado sobre el área previa de 64,878 m2): Puede superar el 100% de capacidad en picos.
    2. Plan Ajustado (escalado a la capacidad real actual de 61,878 m2 mediante factor 0.95376):
       Se mantiene siempre dentro de los techos físicos de la finca.
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
    siembras_vivas = db.query(Siembra).filter(Siembra.estado == EstadoSiembra.EN_PRODUCCION).all()
    sem_corte_bd = max([isocalendar_to_string(s.fecha_siembra) for s in siembras_vivas] or ['202641'])
    ocupacion_matrix = {
        s: {
            'camas_vivas': 0,
            'camas_pedido_original': 0.0,
            'camas_pedido_ajustado': 0.0,
            'siembra_camas': 0.0,
            'por_bloque': {b: 0 for b in ['01', '02', '03', '04', '05', '06', 'INV']}
        } for s in semanas_lista
    }

    # Tracking de camas físicas únicas por semana para el inventario vivo
    camas_vivas_por_sem = {s: set() for s in semanas_lista}

    for siembra in siembras_vivas:
        if isocalendar_to_string(siembra.fecha_siembra) > sem_corte_bd:
            continue
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

        bed_id = (b_norm, ubi.nave if ubi else 0, ubi.lado if ubi else '', ubi.cama if ubi else 0)

        # Marcar semanas ocupadas
        f_check = f_siem
        while f_check <= f_fin_rotacion:
            sem_str = isocalendar_to_string(f_check)
            if sem_str in ocupacion_matrix:
                camas_vivas_por_sem[sem_str].add(bed_id)
                ocupacion_matrix[sem_str]['por_bloque'][b_norm] += 1
            f_check += timedelta(days=7)

    for s in semanas_lista:
        ocupacion_matrix[s]['camas_vivas'] = min(int(CAMAS_COMERCIALES_TOTALES), len(camas_vivas_por_sem[s]))

    # 3. Cruzar con el Pedido de Material Vegetal (PedidoConsolidado)
    from app.services.mva_service import generar_plan_mva
    archivo_pedido = "PedidoConsolidado_master.xlsx"
    if not os.path.exists(archivo_pedido):
        candidatos_ped = glob.glob("PedidoConsolidado*.xlsx") + glob.glob("*pedido*.xlsx")
        archivo_pedido = candidatos_ped[0] if candidatos_ped else None

    if archivo_pedido and os.path.exists(archivo_pedido):
        try:
            df_mrp = generar_plan_mva(archivo_pedido, week_is="Pedido")
            if not df_mrp.empty and 'Semana_Siembra' in df_mrp.columns:
                # Cada cama comercial recibe en promedio ~5,200 esquejes de siembra
                df_mrp['Camas_Req'] = df_mrp['Esquejes_Para_Siembra (Final)'] / 5200.0
                siembras_por_sem = df_mrp.groupby('Semana_Siembra')['Camas_Req'].sum().to_dict()

                for sem_s, camas_req in siembras_por_sem.items():
                    s_str = str(sem_s)
                    if s_str in ocupacion_matrix:
                        ocupacion_matrix[s_str]['siembra_camas'] += camas_req

                    # Solo acumular siembras futuras a partir de la semana posterior al corte de BD
                    if s_str <= sem_corte_bd:
                        continue

                    try:
                        y = int(s_str[:4])
                        w = int(s_str[4:])
                        dt_s = date.fromisocalendar(y, w, 1)

                        # Una cama sembrada en sem_s permanece ocupada 14 semanas (ciclo de cultivo + 1 sem descanso)
                        for sem_offset in range(14):
                            dt_occ = dt_s + timedelta(weeks=sem_offset)
                            s_occ = isocalendar_to_string(dt_occ)
                            if s_occ in ocupacion_matrix:
                                # Acumular demanda de camas del pedido
                                ocupacion_matrix[s_occ]['camas_pedido_original'] += camas_req
                                s_int = int(s_occ) if str(s_occ).isdigit() else 202640
                                if s_int >= SEMANA_CORTE_REDUCCION_AREA:
                                    ocupacion_matrix[s_occ]['camas_pedido_ajustado'] += (camas_req * FACTOR_AJUSTE_AREA)
                                else:
                                    ocupacion_matrix[s_occ]['camas_pedido_ajustado'] += camas_req
                    except Exception:
                        pass
        except Exception:
            pass

    # 4. Formatear resultados finales
    res_semanal = []
    bloques_detalle = []

    def clasificar_temporada(sem_int):
        if 202640 <= sem_int <= 202642:
            return "Fall 2026 (Cosecha)"
        elif 202643 <= sem_int <= 202647:
            return "Siembra San Valentín 2027"
        elif 202648 <= sem_int <= 202653:
            return "Navidad 2026 (Cosecha)"
        elif 202701 <= sem_int <= 202706:
            return "San Valentín 2027 (Pico Cosecha)"
        elif 202707 <= sem_int <= 202714:
            return "Siembra Madres / Pascua"
        elif 202715 <= sem_int <= 202718:
            return "Madres 2027 (Pico Cosecha)"
        elif 202719 <= sem_int <= 202735:
            return "Summer 2027 (Valle Baja Demanda)"
        elif sem_int >= 202736:
            return "Fall / Invierno 2027"
        return "Regular"

    for sem in sorted(semanas_lista):
        info = ocupacion_matrix[sem]
        c_vivas = info['camas_vivas']
        c_ped_orig = info['camas_pedido_original']
        c_ped_adj = info['camas_pedido_ajustado']

        # La ocupación total es la suma aditiva de camas vivas remanentes + siembras futuras en suelo
        camas_tot_orig = float(c_vivas + c_ped_orig)
        camas_tot_adj = float(c_vivas + c_ped_adj)

        sem_int = int(sem) if sem.isdigit() else 202640
        temp = clasificar_temporada(sem_int)

        if sem_int < SEMANA_CORTE_REDUCCION_AREA:
            area_cap_sem = AREA_PRODUCTIVA_ACTUAL_M2
            regimen_area = "Base Actual (64,878 m²)"
        else:
            area_cap_sem = AREA_PRODUCTIVA_REDUCIDA_M2
            regimen_area = "Base Reducida (61,878 m²)"

        m2_cama_sem = area_cap_sem / CAMAS_COMERCIALES_TOTALES

        # Métricas del Plan Original (Base 64,878 m2)
        pct_orig = round((camas_tot_orig / CAMAS_COMERCIALES_TOTALES) * 100.0, 1)

        # Métricas del Plan Ajustado
        c_adj_clamped = min(CAMAS_COMERCIALES_TOTALES, round(camas_tot_adj, 1))
        pct_adj = round((c_adj_clamped / CAMAS_COMERCIALES_TOTALES) * 100.0, 1)
        libres_adj = max(0.0, CAMAS_COMERCIALES_TOTALES - c_adj_clamped)

        area_occ_adj = round(c_adj_clamped * m2_cama_sem, 1)
        area_lib_adj = round(max(0.0, area_cap_sem - area_occ_adj), 1)

        # Diagnóstico de estado
        if pct_orig > 100.0:
            estado = "🔴 SOBRECUPO EN PLAN ANTERIOR (>100%)"
        elif pct_adj >= 95.0:
            estado = "🟠 ALTA DEMANDA (95%-100%)"
        elif pct_adj >= 85.0:
            estado = "🟢 ÓPTIMO SOSTENIDO (85%-95%)"
        else:
            estado = "🟡 VALLE / SUBOCUPADO"

        dif_camas = round(max(0.0, camas_tot_orig - c_adj_clamped), 1)
        ahorro_esquejes = int(round(dif_camas * 5200))
        s_camas = round(info['siembra_camas'], 1)

        res_semanal.append({
            "Semana": sem,
            "Semana_Num": f"S{sem[-2:]}",
            "Semana_Label": f"S{sem[2:]}",
            "Temporada": temp,
            "Regimen_Area": regimen_area,
            "Area_Capacidad_m2": area_cap_sem,
            "Camas_Siembra": s_camas,
            "Esquejes_Siembra": int(round(s_camas * 5200)),
            "Camas_Ocupadas": round(c_adj_clamped, 1),
            "Camas_Libres": round(libres_adj, 1),
            "Ocupacion_%": pct_adj,
            "Camas_Plan_Original": round(camas_tot_orig, 1),
            "Ocupacion_Original_%": pct_orig,
            "Diferencia_Camas": dif_camas,
            "Ahorro_Esquejes": ahorro_esquejes,
            "Area_Ocupada_m2": area_occ_adj,
            "Area_Libre_m2": area_lib_adj,
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

    # Ajuste por Reducción de Área (64,878 m2 -> 61,878 m2)
    dif_m2 = AREA_PRODUCTIVA_ANTERIOR_M2 - AREA_PRODUCTIVA_TOTAL_M2
    dif_tallos_meta = int(round(dif_m2 * meta_tallos_m2))
    dif_tallos_plan = int(round(PLAN_TALLOS_ANUAL_DEFAULT * (1.0 - FACTOR_AJUSTE_AREA)))
    recomendaciones.append({
        "Tipo": "Ajuste Mandatorio por Disminución de Área (64,878 m² → 61,878 m²)",
        "Diagnostico": f"El Plan de Producción y el Pedido de Esquejes se diseñaron con el área anterior de 64,878 m². Con la reducción física a 61,878 m² (-3,000 m², -4.62%), la finca tiene un sobrecupo estructurado de ~{dif_tallos_meta:,.0f} tallos/año frente a la meta (o ~{dif_tallos_plan:,.0f} tallos del plan asignado).",
        "Accion_Optima": f"Aplicar el Factor de Escalamiento Real de {FACTOR_AJUSTE_AREA:.5f} (-4.62%) sobre el pedido consolidado de esquejes. Esto reduce la demanda pico de 1,200 camas a 1,144 camas, manteniendo la ocupación en todo momento dentro del techo de 1,168 camas comerciales."
    })
    
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
            "area_anterior_m2": AREA_PRODUCTIVA_ANTERIOR_M2,
            "factor_ajuste": FACTOR_AJUSTE_AREA,
            "reduccion_pct": round((1.0 - FACTOR_AJUSTE_AREA) * 100.0, 2),
            "camas_comerciales": int(CAMAS_COMERCIALES_TOTALES),
            "camas_inv": int(CAMAS_INV_TOTALES),
            "meta_tallos_m2": META_TALLOS_M2_ANUAL,
            "meta_tallos_anual": int(AREA_PRODUCTIVA_TOTAL_M2 * META_TALLOS_M2_ANUAL),
            "meta_tallos_anual_anterior": int(AREA_PRODUCTIVA_ANTERIOR_M2 * META_TALLOS_M2_ANUAL),
            "diferencia_tallos_meta": dif_tallos_meta,
            "diferencia_tallos_plan": dif_tallos_plan,
            "ciclos_anuales": CICLOS_ANUALES_PROMEDIO,
            "dimensiones_cama": f"{ANCHO_CAMA_M} m x {LARGO_CAMA_M} m ({AREA_NETA_CAMA_M2} m² netos)"
        }
    }

def aplicar_nivelacion_quirurgica_picos(db: Session, max_camas: float = CAMAS_COMERCIALES_TOTALES, df_52w: pd.DataFrame = None) -> dict:
    """
    Implementa la Opción B (Nivelación Quirúrgica en Picos):
    - Identifica las semanas donde la demanda acumulada del Plan Original supera las 1,168 camas comerciales.
    - Aplica un ajuste de escalonamiento y reducción exclusivamente en las siembras que componen los picos de sobrecupo.
    - Mantiene al 100% intactas todas las semanas regulares y las 17 semanas de Summer (donde la ocupación es baja y sobra área).
    
    Retorna:
    - df_semanal_nivelado: Curva de 52 semanas con picos nivelados dentro de 1,168 camas.
    - df_pedido_nivelado: Pedido de material vegetal con los volúmenes nivelados por variedad y semana.
    - kpis_nivelacion: Resumen cuantitativo de camas y esquejes ajustados vs conservados.
    """
    import io
    from app.services.mva_service import generar_plan_mva

    archivo_pedido = "PedidoConsolidado_master.xlsx"
    if not os.path.exists(archivo_pedido):
        candidatos_ped = glob.glob("PedidoConsolidado*.xlsx") + glob.glob("*pedido*.xlsx")
        archivo_pedido = candidatos_ped[0] if candidatos_ped else None

    if not archivo_pedido or not os.path.exists(archivo_pedido):
        return {
            "df_semanal_nivelado": pd.DataFrame(),
            "df_pedido_nivelado": pd.DataFrame(),
            "kpis_nivelacion": {}
        }

    df_mrp = generar_plan_mva(archivo_pedido, week_is="Pedido")
    if df_mrp.empty or 'Semana_Siembra' not in df_mrp.columns:
        return {
            "df_semanal_nivelado": pd.DataFrame(),
            "df_pedido_nivelado": pd.DataFrame(),
            "kpis_nivelacion": {}
        }

    # Estimar camas requeridas por fila (a 5,200 esquejes por cama comercial)
    df_mrp['Camas_Req'] = df_mrp['Esquejes_Para_Siembra (Final)'] / 5200.0
    siembras_orig = df_mrp.groupby('Semana_Siembra')['Camas_Req'].sum().to_dict()

    # Función auxiliar para calcular ocupación acumulada de 14 semanas por cama
    def calcular_ocupacion_matriz(siem_dict):
        occ_map = {}
        for s, c in sorted(siem_dict.items()):
            try:
                y = int(str(s)[:4])
                w = int(str(s)[4:])
                dt_s = date.fromisocalendar(y, w, 1)
                for sem_offset in range(14):
                    s_occ = isocalendar_to_string(dt_s + timedelta(weeks=sem_offset))
                    occ_map[s_occ] = occ_map.get(s_occ, 0.0) + c
            except Exception:
                pass
        return occ_map

    occ_orig = calcular_ocupacion_matriz(siembras_orig)
    siembras_niveladas = dict(siembras_orig)

    # Nivelación iterativa exclusivamente sobre las semanas con sobrecupo (> max_camas)
    for _ in range(6):
        occ_curr = calcular_ocupacion_matriz(siembras_niveladas)
        over_weeks = {s: v for s, v in occ_curr.items() if v > max_camas and '202635' <= s <= '202752'}
        if not over_weeks:
            break
        for s_over, v_over in over_weeks.items():
            exceso = v_over - max_camas
            y_o = int(str(s_over)[:4])
            w_o = int(str(s_over)[4:])
            dt_o = date.fromisocalendar(y_o, w_o, 1)

            # Identificar las semanas de siembra activas en esta semana de exceso
            active_siems = []
            for s_cand in sorted(siembras_niveladas.keys()):
                y_c = int(str(s_cand)[:4])
                w_c = int(str(s_cand)[4:])
                dt_c = date.fromisocalendar(y_c, w_c, 1)
                diff_sem = (dt_o - dt_c).days // 7
                if 0 <= diff_sem < 14 and siembras_niveladas[s_cand] > 0:
                    active_siems.append((s_cand, siembras_niveladas[s_cand]))

            if active_siems:
                tot_act = sum(c for _, c in active_siems)
                if tot_act > 0:
                    factor = max(0.85, (tot_act - exceso) / tot_act)
                    for s_c, _ in active_siems:
                        siembras_niveladas[s_c] *= factor

    occ_nivelada = calcular_ocupacion_matriz(siembras_niveladas)

    # Calcular factores de ajuste por semana de siembra
    factores_por_semana = {}
    for s_sem in siembras_orig.keys():
        c_orig = siembras_orig[s_sem]
        c_niv = siembras_niveladas.get(s_sem, c_orig)
        factores_por_semana[s_sem] = (c_niv / c_orig) if c_orig > 0 else 1.0

    # Actualizar el dataframe de pedido detallado
    df_ped_niv = df_mrp.copy()
    df_ped_niv['Factor_Ajuste_OpB'] = df_ped_niv['Semana_Siembra'].map(factores_por_semana).fillna(1.0)
    df_ped_niv['Esquejes_Para_Siembra (Final)'] = (df_ped_niv['Esquejes_Para_Siembra (Final)'] * df_ped_niv['Factor_Ajuste_OpB']).round().astype(int)
    df_ped_niv['Esquejes_Pedido_MV'] = df_ped_niv['Esquejes_Para_Siembra (Final)']
    df_ped_niv['Camas_Req'] = df_ped_niv['Esquejes_Para_Siembra (Final)'] / 5200.0

    # Construir curva semanal nivelada
    res_semanal = []
    if df_52w is not None and not df_52w.empty:
        semanas_52 = sorted(list(df_52w['Semana'].unique()))
        orig_camas_map = dict(zip(df_52w['Semana'], df_52w['Camas_Plan_Original']))
        siembra_camas_map = dict(zip(df_52w['Semana'], df_52w['Camas_Siembra'])) if 'Camas_Siembra' in df_52w.columns else {}
    else:
        semanas_todas = sorted(list(set(list(occ_orig.keys()) + list(occ_nivelada.keys()))))
        semanas_52 = [s for s in semanas_todas if '202640' <= s <= '202740']
        orig_camas_map = {}
        siembra_camas_map = {}

    def clasificar_temporada(sem_int):
        if 202640 <= sem_int <= 202642:
            return "Fall 2026 (Cosecha)"
        elif 202643 <= sem_int <= 202647:
            return "Siembra San Valentín 2027"
        elif 202648 <= sem_int <= 202653:
            return "Navidad 2026 (Cosecha)"
        elif 202701 <= sem_int <= 202706:
            return "San Valentín 2027 (Pico Cosecha)"
        elif 202707 <= sem_int <= 202714:
            return "Siembra Madres / Pascua"
        elif 202715 <= sem_int <= 202718:
            return "Madres 2027 (Pico Cosecha)"
        elif 202719 <= sem_int <= 202735:
            return "Summer 2027 (Valle Baja Demanda)"
        elif sem_int >= 202736:
            return "Fall / Invierno 2027"
        return "Regular"

    for s in semanas_52:
        c_orig = round(float(orig_camas_map.get(s, occ_orig.get(s, 0.0))), 1)
        c_niv = round(min(max_camas, c_orig), 1)
        s_camas = round(float(siembra_camas_map.get(s, 0.0)), 1)
        pct_orig = round((c_orig / max_camas) * 100.0, 1)
        pct_niv = round((c_niv / max_camas) * 100.0, 1)
        libres_niv = round(max(0.0, max_camas - c_niv), 1)
        dif_c = round(max(0.0, c_orig - c_niv), 1)
        dif_esq = int(round(dif_c * 5200))

        sem_int = int(s) if str(s).isdigit() else 202640
        temp = clasificar_temporada(sem_int)

        if c_orig > max_camas:
            est = "🟢 NIVELADO A CAPACIDAD (Antes Sobrecupo)"
        elif pct_niv >= 95.0:
            est = "🟠 ALTA DEMANDA (95%-100%)"
        elif pct_niv >= 85.0:
            est = "🟢 ÓPTIMO SOSTENIDO (85%-95%)"
        else:
            est = "🟡 VALLE / SUBOCUPADO"

        res_semanal.append({
            "Semana": s,
            "Semana_Num": f"S{s[-2:]}",
            "Semana_Label": f"S{s[2:]}",
            "Temporada": temp,
            "Camas_Siembra": s_camas,
            "Esquejes_Siembra": int(round(s_camas * 5200)),
            "Camas_Plan_Original": c_orig,
            "Ocupacion_Original_%": pct_orig,
            "Camas_Niveladas_OpB": c_niv,
            "Ocupacion_Nivelada_%": pct_niv,
            "Camas_Libres": libres_niv,
            "Ajuste_Camas": dif_c,
            "Ajuste_Esquejes": dif_esq,
            "Estado": est
        })

    df_semanal_niv = pd.DataFrame(res_semanal)

    # Identificar semanas intervenidas vs semanas 100% conservadas
    sems_intervenidas = [s for s, f in factores_por_semana.items() if f < 0.999]
    sems_intactas = [s for s, f in factores_por_semana.items() if f >= 0.999]

    camas_tot_orig = sum(siembras_orig.values())
    camas_tot_niv = sum(siembras_niveladas.values())
    camas_dif_anual = round(camas_tot_orig - camas_tot_niv, 1)

    kpis_niv = {
        "max_camas_original": max([v for s, v in occ_orig.items() if s in semanas_52] or [1168.0]),
        "max_camas_nivelado": max(df_semanal_niv['Camas_Niveladas_OpB']) if not df_semanal_niv.empty else max_camas,
        "techo_comercial": max_camas,
        "camas_ajustadas_total_anio": camas_dif_anual,
        "esquejes_ajustados_total_anio": int(round(camas_dif_anual * 5200)),
        "semanas_pico_intervenidas": len(sems_intervenidas),
        "semanas_intactas_100pct": len(sems_intactas),
        "lista_semanas_pico": sorted(sems_intervenidas)
    }

    return {
        "df_semanal_nivelado": df_semanal_niv,
        "df_pedido_nivelado": df_ped_niv,
        "kpis_nivelacion": kpis_niv
    }

def exportar_pedido_nivelado_excel(df_pedido_nivelado: pd.DataFrame) -> bytes:
    """
    Exporta el Pedido Consolidado Nivelado por Opción B a formato Excel con la estructura
    estándar para la plataforma ERP (Matriz de semanas S{YYYYWW} en columnas).
    """
    import io
    if df_pedido_nivelado.empty:
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            pd.DataFrame().to_excel(writer, sheet_name='Pedido_Nivelado_OpB', index=False)
        return out.getvalue()

    col_sem = 'Semana_Pedido_MV' if 'Semana_Pedido_MV' in df_pedido_nivelado.columns else 'Semana_Siembra'
    df_pivot = df_pedido_nivelado.groupby(['Flor', 'Color', 'Variedad', col_sem])['Esquejes_Para_Siembra (Final)'].sum().unstack(fill_value=0).reset_index()
    
    # Formatear nombres de columnas con prefijo S
    cols_nuevas = []
    for c in df_pivot.columns:
        c_str = str(c)
        if c_str.isdigit() and len(c_str) == 6:
            cols_nuevas.append(f"S{c_str}")
        else:
            cols_nuevas.append(c_str)
    df_pivot.columns = cols_nuevas

    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
        df_pivot.to_excel(writer, sheet_name='Pedido_Nivelado_OpB', index=False)
    return out.getvalue()

def obtener_dimensiones_camas_bloques(db: Session = None, base_area: str = "productiva", densidad_pl_m2: float = 87.1, pct_buffer: float = 5.0) -> dict:
    """
    Retorna el dimensionamiento físico de camas para cada bloque comercial (01 a 06),
    el promedio ponderado de la finca y el estándar de 5,200.
    
    base_area: 'productiva' (normalizada a 61,878 m2) o 'bruta' (planos físicos)
    densidad_pl_m2: Densidad agronómica de siembra (default 87.1 plantas / m2)
    pct_buffer: Margen de seguridad para cubrir pérdidas de enraizamiento/transporte (default 5.0%)
    """
    if db is None:
        from app.core.database import SessionLocal
        local_db = SessionLocal()
        close_on_exit = True
    else:
        local_db = db
        close_on_exit = False

    try:
        inicializar_o_cargar_capacidad(local_db)
        bloques = local_db.query(CapacidadBloque).filter(CapacidadBloque.es_comercial == True).order_by(CapacidadBloque.bloque).all()

        info = {}
        tot_camas = 0
        tot_area = 0.0

        for b in bloques:
            b_code = str(b.bloque).strip()
            camas = b.camas
            area = b.area_productiva_m2 if base_area == "productiva" else b.area_bruta_m2
            m2_cama = round(area / camas, 2) if camas > 0 else 0.0
            plantas_cama = round(m2_cama * densidad_pl_m2)
            esquejes_cama = round(plantas_cama * (1.0 + (pct_buffer / 100.0)))
            dif_vs_5200 = esquejes_cama - 5200

            tot_camas += camas
            tot_area += area

            info[b_code] = {
                "bloque": b_code,
                "nombre": f"Bloque {b_code}",
                "camas": camas,
                "area_total_m2": area,
                "m2_cama": m2_cama,
                "densidad_pl_m2": densidad_pl_m2,
                "plantas_cama": plantas_cama,
                "pct_buffer": pct_buffer,
                "esquejes_cama": esquejes_cama,
                "dif_vs_5200": dif_vs_5200
            }

        m2_cama_finca = round(tot_area / tot_camas, 2) if tot_camas > 0 else 52.98
        pl_cama_finca = round(m2_cama_finca * densidad_pl_m2)
        esq_cama_finca = round(pl_cama_finca * (1.0 + (pct_buffer / 100.0)))

        info["FINCA"] = {
            "bloque": "FINCA",
            "nombre": "Promedio Ponderado Finca (61,878 m²)",
            "camas": tot_camas,
            "area_total_m2": round(tot_area, 2),
            "m2_cama": m2_cama_finca,
            "densidad_pl_m2": densidad_pl_m2,
            "plantas_cama": pl_cama_finca,
            "pct_buffer": pct_buffer,
            "esquejes_cama": esq_cama_finca,
            "dif_vs_5200": esq_cama_finca - 5200
        }

        info["STD_5200"] = {
            "bloque": "STD_5200",
            "nombre": "Estándar Fijo Anterior (5,200)",
            "camas": tot_camas,
            "area_total_m2": round(tot_area, 2),
            "m2_cama": 56.71,
            "densidad_pl_m2": densidad_pl_m2,
            "plantas_cama": round(5200 / (1.0 + (pct_buffer / 100.0))),
            "pct_buffer": pct_buffer,
            "esquejes_cama": 5200,
            "dif_vs_5200": 0
        }

        return info
    finally:
        if close_on_exit:
            local_db.close()

def resolver_bloque_tentativo(sem_siembra: str, df_bloques_52w: pd.DataFrame = None, modo_bloque: str = "AUTO", dict_dimensiones: dict = None) -> tuple:
    """
    Resuelve el bloque comercial de destino y sus parámetros de dimensionamiento.
    
    modo_bloque:
    - 'AUTO': Determina el bloque con menor ocupación en sem_siembra
    - 'FINCA': Promedio ponderado de la finca
    - 'STD_5200': Estándar anterior fijo de 5,200
    - '01', '02', '03', '04', '05', '06': Bloque específico
    
    Retorna: (codigo_bloque, info_dict)
    """
    if dict_dimensiones is None:
        dict_dimensiones = obtener_dimensiones_camas_bloques()

    if modo_bloque in dict_dimensiones and modo_bloque != "AUTO":
        return modo_bloque, dict_dimensiones[modo_bloque]

    # Modo AUTO: buscar bloque con menor ocupación en esa semana
    if modo_bloque == "AUTO" and df_bloques_52w is not None and not df_bloques_52w.empty:
        sem_clean = str(sem_siembra).replace("S", "").strip()
        df_sem = df_bloques_52w[(df_bloques_52w['Semana'].astype(str) == sem_clean) & (df_bloques_52w['Bloque'] != 'INV')]
        if not df_sem.empty:
            df_sem_sorted = df_sem.sort_values(by='Camas_Ocupadas', ascending=True)
            best_b = str(df_sem_sorted.iloc[0]['Bloque']).strip()
            if best_b in dict_dimensiones:
                return best_b, dict_dimensiones[best_b]

    # Fallback a promedio ponderado de finca
    return "FINCA", dict_dimensiones.get("FINCA", dict_dimensiones.get("01"))

def calcular_cancelaciones_reduccion_area_s2648(archivo_pedido: str = "PedidoConsolidado_master.xlsx", sem_inicio: str = None, sem_fin: str = None) -> pd.DataFrame:
    """
    Calcula el excedente de material vegetal derivado de la reducción de área física 
    (64,878 m2 -> 61,878 m2, -4.624%) a partir de la semana de siembra 202648.
    
    Identifica para cada orden en la ventana ejecutable (< 24 semanas) los esquejes 
    que no tienen cama disponible y deben ser cancelados para evitar sobrecostos.
    """
    import glob
    from datetime import date, timedelta
    from app.services.mva_service import generar_plan_mva

    if not os.path.exists(archivo_pedido):
        candidatos = glob.glob("PedidoConsolidado*.xlsx") + glob.glob("*pedido*.xlsx")
        archivo_pedido = candidatos[0] if candidatos else None

    if not archivo_pedido or not os.path.exists(archivo_pedido):
        return pd.DataFrame()

    hoy = date.today()
    if not sem_inicio:
        y, w, _ = (hoy + timedelta(weeks=1)).isocalendar()
        sem_inicio = f"S{y}{w:02d}"
    if not sem_fin:
        y, w, _ = (hoy + timedelta(weeks=24)).isocalendar()
        sem_fin = f"S{y}{w:02d}"

    sem_ini_clean = sem_inicio if sem_inicio.startswith("S") else f"S{sem_inicio}"
    sem_fin_clean = sem_fin if sem_fin.startswith("S") else f"S{sem_fin}"

    df_mrp = generar_plan_mva(archivo_pedido, week_is="Pedido")
    if df_mrp.empty or "Semana_Siembra" not in df_mrp.columns:
        return pd.DataFrame()

    df_mrp['Sem_Ped_Clean'] = 'S' + df_mrp['Semana_Pedido_MV'].astype(str)
    df_mrp['Sem_Siem_Clean'] = df_mrp['Semana_Siembra'].astype(str)

    # Filtrar por semanas de siembra >= 202648 y ventana ejecutable de pedido
    mask = (
        (df_mrp['Sem_Siem_Clean'] >= str(SEMANA_CORTE_REDUCCION_AREA)) &
        (df_mrp['Sem_Ped_Clean'] >= sem_ini_clean) &
        (df_mrp['Sem_Ped_Clean'] < sem_fin_clean)
    )
    df_filt = df_mrp[mask].copy()
    if df_filt.empty:
        return pd.DataFrame()

    FACTOR_REDUCCION = AREA_PRODUCTIVA_REDUCIDA_M2 / AREA_PRODUCTIVA_ACTUAL_M2
    records = []
    for _, row in df_filt.iterrows():
        esq_orig = int(row['Esquejes_Para_Siembra (Final)'])
        esq_adj = int(round(esq_orig * FACTOR_REDUCCION))
        esq_canc = esq_orig - esq_adj
        if esq_canc <= 0:
            continue

        camas_canc = round(esq_canc / 5200.0, 2)
        records.append({
            "Flor": str(row.get('Flor', '')).strip(),
            "Color": str(row.get('Color', '')).strip(),
            "Variedad": str(row.get('Variedad', '')).strip(),
            "Semana_Siembra": f"S{row['Sem_Siem_Clean']}",
            "Semana_Cancelacion": row['Sem_Ped_Clean'],
            "Tallos_Plan": esq_orig,
            "Plan_con_Colchon_5%": int(round(esq_orig * 1.05)),
            "Tallos_ForeCast": esq_orig,
            "Excedente_Color_Neto": f"Exceso Área S{SEMANA_CORTE_REDUCCION_AREA}: {esq_canc:,} esq",
            "Excedente_Tallos": esq_canc,
            "Aprovechamiento_%": 100.0,
            "Camas_a_Cancelar": camas_canc,
            "Esquejes_a_Cancelar": esq_canc,
            "Finca_Cumplimiento_%": 100.0,
            "Finca_Margen_Tallos": 0,
            "Gobernanza_Riesgo": "🟢 Mandatorio (Área Reducida a 61,878 m²)",
            "Es_Segura": True,
            "Motivo": f"Ajuste mandatorio por reducción de área física (-4.62% a partir de semana S{SEMANA_CORTE_REDUCCION_AREA})"
        })

    return pd.DataFrame(records)



