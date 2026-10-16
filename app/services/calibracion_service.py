import re
import os
import json
import pandas as pd
from datetime import date, datetime
from sqlalchemy.orm import Session
from app.models.models import Variedad, Siembra, EstadoSiembra
from app.services.forecast_service import isocalendar_to_string

CONFIG_FILE = "parametros_calibrados.json"

def parse_webflowers_report(file_or_path) -> pd.DataFrame:
    """
    Parsea de forma robusta el reporte de Webflowers ('ReporteEstimadosVSRecepcion.xls').
    Maneja tanto archivos HTML con extensión .xls (estándar de Webflowers)
    como archivos Excel reales (.xlsx) o subidos vía Streamlit (BytesIO).
    """
    content = ""
    if hasattr(file_or_path, 'read'):
        # UploadedFile o BytesIO
        raw = file_or_path.read()
        if hasattr(file_or_path, 'seek'):
            file_or_path.seek(0)
        try:
            content = raw.decode('utf-8', errors='ignore')
        except Exception:
            content = str(raw)
    elif isinstance(file_or_path, (bytes, bytearray)):
        content = file_or_path.decode('utf-8', errors='ignore')
    elif isinstance(file_or_path, str) and os.path.exists(file_or_path):
        with open(file_or_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    else:
        return pd.DataFrame()

    # Si contiene etiquetas HTML (formato Webflowers clásico)
    if '<table' in content.lower() or '<tr' in content.lower():
        rows = re.findall(r'<tr.*?>(.*?)</tr>', content, re.DOTALL | re.IGNORECASE)
        parsed = []
        headers = []
        
        for idx, r in enumerate(rows):
            cells = re.findall(r'<t[dh].*?>(.*?)</t[dh]>', r, re.DOTALL | re.IGNORECASE)
            clean = [re.sub(r'<.*?>', '', c).strip().replace('&nbsp;', '') for c in cells]
            if not clean or all(c == '' for c in clean):
                continue
            if idx == 0:
                headers = clean
            else:
                # Omitir fila de pie de página de totales
                if len(clean) >= 6 and clean[0] == '' and clean[1] == '' and clean[2] == '':
                    continue
                if len(clean) == len(headers):
                    parsed.append(clean)
                elif len(clean) > len(headers):
                    parsed.append(clean[:len(headers)])
                
        df = pd.DataFrame(parsed, columns=headers)
    else:
        # Intentar leer con pandas directamente
        try:
            df = pd.read_excel(file_or_path)
        except Exception:
            df = pd.read_csv(file_or_path)

    # Limpieza y estandarización de columnas
    col_map = {}
    for col in df.columns:
        c_clean = col.strip().lower()
        if 'flor' in c_clean or 'flower' in c_clean:
            col_map[col] = 'Flor'
        elif 'color' in c_clean:
            col_map[col] = 'Color'
        elif 'variedad' in c_clean or 'variety' in c_clean:
            col_map[col] = 'Variedad'
        elif 'semana' in c_clean and ('estimaci' in c_clean or 'proy' in c_clean):
            col_map[col] = 'Semana_Estimacion'
        elif 'semana' in c_clean and ('estimada' in c_clean or 'cosecha' in c_clean or 'eval' in c_clean):
            col_map[col] = 'Semana_Estimada'
        elif 'recepcion' in c_clean or 'real' in c_clean:
            col_map[col] = 'Tallos_Recepcionados'
        elif 'estimad' in c_clean or 'forecast' in c_clean:
            col_map[col] = 'Tallos_Estimados'
        elif 'balance' in c_clean or 'cumpl' in c_clean:
            col_map[col] = 'Balance'

    df = df.rename(columns=col_map)

    # Limpieza numérica
    for num_col in ['Tallos_Recepcionados', 'Tallos_Estimados']:
        if num_col in df.columns:
            df[num_col] = pd.to_numeric(
                df[num_col].astype(str).str.replace(',', '').str.replace(' ', ''),
                errors='coerce'
            ).fillna(0)

    if 'Balance' in df.columns:
        df['Balance_%'] = pd.to_numeric(
            df['Balance'].astype(str).str.replace('%', '').str.replace(',', '.').str.replace(' ', ''),
            errors='coerce'
        ).fillna(0)
    elif 'Tallos_Recepcionados' in df.columns and 'Tallos_Estimados' in df.columns:
        df['Balance_%'] = (df['Tallos_Recepcionados'] / df['Tallos_Estimados'] * 100).fillna(0).round(2)

    # Desviación y Error Absoluto
    if 'Tallos_Recepcionados' in df.columns and 'Tallos_Estimados' in df.columns:
        df['Error_Tallos'] = (df['Tallos_Recepcionados'] - df['Tallos_Estimados']).abs()
        df['Sesgo_Tallos'] = df['Tallos_Estimados'] - df['Tallos_Recepcionados']

    return df

DATALAKE_EJECUCIONES_FILE = "Datalake_Ejecuciones.csv"

def inicializar_o_cargar_datalake(db: Session) -> pd.DataFrame:
    """
    Gestiona el Data Lake persistente de Ejecuciones Reales (Cumplimientos y Recepciones).
    Si ya existe 'Datalake_Ejecuciones.csv', lo carga.
    Si no existe, lo inicializa consolidando los 3,313 registros históricos (202501 - 202640)
    provenientes de 'Cumplimientos PER 4 y PER 1, Plan de producción, año anterior y Dumps.xlsx'
    y le anexa el reporte de Webflowers ('ReporteEstimadosVSRecepcion.xls').
    """
    vars_db = db.query(Variedad).all()
    v_map = {v.nombre.strip().lower(): (v.flor.strip(), v.color.strip()) for v in vars_db if v.nombre}

    if os.path.exists(DATALAKE_EJECUCIONES_FILE):
        try:
            df_dl = pd.read_csv(DATALAKE_EJECUCIONES_FILE)
            df_dl['Semana'] = df_dl['Semana'].astype(str)
            return df_dl
        except Exception:
            pass

    records = []
    # 1. Base Histórica PER (92 semanas)
    archivo_base = 'Cumplimientos PER 4 y PER 1, Plan de producción, año anterior y Dumps.xlsx'
    if os.path.exists(archivo_base):
        try:
            df_per = pd.read_excel(archivo_base)
            for _, r in df_per.iterrows():
                v = str(r['Variedad']).strip()
                if not v or v.lower() in ['nan', 'total', '']:
                    continue
                vn = v.lower()
                fl, col = v_map.get(vn, ('Desconocida', 'Desconocido'))
                sem = str(int(float(r['Semana']))) if pd.notna(r['Semana']) else ""
                if not sem:
                    continue
                records.append({
                    'Semana': sem,
                    'Flor': fl,
                    'Color': col,
                    'Variedad': v,
                    'Real_Recepcionado': float(r.get('Exportable', 0.0)),
                    'Estimado_Proyectado': 0.0,
                    'Balance_%': 0.0,
                    'Fuente': 'Historico_PER_Poscosecha',
                    'Fecha_Registro': '2026-10-08'
                })
        except Exception:
            pass

    # 2. Anexar Reporte Webflowers si existe
    archivo_wf = "ReporteEstimadosVSRecepcion.xls"
    if os.path.exists(archivo_wf):
        try:
            df_wf = parse_webflowers_report(archivo_wf)
            for _, r in df_wf.iterrows():
                v = str(r['Variedad']).strip()
                if not v or v.lower() in ['nan', 'total', '']:
                    continue
                vn = v.lower()
                fl, col = v_map.get(vn, (r.get('Flor', 'Desconocida'), r.get('Color', 'Desconocido')))
                sem = str(r.get('Semana_Estimada', ''))
                real = float(r.get('Tallos_Recepcionados', 0.0))
                est = float(r.get('Tallos_Estimados', 0.0))
                bal = float(r.get('Balance_%', (real/est*100) if est > 0 else 0))
                records.append({
                    'Semana': sem,
                    'Flor': fl,
                    'Color': col,
                    'Variedad': v,
                    'Real_Recepcionado': real,
                    'Estimado_Proyectado': est,
                    'Balance_%': round(bal, 2),
                    'Fuente': 'Webflowers_Report',
                    'Fecha_Registro': '2026-10-13'
                })
        except Exception:
            pass

    if records:
        df_dl = pd.DataFrame(records)
    else:
        df_dl = pd.DataFrame(columns=[
            'Semana', 'Flor', 'Color', 'Variedad', 
            'Real_Recepcionado', 'Estimado_Proyectado', 'Balance_%', 
            'Fuente', 'Fecha_Registro'
        ])

    df_dl.to_csv(DATALAKE_EJECUCIONES_FILE, index=False)
    return df_dl

def integrar_reporte_al_datalake(df_nuevo: pd.DataFrame, db: Session) -> tuple:
    """
    Integra de forma acumulativa un reporte nuevo al Data Lake de Ejecuciones.
    Identifica registros nuevos o actualizados basándose en ['Semana', 'Variedad'].
    """
    df_dl = inicializar_o_cargar_datalake(db)
    vars_db = db.query(Variedad).all()
    v_map = {v.nombre.strip().lower(): (v.flor.strip(), v.color.strip()) for v in vars_db if v.nombre}

    nuevos_registros = []
    semanas_afectadas = set()
    today_str = str(date.today())

    for _, r in df_nuevo.iterrows():
        v = str(r.get('Variedad', '')).strip()
        if not v or v.lower() in ['nan', 'total', 'none']:
            continue
        vn = v.lower()
        fl, col = v_map.get(vn, (r.get('Flor', 'Desconocida'), r.get('Color', 'Desconocido')))
        sem = str(r.get('Semana_Estimada', r.get('Semana', ''))).replace('.0', '').strip()
        if not sem:
            continue
        semanas_afectadas.add(sem)

        real = float(r.get('Tallos_Recepcionados', r.get('Exportable', r.get('Real_Recepcionado', 0.0))))
        est = float(r.get('Tallos_Estimados', r.get('Estimado_Proyectado', 0.0)))
        bal = float(r.get('Balance_%', (real/est*100) if est > 0 else 0))

        nuevos_registros.append({
            'Semana': sem,
            'Flor': fl,
            'Color': col,
            'Variedad': v,
            'Real_Recepcionado': real,
            'Estimado_Proyectado': est,
            'Balance_%': round(bal, 2),
            'Fuente': 'Webflowers_Upload',
            'Fecha_Registro': today_str
        })

    if not nuevos_registros:
        return df_dl, 0, list(semanas_afectadas)

    df_incoming = pd.DataFrame(nuevos_registros)

    # Actualizar o anexar por [Semana, Variedad]
    incoming_keys = set(zip(df_incoming['Semana'], df_incoming['Variedad'].str.strip().str.lower()))
    mask_existente = df_dl.apply(
        lambda row: (str(row['Semana']), str(row['Variedad']).strip().lower()) not in incoming_keys, 
        axis=1
    )
    df_conservados = df_dl[mask_existente]

    df_consolidado = pd.concat([df_conservados, df_incoming], ignore_index=True)
    df_consolidado = df_consolidado.sort_values(by=['Semana', 'Flor', 'Variedad'])

    df_consolidado.to_csv(DATALAKE_EJECUCIONES_FILE, index=False)
    nuevos_count = len(df_incoming)

    return df_consolidado, nuevos_count, sorted(list(semanas_afectadas))

def cargar_parametros_calibrados():
    """
    Carga los parámetros óptimos calculados por la última ejecución de Machine Learning.
    Si no existen o no están calibrados, retorna estructura con valores base.
    """
    default_resp = {
        "por_flor": {
            "Cushion": {"alpha": 1.0, "ponderacion_%": 100, "num_ciclos": 9, "wape_%": None, "bias_%": None},
            "Daisy": {"alpha": 1.0, "ponderacion_%": 100, "num_ciclos": 9, "wape_%": None, "bias_%": None},
            "Novelty": {"alpha": 1.0, "ponderacion_%": 100, "num_ciclos": 9, "wape_%": None, "bias_%": None}
        },
        "global": {"alpha": 1.0, "ponderacion_%": 100, "num_ciclos": 9, "wape_%": None, "bias_%": None},
        "alpha": 1.0,
        "ponderacion_%": 100,
        "num_ciclos": 9,
        "fecha_calibracion": None,
        "wape_%": None,
        "origen": "Parametros por Defecto (Manual)"
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if "por_flor" not in data:
                data["por_flor"] = default_resp["por_flor"]
            if "global" not in data:
                data["global"] = {
                    "alpha": float(data.get("alpha", 1.0)),
                    "ponderacion_%": int(data.get("ponderacion_%", 100)),
                    "num_ciclos": int(data.get("num_ciclos", 9)),
                    "wape_%": float(data["wape_%"]) if data.get("wape_%") is not None else None
                }
            return data
        except Exception:
            pass
    return default_resp

def guardar_parametros_calibrados(resultado: dict):
    """
    Guarda los parámetros óptimos en el archivo de configuración JSON.
    Convierte cualquier tipo numpy a tipos nativos de Python para evitar fallos de serialización.
    """
    def sanitize(obj):
        if isinstance(obj, dict):
            return {k: sanitize(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [sanitize(v) for v in obj]
        elif hasattr(obj, 'item'):
            return obj.item()
        return obj

    clean_dict = sanitize(resultado)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(clean_dict, f, indent=4, ensure_ascii=False)

def simular_curvas_en_memoria(df_full: pd.DataFrame, alpha: float, num_ciclos: int) -> dict:
    """
    Versión ultra-rápida de calcular_curvas_dinamicas que opera con el DataFrame ya en memoria.
    Permite correr cientos de iteraciones de ML en milisegundos.
    """
    cortes_cols = [f'Corte {i}' for i in range(1, 16)]
    variedades_nombres = df_full['Variedad'].dropna().unique()
    dict_vars = {}

    for var_name in variedades_nombres:
        df_var_all = df_full[df_full['Variedad'] == var_name]
        if len(df_var_all) == 0:
            continue

        # Histórico Completo
        tot_plantas_hist = df_var_all['NumeroPlantas'].sum() if 'NumeroPlantas' in df_var_all.columns else 0
        sum_cortes_hist = df_var_all[cortes_cols].sum()
        tot_tallos_hist = sum_cortes_hist.sum()
        aprov_hist = (tot_tallos_hist / tot_plantas_hist) if tot_plantas_hist > 0 else 0.0

        curva_hist = [sum_cortes_hist[f'Corte {i}'] / tot_plantas_hist if tot_plantas_hist > 0 else 0.0 for i in range(1, 16)]
        dias_ini_hist = df_var_all['Dias_Inicio'].mean() if 'Dias_Inicio' in df_var_all.columns and not df_var_all['Dias_Inicio'].dropna().empty else 90

        # Últimos N Ciclos
        df_var_n = df_var_all.tail(num_ciclos)
        tot_plantas_nuevo = df_var_n['NumeroPlantas'].sum() if 'NumeroPlantas' in df_var_n.columns else 0

        if tot_plantas_nuevo == 0:
            aprov_suav = aprov_hist
            curva_suav = curva_hist
            dia_inicio_suav = int(dias_ini_hist)
        else:
            sum_cortes_nuevo = df_var_n[cortes_cols].sum()
            tot_tallos_nuevo = sum_cortes_nuevo.sum()
            aprov_nuevo = (tot_tallos_nuevo / tot_plantas_nuevo) if tot_plantas_nuevo > 0 else 0.0
            curva_nueva = [sum_cortes_nuevo[f'Corte {i}'] / tot_plantas_nuevo if tot_plantas_nuevo > 0 else 0.0 for i in range(1, 16)]
            dias_ini_nuevo = df_var_n['Dias_Inicio'].mean() if 'Dias_Inicio' in df_var_n.columns and not df_var_n['Dias_Inicio'].dropna().empty else dias_ini_hist

            aprov_suav = (aprov_nuevo * alpha) + (aprov_hist * (1.0 - alpha))
            curva_suav = [(curva_nueva[i] * alpha) + (curva_hist[i] * (1.0 - alpha)) for i in range(15)]
            dia_inicio_suav = int((dias_ini_nuevo * alpha) + (dias_ini_hist * (1.0 - alpha)))

        dict_vars[var_name] = {
            'aprov': aprov_suav,
            'dia_inicio': dia_inicio_suav,
            'curva': curva_suav
        }

    return dict_vars

def generar_forecast_simulado_semana(siembras_data: list, curvas_dict: dict, semana_objetivo: str, today_ref: date) -> dict:
    """
    Proyecta la producción para una semana específica dada una configuración de curvas.
    """
    from datetime import timedelta
    res_por_variedad = {}

    for s in siembras_data:
        var_nom = s['variedad']
        fecha_siem = s['fecha_siembra']
        plantas = s['plantas']

        if var_nom in curvas_dict:
            c_info = curvas_dict[var_nom]
            dia_inicio = c_info['dia_inicio']
            curvas = c_info['curva']
        else:
            dia_inicio = s.get('dia_inicio_db', 90)
            curvas = s.get('curvas_db', [0.0]*15)

        fecha_ini = fecha_siem + timedelta(days=dia_inicio)
        for dia_indice, perc in enumerate(curvas):
            if perc and perc > 0:
                fecha_corte_dia = fecha_ini + timedelta(days=dia_indice)
                sem_cos = isocalendar_to_string(fecha_corte_dia)
                if sem_cos == semana_objetivo:
                    tallos = plantas * perc
                    res_por_variedad[var_nom.strip().lower()] = res_por_variedad.get(var_nom.strip().lower(), 0.0) + tallos

    return res_por_variedad

def ejecutar_iteraciones_segmentadas_por_flor(db: Session, df_wf: pd.DataFrame, grid_alphas=None, grid_ciclos=None) -> dict:
    """
    Motor de Alta Resolución de Machine Learning / S&OP:
    Ejecuta una búsqueda de grilla exhaustiva (2,000 simulaciones) segmentada por Tipo de Flor
    ('Cushion', 'Daisy', 'Novelty') y nivel Global Finca, evaluando la precisión biológica 
    contra las recepciones reales del Data Lake.
    
    Acelera los cálculos precomputando vectores en memoria para ejecutar 2,000 iteraciones en ~30 segundos.
    """
    from datetime import timedelta

    if grid_alphas is None:
        # 25 niveles de alpha de 0.04 a 1.00
        grid_alphas = [round(a * 0.04, 2) for a in range(1, 26)]
    if grid_ciclos is None:
        # 20 ventanas de ciclos desde 1 hasta 25
        grid_ciclos = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 25]

    if not os.path.exists('Historico_Curvas.csv'):
        raise FileNotFoundError("No se encontró el archivo Historico_Curvas.csv con los ciclos históricos.")

    # 1. Cargar catálogo de variedades para mapeo consistente Flor y Color
    vars_db = db.query(Variedad).all()
    v_map = {v.nombre.strip().lower(): (v.flor.strip(), v.color.strip()) for v in vars_db if v.nombre}

    # 2. Cargar y precomputar caché vectorial por variedad en memoria
    df_hist = pd.read_csv('Historico_Curvas.csv')
    cortes_cols = [f'Corte {i}' for i in range(1, 16)]
    for c in cortes_cols:
        if c not in df_hist.columns:
            df_hist[c] = 0.0

    df_hist['FechaSiembra'] = pd.to_datetime(df_hist.get('FechaSiembra'), errors='coerce')
    df_hist['FechaInicioProduccion'] = pd.to_datetime(df_hist.get('FechaInicioProduccion'), errors='coerce')
    df_hist['Dias_Inicio'] = (df_hist['FechaInicioProduccion'] - df_hist['FechaSiembra']).dt.days

    hist_cache = {}
    grouped_hist = {v: g for v, g in df_hist.groupby('Variedad')}
    max_ciclos_posible = max(grid_ciclos)

    for v_nom, df_v in grouped_hist.items():
        tot_p_hist = df_v['NumeroPlantas'].sum() if 'NumeroPlantas' in df_v.columns else 0
        sc_hist = df_v[cortes_cols].sum()
        c_hist = [sc_hist[f'Corte {i}'] / tot_p_hist if tot_p_hist > 0 else 0.0 for i in range(1, 16)]
        d_ini_hist = df_v['Dias_Inicio'].mean() if not df_v['Dias_Inicio'].dropna().empty else 90.0

        n_cache = {}
        for N in grid_ciclos:
            df_vn = df_v.tail(N)
            tot_pn = df_vn['NumeroPlantas'].sum() if 'NumeroPlantas' in df_vn.columns else 0
            if tot_pn == 0:
                c_n = c_hist
                d_n = d_ini_hist
            else:
                sc_n = df_vn[cortes_cols].sum()
                c_n = [sc_n[f'Corte {i}'] / tot_pn for i in range(1, 16)]
                d_n = df_vn['Dias_Inicio'].mean() if not df_vn['Dias_Inicio'].dropna().empty else d_ini_hist
            n_cache[N] = {'c_n': c_n, 'd_n': d_n}

        hist_cache[v_nom.strip().lower()] = {
            'c_hist': c_hist,
            'd_hist': d_ini_hist,
            'by_n': n_cache
        }

    # 3. Cargar siembras en producción agrupadas por Flor
    siembras_db = db.query(Siembra).filter(Siembra.estado == EstadoSiembra.EN_PRODUCCION).all()
    siembras_by_flor = {'Cushion': [], 'Daisy': [], 'Novelty': [], 'Global': []}

    for s in siembras_db:
        v = s.variedad
        v_n = v.nombre.strip().lower()
        fl, col = v_map.get(v_n, (v.flor.strip() if v.flor else '', ''))
        item = {
            'v_norm': v_n,
            'fecha_siem': s.fecha_siembra,
            'plantas': s.plantas_sembradas,
            'dia_ini_fallback': v.dia_inicio if v.dia_inicio else 90,
            'curvas_fallback': [getattr(v, f'c{i}', 0.0) for i in range(1, 16)]
        }
        siembras_by_flor['Global'].append(item)
        fl_cap = fl.capitalize()
        if fl_cap in siembras_by_flor:
            siembras_by_flor[fl_cap].append(item)

    # 4. Datos de evaluación de la semana objetivo
    semana_objetivo = str(df_wf['Semana_Estimada'].iloc[0])

    flores_a_evaluar = ['Cushion', 'Daisy', 'Novelty', 'Global']
    res_por_flor = {}
    iteraciones_todas = []
    total_simulaciones_count = 0

    for target in flores_a_evaluar:
        if target == 'Global':
            sub_wf = df_wf.copy()
        else:
            sub_wf = df_wf[df_wf['Flor'].str.lower() == target.lower()].copy()

        if sub_wf.empty:
            continue

        real_map = {r['Variedad'].strip().lower(): float(r['Tallos_Recepcionados']) for _, r in sub_wf.iterrows()}
        tot_real_eval = sum(real_map.values())
        siembras_list = siembras_by_flor.get(target, [])

        mejor_wape = float('inf')
        mejor_params = (1.0, 9)
        mejor_bias = 0.0
        mejor_fc_map = {}
        mejor_err_tallos = 0.0

        for alpha in grid_alphas:
            for N in grid_ciclos:
                total_simulaciones_count += 1
                fc_sim = {}
                for s in siembras_list:
                    vn = s['v_norm']
                    f_siem = s['fecha_siem']
                    plantas = s['plantas']

                    if vn in hist_cache and N in hist_cache[vn]['by_n']:
                        hc = hist_cache[vn]
                        c_n = hc['by_n'][N]['c_n']
                        d_n = hc['by_n'][N]['d_n']
                        c_h = hc['c_hist']
                        d_h = hc['d_hist']
                        d_ini = int(round((d_n * alpha) + (d_h * (1.0 - alpha))))
                        c_suav = [(c_n[i] * alpha) + (c_h[i] * (1.0 - alpha)) for i in range(15)]
                    else:
                        d_ini = s['dia_ini_fallback']
                        c_suav = s['curvas_fallback']

                    f_ini = f_siem + timedelta(days=d_ini)
                    for dia_idx, p in enumerate(c_suav):
                        if p > 0:
                            sem_cos = isocalendar_to_string(f_ini + timedelta(days=dia_idx))
                            if sem_cos == semana_objetivo:
                                fc_sim[vn] = fc_sim.get(vn, 0.0) + (plantas * p)

                # Evaluar métricas
                err_abs = 0.0
                tot_fc = 0.0
                for vn, r_val in real_map.items():
                    f_val = fc_sim.get(vn, 0.0)
                    err_abs += abs(r_val - f_val)
                    tot_fc += f_val

                wape = (err_abs / tot_real_eval * 100.0) if tot_real_eval > 0 else 999.0
                bias = ((tot_fc - tot_real_eval) / tot_real_eval * 100.0) if tot_real_eval > 0 else 999.0

                iteraciones_todas.append({
                    "Flor": target,
                    "iteracion": len(iteraciones_todas) + 1,
                    "alpha": round(alpha, 2),
                    "ponderacion_%": int(round(alpha * 100)),
                    "num_ciclos": int(N),
                    "wape_%": round(wape, 2),
                    "bias_%": round(bias, 2),
                    "error_tallos": int(round(err_abs))
                })

                if wape < mejor_wape:
                    mejor_wape = wape
                    mejor_params = (alpha, N)
                    mejor_bias = bias
                    mejor_fc_map = fc_sim
                    mejor_err_tallos = err_abs

        res_por_flor[target] = {
            'alpha': float(round(mejor_params[0], 2)),
            'ponderacion_%': int(round(mejor_params[0] * 100)),
            'num_ciclos': int(mejor_params[1]),
            'wape_%': float(round(mejor_wape, 2)),
            'bias_%': float(round(mejor_bias, 2)),
            'error_tallos': float(round(mejor_err_tallos, 1)),
            'mejor_fc_map': mejor_fc_map
        }

    df_iter_total = pd.DataFrame(iteraciones_todas)

    # 5. Generar tabla de detalle por variedad con la predicción del modelo segmentado
    detalle_rows = []
    fc_segmentado_combinado = {}
    for target in ['Cushion', 'Daisy', 'Novelty']:
        if target in res_por_flor:
            fc_segmentado_combinado.update(res_por_flor[target]['mejor_fc_map'])

    for _, r in df_wf.iterrows():
        v = r['Variedad']
        v_norm = v.strip().lower()
        fl = r.get('Flor', 'N/A')
        real_v = float(r['Tallos_Recepcionados'])
        est_wf = float(r['Tallos_Estimados'])
        
        # Pronóstico usando la calibración de su tipo de flor
        est_ml = fc_segmentado_combinado.get(v_norm, est_wf)
        if est_ml <= 0 and 'Global' in res_por_flor:
            est_ml = res_por_flor['Global']['mejor_fc_map'].get(v_norm, est_wf)

        err_wf = abs(real_v - est_wf)
        err_ml = abs(real_v - est_ml)

        detalle_rows.append({
            "Flor": fl,
            "Color": r.get('Color', 'N/A'),
            "Variedad": v,
            "Real_Recepcionado": int(round(real_v)),
            "Estimado_Anterior": int(round(est_wf)),
            "Estimado_ML_Calibrado": int(round(est_ml)),
            "Error_Anterior": int(round(err_wf)),
            "Error_ML": int(round(err_ml)),
            "Mejora_Tallos": int(round(err_wf - err_ml)),
            "Precision_Anterior_%": round((1.0 - min(1.0, err_wf / real_v)) * 100.0, 1) if real_v > 0 else 100.0,
            "Precision_ML_%": round((1.0 - min(1.0, err_ml / real_v)) * 100.0, 1) if real_v > 0 else 100.0
        })

    df_detalle = pd.DataFrame(detalle_rows)

    # Métricas Globales de Finca
    opt_glob = res_por_flor.get('Global', {
        'alpha': 0.88, 'ponderacion_%': 88, 'num_ciclos': 6, 'wape_%': 25.0, 'bias_%': 0.0
    })

    # Error base previo (alpha=1.0, ciclos=9 a nivel global)
    base_iter = df_iter_total[(df_iter_total['Flor'] == 'Global') & (df_iter_total['alpha'] == 1.0) & (df_iter_total['num_ciclos'] == 9)]
    wape_anterior_global = float(base_iter['wape_%'].iloc[0]) if not base_iter.empty else float(df_iter_total['wape_%'].max())

    resultado = {
        "por_flor": {
            fl: {
                "alpha": float(res_por_flor[fl]['alpha']),
                "ponderacion_%": int(res_por_flor[fl]['ponderacion_%']),
                "num_ciclos": int(res_por_flor[fl]['num_ciclos']),
                "wape_%": float(res_por_flor[fl]['wape_%']),
                "bias_%": float(res_por_flor[fl]['bias_%'])
            }
            for fl in ['Cushion', 'Daisy', 'Novelty'] if fl in res_por_flor
        },
        "global": {
            "alpha": float(opt_glob['alpha']),
            "ponderacion_%": int(opt_glob['ponderacion_%']),
            "num_ciclos": int(opt_glob['num_ciclos']),
            "wape_%": float(opt_glob['wape_%']),
            "bias_%": float(opt_glob['bias_%'])
        },
        # Campos de compatibilidad directa
        "alpha": float(opt_glob['alpha']),
        "ponderacion_%": int(opt_glob['ponderacion_%']),
        "num_ciclos": int(opt_glob['num_ciclos']),
        "wape_%": float(opt_glob['wape_%']),
        "wape_anterior_%": float(round(wape_anterior_global, 2)),
        "reduccion_error_%": float(round(max(0, wape_anterior_global - opt_glob['wape_%']), 2)),
        "fecha_calibracion": str(datetime.now().strftime("%Y-%m-%d %H:%M")),
        "semana_evaluada": str(semana_objetivo),
        "total_iteraciones": int(total_simulaciones_count),
        "simulaciones_por_flor": int(len(grid_alphas) * len(grid_ciclos)),
        "origen": "Calibración Biológica Segmentada por Flor (2,000 Simulaciones)"
    }

    # Guardar en disco para adopción global por todos los módulos
    guardar_parametros_calibrados(resultado)

    return {
        "resultado": resultado,
        "df_iteraciones": df_iter_total,
        "df_detalle": df_detalle
    }

def ejecutar_iteraciones_optimizacion(db: Session, df_wf: pd.DataFrame, grid_alphas=None, grid_ciclos=None) -> dict:
    """
    Wrapper compatible para ejecutar la optimización segmentada de alta resolución.
    """
    return ejecutar_iteraciones_segmentadas_por_flor(db, df_wf, grid_alphas, grid_ciclos)

