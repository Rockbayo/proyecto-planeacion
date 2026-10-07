import sys

with open('app/ui/main_ui.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
in_maestro = False
skip_lines = False

for i, line in enumerate(lines):
    if 'elif modulo == "Maestro Variedades":' in line:
        in_maestro = True
        skip_lines = True
        
        new_section = """elif modulo == "Maestro Variedades":
    st.header("🌺 Maestro de Variedades")
    
    variedades_db = db.query(Variedad).all()
    nombres_variedades = ["Todas"] + sorted([v.nombre for v in variedades_db if v.nombre])
    filtro_var = st.selectbox("Buscar variedad puntual:", nombres_variedades)
    
    if filtro_var != "Todas":
        variedades = [v for v in variedades_db if v.nombre == filtro_var]
    else:
        variedades = variedades_db
    
    data = []
    for v in variedades:
        aprov_val = int(round(v.aprov_pp * 100)) if v.aprov_pp is not None else 0
        data.append({
            "ID": v.id,
            "Nombre": v.nombre,
            "Flor": v.flor,
            "Color": v.color,
            "Días Inicio": v.dia_inicio,
            "Días Pico": v.dia_pico,
            "Días Desbotone": v.dias_desb,
            "% APROV": f"{aprov_val}%"
        })
    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True)
"""
        new_lines.append(new_section)
        continue
        
    if skip_lines:
        if 'elif modulo ==' in line and 'Inventario Camas' in line:
            skip_lines = False
            new_lines.append(line)
        continue
        
    if not skip_lines:
        new_lines.append(line)

with open('app/ui/main_ui.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Updated via script.")

