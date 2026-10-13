import pandas as pd
import numpy as np
from datetime import timedelta, date
from xgboost import XGBRegressor
import joblib
import os

def isocalendar_to_string(dt):
    dt_shifted = dt + timedelta(days=1)
    iso_year, iso_week, _ = dt_shifted.isocalendar()
    return f"{iso_year}{iso_week:02d}"

def restar_semanas(semana_str, n_semanas):
    year = int(semana_str[:4])
    week = int(semana_str[4:])
    week -= n_semanas
    while week <= 0:
        year -= 1
        week += 52
    return f"{year}{week:02d}"

def entrenar_modelo_xgboost():
    print("Cargando datos históricos para entrenar XGBoost Avanzado...")
    try:
        df_siembras = pd.read_excel('Detalle (3).xlsx')
        df_prod = pd.read_excel('Cumplimientos PER 4 y PER 1, Plan de producción, año anterior y Dumps.xlsx')
    except Exception as e:
        print(f"Error cargando datos: {e}")
        return False
        
    df_prod = df_prod[df_prod['Sede'].isin(['CH', 'FD'])]
    df_prod['Semana_str'] = df_prod['Semana'].astype(str)
    df_real = df_prod.groupby(['Variedad', 'Semana_str'])['Exportable'].sum().reset_index()

    if 'Fecha de siembra' not in df_siembras.columns:
        df_siembras.rename(columns=lambda x: x.replace('Fecha de Siembra', 'Fecha de siembra'), inplace=True)
        
    df_siembras['Fecha de siembra'] = pd.to_datetime(df_siembras['Fecha de siembra'], errors='coerce')
    df_siembras = df_siembras.dropna(subset=['Fecha de siembra', 'Variedad', 'Plantas sembradas'])
    df_siembras['Semana_Siembra'] = df_siembras['Fecha de siembra'].apply(isocalendar_to_string)
    df_siembras_grp = df_siembras.groupby(['Variedad', 'Semana_Siembra'])['Plantas sembradas'].sum().reset_index()

    siembras_dict = {}
    for _, row in df_siembras_grp.iterrows():
        var = row['Variedad']
        sem = row['Semana_Siembra']
        if var not in siembras_dict:
            siembras_dict[var] = {}
        siembras_dict[var][sem] = row['Plantas sembradas']

    dataset = []
    for _, row in df_real.iterrows():
        var = row['Variedad']
        sem_corte = row['Semana_str']
        target = row['Exportable']
        
        if sem_corte >= "202510":
            semana_del_año = int(sem_corte[4:])
            record = {
                'Variedad': var,
                'Semana': sem_corte,
                'Target_Exportable': target,
                'Estacionalidad_Semana': semana_del_año
            }
            # Lags 9 a 16 para capturar mejor los picos y colas
            for lag in range(9, 17):
                sem_siembra = restar_semanas(sem_corte, lag)
                plantas = siembras_dict.get(var, {}).get(sem_siembra, 0)
                record[f'Lag_{lag}'] = plantas
            dataset.append(record)

    df_ml = pd.DataFrame(dataset)
    df_ml = pd.get_dummies(df_ml, columns=['Variedad'])

    X = df_ml.drop(columns=['Semana', 'Target_Exportable'])
    y = df_ml['Target_Exportable']

    model = XGBRegressor(n_estimators=200, max_depth=6, learning_rate=0.05, objective='reg:squarederror', random_state=42)
    model.fit(X, y)

    joblib.dump(model, 'ml_model_xgb.pkl')
    joblib.dump(list(X.columns), 'ml_features_xgb.pkl')
    print("Modelo XGBoost entrenado y guardado con éxito.")
    return True

if __name__ == "__main__":
    entrenar_modelo_xgboost()

