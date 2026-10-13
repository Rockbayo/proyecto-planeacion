import os
import sys
import pandas as pd

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from app.core.database import SessionLocal
from app.models.models import Variedad

def migrar_curvas():
    db = SessionLocal()
    analitica_path = "Analitica_Planeacion_2.0.xlsm"
    
    print(f"Cargando {analitica_path}...")
    df = pd.read_excel(analitica_path, sheet_name='Indices', header=None)
    
    registros_actualizados = 0
    registros_creados = 0
    
    for col_idx in range(2, df.shape[1]):
        var_name = str(df.iloc[2, col_idx]).strip()
        if var_name.lower() == 'nan' or not var_name:
            continue
            
        dia_pico = pd.to_numeric(df.iloc[4, col_idx], errors='coerce')
        dia_pico = int(dia_pico) if not pd.isna(dia_pico) else 70
            
        curvas = []
        for row_idx in range(5, 20):
            val = pd.to_numeric(df.iloc[row_idx, col_idx], errors='coerce')
            curvas.append(float(val) if not pd.isna(val) else 0.0)
            
        flor = str(df.iloc[0, col_idx]).strip()
        color = str(df.iloc[1, col_idx]).strip()
        
        flor = flor if flor and flor.lower() != 'nan' else 'Genérico'
        color = color if color and color.lower() != 'nan' else 'Genérico'
            
        var_db = db.query(Variedad).filter(Variedad.nombre == var_name).first()
        
        if var_db:
            var_db.dia_pico = dia_pico
            var_db.dia_inicio = dia_pico - 2
            for i, c in enumerate(curvas):
                setattr(var_db, f'c{i+1}', c)
            registros_actualizados += 1
        else:
            var_db = Variedad(
                nombre=var_name,
                flor=flor,
                color=color,
                dia_pico=dia_pico,
                dia_inicio=dia_pico - 2
            )
            for i, c in enumerate(curvas):
                setattr(var_db, f'c{i+1}', c)
            db.add(var_db)
            registros_creados += 1
            
    db.commit()
    db.close()
    
    print(f"Migración completada. Creadas: {registros_creados}. Actualizadas: {registros_actualizados}.")

if __name__ == "__main__":
    migrar_curvas()

