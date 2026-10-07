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
    
    # Asegurarnos de que el forecast este agrupado por Variedad y Semana_Cosecha
    if not df_forecast.empty:
        # El df_forecast devuelto por generar_forecast_13wk ya es un pivot table
        # con index=['Sede', 'Flor', 'Color', 'Variedad'] y columns=['Semana_Cosecha']
        # Vamos a colapsarlo a nivel de variedad para facilitar la busqueda
        fc_var = df_forecast.groupby('Variedad').sum()
        # Normalizar el indice (nombres de variedades) para evitar errores de mayusculas/minusculas
        fc_var.index = fc_var.index.str.strip().str.lower()
    else:
        fc_var = pd.DataFrame()
        
    for filename, filebytes in templates_dict.items():
        try:
            # Cargar la plantilla
            df = pd.read_excel(io.BytesIO(filebytes), sheet_name=0)
            
            # Extraer las columnas que son semanas
            cols_semanas = [c for c in df.columns if str(c).startswith('202')]
            
            # Separar en las primeras 9 y las restantes
            semanas_forecast = cols_semanas[:9]
            semanas_plan = cols_semanas[9:]
            
            # Rellenar cada fila
            for idx, row in df.iterrows():
                variedad_original = row['Variedad']
                variedad_norm = str(variedad_original).strip().lower()
                
                # 1. Rellenar las primeras 9 semanas con el ForeCast
                for sem in semanas_forecast:
                    sem_str = str(int(sem)) if isinstance(sem, float) else str(sem)
                    valor_proyectado = 0
                    if not fc_var.empty and sem_str in fc_var.columns and variedad_norm in fc_var.index:
                        valor_proyectado = fc_var.loc[variedad_norm, sem_str]
                    df.at[idx, sem] = int(valor_proyectado)
                
                # 2. Rellenar las ultimas semanas con el Plan de Produccion
                for sem in semanas_plan:
                    sem_str = str(int(sem)) if isinstance(sem, float) else str(sem)
                    valor_plan = 0
                    if df_plan is not None and not df_plan.empty and sem_str in df_plan.columns and variedad_norm in df_plan.index:
                        valor_plan = df_plan.loc[variedad_norm, sem_str]
                    
                    df.at[idx, sem] = int(valor_plan)
            
            # Guardar en memoria
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Plantilla')
            output.seek(0)
            
            resultados[filename] = output.getvalue()
            
        except Exception as e:
            print(f"Error procesando {filename}: {e}")
            
    return resultados

