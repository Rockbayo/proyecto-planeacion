import sys
import os
import pandas as pd
sys.path.append(os.path.abspath('.'))
from app.core.database import engine

df = pd.read_sql("SELECT u.lado, u.area_m2, u.capacidad_plantas, s.plantas_sembradas FROM ubicaciones u LEFT JOIN siembras s ON u.id = s.ubicacion_id WHERE u.bloque='1.0' AND u.nave='1.0' AND u.cama='1.0'", engine)
print(df)

