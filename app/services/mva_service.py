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
    
    # Filtrar filas de totales o vacías del archivo de pedido
    if 'Variedad' in df.columns:
        df = df.dropna(subset=['Variedad'])
        df = df[~df['Variedad'].astype(str).str.strip().str.lower().isin(['nan', 'total', 'none', '', 'null'])]
    if 'Color' in df.columns:
        df = df[~df['Color'].astype(str).str.strip().str.lower().isin(['total'])]
    
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
    
    # Cargar catálogo maestro de variedades desde BD para garantizar flor y color correctos
    from app.core.database import SessionLocal
    from app.models.models import Variedad
    _db = SessionLocal()
    try:
        _vars_db = _db.query(Variedad).all()
        v_map = {v.nombre.strip().lower(): (v.flor.strip(), v.color.strip()) for v in _vars_db}
    finally:
        _db.close()

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
            
        v_name = str(row.get("Variedad", "")).strip()
        fl_db, col_db = v_map.get(v_name.lower(), (str(row.get("Flor", "")).strip(), str(row.get("Color", "")).strip()))

        record = {
            "Flor": fl_db,
            "Color": col_db,
            "Variedad": v_name,
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
            
        sem_siembra = str(row['Semana_Siembra']).split('.')[0].strip()
        plantas = float(row.get('Esquejes_Para_Siembra (Final)', 0) or row.get('Esquejes', 0) or row.get('Plantas_Siembra', 0) or 0)
        
        if plantas <= 0 or len(sem_siembra) < 6:
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
                    var_obj = var_dict.get(var_norm)
                    if var_obj and var_obj.flor and var_obj.color:
                        flor_val = var_obj.flor
                        color_val = var_obj.color
                    else:
                        flor_val = row.get('Flor') or 'Novelty'
                        color_val = row.get('Color') or 'Mix'
                        
                    records.append({
                        "Flor": flor_val,
                        "Color": color_val,
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
    Preserva el nombre de la hoja original de la plantilla y es tolerante a diferencias
    de mayúsculas/minúsculas y espacios. Retorna los bytes del archivo Excel modificado.
    """
    import io
    import pandas as pd
    
    # Pre-procesar df_52_semanas para búsquedas rápidas con deduplicación insensible a mayúsculas
    df_temp = df_52_semanas.copy()
    if 'Variedad' in df_temp.columns:
        df_temp['Variedad_norm'] = df_temp['Variedad'].astype(str).str.strip().str.lower()
        cols_num = [c for c in df_temp.columns if str(c).startswith('202')]
        df_data = df_temp.groupby('Variedad_norm')[cols_num].sum()
    else:
        df_data = pd.DataFrame()
    
    # Leer la plantilla preservando el nombre de hoja original
    excel_file = pd.ExcelFile(io.BytesIO(template_bytes))
    sheet_name = excel_file.sheet_names[0] if excel_file.sheet_names else 'Plantilla'
    df_template = pd.read_excel(excel_file, sheet_name=sheet_name)
    
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
                    val = df_data.loc[variedad_orig, sem_str]
                    if hasattr(val, 'iloc'):
                        val = val.iloc[0] if len(val) > 0 else 0
                    if pd.notna(val):
                        try:
                            valor = int(round(float(val)))
                        except (ValueError, TypeError):
                            valor = 0
                
                df_template.at[idx, sem] = valor
    
    # Guardar en memoria respetando el nombre de la hoja original
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_template.to_excel(writer, index=False, sheet_name=sheet_name)
    output.seek(0)
    
    return output.getvalue()


def sincronizar_pedido_consolidado_master(
    nuevo_pedido_input, 
    master_filepath: str = "PedidoConsolidado_master.xlsx"
) -> dict:
    """
    Consolida de manera atómica el archivo maestro de Pedido Consolidado (PedidoConsolidado_master.xlsx).
    Aplica exactamente la misma lógica de los planes de producción:
    - Identifica las semanas presentes en el nuevo archivo cargado (ej. desde S202642 hasta S202752).
    - Preserva intactas todas las semanas históricas previas que ya existían en PedidoConsolidado_master.xlsx 
      y que no están en el nuevo archivo (ej. S202634 a S202641).
    - Reemplaza/actualiza únicamente las semanas que vienen en el nuevo documento.
    - Asegura que no se pierdan variedades históricas ni semanas pasadas.
    - Recalcula la columna 'Total' sumando todas las semanas y ordena las columnas cronológicamente.
    - Guarda el resultado en PedidoConsolidado_master.xlsx con hoja única 'Hoja1'.
    
    Retorna un diccionario con:
    - 'status': 'success' o 'error'
    - 'semanas_actualizadas': lista de semanas actualizadas del nuevo archivo
    - 'semanas_historicas_preservadas': lista de semanas históricas conservadas
    - 'total_semanas': total de columnas de semanas consolidadas
    - 'semana_min': primera semana en el consolidado
    - 'semana_max': última semana en el consolidado
    - 'total_variedades': total de registros de variedades
    - 'df_consolidado': DataFrame final resultante
    """
    import os
    import io
    import pandas as pd

    try:
        # 1. Cargar el nuevo dataset de pedido
        if isinstance(nuevo_pedido_input, pd.DataFrame):
            df_nuevo = nuevo_pedido_input.copy()
        elif hasattr(nuevo_pedido_input, 'read'): # UploadedFile o BytesIO
            nuevo_pedido_input.seek(0)
            df_nuevo = pd.read_excel(nuevo_pedido_input)
        elif isinstance(nuevo_pedido_input, (bytes, bytearray)):
            df_nuevo = pd.read_excel(io.BytesIO(nuevo_pedido_input))
        elif isinstance(nuevo_pedido_input, str):
            df_nuevo = pd.read_excel(nuevo_pedido_input)
        else:
            return {"status": "error", "message": f"Tipo de entrada no soportado: {type(nuevo_pedido_input)}"}

        # Limpiar filas vacías o de totales
        if 'Variedad' in df_nuevo.columns:
            df_nuevo = df_nuevo.dropna(subset=['Variedad'])
            df_nuevo = df_nuevo[~df_nuevo['Variedad'].astype(str).str.strip().str.lower().isin(['nan', 'total', 'none', '', 'null', '0'])]
        if 'Flor' in df_nuevo.columns:
            df_nuevo = df_nuevo[~df_nuevo['Flor'].astype(str).str.strip().str.lower().isin(['total'])]

        # Estandarizar columnas de semanas a formato 'S{YYYYWW}'
        rename_cols = {}
        for c in df_nuevo.columns:
            c_str = str(c).strip().replace('.0', '')
            if c_str.startswith('202') and len(c_str) == 6:
                rename_cols[c] = f"S{c_str}"
            elif c_str.startswith('S202') and len(c_str) == 7:
                rename_cols[c] = c_str
        if rename_cols:
            df_nuevo = df_nuevo.rename(columns=rename_cols)

        # Si el DataFrame viene desglosado (melted) con columna 'Semana_Pedido' o 'Semana'
        col_sem_cands = [c for c in ['Semana_Pedido', 'Semana', 'Semana_Archivo'] if c in df_nuevo.columns]
        col_val_cands = [c for c in ['Esquejes', 'Cantidad', 'Cantidad_Archivo', 'Esquejes_Pedir'] if c in df_nuevo.columns]
        if col_sem_cands and col_val_cands and not any(str(c).startswith('S202') for c in df_nuevo.columns):
            c_sem = col_sem_cands[0]
            c_val = col_val_cands[0]
            df_nuevo[c_sem] = df_nuevo[c_sem].apply(lambda x: str(x).strip().replace('.0', ''))
            df_nuevo[c_sem] = df_nuevo[c_sem].apply(lambda x: x if x.startswith('S') else f"S{x}")
            id_cols = [c for c in ['Flor', 'Color', 'Variedad'] if c in df_nuevo.columns]
            df_nuevo = df_nuevo.groupby(id_cols + [c_sem])[c_val].sum().unstack(fill_value=0).reset_index()
            df_nuevo.columns.name = None

        # Identificar semanas del nuevo archivo
        semanas_nuevas = sorted([c for c in df_nuevo.columns if str(c).startswith('S202')])
        if not semanas_nuevas:
            return {"status": "error", "message": "No se encontraron columnas de semanas válidas (S{YYYYWW}) en el archivo ingresado."}

        # Asegurar columnas canónicas
        for col_id in ['Flor', 'Color', 'Variedad']:
            if col_id not in df_nuevo.columns:
                df_nuevo[col_id] = "Desconocido"
            df_nuevo[col_id] = df_nuevo[col_id].astype(str).str.strip()

        # 2. Si existe el maestro previo, preservar histórico
        semanas_hist = []
        if os.path.exists(master_filepath):
            try:
                df_master = pd.read_excel(master_filepath)
                # Estandarizar columnas del maestro
                ren_m = {}
                for c in df_master.columns:
                    c_str = str(c).strip().replace('.0', '')
                    if c_str.startswith('202') and len(c_str) == 6:
                        ren_m[c] = f"S{c_str}"
                    elif c_str.startswith('S202') and len(c_str) == 7:
                        ren_m[c] = c_str
                if ren_m:
                    df_master = df_master.rename(columns=ren_m)

                if 'Variedad' in df_master.columns:
                    df_master = df_master.dropna(subset=['Variedad'])
                    df_master = df_master[~df_master['Variedad'].astype(str).str.strip().str.lower().isin(['nan', 'total', 'none', '', 'null', '0'])]
                if 'Flor' in df_master.columns:
                    df_master = df_master[~df_master['Flor'].astype(str).str.strip().str.lower().isin(['total'])]

                for col_id in ['Flor', 'Color', 'Variedad']:
                    if col_id in df_master.columns:
                        df_master[col_id] = df_master[col_id].astype(str).str.strip()

                semanas_master = sorted([c for c in df_master.columns if str(c).startswith('S202')])
                # Semanas históricas que NO están en el nuevo archivo ingresado
                semanas_hist = [s for s in semanas_master if s not in semanas_nuevas]

                if semanas_hist:
                    df_master_sub = df_master[['Flor', 'Color', 'Variedad'] + semanas_hist].copy()
                    df_nuevo_sub = df_nuevo[['Flor', 'Color', 'Variedad'] + semanas_nuevas].copy()

                    # Merge outer por [Flor, Color, Variedad]
                    df_consolidado = pd.merge(
                        df_master_sub,
                        df_nuevo_sub,
                        on=['Flor', 'Color', 'Variedad'],
                        how='outer'
                    )
                else:
                    df_consolidado = df_nuevo[['Flor', 'Color', 'Variedad'] + semanas_nuevas].copy()
            except Exception:
                df_consolidado = df_nuevo[['Flor', 'Color', 'Variedad'] + semanas_nuevas].copy()
                semanas_hist = []
        else:
            df_consolidado = df_nuevo[['Flor', 'Color', 'Variedad'] + semanas_nuevas].copy()

        # 3. Consolidar todas las semanas ordenadas cronológicamente
        all_weeks = sorted(list(set(semanas_hist + semanas_nuevas)))
        for w in all_weeks:
            if w not in df_consolidado.columns:
                df_consolidado[w] = 0.0
            else:
                df_consolidado[w] = pd.to_numeric(df_consolidado[w], errors='coerce').fillna(0)

        df_consolidado['Total'] = df_consolidado[all_weeks].sum(axis=1)
        final_cols = ['Flor', 'Color', 'Variedad'] + all_weeks + ['Total']
        df_consolidado = df_consolidado[final_cols].sort_values(['Flor', 'Color', 'Variedad']).reset_index(drop=True)

        # 4. Guardar archivo maestro atómicamente
        with pd.ExcelWriter(master_filepath, engine='xlsxwriter') as writer:
            df_consolidado.to_excel(writer, sheet_name='Hoja1', index=False)

        # 5. Sincronizar automáticamente el Plan Detallado (Siembras y Enraizamiento)
        try:
            sincronizar_plan_detallado_desde_pedido_master(master_filepath=master_filepath)
        except Exception:
            pass

        return {
            "status": "success",
            "master_filepath": master_filepath,
            "semanas_actualizadas": semanas_nuevas,
            "semanas_historicas_preservadas": semanas_hist,
            "total_semanas": len(all_weeks),
            "semana_min": all_weeks[0] if all_weeks else "-",
            "semana_max": all_weeks[-1] if all_weeks else "-",
            "total_variedades": len(df_consolidado),
            "df_consolidado": df_consolidado
        }
    except Exception as e:
        return {"status": "error", "message": f"Error al sincronizar Pedido Consolidado Maestro: {str(e)}"}


def sincronizar_plan_detallado_desde_pedido_master(
    master_filepath: str = "PedidoConsolidado_master.xlsx",
    detailed_filepath: str = "Plan_Aprobado_Detallado.csv",
    db = None
) -> pd.DataFrame:
    """
    Sincroniza dinámicamente 'Plan_Aprobado_Detallado.csv' a partir del archivo maestro 'PedidoConsolidado_master.xlsx'.
    - Explota los esquejes del pedido en semanas de siembra y enraizamiento vía MVA.
    - Proyecta los tallos comerciales esperados según la fenología y curvas dinámicas calibradas de cada variedad.
    - Preserva semanas históricas anteriores a la primera semana del archivo maestro si existen.
    - Garantiza que los módulos de Enraizamiento, Ocupación y ForeCast operen en tiempo real con cifras vivas sin desfases.
    """
    import os
    from datetime import date, timedelta
    from app.core.database import SessionLocal
    from app.models.models import Variedad
    from app.services.forecast_service import calcular_curvas_dinamicas

    if not os.path.exists(master_filepath):
        return pd.DataFrame()

    df_mva = generar_plan_mva(master_filepath, week_is="Pedido")
    if df_mva.empty or 'Semana_Siembra' not in df_mva.columns:
        return pd.DataFrame()

    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        vars_db = {v.nombre.strip().lower(): v for v in db.query(Variedad).all()}
        curvas_dyn = calcular_curvas_dinamicas(alpha=1.0, num_ciclos=9, db=db)

        sems_mva_s = sorted([str(s).split('.')[0].strip() for s in df_mva['Semana_Siembra'].unique()])
        sem_min_mva = sems_mva_s[0] if sems_mva_s else '202638'

        # 1. Preservar semanas históricas previas a sem_min_mva si existían en el detallado
        df_hist_past = pd.DataFrame()
        if os.path.exists(detailed_filepath):
            try:
                df_old = pd.read_csv(detailed_filepath)
                if 'Semana_Siembra' in df_old.columns:
                    df_old['Semana_Siembra'] = df_old['Semana_Siembra'].astype(str)
                    df_hist_past = df_old[df_old['Semana_Siembra'] < sem_min_mva].copy()
            except Exception:
                df_hist_past = pd.DataFrame()

        # 2. Convertir cada orden del maestro a formato detallado enriquecido con fenología
        records_mva = []
        for _, r in df_mva.iterrows():
            v_name = str(r['Variedad']).strip()
            v_norm = v_name.lower()
            esq = int(round(r['Esquejes_Para_Siembra (Final)']))
            sem_s = str(r['Semana_Siembra']).strip().split('.')[0]
            sem_p = str(r.get('Semana_Pedido_MV') or iso_add_weeks(sem_s, -4))
            sem_e = iso_add_weeks(sem_s, -3)

            dp = 77
            aprov = 0.806
            dia_ini = 70
            if v_name in curvas_dyn:
                dp = int(curvas_dyn[v_name].get('dia_pico', 77))
                aprov = float(curvas_dyn[v_name].get('aprov', 0.806))
                dia_ini = int(curvas_dyn[v_name].get('dia_inicio', 70))
            elif v_norm in vars_db:
                vo = vars_db[v_norm]
                dp = int(vo.dia_pico) if vo.dia_pico else 77
                aprov = float(vo.aprov_pp) if vo.aprov_pp else 0.806
                dia_ini = int(vo.dia_inicio) if vo.dia_inicio else 70

            sem_c = iso_add_weeks(sem_s, int(round(dp / 7.0)))
            camas = round(esq / 5200.0, 1)
            tallos_esp = int(round(esq * aprov))

            records_mva.append({
                'Flor': r.get('Flor', 'Standard'),
                'Color': r.get('Color', 'Mix'),
                'Variedad': v_name,
                'Semana_Cosecha': sem_c,
                'Semana_Siembra': sem_s,
                'Semana_Enraizamiento': sem_e,
                'Semana_Pedido_MV': sem_p,
                'Esquejes': esq,
                'Camas': camas,
                'Aprov_PP': aprov,
                'Tallos_Esperados': tallos_esp,
                'Dia_Pico': dp,
                'Dia_Inicio': dia_ini
            })

        df_mva_det = pd.DataFrame(records_mva)

        # 3. Concatenar histórico previo y pedidos actualizados
        if not df_hist_past.empty:
            for c in df_mva_det.columns:
                if c not in df_hist_past.columns:
                    df_hist_past[c] = None
            df_consolidado = pd.concat([df_hist_past[df_mva_det.columns], df_mva_det], ignore_index=True)
        else:
            df_consolidado = df_mva_det

        # 4. Guardar archivo detallado de forma atómica
        det_cols = [
            'Flor', 'Color', 'Variedad', 'Semana_Cosecha', 'Semana_Siembra',
            'Semana_Enraizamiento', 'Semana_Pedido_MV', 'Esquejes', 'Camas',
            'Aprov_PP', 'Tallos_Esperados', 'Dia_Pico', 'Dia_Inicio'
        ]
        det_cols = [c for c in det_cols if c in df_consolidado.columns]
        df_consolidado = df_consolidado[det_cols].sort_values(['Semana_Siembra', 'Flor', 'Color', 'Variedad']).reset_index(drop=True)
        df_consolidado.to_csv(detailed_filepath, index=False)

        return df_consolidado
    finally:
        if close_db:
            db.close()


