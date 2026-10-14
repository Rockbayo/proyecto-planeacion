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
AREA_PRODUCTIVA_TOTAL_M2 = 61878.0       # Área comercial productiva real actual
AREA_PRODUCTIVA_ANTERIOR_M2 = 64878.0   # Área comercial previa (con la que se diseñó el Plan Original)
FACTOR_AJUSTE_AREA = AREA_PRODUCTIVA_TOTAL_M2 / AREA_PRODUCTIVA_ANTERIOR_M2 # 0.953759 (-4.62%)

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
    ocupacion_matrix = {
        s: {
            'camas_vivas': 0,
            'camas_pedido_original': 0.0,
            'camas_pedido_ajustado': 0.0,
            'por_bloque': {b: 0 for b in ['01', '02', '03', '04', '05', '06', 'INV']}
        } for s in semanas_lista
    }

    # Tracking de camas físicas únicas por semana para el inventario vivo
    camas_vivas_por_sem = {s: set() for s in semanas_lista}

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
                    try:
                        y = int(str(sem_s)[:4])
                        w = int(str(sem_s)[4:])
                        dt_s = date.fromisocalendar(y, w, 1)

                        # Una cama sembrada en sem_s permanece ocupada 14 semanas (ciclo de cultivo + 1 sem descanso)
                        for sem_offset in range(14):
                            dt_occ = dt_s + timedelta(weeks=sem_offset)
                            s_occ = isocalendar_to_string(dt_occ)
                            if s_occ in ocupacion_matrix:
                                # Acumular demanda de camas del pedido
                                ocupacion_matrix[s_occ]['camas_pedido_original'] += camas_req
                                ocupacion_matrix[s_occ]['camas_pedido_ajustado'] += (camas_req * FACTOR_AJUSTE_AREA)
                    except Exception:
                        pass
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

    m2_por_cama_prom = AREA_PRODUCTIVA_TOTAL_M2 / CAMAS_COMERCIALES_TOTALES

    for sem in sorted(semanas_lista):
        info = ocupacion_matrix[sem]
        c_vivas = info['camas_vivas']
        c_ped_orig = info['camas_pedido_original']
        c_ped_adj = info['camas_pedido_ajustado']

        # En semanas futuras donde se libera el inventario vivo, entra la demanda del pedido
        if sem > semana_actual and c_ped_orig > 0:
            camas_tot_orig = max(float(c_vivas), c_ped_orig)
            camas_tot_adj = max(float(c_vivas), c_ped_adj)
        else:
            camas_tot_orig = float(c_vivas)
            camas_tot_adj = float(c_vivas)

        # Métricas del Plan Original (Base 64,878 m2)
        pct_orig = round((camas_tot_orig / CAMAS_COMERCIALES_TOTALES) * 100.0, 1)

        # Métricas del Plan Ajustado (Base 61,878 m2)
        c_adj_clamped = min(CAMAS_COMERCIALES_TOTALES, round(camas_tot_adj, 1))
        pct_adj = round((c_adj_clamped / CAMAS_COMERCIALES_TOTALES) * 100.0, 1)
        libres_adj = max(0.0, CAMAS_COMERCIALES_TOTALES - c_adj_clamped)

        area_occ_adj = round(c_adj_clamped * m2_por_cama_prom, 1)
        area_lib_adj = round(max(0.0, AREA_PRODUCTIVA_TOTAL_M2 - area_occ_adj), 1)

        sem_int = int(sem) if sem.isdigit() else 202640
        temp = clasificar_temporada(sem_int)

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

        res_semanal.append({
            "Semana": sem,
            "Semana_Num": f"S{sem[-2:]}",
            "Temporada": temp,
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

