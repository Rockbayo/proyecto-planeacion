from sqlalchemy import Column, Integer, String, Float, Boolean, Date, ForeignKey, Enum
from sqlalchemy.orm import relationship
import enum
from app.core.database import Base

class EstadoSiembra(enum.Enum):
    PROGRAMADA = "Programada"
    ENRAIZAMIENTO = "Enraizamiento"
    EN_PRODUCCION = "En Produccion"
    TERMINADO = "Terminado"

class Variedad(Base):
    __tablename__ = "variedades"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, unique=True, index=True, nullable=False)
    flor = Column(String, index=True, nullable=False)   # Ej: Cushion, Daisy, Novelty
    color = Column(String, nullable=False)
    
    # Tiempos fenolgicos (Das)
    dia_inicio = Column(Integer, nullable=False, default=0)
    dia_pico = Column(Integer, nullable=False, default=0)
    dias_desb = Column(Integer, nullable=False, default=0)
    
    # Rendimiento esperado general
    aprov_pp = Column(Float, nullable=False, default=1.0) # Ej: 0.95 (95%)
    
    # Curva de extraccin histrica (Porcentajes semanales C1 a C15)
    c1 = Column(Float, default=0.0)
    c2 = Column(Float, default=0.0)
    c3 = Column(Float, default=0.0)
    c4 = Column(Float, default=0.0)
    c5 = Column(Float, default=0.0)
    c6 = Column(Float, default=0.0)
    c7 = Column(Float, default=0.0)
    c8 = Column(Float, default=0.0)
    c9 = Column(Float, default=0.0)
    c10 = Column(Float, default=0.0)
    c11 = Column(Float, default=0.0)
    c12 = Column(Float, default=0.0)
    c13 = Column(Float, default=0.0)
    c14 = Column(Float, default=0.0)
    c15 = Column(Float, default=0.0)

    activo = Column(Boolean, default=True) # Para cuando el comit (Acta INV) las retira del MVA

    siembras = relationship("Siembra", back_populates="variedad")


class Ubicacion(Base):
    __tablename__ = "ubicaciones"

    id = Column(Integer, primary_key=True, index=True)
    sede = Column(String, nullable=False, default="CH")
    bloque = Column(String, nullable=False)
    nave = Column(String, nullable=False)
    lado = Column(String, nullable=False)
    cama = Column(String, nullable=False)
    
    # Variables fsicas
    area_m2 = Column(Float, nullable=False)
    capacidad_plantas = Column(Integer, nullable=False) # Calculado a partir de la densidad estndar
    
    siembras = relationship("Siembra", back_populates="ubicacion")


class Siembra(Base):
    """
    Representa un 'Lote' o un ciclo especfico sembrado en una cama (Datos_Campo / Siembra Actual).
    """
    __tablename__ = "siembras"

    id = Column(Integer, primary_key=True, index=True)
    ubicacion_id = Column(Integer, ForeignKey("ubicaciones.id"), nullable=False)
    variedad_id = Column(Integer, ForeignKey("variedades.id"), nullable=False)
    
    fecha_siembra = Column(Date, nullable=False)
    plantas_sembradas = Column(Integer, nullable=False)
    plantas_muertas = Column(Integer, default=0)
    
    # El estado avanza a medida que pasa el tiempo
    estado = Column(Enum(EstadoSiembra), default=EstadoSiembra.PROGRAMADA)

    ubicacion = relationship("Ubicacion", back_populates="siembras")
    variedad = relationship("Variedad", back_populates="siembras")
    cortes = relationship("RegistroCorte", back_populates="siembra", cascade="all, delete")
    perdidas = relationship("RegistroPerdida", back_populates="siembra", cascade="all, delete")


class RegistroCorte(Base):
    """
    Guarda la extraccin real de tallos por cada semana del ciclo (Corte 1 a Corte 15)
    Esto alimenta el reclculo de los ndices de la curva de variedad.
    """
    __tablename__ = "registros_cortes"

    id = Column(Integer, primary_key=True, index=True)
    siembra_id = Column(Integer, ForeignKey("siembras.id"), nullable=False)
    
    semana_corte = Column(Integer, nullable=False) # 1, 2, ..., 15
    tallos_recolectados = Column(Integer, nullable=False, default=0)

    siembra = relationship("Siembra", back_populates="cortes")


class RegistroPerdida(Base):
    """
    Guarda las prdidas por factores cualitativos (Torcidos, Trips, Acaros, etc).
    Esto es vital para recalcular el % APROV de la variedad.
    """
    __tablename__ = "registros_perdidas"

    id = Column(Integer, primary_key=True, index=True)
    siembra_id = Column(Integer, ForeignKey("siembras.id"), nullable=False)
    
    causa = Column(String, nullable=False) # Ej: "Torcidos", "Mecanico", "Trips"
    cantidad = Column(Integer, nullable=False, default=0)

    siembra = relationship("Siembra", back_populates="perdidas")

