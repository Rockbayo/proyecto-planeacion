import os
import sys
import glob
import pandas as pd
from datetime import timedelta

# Asegurar que los módulos del app puedan importarse
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from app.services.forecast_service import calcular_curvas_dinamicas

def get_iso_week_string(dt) -> str:
    # Como en forecast_service
    dt_shifted = dt + timedelta(days=1)
    iso_year, iso_week, _ = dt_shifted.isocalendar()
    return f"{iso_year}{iso_week:02d}"

def add_weeks_to_iso(iso_str, weeks):
    iso_year = int(iso_str[:4])
    iso_week = int(iso_str[4:])
    iso_week += weeks
    while iso_week > 52:
        iso_year += 1
        iso_week -= 52
    return f"{iso_year}{iso_week:02d}"

def iterar():
    print("Cargando Cumplimientos...")
    f1 = glob.glob('Cumplimientos*.xlsx')[0]
    df_cump = pd.read_excel(f1)
    
    # Normalizar variedad y semana
    df_cump['Variedad'] = df_cump['Variedad'].astype(str).str.strip().str.lower()
    df_cump['Semana'] = df_cump['Semana'].astype(str)
    # Agrupar producción real
    df_real = df_cump.groupby(['Variedad', 'Semana'])['Exportable'].sum().to_dict()
    
    print("Cargando Detalle de Siembras...")
    f2 = 'Detalle (3).xlsx'
    df_det = pd.read_excel(f2)
    df_det = df_det.dropna(subset=['Variedad', 'Fecha de siembra', 'Plantas sembradas'])
    
    plantings = []
    for _, row in df_det.iterrows():
        var = str(row['Variedad']).strip().lower()
        fecha = pd.to_datetime(row['Fecha de siembra'])
        plantas = float(row['Plantas sembradas'])
        if plantas <= 0:
            continue
        sem_siembra = get_iso_week_string(fecha)
        plantings.append((var, sem_siembra, plantas))
        
    print(f"Siembras cargadas: {len(plantings)}")
    
    alphas = [0.0, 0.3, 0.5, 0.7, 0.9, 1.0]
    ciclos = [1, 5, 9, 15]
    
    resultados = []
    
    for alpha in alphas:
        for c in ciclos:
            print(f"Procesando Alpha={alpha}, Ciclos={c}...")
            dyn_curves = calcular_curvas_dinamicas(alpha, c)
            dyn_curves_raw = calcular_curvas_dinamicas(alpha, c)
            dyn_curves = {str(k).strip().lower(): v for k, v in dyn_curves_raw.items()}
            
            projected = {}
            for var, sem_siembra, plantas in plantings:
                if var not in dyn_curves:
                    continue
                    
                curva_info = dyn_curves[var]
                aprov = curva_info['aprov']
                dia_inicio = curva_info['dia_inicio']
                
                tallos_totales = plantas * aprov
                
                # Calcular la semana de inicio del corte (Suma dia_inicio)
                semanas_desfase = dia_inicio // 7
                sem_inicio_corte = add_weeks_to_iso(sem_siembra, semanas_desfase)
                
                for i in range(1, 16):
                    pct = curva_info[f'c{i}']
                    if pct > 0:
                        sem_corte = add_weeks_to_iso(sem_inicio_corte, i - 1)
                        k = (var, sem_corte)
                        projected[k] = projected.get(k, 0) + (tallos_totales * pct)
                        
            # Calcular Error Medio Absoluto (MAE)
            errores = []
            matches = 0
            
            # Solo comparamos en las llaves (Variedad, Semana) que existan en lo Real
            for k, real_qty in df_real.items():
                if pd.isna(real_qty) or real_qty <= 0:
                    continue
                proj_qty = projected.get(k, 0)
                if proj_qty > 0:
                    matches += 1
                errores.append(abs(real_qty - proj_qty))
                
            if len(errores) > 0:
                mae = sum(errores) / len(errores)
            else:
                mae = 9999999
                
            resultados.append({
                'Alpha': alpha,
                'Ciclos': c,
                'Matches': matches,
                'MAE': mae
            })
            
    print("\n=== RESULTADOS DE ITERACIÓN ===")
    df_res = pd.DataFrame(resultados).sort_values('MAE')
    print(df_res.to_string(index=False))
    
if __name__ == '__main__':
    iterar()
