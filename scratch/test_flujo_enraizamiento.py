import os
import sys
sys.path.insert(0, os.path.abspath("."))
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pandas as pd
import app.services.enraizamiento_service as es

engine = create_engine('sqlite:///data/planeacion.db')
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

print("=== 1. Generar Plano Operativo 202643 ===")
res_plano_43 = es.generar_plano_enraizamiento_semanal(db, "202643")
print("Filas en plano detallado 202643:", len(res_plano_43["df_plano_detallado"]))

print("\n=== 2. Precargar Inventario Base 202643 ===")
df_inv_43 = es.precargar_inventario_desde_plano(res_plano_43)
print("Variedades en inventario:", len(df_inv_43))
total_req = df_inv_43["Esquejes_Requeridos"].sum()
print("Total Requerido en Plano:", f"{total_req:,d}")

# Modificar algunas variedades para simular la realidad:
v0 = df_inv_43.index[0]
v1 = df_inv_43.index[1]
nom0 = df_inv_43.loc[v0, "Variedad"]
nom1 = df_inv_43.loc[v1, "Variedad"]
f0, c0 = df_inv_43.loc[v0, "Flor"], df_inv_43.loc[v0, "Color"]
f1, c1 = df_inv_43.loc[v1, "Flor"], df_inv_43.loc[v1, "Color"]

# Simular recepcion con deficit en v0 y bajas
df_inv_43.loc[v0, "Esquejes_Recepcion"] = max(0, int(df_inv_43.loc[v0, "Esquejes_Requeridos"]) - 1000)
df_inv_43.loc[v0, "Bajas_Descartes"] = 200
df_inv_43.loc[v0, "Total_Disponible"] = int(df_inv_43.loc[v0, "Stock_Cuarto_Frio"]) + int(df_inv_43.loc[v0, "Esquejes_Recepcion"]) - int(df_inv_43.loc[v0, "Bajas_Descartes"])

# Simular recepcion con excedente en v1
df_inv_43.loc[v1, "Esquejes_Recepcion"] = int(df_inv_43.loc[v1, "Esquejes_Requeridos"]) + 2000
df_inv_43.loc[v1, "Total_Disponible"] = int(df_inv_43.loc[v1, "Stock_Cuarto_Frio"]) + int(df_inv_43.loc[v1, "Esquejes_Recepcion"])

print(f"Lote 1: [{nom0}] ({f0}-{c0}) -> Requerido={df_inv_43.loc[v0, 'Esquejes_Requeridos']}, Disp={df_inv_43.loc[v0, 'Total_Disponible']} (Déficit: {df_inv_43.loc[v0, 'Total_Disponible'] - df_inv_43.loc[v0, 'Esquejes_Requeridos']})")
print(f"Lote 2: [{nom1}] ({f1}-{c1}) -> Requerido={df_inv_43.loc[v1, 'Esquejes_Requeridos']}, Disp={df_inv_43.loc[v1, 'Total_Disponible']} (Excedente: {df_inv_43.loc[v1, 'Total_Disponible'] - df_inv_43.loc[v1, 'Esquejes_Requeridos']})")

print("\n=== 3. Ejecutar Compensación Jerárquica ===")
df_comp, alerts = es.ejecutar_compensacion_inventario(df_inv_43)
print(f"Alertas generadas: {len(alerts)}")
for a in alerts:
    print(f"  {a['Nivel']} -> {a['Mensaje']}")

print("\nDetalle de Lotes Evaluados en df_comp:")
print(df_comp.loc[[v0, v1], ["Variedad", "Flor", "Color", "Total_Disponible", "Esquejes_Requeridos", "Compensacion_Volumen", "Reprogramado_Siguiente_Semana", "Esquejes_Efectivos_Clavar", "Remanente_Final", "Estado_Disponibilidad"]])

print("\n=== 4. Aprobar Ejecución y Descontar de Inventario ===")
res_aprob = es.aprobar_ejecucion_y_descontar_inventario("202643", None, df_comp)
print("Aprobado con éxito:", res_aprob["exito"])
print("Total Clavado Real:", f"{res_aprob['total_clavado']:,d}")
print("Total Remanente Cuarto Frío:", f"{res_aprob['total_remanente']:,d}")
print("Semana Siguiente:", res_aprob["semana_siguiente"])

print("\n=== 5. Precargar Semana Siguiente (202644) ===")
res_plano_44 = es.generar_plano_enraizamiento_semanal(db, "202644")
df_inv_44 = es.precargar_inventario_desde_plano(res_plano_44)
stk_total_44 = df_inv_44["Stock_Cuarto_Frio"].sum()
print(f"Total Stock Cuarto Frío transferido a 202644: {stk_total_44:,d}")
df_stk_heredado = df_inv_44[df_inv_44["Stock_Cuarto_Frio"] > 0]
if not df_stk_heredado.empty:
    print("Variedades con stock heredado:")
    print(df_stk_heredado[["Variedad", "Flor", "Color", "Stock_Cuarto_Frio", "Esquejes_Recepcion", "Total_Disponible"]])

db.close()
