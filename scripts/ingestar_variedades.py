import sys
import os
import pandas as pd
import numpy as np

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import SessionLocal
from app.models.models import Variedad

def ingestar_variedades_reales():
    print("Leyendo Datos_Variedades del archivo Analitica_Planeacion_2.0.xlsm...")
    df = pd.read_excel("Analitica_Planeacion_2.0.xlsm", sheet_name="Datos_Variedades", header=2)
    
    # Limpiar columnas
    df = df.dropna(subset=['Variedad', 'Flor', 'Color'])
    
    db = SessionLocal()
    
    # Actualizar o insertar
    for _, row in df.iterrows():
        nombre_var = str(row['Variedad']).strip()
        
        var_db = db.query(Variedad).filter(Variedad.nombre == nombre_var).first()
        if var_db:
            var_db.flor = str(row['Flor']).strip()
            var_db.color = str(row['Color']).strip()
            var_db.dia_inicio = int(row['Dia_Inicio']) if pd.notna(row['Dia_Inicio']) else 70
            var_db.dia_pico = int(row['Dia_Pico']) if pd.notna(row['Dia_Pico']) else 75
            var_db.dias_desb = int(row['Dias_Desb']) if pd.notna(row['Dias_Desb']) else 30
            var_db.aprov_pp = float(row['Aprov_PP']) if pd.notna(row['Aprov_PP']) else 0.90
            
            # Curvas
            var_db.c1 = float(row['C1']) if pd.notna(row['C1']) else 0.0
            var_db.c2 = float(row['C2']) if pd.notna(row['C2']) else 0.0
            var_db.c3 = float(row['C3']) if pd.notna(row['C3']) else 0.0
            var_db.c4 = float(row['C4']) if pd.notna(row['C4']) else 0.0
            var_db.c5 = float(row['C5']) if pd.notna(row['C5']) else 0.0
            var_db.c6 = float(row['C6']) if pd.notna(row['C6']) else 0.0
            var_db.c7 = float(row['C7']) if pd.notna(row['C7']) else 0.0
            var_db.c8 = float(row['C8']) if pd.notna(row['C8']) else 0.0
            var_db.c9 = float(row['C9']) if pd.notna(row['C9']) else 0.0
            var_db.c10 = float(row['C10']) if pd.notna(row['C10']) else 0.0
            var_db.c11 = float(row['C11']) if pd.notna(row['C11']) else 0.0
            var_db.c12 = float(row['C12']) if pd.notna(row['C12']) else 0.0
            var_db.c13 = float(row['C13']) if pd.notna(row['C13']) else 0.0
            var_db.c14 = float(row['C14']) if pd.notna(row['C14']) else 0.0
            var_db.c15 = float(row['C15']) if pd.notna(row['C15']) else 0.0
        else:
            # Si no existe, la creamos (aunque ingestar_siembra debi haberlas creado)
            pass
            
    db.commit()
    db.close()
    print("Variedades actualizadas con la data real fenolgica.")

if __name__ == "__main__":
    ingestar_variedades_reales()

