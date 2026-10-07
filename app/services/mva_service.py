import pandas as pd
from datetime import datetime, date, timedelta

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


def proyectar_cosecha_desde_mva(df_mrp, db):
    """
    Toma el DataFrame resultante de generar_plan_mva (que contiene Semana_Siembra y Plantas finales)
    y proyecta la cosecha a futuro (52 semanas) usando las curvas de las variedades.
    """
    from app.models.models import Variedad
    from app.services.forecast_service import isocalendar_to_string
    
    records = []
    
    # Cargar todas las variedades en un diccionario para rapido acceso
    variedades_db = db.query(Variedad).all()
    var_dict = {v.nombre.strip().lower(): v for v in variedades_db}
    
    for idx, row in df_mrp.iterrows():
        var_nombre_orig = row['Variedad']
        var_norm = str(var_nombre_orig).strip().lower()
        
        if var_norm not in var_dict:
            continue
            
        var = var_dict[var_norm]
        sem_siembra = str(row['Semana_Siembra'])
        plantas = row['Esquejes_Para_Siembra (Final)']
        
        if plantas <= 0:
            continue
            
        # Determinar la fecha de siembra óptima en esa semana
        # Buscamos el día de siembra (Lunes a Domingo) para que el 'Día Pico' caiga un Jueves (mitad de semana),
        # logrando así que la curva de cosecha concentre su mayor volumen en una sola semana ISO.
        year = int(sem_siembra[:4])
        week = int(sem_siembra[4:])
        
        fecha_siembra = date.fromisocalendar(year, week, 1) # Default a lunes
        for d in range(1, 8):
            test_fecha = date.fromisocalendar(year, week, d)
            fecha_pico = test_fecha + timedelta(days=var.dia_pico)
            if fecha_pico.isoweekday() == 4: # 4 = Jueves
                fecha_siembra = test_fecha
                break
        
        fecha_inicio_cosecha = fecha_siembra + timedelta(days=var.dia_inicio)
        
        curvas = [var.c1, var.c2, var.c3, var.c4, var.c5, 
                  var.c6, var.c7, var.c8, var.c9, var.c10, 
                  var.c11, var.c12, var.c13, var.c14, var.c15]
                  
        for dia_indice, porcentaje_cosecha in enumerate(curvas):
            if porcentaje_cosecha and porcentaje_cosecha > 0:
                fecha_corte_dia = fecha_inicio_cosecha + timedelta(days=dia_indice)
                semana_operativa = isocalendar_to_string(fecha_corte_dia)
                tallos_esperados = plantas * porcentaje_cosecha
                
                if tallos_esperados > 0:
                    records.append({
                        "Flor": var.flor,
                        "Color": var.color,
                        "Variedad": var.nombre,
                        "Semana_Siembra": sem_siembra,
                        "Semana_Cosecha": semana_operativa,
                        "Tallos_Proyectados": int(tallos_esperados)
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
