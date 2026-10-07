import sys
import re

with open('app/ui/main_ui.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Modificar Chart 1
content = re.sub(
    r'if semanas_futuras:\s*fc_agrupado = df_fc\[semanas_futuras\]\.sum\(\)',
    r'if len(semanas_futuras) > 13:\n            semanas_futuras = semanas_futuras[:13]\n        if semanas_futuras:\n            fc_agrupado = df_fc[semanas_futuras].sum()',
    content
)

# Modificar tabla 1
content = re.sub(
    r'st\.caption\(f\"Mostrando desde la semana actual.*?\n\s*# --- AJUSTE: Mostrar tabla de produccion ---\n\s*st\.markdown\(\"\*\*Total Producci.*?n por Semana:\*\*\"\)\n\s*st\.dataframe\(df_chart\.T\.astype\(int\), use_container_width=True\)',
    r'# --- AJUSTE: Mostrar tabla de produccion ---\n            st.markdown("**Total Producción por Semana:**")\n            st.dataframe(df_chart.T.astype(int), use_container_width=True)',
    content
)

# Modificar opciones de tiempo
content = re.sub(
    r'\["1 Semana", "1 Mes \(4 Semanas\)", "3 Meses \(13 Semanas\)", "6 Meses \(26 Semanas\)", "12 Meses \(52 Semanas\)"\]',
    r'["1 Semana", "1 Mes", "3 Meses", "6 Meses", "12 Meses"]',
    content
)

# Modificar chart 3 Altair
altair_code = """        if records:
            df_plot = pd.DataFrame(records)
            df_plot = df_plot.sort_values(by='Día de Vida')
            import altair as alt
            chart = alt.Chart(df_plot).mark_line(point=True).encode(
                x=alt.X('Día de Vida:O', title='Días de Vida (Edad de Planta)'),
                y=alt.Y('% Cosecha:Q', title='% de Cosecha'),
                color='Flor:N'
            ).properties(height=400)
            st.altair_chart(chart, use_container_width=True)
            st.caption('Eje X: Días de vida. Eje Y: % Cosecha.')
"""
content = re.sub(
    r'        if records:\n            df_plot = pd\.DataFrame\(records\).*?st\.caption\(.*?Flor"\)',
    altair_code,
    content,
    flags=re.DOTALL
)

with open('app/ui/main_ui.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("UI Updated")

