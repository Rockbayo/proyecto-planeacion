import pandas as pd
import io
from app.services.forecast_service import generar_forecast_13wk
from app.core.database import SessionLocal

def procesar_plantillas_plataforma(templates_dict, df_forecast, df_plan=None):
    """
    templates_dict: { "nombre_archivo.xlsx": bytes_del_archivo }
    df_forecast: dataframe de proyeccion (con Variedad y semanas)
    df_plan: (opcional) dataframe con el plan de produccion por variedad y semana
    
    Retorna: { "nombre_archivo_procesado.xlsx": bytes_listos_para_descargar }
    """
    resultados = {}
    
    # Preparar df_forecast agrupado de forma insensible a mayúsculas/minúsculas
    if not df_forecast.empty:
        df_fc = df_forecast.copy()
        if 'Variedad' in df_fc.columns:
            df_fc['Variedad_norm'] = df_fc['Variedad'].astype(str).str.strip().str.lower()
            cols_num = [c for c in df_fc.columns if str(c).startswith('202')]
            fc_var = df_fc.groupby('Variedad_norm')[cols_num].sum()
        else:
            fc_var = pd.DataFrame()
    else:
        fc_var = pd.DataFrame()
        
    # Preparar df_plan agrupado de forma insensible a mayúsculas/minúsculas
    plan_var = pd.DataFrame()
    if df_plan is not None and not df_plan.empty:
        df_p = df_plan.copy()
        if 'Variedad' in df_p.columns:
            df_p['Variedad_norm'] = df_p['Variedad'].astype(str).str.strip().str.lower()
            cols_num = [c for c in df_p.columns if str(c).startswith('202')]
            plan_var = df_p.groupby('Variedad_norm')[cols_num].sum()
        else:
            df_p.index = df_p.index.astype(str).str.strip().str.lower()
            cols_num = [c for c in df_p.columns if str(c).startswith('202')]
            plan_var = df_p.groupby(level=0)[cols_num].sum()
        
    for filename, filebytes in templates_dict.items():
        try:
            # Cargar la plantilla preservando el nombre de hoja original
            excel_file = pd.ExcelFile(io.BytesIO(filebytes))
            sheet_name = excel_file.sheet_names[0] if excel_file.sheet_names else 'Plantilla'
            df = pd.read_excel(excel_file, sheet_name=sheet_name)
            
            # Extraer las columnas que son semanas
            cols_semanas = [c for c in df.columns if str(c).startswith('202')]
            
            # Separar en las primeras 10 semanas de corto plazo (Inventario Vivo) y las restantes (Plan MVA)
            semanas_forecast = cols_semanas[:10]
            semanas_plan = cols_semanas[10:]
            
            # Rellenar cada fila
            for idx, row in df.iterrows():
                variedad_original = row['Variedad']
                variedad_norm = str(variedad_original).strip().lower()
                
                # 1. Rellenar las primeras 10 semanas con el ForeCast (Inventario Vivo)
                for sem in semanas_forecast:
                    sem_str = str(int(sem)) if isinstance(sem, float) else str(sem)
                    valor_proyectado = 0
                    if not fc_var.empty and sem_str in fc_var.columns and variedad_norm in fc_var.index:
                        val = fc_var.loc[variedad_norm, sem_str]
                        if hasattr(val, 'iloc'):
                            val = val.iloc[0] if len(val) > 0 else 0
                        if pd.notna(val):
                            try:
                                valor_proyectado = int(round(float(val)))
                            except (ValueError, TypeError):
                                valor_proyectado = 0
                    df.at[idx, sem] = valor_proyectado
                
                # 2. Rellenar las ultimas semanas con el Plan de Produccion
                for sem in semanas_plan:
                    sem_str = str(int(sem)) if isinstance(sem, float) else str(sem)
                    valor_plan = 0
                    if not plan_var.empty and sem_str in plan_var.columns and variedad_norm in plan_var.index:
                        val = plan_var.loc[variedad_norm, sem_str]
                        if hasattr(val, 'iloc'):
                            val = val.iloc[0] if len(val) > 0 else 0
                        if pd.notna(val):
                            try:
                                valor_plan = int(round(float(val)))
                            except (ValueError, TypeError):
                                valor_plan = 0
                    
                    df.at[idx, sem] = valor_plan
            
            # Guardar en memoria
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name=sheet_name)
            output.seek(0)
            
            resultados[filename] = output.getvalue()
            
        except Exception as e:
            print(f"Error procesando {filename}: {e}")
            
    return resultados

