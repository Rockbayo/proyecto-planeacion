import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import SessionLocal
from app.models.models import Variedad

def inyectar_curvas_demo():
    print("Inyectando curvas fenolgicas simuladas para demostracin del ForeCast...")
    db = SessionLocal()
    variedades = db.query(Variedad).all()
    
    for v in variedades:
        # Simulamos que la cosecha arranca a las 10 semanas (70 das)
        v.dia_inicio = 70
        v.dia_pico = 84 # Pico en la semana 2 de cosecha
        v.dias_desb = 35 # Desbotone a la semana 5
        v.aprov_pp = 0.95 # 95% de aprovechamiento estndar
        
        # Simulamos una curva normal (Campana de Gauss) distribuida en 15 DÍAS de corte
        v.c1 = 0.01
        v.c2 = 0.02
        v.c3 = 0.04
        v.c4 = 0.08
        v.c5 = 0.12
        v.c6 = 0.15
        v.c7 = 0.16 # Día Pico
        v.c8 = 0.15
        v.c9 = 0.10
        v.c10 = 0.07
        v.c11 = 0.05
        v.c12 = 0.03
        v.c13 = 0.01
        v.c14 = 0.005
        v.c15 = 0.005
        
    db.commit()
    db.close()
    print("Curvas de rendimiento inyectadas correctamente en la base de datos.")

if __name__ == "__main__":
    inyectar_curvas_demo()

