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
    
    st.subheader("Carga de Insumos Maestros")
    st.markdown("Sube aquí los archivos base. Una vez cargados, todos los módulos del sistema los usarán automáticamente.")
    
    col_ins1, col_ins2 = st.columns(2)
    
    with col_ins1:
        st.markdown("**1. Plano de Siembra (Inventario Vivo)**")
        if os.path.exists("last_dataset_name.txt"):
            with open("last_dataset_name.txt", "r") as f:
                last_file = f.read().strip()
        else:
            last_file = "Ninguno"
            
        st.info(f"**Cargado:** {last_file}")
        
        uploaded_file = st.file_uploader("Cargar nuevo dataset de Siembras", type=["xlsx", "xls"])
        if uploaded_file is not None:
            if st.button("Procesar Siembras"):
                with st.spinner("Procesando dataset de siembras..."):
                    file_path = "Siembra Actual (16).xlsx"
                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    
                    with open("last_dataset_name.txt", "w") as f:
                        f.write(uploaded_file.name)
                    
                    from scripts.ingestar_siembra import ingestar_siembra_actual
                    ingestar_siembra_actual()
                    
                    st.success("Datos de siembra actualizados.")
                    st.rerun()
                    
    with col_ins2:
        st.markdown("**2. Pedido Consolidado (MVA)**")
        if os.path.exists("PedidoConsolidado_master.xlsx"):
            st.info("✅ Pedido Consolidado disponible en el sistema.")
        else:
            st.warning("⚠️ No hay Pedido Consolidado cargado.")
            
        uploaded_pedido = st.file_uploader("Cargar nuevo Pedido Consolidado", type=["xlsx", "xls"])
        if uploaded_pedido is not None:
            if st.button("Guardar Pedido MVA"):
                with open("PedidoConsolidado_master.xlsx", "wb") as f:
                    f.write(uploaded_pedido.getbuffer())
                st.success("Pedido guardado. Se usará automáticamente en las proyecciones.")
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
        st.info("💡 **Automatización 13 Semanas:** Las primeras 9 semanas se llenan con la proyección real de campo. Las 4 semanas finales se rellenan usando el Pedido Consolidado MVA configurado en el Dashboard.")

    if uploaded_templates:
        if st.button("Procesar y Llenar Plantillas"):
            with st.spinner("Generando proyecciones e inyectando datos en las plantillas..."):
                # Generar forecast global (primeras 9 semanas)
                df_forecast = generar_forecast_13wk(db)
                
                # Cargar plan (últimas 4 semanas) desde MVA si existe el maestro
                df_plan = None
                file_path = "PedidoConsolidado_master.xlsx"
                if os.path.exists(file_path):
                    import sys
                    import os
                    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
                    from app.services.mva_service import generar_plan_mva, proyectar_cosecha_desde_mva
                    
                    try:
                        df_mrp = generar_plan_mva(file_path, week_is="Pedido")
                        df_proyeccion = proyectar_cosecha_desde_mva(df_mrp, db)
                        
                        if not df_proyeccion.empty:
                            # Preparar df_plan agrupando por Variedad y normalizando el índice
                            df_plan = df_proyeccion.groupby('Variedad').sum()
                            df_plan.index = df_plan.index.astype(str).str.strip().str.lower()
                    except Exception as e:
                        st.error(f"Error procesando Pedido MVA maestro: {e}")
                else:
                    st.warning("No se encontró un Pedido Consolidado MVA en el sistema. Las últimas 4 semanas quedarán en blanco.")
                
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
    
    uploaded_template_52 = st.file_uploader("📋 Cargar Plantilla Vacía 52 Semanas (Opcional - Excel)", type=["xlsx", "xls"])
    
    if st.button("Generar Proyecciones"):
        file_path = "PedidoConsolidado_master.xlsx"
        if not os.path.exists(file_path):
            st.error("❌ No hay un Pedido Consolidado configurado. Ve al 'Dashboard General' y cárgalo primero.")
        else:
            with st.spinner("Procesando siembras futuras y calculando proyecciones de cosecha a largo plazo..."):
                import sys
                import os
                sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
                from app.services.mva_service import generar_plan_mva, proyectar_cosecha_desde_mva, combinar_proyecciones_52_semanas, llenar_plantilla_52_semanas
                from app.services.forecast_service import generar_forecast_13wk
                
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
                        
                        # Generar Proyeccion 52 Semanas (MVA puro)
                        df_proyeccion_mva = proyectar_cosecha_desde_mva(df_mrp, db)
                        
                        # Combinar con el inventario vivo (PER13)
                        df_forecast_vivo = generar_forecast_13wk(db)
                        df_52_semanas = combinar_proyecciones_52_semanas(df_forecast_vivo, df_proyeccion_mva)
                        
                        st.success(f"También se ha generado la proyección Consolidada de 52 Semanas (combinando {len([c for c in df_forecast_vivo.columns if str(c).startswith('202')][:9])} semanas de inventario vivo y el resto del pedido MVA).")
                        
                        # Descargar Archivos
                        import io
                        output_mrp = io.BytesIO()
                        with pd.ExcelWriter(output_mrp, engine='xlsxwriter') as writer:
                            df_mrp.to_excel(writer, index=False, sheet_name="Explosion_MVA")
                        
                        # Si subió plantilla, usarla. Si no, descargar el raw df
                        if uploaded_template_52 is not None:
                            filled_template_bytes = llenar_plantilla_52_semanas(uploaded_template_52.getvalue(), df_52_semanas)
                            proy_data = filled_template_bytes
                            proy_filename = uploaded_template_52.name
                        else:
                            output_proy = io.BytesIO()
                            with pd.ExcelWriter(output_proy, engine='xlsxwriter') as writer:
                                df_52_semanas.to_excel(writer, index=False, sheet_name="Proyeccion_52W")
                            proy_data = output_proy.getvalue()
                            proy_filename = "Proyeccion_52_Semanas_Consolidada.xlsx"
                        
                        col_dl1, col_dl2 = st.columns(2)
                        col_dl1.download_button(
                            label="⬇️ Descargar Archivo de Siembras (MVA)",
                            data=output_mrp.getvalue(),
                            file_name="Plan_Siembras_Proyectadas.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            type="primary"
                        )
                        col_dl2.download_button(
                            label="⬇️ Descargar Proyección 52 Semanas",
                            data=proy_data,
                            file_name=proy_filename,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            type="primary"
                        )
                    else:
                        st.warning("El archivo no contenía datos válidos para generar la proyección de MVA.")
                except Exception as e:
                    st.error(f"Error al procesar el archivo: {e}")
