import pandas as pd
import numpy as np
import sys
import os

from app.core.database import SessionLocal
from app.services.mva_service import generar_plan_mva, proyectar_cosecha_desde_mva
from app.models.models import Variedad

def main():
    print("Loading data...")
    # 1. Get the app's projection
    db = SessionLocal()
    df_mrp = generar_plan_mva('PedidoConsolidado (1).xlsx', week_is="Pedido")
    df_app = proyectar_cosecha_desde_mva(df_mrp, db)
    
    # 2. Get the manual Excel projection
    df_manual = pd.read_excel('Analitica_Planeacion_2.0.xlsm', sheet_name='Plataforma vs Planeador', skiprows=148, nrows=75, usecols='B:CG')
    
    # Pre-process Manual
    df_manual = df_manual.dropna(subset=['Variedad'])
    cols_to_keep = ['Variedad'] + [c for c in df_manual.columns if isinstance(c, (int, float)) and 200000 < int(c) < 300000]
    df_manual = df_manual[cols_to_keep].copy()
    
    for c in df_manual.columns:
        if c != 'Variedad':
            df_manual.rename(columns={c: str(int(c))}, inplace=True)
            
    df_manual['Variedad'] = df_manual['Variedad'].astype(str).str.strip().str.lower()
    df_manual = df_manual.set_index('Variedad')
    df_manual = df_manual.fillna(0)
    
    # Pre-process App
    df_app['Variedad'] = df_app['Variedad'].astype(str).str.strip().str.lower()
    df_app = df_app.set_index('Variedad')
    
    app_weeks = [c for c in df_app.columns if c.startswith('202')]
    df_app = df_app[app_weeks].copy()
    df_app = df_app.fillna(0)
    
    # Find common varieties
    varieties_app = set(df_app.index)
    varieties_manual = set(df_manual.index)
    
    common_varieties = varieties_app.intersection(varieties_manual)
    common_weeks = sorted(list(set(df_app.columns).intersection(set(df_manual.columns))))
    
    print(f"App varieties: {len(varieties_app)}")
    print(f"Manual varieties: {len(varieties_manual)}")
    print(f"Common varieties: {len(common_varieties)}")
    
    # Compare totals
    print("\n--- Comparando Totales por Variedad ---")
    df_app_common = df_app.loc[list(common_varieties), common_weeks]
    df_manual_common = df_manual.loc[list(common_varieties), common_weeks]
    
    df_manual_common = df_manual_common.reindex(df_app_common.index)
    
    totals_app = df_app_common.sum(axis=1)
    totals_manual = df_manual_common.sum(axis=1)
    
    diff = totals_app - totals_manual
    pct_diff = (diff / totals_manual.replace(0, np.nan)) * 100
    
    summary = pd.DataFrame({
        'App_Total': totals_app,
        'Manual_Total': totals_manual,
        'Difference': diff,
        'Diff_%': pct_diff
    })
    
    summary = summary.sort_values('Difference')
    
    print("\nTotal Global App:", totals_app.sum())
    print("Total Global Manual:", totals_manual.sum())
    print("Diferencia Global:", totals_app.sum() - totals_manual.sum())
    
    print("\nMayores diferencias (App - Manual):")
    print(summary[summary['Difference'] != 0].head(10))
    print("...")
    print(summary[summary['Difference'] != 0].tail(10))
    
    print("\n--- Difference by Week for top discrepant variety ---")
    if not summary[summary['Difference'] != 0].empty:
        top_diff_var = summary.index[0] # Most negative
        print(f"Analyzing {top_diff_var}")
        s_app = df_app_common.loc[top_diff_var]
        s_manual = df_manual_common.loc[top_diff_var]
        df_top = pd.DataFrame({'App': s_app, 'Manual': s_manual})
        df_top['Diff'] = df_top['App'] - df_top['Manual']
        print(df_top[df_top['Diff'] != 0])
        
if __name__ == "__main__":
    main()

