import pandas as pd
from datetime import date, timedelta
from app.core.database import SessionLocal
from app.services.forecast_service import generar_forecast_13wk
from app.services.mva_service import generar_plan_mva, proyectar_cosecha_desde_mva, combinar_proyecciones_52_semanas
from app.ui.pedido_ui import obtener_stats_jerarquicos

db = SessionLocal()
dyn, dyn_lower, fc_stats, f_stats, global_stats = obtener_stats_jerarquicos(db)

# 1. Combined Forecast
df_fc_vivo = generar_forecast_13wk(db, alpha=1.0, num_ciclos=9)
df_mrp = generar_plan_mva('PedidoConsolidado_master.xlsx', week_is='Pedido')
df_proy_mva = proyectar_cosecha_desde_mva(df_mrp, db)
df_fc_completo = combinar_proyecciones_52_semanas(df_fc_vivo, df_proy_mva)

semanas_fc_cols = [c for c in df_fc_completo.columns if str(c).startswith('202')]

fc_melt = df_fc_completo.melt(
    id_vars=['Flor', 'Color', 'Variedad'],
    value_vars=semanas_fc_cols,
    var_name='Semana',
    value_name='Tallos_Forecast'
)
fc_melt['Variedad_Norm'] = fc_melt['Variedad'].str.strip().str.lower()
fc_melt['Flor_Norm'] = fc_melt['Flor'].str.strip().str.lower()
fc_melt['Color_Norm'] = fc_melt['Color'].str.strip().str.lower()
fc_melt['Semana_Clean'] = fc_melt['Semana'].astype(str)

# 2. Plan
df_plan = pd.read_csv('Plan_Aprobado.csv')
col_cap = 'Tallos a Producir (Capacidad)' if 'Tallos a Producir (Capacidad)' in df_plan.columns else 'Suma de Tallos'
col_flor = 'Flor' if 'Flor' in df_plan.columns else 'Flower'
df_plan_eval = df_plan.dropna(subset=[col_cap]).copy()
df_plan_eval = df_plan_eval[df_plan_eval[col_cap] > 0]
df_plan_eval['Semana_Clean'] = df_plan_eval['Semana'].astype(str).str.replace('.0', '', regex=False)
df_plan_eval['Variedad_Norm'] = df_plan_eval['Variedad'].astype(str).str.strip().str.lower()
df_plan_eval['Flor_Norm'] = df_plan_eval[col_flor].astype(str).str.strip().str.lower()
df_plan_eval['Color_Norm'] = df_plan_eval['Color'].astype(str).str.strip().str.lower()

hoy = date.today()
sem_siguiente = f"S{(hoy + timedelta(weeks=1)).isocalendar()[0]}{(hoy + timedelta(weeks=1)).isocalendar()[1]:02d}"
sem_firme = f"S{(hoy + timedelta(weeks=24)).isocalendar()[0]}{(hoy + timedelta(weeks=24)).isocalendar()[1]:02d}"

# Grupo Color level analysis
p_gc = df_plan_eval.groupby(['Flor_Norm', 'Color_Norm', 'Semana_Clean'])[col_cap].sum().reset_index().rename(columns={col_cap: 'Plan'})
fc_gc = fc_melt.groupby(['Flor_Norm', 'Color_Norm', 'Semana_Clean'])['Tallos_Forecast'].sum().reset_index().rename(columns={'Tallos_Forecast': 'FC'})

m = pd.merge(p_gc, fc_gc, on=['Flor_Norm', 'Color_Norm', 'Semana_Clean'], how='inner')
m['Diff'] = m['FC'] - m['Plan']
m['Deficit'] = (m['Plan'] - m['FC']).clip(lower=0)
m['Surplus'] = (m['FC'] - m['Plan'] * 1.05).clip(lower=0)

def get_ped_week(sc, fl_n, col_n):
    if (fl_n, col_n) in fc_stats:
        dp = fc_stats[(fl_n, col_n)]['dia_pico']
    elif fl_n in f_stats:
        dp = f_stats[fl_n]['dia_pico']
    else:
        dp = global_stats['dia_pico']
    try:
        y, w = int(sc[:4]), int(sc[4:])
        f_pico = date.fromisocalendar(y, w, 4)
        f_ped = f_pico - timedelta(days=dp) - timedelta(weeks=4)
        y_p, w_p, _ = f_ped.isocalendar()
        return f"S{y_p}{w_p:02d}", dp
    except Exception:
        return 'S' + sc, dp

res_ped = m.apply(lambda r: get_ped_week(r['Semana_Clean'], r['Flor_Norm'], r['Color_Norm']), axis=1)
m['Sem_Ped'] = [x[0] for x in res_ped]
m['Dia_Pico'] = [x[1] for x in res_ped]

m_win = m[(m['Sem_Ped'] >= sem_siguiente) & (m['Sem_Ped'] < sem_firme)].copy()

print("=" * 60)
print(f"ANALISIS DE VENTANA DE PEDIDOS: {sem_siguiente} hasta {sem_firme}")
print("=" * 60)
plan_tot = m_win['Plan'].sum()
fc_tot = m_win['FC'].sum()
diff_tot = fc_tot - plan_tot
def_tot = m_win['Deficit'].sum()
sur_tot = m_win['Surplus'].sum()

print(f"Plan Aprobado Total:            {plan_tot:14,.0f} tallos")
print(f"ForeCast Proyectado Total:      {fc_tot:14,.0f} tallos")
print(f"Diferencia NETA Global (FC-Plan):{diff_tot:13,.0f} tallos ({diff_tot/plan_tot*100:+.2f}%)")
print(f"Suma de Deficits puntuales:     {def_tot:14,.0f} tallos")
print(f"Suma de Excedentes puntuales:   {sur_tot:14,.0f} tallos")

print("\n" + "=" * 60)
print("BALANCE POR TIPO DE FLOR EN LA VENTANA:")
print("=" * 60)
by_flor = m_win.groupby('Flor_Norm').agg(
    Plan=('Plan', 'sum'),
    FC=('FC', 'sum'),
    Deficit=('Deficit', 'sum'),
    Surplus=('Surplus', 'sum')
)
by_flor['Diferencia_Neta'] = by_flor['FC'] - by_flor['Plan']
print(by_flor.to_string())

print("\n" + "=" * 60)
print("BALANCE POR COMBINACION FLOR + COLOR:")
print("=" * 60)
by_fc = m_win.groupby(['Flor_Norm', 'Color_Norm']).agg(
    Plan=('Plan', 'sum'),
    FC=('FC', 'sum'),
    Deficit=('Deficit', 'sum'),
    Surplus=('Surplus', 'sum')
)
by_fc['Diferencia_Neta'] = by_fc['FC'] - by_fc['Plan']
by_fc = by_fc.sort_values('Deficit', ascending=False)
print(by_fc.head(15).to_string())

print("\n" + "=" * 60)
print("BALANCE SEMANA POR SEMANA DE PEDIDO (Muestra 12 semanas):")
print("=" * 60)
by_sem = m_win.groupby('Sem_Ped').agg(
    Plan=('Plan', 'sum'),
    FC=('FC', 'sum'),
    Deficit=('Deficit', 'sum'),
    Surplus=('Surplus', 'sum')
)
by_sem['Diferencia_Neta'] = by_sem['FC'] - by_sem['Plan']
print(by_sem.head(12).to_string())

