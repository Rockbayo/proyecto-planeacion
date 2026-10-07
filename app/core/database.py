from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Configuracin de la Base de Datos Local SQLite
# "check_same_thread": False es necesario para FastAPI/Streamlit con SQLite
SQLALCHEMY_DATABASE_URL = "sqlite:///./data/planeacion.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

