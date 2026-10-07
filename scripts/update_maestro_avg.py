import sys

with open('app/ui/main_ui.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_section = """    data = []
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
    st.dataframe(df, use_container_width=True)"""

new_section = """    data = []
    for v in variedades:
        aprov_val = int(round(v.aprov_pp * 100)) if v.aprov_pp is not None else 0
        data.append({
            "ID": str(v.id),
            "Nombre": v.nombre,
            "Flor": v.flor,
            "Color": v.color,
            "Días Inicio": v.dia_inicio,
            "Días Pico": v.dia_pico,
            "Días Desbotone": v.dias_desb,
            "% APROV": f"{aprov_val}%",
            "_aprov_num": aprov_val
        })
    df = pd.DataFrame(data)
    
    if not df.empty and filtro_var == "Todas":
        avg_inicio = int(round(df['Días Inicio'].mean())) if not df['Días Inicio'].isnull().all() else 0
        avg_pico = int(round(df['Días Pico'].mean())) if not df['Días Pico'].isnull().all() else 0
        avg_desb = int(round(df['Días Desbotone'].mean())) if not df['Días Desbotone'].isnull().all() else 0
        avg_aprov = int(round(df['_aprov_num'].mean())) if not df['_aprov_num'].isnull().all() else 0
        
        summary_row = pd.DataFrame([{
            "ID": "-",
            "Nombre": "== PROMEDIO TOTAL ==",
            "Flor": "-",
            "Color": "-",
            "Días Inicio": avg_inicio,
            "Días Pico": avg_pico,
            "Días Desbotone": avg_desb,
            "% APROV": f"{avg_aprov}%",
            "_aprov_num": avg_aprov
        }])
        
        df = pd.concat([df, summary_row], ignore_index=True)
        
    if '_aprov_num' in df.columns:
        df = df.drop(columns=['_aprov_num'])
        
    st.dataframe(df, use_container_width=True)"""

if old_section in content:
    content = content.replace(old_section, new_section)
    with open('app/ui/main_ui.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("UI Updated successfully")
else:
    print("Old section not found")

