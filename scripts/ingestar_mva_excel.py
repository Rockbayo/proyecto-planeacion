import sys
import os
import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.core.database import SessionLocal
from app.models.models import DistribucionMVA

def ingestar_mva_inicial():
    file_path = "Analitica_Planeacion_2.0.xlsm"
    
    print("Leyendo tabla Plan a MVA...")
    df = pd.read_excel(file_path, sheet_name='Plan a MVA', skiprows=2, usecols='B:F', nrows=63)
    
    # Limpiar nulos
    df = df.dropna(subset=['Flor', 'Variedad', '%'])
    
    db = SessionLocal()
    try:
        # Borrar tabla actual
        db.query(DistribucionMVA).delete()
        
        for _, row in df.iterrows():
            temporada = str(row['Temporada']).strip().upper() if pd.notna(row['Temporada']) else "EVERY DAY"
            # Si era 'Every Day', asegurarnos de que quede igual que en el parser
            if temporada == "EVERY DAY":
                temporada = "EVERYDAY"
                
            flor = str(row['Flor']).strip() if pd.notna(row['Flor']) else ""
            flor_code = flor.title()
            
            color = str(row['Color']).strip() if pd.notna(row['Color']) else ""
            color_code = color.title()
            
            variedad = str(row['Variedad']).strip()
            porcentaje = float(row['%'])
            
            if variedad and porcentaje > 0:
                nuevo_mva = DistribucionMVA(
                    finca="ALL",
                    temporada=temporada,
                    flor=flor_code,
                    color=color_code,
                    variedad_nombre=variedad,
                    porcentaje=porcentaje
                )
                db.add(nuevo_mva)
        
        db.commit()
        count = db.query(DistribucionMVA).count()
        print(f"Éxito: {count} registros de DistribucionMVA insertados en la base de datos.")
        
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    ingestar_mva_inicial()

