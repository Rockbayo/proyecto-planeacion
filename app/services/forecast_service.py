from datetime import timedelta, date
from sqlalchemy.orm import Session
import pandas as pd
from app.models.models import Siembra, Variedad, EstadoSiembra

def isocalendar_to_string(dt: date) -> str:
    """Convierte una fecha a formato AioSemana (ej. 202639).
    Se suma 1 dia para que el Domingo sea considerado el primer dia de la semana operativa."""
    dt_shifted = dt + timedelta(days=1)
    iso_year, iso_week, _ = dt_shifted.isocalendar()
    return f"{iso_year}{iso_week:02d}"

def generar_forecast_13wk(db: Session, start_date: date = None):
    """
    Calcula el ForeCast a 10 Semanas Mviles para todos los lotes en produccin.
    Cruza el inventario de plantas vivas con la curva productiva de cada variedad.
    """
    if not start_date:
        start_date = date.today()
        
    siembras = db.query(Siembra).filter(Siembra.estado == EstadoSiembra.EN_PRODUCCION).all()
    
    forecast_records = []
    
    for siembra in siembras:
        var = siembra.variedad
        ubi = siembra.ubicacion
        
        # 1. Cundo empieza a botar flor este lote?
        # fecha_siembra + dia_inicio (de la variedad)
        fecha_inicio_cosecha = siembra.fecha_siembra + timedelta(days=var.dia_inicio)
        
        # Extraer las curvas (15 semanas)
        curvas = [
            var.c1, var.c2, var.c3, var.c4, var.c5, 
            var.c6, var.c7, var.c8, var.c9, var.c10, 
            var.c11, var.c12, var.c13, var.c14, var.c15
        ]
        
        # 2. Distribuir la cosecha a lo largo de los 15 días de corte
        for dia_indice, porcentaje_cosecha in enumerate(curvas):
            if porcentaje_cosecha and porcentaje_cosecha > 0:
                # Calcular la fecha exacta de ese día de cosecha
                fecha_corte_dia = fecha_inicio_cosecha + timedelta(days=dia_indice)
                
                # Convertirla al formato operativo de planeacion (ej: "202641") para agrupar por semana
                semana_operativa = isocalendar_to_string(fecha_corte_dia)
                
                # 3. Lógica Core de S&OP: Plantas sembradas * índice del día de vida (C1..C15 ya contiene el rendimiento/aprovechamiento)
                tallos_esperados = siembra.plantas_sembradas * porcentaje_cosecha
                
                if tallos_esperados > 0:
                    forecast_records.append({
                        "Sede": ubi.sede,
                        "Bloque": ubi.bloque,
                        "Cama": ubi.cama,
                        "Flor": var.flor,
                        "Color": var.color,
                        "Variedad": var.nombre,
                        "Semana_Siembra": isocalendar_to_string(siembra.fecha_siembra),
                        "Semana_Cosecha": semana_operativa,
                        "Tallos_Proyectados": int(tallos_esperados)
                    })
                    
    # Convertir a DataFrame
    if forecast_records:
        df = pd.DataFrame(forecast_records)
        df_pivot = pd.pivot_table(
            df, 
            values='Tallos_Proyectados', 
            index=['Sede', 'Flor', 'Color', 'Variedad'], 
            columns=['Semana_Cosecha'], 
            aggfunc='sum',
            fill_value=0
        ).reset_index()
    else:
        df_pivot = pd.DataFrame()
        
    # Obtener TODAS las variedades de la base de datos para no omitir ninguna
    todas_variedades = db.query(Variedad).all()
    lista_vars = []
    for v in todas_variedades:
        lista_vars.append({
            "Sede": "",
            "Flor": v.flor,
            "Color": v.color,
            "Variedad": v.nombre
        })
    df_todas = pd.DataFrame(lista_vars)
    
    if not df_pivot.empty:
        # Hacemos un merge para asegurarnos de que TODAS esten
        # Utilizamos on=['Flor', 'Color', 'Variedad'] y un outer join o right join
        df_final = pd.merge(df_todas, df_pivot, on=['Flor', 'Color', 'Variedad'], how='left', suffixes=('_orig', ''))
        # Para la Sede, preferimos la que ya tenia proyeccion, si no, dejamos la original ("")
        if 'Sede' in df_final.columns and 'Sede_orig' in df_final.columns:
            df_final['Sede'] = df_final['Sede'].fillna(df_final['Sede_orig'])
            df_final = df_final.drop(columns=['Sede_orig'])
        df_final = df_final.fillna(0)
    else:
        df_final = df_todas
        
    return df_final


def calcular_distribucion_diaria_curvas(db: Session):
    """
    Calcula el porcentaje de distribucion diaria de cosecha (Lunes a Domingo)
    agrupado por Flor. Se basa en el cruce del inventario vivo y las curvas
    de las variedades (para los proximos 90 dias).
    """
    start_date = date.today()
    siembras = db.query(Siembra).filter(Siembra.estado == EstadoSiembra.EN_PRODUCCION).all()
    
    records = []
    for siembra in siembras:
        var = siembra.variedad
        
        fecha_inicio_cosecha = siembra.fecha_siembra + timedelta(days=var.dia_inicio)
        curvas = [var.c1, var.c2, var.c3, var.c4, var.c5, var.c6, var.c7, var.c8, var.c9, var.c10, var.c11, var.c12, var.c13, var.c14, var.c15]
        
        for dia_indice, porcentaje_cosecha in enumerate(curvas):
            if porcentaje_cosecha and porcentaje_cosecha > 0:
                fecha_corte_dia = fecha_inicio_cosecha + timedelta(days=dia_indice)
                
                # Solo los proximos 90 dias
                if fecha_corte_dia >= start_date and (fecha_corte_dia - start_date).days <= 90:
                    tallos_esperados = siembra.plantas_sembradas * porcentaje_cosecha
                    if tallos_esperados > 0:
                        records.append({
                            "Flor": var.flor,
                            "Weekday": fecha_corte_dia.weekday(), # 0=Mon, 1=Tue... 6=Sun
                            "Tallos": tallos_esperados
                        })

    if not records:
        return {}
        
    df = pd.DataFrame(records)
    df_agrupado = df.groupby(["Flor", "Weekday"])["Tallos"].sum().reset_index()
    df_totales = df_agrupado.groupby("Flor")["Tallos"].sum().reset_index().rename(columns={"Tallos": "Total"})
    
    df_calc = pd.merge(df_agrupado, df_totales, on="Flor")
    df_calc["Pct"] = (df_calc["Tallos"] / df_calc["Total"]) * 100
    
    df_pivot = df_calc.pivot(index="Flor", columns="Weekday", values="Pct").fillna(0)
    
    dias_nombres = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
    df_pivot = df_pivot.rename(columns=dias_nombres)
    
    # Asegurar que existan todas las columnas
    for dia in dias_nombres.values():
        if dia not in df_pivot.columns:
            df_pivot[dia] = 0.0
            
    # Reordenar columnas
    df_pivot = df_pivot[["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]]
    
    # Convertir a dict { "Cushion": {"Lunes": 14.5, ...}, ... }
    return df_pivot.to_dict(orient="index")
