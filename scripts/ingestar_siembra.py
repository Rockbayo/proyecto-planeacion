import sys
import os
import pandas as pd
from datetime import datetime

# Aadir el directorio raz al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import SessionLocal
from app.models.models import Variedad, Ubicacion, Siembra, EstadoSiembra

def parse_date(date_val):
    if pd.isna(date_val):
        return None
    if isinstance(date_val, datetime):
        return date_val.date()
    if isinstance(date_val, str):
        try:
            return datetime.strptime(date_val.split()[0], '%Y-%m-%d').date()
        except:
            pass
    return None

def ingestar_siembra_actual():
    print("Iniciando ingesta de 'Siembra Actual (16).xlsx'...")
    file_path = "Siembra Actual (16).xlsx"
    
    if not os.path.exists(file_path):
        print(f"Error: No se encontr el archivo {file_path}")
        return

    df = pd.read_excel(file_path, sheet_name="Export")
    db = SessionLocal()
    
    # 1. Cargar Variedades Únicas
    print("1. Extrayendo Variedades...")
    variedades_unicas = df[['Variedad', 'Flor', 'Color']].drop_duplicates().dropna(subset=['Variedad'])
    variedad_cache = {}
    
    for _, row in variedades_unicas.iterrows():
        nombre = str(row['Variedad']).strip()
        flor = str(row['Flor']).strip()
        color = str(row['Color']).strip()
        
        # Buscar de manera insensible a mayúsculas/minúsculas
        var_db = db.query(Variedad).filter(Variedad.nombre.ilike(nombre)).first()
        if not var_db:
            var_db = Variedad(nombre=nombre, flor=flor, color=color, aprov_pp=1.0)
            db.add(var_db)
            db.commit()
            db.refresh(var_db)
        variedad_cache[nombre] = var_db.id

    # 2. Cargar Ubicaciones Únicas
    print("2. Extrayendo Ubicaciones/Camas...")
    # Filtrar solo filas con siembras reales (excluir fila Total)
    df_valid = df.dropna(subset=['Variedad', 'Fecha de siembra']).copy()
    
    # Calcular área total de cada cama física (si una cama tiene múltiples siembras, sumar sus áreas)
    bed_areas = df_valid.groupby(['Sede', 'Bloque', 'Nave', 'Lado', 'Cama'])['Área (m2)'].sum().reset_index()
    ubicacion_cache = {}
    
    for _, row in bed_areas.iterrows():
        sede = str(row.get('Sede', 'CH')).strip()
        bloque = str(row['Bloque']).strip()
        nave = str(row['Nave']).strip()
        lado = str(row['Lado']).strip()
        cama = str(row['Cama']).strip()
        area = float(row.get('Área (m2)', 0.0))
        if pd.isna(area):
            area = 0.0
            
        loc_key = f"{sede}-{bloque}-{nave}-{lado}-{cama}"
        
        ubi_db = db.query(Ubicacion).filter(
            Ubicacion.sede == sede, Ubicacion.bloque == bloque, 
            Ubicacion.nave == nave, Ubicacion.lado == lado, Ubicacion.cama == cama
        ).first()
        
        if not ubi_db:
            ubi_db = Ubicacion(
                sede=sede, bloque=bloque, nave=nave, lado=lado, cama=cama,
                area_m2=area, capacidad_plantas=int(area * 87) # Densidad estimada 87 pls/m2 segun piloto
            )
            db.add(ubi_db)
            db.commit()
            db.refresh(ubi_db)
        else:
            # Actualizar el área de la cama física con la suma real de sus secciones
            ubi_db.area_m2 = area
            ubi_db.capacidad_plantas = int(area * 87)
            db.commit()
            
        ubicacion_cache[loc_key] = ubi_db.id

    # 3. Cargar Siembras (Lotes Físicos)
    print("3. Limpiando inventario anterior y registrando Lotes de Siembra Activos...")
    
    # IMPORTANTE: Como el archivo es un "snapshot" del inventario vivo actual,
    # debemos limpiar las siembras anteriores que ya no existen (fueron erradicadas).
    db.query(Siembra).delete()
    db.commit()
    
    siembras_agregadas = 0
    for _, row in df.iterrows():
        if pd.isna(row['Variedad']) or pd.isna(row['Fecha de siembra']):
            continue
            
        nombre_var = str(row['Variedad']).strip()
        var_id = variedad_cache.get(nombre_var)
        
        sede = str(row.get('Sede', 'CH')).strip()
        bloque = str(row['Bloque']).strip()
        nave = str(row['Nave']).strip()
        lado = str(row['Lado']).strip()
        cama = str(row['Cama']).strip()
        loc_key = f"{sede}-{bloque}-{nave}-{lado}-{cama}"
        ubi_id = ubicacion_cache.get(loc_key)
        
        fecha_siembra = parse_date(row['Fecha de siembra'])
        
        if var_id and ubi_id and fecha_siembra:
            plantas_sembradas = int(row.get('Plantas sembradas', 0))
            plantas_muertas = int(row.get('Plantas muertas', 0))
            area_lote = float(row.get('Área (m2)', 0.0))
            if pd.isna(area_lote):
                area_lote = 0.0
            
            nueva_siembra = Siembra(
                ubicacion_id=ubi_id,
                variedad_id=var_id,
                fecha_siembra=fecha_siembra,
                area_m2=area_lote,
                plantas_sembradas=plantas_sembradas,
                plantas_muertas=plantas_muertas,
                estado=EstadoSiembra.EN_PRODUCCION # Asumimos que si están vivas están en campo
            )
            db.add(nueva_siembra)
            siembras_agregadas += 1
                
    db.commit()
    db.close()
    print(f"Ingesta Finalizada! Se insertaron {len(variedad_cache)} Variedades, {len(ubicacion_cache)} Ubicaciones y {siembras_agregadas} Lotes sembrados.")

if __name__ == "__main__":
    ingestar_siembra_actual()
