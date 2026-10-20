import pandas as pd
import io
import openpyxl
from app.services.forecast_service import generar_forecast_13wk
from app.core.database import SessionLocal
from app.services.mva_service import extraer_semana_iso

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
        # Intento 1: Usar openpyxl para preservar 100% el formato, estilos, colores y fuentes
        processed_with_openpyxl = False
        try:
            wb = openpyxl.load_workbook(io.BytesIO(filebytes))
            ws = wb.active
            
            # Detectar fila de encabezados y columna de Variedad
            header_row = 1
            col_var_idx = None
            col_semanas_map = {} # {col_idx: iso_semana}
            
            for r in range(1, min(10, ws.max_row + 1)):
                temp_map = {}
                v_idx = None
                for c in range(1, ws.max_column + 1):
                    val = ws.cell(r, c).value
                    if val is not None:
                        s_val = str(val).strip().lower()
                        if 'variedad' in s_val:
                            v_idx = c
                        iso = extraer_semana_iso(val)
                        if iso:
                            temp_map[c] = iso
                if temp_map and v_idx:
                    header_row = r
                    col_var_idx = v_idx
                    col_semanas_map = temp_map
                    break

            if col_var_idx and col_semanas_map:
                cols_ordenadas = sorted(col_semanas_map.keys())
                semanas_forecast = cols_ordenadas[:9]
                semanas_plan = cols_ordenadas[9:]
                
                for r in range(header_row + 1, ws.max_row + 1):
                    var_val = ws.cell(r, col_var_idx).value
                    if not var_val:
                        continue
                    var_norm = str(var_val).strip().lower()
                    
                    # 1. Rellenar las primeras 9 semanas con Inventario Vivo (fc_var)
                    for c in semanas_forecast:
                        iso_wk = col_semanas_map[c]
                        val_num = 0
                        if not fc_var.empty and iso_wk in fc_var.columns and var_norm in fc_var.index:
                            v = fc_var.loc[var_norm, iso_wk]
                            if hasattr(v, 'iloc'):
                                v = v.iloc[0] if len(v) > 0 else 0
                            if pd.notna(v):
                                try:
                                    val_num = int(round(float(v)))
                                except (ValueError, TypeError):
                                    val_num = 0
                        ws.cell(r, c).value = val_num
                        
                    # 2. Rellenar las semanas restantes con Plan Maestro (plan_var)
                    for c in semanas_plan:
                        iso_wk = col_semanas_map[c]
                        val_num = 0
                        if not plan_var.empty and iso_wk in plan_var.columns and var_norm in plan_var.index:
                            v = plan_var.loc[var_norm, iso_wk]
                            if hasattr(v, 'iloc'):
                                v = v.iloc[0] if len(v) > 0 else 0
                            if pd.notna(v):
                                try:
                                    val_num = int(round(float(v)))
                                except (ValueError, TypeError):
                                    val_num = 0
                        ws.cell(r, c).value = val_num
                        
                out = io.BytesIO()
                wb.save(out)
                resultados[filename] = out.getvalue()
                processed_with_openpyxl = True
        except Exception as e_op:
            print(f"Advertencia openpyxl en {filename}: {e_op}")
            processed_with_openpyxl = False
            
        if processed_with_openpyxl:
            continue
            
        # Fallback con pandas si openpyxl falla
        try:
            excel_file = pd.ExcelFile(io.BytesIO(filebytes))
            sheet_name = excel_file.sheet_names[0] if excel_file.sheet_names else 'Plantilla'
            df = pd.read_excel(excel_file, sheet_name=sheet_name)
            
            # Detectar columna variedad y mapeo de semanas
            col_var = None
            for c in df.columns:
                if 'variedad' in str(c).lower():
                    col_var = c
                    break
            if not col_var:
                col_var = 'Variedad' if 'Variedad' in df.columns else None
                
            mapa_sem = {}
            for c in df.columns:
                iso = extraer_semana_iso(c)
                if iso:
                    mapa_sem[c] = iso
                    
            cols_semanas = list(mapa_sem.keys())
            semanas_forecast = cols_semanas[:9]
            semanas_plan = cols_semanas[9:]
            
            for idx, row in df.iterrows():
                if not col_var or pd.isna(row[col_var]):
                    continue
                variedad_norm = str(row[col_var]).strip().lower()
                
                for sem in semanas_forecast:
                    iso_wk = mapa_sem[sem]
                    val_num = 0
                    if not fc_var.empty and iso_wk in fc_var.columns and variedad_norm in fc_var.index:
                        v = fc_var.loc[variedad_norm, iso_wk]
                        if hasattr(v, 'iloc'):
                            v = v.iloc[0] if len(v) > 0 else 0
                        if pd.notna(v):
                            try:
                                val_num = int(round(float(v)))
                            except (ValueError, TypeError):
                                val_num = 0
                    df.at[idx, sem] = val_num
                    
                for sem in semanas_plan:
                    iso_wk = mapa_sem[sem]
                    val_num = 0
                    if not plan_var.empty and iso_wk in plan_var.columns and variedad_norm in plan_var.index:
                        v = plan_var.loc[variedad_norm, iso_wk]
                        if hasattr(v, 'iloc'):
                            v = v.iloc[0] if len(v) > 0 else 0
                        if pd.notna(v):
                            try:
                                val_num = int(round(float(v)))
                            except (ValueError, TypeError):
                                val_num = 0
                    df.at[idx, sem] = val_num
                    
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name=sheet_name)
            output.seek(0)
            resultados[filename] = output.getvalue()
        except Exception as e:
            print(f"Error procesando {filename}: {e}")
            
    return resultados
