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
        
        var_db = db.query(Variedad).filter(Variedad.nombre == nombre).first()
        if not var_db:
            var_db = Variedad(nombre=nombre, flor=flor, color=color, aprov_pp=1.0)
            db.add(var_db)
            db.commit()
            db.refresh(var_db)
        variedad_cache[nombre] = var_db.id

    # 2. Cargar Ubicaciones Únicas
    print("2. Extrayendo Ubicaciones/Camas...")
    ubicaciones_unicas = df[['Sede', 'Bloque', 'Nave', 'Lado', 'Cama', 'Área (m2)']].drop_duplicates()
    ubicacion_cache = {}
    
    for _, row in ubicaciones_unicas.iterrows():
        sede = str(row.get('Sede', 'CH')).strip()
        bloque = str(row['Bloque']).strip()
        nave = str(row['Nave']).strip()
        lado = str(row['Lado']).strip()
        cama = str(row['Cama']).strip()
        area = float(row.get('Área (m2)', 0.0))
        
        # Clave nica para cach
        loc_key = f"{sede}-{bloque}-{nave}-{lado}-{cama}"
        
        ubi_db = db.query(Ubicacion).filter(
            Ubicacion.sede == sede, Ubicacion.bloque == bloque, 
            Ubicacion.nave == nave, Ubicacion.lado == lado, Ubicacion.cama == cama
        ).first()
        
        if pd.isna(area):
            area = 0.0
            
        if not ubi_db:
            ubi_db = Ubicacion(
                sede=sede, bloque=bloque, nave=nave, lado=lado, cama=cama,
                area_m2=area, capacidad_plantas=int(area * 87) # Densidad estimada 87 pls/m2 segun piloto
            )
            db.add(ubi_db)
            db.commit()
            db.refresh(ubi_db)
        ubicacion_cache[loc_key] = ubi_db.id

    # 3. Cargar Siembras (Lotes Fsicos)
    print("3. Registrando Lotes de Siembra Activos...")
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
            
            # Verificar si ya existe para evitar duplicados en mltiples ejecuciones
            siembra_db = db.query(Siembra).filter(
                Siembra.ubicacion_id == ubi_id,
                Siembra.variedad_id == var_id,
                Siembra.fecha_siembra == fecha_siembra
            ).first()
            
            if siembra_db:
                siembra_db.plantas_sembradas = plantas_sembradas
                siembra_db.plantas_muertas = plantas_muertas
            else:
                nueva_siembra = Siembra(
                    ubicacion_id=ubi_id,
                    variedad_id=var_id,
                    fecha_siembra=fecha_siembra,
                    plantas_sembradas=plantas_sembradas,
                    plantas_muertas=plantas_muertas,
                    estado=EstadoSiembra.EN_PRODUCCION # Asumimos que si estn vivas estn en campo
                )
                db.add(nueva_siembra)
                siembras_agregadas += 1
                
    db.commit()
    db.close()
    print(f"Ingesta Finalizada! Se insertaron {len(variedad_cache)} Variedades, {len(ubicacion_cache)} Ubicaciones y {siembras_agregadas} Lotes sembrados.")

if __name__ == "__main__":
    ingestar_siembra_actual()
