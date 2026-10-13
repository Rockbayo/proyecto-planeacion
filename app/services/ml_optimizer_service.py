import pandas as pd
import joblib
import os
import math
from app.models.models import Variedad, Siembra
from app.services.forecast_service import isocalendar_to_string

def restar_semanas(semana_str, n_semanas):
    year = int(semana_str[:4])
    week = int(semana_str[4:])
    week -= n_semanas
    while week <= 0:
        year -= 1
        week += 52
    return f"{year}{week:02d}"

def sumar_semanas(semana_str, n_semanas):
    year = int(semana_str[:4])
    week = int(semana_str[4:])
    week += n_semanas
    while week > 52: # Simplificación: años de 52 semanas
        year += 1
        week -= 52
    return f"{year}{week:02d}"

def optimizar_siembras_con_ml(db, df_target):
    """
    df_target debe tener: ['Variedad', 'Semana_Objetivo', 'Exportable_Meta']
    Retorna un DataFrame con el plan de siembra optimizado.
    """
    if not os.path.exists('ml_model_xgb.pkl') or not os.path.exists('ml_features_xgb.pkl'):
        raise Exception("El modelo XGBoost no está entrenado. Por favor entrena el modelo primero.")
        
    model = joblib.load('ml_model_xgb.pkl')
    ml_features = joblib.load('ml_features_xgb.pkl')
    
    variedades = db.query(Variedad).filter(Variedad.activo == True).all()
    dict_vars = {v.nombre.strip().upper(): v for v in variedades}
    
    # 1. Cargar inventario vivo (pasado y presente) que no podemos alterar
    siembras = db.query(Siembra).all()
    inventario_base = {}
    for s in siembras:
        v_name_s = s.variedad.nombre.strip().upper()
        sem = isocalendar_to_string(s.fecha_siembra)
        if v_name_s not in inventario_base:
            inventario_base[v_name_s] = {}
        inventario_base[v_name_s][sem] = inventario_base[v_name_s].get(sem, 0) + s.plantas_sembradas
        
    # 2. Inicializar plan de siembra propuesto usando la heurística clásica
    # (Plantas = Meta / APROV sembradas en Semana_Objetivo - dia_pico)
    plan_propuesto = {} # {var: {sem_siembra: plantas}}
    
    # Mapear variedad exacta en el dataframe objetivo
    def map_variedad(v):
        v_upper = str(v).strip().upper()
        
        # Mapeo de abreviaturas comunes si existen en los archivos
        abrevs = {
            'VAL': 'VALENTINO',
            'FREE': 'FREEDOM',
            'MON': 'MONDIAL',
            'EXC': 'EXPLORER',
            'EXP': 'EXPLORER'
        }
        if v_upper in abrevs:
            v_upper = abrevs[v_upper]
            
        return dict_vars[v_upper].nombre if v_upper in dict_vars else None
        
    df_target['Variedad_Exacta'] = df_target['Variedad'].apply(map_variedad)
    df_target['Semana_Objetivo_Clean'] = df_target['Semana_Objetivo'].apply(lambda x: str(x).replace('.0', '').strip())
    
    # Regla de Negocio: Aplicar un colchón de seguridad del 5% sobre el plan para garantizar el cumplimiento
    df_target['Exportable_Meta'] = pd.to_numeric(df_target['Exportable_Meta'].astype(str).str.replace(',', ''), errors='coerce').fillna(0) * 1.05
    
    # MUY IMPORTANTE: Agrupar metas por Variedad_Exacta y Semana_Objetivo para evitar duplicación/producto cartesiano
    df_target = df_target.groupby(['Variedad_Exacta', 'Semana_Objetivo_Clean'], as_index=False)['Exportable_Meta'].sum()
    
    for _, row in df_target.iterrows():
        # Limpieza de datos
        v_name_exact = row['Variedad_Exacta']
        if not v_name_exact:
            print("Missing:", row['Variedad_Exacta'], "Raw:", row['Variedad'])
            continue
        try:
            meta = float(str(row['Exportable_Meta']).replace(',', ''))
        except ValueError:
            meta = 0.0
            
        sem_obj = row['Semana_Objetivo_Clean']
        
        if meta > 0:
            var = dict_vars[v_name_exact.upper()]
            
            semanas_pico = max(10, int(round((var.dia_pico if var.dia_pico else 70) / 7.0)))
            sem_siembra = restar_semanas(sem_obj, semanas_pico)
            
            # Permitimos planear siembras en el pasado para efectos de simulación e históricos
            plantas_req = meta / (var.aprov_pp if var.aprov_pp > 0 else 1.0)
            if v_name_exact not in plan_propuesto:
                plan_propuesto[v_name_exact] = {}
            plan_propuesto[v_name_exact][sem_siembra] = plan_propuesto[v_name_exact].get(sem_siembra, 0) + plantas_req
                
    # 3. Bucle de Optimización (Simulación -> Corrección)
    learning_rate = 0.5
    iterations = 5
    
    for iteration in range(iterations):
        # Preparar features para todo el target
        dataset = []
        for _, row in df_target.iterrows():
            v_name_exact = row['Variedad_Exacta']
            if not v_name_exact:
                continue
                
            sem_obj = row['Semana_Objetivo_Clean']
            v_name_upper = v_name_exact.upper()
            
            record = {
                'Variedad': v_name_exact,
                'Semana_Cosecha': sem_obj,
                'Estacionalidad_Semana': int(sem_obj[4:]) if len(sem_obj) == 6 else 1
            }
            
            for f in ml_features:
                if f.startswith('Variedad_'):
                    v_feat = f.replace('Variedad_', '')
                    record[f] = 1 if v_feat == v_name_exact else 0
                    
            for lag in range(9, 17):
                sem_s = restar_semanas(sem_obj, lag)
                # Combinar inventario base (fijo) y plan propuesto (variable)
                plantas_base = inventario_base.get(v_name_upper, {}).get(sem_s, 0)
                plantas_plan = plan_propuesto.get(v_name_exact, {}).get(sem_s, 0)
                record[f'Lag_{lag}'] = plantas_base + plantas_plan
                
            dataset.append(record)
            
        if not dataset:
            return pd.DataFrame()
            
        df_sim = pd.DataFrame(dataset)
        for col in ml_features:
            if col not in df_sim.columns:
                df_sim[col] = 0
                
        X_sim = df_sim[ml_features]
        preds = model.predict(X_sim)
        df_sim['Prediccion_ML'] = preds
        df_sim['Prediccion_ML'] = df_sim['Prediccion_ML'].apply(lambda x: max(0, x))
        
        # Unir prediccion con la meta
        df_eval = pd.merge(df_sim[['Variedad', 'Semana_Cosecha', 'Prediccion_ML']], 
                           df_target, left_on=['Variedad', 'Semana_Cosecha'], right_on=['Variedad_Exacta', 'Semana_Objetivo_Clean'])
                           
        # Corregir el plan_propuesto
        for _, row in df_eval.iterrows():
            v_name_exact = row['Variedad_Exacta']
            sem_obj = row['Semana_Cosecha']
            error = row['Exportable_Meta'] - row['Prediccion_ML']
            
            # Si el error es positivo, faltan tallos. Si es negativo, sobran tallos.
            if abs(error) > 1000:
                var = dict_vars.get(v_name_exact.upper())
                if var:
                    semanas_pico = max(10, int(round((var.dia_pico if var.dia_pico else 70) / 7.0)))
                    sem_siembra = restar_semanas(sem_obj, semanas_pico)
                    
                    ajuste_plantas = (error / (var.aprov_pp if var.aprov_pp > 0 else 1.0)) * learning_rate
                    actual = plan_propuesto.get(v_name_exact, {}).get(sem_siembra, 0)
                    
                    # Guardrail contra inflación desmedida (ej. si el modelo predice 0 consistentemente)
                    # Limitamos la sugerencia máxima a 1.5x el requerimiento base
                    base_req = (row['Exportable_Meta'] / (var.aprov_pp if var.aprov_pp > 0 else 1.0))
                    nuevo_valor = min(base_req * 1.5, max(0, actual + ajuste_plantas))
                    
                    if v_name_exact not in plan_propuesto:
                        plan_propuesto[v_name_exact] = {}
                    plan_propuesto[v_name_exact][sem_siembra] = nuevo_valor
    # 4. Formatear la salida
    records_finales = []
    for v_name, dict_sem in plan_propuesto.items():
        var = dict_vars.get(str(v_name).strip().upper())
        flor = var.flor if var else ''
        for sem, plantas in dict_sem.items():
            if plantas > 0:
                # El MVA pide semana de PEDIDO (4 semanas antes de siembra)
                sem_pedido = restar_semanas(sem, 4)
                
                # Regla de negocio: Camas completas de 5200 plantas promedio
                camas = math.ceil(plantas / 5200.0)
                plantas_redondeadas = camas * 5200
                
                records_finales.append({
                    'Flor': flor,
                    'Variedad': v_name,
                    'Semana_Pedido_MV': sem_pedido,
                    'Semana_Siembra': sem,
                    'Camas_Sugeridas': camas,
                    'Esquejes_Sugeridos (Optimizado ML)': plantas_redondeadas
                })
                
    df_opt = pd.DataFrame(records_finales)
    if not df_opt.empty:
        df_opt = df_opt.sort_values(['Semana_Pedido_MV', 'Variedad'])
    return df_opt


def generar_mva_clasico(db, df_target):
    """
    Genera el plan MVA (Material Vegetal) de forma clasica (deterministica)
    calculando (Meta / Aprovechamiento) y desplazando las semanas.
    """
    variedades = db.query(Variedad).filter(Variedad.activo == True).all()
    dict_vars = {v.nombre.strip().upper(): v for v in variedades}
    
    def map_variedad(v):
        v_upper = str(v).strip().upper()
        abrevs = {'VAL': 'VALENTINO', 'FREE': 'FREEDOM', 'MON': 'MONDIAL', 'EXC': 'EXPLORER', 'EXP': 'EXPLORER'}
        if v_upper in abrevs: v_upper = abrevs[v_upper]
        return dict_vars[v_upper].nombre if v_upper in dict_vars else None

    df_target = df_target.copy()
    df_target['Variedad_Exacta'] = df_target['Variedad'].apply(map_variedad)
    df_target['Semana_Objetivo_Clean'] = df_target['Semana_Objetivo'].apply(lambda x: str(x).replace('.0', '').strip())
    
    df_target['Exportable_Meta'] = pd.to_numeric(df_target['Exportable_Meta'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    df_target = df_target.groupby(['Variedad_Exacta', 'Semana_Objetivo_Clean'], as_index=False)['Exportable_Meta'].sum()
    
    records = []
    for _, row in df_target.iterrows():
        v_name_exact = row['Variedad_Exacta']
        if not v_name_exact: continue
        meta = row['Exportable_Meta']
        sem_obj = row['Semana_Objetivo_Clean']
        
        if meta > 0:
            var = dict_vars[v_name_exact.upper()]
            semanas_pico = max(10, int(round((var.dia_pico if var.dia_pico else 70) / 7.0)))
            sem_siembra = restar_semanas(sem_obj, semanas_pico)
            sem_pedido = restar_semanas(sem_siembra, 4)
            plantas_req = meta / (var.aprov_pp if var.aprov_pp > 0 else 1.0)
            
            records.append({
                'Flor': var.flor if var.flor else '',
                'Variedad': v_name_exact,
                'Semana_Pedido_MV': sem_pedido,
                'Semana_Siembra': sem_siembra,
                'Semana_Produccion_Objetivo': sem_obj,
                'Meta_Produccion_Tallos': meta,
                'Aprovechamiento_Usado': var.aprov_pp,
                'Esquejes_Requeridos_Base': plantas_req,
                'Esquejes_Sugeridos': math.ceil(plantas_req)
            })
            
    df_opt = pd.DataFrame(records)
    if not df_opt.empty:
        df_opt = df_opt.groupby(['Flor', 'Variedad', 'Semana_Pedido_MV', 'Semana_Siembra', 'Aprovechamiento_Usado'], as_index=False).agg({
            'Meta_Produccion_Tallos': 'sum',
            'Esquejes_Requeridos_Base': 'sum',
            'Esquejes_Sugeridos': 'sum'
        })
        df_opt = df_opt.sort_values(['Semana_Pedido_MV', 'Variedad'])
    return df_opt
