import sys
import os
import streamlit as st
import pandas as pd
from datetime import date

# Añadir el directorio raíz al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from app.core.database import SessionLocal, engine
from app.models.models import Variedad, Ubicacion, Siembra
from app.services.forecast_service import generar_forecast_13wk, isocalendar_to_string

st.set_page_config(page_title="Analitica Planeacion S&OP", layout="wide")

st.title("🌱 Analítica Planeación S&OP")
st.markdown("Sistema maestro de planeación agrícola.")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db = next(get_db())

st.sidebar.title("Navegación")
modulo = st.sidebar.radio("Ir a:", ["Dashboard General", "ForeCast 10 Wk", "Exportación Plataforma", "Proyección desde Pedido MV"])

if modulo == "Dashboard General":
    st.header("📊 Dashboard General")
    
    # KPIs basicos
    col1, col2, col3, col4 = st.columns(4)
    total_vars = db.query(Variedad).count()
    
    # Calcular metricas de siembras y area
    df_metrics = pd.read_sql("SELECT count(s.id) as camas, sum(s.plantas_sembradas) as plantas, sum(u.area_m2) as area_ocupada FROM siembras s JOIN ubicaciones u ON s.ubicacion_id = u.id", engine)
    total_camas_sembradas = df_metrics['camas'].iloc[0] if not df_metrics.empty else 0
    total_plantas_sembradas = df_metrics['plantas'].iloc[0] if not df_metrics.empty else 0
    area_ocupada = df_metrics['area_ocupada'].iloc[0] if not df_metrics.empty and pd.notnull(df_metrics['area_ocupada'].iloc[0]) else 0
    
    col1.metric("Variedades Activas", f"{total_vars:,.0f}")
    col2.metric("Área Ocupada (m2)", f"{area_ocupada:,.2f}")
    col3.metric("Lotes Sembrados", f"{total_camas_sembradas:,.0f}")
    col4.metric("Plantas Sembradas", f"{total_plantas_sembradas:,.0f}")
    
    st.divider()
    
    # --- Módulo de Carga ---
    st.subheader("Carga de Plano de Siembra")
    
    if os.path.exists("last_dataset_name.txt"):
        with open("last_dataset_name.txt", "r") as f:
            last_file = f.read().strip()
    else:
        last_file = "Siembra Actual (16).xlsx (Cargado por defecto)"
        
    st.info(f"**Último dataset cargado:** {last_file}")
    
    uploaded_file = st.file_uploader("Cargar nuevo dataset de Siembras (Excel)", type=["xlsx", "xls"])
    if uploaded_file is not None:
        if st.button("Procesar Dataset"):
            with st.spinner("Cargando y procesando dataset... esto puede tardar un momento."):
                file_path = "Siembra Actual (16).xlsx"
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                with open("last_dataset_name.txt", "w") as f:
                    f.write(uploaded_file.name)
                
                from scripts.ingestar_siembra import ingestar_siembra_actual
                ingestar_siembra_actual()
                
                st.success("Dataset procesado con éxito. Los datos han sido actualizados.")
                st.rerun()
                
    st.divider()
    
    # --- Filtro de Aprovechamiento y Curvas ---
    st.subheader("Aprovechamiento y Curvas de Variedades")
    st.markdown("Filtra el rendimiento histórico y comportamiento fenológico.")
    
    col_f1, col_f2 = st.columns(2)
    
    opcion_tiempo = col_f1.selectbox(
        "Periodo hacia atrás a promediar:",
        ["1 Semana", "1 Mes", "3 Meses", "6 Meses", "12 Meses"],
        index=1,
        help="En el futuro conectará con cortes reales para recalcular las curvas dinámicamente en este lapso."
    )
    
    variedades_db = db.query(Variedad).all()
    nombres_variedades = ["Todas"] + sorted([v.nombre for v in variedades_db if v.nombre])
    filtro_var = col_f2.selectbox("Filtrar variedad puntual:", nombres_variedades)
    
    if filtro_var != "Todas":
        variedades = [v for v in variedades_db if v.nombre == filtro_var]
    else:
        variedades = variedades_db
        
    data = []
    for v in variedades:
        aprov_val = int(round(v.aprov_pp * 100)) if v.aprov_pp is not None else 0
        data.append({
            "Variedad": v.nombre,
            "Flor": v.flor,
            "Color": v.color,
            "Días Inicio": v.dia_inicio,
            "Días Pico": v.dia_pico,
            "Días Desbotone": v.dias_desb,
            "% APROV": f"{aprov_val}%",
            "_aprov_num": aprov_val,
            "c1": v.c1, "c2": v.c2, "c3": v.c3, "c4": v.c4, "c5": v.c5,
            "c6": v.c6, "c7": v.c7, "c8": v.c8, "c9": v.c9, "c10": v.c10,
            "c11": v.c11, "c12": v.c12, "c13": v.c13, "c14": v.c14, "c15": v.c15
        })
    df_vars = pd.DataFrame(data)
    
    if not df_vars.empty:
        col_res1, col_res2 = st.columns(2)
        
        with col_res1:
            if filtro_var == "Todas":
                avg_aprov = int(round(df_vars['_aprov_num'].mean()))
                st.metric(f"Promedio Aprovechamiento (Todas)", f"{avg_aprov}%")
            else:
                val_aprov = df_vars['_aprov_num'].iloc[0]
                st.metric(f"Aprovechamiento {filtro_var}", f"{val_aprov}%")
                
            cols_to_drop = ['_aprov_num', 'c1', 'c2', 'c3', 'c4', 'c5', 'c6', 'c7', 'c8', 'c9', 'c10', 'c11', 'c12', 'c13', 'c14', 'c15']
            st.dataframe(df_vars.drop(columns=cols_to_drop), use_container_width=True)
            
        with col_res2:
            st.markdown("**Curva Fenológica Esperada (% Cosecha por Día de Vida)**")
            records = []
            
            if filtro_var == "Todas":
                # Agrupar por Flor
                df_grouped = df_vars.groupby('Flor').agg({
                    'Días Inicio': 'mean',
                    'c1': 'mean', 'c2': 'mean', 'c3': 'mean', 'c4': 'mean', 'c5': 'mean',
                    'c6': 'mean', 'c7': 'mean', 'c8': 'mean', 'c9': 'mean', 'c10': 'mean',
                    'c11': 'mean', 'c12': 'mean', 'c13': 'mean', 'c14': 'mean', 'c15': 'mean'
                }).reset_index()
                
                for _, row in df_grouped.iterrows():
                    flor = row['Flor']
                    d_inicio = int(round(row['Días Inicio']))
                    for i in range(1, 16):
                        val = row[f'c{i}']
                        if pd.notna(val) and val > 0:
                            records.append({
                                "Serie": flor,
                                "Día de Vida": d_inicio + i - 1,
                                "% Cosecha": val * 100
                            })
            else:
                # Mostrar solo la variedad seleccionada
                row = df_vars.iloc[0]
                var_nombre = row['Variedad']
                d_inicio = int(row['Días Inicio'])
                for i in range(1, 16):
                    val = row[f'c{i}']
                    if pd.notna(val) and val > 0:
                        records.append({
                            "Serie": var_nombre,
                            "Día de Vida": d_inicio + i - 1,
                            "% Cosecha": val * 100
                        })
                        
            if records:
                df_plot = pd.DataFrame(records)
                df_pivot_plot = df_plot.pivot(index='Día de Vida', columns='Serie', values='% Cosecha')
                st.line_chart(df_pivot_plot)
                st.caption(f"Visualizando periodo: {opcion_tiempo}")
            else:
                st.info("No hay curvas fenológicas configuradas para esta selección.")

elif modulo == "ForeCast 10 Wk":
    st.header("📈 ForeCast a 10 Semanas Móviles")
    st.markdown("Proyección de cosecha basada en inventario activo.")
    
    # Parametros visuales
    st.sidebar.markdown("### Parámetros de Suavización")
    ponderacion = st.sidebar.slider("Ponderación (%)", 0, 100, 70)
    periodos = st.sidebar.number_input("Ciclos (Periodos)", min_value=1, value=9)
    
    with st.spinner("Generando matriz de pronóstico (ForeCast)..."):
        df_forecast = generar_forecast_13wk(db)
        
    if df_forecast.empty:
        st.warning("No hay datos suficientes para generar el forecast.")
    else:
        semanas_cols = [col for col in df_forecast.columns if col not in ['Sede', 'Flor', 'Color', 'Variedad']]
        semanas_cols = sorted(semanas_cols)
        
        semana_actual = isocalendar_to_string(date.today())
        semanas_futuras = [s for s in semanas_cols if s >= semana_actual]
        if len(semanas_futuras) > 10:
            semanas_futuras = semanas_futuras[:10]
            
        if semanas_futuras:
            fc_agrupado = df_forecast[semanas_futuras].sum()
            
            st.subheader("Proyección Semanal vs Plan de Producción")
            
            col_plan1, col_plan2 = st.columns([1, 3])
            plan_semanal = col_plan1.number_input("Meta del Plan (Tallos/Semana)", value=400000, step=10000, help="Define el plan de producción para visualizar la variación.")
            
            df_chart = pd.DataFrame({
                "Proyección (ForeCast)": fc_agrupado,
                "Plan Producción": plan_semanal
            })
            st.line_chart(df_chart)
            
            st.markdown("**Comparativo ForeCast vs Plan de Producción:**")
            df_comp = df_chart.copy()
            # Evitar división por cero si el plan es 0
            df_comp['Variación %'] = df_comp.apply(lambda row: ((row['Proyección (ForeCast)'] / row['Plan Producción']) - 1) * 100 if row['Plan Producción'] > 0 else 0, axis=1)
            
            df_comp_display = df_comp.copy()
            df_comp_display['Proyección (ForeCast)'] = df_comp_display['Proyección (ForeCast)'].apply(lambda x: f"{int(x):,}")
            df_comp_display['Plan Producción'] = df_comp_display['Plan Producción'].apply(lambda x: f"{int(x):,}")
            df_comp_display['Variación %'] = df_comp_display['Variación %'].apply(lambda x: f"{x:+.1f}%")
            
            st.dataframe(df_comp_display.T, use_container_width=True)
            
        st.divider()
        st.subheader("Resumen Total por Flor")
        df_forecast['TOTAL'] = df_forecast[semanas_futuras].sum(axis=1) if semanas_futuras else 0
        
        if semanas_futuras:
            resumen_flor = df_forecast.groupby('Flor')[semanas_futuras + ['TOTAL']].sum()
            total_row_flor = pd.DataFrame(resumen_flor.sum()).T
            total_row_flor.index = ['TOTAL GENERAL']
            resumen_flor = pd.concat([resumen_flor, total_row_flor])
            st.dataframe(resumen_flor.style.format("{:,.0f}"), use_container_width=True)

        st.subheader("Matriz ForeCast Detallada")
        if semanas_futuras:
            cols_num = semanas_futuras + ['TOTAL']
            total_row = pd.DataFrame(df_forecast[cols_num].sum()).T
            total_row.index = ['TOTAL GENERAL']
            
            for col in ['Sede', 'Flor', 'Color', 'Variedad']:
                if col in df_forecast.columns:
                    total_row[col] = ""
            
            meta_cols = [c for c in ['Sede', 'Flor', 'Color', 'Variedad'] if c in df_forecast.columns]
            df_forecast = df_forecast[meta_cols + cols_num]
            
            df_forecast = pd.concat([df_forecast, total_row])
            st.dataframe(df_forecast.style.format(formatter={col: "{:,.0f}" for col in cols_num}), use_container_width=True)
        else:
            st.dataframe(df_forecast, use_container_width=True)

elif modulo == "Exportación Plataforma":
    st.header("📤 Exportación a Plataforma")
    st.markdown("Carga las plantillas vacías descargadas de la plataforma. El sistema inyectará **9 semanas** de proyecciones basadas en inventario vivo, y dejará el espacio de las **4 semanas** restantes para cruzar con el Plan de Producción.")
    
    col_up1, col_up2 = st.columns(2)
    with col_up1:
        uploaded_templates = st.file_uploader("Sube las plantillas por flor (Ej: Cushion_...xlsx)", type=["xlsx", "xls"], accept_multiple_files=True)
    
    with col_up2:
        st.info("💡 **Nota sobre el Plan de Producción:** Las plantillas tienen 13 semanas. Las primeras 9 se llenan con la proyección real de campo. Las 4 restantes deben llenarse con la meta de siembra futura (Plan).")
        uploaded_plan = st.file_uploader("Opcional: Sube el dataset de Plan de Producción (Excel) para llenar las 4 semanas finales", type=["xlsx", "xls"])

    if uploaded_templates:
        if st.button("Procesar y Llenar Plantillas"):
            with st.spinner("Generando forecast e inyectando datos en las plantillas..."):
                # Generar forecast global
                df_forecast = generar_forecast_13wk(db)
                
                # Cargar plan si existe
                df_plan = None
                if uploaded_plan is not None:
                    # Logica basica asumiendo que el plan tiene Variedad en la primera columna y semanas en las siguientes
                    df_plan = pd.read_excel(uploaded_plan)
                    if 'Variedad' in df_plan.columns:
                        df_plan = df_plan.set_index('Variedad')
                
                # Importamos el procesador
                import sys
                import os
                sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
                from scripts.export_plataforma import procesar_plantillas_plataforma
                
                templates_dict = {f.name: f.getvalue() for f in uploaded_templates}
                resultados = procesar_plantillas_plataforma(templates_dict, df_forecast, df_plan)
                
                st.success(f"Se procesaron {len(resultados)} plantillas exitosamente.")
                
                # Generar un solo boton usando HTML/JS para descargar multiples archivos sin comprimirlos en ZIP
                import base64
                import json
                import streamlit.components.v1 as components
                
                files_data = []
                for filename, filebytes in resultados.items():
                    b64 = base64.b64encode(filebytes).decode("utf-8")
                    files_data.append({"filename": filename, "b64": b64})
                
                js_code = f"""
                <script>
                function downloadAll() {{
                    const files = {json.dumps(files_data)};
                    files.forEach((file, index) => {{
                        setTimeout(() => {{
                            const link = document.createElement("a");
                            link.href = "data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64," + file.b64;
                            link.download = file.filename;
                            document.body.appendChild(link);
                            link.click();
                            document.body.removeChild(link);
                        }}, index * 500); // Pequeño retraso para que el navegador no lo bloquee
                    }});
                }}
                </script>
                <button onclick="downloadAll()" style="background-color: #FF4B4B; border: none; color: white; padding: 10px 20px; text-align: center; text-decoration: none; display: inline-block; font-size: 16px; margin: 4px 2px; cursor: pointer; border-radius: 5px; font-family: sans-serif; font-weight: bold;">
                    ⬇️ Descargar Todos los Archivos (1 Clic)
                </button>
                """
                
                components.html(js_code, height=60)

elif modulo == "Proyección desde Pedido MV":
    st.header("🌱 Proyección desde Pedido Confirmado MV")
    st.markdown("Carga el pedido consolidado aprobado por la finca propagadora. El sistema descontará la merma y proyectará las siembras y la cosecha futura.")
    
    # Explicacion visual
    st.info("🕒 **Línea de Tiempo Operativa**: Pedido Confirmado / Recepción (Semana **S**) ➔ 3 Semanas Enraizamiento ➔ Siembra a Campo (Semana **S+4**).")
    
    uploaded_plan = st.file_uploader("📥 Cargar Pedido Consolidado (Excel)", type=["xlsx", "xls"])
    
    if uploaded_plan is not None:
        if st.button("Generar Proyecciones"):
            with st.spinner("Procesando siembras futuras y calculando proyecciones de cosecha a largo plazo..."):
                import sys
                import os
                sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
                from app.services.mva_service import generar_plan_mva
                
                # Guardar el archivo temporalmente para leerlo con pandas
                file_path = "temp_plan_mva.xlsx"
                with open(file_path, "wb") as f:
                    f.write(uploaded_plan.getbuffer())
                
                try:
                    df_mrp = generar_plan_mva(file_path, week_is="Pedido")
                    
                    if not df_mrp.empty:
                        st.success("Cálculo de pedidos generado con éxito.")
                        
                        # Tabla principal agrupada por semana de pedido y variedad
                        df_resumen = df_mrp.groupby(['Semana_Pedido_MV', 'Variedad']).agg({
                            'Esquejes_Pedido_MV': 'sum',
                            'Esquejes_Para_Siembra (Final)': 'sum'
                        }).reset_index()
                        
                        # Mostramos una tabla dinámica
                        st.subheader("Resumen de Siembras Proyectadas")
                        st.dataframe(df_resumen.style.format({
                            'Esquejes_Pedido_MV': "{:,.0f}",
                            'Esquejes_Para_Siembra (Final)': "{:,.0f}"
                        }), use_container_width=True)
                        
                        # Generar Proyeccion 52 Semanas
                        from app.services.mva_service import proyectar_cosecha_desde_mva
                        df_proyeccion = proyectar_cosecha_desde_mva(df_mrp, db)
                        
                        st.success(f"También se ha generado la proyección de cosecha a largo plazo basada en estas siembras futuras (abarcando {len([c for c in df_proyeccion.columns if str(c).startswith('202')])} semanas proyectadas).")
                        
                        # Descargar Archivos
                        import io
                        output_mrp = io.BytesIO()
                        with pd.ExcelWriter(output_mrp, engine='xlsxwriter') as writer:
                            df_mrp.to_excel(writer, index=False, sheet_name="Explosion_MVA")
                            
                        output_proy = io.BytesIO()
                        with pd.ExcelWriter(output_proy, engine='xlsxwriter') as writer:
                            df_proyeccion.to_excel(writer, index=False, sheet_name="Proyeccion_Cosecha")
                        
                        col_dl1, col_dl2 = st.columns(2)
                        col_dl1.download_button(
                            label="⬇️ Descargar Archivo de Siembras (MVA)",
                            data=output_mrp.getvalue(),
                            file_name="Plan_Siembras_Proyectadas.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            type="primary"
                        )
                        col_dl2.download_button(
                            label="⬇️ Descargar Proyección de Cosecha a Futuro",
                            data=output_proy.getvalue(),
                            file_name="Proyeccion_Cosecha_Largo_Plazo.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            type="primary"
                        )
                    else:
                        st.warning("El archivo no contenía datos válidos para generar la proyección de MVA.")
                except Exception as e:
                    st.error(f"Error al procesar el archivo: {e}")
