import streamlit as st
import pandas as pd
from app.models.models import Variedad
import os
import plotly.express as px

def render_curvas_module(db):
    st.header("📈 Curvas e Índices (Datos de Campo)")
    st.markdown("""
    Este módulo consolida la información real de cosecha proveniente de los reportes de campo.
    """)
    
    tab1, tab2 = st.tabs(["📊 Análisis por Flor y Periodo", "⚙️ Ingreso y Simulación de Datos"])
    
    with tab1:
        st.subheader("Análisis de Aprovechamiento y Curvas Reales")
        st.markdown("Selecciona un periodo de cosecha para verificar el comportamiento y aprovechamiento real obtenido por tipo de flor.")
        
        if not os.path.exists('Historico_Curvas.csv'):
            st.warning("No hay datos históricos disponibles. Por favor, sube un reporte en la pestaña de Ingreso de Datos.")
        else:
            df_hist = pd.read_csv('Historico_Curvas.csv')
            
            # Normalizar fechas
            for f in ['FechaSiembra', 'FechaDesbotone', 'FechaInicioProduccion']:
                if f in df_hist.columns:
                    df_hist[f] = pd.to_datetime(df_hist[f], errors='coerce').dt.normalize()
            
            # Cargar información de Flor y Color de la BD maestra
            variedades_db = db.query(Variedad).all()
            var_to_flor = {v.nombre.strip().lower(): v.flor for v in variedades_db}
            var_to_color = {v.nombre.strip().lower(): v.color for v in variedades_db}
            
            df_hist['Flor'] = df_hist['Variedad'].astype(str).str.strip().str.lower().map(var_to_flor)
            df_hist['Flor'] = df_hist['Flor'].fillna('Desconocida')
            df_hist['Color'] = df_hist['Variedad'].astype(str).str.strip().str.lower().map(var_to_color)
            df_hist['Color'] = df_hist['Color'].fillna('Desconocido')
            
            # Filtros de fecha basados en FechaInicioProduccion
            min_date = df_hist['FechaInicioProduccion'].min()
            max_date = df_hist['FechaInicioProduccion'].max()
            
            if pd.isna(min_date) or pd.isna(max_date):
                st.warning("Las fechas de inicio de producción en el histórico son inválidas.")
            else:
                col_f1, col_f2, col_f3 = st.columns([1.5, 1.5, 2])
                with col_f1:
                    start_date = st.date_input("Fecha Inicio Cosecha", min_date)
                with col_f2:
                    end_date = st.date_input("Fecha Fin Cosecha", max_date)
                with col_f3:
                    modo_vista = st.radio("Nivel de Análisis:", ["Por Tipo de Flor", "Por Variedad"], horizontal=True)
                    
                # Aplicar filtro
                start_ts = pd.to_datetime(start_date)
                end_ts = pd.to_datetime(end_date)
                
                mask = (df_hist['FechaInicioProduccion'] >= start_ts) & (df_hist['FechaInicioProduccion'] <= end_ts)
                df_filtered = df_hist.loc[mask].copy()
                
                if df_filtered.empty:
                    st.info("No hay ciclos cosechados en el periodo seleccionado.")
                else:
                    cortes_cols = [f'Corte {i}' for i in range(1, 16)]
                    for c in cortes_cols:
                        if c not in df_filtered.columns:
                            df_filtered[c] = 0.0
                            
                    # Calcular días desde siembra para cada registro
                    df_filtered['DiasInicio'] = (df_filtered['FechaInicioProduccion'] - df_filtered['FechaSiembra']).dt.days
                    
                    if modo_vista == "Por Tipo de Flor":
                        resultados = []
                        records_plot = []
                        
                        df_grouped = df_filtered.groupby('Flor')
                        for flor, group in df_grouped:
                            plantas = group['NumeroPlantas'].sum()
                            sum_cortes = group[cortes_cols].sum()
                            tallos = sum_cortes.sum()
                            aprov = tallos / plantas if plantas > 0 else 0.0
                            
                            dias_ini_series = group['DiasInicio'].dropna()
                            dia_inicio = int(round(dias_ini_series.mean())) if not dias_ini_series.empty else 70
                            
                            corte_max_idx = int(sum_cortes.values.argmax()) if tallos > 0 else 0
                            dia_pico = dia_inicio + corte_max_idx
                            
                            res = {
                                'Flor': flor,
                                'Ciclos Evaluados': len(group),
                                'Total Plantas': plantas,
                                'Total Tallos': tallos,
                                'Aprovechamiento': aprov,
                                'Día Inicio (Promedio)': dia_inicio,
                                'Día Pico (Promedio)': dia_pico
                            }
                            resultados.append(res)
                            
                            for i in range(1, 16):
                                dia_vida = dia_inicio + (i - 1)
                                pct = (sum_cortes[f'Corte {i}'] / tallos * 100) if tallos > 0 else 0.0
                                records_plot.append({
                                    'Serie': flor,
                                    'Día de Vida': dia_vida,
                                    '% de Producción': pct,
                                    'Corte': f"Corte {i}"
                                })
                                
                        if resultados:
                            df_res = pd.DataFrame(resultados)
                            st.markdown("#### Resumen de Aprovechamiento y Ciclos")
                            
                            # Totales y Promedios Ponderados
                            tot_ciclos = int(df_res['Ciclos Evaluados'].sum())
                            tot_plantas = float(df_res['Total Plantas'].sum())
                            tot_tallos = float(df_res['Total Tallos'].sum())
                            aprov_ponderado = (tot_tallos / tot_plantas) if tot_plantas > 0 else 0.0
                            prom_dia_inicio = int(round((df_res['Día Inicio (Promedio)'] * df_res['Total Tallos']).sum() / tot_tallos)) if tot_tallos > 0 else 0
                            prom_dia_pico = int(round((df_res['Día Pico (Promedio)'] * df_res['Total Tallos']).sum() / tot_tallos)) if tot_tallos > 0 else 0
                            
                            m1, m2, m3, m4, m5 = st.columns(5)
                            m1.metric("Ciclos Totales", f"{tot_ciclos:,}")
                            m2.metric("Plantas Totales", f"{tot_plantas:,.0f}")
                            m3.metric("Tallos Totales", f"{tot_tallos:,.0f}")
                            m4.metric("Aprovechamiento Global", f"{aprov_ponderado*100:.1f}%")
                            m5.metric("Ciclo Promedio", f"{prom_dia_inicio} d (Inicio) / {prom_dia_pico} d (Pico)")
                            
                            df_base = df_res[['Flor', 'Ciclos Evaluados', 'Total Plantas', 'Total Tallos', 'Aprovechamiento', 'Día Inicio (Promedio)', 'Día Pico (Promedio)']].copy()
                            
                            row_total = pd.DataFrame([{
                                'Flor': 'TOTAL / PROMEDIO',
                                'Ciclos Evaluados': tot_ciclos,
                                'Total Plantas': tot_plantas,
                                'Total Tallos': tot_tallos,
                                'Aprovechamiento': aprov_ponderado,
                                'Día Inicio (Promedio)': prom_dia_inicio,
                                'Día Pico (Promedio)': prom_dia_pico
                            }])
                            
                            df_final = pd.concat([df_base, row_total], ignore_index=True)
                            df_show = df_final.copy()
                            df_show['Ciclos Evaluados'] = df_show['Ciclos Evaluados'].map("{:,.0f}".format)
                            df_show['Total Plantas'] = df_show['Total Plantas'].map("{:,.0f}".format)
                            df_show['Total Tallos'] = df_show['Total Tallos'].map("{:,.0f}".format)
                            df_show['Aprovechamiento'] = (df_show['Aprovechamiento'] * 100).map("{:.1f}%".format)
                            df_show['Día Inicio (Promedio)'] = df_show['Día Inicio (Promedio)'].map("{:.0f}".format)
                            df_show['Día Pico (Promedio)'] = df_show['Día Pico (Promedio)'].map("{:.0f}".format)
                            st.dataframe(df_show, use_container_width=True)
                            
                            st.markdown("#### Comportamiento Fenológico por Días de Vida")
                            df_plot = pd.DataFrame(records_plot).sort_values(['Serie', 'Día de Vida'])
                            
                            fig = px.line(
                                df_plot,
                                x='Día de Vida',
                                y='% de Producción',
                                color='Serie',
                                markers=True,
                                title=f"Curvas de Cosecha por Días de Vida ({start_date} a {end_date})",
                                labels={'% de Producción': '% de Producción', 'Día de Vida': 'Días de Vida (desde siembra)'},
                                hover_data={'Corte': True, 'Día de Vida': True, '% de Producción': ':.1f%'}
                            )
                            fig.update_layout(
                                xaxis=dict(title="Días de Vida (Días desde siembra)", tickmode='linear', dtick=2),
                                yaxis=dict(title="% de Producción Semanal/Corte", ticksuffix="%"),
                                hovermode="x unified"
                            )
                            st.plotly_chart(fig, use_container_width=True)
                    else:
                        # Modo Por Variedad
                        flores_disponibles = sorted([f for f in df_filtered['Flor'].unique() if f and f != 'Desconocida'])
                        col_var1, col_var2 = st.columns([1, 2])
                        with col_var1:
                            flor_sel = st.selectbox("Filtrar por Flor:", ["Todas"] + flores_disponibles)
                            
                        df_var_filter = df_filtered if flor_sel == "Todas" else df_filtered[df_filtered['Flor'] == flor_sel]
                        
                        top_vars_vol = df_var_filter.groupby('Variedad')['NumeroPlantas'].sum().sort_values(ascending=False).index.tolist()
                        
                        with col_var2:
                            vars_selected = st.multiselect(
                                "Variedades a comparar:",
                                options=top_vars_vol,
                                default=top_vars_vol[:5] if len(top_vars_vol) >= 5 else top_vars_vol,
                                help="Selecciona las variedades que deseas comparar en la gráfica de días de vida."
                            )
                            
                        if not vars_selected:
                            st.warning("Selecciona al menos una variedad para graficar.")
                        else:
                            resultados_var = []
                            records_plot_var = []
                            
                            for var_name in vars_selected:
                                group = df_var_filter[df_var_filter['Variedad'] == var_name]
                                plantas = group['NumeroPlantas'].sum()
                                sum_cortes = group[cortes_cols].sum()
                                tallos = sum_cortes.sum()
                                aprov = tallos / plantas if plantas > 0 else 0.0
                                
                                dias_ini_series = group['DiasInicio'].dropna()
                                dia_inicio = int(round(dias_ini_series.mean())) if not dias_ini_series.empty else 70
                                
                                corte_max_idx = int(sum_cortes.values.argmax()) if tallos > 0 else 0
                                dia_pico = dia_inicio + corte_max_idx
                                
                                flor_v = group['Flor'].iloc[0] if not group.empty else ''
                                
                                resultados_var.append({
                                    'Variedad': var_name,
                                    'Flor': flor_v,
                                    'Ciclos Evaluados': len(group),
                                    'Total Plantas': plantas,
                                    'Total Tallos': tallos,
                                    'Aprovechamiento': aprov,
                                    'Día Inicio (Promedio)': dia_inicio,
                                    'Día Pico (Promedio)': dia_pico
                                })
                                
                                for i in range(1, 16):
                                    dia_vida = dia_inicio + (i - 1)
                                    pct = (sum_cortes[f'Corte {i}'] / tallos * 100) if tallos > 0 else 0.0
                                    records_plot_var.append({
                                        'Serie': var_name,
                                        'Día de Vida': dia_vida,
                                        '% de Producción': pct,
                                        'Corte': f"Corte {i}"
                                    })
                                    
                            if resultados_var:
                                df_res_var = pd.DataFrame(resultados_var)
                                st.markdown("#### Resumen de Variedades Seleccionadas")
                                
                                # Totales y Promedios Ponderados para las variedades seleccionadas
                                tot_ciclos_v = int(df_res_var['Ciclos Evaluados'].sum())
                                tot_plantas_v = float(df_res_var['Total Plantas'].sum())
                                tot_tallos_v = float(df_res_var['Total Tallos'].sum())
                                aprov_ponderado_v = (tot_tallos_v / tot_plantas_v) if tot_plantas_v > 0 else 0.0
                                prom_dia_inicio_v = int(round((df_res_var['Día Inicio (Promedio)'] * df_res_var['Total Tallos']).sum() / tot_tallos_v)) if tot_tallos_v > 0 else 0
                                prom_dia_pico_v = int(round((df_res_var['Día Pico (Promedio)'] * df_res_var['Total Tallos']).sum() / tot_tallos_v)) if tot_tallos_v > 0 else 0
                                
                                m1, m2, m3, m4, m5 = st.columns(5)
                                m1.metric("Ciclos Totales", f"{tot_ciclos_v:,}")
                                m2.metric("Plantas Totales", f"{tot_plantas_v:,.0f}")
                                m3.metric("Tallos Totales", f"{tot_tallos_v:,.0f}")
                                m4.metric("Aprovechamiento Global", f"{aprov_ponderado_v*100:.1f}%")
                                m5.metric("Ciclo Promedio", f"{prom_dia_inicio_v} d (Inicio) / {prom_dia_pico_v} d (Pico)")
                                
                                df_base_v = df_res_var[['Variedad', 'Flor', 'Ciclos Evaluados', 'Total Plantas', 'Total Tallos', 'Aprovechamiento', 'Día Inicio (Promedio)', 'Día Pico (Promedio)']].copy()
                                
                                row_total_v = pd.DataFrame([{
                                    'Variedad': 'TOTAL / PROMEDIO',
                                    'Flor': '-',
                                    'Ciclos Evaluados': tot_ciclos_v,
                                    'Total Plantas': tot_plantas_v,
                                    'Total Tallos': tot_tallos_v,
                                    'Aprovechamiento': aprov_ponderado_v,
                                    'Día Inicio (Promedio)': prom_dia_inicio_v,
                                    'Día Pico (Promedio)': prom_dia_pico_v
                                }])
                                
                                df_final_v = pd.concat([df_base_v, row_total_v], ignore_index=True)
                                df_show_v = df_final_v.copy()
                                df_show_v['Ciclos Evaluados'] = df_show_v['Ciclos Evaluados'].map("{:,.0f}".format)
                                df_show_v['Total Plantas'] = df_show_v['Total Plantas'].map("{:,.0f}".format)
                                df_show_v['Total Tallos'] = df_show_v['Total Tallos'].map("{:,.0f}".format)
                                df_show_v['Aprovechamiento'] = (df_show_v['Aprovechamiento'] * 100).map("{:.1f}%".format)
                                df_show_v['Día Inicio (Promedio)'] = df_show_v['Día Inicio (Promedio)'].map("{:.0f}".format)
                                df_show_v['Día Pico (Promedio)'] = df_show_v['Día Pico (Promedio)'].map("{:.0f}".format)
                                st.dataframe(df_show_v, use_container_width=True)
                                
                                st.markdown("#### Comportamiento Fenológico por Días de Vida")
                                df_plot_v = pd.DataFrame(records_plot_var).sort_values(['Serie', 'Día de Vida'])
                                
                                fig = px.line(
                                    df_plot_v,
                                    x='Día de Vida',
                                    y='% de Producción',
                                    color='Serie',
                                    markers=True,
                                    title=f"Curvas de Variedades por Días de Vida ({start_date} a {end_date})",
                                    labels={'% de Producción': '% de Producción', 'Día de Vida': 'Días de Vida (desde siembra)'},
                                    hover_data={'Corte': True, 'Día de Vida': True, '% de Producción': ':.1f%'}
                                )
                                fig.update_layout(
                                    xaxis=dict(title="Días de Vida (Días desde siembra)", tickmode='linear', dtick=2),
                                    yaxis=dict(title="% de Producción Semanal/Corte", ticksuffix="%"),
                                    hovermode="x unified"
                                )
                                st.plotly_chart(fig, use_container_width=True)
                        
    with tab2:
        st.subheader("Ingreso de Datos y Motor de Suavización")
        st.markdown("""
        Sube el **Reporte de Camas Piloto** (Cosecha real y Mermas) para recalcular estadísticamente el comportamiento de cada variedad.
        La plataforma utiliza este insumo crudo para aplicar la **Estadística Determinística** y proyectar a futuro.
        """)
        
        archivo = st.file_uploader("📥 Subir Reporte Camas Piloto (Excel)", type=["xlsx", "xls"])
        
        if archivo is not None:
            col1, col2 = st.columns(2)
            with col1:
                num_ciclos = st.slider("Cantidad de Ciclos a evaluar (# Periodos)", min_value=1, max_value=50, value=9,
                                       help="Tomará los últimos N lotes/ciclos sembrados de la variedad para calcular el nuevo comportamiento.")
            with col2:
                alpha = st.slider("Porcentaje de Ponderación (Peso de los N ciclos)", min_value=0.0, max_value=1.0, value=1.00, step=0.05, 
                                  help="1.0 significa que los N ciclos recientes tendrán un 100% de peso (estadística pura de corto plazo).")

            if st.button("Cargar y Procesar Archivo"):
                with st.spinner("Procesando e integrando con el histórico completo..."):
                    try:
                        df_ciclos = pd.read_excel(archivo.getvalue(), sheet_name='CapturaCiclos2')
                        
                        df_nuevo = df_ciclos.dropna(subset=['Variedad']).copy()
                        for f in ['FechaSiembra', 'FechaDesbotone', 'FechaInicioProduccion']:
                            if f in df_nuevo.columns:
                                df_nuevo[f] = pd.to_datetime(df_nuevo[f], errors='coerce').dt.normalize()
                                
                        # Actualizar archivo log histórico
                        lotes_nuevos = 0
                        variedades_a_analizar = []
                        
                        if os.path.exists('Historico_Curvas.csv'):
                            df_hist_local = pd.read_csv('Historico_Curvas.csv')
                            if not df_hist_local.empty:
                                for f in ['FechaSiembra', 'FechaDesbotone', 'FechaInicioProduccion']:
                                    if f in df_hist_local.columns:
                                        df_hist_local[f] = pd.to_datetime(df_hist_local[f], errors='coerce').dt.normalize()
                                
                                # Identificar lotes realmente nuevos
                                merge_cols = ['Variedad', 'FechaSiembra', 'NumeroPlantas']
                                if all(c in df_nuevo.columns and c in df_hist_local.columns for c in merge_cols):
                                    df_merged = pd.merge(df_nuevo, df_hist_local[merge_cols], on=merge_cols, how='left', indicator=True)
                                    df_truly_new = df_nuevo[df_merged['_merge'] == 'left_only'].copy()
                                else:
                                    df_truly_new = df_nuevo
                                    
                                lotes_nuevos = len(df_truly_new)
                                
                                if lotes_nuevos > 0:
                                    df_consolidado = pd.concat([df_hist_local, df_truly_new], ignore_index=True)
                                    df_consolidado.to_csv('Historico_Curvas.csv', index=False)
                                    variedades_a_analizar = df_truly_new['Variedad'].unique()
                                else:
                                    df_consolidado = df_hist_local
                        else:
                            df_nuevo.to_csv('Historico_Curvas.csv', index=False)
                            df_consolidado = df_nuevo
                            lotes_nuevos = len(df_nuevo)
                            variedades_a_analizar = df_nuevo['Variedad'].unique()
                            
                        st.session_state['df_hist_full'] = df_consolidado
                        st.session_state['variedades_a_analizar'] = variedades_a_analizar
                        st.session_state['lotes_nuevos'] = lotes_nuevos
                            
                    except Exception as e:
                        import traceback
                        st.error(f"Error al procesar el archivo: {e}")
                        st.text(traceback.format_exc())

            if 'df_hist_full' in st.session_state:
                lotes_nuevos = st.session_state.get('lotes_nuevos', 0)
                if lotes_nuevos == 0:
                    st.warning("⚠️ El archivo subido no contiene ciclos/lotes nuevos. Todos los registros ya existían en el histórico.")
                else:
                    st.info(f"✅ Se encontraron y cargaron {lotes_nuevos} lotes nuevos al histórico.")
                    
                df_full = st.session_state['df_hist_full']
                
                cortes_cols = [f'Corte {i}' for i in range(1, 16)]
                for c in cortes_cols:
                    if c not in df_full.columns:
                        df_full[c] = 0.0
                        
                for f in ['FechaSiembra', 'FechaDesbotone', 'FechaInicioProduccion']:
                    if f in df_full.columns:
                        df_full[f] = pd.to_datetime(df_full[f], errors='coerce')
                        
                variedades_nombres = st.session_state.get('variedades_a_analizar', [])
                if 'df_nuevo' in locals():
                    variedades_nombres = df_nuevo['Variedad'].unique()
                
                if len(variedades_nombres) > 0:
                    resultados = []
                    for var in variedades_nombres:
                        df_var_all = df_full[df_full['Variedad'] == var].copy()
                        if len(df_var_all) == 0:
                            continue
                            
                        if 'FechaSiembra' in df_var_all.columns:
                            df_var_all = df_var_all.sort_values('FechaSiembra')
                            
                        total_plantas_hist = df_var_all['NumeroPlantas'].sum() if 'NumeroPlantas' in df_var_all.columns else 0
                        sum_cortes_hist = df_var_all[cortes_cols].sum()
                        total_tallos_hist = sum_cortes_hist.sum()
                        aprov_hist = total_tallos_hist / total_plantas_hist if total_plantas_hist > 0 else 0.0
                        
                        curva_hist = {}
                        for i in range(1, 16):
                            c_val = sum_cortes_hist[f'Corte {i}']
                            curva_hist[f'c{i}'] = c_val / total_tallos_hist if total_tallos_hist > 0 else 0.0
                            
                        dias_desb_list_hist = (df_var_all['FechaDesbotone'] - df_var_all['FechaSiembra']).dt.days.dropna()
                        dias_inicio_list_hist = (df_var_all['FechaInicioProduccion'] - df_var_all['FechaSiembra']).dt.days.dropna()
                        dia_inicio_hist = int(dias_inicio_list_hist.mean()) if not dias_inicio_list_hist.empty else 0
                        dias_desb_hist = int(dias_desb_list_hist.mean()) if not dias_desb_list_hist.empty else 0
                        
                        corte_max_hist = sum_cortes_hist.idxmax() if total_tallos_hist > 0 else "Corte 1"
                        try:
                            semana_pico_hist = int(corte_max_hist.replace("Corte ", ""))
                        except:
                            semana_pico_hist = 1
                        dia_pico_hist = (semana_pico_hist - 1) * 7 + 3
                        
                        df_var_n_ciclos = df_var_all.tail(num_ciclos)
                        total_plantas_nuevo = df_var_n_ciclos['NumeroPlantas'].sum() if 'NumeroPlantas' in df_var_n_ciclos.columns else 0
                        if total_plantas_nuevo == 0:
                            continue
                            
                        sum_cortes_nuevo = df_var_n_ciclos[cortes_cols].sum()
                        total_tallos_nuevo = sum_cortes_nuevo.sum()
                        aprov_nuevo = total_tallos_nuevo / total_plantas_nuevo if total_plantas_nuevo > 0 else 0.0
                        
                        curva_nueva = {}
                        for i in range(1, 16):
                            c_val = sum_cortes_nuevo[f'Corte {i}']
                            curva_nueva[f'c{i}'] = c_val / total_tallos_nuevo if total_tallos_nuevo > 0 else 0.0
                            
                        dias_desb_list = (df_var_n_ciclos['FechaDesbotone'] - df_var_n_ciclos['FechaSiembra']).dt.days.dropna()
                        dias_inicio_list = (df_var_n_ciclos['FechaInicioProduccion'] - df_var_n_ciclos['FechaSiembra']).dt.days.dropna()
                        dias_desb_nuevo = int(dias_desb_list.mean()) if not dias_desb_list.empty else 0
                        dias_inicio_nuevo = int(dias_inicio_list.mean()) if not dias_inicio_list.empty else 0
                        
                        corte_max = sum_cortes_nuevo.idxmax() if total_tallos_nuevo > 0 else "Corte 1"
                        try:
                            semana_pico = int(corte_max.replace("Corte ", ""))
                        except:
                            semana_pico = 1
                        dia_pico_nuevo = (semana_pico - 1) * 7 + 3
                        
                        aprov_suavizado = (aprov_nuevo * alpha) + (aprov_hist * (1 - alpha))
                        dia_inicio_suav = int((dias_inicio_nuevo * alpha) + (dia_inicio_hist * (1 - alpha)))
                        dias_desb_suav = int((dias_desb_nuevo * alpha) + (dias_desb_hist * (1 - alpha)))
                        dia_pico_suav = int((dia_pico_nuevo * alpha) + (dia_pico_hist * (1 - alpha)))
                        
                        curva_suavizada = {}
                        for i in range(1, 16):
                            curva_suavizada[f'c{i}'] = (curva_nueva[f'c{i}'] * alpha) + (curva_hist[f'c{i}'] * (1 - alpha))
                            
                        suma_curva = sum(curva_suavizada.values())
                        if suma_curva > 0:
                            curva_suavizada = {k: v / suma_curva for k, v in curva_suavizada.items()}
                        
                        res = {
                            'Variedad': var,
                            'Lotes en Cálculo': len(df_var_n_ciclos),
                            'APROV Crudo (Total)': f"{aprov_hist*100:.1f}%",
                            'APROV N Ciclos': f"{aprov_nuevo*100:.1f}%",
                            'APROV Suavizado': f"{aprov_suavizado*100:.1f}%",
                            'Nuevo D. Inicio': dia_inicio_suav,
                            'Nuevo D. Desb': dias_desb_suav,
                            'Nuevo D. Pico': dia_pico_suav
                        }
                        for i in range(1, 16):
                            res[f'C{i}'] = f"{curva_suavizada[f'c{i}']*100:.1f}%"
                            
                        resultados.append(res)
                    
                    if resultados:
                        df_res = pd.DataFrame(resultados)
                        st.subheader("📊 Previsualización Dinámica de Cambios")
                        cols_to_show = ['Variedad', 'Lotes en Cálculo', 'APROV Crudo (Total)', 'APROV N Ciclos', 'APROV Suavizado', 'Nuevo D. Inicio', 'Nuevo D. Desb', 'Nuevo D. Pico'] + [f'C{i}' for i in range(1, 16)]
                        st.dataframe(df_res[cols_to_show], use_container_width=True)
                        st.info("💡 **Nota:** Las curvas suavizadas **no** se guardan estáticamente en la base de datos. La plataforma las calcula en tiempo real a partir del CSV y parámetros de Forecast. Esta tabla es un simulador interactivo.")
                        
                        if st.button("Limpiar Simulador", type="secondary"):
                            st.session_state.pop('df_hist_full', None)
                            st.rerun()
