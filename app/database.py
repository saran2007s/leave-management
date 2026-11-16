from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# SQLite database file stored in the project root
DATABASE_URL = "sqlite:///./leave.db"

# check_same_thread=False is required by SQLite when used with FastAPI
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


# Enable SQLite foreign key enforcement on every connection
@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# Session factory used to create a fresh DB session per request
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Base class for all SQLAlchemy 2.x ORM models
class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency that provides a DB session and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()