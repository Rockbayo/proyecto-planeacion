from datetime import timedelta, date
from sqlalchemy.orm import Session
import pandas as pd
from app.models.models import Siembra, Variedad, EstadoSiembra

def isocalendar_to_string(dt: date) -> str:
    """Convierte una fecha a formato AioSemana (ej. 202639).
    Se suma 1 dia para que el Domingo sea considerado el primer dia de la semana operativa."""
    dt_shifted = dt + timedelta(days=1)
    iso_year, iso_week, _ = dt_shifted.isocalendar()
    return f"{iso_year}{iso_week:02d}"

import os

def calcular_curvas_dinamicas(alpha: float = None, num_ciclos: int = None, db: Session = None, params_por_flor: dict = None):
    # Retorna un diccionario con las variedades y sus valores suavizados
    # { 'VariedadA': { 'aprov': 0.85, 'dia_inicio': 60, 'c1': ..., 'c15': ..., 'flor': 'Cushion' }, ... }
    dict_vars = {}
    if not os.path.exists('Historico_Curvas.csv'):
        return dict_vars
        
    try:
        df_full = pd.read_csv('Historico_Curvas.csv')
    except Exception:
        return dict_vars
        
    cortes_cols = [f'Corte {i}' for i in range(1, 16)]
    for c in cortes_cols:
        if c not in df_full.columns:
            df_full[c] = 0.0
            
    for f in ['FechaSiembra', 'FechaDesbotone', 'FechaInicioProduccion']:
        if f in df_full.columns:
            df_full[f] = pd.to_datetime(df_full[f], errors='coerce')
            
    if 'Variedad' not in df_full.columns:
        return dict_vars

    # Cargar calibración persistida si no se especifican parámetros manuales
    if params_por_flor is None:
        try:
            from app.services.calibracion_service import cargar_parametros_calibrados
            cal_data = cargar_parametros_calibrados()
            if cal_data.get('fecha_calibracion'):
                params_por_flor = cal_data.get('por_flor')
                if alpha is None:
                    alpha = float(cal_data.get('alpha', 1.0))
                if num_ciclos is None:
                    num_ciclos = int(cal_data.get('num_ciclos', 9))
        except Exception:
            pass

    if alpha is None:
        alpha = 1.0
    if num_ciclos is None:
        num_ciclos = 9

    # Mapeo de Variedad a Tipo de Flor
    v_to_flor = {}
    try:
        if db is not None:
            vars_db = db.query(Variedad).all()
            v_to_flor = {v.nombre.strip().lower(): v.flor.strip() for v in vars_db if v.nombre and v.flor}
        else:
            from app.core.database import SessionLocal
            with SessionLocal() as s_local:
                vars_db = s_local.query(Variedad).all()
                v_to_flor = {v.nombre.strip().lower(): v.flor.strip() for v in vars_db if v.nombre and v.flor}
    except Exception:
        pass
        
    variedades_nombres = df_full['Variedad'].dropna().unique()
    
    for var_name in variedades_nombres:
        df_var_all = df_full[df_full['Variedad'] == var_name].copy()
        if len(df_var_all) == 0:
            continue
            
        if 'FechaSiembra' in df_var_all.columns:
            df_var_all = df_var_all.sort_values('FechaSiembra')

        # Determinar alpha y ciclos según el Tipo de Flor de la variedad
        fl_var = v_to_flor.get(var_name.strip().lower(), '')
        fl_cap = fl_var.capitalize()

        if params_por_flor and fl_cap in params_por_flor:
            p_fl = params_por_flor[fl_cap]
            alpha_var = float(p_fl.get('alpha', alpha))
            ciclos_var = int(p_fl.get('num_ciclos', num_ciclos))
        else:
            alpha_var = alpha
            ciclos_var = num_ciclos
            
        # 1. Histórico Crudo Total
        total_plantas_hist = df_var_all['NumeroPlantas'].sum() if 'NumeroPlantas' in df_var_all.columns else 0
        sum_cortes_hist = df_var_all[cortes_cols].sum()
        total_tallos_hist = sum_cortes_hist.sum()
        aprov_hist = total_tallos_hist / total_plantas_hist if total_plantas_hist > 0 else 0.0
        
        curva_hist = {}
        for i in range(1, 16):
            c_val = sum_cortes_hist[f'Corte {i}']
            # Curva relativa a plantas para que sumen APROV
            curva_hist[f'c{i}'] = c_val / total_plantas_hist if total_plantas_hist > 0 else 0.0
            
        dias_inicio_list_hist = (df_var_all['FechaInicioProduccion'] - df_var_all['FechaSiembra']).dt.days.dropna()
        dia_inicio_hist = int(dias_inicio_list_hist.mean()) if not dias_inicio_list_hist.empty else 0
        
        # 2. Datos Nuevos (Últimos N Ciclos para esta variedad y flor)
        df_var_n = df_var_all.tail(ciclos_var)
        total_plantas_nuevo = df_var_n['NumeroPlantas'].sum() if 'NumeroPlantas' in df_var_n.columns else 0
        
        if total_plantas_nuevo == 0:
            aprov_nuevo = aprov_hist
            curva_nueva = curva_hist
            dia_inicio_nuevo = dia_inicio_hist
        else:
            sum_cortes_nuevo = df_var_n[cortes_cols].sum()
            total_tallos_nuevo = sum_cortes_nuevo.sum()
            aprov_nuevo = total_tallos_nuevo / total_plantas_nuevo if total_plantas_nuevo > 0 else 0.0
            
            curva_nueva = {}
            for i in range(1, 16):
                c_val = sum_cortes_nuevo[f'Corte {i}']
                curva_nueva[f'c{i}'] = c_val / total_plantas_nuevo if total_plantas_nuevo > 0 else 0.0
                
            dias_inicio_list = (df_var_n['FechaInicioProduccion'] - df_var_n['FechaSiembra']).dt.days.dropna()
            dia_inicio_nuevo = int(dias_inicio_list.mean()) if not dias_inicio_list.empty else 0
            
        # 3. Suavización Exponencial
        aprov_suav = (aprov_nuevo * alpha_var) + (aprov_hist * (1.0 - alpha_var))
        dia_inicio_suav = int((dia_inicio_nuevo * alpha_var) + (dia_inicio_hist * (1.0 - alpha_var)))
        
        curva_suav = {}
        for i in range(1, 16):
            curva_suav[f'c{i}'] = (curva_nueva[f'c{i}'] * alpha_var) + (curva_hist[f'c{i}'] * (1.0 - alpha_var))
            
        corte_max = max(curva_suav.items(), key=lambda k: k[1]) if sum(curva_suav.values()) > 0 else ('c1', 0)
        semana_pico = int(corte_max[0].replace('c', ''))
        dia_pico_suav = dia_inicio_suav + ((semana_pico - 1) * 7) + 3 # Estimación del dia pico
            
        res = {
            'flor': fl_cap,
            'alpha_usado': alpha_var,
            'num_ciclos_usado': ciclos_var,
            'aprov': aprov_suav,
            'dia_inicio': dia_inicio_suav,
            'dia_pico': dia_pico_suav
        }
        for i in range(1, 16):
            res[f'c{i}'] = curva_suav[f'c{i}']
            
        dict_vars[var_name] = res
        
    return dict_vars

def generar_forecast_13wk(db: Session, start_date: date = None, alpha: float = None, num_ciclos: int = None, params_por_flor: dict = None):
    """
    Calcula el ForeCast a 10 Semanas Móviles para todos los lotes en producción.
    Cruza el inventario de plantas vivas con la curva productiva de cada variedad.
    Aplica suavización exponencial dinámica segmentada por tipo de flor (Cushion, Daisy, Novelty).
    """
    if not start_date:
        start_date = date.today()
        
    # Calcular las curvas suavizadas dinámicamente con los parámetros calibrados por flor
    curvas_dinamicas = calcular_curvas_dinamicas(alpha=alpha, num_ciclos=num_ciclos, db=db, params_por_flor=params_por_flor)
        
    siembras = db.query(Siembra).filter(Siembra.estado == EstadoSiembra.EN_PRODUCCION).all()

    
    forecast_records = []
    
    for siembra in siembras:
        var = siembra.variedad
        ubi = siembra.ubicacion
        
        # Obtener parámetros dinámicos si existen, si no, usar los de la base de datos (fallback)
        if var.nombre in curvas_dinamicas:
            v_dyn = curvas_dinamicas[var.nombre]
            dia_inicio_var = v_dyn['dia_inicio']
            curvas = [v_dyn[f'c{i}'] for i in range(1, 16)]
        else:
            dia_inicio_var = var.dia_inicio if var.dia_inicio else 0
            curvas = [
                var.c1, var.c2, var.c3, var.c4, var.c5, 
                var.c6, var.c7, var.c8, var.c9, var.c10, 
                var.c11, var.c12, var.c13, var.c14, var.c15
            ]
            # Si en DB la suma de curvas es 1.0 pero aprov_pp es diferente, ajustarlo para S&OP
            suma_c = sum([c for c in curvas if c])
            if abs(suma_c - 1.0) < 0.01 and var.aprov_pp and var.aprov_pp != 1.0:
                curvas = [c * var.aprov_pp if c else 0.0 for c in curvas]
        
        # 1. Cuándo empieza a botar flor este lote?
        fecha_inicio_cosecha = siembra.fecha_siembra + timedelta(days=dia_inicio_var)
        
        # 2. Distribuir la cosecha a lo largo de los 15 días de corte
        for dia_indice, porcentaje_cosecha in enumerate(curvas):
            if porcentaje_cosecha and porcentaje_cosecha > 0:
                # Calcular la fecha exacta de ese día de cosecha
                fecha_corte_dia = fecha_inicio_cosecha + timedelta(days=dia_indice)
                
                # Convertirla al formato operativo de planeacion
                semana_operativa = isocalendar_to_string(fecha_corte_dia)
                
                # 3. Lógica Core de S&OP
                tallos_esperados = siembra.plantas_sembradas * porcentaje_cosecha
                
                if tallos_esperados > 0:
                    forecast_records.append({
                        "Sede": ubi.sede,
                        "Bloque": ubi.bloque,
                        "Cama": ubi.cama,
                        "Flor": var.flor,
                        "Color": var.color,
                        "Variedad": var.nombre,
                        "Semana_Siembra": isocalendar_to_string(siembra.fecha_siembra),
                        "Semana_Cosecha": semana_operativa,
                        "Tallos_Proyectados": int(tallos_esperados)
                    })
                    
    # Convertir a DataFrame
    if forecast_records:
        df = pd.DataFrame(forecast_records)
        df_pivot = pd.pivot_table(
            df, 
            values='Tallos_Proyectados', 
            index=['Sede', 'Flor', 'Color', 'Variedad'], 
            columns=['Semana_Cosecha'], 
            aggfunc='sum',
            fill_value=0
        ).reset_index()
    else:
        df_pivot = pd.DataFrame()
        
    # Obtener TODAS las variedades de la base de datos para no omitir ninguna
    todas_variedades = db.query(Variedad).all()
    lista_vars = []
    for v in todas_variedades:
        lista_vars.append({
            "Sede": "",
            "Flor": v.flor,
            "Color": v.color,
            "Variedad": v.nombre
        })
    df_todas = pd.DataFrame(lista_vars)
    
    if not df_pivot.empty:
        df_final = pd.merge(df_todas, df_pivot, on=['Flor', 'Color', 'Variedad'], how='left', suffixes=('_orig', ''))
        if 'Sede' in df_final.columns and 'Sede_orig' in df_final.columns:
            df_final['Sede'] = df_final['Sede'].fillna(df_final['Sede_orig'])
            df_final = df_final.drop(columns=['Sede_orig'])
        df_final = df_final.fillna(0)
    else:
        df_final = df_todas
        
    return df_final


def calcular_distribucion_diaria_curvas(db: Session):
    """
    Calcula el porcentaje de distribucion diaria de cosecha (Lunes a Domingo)
    agrupado por Flor. Se basa en el cruce del inventario vivo y las curvas
    de las variedades (para los proximos 90 dias).
    """
    start_date = date.today()
    siembras = db.query(Siembra).filter(Siembra.estado == EstadoSiembra.EN_PRODUCCION).all()
    
    records = []
    for siembra in siembras:
        var = siembra.variedad
        
        fecha_inicio_cosecha = siembra.fecha_siembra + timedelta(days=var.dia_inicio)
        curvas = [var.c1, var.c2, var.c3, var.c4, var.c5, var.c6, var.c7, var.c8, var.c9, var.c10, var.c11, var.c12, var.c13, var.c14, var.c15]
        
        for dia_indice, porcentaje_cosecha in enumerate(curvas):
            if porcentaje_cosecha and porcentaje_cosecha > 0:
                fecha_corte_dia = fecha_inicio_cosecha + timedelta(days=dia_indice)
                
                # Solo los proximos 90 dias
                if fecha_corte_dia >= start_date and (fecha_corte_dia - start_date).days <= 90:
                    tallos_esperados = siembra.plantas_sembradas * porcentaje_cosecha
                    if tallos_esperados > 0:
                        records.append({
                            "Flor": var.flor,
                            "Weekday": fecha_corte_dia.weekday(), # 0=Mon, 1=Tue... 6=Sun
                            "Tallos": tallos_esperados
                        })

    if not records:
        return {}
        
    df = pd.DataFrame(records)
    df_agrupado = df.groupby(["Flor", "Weekday"])["Tallos"].sum().reset_index()
    df_totales = df_agrupado.groupby("Flor")["Tallos"].sum().reset_index().rename(columns={"Tallos": "Total"})
    
    df_calc = pd.merge(df_agrupado, df_totales, on="Flor")
    df_calc["Pct"] = (df_calc["Tallos"] / df_calc["Total"]) * 100
    
    df_pivot = df_calc.pivot(index="Flor", columns="Weekday", values="Pct").fillna(0)
    
    dias_nombres = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
    df_pivot = df_pivot.rename(columns=dias_nombres)
    
    # Asegurar que existan todas las columnas
    for dia in dias_nombres.values():
        if dia not in df_pivot.columns:
            df_pivot[dia] = 0.0
            
    # Reordenar columnas
    df_pivot = df_pivot[["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]]
    
    # Convertir a dict { "Cushion": {"Lunes": 14.5, ...}, ... }
    return df_pivot.to_dict(orient="index")

def generar_forecast_ml_live(db: Session, start_date: date = None, semanas_a_proyectar: int = 13, df_plan_mva: pd.DataFrame = None):
    import joblib
    import os
    
    if not os.path.exists('ml_model.pkl') or not os.path.exists('ml_features.pkl'):
        return pd.DataFrame()
        
    try:
        model = joblib.load('ml_model.pkl')
        ml_features = joblib.load('ml_features.pkl')
    except:
        return pd.DataFrame()
        
    if not start_date:
        start_date = date.today()
        
    # Obtener inventario vivo actual de la DB
    siembras = db.query(Siembra).all()
    
    # Agrupar siembras por Variedad y Semana de Siembra
    inventario_dict = {}
    for s in siembras:
        var_name = s.variedad.nombre
        sem_siembra = isocalendar_to_string(s.fecha_siembra)
        if var_name not in inventario_dict:
            inventario_dict[var_name] = {}
        inventario_dict[var_name][sem_siembra] = inventario_dict[var_name].get(sem_siembra, 0) + s.plantas_sembradas
        
    # Integrar las siembras futuras planeadas (MVA) para que el modelo ML pueda proyectar > 9 semanas
    # Solo tomamos las siembras planeadas desde la semana actual en adelante para evitar duplicar
    # con el inventario vivo que ya está sembrado en la BD.
    semana_actual = isocalendar_to_string(start_date)
    if df_plan_mva is not None and not df_plan_mva.empty:
        for _, row in df_plan_mva.iterrows():
            var_name = row.get('Variedad', '')
            sem_siembra = str(row.get('Semana_Siembra', ''))
            plantas = row.get('Esquejes_Para_Siembra (Final)', 0)
            if var_name and sem_siembra and plantas > 0 and sem_siembra >= semana_actual:
                if var_name not in inventario_dict:
                    inventario_dict[var_name] = {}
                inventario_dict[var_name][sem_siembra] = inventario_dict[var_name].get(sem_siembra, 0) + plantas
        
    # Construir data a proyectar
    semanas_futuras = []
    fecha_iter = start_date
    for _ in range(semanas_a_proyectar):
        semanas_futuras.append(isocalendar_to_string(fecha_iter))
        fecha_iter += timedelta(days=7)
        
    def restar_semanas(semana_str, n_semanas):
        year = int(semana_str[:4])
        week = int(semana_str[4:])
        week -= n_semanas
        while week <= 0:
            year -= 1
            week += 52
        return f"{year}{week:02d}"
        
    # Todas las variedades activas
    todas_variedades = db.query(Variedad).filter(Variedad.activo == True).all()
    
    dataset = []
    for var in todas_variedades:
        var_name = var.nombre
        for sem_futura in semanas_futuras:
            semana_del_año = int(sem_futura[4:])
            
            record = {
                'Sede': 'CH', # Default
                'Flor': var.flor,
                'Color': var.color,
                'Variedad': var_name,
                'Semana_Cosecha': sem_futura,
                'Estacionalidad_Semana': semana_del_año
            }
            
            # Construir variables dummy igual que en entrenamiento
            for f in ml_features:
                if f.startswith('Variedad_'):
                    v_feat = f.replace('Variedad_', '')
                    record[f] = 1 if v_feat == var_name else 0
                    
            # Construir lags (10 a 16)
            for lag in range(10, 17):
                sem_siembra_lag = restar_semanas(sem_futura, lag)
                plantas = inventario_dict.get(var_name, {}).get(sem_siembra_lag, 0)
                record[f'Lag_{lag}'] = plantas
                
            dataset.append(record)
            
    if not dataset:
        return pd.DataFrame()
        
    df_live = pd.DataFrame(dataset)
    
    # Asegurar que todas las columnas del modelo estén presentes
    for col in ml_features:
        if col not in df_live.columns:
            df_live[col] = 0
            
    # Ordenar columnas exactamente como espera el modelo
    X_live = df_live[ml_features]
    
    preds = model.predict(X_live)
    df_live['Tallos_Proyectados'] = preds
    df_live['Tallos_Proyectados'] = df_live['Tallos_Proyectados'].apply(lambda x: int(max(0, x)))
    
    # Pivotear igual que el forecast clásico
    df_pivot = pd.pivot_table(
        df_live, 
        values='Tallos_Proyectados', 
        index=['Sede', 'Flor', 'Color', 'Variedad'], 
        columns=['Semana_Cosecha'], 
        aggfunc='sum',
        fill_value=0
    ).reset_index()
    
    return df_pivot
