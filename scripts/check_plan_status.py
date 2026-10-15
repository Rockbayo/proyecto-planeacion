import pandas as pd

df = pd.read_csv("Plan_Aprobado.csv")
print("Total rows:", len(df))
print("Columns:", df.columns.tolist())

# Check row 0
print("\nRow 0 null check:", df.iloc[0].isna().to_dict())

# Check weeks 202701 to 202706
print("\nSemanas 202701 to 202706:")
for sem in [202701, 202702, 202703, 202704, 202705, 202706]:
    sub = df[df["Semana"] == float(sem)]
    p = sub["Tallos Pedidos (Plan)"].sum()
    c = sub["Tallos a Producir (Capacidad)"].sum()
    print(f"Semana {sem}: {len(sub)} rows | Pedidos: {p:,.0f} | Capacidad: {c:,.0f}")

sv_p = df[df["Semana"].isin([202703.0, 202704.0, 202705.0])]["Tallos Pedidos (Plan)"].sum()
sv_c = df[df["Semana"].isin([202703.0, 202704.0, 202705.0])]["Tallos a Producir (Capacidad)"].sum()
print(f"\nTOTAL SAN VALENTIN (S2703-S2705): Pedidos = {sv_p:,.0f} | Capacidad = {sv_c:,.0f}")

