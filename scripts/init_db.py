import sys
import os

# Aadir el directorio raz al path para poder importar 'app'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import engine, Base
from app.models import models

def init_db():
    print("Creando tablas en la base de datos local SQLite (planeacion.db)...")
    Base.metadata.create_all(bind=engine)
    print("Base de datos inicializada exitosamente con el esquema relacional S&OP.")

if __name__ == "__main__":
    init_db()

