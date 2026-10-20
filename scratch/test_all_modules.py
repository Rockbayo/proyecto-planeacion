import sys
import os
import io
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))
from app.core.database import SessionLocal, engine
from app.models.models import Variedad, Siembra, Ubicacion, CapacidadBloque
from app.services import (
    alertas_service,
    forecast_service,
    calibracion_service,
    mva_service,
    ocupacion_service,
    produccion_service,
    enraizamiento_service
)

db = SessionLocal()

print('=== 1. DATABASE CHECK ===')
n_vars = db.query(Variedad).count()
n_siembras = db.query(Siembra).count()
n_ubic = db.query(Ubicacion).count()
print(f'Variedades: {n_vars}, Siembras: {n_siembras}, Ubicaciones: {n_ubic}')

print('\n=== 2. ALERTAS SOP CHECK ===')
alertas = alertas_service.obtener_alertas_sop()
print(f'Total alertas generadas: {len(alertas)}')
for k, a in alertas.items():
    t = a.get('status', 'INFO')
    tit = a.get('titulo', '')
    msg = a.get('mensaje', '')[:65]
    print(f'  [{t}] {tit}: {msg}...')

print('\n=== 3. FORECAST SERVICE CHECK ===')
res_fc = forecast_service.generar_forecast_13wk(db)
print(f'Forecast 13wk rows: {len(res_fc)}')

print('\n=== 4. PLAN DE PRODUCCION VIGENTE CHECK ===')
res_prod = produccion_service.obtener_resumen_plan_vigente(db=db)
print(f"Plan vigente activo: {res_prod.get('activo')}, Num semanas: {res_prod.get('num_semanas')}, Total capacidad: {res_prod.get('total_capacidad', 0):,.0f}")

print('\n=== 5. OCUPACION SERVICE CHECK ===')
res_oc = ocupacion_service.calcular_ocupacion_semanal_52w(db)
df_oc = res_oc[0] if isinstance(res_oc, tuple) else res_oc
if isinstance(df_oc, pd.DataFrame):
    print(f'Ocupacion semanal 52w shape: {df_oc.shape}')
else:
    print(f'Ocupacion type: {type(df_oc)}')

print('\n=== 6. ENRAIZAMIENTO SERVICE CHECK ===')
df_inv = enraizamiento_service.cargar_inventario_recepcion('202643')
if df_inv is not None and not df_inv.empty:
    df_inv['Esquejes_Efectivos_Clavar'] = df_inv.apply(enraizamiento_service.calcular_esquejes_efectivos_clavar, axis=1)

res_p = enraizamiento_service.generar_plano_enraizamiento_semanal(db, '202643', df_inventario_ajustado=df_inv)
df_det = res_p.get('df_plano_detallado', pd.DataFrame())
print(f'Plano enraizamiento S2643 lotes: {len(df_det)}')
print(f'Columnas en plano detallado: {df_det.columns.tolist()}')

print('\n=== 7. SIEMBRA SERVICE CHECK ===')
from app.services import siembra_service
res_s = siembra_service.generar_plano_siembra_semanal(db, '202646')
print(f"Plano siembra S2646 lotes: {len(res_s['df_plano_detallado'])}, Camas: {res_s['kpis']['total_camas']}")
pdf_s = siembra_service.generar_pdf_plano_siembra(res_s)
print(f"PDF siembra size: {len(pdf_s)} bytes")

print('\nALL CORE SERVICES ARE OPERATIONAL!')
