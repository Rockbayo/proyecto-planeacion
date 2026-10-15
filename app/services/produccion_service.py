import pandas as pd
from datetime import date, timedelta


def get_iso_week_string(dt: date) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}{w:02d}"

def process_plan_produccion(plan_bytes: bytes, db):
    """
    Procesa el archivo del plan de producción, aplica MVA si no hay variedad,
    agrupa por semana, aplica regla de mínimo 2000 tallos (y 2 semanas), 
    convierte a camas completas y realiza backward scheduling.
    """
    import io
    import json
    import os
    from app.models.models import DistribucionMVA, Variedad
    
    # 1. Cargar el plan
    df_plan_original = pd.read_excel(io.BytesIO(plan_bytes))
    df_plan = df_plan_original.copy()
    
    with open("debug_error.txt", "w") as f:
        f.write(f"Iniciando proceso. Filas originales: {len(df_plan)}\n")
        
    # Normalizar columnas esperadas
    cols_necesarias = ['Flower', 'Color', 'Variedad', 'Semana', 'Suma de Tallos']
    for c in cols_necesarias:
        if c not in df_plan.columns:
            raise ValueError(f"Falta la columna '{c}' en el archivo de plan.")
    
    df_plan = df_plan[cols_necesarias].copy()
    
    # 2. Cargar Temporadas desde JSON (Programación Diaria)
    seasons_file = "config_temporadas.json"
    if os.path.exists(seasons_file):
        with open(seasons_file, "r") as f:
            seasons_config = json.load(f)
    else:
        seasons_config = [
            {"Temporada": "Fall", "Semana Inicio": 202632, "Semana Fin": 202646},
            {"Temporada": "Navidad", "Semana Inicio": 202647, "Semana Fin": 202650},
            {"Temporada": "San valentin", "Semana Inicio": 202703, "Semana Fin": 202705},
            {"Temporada": "Madres", "Semana Inicio": 202716, "Semana Fin": 202718},
            {"Temporada": "Summer", "Semana Inicio": 202719, "Semana Fin": 202731}
        ]

    def get_temporada(semana):
        try:
            sem_num = int(float(semana))
            week_target = sem_num % 100
        except:
            return "EVERYDAY"
            
        for s in seasons_config:
            ini = s.get("Semana Inicio", 0)
            fin = s.get("Semana Fin", 0)
            if ini == 0 and fin == 0:
                continue
                
            w_ini = ini % 100 if ini > 100 else ini
            w_fin = fin % 100 if fin > 100 else fin
            
            if w_ini <= w_fin:
                in_season = (w_ini <= week_target <= w_fin)
            else:
                in_season = (week_target >= w_ini or week_target <= w_fin)
                
            if in_season:
                name = str(s.get("Temporada", "")).strip().upper()
                if name == "NAVIDAD": return "XMASS"
                if name == "SAN VALENTIN": return "VALENTINE'S DAY"
                return name
        return "EVERYDAY"
        
    # 2.5 Cargar MVA desde Base de Datos SQLite
    # Asumimos finca "CH" por defecto como en la UI
    mva_records = db.query(DistribucionMVA).filter(DistribucionMVA.finca.in_(["CH", "ALL"])).all()
    
    # Crear un diccionario para búsquedas rápidas del MVA
    # key: (Temporada, Flor, Color) -> list of (Variedad, %)
    mva_dict = {}
    for r in mva_records:
        if not r.flor or not r.color or not r.temporada or not r.variedad_nombre:
            continue
        k = (str(r.temporada).strip().upper(), 
             str(r.flor).strip().upper(), 
             str(r.color).strip().upper())
        if k not in mva_dict:
            mva_dict[k] = []
        if r.porcentaje and r.porcentaje > 0:
            mva_dict[k].append((str(r.variedad_nombre).strip(), float(r.porcentaje)))

    # Cargar mapeo maestro de variedades para garantizar flor y color canónicos
    vars_db = db.query(Variedad).all()
    v_map = {v.nombre.strip().lower(): (v.flor.strip(), v.color.strip()) for v in vars_db}

    # 3. Aplicar MVA y agrupar por Variedad y Semana
    records = []
    for _, row in df_plan.iterrows():
        semana_raw = row['Semana']
        if pd.isna(semana_raw):
            continue
        try:
            # Handle float representation safely (e.g. 202640.0 -> "202640")
            semana_str = str(int(float(semana_raw)))
        except:
            semana_str = str(semana_raw).strip()
            
        temporada = get_temporada(semana_str)
        flor = str(row['Flower']).strip()
        color = str(row['Color']).strip()
        variedad = row['Variedad']
        tallos = pd.to_numeric(row['Suma de Tallos'], errors='coerce')
        if pd.isna(tallos) or tallos <= 0:
            continue
            
        flor_key = flor.upper()
        color_key = color.upper()
            
        if pd.isna(variedad) or str(variedad).strip() == "":
            # Aplicar MVA
            k_temporada = (temporada, flor_key, color_key)
            k_everyday = ("EVERYDAY", flor_key, color_key)
            
            mva_list = mva_dict.get(k_temporada)
            if not mva_list:
                # Fallback to Everyday si no existe para la temporada
                mva_list = mva_dict.get(k_everyday)
                
            if not mva_list:
                # Excepción: Ignorar completamente si no existe ni en Temporada ni en Everyday
                continue
            else:
                for (var_mva, pct) in mva_list:
                    var_clean = str(var_mva).strip()
                    fl_can, col_can = v_map.get(var_clean.lower(), (flor, color))
                    records.append({
                        "Flor": fl_can, "Color": col_can, "Variedad": var_clean,
                        "Semana_Cosecha": semana_str, "Tallos": tallos * pct
                    })
        else:
            var_clean = str(variedad).strip()
            fl_can, col_can = v_map.get(var_clean.lower(), (flor, color))
            records.append({
                "Flor": fl_can, "Color": col_can, "Variedad": var_clean,
                "Semana_Cosecha": semana_str, "Tallos": tallos
            })
            
    df_records = pd.DataFrame(records)
    if df_records.empty:
        return pd.DataFrame(), pd.DataFrame()
        
    # Agrupar por Flor, Color, Variedad y Semana_Cosecha
    df_grouped = df_records.groupby(['Flor', 'Color', 'Variedad', 'Semana_Cosecha'], as_index=False)['Tallos'].sum()
    
    # Ordenar por Variedad y Semana
    df_grouped = df_grouped.sort_values(['Variedad', 'Semana_Cosecha'])
    
    # 4. Calcular Plantas a Sembrar (sin regla de camas completas) y Backward Scheduling
    final_records = []
    
    # Generar curvas de distribución mediante el modelo determinístico dinámico
    from app.services.forecast_service import calcular_curvas_dinamicas
    dyn_curves = calcular_curvas_dinamicas(alpha=1.0, num_ciclos=9)
    var_dict = {k.strip().lower(): v for k, v in dyn_curves.items()}
    
    # Agrupar por Flor, Color, Semana para distribuir camas sin acumular errores
    df_grouped_fc = df_grouped.groupby(['Flor', 'Color', 'Semana_Cosecha'])
    
    for (flor, color, sem_cosecha), group in df_grouped_fc:
        variedades_info = []
        total_plantas_teoricas = 0.0
        
        for _, row in group.iterrows():
            variedad = row['Variedad']
            tallos = row['Tallos']
            
            var_norm = str(variedad).strip().lower()
            var_db = var_dict.get(var_norm)
            
            suma_curva = 1.0
            dia_pico = 70
            if var_db:
                sc = sum(var_db.get(f'c{i}', 0) for i in range(1, 16))
                if sc > 0:
                    suma_curva = sc
                if 'dia_pico' in var_db and var_db['dia_pico'] > 0:
                    dia_pico = var_db['dia_pico']
                    
            plantas_t = tallos / suma_curva
            total_plantas_teoricas += plantas_t
            
            variedades_info.append({
                'variedad': variedad,
                'tallos': tallos,
                'plantas_teoricas': plantas_t,
                'suma_curva': suma_curva,
                'dia_pico': dia_pico
            })
            
        # Calcular total de camas para este Flor-Color-Semana
        camas_objetivo = round(total_plantas_teoricas / 4800)
        if camas_objetivo == 0 and total_plantas_teoricas > 0:
            camas_objetivo = 1
            
        # Asignación inicial (pisos)
        camas_asignadas = 0
        for info in variedades_info:
            info['camas'] = int(info['plantas_teoricas'] // 4800)
            info['fraccion'] = info['plantas_teoricas'] / 4800 - info['camas']
            camas_asignadas += info['camas']
            
        # Asignar camas restantes a los que tengan mayor fracción
        camas_faltantes = camas_objetivo - camas_asignadas
        if camas_faltantes > 0:
            # Ordenar por fracción descendente
            variedades_info.sort(key=lambda x: x['fraccion'], reverse=True)
            for i in range(camas_faltantes):
                variedades_info[i % len(variedades_info)]['camas'] += 1
                
        # Ahora que ya tienen las camas exactas, generamos los records
        for info in variedades_info:
            if info['camas'] == 0:
                continue # No se planta esta variedad porque el volumen fue muy pequeño y perdió en el reparto
                
            plantas_siembra = info['camas'] * 4800
            
            try:
                year = int(sem_cosecha[:4])
                week = int(sem_cosecha[4:])
                fecha_pico = date.fromisocalendar(year, week, 4)
            except Exception as e:
                with open("debug_error.txt", "a") as f:
                    f.write(f"Error parsing date for sem_cosecha '{sem_cosecha}': {e}\n")
                continue
                
            fecha_siembra = fecha_pico - timedelta(days=info['dia_pico'])
            sem_siembra = get_iso_week_string(fecha_siembra)
            
            fecha_enraizamiento = fecha_siembra - timedelta(days=21)
            sem_enraizamiento = get_iso_week_string(fecha_enraizamiento)
            
            final_records.append({
                "Flor": flor,
                "Color": color,
                "Variedad": info['variedad'],
                "Semana_Cosecha": sem_cosecha,
                "Tallos_Requeridos": round(info['tallos'], 2),
                "Plantas_Siembra": plantas_siembra,
                "Semana_Siembra": sem_siembra,
                "Semana_Enraizamiento": sem_enraizamiento,
                "Suma_Curva": info['suma_curva']
            })
        
    df_backwards = pd.DataFrame(final_records)
    
    with open("debug_error.txt", "a") as f:
        f.write(f"Final records count: {len(final_records)}\n")
        f.write(f"df_records count: {len(df_records)}\n")
        if not df_records.empty:
            f.write(f"Sample df_records: {df_records.head(2).to_dict()}\n")
            
    if df_backwards.empty:
        return pd.DataFrame(), pd.DataFrame()
    
    # 6. Generar Contrapropuesta (Capacidad Real, asignación directa sin curva biológica)
    df_cp_base = df_backwards.copy()
    df_cp_base['Suma de Tallos'] = (df_cp_base['Plantas_Siembra'] * df_cp_base['Suma_Curva']).round(0)
    
    # Agrupar df_cp_base por Flor, Color, Semana_Cosecha
    df_cp_grp = df_cp_base.groupby(['Flor', 'Color', 'Semana_Cosecha'], as_index=False)['Suma de Tallos'].sum()
    df_cp_grp.rename(columns={'Flor': 'Flower', 'Semana_Cosecha': 'Semana'}, inplace=True)
    df_cp_grp['Semana'] = df_cp_grp['Semana'].astype(str)
    
    # Preparar df_plan_original (agrupar para tener 1 fila por Flower, Color, Semana con sus metadatos)
    df_plan_copy = df_plan_original.copy()
    
    # Sanitizar la columna Semana para evitar diferencias en el cruce (ej. '202644.0' vs '202644')
    def clean_semana(val):
        if pd.isna(val):
            return ""
        try:
            return str(int(float(val)))
        except:
            return str(val).strip()
            
    df_plan_copy['Semana'] = df_plan_copy['Semana'].apply(clean_semana)
    
    # Queremos mantener todas las columnas de df_plan_copy excepto Variedad, Suma de Tallos, Flower, Color, Semana
    group_cols = [c for c in df_plan_copy.columns if c not in ['Variedad', 'Suma de Tallos', 'Flower', 'Color', 'Semana']]
    
    # Agrupar df_plan_copy por Flower, Color, Semana y coger el first() de las estáticas, y sum() de 'Suma de Tallos'
    agg_dict = {'Suma de Tallos': 'sum'}
    for c in group_cols:
        agg_dict[c] = 'first'
        
    df_req_grp = df_plan_copy.groupby(['Flower', 'Color', 'Semana'], as_index=False, dropna=False).agg(agg_dict)
    df_req_grp.rename(columns={'Suma de Tallos': 'Tallos Solicitados (Plan)'}, inplace=True)
    
    # Unir df_req_grp (izquierda) con df_cp_grp (derecha) para no agregar semanas que no estaban en el plan
    df_contrapropuesta = pd.merge(df_req_grp, df_cp_grp, on=['Flower', 'Color', 'Semana'], how='left')
    
    df_contrapropuesta['Suma de Tallos'] = df_contrapropuesta['Suma de Tallos'].fillna(0)
    df_contrapropuesta['Tallos Solicitados (Plan)'] = df_contrapropuesta['Tallos Solicitados (Plan)'].fillna(0)
    df_contrapropuesta['Variacion'] = (df_contrapropuesta['Suma de Tallos'] - df_contrapropuesta['Tallos Solicitados (Plan)']).round(0)
    
    # Reordenar columnas para que se parezca al original
    cols_order = []
    for c in df_plan_original.columns:
        if c == 'Variedad':
            continue # No mostramos variedad en la contrapropuesta final
        elif c == 'Suma de Tallos':
            cols_order.extend(['Tallos Solicitados (Plan)', 'Suma de Tallos', 'Variacion'])
        elif c in df_contrapropuesta.columns:
            cols_order.append(c)
            
    # Añadir cualquier otra que falte
    for c in df_contrapropuesta.columns:
        if c not in cols_order:
            cols_order.append(c)
            
    df_contrapropuesta = df_contrapropuesta[cols_order].sort_values(['Semana', 'Flower', 'Color'])
    
    # Preparar df_detailed combinando lo pedido con lo que se va a producir (df_backwards)
    df_grouped.rename(columns={'Tallos': 'Tallos Pedidos (Plan)'}, inplace=True)
    
    if not df_backwards.empty:
        df_backwards['Tallos a Producir (Capacidad)'] = (df_backwards['Plantas_Siembra'] * df_backwards['Suma_Curva']).round(0)
        
        df_detailed = pd.merge(
            df_grouped,
            df_backwards[['Flor', 'Color', 'Variedad', 'Semana_Cosecha', 'Plantas_Siembra', 'Semana_Siembra', 'Semana_Enraizamiento', 'Tallos a Producir (Capacidad)']],
            on=['Flor', 'Color', 'Variedad', 'Semana_Cosecha'],
            how='left'
        )
    else:
        df_detailed = df_grouped.copy()
        df_detailed['Plantas_Siembra'] = 0
        df_detailed['Semana_Siembra'] = ""
        df_detailed['Semana_Enraizamiento'] = ""
        df_detailed['Tallos a Producir (Capacidad)'] = 0

    df_detailed['Tallos a Producir (Capacidad)'] = df_detailed['Tallos a Producir (Capacidad)'].fillna(0)
    df_detailed['Plantas_Siembra'] = df_detailed['Plantas_Siembra'].fillna(0)
    df_detailed['Diferencia'] = df_detailed['Tallos a Producir (Capacidad)'] - df_detailed['Tallos Pedidos (Plan)']
    
    df_detailed.rename(columns={'Semana_Cosecha': 'Semana'}, inplace=True)

    # Reordenar columnas para mejor legibilidad
    column_order = ['Semana', 'Flor', 'Color', 'Variedad', 'Tallos Pedidos (Plan)', 'Tallos a Producir (Capacidad)', 'Diferencia']
    df_detailed = df_detailed[column_order]

    return df_detailed, df_contrapropuesta, df_backwards


def sincronizar_plan_maestro_y_detallado(
    df_produccion: pd.DataFrame, 
    df_backwards: pd.DataFrame = None, 
    db = None,
    plan_file_path: str = "Plan_Aprobado.csv",
    detailed_file_path: str = "Plan_Aprobado_Detallado.csv"
) -> dict:
    """
    Consolida de manera atómica y persistente el plan de producción aprobado
    tanto en Plan_Aprobado.csv como en Plan_Aprobado_Detallado.csv.
    Garantiza:
    - Semanas limpias en formato texto ISO (ej. '202703', sin .0 ni NaNs ni filas corruptas).
    - Columnas canónicas estandarizadas.
    - Sincronía 100% entre semanas de cosecha y semanas de siembra/enraizamiento.
    """
    import os
    from datetime import date, timedelta
    from app.models.models import Variedad

    def clean_sem(val):
        if pd.isna(val) or str(val).lower() == 'nan':
            return ""
        try:
            return str(int(float(val)))
        except:
            return str(val).strip()

    df_p = df_produccion.copy()
    df_p['Semana'] = df_p['Semana'].apply(clean_sem)
    df_p = df_p[df_p['Semana'] != ""].copy()
    nuevas_semanas = sorted(df_p['Semana'].unique().tolist())

    canon_cols = ['Semana', 'Flor', 'Color', 'Variedad', 'Tallos Pedidos (Plan)', 'Tallos a Producir (Capacidad)', 'Diferencia']
    
    # 1. Consolidar Plan_Aprobado.csv
    if os.path.exists(plan_file_path):
        try:
            df_master = pd.read_csv(plan_file_path)
            # Descartar fila 0 corrupta si existe
            if 'Semana' in df_master.columns and pd.isna(df_master.iloc[0]['Semana']):
                df_master = df_master.iloc[1:].copy()
            df_master['Semana'] = df_master['Semana'].apply(clean_sem)
            df_master = df_master[df_master['Semana'] != ""].copy()
            if 'Flower' in df_master.columns and 'Flor' in df_master.columns:
                df_master['Flor'] = df_master['Flor'].fillna(df_master['Flower'])
            cols_exist = [c for c in canon_cols if c in df_master.columns]
            df_master = df_master[cols_exist].copy()
            df_master = df_master[~df_master['Semana'].isin(nuevas_semanas)]
            df_consolidado = pd.concat([df_master, df_p[canon_cols]], ignore_index=True)
        except Exception:
            df_consolidado = df_p[canon_cols].copy()
    else:
        df_consolidado = df_p[canon_cols].copy()

    df_consolidado = df_consolidado.sort_values(['Semana', 'Flor', 'Color', 'Variedad'])
    df_consolidado.to_csv(plan_file_path, index=False)

    # 2. Consolidar Plan_Aprobado_Detallado.csv
    vars_db = {v.nombre.lower().strip(): v for v in db.query(Variedad).all()} if db else {}
    
    recs_det = []
    if df_backwards is not None and not df_backwards.empty:
        df_bw = df_backwards.copy()
        for _, r in df_bw.iterrows():
            sem_c = clean_sem(r.get('Semana_Cosecha', ''))
            sem_s = clean_sem(r.get('Semana_Siembra', ''))
            sem_e = clean_sem(r.get('Semana_Enraizamiento', ''))
            plantas = int(round(r.get('Plantas_Siembra', 0)))
            camas = round(plantas / 5200.0, 1)
            recs_det.append({
                'Flor': r.get('Flor', ''),
                'Color': r.get('Color', ''),
                'Variedad': r.get('Variedad', ''),
                'Semana_Cosecha': sem_c,
                'Semana_Siembra': sem_s,
                'Semana_Enraizamiento': sem_e,
                'Esquejes': plantas,
                'Camas': camas
            })
    else:
        for _, r in df_p.iterrows():
            v_nom = str(r['Variedad']).strip()
            v_obj = vars_db.get(v_nom.lower())
            dp = v_obj.dia_pico if (v_obj and v_obj.dia_pico) else 77
            ap = v_obj.aprov_pp if (v_obj and v_obj.aprov_pp and v_obj.aprov_pp > 0) else 0.806
            tallos = float(r.get('Tallos a Producir (Capacidad)', 0) or r.get('Tallos Pedidos (Plan)', 0) or 0)
            if tallos <= 0:
                continue
            esq = int(round(tallos / ap))
            cam = round(esq / 5200.0, 1)
            sem_c = clean_sem(r['Semana'])
            y = int(sem_c[:4])
            w = int(sem_c[4:])
            fp = date.fromisocalendar(y, w, 4)
            fs = fp - timedelta(days=dp)
            y_s, w_s, _ = fs.isocalendar()
            sem_s = f'{y_s}{w_s:02d}'
            fe = fs - timedelta(days=21)
            y_e, w_e, _ = fe.isocalendar()
            sem_e = f'{y_e}{w_e:02d}'
            recs_det.append({
                'Flor': r['Flor'],
                'Color': r['Color'],
                'Variedad': v_nom,
                'Semana_Cosecha': sem_c,
                'Semana_Siembra': sem_s,
                'Semana_Enraizamiento': sem_e,
                'Esquejes': esq,
                'Camas': cam
            })

    df_det_new = pd.DataFrame(recs_det)
    
    if os.path.exists(detailed_file_path):
        try:
            df_det_master = pd.read_csv(detailed_file_path)
            # Si el archivo detallado ya es el Pedido de Material Vegetal oficial consolidado (con sus semanas de siembra exactas y 20M+ esquejes),
            # preservamos estrictamente su integridad sin sobreescribir con corrimientos sintéticos.
            if len(df_det_master) > 0 and 'Semana_Siembra' in df_det_master.columns and df_det_master['Esquejes'].sum() > 20000000:
                df_det_consolidado = df_det_master
            else:
                if 'Semana_Cosecha' in df_det_master.columns:
                    df_det_master['Semana_Cosecha'] = df_det_master['Semana_Cosecha'].apply(clean_sem)
                    df_det_master = df_det_master[~df_det_master['Semana_Cosecha'].isin(nuevas_semanas)]
                df_det_consolidado = pd.concat([df_det_master, df_det_new], ignore_index=True)
        except Exception:
            df_det_consolidado = df_det_new
    else:
        df_det_consolidado = df_det_new

    det_order = ['Flor', 'Color', 'Variedad', 'Semana_Cosecha', 'Semana_Siembra', 'Semana_Enraizamiento', 'Esquejes', 'Camas']
    det_order = [c for c in det_order if c in df_det_consolidado.columns]
    df_det_consolidado = df_det_consolidado[det_order].sort_values(['Semana_Siembra', 'Flor', 'Color', 'Variedad'])
    df_det_consolidado.to_csv(detailed_file_path, index=False)

    return {
        "nuevas_semanas": nuevas_semanas,
        "total_filas_master": len(df_consolidado),
        "total_filas_detallado": len(df_det_consolidado),
        "df_consolidado": df_consolidado,
        "df_detallado": df_det_consolidado
    }


def obtener_resumen_plan_vigente(plan_file_path: str = "Plan_Aprobado.csv", db = None) -> dict:
    """
    Retorna los KPIs y datos consolidados del plan maestro actualmente activo.
    """
    import os
    from datetime import datetime

    if not os.path.exists(plan_file_path):
        return {"activo": False}

    try:
        df = pd.read_csv(plan_file_path)
        if df.empty:
            return {"activo": False}

        def clean_sem(val):
            if pd.isna(val) or str(val).lower() == 'nan':
                return ""
            try:
                return str(int(float(val)))
            except:
                return str(val).strip()

        if pd.isna(df.iloc[0].get('Semana')):
            df = df.iloc[1:].copy()

        df['Semana'] = df['Semana'].apply(clean_sem)
        df = df[df['Semana'] != ""].copy()

        mtime = os.path.getmtime(plan_file_path)
        fecha_act = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

        tot_ped = float(df['Tallos Pedidos (Plan)'].sum()) if 'Tallos Pedidos (Plan)' in df.columns else 0.0
        tot_cap = float(df['Tallos a Producir (Capacidad)'].sum()) if 'Tallos a Producir (Capacidad)' in df.columns else (float(df['Suma de Tallos'].sum()) if 'Suma de Tallos' in df.columns else 0.0)
        diff_tot = tot_cap - tot_ped

        semanas_u = sorted(df['Semana'].unique().tolist())
        
        # Resumen San Valentín (S2703 a S2705)
        sv_sems = [s for s in ['202703', '202704', '202705'] if s in semanas_u]
        df_sv = df[df['Semana'].isin(sv_sems)] if sv_sems else pd.DataFrame()
        sv_ped = float(df_sv['Tallos Pedidos (Plan)'].sum()) if not df_sv.empty and 'Tallos Pedidos (Plan)' in df_sv.columns else 0.0
        sv_cap = float(df_sv['Tallos a Producir (Capacidad)'].sum()) if not df_sv.empty and 'Tallos a Producir (Capacidad)' in df_sv.columns else 0.0

        return {
            "activo": True,
            "df_plan": df,
            "fecha_actualizacion": fecha_act,
            "total_filas": len(df),
            "semanas": semanas_u,
            "num_semanas": len(semanas_u),
            "semana_min": semanas_u[0] if semanas_u else "-",
            "semana_max": semanas_u[-1] if semanas_u else "-",
            "total_pedidos": tot_ped,
            "total_capacidad": tot_cap,
            "variacion": diff_tot,
            "sv_pedidos": sv_ped,
            "sv_capacidad": sv_cap,
            "sv_semanas": sv_sems
        }
    except Exception as e:
        return {"activo": False, "error": str(e)}

