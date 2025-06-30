import os
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, Engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from loguru import logger
from .models import Base

class DatabaseManager:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = self._create_engine()
        self.session_factory = sessionmaker(bind=self.engine)
    
    def _create_engine(self) -> Engine:
        return create_engine(
            self.database_url,
            poolclass=QueuePool,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False
        )
    
    def create_tables(self):
        try:
            Base.metadata.create_all(self.engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating database tables: {e}")
            raise
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    def test_connection(self) -> bool:
        try:
            with self.get_session() as session:
                session.execute(text("SELECT 1"))
                logger.info("Database connection test successful")
                return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False
    
    def close(self):
        self.engine.dispose()
        logger.info("Database connection closed")

# Global database manager instance
_db_manager = None

def get_database_manager() -> DatabaseManager:
    global _db_manager
    if _db_manager is None:
        database_url = os.getenv('DATABASE_URL', 'postgresql://admin:sports_science_password@localhost:5432/sports_science')
        _db_manager = DatabaseManager(database_url)
    return _db_manager

@contextmanager
def get_session() -> Generator[Session, None, None]:
    db_manager = get_database_manager()
    with db_manager.get_session() as session:
        yield session