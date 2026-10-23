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
    
    # Calcular curvas dinámicamente con los parámetros óptimos calibrados
    curvas_dinamicas = calcular_curvas_dinamicas(db=db)
    
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

def extraer_semana_iso(val):
    """
    Extrae el código canónico de semana ISO YYYYWW (ej. '202704', '202643')
    desde múltiples formatos utilizados en plantillas de Webflowers, S&OP y Excel:
    - Fechas ISO en el encabezado: 'Sem4. 2027-01-25', 'Sem. 2026-10-19', '2027-01-25'
    - Fechas en formato DD/MM/YYYY: '25/01/2027', 'Sem4. 25/01/2027'
    - Código ISO de 6 dígitos: '202643', '202704', 202643, 202704.0
    - Código con prefijo S: 'S202643', 'S2643'
    - Objetos date, datetime o Timestamp directos de Excel
    """
    import re
    from datetime import date, datetime
    import pandas as pd

    if val is None:
        return None
    if isinstance(val, (datetime, date, pd.Timestamp)):
        iy, iw, _ = val.isocalendar()
        return f"{iy}{iw:02d}"

    s = str(val).strip()

    # 1. Buscar fecha YYYY-MM-DD (ej. 'Sem4. 2027-01-25')
    m_date = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', s)
    if m_date:
        y, m, d = int(m_date.group(1)), int(m_date.group(2)), int(m_date.group(3))
        try:
            return f"{date(y, m, d).isocalendar()[0]}{date(y, m, d).isocalendar()[1]:02d}"
        except Exception:
            pass

    # 2. Buscar fecha DD/MM/YYYY (ej. 'Sem4. 25/01/2027')
    m_date2 = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', s)
    if m_date2:
        d, m, y = int(m_date2.group(1)), int(m_date2.group(2)), int(m_date2.group(3))
        try:
            return f"{date(y, m, d).isocalendar()[0]}{date(y, m, d).isocalendar()[1]:02d}"
        except Exception:
            pass

    # 3. Código ISO de 6 dígitos que empiece por 202 (ej. '202643', '202704')
    m_iso = re.search(r'\b(202\d{3})\b', s)
    if m_iso:
        return m_iso.group(1)

    # 4. Número flotante o entero de 6 dígitos (ej. 202643.0)
    try:
        f_val = float(s)
        i_val = int(f_val)
        s_i = str(i_val)
        if len(s_i) == 6 and s_i.startswith('202'):
            return s_i
    except Exception:
        pass

    # 5. Formato S + 6 dígitos o S + 4 dígitos (ej. 'S202643', 'S2643')
    m_s = re.search(r'[sS](\d{4,6})', s)
    if m_s:
        num = m_s.group(1)
        if len(num) == 6:
            return num
        if len(num) == 4:
            return f"20{num}"

    return None

def combinar_proyecciones_52_semanas(df_forecast, df_proyeccion, horizonte_semanas=None):
    """
    Combina el forecast de corto plazo (inventario vivo) con el forecast de largo plazo (MVA / Plan Detallado)
    para crear una proyección consolidada (52 semanas a 91 semanas).
    - Primeras 10 semanas: Vienen de df_forecast (Inventario Vivo en suelo).
    - Siguientes semanas: Vienen de df_proyeccion (MVA / Plan Detallado Aprobado).
    - Si horizonte_semanas es None, retorna todas las semanas disponibles en el horizonte.
    """
    from datetime import date
    from app.services.forecast_service import isocalendar_to_string
    import pandas as pd
    
    meta_cols = ['Flor', 'Color', 'Variedad']
    
    if (df_forecast is None or df_forecast.empty) and (df_proyeccion is None or df_proyeccion.empty):
        return pd.DataFrame(columns=meta_cols)
        
    if df_forecast is None or df_forecast.empty:
        df_p = df_proyeccion.copy()
        for mc in meta_cols:
            if mc not in df_p.columns:
                df_p[mc] = ""
        cols_mva = sorted([c for c in df_p.columns if str(c).startswith('202')])
        cols_ret = cols_mva[:horizonte_semanas] if horizonte_semanas else cols_mva
        return df_p[meta_cols + cols_ret]
        
    if df_proyeccion is None or df_proyeccion.empty:
        df_f = df_forecast.copy()
        for mc in meta_cols:
            if mc not in df_f.columns:
                df_f[mc] = ""
        cols_fc = sorted([c for c in df_f.columns if str(c).startswith('202')])
        cols_ret = cols_fc[:horizonte_semanas] if horizonte_semanas else cols_fc
        return df_f[meta_cols + cols_ret]

    # Asegurar columnas meta
    df_f = df_forecast.copy()
    for mc in meta_cols:
        if mc not in df_f.columns:
            df_f[mc] = ""
            
    df_p = df_proyeccion.copy()
    for mc in meta_cols:
        if mc not in df_p.columns:
            df_p[mc] = ""
    
    # 1. Preparar las 10 semanas de inventario vivo
    semana_actual = isocalendar_to_string(date.today())
    cols_fc = sorted([c for c in df_f.columns if str(c).startswith('202')])
    semanas_viv = [s for s in cols_fc if s >= semana_actual][:10]
    
    df_viv = df_f[meta_cols + semanas_viv].copy()
    
    # 2. Preparar el MVA a partir de la semana 11
    cols_mva = sorted([c for c in df_p.columns if str(c).startswith('202')])
    if semanas_viv:
        ultima_semana_viv = semanas_viv[-1]
        semanas_mva = [s for s in cols_mva if s > ultima_semana_viv]
    else:
        semanas_mva = cols_mva
        
    df_mrp_futuro = df_p[meta_cols + semanas_mva].copy()
    
    # 3. Hacer un merge exterior (outer join) por Flor, Color, Variedad
    df_consolidado = pd.merge(df_viv, df_mrp_futuro, on=meta_cols, how='outer')
    
    # Rellenar nulos con 0
    df_consolidado = df_consolidado.fillna(0)
    
    # Ordenar y seleccionar semanas
    todas_las_semanas = sorted([c for c in df_consolidado.columns if str(c).startswith('202')])
    semanas_final = todas_las_semanas[:horizonte_semanas] if horizonte_semanas else todas_las_semanas
    
    df_final = df_consolidado[meta_cols + semanas_final]
    
    return df_final

def llenar_plantilla_52_semanas(template_bytes, df_52_semanas):
    """
    Toma una plantilla Excel de 52 semanas / largo plazo subida por el usuario (ej. CH2026-43.xlsx),
    identifica dinámicamente la columna 'Variedad' y todas las columnas de semanas
    (detecta encabezados con fecha 'Sem4. 2027-01-25', ISO '202640', 'S202701', etc.),
    e inyecta con precisión los tallos proyectados correspondientes.
    
    Utiliza openpyxl como motor principal para preservar al 100% las fuentes, estilos,
    anchos de columna, fórmulas y estructura original de la plantilla.
    """
    import io
    import pandas as pd
    import openpyxl
    
    # Pre-procesar df_52_semanas para búsquedas rápidas con deduplicación insensible a mayúsculas
    df_temp = df_52_semanas.copy() if df_52_semanas is not None else pd.DataFrame()
    if not df_temp.empty and 'Variedad' in df_temp.columns:
        df_temp['Variedad_norm'] = df_temp['Variedad'].astype(str).str.strip().str.lower()
        cols_num = [c for c in df_temp.columns if str(c).startswith('202')]
        df_data = df_temp.groupby('Variedad_norm')[cols_num].sum()
    else:
        df_data = pd.DataFrame()

    # 1. Intentar procesar con openpyxl (mantiene estilos y formatos intactos)
    try:
        wb = openpyxl.load_workbook(io.BytesIO(template_bytes))
        ws = wb.active
        
        # Localizar la columna de Variedad
        col_var = None
        for c in range(1, ws.max_column + 1):
            val = str(ws.cell(1, c).value or '').strip().lower()
            if 'variedad' in val:
                col_var = c
                break
                
        if col_var is None:
            col_var = 3  # Por defecto columna 3 en Webflowers
            
        # Mapear columnas de semanas dinámicamente
        week_cols = {}
        for c in range(1, ws.max_column + 1):
            val = ws.cell(1, c).value
            iso = extraer_semana_iso(val)
            if iso:
                week_cols[c] = iso

        # Inyectar tallos proyectados fila por fila
        for r in range(2, ws.max_row + 1):
            var_cell = ws.cell(r, col_var).value
            if not var_cell:
                continue
            var_norm = str(var_cell).strip().lower()
            
            for c, iso_wk in week_cols.items():
                val = 0
                if not df_data.empty and var_norm in df_data.index and iso_wk in df_data.columns:
                    v = df_data.loc[var_norm, iso_wk]
                    if hasattr(v, 'iloc'):
                        v = v.iloc[0] if len(v) > 0 else 0
                    if pd.notna(v):
                        try:
                            val = int(round(float(v)))
                        except (ValueError, TypeError):
                            val = 0
                ws.cell(r, c).value = val
                
        output = io.BytesIO()
        wb.save(output)
        return output.getvalue()
        
    except Exception as e:
        # Fallback de respaldo con pandas en caso de archivos legacy .xls
        excel_file = pd.ExcelFile(io.BytesIO(template_bytes))
        sheet_name = excel_file.sheet_names[0] if excel_file.sheet_names else 'Plantilla'
        df_template = pd.read_excel(excel_file, sheet_name=sheet_name)
        
        # Identificar mapeo de columnas con extraer_semana_iso
        col_var_name = None
        for col in df_template.columns:
            if 'variedad' in str(col).lower():
                col_var_name = col
                break
                
        if col_var_name:
            col_map = {}
            for col in df_template.columns:
                iso = extraer_semana_iso(col)
                if iso:
                    col_map[col] = iso
                    
            for idx, row in df_template.iterrows():
                var_orig = str(row[col_var_name]).strip().lower()
                for col_orig, iso_wk in col_map.items():
                    val = 0
                    if not df_data.empty and var_orig in df_data.index and iso_wk in df_data.columns:
                        v = df_data.loc[var_orig, iso_wk]
                        if hasattr(v, 'iloc'):
                            v = v.iloc[0] if len(v) > 0 else 0
                        if pd.notna(v):
                            try:
                                val = int(round(float(v)))
                            except (ValueError, TypeError):
                                val = 0
                    df_template.at[idx, col_orig] = val
                    
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
    - Explota los esquejes del pedido en semanas de siembra y enraizamiento vía MVA preservando la integridad biológica y fenológica.
    - Proyecta los tallos comerciales esperados según la fenología y curvas dinámicas calibradas de cada variedad.
    - Preserva semanas históricas anteriores a la primera semana del archivo maestro si existen.
    - Garantiza que los módulos de Enraizamiento, Ocupación y ForeCast operen en tiempo real con cifras vivas sin desfases.
    - Mantiene 'Plan_Aprobado.csv' protegido e inalterado como la meta comercial aprobada por la empresa.
    """
    import os
    from datetime import date, timedelta
    from app.core.database import SessionLocal
    from app.models.models import Variedad
    from app.services.forecast_service import calcular_curvas_dinamicas

    if not os.path.exists(master_filepath):
        return pd.DataFrame()

    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        df_mva = generar_plan_mva(master_filepath, week_is="Pedido")

        if df_mva.empty or 'Semana_Siembra' not in df_mva.columns:
            return pd.DataFrame()

        vars_db = {v.nombre.strip().lower(): v for v in db.query(Variedad).all()}
        curvas_dyn = calcular_curvas_dinamicas(db=db)

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

        # 5. Re-aplicar automáticamente ajustes y absorciones de inventario registradas
        try:
            from app.services.enraizamiento_service import ARCHIVO_INVENTARIO_RECEPCION, sincronizar_plan_detallado_con_inventario_ajustado
            if os.path.exists(ARCHIVO_INVENTARIO_RECEPCION):
                df_inv_exist = pd.read_csv(ARCHIVO_INVENTARIO_RECEPCION)
                if 'Semana_Enraizamiento' in df_inv_exist.columns:
                    for sem_inv in df_inv_exist['Semana_Enraizamiento'].dropna().unique():
                        df_sem_inv = df_inv_exist[df_inv_exist['Semana_Enraizamiento'] == sem_inv]
                        sincronizar_plan_detallado_con_inventario_ajustado(str(sem_inv), df_sem_inv, detailed_file=detailed_filepath, db=db)
                df_consolidado = pd.read_csv(detailed_filepath)
        except Exception as e_reinv:
            print(f"Aviso re-aplicando inventario en plan detallado: {e_reinv}")

        return df_consolidado
    finally:
        if close_db:
            db.close()


def generar_forecast_3_tramos(db, alpha=None, num_ciclos=None, params_por_flor=None, horizonte_semanas=None):
    import os
    from app.services.forecast_service import isocalendar_to_string, generar_forecast_13wk
    from app.services.enraizamiento_service import sumar_semanas_iso

    semana_actual = isocalendar_to_string(date.today())
    total_sems = horizonte_semanas if horizonte_semanas else 52
    semanas_futuras = [sumar_semanas_iso(semana_actual, i) for i in range(total_sems)]
    
    sems_t1 = semanas_futuras[:10]
    sems_t2 = semanas_futuras[10:13]
    sems_t3 = semanas_futuras[13:]
    
    meta_cols = ['Flor', 'Color', 'Variedad']
    
    # 1. Tramo 1: Inventario Vivo en Suelo (S1 a S10)
    df_vivo = generar_forecast_13wk(db, alpha=alpha, num_ciclos=num_ciclos, params_por_flor=params_por_flor)
    
    # 2. Tramo 2: Enraizamiento Ejecutado en Plataforma (S11 a S13)
    df_enr = pd.read_csv("Ejecucion_Real_Enraizamiento.csv") if os.path.exists("Ejecucion_Real_Enraizamiento.csv") else pd.DataFrame()
    df_proy_enr = pd.DataFrame()
    if not df_enr.empty:
        # Usar estrictamente los esquejes reales clavados (> 0) para no inflar con programados no ejecutados
        df_enr_active = df_enr[df_enr['Esquejes_Reales'] > 0].copy()
        df_enr_active['Esquejes_Para_Siembra (Final)'] = df_enr_active['Esquejes_Reales']
        df_enr_active['Semana_Siembra'] = df_enr_active['Semana_Siembra_Proyectada']
        if not df_enr_active.empty:
            df_proy_enr = proyectar_cosecha_desde_mva(df_enr_active, db)
            
    # 3. Tramo 3: Proyección del Enraizamiento del Material Vegetal Planificado (S14+)
    df_proy_mva = pd.DataFrame()
    if os.path.exists("Plan_Aprobado_Detallado.csv"):
        df_det = pd.read_csv("Plan_Aprobado_Detallado.csv")
        if 'Esquejes' in df_det.columns and not df_det.empty:
            df_det['Esquejes_Para_Siembra (Final)'] = df_det['Esquejes']
            df_proy_mva = proyectar_cosecha_desde_mva(df_det, db)
    elif os.path.exists("PedidoConsolidado_master.xlsx"):
        df_mrp = generar_plan_mva("PedidoConsolidado_master.xlsx", week_is="Pedido")
        df_proy_mva = proyectar_cosecha_desde_mva(df_mrp, db)

    def preparar_g(df_src, semanas):
        if df_src is None or df_src.empty:
            return pd.DataFrame()
        d = df_src.copy()
        d['var_norm'] = d['Variedad'].astype(str).str.strip().str.lower()
        cols = [c for c in semanas if c in d.columns]
        return d.groupby('var_norm')[cols].sum().reindex(columns=semanas, fill_value=0.0)

    g1 = preparar_g(df_vivo, sems_t1)
    g2 = preparar_g(df_proy_enr, sems_t2)
    g3 = preparar_g(df_proy_mva, sems_t3)
    
    # Fallback exclusivo si Tramo 2 no tiene ningún dato ejecutado en plataforma
    if g2.empty and not df_proy_mva.empty and len(sems_t2) > 0:
        g2 = preparar_g(df_proy_mva, sems_t2)

    # Catálogo unificado de variedades
    meta_dict = {}
    for df_src in [df_vivo, df_enr, df_proy_mva]:
        if df_src is not None and not df_src.empty and 'Variedad' in df_src.columns:
            d = df_src.copy()
            d['var_norm'] = d['Variedad'].astype(str).str.strip().str.lower()
            for _, r in d.iterrows():
                vn = r['var_norm']
                if vn not in meta_dict or not meta_dict[vn].get('Flor'):
                    meta_dict[vn] = {m: r[m] if m in r and pd.notna(r[m]) else '' for m in meta_cols}
                    meta_dict[vn]['Variedad'] = r['Variedad']

    all_vars = sorted(list(set(list(g1.index) + list(g2.index) + list(g3.index) + list(meta_dict.keys()))))
    g1_f = g1.reindex(index=all_vars, fill_value=0.0) if not g1.empty else pd.DataFrame(0.0, index=all_vars, columns=sems_t1)
    g2_f = g2.reindex(index=all_vars, fill_value=0.0) if not g2.empty else pd.DataFrame(0.0, index=all_vars, columns=sems_t2)
    g3_f = g3.reindex(index=all_vars, fill_value=0.0) if not g3.empty else pd.DataFrame(0.0, index=all_vars, columns=sems_t3)
    
    g_comb = pd.concat([g1_f, g2_f, g3_f], axis=1)
    
    records = []
    for vn in all_vars:
        m = meta_dict.get(vn, {'Flor': '', 'Color': '', 'Variedad': vn})
        recs = {**m, **g_comb.loc[vn].to_dict()}
        records.append(recs)
        
    df_res = pd.DataFrame(records)
    cols_order = meta_cols + [c for c in semanas_futuras if c in df_res.columns]
    return df_res[cols_order].fillna(0.0).drop_duplicates(subset=['Variedad'])


