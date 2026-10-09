import pandas as pd
from datetime import date, timedelta

def iso_add_weeks(iso_str: str, weeks: int) -> str:
    """
    Suma o resta semanas a un string ISO como '202639' (o 'S202639').
    Retorna el string en formato '202639'.
    """
    if str(iso_str).startswith('S'):
        iso_str = iso_str[1:]
    
    year = int(iso_str[:4])
    week = int(iso_str[4:])
    
    # Aproximación usando datetime
    # El jueves de la semana iso cae en el mismo año que la semana iso
    # A partir del año y la semana, encontramos una fecha.
    # ISO calendar: strptime %G %V no siempre es estándar en todas partes.
    # Usamos date.fromisocalendar (Python 3.8+)
    dt = date.fromisocalendar(year, week, 1)
    
    dt_new = dt + timedelta(weeks=weeks)
    new_year, new_week, _ = dt_new.isocalendar()
    return f"{new_year}{new_week:02d}"

def generar_plan_mva(filepath, week_is="Pedido"):
    """
    Lee el PedidoConsolidado y explota los materiales calculando las semanas
    de Siembra.
    
    week_is: Define qué representa la semana de la columna en el archivo.
             Por defecto asumimos que representa la Semana de Pedido.
    """
    df = pd.read_excel(filepath)
    
    # Identificamos las columnas de semanas
    cols_semanas = [c for c in df.columns if str(c).startswith('S202') or str(c).startswith('202')]
    
    # Melt para pasar las semanas a filas
    id_vars = ['Flor', 'Color', 'Variedad']
    # Filtrar solo si existen en el df
    id_vars = [c for c in id_vars if c in df.columns]
    
    df_melt = pd.melt(df, id_vars=id_vars, value_vars=cols_semanas, 
                      var_name='Semana_Archivo', value_name='Cantidad_Archivo')
    
    # Filtrar ceros o nulos
    df_melt = df_melt[df_melt['Cantidad_Archivo'] > 0].copy()
    
    records = []
    
    for idx, row in df_melt.iterrows():
        sem_str = str(row['Semana_Archivo']).replace('S', '')
        cantidad = row['Cantidad_Archivo']
        
        # Plantas finales a sembrar (el pedido ya tiene aplicado el MVA, por lo que es la misma cantidad)
        plantas_siembra = int(cantidad)
        
        if week_is == "Pedido":
            sem_pedido = sem_str
            sem_siembra = iso_add_weeks(sem_pedido, 4)
        else:
            sem_siembra = sem_str
            sem_pedido = iso_add_weeks(sem_siembra, -4)
            
        record = {
            "Flor": row.get("Flor", ""),
            "Variedad": row.get("Variedad", ""),
            "Semana_Pedido_MV": sem_pedido,
            "Semana_Siembra": sem_siembra,
            "Esquejes_Pedido_MV": cantidad,
            "Esquejes_Para_Siembra (Final)": plantas_siembra
        }
        records.append(record)
        
    df_resultado = pd.DataFrame(records)
    
    # Ordenar por Semana de Pedido y Variedad
    if not df_resultado.empty:
        df_resultado = df_resultado.sort_values(['Semana_Pedido_MV', 'Variedad'])
        
    return df_resultado


def proyectar_cosecha_desde_mva(df_mrp, db, var_dict=None):
    """
    Toma el DataFrame resultante de generar_plan_mva (que contiene Semana_Siembra y Plantas finales)
    y proyecta la cosecha a futuro (52 semanas) usando las curvas de las variedades.
    """
    from app.models.models import Variedad
    from app.services.forecast_service import isocalendar_to_string, calcular_curvas_dinamicas
    
    records = []
    
    # Calcular curvas dinámicamente con los parámetros óptimos (1.0 y 9)
    curvas_dinamicas = calcular_curvas_dinamicas(alpha=1.0, num_ciclos=9)
    
    if var_dict is None:
        # Cargar todas las variedades en un diccionario para rapido acceso
        variedades_db = db.query(Variedad).all()
        var_dict = {v.nombre.strip().lower(): v for v in variedades_db}
    
    for idx, row in df_mrp.iterrows():
        var_nombre_orig = row['Variedad']
        var_norm = str(var_nombre_orig).strip().lower()
        
        # Obtener valores dinámicos si existen, fallback a DB
        if var_nombre_orig in curvas_dinamicas:
            v_dyn = curvas_dinamicas[var_nombre_orig]
            dia_pico = v_dyn['dia_pico']
            dia_inicio = v_dyn['dia_inicio']
            curvas = [v_dyn[f'c{i}'] for i in range(1, 16)]
        elif var_norm in var_dict:
            var = var_dict[var_norm]
            dia_pico = var.dia_pico if var.dia_pico else 70
            dia_inicio = var.dia_inicio if var.dia_inicio else 68
            curvas = [var.c1, var.c2, var.c3, var.c4, var.c5, 
                      var.c6, var.c7, var.c8, var.c9, var.c10, 
                      var.c11, var.c12, var.c13, var.c14, var.c15]
        else:
            # Crear variedad genérica (mock) para no perder los tallos
            dia_pico = 70
            dia_inicio = 68
            curvas = [1.0] + [0.0] * 14
            
        sem_siembra = str(row['Semana_Siembra'])
        plantas = row['Esquejes_Para_Siembra (Final)']
        
        if plantas <= 0:
            continue
            
        # Determinar la fecha de siembra óptima en esa semana
        year = int(sem_siembra[:4])
        week = int(sem_siembra[4:])
        
        fecha_siembra = date.fromisocalendar(year, week, 1) # Default a lunes
        for d in range(1, 8):
            test_fecha = date.fromisocalendar(year, week, d)
            fecha_pico_test = test_fecha + timedelta(days=dia_pico)
            if fecha_pico_test.isoweekday() == 4: # 4 = Jueves
                fecha_siembra = test_fecha
                break
        
        fecha_inicio_cosecha = fecha_siembra + timedelta(days=dia_inicio)
        
        for dia_indice, porcentaje_cosecha in enumerate(curvas):
            if porcentaje_cosecha and porcentaje_cosecha > 0:
                fecha_corte_dia = fecha_inicio_cosecha + timedelta(days=dia_indice)
                semana_operativa = isocalendar_to_string(fecha_corte_dia)
                tallos_esperados = plantas * porcentaje_cosecha
                
                if tallos_esperados > 0:
                    records.append({
                        "Flor": row.get('Flor', 'Genérico'),
                        "Color": row.get('Color', 'Genérico'),
                        "Variedad": var_nombre_orig,
                        "Semana_Siembra": sem_siembra,
                        "Semana_Cosecha": semana_operativa,
                        "Tallos_Proyectados": tallos_esperados
                    })
                    
    if not records:
        return pd.DataFrame()
        
    df = pd.DataFrame(records)
    
    df_pivot = pd.pivot_table(
        df, 
        values='Tallos_Proyectados', 
        index=['Flor', 'Color', 'Variedad'], 
        columns=['Semana_Cosecha'], 
        aggfunc='sum',
        fill_value=0
    ).reset_index()
    
    # Ordenar columnas numericas
    cols_semanas = sorted([c for c in df_pivot.columns if str(c).startswith('202')])
    meta_cols = [c for c in ['Flor', 'Color', 'Variedad'] if c in df_pivot.columns]
    
    return df_pivot[meta_cols + cols_semanas]

def combinar_proyecciones_52_semanas(df_forecast, df_proyeccion):
    """
    Combina el forecast de corto plazo (inventario vivo) con el forecast de largo plazo (MVA)
    para crear una proyección consolidada de 52 semanas.
    - Primeras 10 semanas: Vienen de df_forecast (Inventario Vivo).
    - Siguientes semanas (hasta la 52): Vienen de df_proyeccion (MVA).
    """
    from datetime import date
    from app.services.forecast_service import isocalendar_to_string
    import pandas as pd
    
    # 1. Preparar las 10 semanas de inventario vivo
    semana_actual = isocalendar_to_string(date.today())
    cols_fc = sorted([c for c in df_forecast.columns if str(c).startswith('202')])
    semanas_viv = [s for s in cols_fc if s >= semana_actual][:10]
    
    df_viv = df_forecast[['Flor', 'Color', 'Variedad'] + semanas_viv].copy()
    
    # 2. Preparar el MVA a partir de la semana 11
    cols_mva = sorted([c for c in df_proyeccion.columns if str(c).startswith('202')])
    if semanas_viv:
        ultima_semana_viv = semanas_viv[-1]
        semanas_mva = [s for s in cols_mva if s > ultima_semana_viv]
    else:
        semanas_mva = cols_mva
        
    df_mrp_futuro = df_proyeccion[['Flor', 'Color', 'Variedad'] + semanas_mva].copy()
    
    # 3. Hacer un merge exterior (outer join) por Flor, Color, Variedad
    df_consolidado = pd.merge(df_viv, df_mrp_futuro, on=['Flor', 'Color', 'Variedad'], how='outer')
    
    # Rellenar nulos con 0
    df_consolidado = df_consolidado.fillna(0)
    
    # Limitar a exactamente 52 semanas (10 de vivo + 42 de mva)
    todas_las_semanas = sorted([c for c in df_consolidado.columns if str(c).startswith('202')])
    semanas_52 = todas_las_semanas[:52]
    
    df_final = df_consolidado[['Flor', 'Color', 'Variedad'] + semanas_52]
    
    return df_final

def llenar_plantilla_52_semanas(template_bytes, df_52_semanas):
    """
    Toma una plantilla Excel de 52 semanas subida por el usuario,
    busca la columna 'Variedad' y rellena las columnas de semanas
    con los datos de df_52_semanas. Mantiene las variedades en 0 si no hay datos.
    Retorna los bytes del archivo Excel modificado.
    """
    import io
    import pandas as pd
    
    # Pre-procesar df_52_semanas para búsquedas rápidas
    df_data = df_52_semanas.groupby('Variedad').sum()
    df_data.index = df_data.index.astype(str).str.strip().str.lower()
    
    # Leer la plantilla
    df_template = pd.read_excel(io.BytesIO(template_bytes), sheet_name=0)
    
    # Identificar las columnas de semanas (ej. 202640, 202701)
    cols_semanas = [c for c in df_template.columns if str(c).startswith('202')]
    
    # Iterar y rellenar
    if 'Variedad' in df_template.columns:
        for idx, row in df_template.iterrows():
            variedad_orig = str(row['Variedad']).strip().lower()
            
            for sem in cols_semanas:
                sem_str = str(int(sem)) if isinstance(sem, float) else str(sem)
                valor = 0
                if not df_data.empty and variedad_orig in df_data.index and sem_str in df_data.columns:
                    valor = df_data.loc[variedad_orig, sem_str]
                
                df_template.at[idx, sem] = int(valor)
    
    # Guardar en memoria
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_template.to_excel(writer, index=False, sheet_name='Proyeccion_52W')
    output.seek(0)
    
    return output.getvalue()
