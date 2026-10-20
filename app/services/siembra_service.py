import os
import glob
import pandas as pd
from datetime import date, timedelta
from sqlalchemy.orm import Session
from app.models.models import Variedad
from app.services.enraizamiento_service import (
    SEMANAS_ENRAIZAMIENTO,
    CAVIDADES_POR_BANDEJA,
    HORAS_JORNADA,
    TOTAL_HORAS_SEMANA_ESTANDAR,
    ARCHIVO_EJECUCION_REAL,
    ARCHIVO_CIERRE_ENRAIZAMIENTO,
    sumar_semanas_iso,
    restar_semanas_iso,
    clasificar_temporada_semana,
    calcular_bandejas_redondeadas,
    calcular_dia_tentativo_enraizamiento,
    nivelar_distribucion_diaria,
    resolver_bloque_tentativo,
    obtener_dimensiones_camas_bloques,
    cargar_ejecucion_real
)

def obtener_catalogo_semanas_siembra(db: Session = None) -> list[dict]:
    """
    Retorna el catálogo completo de semanas de siembra del horizonte productivo,
    identificando de manera estricta cuáles cuentan con EJECUCIÓN REAL de clavado
    en propagación (3 semanas antes) y cuáles se encuentran PENDIENTES / BLOQUEADAS.
    Evita cualquier simulación teórica al 100%.
    """
    semanas_set = set()

    # 1. Semanas del plan maestro detallado
    if os.path.exists("Plan_Aprobado_Detallado.csv"):
        try:
            df_det = pd.read_csv("Plan_Aprobado_Detallado.csv")
            if 'Semana_Siembra' in df_det.columns:
                for s in df_det['Semana_Siembra'].dropna().unique():
                    s_str = str(int(float(s)))
                    if len(s_str) == 6 and s_str.startswith('202'):
                        semanas_set.add(s_str)
        except Exception:
            pass

    # 2. Semanas registradas en el archivo de ejecución real de propagación
    df_ejec = pd.DataFrame()
    if os.path.exists(ARCHIVO_EJECUCION_REAL):
        try:
            df_ejec = pd.read_csv(ARCHIVO_EJECUCION_REAL)
            if not df_ejec.empty and 'Semana_Enraizamiento' in df_ejec.columns:
                df_ejec['Semana_Enraizamiento'] = df_ejec['Semana_Enraizamiento'].astype(str)
                df_ejec['Bandejas_Reales'] = pd.to_numeric(df_ejec.get('Bandejas_Reales', 0), errors='coerce').fillna(0).astype(int)
                df_ejec['Esquejes_Reales'] = pd.to_numeric(df_ejec.get('Esquejes_Reales', 0), errors='coerce').fillna(0).astype(int)
                df_ejec['Camas_Reales'] = pd.to_numeric(df_ejec.get('Camas_Reales', 0.0), errors='coerce').fillna(0.0).astype(float)
                for s_enr in df_ejec['Semana_Enraizamiento'].unique():
                    s_siem = sumar_semanas_iso(str(s_enr), SEMANAS_ENRAIZAMIENTO)
                    semanas_set.add(s_siem)
        except Exception:
            pass

    if not semanas_set:
        semanas_set.add("202646")

    catalogo = []
    for sem_s in sorted(list(semanas_set)):
        sem_e = restar_semanas_iso(sem_s, SEMANAS_ENRAIZAMIENTO)
        sem_c = sumar_semanas_iso(sem_s, 11)
        temp = clasificar_temporada_semana(int(sem_c) if str(sem_c).isdigit() else 202704)

        tiene_ejec = False
        tot_band = 0
        tot_esq = 0
        tot_camas = 0.0
        num_vars = 0

        if not df_ejec.empty:
            grp = df_ejec[df_ejec['Semana_Enraizamiento'] == str(sem_e)]
            if not grp.empty:
                tot_band = int(grp['Bandejas_Reales'].sum())
                tot_esq = int(grp['Esquejes_Reales'].sum())
                tot_camas = round(float(grp['Camas_Reales'].sum()), 1)
                num_vars = int((grp['Bandejas_Reales'] > 0).sum())
                if tot_band > 0:
                    tiene_ejec = True

        if tiene_ejec:
            label = f"Semana S{sem_s[2:]} ({sem_s}) — 🟢 Con Ejecución Real ({tot_camas:.1f} cam., {tot_band:,d} band., {num_vars} vars)"
            estado = "🟢 Con Ejecución Real"
        else:
            label = f"Semana S{sem_s[2:]} ({sem_s}) — 🔴 Sin Ejecución Real en Propagación (Bloqueada)"
            estado = "🔴 Sin Ejecución Real (Bloqueada)"

        catalogo.append({
            "Semana_Siembra": sem_s,
            "Semana_Siembra_Label": f"S{sem_s[2:]}",
            "Semana_Enraizamiento": sem_e,
            "Semana_Enraizamiento_Label": f"S{sem_e[2:]}",
            "Semana_Cosecha": sem_c,
            "Semana_Cosecha_Label": f"S{sem_c[2:]}",
            "Temporada": temp,
            "Tiene_Ejecucion_Real": tiene_ejec,
            "Total_Bandejas_112": tot_band,
            "Total_Esquejes": tot_esq,
            "Total_Camas": tot_camas,
            "Num_Variedades": num_vars,
            "Estado": estado,
            "Label": label
        })

    return catalogo

def obtener_semanas_siembra_disponibles(db: Session = None) -> list[dict]:
    """
    Retorna ÚNICAMENTE las semanas de siembra que cuentan con EJECUCIÓN REAL
    de clavado ingresada y registrada en el módulo de enraizamiento (3 semanas antes).
    No simula semanas teóricas al 100%.
    """
    catalogo = obtener_catalogo_semanas_siembra(db)
    return [s for s in catalogo if s.get('Tiene_Ejecucion_Real', False)]



def generar_plano_siembra_semanal(
    db: Session,
    semana_siembra: str,
    base_capacidad: str = "bloque"
) -> dict:
    """
    Genera el Plano Operativo de Siembra Semanal EXCLUSIVAMENTE a partir de los
    lotes que cuentan con EJECUCIÓN REAL de clavado en propagación (3 semanas antes).
    Si la semana de enraizamiento no tiene ejecución real ingresada (Bandejas_Reales == 0),
    bloquea la generación y retorna un error explícito.
    """
    sem_siembra = str(semana_siembra).strip()
    sem_enraizamiento = restar_semanas_iso(sem_siembra, SEMANAS_ENRAIZAMIENTO)

    # 1. Verificar existencia de Ejecución Real en el archivo maestro
    if not os.path.exists(ARCHIVO_EJECUCION_REAL):
        return {
            "error": "sin_ejecucion_real",
            "mensaje": (
                f"⛔ La semana de siembra {sem_siembra} no puede cargarse porque no existe el archivo de ejecución real de propagación. "
                "El plano de siembra en campo no puede simular un cumplimiento del 100% teórico."
            ),
            "semana_siembra": sem_siembra,
            "semana_enraizamiento": sem_enraizamiento
        }

    df_ejec_all = pd.read_csv(ARCHIVO_EJECUCION_REAL)
    if df_ejec_all.empty or 'Semana_Enraizamiento' not in df_ejec_all.columns:
        return {
            "error": "sin_ejecucion_real",
            "mensaje": (
                f"⛔ La semana de siembra {sem_siembra} no cuenta con registros de ejecución real en propagación."
            ),
            "semana_siembra": sem_siembra,
            "semana_enraizamiento": sem_enraizamiento
        }

    df_ejec_all['Semana_Enraizamiento'] = df_ejec_all['Semana_Enraizamiento'].astype(str)
    df_sem_ejec = df_ejec_all[df_ejec_all['Semana_Enraizamiento'] == str(sem_enraizamiento)].copy()

    if df_sem_ejec.empty:
        return {
            "error": "sin_ejecucion_real",
            "mensaje": (
                f"⛔ **Semana {sem_siembra} sin Ejecución Real:**\n\n"
                f"La semana de enraizamiento origen (**S{sem_enraizamiento[2:]}**) aún no tiene registrada la Ejecución Real de clavado en propagación.\n\n"
                "El sistema **no simula cumplimiento teórico al 100%** para evitar programar en campo plántulas no producidas. "
                f"Por favor ingrese y guarde la ejecución real en **Plan de Enraizamiento (Pestaña 3: Ejecución Real)** para habilitar esta siembra."
            ),
            "semana_siembra": sem_siembra,
            "semana_enraizamiento": sem_enraizamiento
        }

    df_sem_ejec['Bandejas_Reales'] = pd.to_numeric(df_sem_ejec.get('Bandejas_Reales', 0), errors='coerce').fillna(0).astype(int)
    tot_band_ejec = int(df_sem_ejec['Bandejas_Reales'].sum())

    if tot_band_ejec <= 0:
        return {
            "error": "sin_ejecucion_real",
            "mensaje": (
                f"⛔ **Semana {sem_siembra} sin Clavado Real:**\n\n"
                f"La planilla de la semana de enraizamiento **S{sem_enraizamiento[2:]}** figura con **0 bandejas reales clavadas** (estado Pendiente).\n\n"
                "Para emitir el Plano Operativo de Siembra en campo, el líder de propagación debe ingresar las bandejas efectivamente clavadas en **Plan de Enraizamiento (Pestaña 3)**."
            ),
            "semana_siembra": sem_siembra,
            "semana_enraizamiento": sem_enraizamiento
        }

    # 2. Catálogo maestro de BD para enriquecer fenología
    try:
        variedades_db = {v.nombre.strip().lower(): v for v in db.query(Variedad).all()}
    except Exception:
        variedades_db = {}

    dict_dimensiones = obtener_dimensiones_camas_bloques(db)

    # 3. Construir lotes de siembra EXCLUSIVAMENTE a partir de los registros ejecutados reales (> 0)
    lotes_raw = []
    df_ejec_positivas = df_sem_ejec[df_sem_ejec['Bandejas_Reales'] > 0].copy()

    for _, r in df_ejec_positivas.iterrows():
        v_nom = str(r['Variedad']).strip()
        v_low = v_nom.lower()
        v_obj = variedades_db.get(v_low)

        flor = str(r.get('Flor') or (v_obj.flor if v_obj else 'Estándar'))
        color = str(r.get('Color') or (v_obj.color if v_obj else 'Mix'))

        ban_real = int(r['Bandejas_Reales'])
        esq_real = int(r.get('Esquejes_Reales', ban_real * CAVIDADES_POR_BANDEJA))
        if esq_real <= 0:
            esq_real = ban_real * CAVIDADES_POR_BANDEJA

        # Camas reales equivalentes calculadas sobre los esquejes efectivamente disponibles
        camas_real = round(esq_real / 5200.0, 1)

        dp = int(v_obj.dia_pico if (v_obj and v_obj.dia_pico) else 77)
        di = int(v_obj.dia_inicio if (v_obj and v_obj.dia_inicio) else 70)
        aprov = float(v_obj.aprov_pp if (v_obj and v_obj.aprov_pp) else 0.806)

        # Bloque de campo destino
        bloque_dest_orig = str(r.get('Bloque_Destino', '')).strip()
        if not bloque_dest_orig or bloque_dest_orig.lower() in ['nan', 'none', '']:
            bloque_dest_res = resolver_bloque_tentativo(sem_siembra, dict_dimensiones=dict_dimensiones)
            b_code = str(bloque_dest_res[0] if isinstance(bloque_dest_res, tuple) else bloque_dest_res)
            bloque_dest_orig = f"Bloque {b_code}" if not b_code.startswith("Bloque") else b_code

        # Día de la semana asignado
        dia_clav = str(r.get('Dia_Clavado', 'Lunes')).strip()
        if dia_clav not in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]:
            dia_clav = "Lunes"

        sem_c_var = sumar_semanas_iso(sem_siembra, int(round(dp / 7.0)))
        temp_var = clasificar_temporada_semana(int(sem_c_var) if sem_c_var.isdigit() else 202704)

        lotes_raw.append({
            "Flor": flor,
            "Color": color,
            "Variedad": v_nom,
            "Camas_Campo": camas_real,
            "Esquejes": esq_real,
            "Plantas_Sembradas": esq_real,
            "Bandejas_112": ban_real,
            "Bloque_Destino": bloque_dest_orig,
            "Dia_Tentativo": dia_clav,
            "Dia_Programado": dia_clav,
            "Es_Nivelado": False,
            "Dia_Pico": dp,
            "Dia_Inicio": di,
            "Aprov_PP": aprov,
            "Tallos_Esperados": int(round(esq_real * aprov)),
            "Semana_Siembra": sem_siembra,
            "Semana_Enraizamiento": sem_enraizamiento,
            "Semana_Cosecha": sem_c_var,
            "Temporada": temp_var,
            "Es_Extemporaneo": bool(str(r.get('Observaciones', '')).lower().find('extemp') >= 0),
            "Observaciones": "",
            "Ejecutado_Real": ""
        })

    if not lotes_raw:
        return {
            "error": "sin_lotes_ejecutados",
            "mensaje": f"No se encontraron lotes con bandejas reales clavadas para la semana de siembra {sem_siembra}."
        }

    # 4. Nivelación y ordenamiento
    dias_orden = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
    dia_order_map = {d: i for i, d in enumerate(dias_orden)}
    lotes_nivelados = sorted(
        lotes_raw,
        key=lambda x: (dia_order_map.get(x.get('Dia_Programado', 'Lunes'), 9), x['Flor'], x['Variedad'])
    )

    df_plano_detallado = pd.DataFrame(lotes_nivelados)
    tot_camas_sem = float(df_plano_detallado['Camas_Campo'].sum())
    tot_plantas_sem = int(df_plano_detallado['Plantas_Sembradas'].sum())
    tot_bandejas_sem = int(df_plano_detallado['Bandejas_112'].sum())

    # 5. Resumen Diario de Siembra
    res_diario = []
    for d in dias_orden:
        df_d = df_plano_detallado[df_plano_detallado['Dia_Programado'] == d]
        c_d = round(float(df_d['Camas_Campo'].sum()), 1) if not df_d.empty else 0.0
        p_d = int(df_d['Plantas_Sembradas'].sum()) if not df_d.empty else 0
        b_d = int(df_d['Bandejas_112'].sum()) if not df_d.empty else 0
        pct_c = (c_d / tot_camas_sem * 100.0) if tot_camas_sem > 0 else 0.0

        res_diario.append({
            "Día": d,
            "Camas": c_d,
            "Plantas / Esquejes": p_d,
            "Bandejas (112)": b_d,
            "% de la Semana": round(pct_c, 1),
            "Variedades a Sembrar": len(df_d)
        })
    df_resumen_diario = pd.DataFrame(res_diario)

    # 6. Resumen por Bloque de Campo
    grp_b = df_plano_detallado.groupby('Bloque_Destino').agg(
        Camas=('Camas_Campo', 'sum'),
        Plantas=('Plantas_Sembradas', 'sum'),
        Bandejas=('Bandejas_112', 'sum'),
        Variedades=('Variedad', 'count')
    ).reset_index()
    grp_b['Camas'] = grp_b['Camas'].round(1)
    df_resumen_bloques = grp_b.sort_values(by='Camas', ascending=False)

    sem_cosecha_default = sumar_semanas_iso(sem_siembra, 11)
    temporada_default = clasificar_temporada_semana(int(sem_cosecha_default) if sem_cosecha_default.isdigit() else 202704)

    return {
        "semana_siembra": sem_siembra,
        "semana_siembra_label": f"S{sem_siembra[2:]}",
        "semana_enraizamiento": sem_enraizamiento,
        "semana_enraizamiento_label": f"S{sem_enraizamiento[2:]}",
        "semana_cosecha": sem_cosecha_default,
        "semana_cosecha_label": f"S{sem_cosecha_default[2:]}",
        "temporada": temporada_default,
        "df_plano_detallado": df_plano_detallado,
        "df_resumen_diario": df_resumen_diario,
        "df_resumen_bloques": df_resumen_bloques,
        "kpis": {
            "total_camas": round(tot_camas_sem, 1),
            "total_plantas": tot_plantas_sem,
            "total_bandejas": tot_bandejas_sem,
            "num_lotes": len(df_plano_detallado),
            "tallos_esperados": int(df_plano_detallado['Tallos_Esperados'].sum()),
            "bloques_asignados": ", ".join(sorted(df_plano_detallado['Bloque_Destino'].unique().tolist()))
        },
        "tiene_ejecucion_real": True
    }


def generar_pdf_plano_siembra(res_siembra: dict) -> bytes:
    """
    Genera el documento PDF oficial en orientación Horizontal (Landscape)
    con el Plano Operativo de Siembra Semanal para entrega al equipo de campo.
    Garantizado en UNA SOLA HOJA:
    - Encabezado con metadatos reales de Siembra y Enraizamiento certificado.
    - Resumen consolidado de Siembra por Día y Bloque.
    - Tabla detallada de siembra con casillas limpias (sin corchetes ni texto precargado).
    - Casilla de Ejecutado Real limpia para anotación manual de camas reales sembradas.
    - Columna de Observaciones limpia para novedades físicas de campo.
    - Firmas de Aprobación reglamentarias.
    """
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    import io

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=20,
        rightMargin=20,
        topMargin=15,
        bottomMargin=15
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=12.5,
        textColor=colors.HexColor('#1b5e20')
    )

    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor('#37474f'),
        alignment=2
    )

    meta_style = ParagraphStyle(
        'DocMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.2,
        leading=8.8,
        textColor=colors.HexColor('#263238')
    )

    meta_style_right = ParagraphStyle(
        'DocMetaRight',
        parent=meta_style,
        alignment=2
    )

    th_style = ParagraphStyle(
        'THeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=6.8,
        leading=8.2,
        textColor=colors.white,
        alignment=1
    )

    n_rows = len(res_siembra.get('df_plano_detallado', []))
    fs = 6.0 if n_rows > 26 else 6.8
    ld = 7.2 if n_rows > 26 else 8.2
    pad = 0.8 if n_rows > 26 else 1.3

    tc_style = ParagraphStyle(
        'TCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=fs,
        leading=ld,
        textColor=colors.HexColor('#222222')
    )

    tc_bold = ParagraphStyle(
        'TCellBold',
        parent=tc_style,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#111111')
    )

    tc_center = ParagraphStyle(
        'TCellCenter',
        parent=tc_style,
        alignment=1
    )

    tc_center_bold = ParagraphStyle(
        'TCellCenterBold',
        parent=tc_bold,
        alignment=1
    )

    elements = []

    sem_s = res_siembra.get("semana_siembra_label", "S2646")
    sem_e = res_siembra.get("semana_enraizamiento_label", "S2643")
    sem_c = res_siembra.get("semana_cosecha_label", "S2704")
    temp = res_siembra.get("temporada", "San Valentín")
    kpis = res_siembra.get("kpis", {})
    tot_camas = kpis.get("total_camas", 0.0)
    tot_plantas = kpis.get("total_plantas", 0)
    tot_band = kpis.get("total_bandejas", 0)
    today_str = date.today().strftime('%d/%m/%Y')

    # 1. Encabezado Institucional
    header_data = [
        [
            Paragraph("<b>JARDINES DE CHÍA S.A.S. — PLANO OPERATIVO DE SIEMBRA SEMANAL (CAMPO)</b>", title_style),
            Paragraph(f"<b>EMISIÓN REAL CERTIFICADA</b> | Fecha: {today_str}", subtitle_style)
        ],
        [
            Paragraph(
                f"<b>Semana Siembra (Campo):</b> {sem_s} &nbsp;|&nbsp; "
                f"<b>Enraizamiento Real Certificado (-3 sem):</b> {sem_e} &nbsp;|&nbsp; "
                f"<b>Cosecha (+8 sem):</b> {sem_c} &nbsp;|&nbsp; "
                f"<b>Temporada:</b> {temp}",
                meta_style
            ),
            Paragraph(
                f"<b>Total Camas Campo:</b> {tot_camas:.1f} &nbsp;|&nbsp; "
                f"<b>Plantas Reales a Sembrar:</b> {tot_plantas:,d} &nbsp;|&nbsp; "
                f"<b>Bandejas Reales (112):</b> {tot_band:,d}",
                meta_style_right
            )
        ]
    ]
    t_header = Table(header_data, colWidths=[520, 232])
    t_header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
    ]))
    elements.append(t_header)
    elements.append(Spacer(1, 3))

    # 2. Resumen Consolidado de Siembra por Día (Lunes a Sábado)
    df_res_dia = res_siembra.get('df_resumen_diario', pd.DataFrame())
    if not df_res_dia.empty:
        dia_headers = ["Labor / Día"] + df_res_dia['Día'].tolist() + ["TOTAL SEMANA"]
        row_camas = ["Camas Campo"] + [f"{c:.1f}" for c in df_res_dia['Camas']] + [f"{tot_camas:.1f}"]
        row_plantas = ["Plantas / Esq."] + [f"{p:,d}" for p in df_res_dia['Plantas / Esquejes']] + [f"{tot_plantas:,d}"]
        row_bandejas = ["Bandejas (112)"] + [f"{b:,d}" for b in df_res_dia['Bandejas (112)']] + [f"{tot_band:,d}"]

        summary_table_data = [
            [Paragraph(f"<b>{h}</b>", th_style) for h in dia_headers],
            [Paragraph(f"<b>{c}</b>" if idx in [0, 7] else c, tc_center_bold if idx in [0, 7] else tc_center) for idx, c in enumerate(row_camas)],
            [Paragraph(f"<b>{c}</b>" if idx in [0, 7] else c, tc_center_bold if idx in [0, 7] else tc_center) for idx, c in enumerate(row_plantas)],
            [Paragraph(f"<b>{c}</b>" if idx in [0, 7] else c, tc_center_bold if idx in [0, 7] else tc_center) for idx, c in enumerate(row_bandejas)],
        ]
        t_summary = Table(summary_table_data, colWidths=[92, 80, 80, 80, 80, 80, 80, 80])
        t_summary.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2e7d32')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#b0bec5')),
            ('TOPPADDING', (0, 0), (-1, -1), 1.2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1.2),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f1f8e9')),
            ('BACKGROUND', (-1, 1), (-1, -1), colors.HexColor('#e8f5e9')),
        ]))
        elements.append(t_summary)
        elements.append(Spacer(1, 3))

    # 3. Plano Detallado de Siembra
    df_det = res_siembra.get("df_plano_detallado", pd.DataFrame())
    if not df_det.empty:
        det_cols = [
            "Día Prog.", "Flor", "Color", "Variedad", 
            "Camas", "Plantas / Esq.", "Bandejas", "Bloque Campo", 
            "Sem. Cosecha", "Ejecutado Real", "Observaciones"
        ]
        table_data = [[Paragraph(f"<b>{c}</b>", th_style) for c in det_cols]]

        for _, r in df_det.iterrows():
            dia_txt = str(r['Dia_Programado'])
            if r.get('Es_Nivelado', False):
                dia_txt += " *"

            var_txt = str(r['Variedad'])
            es_ext = r.get('Es_Extemporaneo', False)
            if es_ext:
                var_txt += " <i>(Extemp.)</i>"

            cam_val = float(r['Camas_Campo'])
            pla_val = int(r['Plantas_Sembradas'])
            ban_val = int(r['Bandejas_112'])

            table_data.append([
                Paragraph(dia_txt, tc_style),
                Paragraph(str(r['Flor']), tc_style),
                Paragraph(str(r['Color']), tc_style),
                Paragraph(f"<b>{var_txt}</b>", tc_bold),
                Paragraph(f"{cam_val:.1f}", tc_center),
                Paragraph(f"{pla_val:,d}", tc_center),
                Paragraph(f"{ban_val:,d}", tc_center),
                Paragraph(str(r.get('Bloque_Destino', 'Bloque 01')), tc_center),
                Paragraph(f"S{str(r['Semana_Cosecha'])[2:]}", tc_center),
                Paragraph("", tc_center),  # Casilla limpia para anotación manual de camas reales
                Paragraph("", tc_style),   # Observaciones limpias para novedades físicas de campo
            ])

        # Fila de Totales
        table_data.append([
            Paragraph("<b>TOTAL GENERAL</b>", tc_bold),
            Paragraph("-", tc_center),
            Paragraph("-", tc_center),
            Paragraph(f"<b>{len(df_det)} Variedades</b>", tc_bold),
            Paragraph(f"<b>{tot_camas:.1f}</b>", tc_center_bold),
            Paragraph(f"<b>{tot_plantas:,d}</b>", tc_center_bold),
            Paragraph(f"<b>{tot_band:,d}</b>", tc_center_bold),
            Paragraph("-", tc_center),
            Paragraph("-", tc_center),
            Paragraph("", tc_center),
            Paragraph("", tc_center),
        ])

        # Anchos de columna (total: 752 pt)
        t_det = Table(table_data, colWidths=[48, 44, 44, 134, 44, 56, 48, 56, 48, 70, 160], repeatRows=1)
        t_det.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1b5e20')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cfd8dc')),
            ('TOPPADDING', (0, 0), (-1, -1), pad),
            ('BOTTOMPADDING', (0, 0), (-1, -1), pad),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f9fbe7')]),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8f5e9')),
            ('LINEABOVE', (0, -1), (-1, -1), 1.0, colors.HexColor('#1b5e20')),
        ]))
        elements.append(t_det)
        elements.append(Spacer(1, 3))

    # Nota Operativa
    nota_style = ParagraphStyle(
        'NotaSiembra',
        parent=meta_style,
        fontName='Helvetica-Oblique',
        fontSize=6.5,
        leading=8.0,
        textColor=colors.HexColor('#1b5e20')
    )
    elements.append(Paragraph(
        "<b>* NOTA OPERATIVA:</b> Este plano de siembra se genera exclusivamente a partir de las plántulas efectivamente enraizadas "
        f"y certificadas en la semana {sem_e}. Las casillas 'Ejecutado Real' y 'Observaciones' deben ser diligenciadas a mano por el líder de siembra.",
        nota_style
    ))
    elements.append(Spacer(1, 2))

    # 4. Pie de Control y Firmas
    sig_data = [
        [
            Paragraph("<b>Elaboró (Planeación S&OP):</b> ______________________ Firma", meta_style),
            Paragraph("<b>Recibió (Líder Siembra Campo):</b> ______________________ Firma", meta_style),
            Paragraph("<b>Validó (Jefatura Producción):</b> ______________________ Firma", meta_style),
        ]
    ]
    t_sig = Table(sig_data, colWidths=[250, 250, 252])
    t_sig.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
    ]))
    elements.append(t_sig)

    doc.build(elements)
    return buffer.getvalue()
