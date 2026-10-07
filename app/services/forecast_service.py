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
                    
    if not forecast_records:
        return pd.DataFrame()
        
    # Convertir a DataFrame
    df = pd.DataFrame(forecast_records)
    
    # 4. Agrupar la informacin para replicar la visibilidad de la matriz ForeCast
    # Agrupamos por Semana de Cosecha, Flor y Variedad
    df_pivot = pd.pivot_table(
        df, 
        values='Tallos_Proyectados', 
        index=['Sede', 'Flor', 'Color', 'Variedad'], 
        columns=['Semana_Cosecha'], 
        aggfunc='sum',
        fill_value=0
    ).reset_index()
    
    return df_pivot

