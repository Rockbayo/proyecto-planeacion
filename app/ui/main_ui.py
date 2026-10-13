import sys
import os
import json
import streamlit as st
import pandas as pd
from datetime import date
import plotly.graph_objects as go

# Añadir el directorio raíz al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from app.core.database import SessionLocal, engine
from app.models.models import Variedad
from app.services.forecast_service import generar_forecast_13wk, generar_forecast_ml_live, isocalendar_to_string

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
modulo = st.sidebar.radio("Ir a:", ["Dashboard General", "Curvas e Índices (Campo)", "ForeCast y Exportación", "Programación Diaria y Temporadas", "Plan de Producción (MVA)", "Pedido Material Vegetal", "Precisión y ML (Accuracy)"])

from app.ui.curvas_ui import render_curvas_module
from app.ui.accuracy_ui import render_accuracy_module
from app.ui.actas_ui import render_actas_module

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
    
    col_ins1, col_ins2, col_ins3 = st.columns(3)
    
    with col_ins1:
        st.markdown("**1. Catálogo de Variedades (Maestro)**")
        total_catalog = db.query(Variedad).count()
        flores_count = pd.read_sql("SELECT flor, count(*) as cant FROM variedades GROUP BY flor", engine)
        flores_str = ", ".join([f"{r['flor']}: {r['cant']}" for _, r in flores_count.iterrows()]) if not flores_count.empty else "Ninguna"
        
        if total_catalog > 0:
            st.info(f"**Registradas:** {total_catalog:,} variedades\n\n*{flores_str}*")
        else:
            st.warning("⚠️ No hay catálogo de variedades registrado.")
            
        uploaded_vars = st.file_uploader("Cargar Listado(s) de Variedades", type=["xlsx", "xls"], accept_multiple_files=True, key="upload_vars")
        if uploaded_vars:
            if st.button("Procesar Catálogo de Variedades"):
                with st.spinner("Procesando listados de variedades..."):
                    from app.services.variedad_service import procesar_archivos_variedades
                    res = procesar_archivos_variedades(uploaded_vars, db)
                    st.success(f"Catálogo actualizado con éxito: {res.get('total_en_db', 0)} variedades en total ({res.get('insertadas', 0)} nuevas, {res.get('actualizadas', 0)} actualizadas).")
                    st.rerun()
                    
    with col_ins2:
        st.markdown("**2. Plano de Siembra (Inventario Vivo)**")
        if os.path.exists("last_dataset_name.txt"):
            with open("last_dataset_name.txt", "r") as f:
                last_file = f.read().strip()
        else:
            last_file = "Ninguno"
            
        st.info(f"**Cargado:** {last_file}")
        
        uploaded_file = st.file_uploader("Cargar nuevo dataset de Siembras", type=["xlsx", "xls"], key="upload_siembras")
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
                    
    with col_ins3:
        st.markdown("**3. Pedido Consolidado (MVA)**")
        if os.path.exists("PedidoConsolidado_master.xlsx"):
            st.info("✅ Pedido Consolidado disponible en el sistema.")
        else:
            st.warning("⚠️ No hay Pedido Consolidado cargado.")
            
        uploaded_pedido = st.file_uploader("Cargar nuevo Pedido Consolidado", type=["xlsx", "xls"], key="upload_pedido")
        if uploaded_pedido is not None:
            if st.button("Guardar Pedido MVA"):
                with open("PedidoConsolidado_master.xlsx", "wb") as f:
                    f.write(uploaded_pedido.getbuffer())
                st.success("Pedido guardado. Se usará automáticamente en las proyecciones.")
                st.rerun()
                
    st.divider()

elif modulo == "Curvas e Índices (Campo)":
    render_curvas_module(db)

elif modulo == "ForeCast y Exportación":
    st.header("📈 ForeCast y Exportación (S&OP)")
    st.markdown("Proyección de cosecha consolidada y exportación de plantillas (Webflowers / 52 Semanas).")
    
    # Selector de horizonte
    vista = st.radio("Selecciona el horizonte de proyección:", ["13 Semanas Móviles", "52 Semanas (Año Completo)"], horizontal=True)
    num_semanas = 14 if vista == "13 Semanas Móviles" else 52
    
    # Parametros visuales
    st.sidebar.markdown("### Parámetros de Suavización")
    ponderacion = st.sidebar.slider("Ponderación (%)", 0, 100, 100)
    periodos = st.sidebar.number_input("Ciclos (Periodos)", min_value=1, value=9)
    
    with st.spinner(f"Generando matriz de pronóstico ({vista})..."):
        # 1. Proyección de Inventario Vivo (Cubre hasta 9 semanas)
        df_forecast_vivo = generar_forecast_13wk(db, alpha=(ponderacion/100.0), num_ciclos=periodos)
        
        # 2. Cargar MVA para las semanas faltantes
        import os
        from app.services.mva_service import generar_plan_mva, proyectar_cosecha_desde_mva, combinar_proyecciones_52_semanas, llenar_plantilla_52_semanas
        file_path = "PedidoConsolidado_master.xlsx"
        
        df_mrp = pd.DataFrame()
        has_mva = False
        if os.path.exists(file_path):
            try:
                df_mrp = generar_plan_mva(file_path, week_is="Pedido")
                df_proyeccion_mva = proyectar_cosecha_desde_mva(df_mrp, db)
                df_forecast = combinar_proyecciones_52_semanas(df_forecast_vivo, df_proyeccion_mva)
                has_mva = not df_proyeccion_mva.empty
                if vista == "13 Semanas Móviles":
                    st.info("💡 **Diferenciación visual:** La línea **Verde continua** corresponde a las semanas calculadas del **Plano de Siembras** (inventario vivo en campo). La línea **Naranja discontinua** corresponde a la proyección del **Pedido de Material Vegetal (MVA)**.")
                else:
                    st.info("💡 **Diferenciación visual:** Las primeras 10 semanas (**Verde continua**) provienen del **Plano de Siembras** (inventario vivo). A partir de la semana 11 (**Naranja discontinua**), la proyección proviene del **Pedido de Material Vegetal (MVA)**.")
            except Exception as e:
                st.warning(f"Error procesando el archivo Maestro MVA: {e}")
                df_forecast = df_forecast_vivo
        else:
            st.warning("No se encontró el Pedido Consolidado Maestro. Mostrando únicamente el inventario vivo.")
            df_forecast = df_forecast_vivo
        
    if df_forecast.empty:
        st.warning("No hay datos suficientes para generar el forecast.")
    else:
        semanas_cols = [col for col in df_forecast.columns if str(col).startswith('202')]
        semanas_cols = sorted(semanas_cols)
        
        semana_actual = isocalendar_to_string(date.today())
        semanas_futuras = [s for s in semanas_cols if s >= semana_actual]
        if len(semanas_futuras) > num_semanas:
            semanas_futuras = semanas_futuras[:num_semanas]
            
        # Resaltar la semana actual
        if semana_actual in df_forecast.columns:
            nombre_actual = f"{semana_actual} (Actual)"
            df_forecast = df_forecast.rename(columns={semana_actual: nombre_actual})
            semanas_futuras = [nombre_actual if s == semana_actual else s for s in semanas_futuras]
            
        if semanas_futuras:
            fc_agrupado = df_forecast[semanas_futuras].sum()
            
            # Clasificar semanas entre Plano de Siembras (Inventario Vivo) y Pedido de Material Vegetal
            cols_fc_vivo = sorted([c for c in df_forecast_vivo.columns if str(c).startswith('202')])
            semanas_viv_raw = set([s for s in cols_fc_vivo if s >= semana_actual][:10])
            
            semanas_plano = [s for s in semanas_futuras if (s.split(" ")[0] in semanas_viv_raw or not has_mva)]
            semanas_mva_fut = [s for s in semanas_futuras if s not in semanas_plano]
            
            ultima_sem_plano = semanas_plano[-1] if semanas_plano else None
            
            # Serie Plano de Siembras
            y_plano = [fc_agrupado[s] if s in semanas_plano else None for s in semanas_futuras]
            # Serie Material Vegetal (enlaza en la última semana de plano para continuidad visual)
            y_mva = [fc_agrupado[s] if (s in semanas_mva_fut or s == ultima_sem_plano) else None for s in semanas_futuras]
            hover_mva = ['skip' if s in semanas_plano else 'all' for s in semanas_futuras]
            
            st.subheader("Proyección Semanal vs Plan Aprobado")
            
            # Intentar cargar el plan aprobado
            plan_aprobado_path = "Plan_Aprobado.csv"
            plan_series = pd.Series(0.0, index=semanas_futuras)
            
            if os.path.exists(plan_aprobado_path):
                try:
                    df_plan_app = pd.read_csv(plan_aprobado_path)
                    col_capacidad = 'Tallos a Producir (Capacidad)' if 'Tallos a Producir (Capacidad)' in df_plan_app.columns else 'Suma de Tallos'
                    if 'Semana' in df_plan_app.columns and col_capacidad in df_plan_app.columns:
                        def clean_semana(val):
                            if pd.isna(val):
                                return ""
                            try:
                                return str(int(float(val)))
                            except:
                                return str(val).strip()
                                
                        df_plan_app['Semana'] = df_plan_app['Semana'].apply(clean_semana)
                        
                        # Agrupar el plan aprobado por semana (Tallos a producir de la contrapropuesta)
                        df_plan_grp = df_plan_app.groupby('Semana')[col_capacidad].sum()
                        
                        # Alinear con las semanas futuras del chart
                        for sem_fut in semanas_futuras:
                            # Limpiar nombre por si tiene " (Actual)"
                            sem_clean = sem_fut.split(" ")[0]
                            if sem_clean in df_plan_grp.index:
                                plan_series[sem_fut] = df_plan_grp[sem_clean]
                    st.success("✅ Comparando contra el Plan Aprobado (Contrapropuesta consolidada).")
                except Exception:
                    st.warning("No se pudo leer el Plan Aprobado, usando 0.")
            else:
                st.info("💡 No hay un 'Plan Aprobado' guardado en el módulo MVA. Usa el módulo 'Plan de Producción' para procesar y consolidar un plan.")
                col_plan1, col_plan2 = st.columns([1, 3])
                plan_fallback = col_plan1.number_input("Meta del Plan (Fallback)", value=400000, step=10000)
                plan_series = pd.Series(plan_fallback, index=semanas_futuras)
                
            fig_fc = go.Figure()
            
            # 1. Trazo ForeCast: Plano de Siembras (Inventario Vivo)
            fig_fc.add_trace(go.Scatter(
                x=semanas_futuras,
                y=y_plano,
                mode='lines+markers',
                name="ForeCast (Plano Siembras)",
                line=dict(color='#2E7D32', width=3),
                marker=dict(size=6, symbol='circle'),
                hovertemplate="<b>Semana %{x}</b><br>Plano Siembras: %{y:,.0f} tallos<extra></extra>"
            ))
            
            # 2. Trazo ForeCast: Material Vegetal (MVA)
            if semanas_mva_fut:
                fig_fc.add_trace(go.Scatter(
                    x=semanas_futuras,
                    y=y_mva,
                    mode='lines+markers',
                    name="ForeCast (Material Vegetal)",
                    line=dict(color='#E65100', width=3, dash='dash'),
                    marker=dict(size=6, symbol='diamond'),
                    hoverinfo=hover_mva,
                    hovertemplate="<b>Semana %{x}</b><br>Material Vegetal: %{y:,.0f} tallos<extra></extra>"
                ))
                
                # Línea y anotación de transición
                if ultima_sem_plano:
                    fig_fc.add_shape(
                        type='line',
                        xref='x',
                        yref='paper',
                        x0=ultima_sem_plano,
                        x1=ultima_sem_plano,
                        y0=0,
                        y1=0.90,
                        line=dict(color='#9E9E9E', width=1.5, dash='dot')
                    )
                    fig_fc.add_annotation(
                        x=ultima_sem_plano,
                        y=0.95,
                        yref='paper',
                        text='<b>Inicio Material Vegetal (MVA) →</b>',
                        showarrow=False,
                        xanchor='left',
                        font=dict(size=11, color='#E65100')
                    )
            
            # 3. Línea de Plan Aprobado
            if plan_series.sum() > 0:
                fig_fc.add_trace(go.Scatter(
                    x=semanas_futuras,
                    y=plan_series,
                    mode='lines+markers',
                    name="Plan Aprobado",
                    line=dict(color='#1976D2', width=2.5, dash='dot'),
                    marker=dict(size=5, symbol='square'),
                    hovertemplate="<b>Semana %{x}</b><br>Plan Aprobado: %{y:,.0f} tallos<extra></extra>"
                ))
                
            fig_fc.update_layout(
                title=dict(text=f"Proyección Semanal vs Plan Aprobado ({vista})", font=dict(size=16)),
                xaxis=dict(
                    type='category',  # Evita formato numérico 202.64k y muestra los nombres exactos de semana
                    title="Semana Operativa",
                    tickangle=-45,
                    fixedrange=True,  # Bloquea zoom y arrastre horizontal
                    gridcolor='#f0f0f0'
                ),
                yaxis=dict(
                    title="Tallos Proyectados",
                    tickformat=",.0f",
                    fixedrange=True,  # Bloquea zoom y arrastre vertical
                    gridcolor='#f0f0f0'
                ),
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                margin=dict(l=40, r=40, t=60, b=40)
            )
            
            st.plotly_chart(fig_fc, use_container_width=True, config={'scrollZoom': False, 'displayModeBar': False})
            
            st.markdown("**Comparativo ForeCast vs Plan Aprobado:**")
            df_comp = pd.DataFrame(index=semanas_futuras)
            df_comp['Origen'] = [
                '🌱 Plano Siembras' if s in semanas_plano else '📦 Material Vegetal'
                for s in semanas_futuras
            ]
            df_comp['ForeCast Total'] = fc_agrupado
            df_comp['Plan Aprobado'] = plan_series
            df_comp['Variación %'] = df_comp.apply(
                lambda row: ((row['ForeCast Total'] / row['Plan Aprobado']) - 1) * 100 if row['Plan Aprobado'] > 0 else 0,
                axis=1
            )
            
            df_comp_display = df_comp.copy()
            df_comp_display['ForeCast Total'] = df_comp_display['ForeCast Total'].apply(lambda x: f"{int(x):,}")
            df_comp_display['Plan Aprobado'] = df_comp_display['Plan Aprobado'].apply(lambda x: f"{int(x):,}")
            df_comp_display['Variación %'] = df_comp_display['Variación %'].apply(lambda x: f"{x:+.1f}%")
            
            st.dataframe(df_comp_display.T, use_container_width=True)
            
        st.divider()
        # Filtrar por variedades que tengan inventario vivo (sembradas actualmente)
        if not df_forecast_vivo.empty and 'Variedad' in df_forecast_vivo.columns:
            variedades_sembradas = df_forecast_vivo['Variedad'].dropna().unique()
            df_forecast = df_forecast[df_forecast['Variedad'].isin(variedades_sembradas)]

        st.subheader("Resumen Total por Flor")
        df_forecast['TOTAL'] = df_forecast[semanas_futuras].sum(axis=1) if semanas_futuras else 0
        
        # Filtrar solo lo que tiene producción en el horizonte
        df_forecast = df_forecast[df_forecast['TOTAL'] > 0]
        
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
            
            for col in ['Sede', 'Flor', 'Color', 'Variedad']:
                if col in df_forecast.columns:
                    total_row[col] = ""
                    
            if 'Variedad' in total_row.columns:
                total_row['Variedad'] = 'TOTAL GENERAL'
            elif 'Flor' in total_row.columns:
                total_row['Flor'] = 'TOTAL GENERAL'
            
            meta_cols = [c for c in ['Sede', 'Flor', 'Color', 'Variedad'] if c in df_forecast.columns]
            df_forecast_display = df_forecast[meta_cols + cols_num].copy()
            
            df_forecast_display = pd.concat([df_forecast_display, total_row], ignore_index=True)
            st.dataframe(df_forecast_display.style.format(formatter={col: "{:,.0f}" for col in cols_num}), use_container_width=True)
        else:
            st.dataframe(df_forecast, use_container_width=True)

        st.divider()
        
        # EXPORTACIONES
        if vista == "13 Semanas Móviles":
            st.subheader("📤 Exportación Webflowers (13 Semanas)")
            st.markdown("Carga las plantillas vacías descargadas de la plataforma. El sistema inyectará **9 semanas** de proyecciones basadas en inventario vivo, y rellenará las **4 semanas** restantes con el Plan de Producción del Pedido Consolidado Maestro.")
            
            col_up1, col_up2 = st.columns(2)
            with col_up1:
                uploaded_templates = st.file_uploader("📥 Subir Plantillas Webflowers Vacías (Excel)", type=["xlsx", "xls"], accept_multiple_files=True)
            
            with col_up2:
                st.info("💡 **Automatización 13 Semanas:** Las primeras 9 semanas se llenan con la proyección real de campo. Las 4 semanas finales se rellenan usando el Pedido Consolidado MVA configurado en el Dashboard.")
            
            if uploaded_templates:
                if st.button("Procesar y Llenar Plantillas 13 Wk"):
                    with st.spinner("Generando proyecciones e inyectando datos en las plantillas..."):
                        # df_forecast ya está calculado con los datos MVA en df_forecast. 
                        # PERO OJO: export_plataforma procesar_plantillas_plataforma espera 
                        # df_forecast (el vivo) y df_plan (el MVA separado).
                        
                        df_plan = None
                        if not df_mrp.empty:
                            df_proyeccion_mva = proyectar_cosecha_desde_mva(df_mrp, db)
                            if not df_proyeccion_mva.empty:
                                df_plan = df_proyeccion_mva.groupby('Variedad').sum()
                                df_plan.index = df_plan.index.astype(str).str.strip().str.lower()
                                
                        import sys
                        import os
                        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
                        from scripts.export_plataforma import procesar_plantillas_plataforma
                        
                        templates_dict = {f.name: f.getvalue() for f in uploaded_templates}
                        resultados = procesar_plantillas_plataforma(templates_dict, df_forecast_vivo, df_plan)
                        
                        st.success(f"Se procesaron {len(resultados)} plantillas exitosamente.")
                        
                        import base64

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
                                }}, index * 500); 
                            }});
                        }}
                        </script>
                        <button onclick="downloadAll()" style="background-color: #FF4B4B; border: none; color: white; padding: 10px 20px; text-align: center; text-decoration: none; display: inline-block; font-size: 16px; margin: 4px 2px; cursor: pointer; border-radius: 5px; font-family: sans-serif; font-weight: bold;">
                            ⬇️ Descargar Todos los Archivos (1 Clic)
                        </button>
                        """
                        
                        components.html(js_code, height=60)
        else:
            st.subheader("📤 Exportación 52 Semanas")
            st.info("🕒 **Línea de Tiempo Operativa**: Pedido Confirmado / Recepción (Semana **S**) ➔ 3 Semanas Enraizamiento ➔ Siembra a Campo (Semana **S+4**).")
            
            uploaded_template_52 = st.file_uploader("📋 Cargar Plantilla Vacía 52 Semanas (Excel)", type=["xlsx", "xls"])
            
            if uploaded_template_52 is not None:
                if st.button("Procesar y Descargar Plantilla 52 Semanas"):
                    with st.spinner("Procesando archivos para descarga..."):
                        import io
                        # Descargar Archivos de MVA original
                        output_mrp = io.BytesIO()
                        if not df_mrp.empty:
                            with pd.ExcelWriter(output_mrp, engine='xlsxwriter') as writer:
                                df_mrp.to_excel(writer, index=False, sheet_name="Explosion_MVA")
                            
                        # Si subió plantilla, usarla.
                        df_proy_mva = proyectar_cosecha_desde_mva(df_mrp, db) if not df_mrp.empty else pd.DataFrame()
                        df_52_semanas = combinar_proyecciones_52_semanas(df_forecast_vivo, df_proy_mva)
                        
                        filled_template_bytes = llenar_plantilla_52_semanas(uploaded_template_52.getvalue(), df_52_semanas)
                        proy_data = filled_template_bytes
                        proy_filename = uploaded_template_52.name
                    
                    col_dl1, col_dl2 = st.columns(2)
                    if not df_mrp.empty:
                        col_dl1.download_button(
                            label="⬇️ Descargar Plan de Siembras (MVA)",
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

elif modulo == "Programación Diaria y Temporadas":
    st.header("📅 Programación Diaria y Gestión de Temporadas")
    st.markdown("Configura la distribución diaria de cortes y haz seguimiento al volumen de las temporadas críticas.")
    
    tab1, tab2 = st.tabs(["Distribución de Corte Diario", "Seguimiento de Temporadas"])
    
    with tab1:
        st.subheader("Porcentajes de Corte Diario por Flor")
        st.markdown("Asigna cómo se distribuye el volumen proyectado de la semana entre los días de corte.")
        
        flores_db = sorted(list(set([v.flor for v in db.query(Variedad).all() if v.flor])))
        
        # Horarios base: Lunes, Martes, Jueves, Viernes: 8h | Miercoles: 7.5h | Sabado: 5h | Domingo: 0h
        # Total normal = 8+8+7.5+8+8+5 = 44.5h
        horas = {"Lunes": 8, "Martes": 8, "Miércoles": 7.5, "Jueves": 8, "Viernes": 8, "Sábado": 5, "Domingo": 0}
        total_horas = sum(horas.values())
        
        pct_base = {dia: (h / total_horas) * 100 for dia, h in horas.items()}
        
        config_diario = {flor: pct_base.copy() for flor in flores_db}
        
        df_config = pd.DataFrame(config_diario).T.reset_index().rename(columns={"index": "Flor"})
        
        col_ed1, col_ed2 = st.columns([2, 1])
        with col_ed1:
            format_config = {d: "{:.0f}%" for d in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]}
            st.dataframe(df_config.style.format(format_config), use_container_width=True, hide_index=True)
            
        with col_ed2:
            st.info("💡 **Nota de Capacidad**: Estos porcentajes reflejan la capacidad operativa estándar (Lun, Mar, Jue, Vie: 6am-2pm [8h] | Mie: 6am-1:30pm [7.5h] | Sab: 6am-11am [5h]).")
            st.info("🔥 **Temporadas**: Los Domingos solo se activarán automáticamente si la semana a desagregar pertenece a las temporadas de 'San valentin' o 'madres'.")
            
        st.divider()
        st.subheader("Generar Plan de Corte Diario")
        col_gen1, col_gen2 = st.columns(2)
        semana_target = col_gen1.text_input("Semana a desagregar (ej. 202640):")
        lunes_festivo = col_gen2.checkbox("¿La semana seleccionada tiene Lunes Festivo?")
        
        if st.button("Calcular Corte Diario"):
            if not semana_target:
                st.warning("Por favor ingresa una semana válida.")
            else:
                with st.spinner("Desagregando proyección..."):
                    df_forecast_vivo = generar_forecast_13wk(db)
                    
                    from app.services.mva_service import generar_plan_mva, proyectar_cosecha_desde_mva, combinar_proyecciones_52_semanas
                    file_path = "PedidoConsolidado_master.xlsx"
                    if os.path.exists(file_path):
                        df_mrp = generar_plan_mva(file_path, week_is="Pedido")
                        df_proyeccion_mva = proyectar_cosecha_desde_mva(df_mrp, db)
                        df_52 = combinar_proyecciones_52_semanas(df_forecast_vivo, df_proyeccion_mva)
                    else:
                        df_52 = df_forecast_vivo
                        
                    if semana_target not in df_52.columns:
                        st.error(f"La semana {semana_target} no tiene proyecciones disponibles.")
                    else:
                        df_week = df_52[['Flor', 'Color', 'Variedad', semana_target]].copy()
                        df_week = df_week[df_week[semana_target] > 0]
                        
                        # Determinar si la semana objetivo está en temporada de domingos
                        es_temporada_domingo = False
                        seasons_file = "config_temporadas.json"
                        if os.path.exists(seasons_file):
                            with open(seasons_file, "r", encoding="utf-8") as f:
                                saved_seasons = json.load(f)
                        else:
                            saved_seasons = [
                                {"Temporada": "Fall", "Semana Inicio": 202632, "Semana Fin": 202646},
                                {"Temporada": "Navidad", "Semana Inicio": 202647, "Semana Fin": 202650},
                                {"Temporada": "San valentin", "Semana Inicio": 202703, "Semana Fin": 202705},
                                {"Temporada": "Madres", "Semana Inicio": 202716, "Semana Fin": 202718},
                                {"Temporada": "Summer", "Semana Inicio": 202719, "Semana Fin": 202731}
                            ]
                        
                        try:
                            sem_target_int = int(semana_target)
                            for s in saved_seasons:
                                name_lower = str(s.get("Temporada", "")).lower()
                                import unicodedata
                                name_lower = ''.join(c for c in unicodedata.normalize('NFD', name_lower) if unicodedata.category(c) != 'Mn')
                                if name_lower in ["san valentin", "madres"]:
                                    ini = s.get("Semana Inicio", 0)
                                    fin = s.get("Semana Fin", 0)
                                    w_ini = ini % 100 if ini > 100 else ini
                                    w_fin = fin % 100 if fin > 100 else fin
                                    week_target = sem_target_int % 100
                                    
                                    if w_ini <= w_fin:
                                        in_season = (w_ini <= week_target <= w_fin)
                                    else:
                                        in_season = (week_target >= w_ini or week_target <= w_fin)
                                        
                                    if in_season:
                                        es_temporada_domingo = True
                                        break
                        except ValueError:
                            pass

                        records_diarios = []
                        records_pcts = []
                        config_actual = df_config.set_index("Flor").to_dict(orient="index")
                        
                        for _, row in df_week.iterrows():
                            flor = row['Flor']
                            vol_semanal = row[semana_target]
                            
                            dist = config_actual.get(flor, {"Lunes": 17.98, "Martes": 17.98, "Miércoles": 16.85, "Jueves": 17.98, "Viernes": 17.98, "Sábado": 11.23, "Domingo": 0.0})
                            
                            dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
                            pcts = {d: float(dist.get(d, 0)) for d in dias}
                            
                            if es_temporada_domingo:
                                # Recalcular porcentajes sobre 49.5 horas en lugar de 44.5
                                # L,M,J,V = 8/49.5 = 16.16%
                                # Mi = 7.5/49.5 = 15.15%
                                # S,D = 5/49.5 = 10.10%
                                pcts = {
                                    "Lunes": 16.1616, "Martes": 16.1616, "Miércoles": 15.1515,
                                    "Jueves": 16.1616, "Viernes": 16.1616, "Sábado": 10.1010, "Domingo": 10.1010
                                }
                            
                            if lunes_festivo and pcts["Lunes"] > 0:
                                pct_a_repartir = pcts["Lunes"]
                                pcts["Lunes"] = 0.0
                                # Repartir entre los dias que tengan porcentaje > 0
                                dias_activos = [d for d in dias if d != "Lunes" and pcts[d] > 0]
                                if dias_activos:
                                    extra_por_dia = pct_a_repartir / len(dias_activos)
                                    for d in dias_activos:
                                        pcts[d] += extra_por_dia
                                        
                            # Calcular tallos
                            tallos_diarios = {d: int(round(vol_semanal * (pcts[d] / 100.0))) for d in dias}
                            
                            # Ajuste por redondeo para que sume exacto el semanal
                            suma_calc = sum(tallos_diarios.values())
                            diff = vol_semanal - suma_calc
                            if diff != 0:
                                # Aplicar la diferencia al dia con mayor volumen
                                dia_max = max(tallos_diarios, key=tallos_diarios.get)
                                tallos_diarios[dia_max] += diff
                                
                            rec = {
                                "Flor": flor,
                                "Color": row['Color'],
                                "Variedad": row['Variedad'],
                                "Vol. Semanal": vol_semanal
                            }
                            rec.update(tallos_diarios)
                            records_diarios.append(rec)
                            
                            rec_pct = {
                                "Flor": flor,
                                "Color": row['Color'],
                                "Variedad": row['Variedad']
                            }
                            rec_pct.update({d: pcts[d] for d in dias})
                            records_pcts.append(rec_pct)
                            
                        if records_diarios:
                            df_pcts = pd.DataFrame(records_pcts)
                            df_diario = pd.DataFrame(records_diarios)
                            
                            st.success(f"Distribución generada para {len(df_diario)} variedades en la semana {semana_target}.")
                            
                            st.markdown("#### Distribución en Porcentajes")
                            format_dict = {d: "{:.0f}%" for d in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]}
                            st.dataframe(df_pcts.style.format(format_dict), use_container_width=True)
                            
                            st.markdown("#### Distribución en Tallos")
                            st.dataframe(df_diario, use_container_width=True)
                            
                            import io
                            output = io.BytesIO()
                            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                                df_diario.to_excel(writer, index=False, sheet_name=f"Corte_{semana_target}")
                            
                            st.download_button(
                                label="⬇️ Descargar Distribución Diaria (Excel)",
                                data=output.getvalue(),
                                file_name=f"Distribucion_Corte_{semana_target}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                type="primary"
                            )
                        else:
                            st.info("No hay proyecciones para desagregar en esta semana.")

    with tab2:
        st.subheader("Configuración de Temporadas")
        st.markdown("Define las semanas que componen cada temporada. **Nota:** Puedes agregar nuevas temporadas en la tabla usando el botón '+' al final (ej. Easter o San Patricio). 'Every Day' se calcula automáticamente como el restante.")
        
        seasons_file = "config_temporadas.json"
        if os.path.exists(seasons_file):
            with open(seasons_file, "r", encoding="utf-8") as f:
                seasons = json.load(f)
        else:
            seasons = [
                {"Temporada": "Fall", "Semana Inicio": 202632, "Semana Fin": 202646},
                {"Temporada": "Navidad", "Semana Inicio": 202647, "Semana Fin": 202650},
                {"Temporada": "San valentin", "Semana Inicio": 202703, "Semana Fin": 202705},
                {"Temporada": "Madres", "Semana Inicio": 202716, "Semana Fin": 202718},
                {"Temporada": "Summer", "Semana Inicio": 202719, "Semana Fin": 202731}
            ]
            
        df_seasons = pd.DataFrame(seasons)
        df_seasons_edited = st.data_editor(df_seasons, num_rows="dynamic", use_container_width=True)
        
        if st.button("Guardar Temporadas"):
            with open(seasons_file, "w", encoding="utf-8") as f:
                json.dump(df_seasons_edited.to_dict(orient="records"), f, indent=4)
            st.success("Temporadas actualizadas.")
            
        st.divider()
        st.subheader("Seguimiento de Temporadas")
        st.markdown("Volumen total proyectado (Inventario Vivo + Pedido Consolidado MVA) para cada temporada.")
        
        with st.spinner("Analizando comportamiento de temporadas..."):
            df_forecast_vivo = generar_forecast_13wk(db)
            from app.services.mva_service import generar_plan_mva, proyectar_cosecha_desde_mva, combinar_proyecciones_52_semanas
            file_path = "PedidoConsolidado_master.xlsx"
            if os.path.exists(file_path):
                df_mrp = generar_plan_mva(file_path, week_is="Pedido")
                df_proyeccion_mva = proyectar_cosecha_desde_mva(df_mrp, db)
                df_52 = combinar_proyecciones_52_semanas(df_forecast_vivo, df_proyeccion_mva)
            else:
                df_52 = df_forecast_vivo
                
            results = []
            cols = [c for c in df_52.columns if str(c).startswith('202')]
            used_cols = set()
            
            for _, s in df_seasons_edited.iterrows():
                name = str(s.get("Temporada", ""))
                start = str(int(s["Semana Inicio"])) if pd.notna(s.get("Semana Inicio")) else ""
                end = str(int(s["Semana Fin"])) if pd.notna(s.get("Semana Fin")) else ""
                try:
                    ini = int(float(s.get("Semana Inicio", 0)))
                    fin = int(float(s.get("Semana Fin", 0)))
                except:
                    ini = 0
                    fin = 0
                
                w_ini = ini % 100 if ini > 100 else ini
                w_fin = fin % 100 if fin > 100 else fin
                
                valid_cols = []
                for c in cols:
                    try:
                        w_c = int(str(c)) % 100
                        if w_ini <= w_fin:
                            if w_ini <= w_c <= w_fin:
                                valid_cols.append(c)
                        else:
                            if w_c >= w_ini or w_c <= w_fin:
                                valid_cols.append(c)
                    except:
                        pass
                
                used_cols.update(valid_cols)
                
                total_vol = df_52[valid_cols].sum().sum() if valid_cols else 0
                    
                results.append({
                    "Temporada": name, 
                    "Rango": f"{start} - {end}", 
                    "Semanas Activas": len(valid_cols), 
                    "Tallos Proyectados": total_vol,
                    "_sort": start if start else "999999"
                })
                
            # Calculamos Every Day con el restante
            valid_cols = [c for c in cols if c not in used_cols]
            total_vol = df_52[valid_cols].sum().sum() if valid_cols else 0
                
            results.append({
                "Temporada": "Every Day", 
                "Rango": "Semanas restantes", 
                "Semanas Activas": len(valid_cols), 
                "Tallos Proyectados": total_vol,
                "_sort": "999999" # Every Day al final
            })
                
            df_res_seasons = pd.DataFrame(results)
            if not df_res_seasons.empty:
                df_res_seasons = df_res_seasons.sort_values(by="_sort").drop(columns=["_sort"]).reset_index(drop=True)
                
                # Crear dataframe para visualización con fila de totales
                df_res_seasons_display = df_res_seasons.copy()
                total_semanas = df_res_seasons_display["Semanas Activas"].sum()
                total_tallos = df_res_seasons_display["Tallos Proyectados"].sum()
                
                total_row = pd.DataFrame([{
                    "Temporada": "TOTAL",
                    "Rango": "-",
                    "Semanas Activas": total_semanas,
                    "Tallos Proyectados": total_tallos
                }])
                df_res_seasons_display = pd.concat([df_res_seasons_display, total_row], ignore_index=True)
            else:
                df_res_seasons_display = df_res_seasons.copy()
            
            col_chart1, col_chart2 = st.columns([1, 2])
            with col_chart1:
                st.dataframe(df_res_seasons_display.style.format({"Tallos Proyectados": "{:,.0f}"}), use_container_width=True)
            with col_chart2:
                if not df_res_seasons.empty and df_res_seasons["Tallos Proyectados"].sum() > 0:
                    import altair as alt
                    chart = alt.Chart(df_res_seasons).mark_bar().encode(
                        x=alt.X('Temporada:N', sort=list(df_res_seasons['Temporada']), title='Temporada', axis=alt.Axis(labelAngle=-45)),
                        y=alt.Y('Tallos Proyectados:Q', title='Tallos'),
                        tooltip=['Temporada', 'Tallos Proyectados']
                    ).properties(height=350)
                    st.altair_chart(chart, use_container_width=True)
                else:
                    st.info("Las proyecciones actuales no alcanzan las semanas de las temporadas configuradas.")

elif modulo == "Plan de Producción (MVA)":
    st.header("📈 Plan de Producción (MVA y Reglas de Negocio)")
    tab_plan, tab_actas = st.tabs(["Planificación y Contrapropuesta", "Gestión MVA"])
    
    with tab_actas:
        render_actas_module(db)
        
    with tab_plan:
        st.markdown("""
        Sube el archivo de plan semanal (Ej: `CH-ValentinesDay-Easter...xlsx`).
        El sistema aplicará la distribución MVA, la regla de 2000 tallos mínimos acumulables en 2 semanas, 
        el cálculo de Camas Completas (Siembra 4800 plantas), y finalmente, **Backward Scheduling** para Siembra y Enraizamiento.
        """)
    
        plan_file = st.file_uploader("Subir Archivo de Plan Semanal (Excel)", type=["xlsx", "xls"])
        if plan_file is not None:
            # Si cambiamos de archivo, limpiamos el estado
            if "plan_file_name" in st.session_state and st.session_state["plan_file_name"] != plan_file.name:
                if "df_contra" in st.session_state:
                    del st.session_state["df_contra"]
                if "df_prod" in st.session_state:
                    del st.session_state["df_prod"]
                
            if "df_contra" not in st.session_state:
                if st.button("Procesar Plan", type="primary"):
                    with st.spinner("Procesando archivo, aplicando MVA y Backward Scheduling..."):
                        try:
                            from app.services.produccion_service import process_plan_produccion
                            df_produccion, df_contrapropuesta = process_plan_produccion(plan_file.getvalue(), db)
                        
                            if df_produccion.empty:
                                st.warning("No se generaron registros. Verifica que el archivo tenga datos válidos.")
                            else:
                                st.session_state["df_contra"] = df_contrapropuesta
                                st.session_state["df_prod"] = df_produccion
                                st.session_state["plan_file_name"] = plan_file.name
                                st.rerun()
                        except Exception as e:
                            import traceback
                            st.error(f"Error procesando el plan: {e}")
                            st.text(traceback.format_exc())
                        
            if "df_contra" in st.session_state:
                df_contrapropuesta = st.session_state["df_contra"]
                df_produccion = st.session_state["df_prod"]
            
                st.success("¡Contrapropuesta generada exitosamente!")
                st.subheader("Contrapropuesta (Ajuste a Capacidad y Aprovechamiento)")
            
                columnas_ui = list(df_contrapropuesta.columns)
                df_contra_display = df_contrapropuesta[columnas_ui].copy()
                if not df_contra_display.empty:
                    total_dict = {}
                    for col in columnas_ui:
                        if col in ['Tallos Solicitados (Plan)', 'Suma de Tallos', 'Variacion']:
                            total_dict[col] = df_contra_display[col].sum()
                        elif col == 'Flower':
                            total_dict[col] = "TOTAL"
                        else:
                            total_dict[col] = ""
                
                    total_contra = pd.DataFrame([total_dict])
                    df_contra_display = pd.concat([df_contra_display, total_contra], ignore_index=True)
            
                st.dataframe(
                    df_contra_display.style.format({
                        "Tallos Solicitados (Plan)": "{:,.0f}",
                        "Suma de Tallos": "{:,.0f}",
                        "Variacion": "{:,.0f}"
                    }),
                    use_container_width=True
                )
            
                st.divider()
            
                col_save, col_dl1, col_dl2 = st.columns([2, 1, 1])
            
                with col_save:
                    if st.button("💾 Guardar Contrapropuesta como Plan Aprobado", type="primary", use_container_width=True):
                        plan_file_path = "Plan_Aprobado.csv"
                        if os.path.exists(plan_file_path):
                            try:
                                # Cargar el plan maestro existente
                                df_master = pd.read_csv(plan_file_path)
                            
                                def clean_sem(val):
                                    if pd.isna(val) or str(val).lower() == 'nan':
                                        return ""
                                    try:
                                        return str(int(float(val)))
                                    except:
                                        return str(val).strip()
                                    
                                df_master['Semana'] = df_master['Semana'].apply(clean_sem)
                            
                                # Identificar semanas en el nuevo ciclo
                                df_produccion['Semana'] = df_produccion['Semana'].apply(clean_sem)
                                nuevas_semanas = df_produccion['Semana'].unique()
                            
                                # Eliminar del maestro las semanas que vienen en este nuevo ciclo
                                df_master = df_master[~df_master['Semana'].isin(nuevas_semanas)]
                            
                                # Agregar el nuevo ciclo y ordenar
                                df_consolidado = pd.concat([df_master, df_produccion], ignore_index=True)
                            
                                if 'Flor' in df_consolidado.columns and 'Color' in df_consolidado.columns and 'Variedad' in df_consolidado.columns:
                                    df_consolidado = df_consolidado.sort_values(['Semana', 'Flor', 'Color', 'Variedad'])
                                else:
                                    df_consolidado = df_consolidado.sort_values(['Semana'])
                                
                                df_consolidado.to_csv(plan_file_path, index=False)
                                st.success(f"¡Ciclo consolidado! Se actualizaron {len(nuevas_semanas)} semanas en el Plan Maestro (semanas {min(nuevas_semanas)} a {max(nuevas_semanas)}).")
                            except Exception as e:
                                st.error(f"Error al consolidar el plan maestro: {e}")
                        else:
                            # Si no existe, guardar como el primero
                            df_produccion.to_csv(plan_file_path, index=False)
                            st.success("¡Primer ciclo guardado como Plan Maestro Aprobado (Detallado por Variedad)!")
            
                import io
                # Generar Excel para Contrapropuesta
                output_contra = io.BytesIO()
                with pd.ExcelWriter(output_contra, engine='xlsxwriter') as writer:
                    df_contrapropuesta.to_excel(writer, index=False, sheet_name='Contrapropuesta')
                output_contra.seek(0)
            
                with col_dl1:
                    st.download_button(
                        label="📥 Descargar Contrapropuesta",
                        data=output_contra.getvalue(),
                        file_name=f"Contrapropuesta_{date.today()}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                
                # Generar Excel para Descargar Plan Detallado
                output_plan = io.BytesIO()
                with pd.ExcelWriter(output_plan, engine='xlsxwriter') as writer:
                    df_produccion.to_excel(writer, index=False, sheet_name='Plan_Detallado')
                output_plan.seek(0)
            
                with col_dl2:
                    st.download_button(
                        label="📥 Descargar Plan Detallado (Flor/Color/Variedad)",
                        data=output_plan.getvalue(),
                        file_name=f"Plan_Detallado_MVA_{date.today()}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

elif modulo == "Pedido Material Vegetal":
    from app.ui.pedido_ui import render_pedido_module
    render_pedido_module(db)

elif modulo == "Precisión y ML (Accuracy)":
    render_accuracy_module(db)


