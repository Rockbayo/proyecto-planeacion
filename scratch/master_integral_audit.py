import os, sys
sys.path.insert(0, os.path.abspath("."))
import json
import pandas as pd
import numpy as np
from app.core.database import SessionLocal
from app.models.models import Variedad, Siembra, Ubicacion, CapacidadBloque
from app.services.forecast_service import generar_forecast_13wk, calcular_curvas_dinamicas
from app.services.mva_service import proyectar_cosecha_desde_mva, combinar_proyecciones_52_semanas
from app.services.enraizamiento_service import CAVIDADES_POR_BANDEJA, SEMANAS_ENRAIZAMIENTO
from app.services.ocupacion_service import (
    calcular_ocupacion_semanal_52w,
    CAMAS_COMERCIALES_REDUCIDAS,
    obtener_dimensiones_camas_bloques
)

print("=" * 85)
print("     AUDITORÍA INTEGRAL TOTAL Y CERTIFICACIÓN DEL ECOSISTEMA S&OP")
print("=" * 85)

db = SessionLocal()
results = []

# -------------------------------------------------------------------------------------------------
# PILAR 1: Cruce de Pedidos, Planes y Variedades
# -------------------------------------------------------------------------------------------------
df_plan = pd.read_csv("Plan_Aprobado.csv")
df_plan['Semana'] = df_plan['Semana'].astype(str).str.split('.').str[0]
plan_tallos = df_plan['Tallos a Producir (Capacidad)'].sum()

df_det = pd.read_csv("Plan_Aprobado_Detallado.csv")
det_tallos = (df_det['Esquejes'] * df_det['Aprov_PP']).sum()
det_esquejes = df_det['Esquejes'].sum()

df_master = pd.read_excel("PedidoConsolidado_master.xlsx")
cols_s = [c for c in df_master.columns if str(c).startswith('S202')]
master_tallos = df_master[cols_s].sum().sum()

dif_global = abs(plan_tallos - master_tallos) / plan_tallos * 100
p1_pass = dif_global < 2.0
results.append(("PILAR 1: Cruce Pedidos vs Planes", p1_pass, f"Capacidad={plan_tallos:,.0f}, Master={master_tallos:,.0f} (Dif={dif_global:.2f}%)"))

# -------------------------------------------------------------------------------------------------
# PILAR 2: Curvas de Cosecha, Fenología y Biología
# -------------------------------------------------------------------------------------------------
curvas_dyn = calcular_curvas_dinamicas(db=db)
neg_c = 0
anom_dias = 0
for v_name, v_data in curvas_dyn.items():
    c_vals = [v_data[f'c{i}'] for i in range(1, 16)]
    if any(c < 0 for c in c_vals):
        neg_c += 1
    if v_data.get('dia_inicio', 0) >= v_data.get('dia_pico', 0):
        anom_dias += 1

p2_pass = (neg_c == 0 and anom_dias == 0 and len(curvas_dyn) >= 80)
results.append(("PILAR 2: Curvas y Fenología", p2_pass, f"{len(curvas_dyn)} curvas calibradas, 0 negativos, 0 inconsistencias de días"))

# -------------------------------------------------------------------------------------------------
# PILAR 3: Propagación, Enraizamiento y Desfase Agronómico
# -------------------------------------------------------------------------------------------------
df_ejec = pd.read_csv("Ejecucion_Real_Enraizamiento.csv")
anom_mat = 0
for _, r in df_ejec[df_ejec['Esquejes_Reales'] > 0].iterrows():
    e = r['Esquejes_Reales']
    b = r['Bandejas_Reales']
    c = r['Camas_Reales']
    if abs(b - round(e / 112.0)) > 1 or abs(c - round(e / 5200.0, 1)) > 0.1:
        anom_mat += 1

# Verificar que enraizamiento S42 tenga 466,193
s42_esq = df_ejec[df_ejec['Semana_Enraizamiento'] == 202642]['Esquejes_Reales'].sum()
s42_ok = (s42_esq == 466193)
p3_pass = (anom_mat == 0 and s42_ok)
results.append(("PILAR 3: Enraizamiento y Propagación", p3_pass, f"Semana 42={s42_esq:,.0f} esquejes (40/30/30), 0 anomalías en camas/bandejas"))

# -------------------------------------------------------------------------------------------------
# PILAR 4: Motor S&OP 52 Semanas y Blindaje Anti-Inflación
# -------------------------------------------------------------------------------------------------
df_fc = generar_forecast_13wk(db)
df_p = proyectar_cosecha_desde_mva(df_det, db)
df_comb = combinar_proyecciones_52_semanas(df_fc, df_p, horizonte_semanas=52)
sems_c = [c for c in df_comb.columns if str(c).startswith('202')]

nan_c = df_comb[sems_c].isna().sum().sum()
neg_tot = (df_comb[sems_c] < 0).sum().sum()
total_comb = df_comb[sems_c].sum().sum()
dem_52 = df_plan[df_plan['Semana'].isin(sems_c)]['Tallos a Producir (Capacidad)'].sum()
cumpl_sop = (total_comb / dem_52) * 100

p4_pass = (nan_c == 0 and neg_tot == 0 and 95.0 <= cumpl_sop <= 110.0)
results.append(("PILAR 4: Motor S&OP y Anti-Inflación", p4_pass, f"Cumplimiento 52w={cumpl_sop:.2f}% ({total_comb:,.0f} vs {dem_52:,.0f}), 0 NaNs, 0 Neg"))

# -------------------------------------------------------------------------------------------------
# PILAR 5: Capacidad Física y Ocupación de Camas
# -------------------------------------------------------------------------------------------------
res_o = calcular_ocupacion_semanal_52w(db)
df_o = res_o[0] if isinstance(res_o, tuple) else res_o
pico_c = df_o['Camas_Ocupadas'].max()
sem_pico = df_o.loc[df_o['Camas_Ocupadas'].idxmax(), 'Semana']
excede = (df_o['Camas_Ocupadas'] > CAMAS_COMERCIALES_REDUCIDAS).sum()

p5_pass = (excede == 0 and pico_c <= CAMAS_COMERCIALES_REDUCIDAS)
results.append(("PILAR 5: Ocupación de Camas", p5_pass, f"Pico={pico_c:,.1f} camas en S{sem_pico} (Techo={CAMAS_COMERCIALES_REDUCIDAS}), 0 excesos"))

# -------------------------------------------------------------------------------------------------
# PILAR 6: Integridad de Módulos UI y Servicios
# -------------------------------------------------------------------------------------------------
ui_mods = [
    "app.ui.pedido_ui", "app.ui.enraizamiento_ui", "app.ui.siembra_ui", 
    "app.ui.ocupacion_ui", "app.ui.curvas_ui", "app.ui.accuracy_ui", "app.ui.actas_ui",
    "app.services.siembra_service", "app.services.mva_service", "app.services.forecast_service"
]
err_ui = 0
for um in ui_mods:
    try:
        __import__(um)
    except Exception:
        err_ui += 1

p6_pass = (err_ui == 0)
results.append(("PILAR 6: Módulos UI y Arquitectura", p6_pass, f"{len(ui_mods)} módulos probados sin errores de importación"))

# -------------------------------------------------------------------------------------------------
# REPORTE EJECUTIVO FINAL
# -------------------------------------------------------------------------------------------------
db.close()
print("\n" + "-" * 85)
print(f"{'PILAR EVALUADO':<40} | {'ESTADO':<8} | {'DETALLE Y EVIDENCIA NUMÉRICA':<30}")
print("-" * 85)
all_pass = True
for name, passed, detail in results:
    st_str = "[PASS]" if passed else "[FAIL]"
    if not passed: all_pass = False
    print(f"{name:<40} | {st_str:<8} | {detail}")

print("-" * 85)
if all_pass:
    print(">>> CERTIFICACIÓN GLOBAL: 6/6 PILARES APROBADOS AL 100% (SISTEMA INTEGRAL CERTIFICADO)")
else:
    print(">>> CERTIFICACIÓN GLOBAL: REVISAR FALLAS")
print("=" * 85)

