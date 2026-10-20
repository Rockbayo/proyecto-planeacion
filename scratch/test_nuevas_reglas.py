import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
from app.services.enraizamiento_service import (
    ejecutar_compensacion_inventario,
    calcular_estado_disponibilidad,
    UMBRAL_DIFERENCIA_DESPRECIABLE
)

print(f"UMBRAL DE TOLERANCIA: {UMBRAL_DIFERENCIA_DESPRECIABLE} esquejes")

test_df = pd.DataFrame([
    # 1. Programada con déficit crítico de 2,000 en Yellow
    {'Flor': 'Cushion', 'Color': 'Yellow', 'Variedad': 'HERTZ', 'Stock_Cuarto_Frio': 0, 'Esquejes_Recepcion': 3000, 'Bajas_Descartes': 0, 'Esquejes_Requeridos': 5000},
    # 2. Extemporánea que llegó con 4,000 en Yellow (no estaba en plano, req=0)
    {'Flor': 'Cushion', 'Color': 'Yellow', 'Variedad': 'EXTEMPO SUN', 'Stock_Cuarto_Frio': 0, 'Esquejes_Recepcion': 4000, 'Bajas_Descartes': 0, 'Esquejes_Requeridos': 0},
    # 3. Programada con variación menor de 300 en White (<= 500, despreciable)
    {'Flor': 'Cushion', 'Color': 'White', 'Variedad': 'SHERPA', 'Stock_Cuarto_Frio': 0, 'Esquejes_Recepcion': 4700, 'Bajas_Descartes': 0, 'Esquejes_Requeridos': 5000},
    # 4. Programada con déficit crítico de 1,200 en Red (> 500, sin excedente compatible -> debe reprogramar)
    {'Flor': 'Cushion', 'Color': 'Red', 'Variedad': 'DON PEDRO', 'Stock_Cuarto_Frio': 0, 'Esquejes_Recepcion': 2800, 'Bajas_Descartes': 0, 'Esquejes_Requeridos': 4000},
])

df_res, alerts = ejecutar_compensacion_inventario(test_df)
print("\n--- ALERTAS GENERADAS ---")
for a in alerts:
    print(f"[{a['Nivel']}] -> {a['Mensaje']}")

print("\n--- RESULTADO DE LA TABLA ---")
cols_view = ['Variedad', 'Color', 'Esquejes_Requeridos', 'Total_Disponible', 'Compensacion_Volumen', 'Reprogramado_Siguiente_Semana', 'Esquejes_Efectivos_Clavar', 'Diferencia_Saldo', 'Estado_Disponibilidad']
print(df_res[cols_view])

