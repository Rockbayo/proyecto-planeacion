import streamlit as st
import pandas as pd
import os
from datetime import date, timedelta
import io

def get_iso_week_string(dt: date) -> str:
    y, w, _ = dt.isocalendar()
    return f"S{y}{w:02d}"

def render_pedido_module(db):
    st.header("🌱 Pedido de Material Vegetal")
    st.markdown("""
    Este módulo calcula el pedido de esquejes a los proveedores basado en el **Plan Aprobado**.
    Se aplica un **5% adicional** sobre la capacidad aprobada para asegurar el cumplimiento, 
    y se redondea en camas físicas de **5200 esquejes**. 
    El pedido se programa para recibirse **4 semanas antes de la siembra**.
    """)

    plan_file_path = "Plan_Aprobado.csv"


    if not os.path.exists(plan_file_path):
        st.warning("No se encontró ningún Plan Aprobado. Ve a 'Plan de Producción' y guarda una contrapropuesta.")
        return

    df_plan = pd.read_csv(plan_file_path)
    
    # Manejar nombres de columnas por compatibilidad
    col_flor = 'Flor' if 'Flor' in df_plan.columns else 'Flower'
    col_capacidad = 'Tallos a Producir (Capacidad)' if 'Tallos a Producir (Capacidad)' in df_plan.columns else 'Suma de Tallos'
    
    if 'Variedad' not in df_plan.columns:
        st.error("❌ El Plan Aprobado actual no tiene el detalle por Variedad. Por favor, ve al módulo 'Plan de Producción', vuelve a Procesar tu archivo y dale click en 'Guardar Contrapropuesta' para que se actualice con el formato correcto.")
        return

    col1, col2 = st.columns(2)
    with col1:
        # Default start week: +24 semanas
        hoy = date.today()
        fecha_default = hoy + timedelta(weeks=24)
        default_sem = get_iso_week_string(fecha_default)
        sem_inicio = st.text_input("Semana Inicio de Pedido (Ej: S202640)", value=default_sem)
    
    with col2:
        st.info("💡 El horizonte abarcará desde la semana de inicio hacia adelante (todas las disponibles en el plan).")

    if st.button("Generar Pedido de Esquejes", type="primary"):
        with st.spinner("Calculando fechas, curvas y consolidando pedido..."):
            try:
                from app.services.forecast_service import calcular_curvas_dinamicas
                dyn_curves = calcular_curvas_dinamicas(alpha=1.0, num_ciclos=9)
                var_dict = {k.strip().lower(): v for k, v in dyn_curves.items()}
                
                records_pedido = []
                
                for _, row in df_plan.iterrows():
                    flor = str(row[col_flor]).strip()
                    color = str(row['Color']).strip()
                    variedad = str(row['Variedad']).strip()
                    sem_cosecha_raw = str(row['Semana']).strip()
                    capacidad = pd.to_numeric(row[col_capacidad], errors='coerce')
                    
                    if pd.isna(capacidad) or capacidad <= 0:
                        continue
                        
                    # 1. Aplicar margen de 5% adicional
                    meta_tallos = capacidad * 1.05
                    
                    # 2. Obtener curva biológica
                    var_norm = variedad.lower()
                    var_db = var_dict.get(var_norm)
                    
                    suma_curva = 1.0
                    dia_pico = 70
                    if var_db:
                        sc = sum(var_db.get(f'c{i}', 0) for i in range(1, 16))
                        if sc > 0:
                            suma_curva = sc
                        if 'dia_pico' in var_db and var_db['dia_pico'] > 0:
                            dia_pico = var_db['dia_pico']
                            
                    # 3. Plantas Teóricas
                    plantas_teoricas = meta_tallos / suma_curva
                    
                    # 4. Camas físicas de 5200 (Redondeo inteligente)
                    camas = round(plantas_teoricas / 5200.0)
                    if camas == 0 and plantas_teoricas > 0:
                        camas = 1
                        
                    esquejes_pedir = camas * 5200
                    
                    if esquejes_pedir == 0:
                        continue
                        
                    # 5. Cálculo de Fechas
                    try:
                        # Extraer año y semana (ej: "202640" o "202640.0")
                        sem_clean = sem_cosecha_raw.replace(".0", "")
                        year = int(sem_clean[:4])
                        week = int(sem_clean[4:])
                        fecha_pico = date.fromisocalendar(year, week, 4)
                    except:
                        continue
                        
                    fecha_siembra = fecha_pico - timedelta(days=dia_pico)
                    # El pedido se recibe 4 semanas antes de la siembra
                    fecha_pedido = fecha_siembra - timedelta(weeks=4)
                    sem_pedido = get_iso_week_string(fecha_pedido)
                    
                    records_pedido.append({
                        "Flor": flor,
                        "Color": color,
                        "Variedad": variedad,
                        "Semana_Pedido": sem_pedido,
                        "Esquejes": esquejes_pedir
                    })
                    
                df_pedido = pd.DataFrame(records_pedido)
                
                if df_pedido.empty:
                    st.warning("No se generaron pedidos. Revisa que el plan aprobado tenga cantidades.")
                    return
                    
                # 6. Crear la tabla dinámica (Pivot Table)
                df_pivot = df_pedido.groupby(['Flor', 'Color', 'Variedad', 'Semana_Pedido'])['Esquejes'].sum().reset_index()
                df_pivot = df_pivot.pivot(index=['Flor', 'Color', 'Variedad'], columns='Semana_Pedido', values='Esquejes').fillna(0)
                
                # Obtener la lista de semanas proyectadas (Horizonte)
                sem_inicio_formatted = sem_inicio if sem_inicio.startswith("S") else f"S{sem_inicio}"
                semanas_presentes = [c for c in df_pivot.columns if str(c).startswith('S')]
                
                if not semanas_presentes:
                    st.warning("No se generaron pedidos válidos.")
                    return
                
                max_sem = max(semanas_presentes)
                sem_inicio_clean = sem_inicio_formatted.replace("S", "").replace("s", "")
                year_start = int(sem_inicio_clean[:4])
                week_start = int(sem_inicio_clean[4:])
                fecha_start = date.fromisocalendar(year_start, week_start, 4)
                
                semanas_horizonte = []
                curr_fecha = fecha_start
                while True:
                    curr_sem_str = get_iso_week_string(curr_fecha)
                    semanas_horizonte.append(curr_sem_str)
                    if curr_sem_str >= max_sem:
                        break
                    curr_fecha += timedelta(weeks=1)
                
                # Asegurar que todas las semanas del horizonte existan en la tabla (con 0 si no hay pedidos)
                for s in semanas_horizonte:
                    if s not in df_pivot.columns:
                        df_pivot[s] = 0
                        
                # Filtrar y ordenar las columnas para que solo queden las del horizonte
                df_pivot = df_pivot[semanas_horizonte]
                
                # Resetear index para visualización plana
                df_pivot = df_pivot.reset_index()
                df_pivot.columns.name = None
                
                st.session_state['df_pedido_consolidado'] = df_pivot
                st.success("¡Pedido Consolidado generado con éxito!")
                
            except Exception as e:
                import traceback
                st.error(f"Error procesando el pedido: {e}")
                st.text(traceback.format_exc())
                
    if 'df_pedido_consolidado' in st.session_state:
        df_result = st.session_state['df_pedido_consolidado']
        st.dataframe(df_result, use_container_width=True)
        
        # Generar Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_result.to_excel(writer, index=False, sheet_name='PedidoConsolidado')
        output.seek(0)
        
        st.download_button(
            label="📥 Descargar Archivo para Plataforma (Pedido Consolidado)",
            data=output.getvalue(),
            file_name=f"PedidoConsolidado_{date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )

