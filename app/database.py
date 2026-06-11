from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import get_settings

settings = get_settings()

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _sqlite_add_column_if_missing(table: str, column: str, col_def: str):
    if not settings.database_url.startswith("sqlite"):
        return
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"PRAGMA table_info({table})"))
            cols = [row[1] for row in result]
            if column not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"))
                conn.commit()
    except Exception:
        pass


def run_migrations():
    _sqlite_add_column_if_missing("render_jobs", "fileCount", "INTEGER")
    _sqlite_add_column_if_missing("render_jobs", "outputFormat", "VARCHAR DEFAULT 'pdf'")
    _sqlite_add_column_if_missing("render_jobs", "pdfVariant", "VARCHAR")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
