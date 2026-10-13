import os
import glob
import pandas as pd
from sqlalchemy.orm import Session
from app.models.models import Variedad

def procesar_archivos_variedades(archivos_o_rutas, db: Session):
    """
    Procesa uno o múltiples archivos de Listado de Variedades (ej. Cushion, Daisy, Novelty).
    Actualiza o inserta en la base de datos para garantizar que no existan 'Genéricos'.
    Retorna un diccionario con estadísticas del proceso.
    """
    dfs = []
    
    for f in archivos_o_rutas:
        try:
            if isinstance(f, str):
                df = pd.read_excel(f)
            else:
                # Es un objeto UploadedFile de Streamlit
                df = pd.read_excel(f)
            
            # Normalizar nombres de columnas a minúsculas y sin espacios
            df.columns = [str(c).strip().lower() for c in df.columns]
            
            # Mapeo flexible de columnas esperadas
            col_map = {}
            for c in df.columns:
                if 'variedad' in c:
                    col_map[c] = 'variedad'
                elif 'flor' in c:
                    col_map[c] = 'flor'
                elif 'color' in c:
                    col_map[c] = 'color'
                elif 'estado' in c:
                    col_map[c] = 'estado'
                elif 'tiempo' in c or 'ciclo' in c:
                    col_map[c] = 'tiempodeciclo'
            
            df = df.rename(columns=col_map)
            
            if 'variedad' in df.columns:
                dfs.append(df)
        except Exception as e:
            print(f"Error procesando archivo de variedades: {e}")
            
    if not dfs:
        return {"total": 0, "insertadas": 0, "actualizadas": 0, "error": "No se pudieron leer datos válidos"}
        
    df_total = pd.concat(dfs, ignore_index=True)
    df_total = df_total.dropna(subset=['variedad'])
    
    # Obtener variedades existentes en base de datos
    vars_db = db.query(Variedad).all()
    vars_dict = {v.nombre.strip().lower(): v for v in vars_db}
    
    insertadas = 0
    actualizadas = 0
    
    # Registrar variedades del listado
    for _, row in df_total.iterrows():
        nombre_orig = str(row['variedad']).strip()
        nombre_norm = nombre_orig.lower()
        if not nombre_norm:
            continue
            
        flor = str(row.get('flor', '')).strip().capitalize() if pd.notna(row.get('flor')) else 'Desconocida'
        color = str(row.get('color', '')).strip().capitalize() if pd.notna(row.get('color')) else 'Genérico'
        estado_str = str(row.get('estado', 'Activa')).strip().lower()
        activo = (estado_str == 'activa')
        
        # Calcular fenología tentativa por TiempoDeCiclo si está disponible
        dias_ciclo = None
        if 'tiempodeciclo' in row and pd.notna(row['tiempodeciclo']):
            try:
                sem = int(row['tiempodeciclo'])
                dias_ciclo = sem * 7
            except:
                pass
                
        if nombre_norm in vars_dict:
            var_existente = vars_dict[nombre_norm]
            # Si tiene flor y color válidos, actualizar
            if flor and flor != 'Desconocida':
                var_existente.flor = flor
            if color and color != 'Genérico':
                var_existente.color = color
            var_existente.activo = activo
            if dias_ciclo and var_existente.dia_pico == 0:
                var_existente.dia_pico = dias_ciclo
                var_existente.dia_inicio = max(dias_ciclo - 7, 0)
            actualizadas += 1
        else:
            dia_pico = dias_ciclo if dias_ciclo else 70
            dia_inicio = max(dia_pico - 7, 0)
            nueva_var = Variedad(
                nombre=nombre_orig,
                flor=flor if flor != 'Desconocida' else 'Novelty',
                color=color if color != 'Genérico' else 'Mix',
                dia_pico=dia_pico,
                dia_inicio=dia_inicio,
                aprov_pp=1.0,
                activo=activo
            )
            db.add(nueva_var)
            vars_dict[nombre_norm] = nueva_var
            insertadas += 1
            
    # Guardar archivo consolidado maestro local para persistencia
    try:
        master_file = "ListaDeVariedad_master.xlsx"
        df_save = df_total.drop_duplicates(subset=['variedad'])
        df_save.to_excel(master_file, index=False)
    except Exception as e:
        print(f"Error guardando master excel: {e}")
        
    db.commit()
    
    total_db = db.query(Variedad).count()
    return {
        "total_en_db": total_db,
        "insertadas": insertadas,
        "actualizadas": actualizadas,
        "total_leidas": len(df_total)
    }

def asegurar_variedades_iniciales(db: Session):
    """
    Verifica si existen archivos ListaDeVariedad*.xlsx en la carpeta raíz y los carga
    si la base de datos tiene menos variedades de las que existen en los archivos.
    """
    total_db = db.query(Variedad).count()
    archivos = sorted(glob.glob("ListaDeVariedad*.xlsx"))
    if archivos and total_db < 200:
        return procesar_archivos_variedades(archivos, db)
    return {"total_en_db": total_db, "insertadas": 0, "actualizadas": 0}

