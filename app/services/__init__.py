"""
Storage abstraction layer for Sample Dispenser.
PostgreSQL-only implementation with connection pooling and schema management.
"""

import os
from typing import Optional, Dict, Any, List
from sqlalchemy import create_engine, Engine, inspect
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
import logging

logger = logging.getLogger(__name__)


class StorageBackend:
    """
    PostgreSQL database abstraction providing engine, session factory, and connection validation.
    """

    def __init__(self):
        self.engine: Optional[Engine] = None
        self.SessionLocal: Optional[sessionmaker] = None
        self._initialized = False

    def initialize(self) -> None:
        """
        Initialize PostgreSQL database engine and session factory.
        """
        if self._initialized:
            return

        self._init_postgres()
        self._initialized = True
        logger.info("Storage backend initialized: PostgreSQL")

    def _init_postgres(self) -> None:
        """Initialize PostgreSQL engine with connection pooling."""
        from app.config.postgres import get_sqlalchemy_url, get_pool_config

        database_url = get_sqlalchemy_url()
        pool_config = get_pool_config()

        engine_kwargs = {
            "echo": False,
            "poolclass": QueuePool,
            "pool_size": pool_config["pool_size"],
            "max_overflow": pool_config["max_overflow"],
            "pool_timeout": pool_config["pool_timeout"],
            "pool_recycle": pool_config["pool_recycle"],
            "pool_pre_ping": pool_config["pool_pre_ping"],
        }

        self.engine = create_engine(database_url, **engine_kwargs)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        # Test connection on initialization
        try:
            with self.engine.connect() as conn:
                conn.execute("SELECT 1")
            logger.info("PostgreSQL connection pool successfully initialized")
        except Exception as e:
            logger.error(f"PostgreSQL connection failed: {e}")
            raise
    
    def get_session(self) -> Session:
        """
        Get a new database session.
        Must call initialize() first.
        """
        if not self._initialized:
            self.initialize()
        
        return self.SessionLocal()
    
    def get_engine(self) -> Engine:
        """Get the SQLAlchemy engine."""
        if not self._initialized:
            self.initialize()
        
        return self.engine
    
    def health_check(self) -> bool:
        """
        Verify database connection is healthy.
        """
        try:
            with self.engine.connect() as conn:
                conn.execute("SELECT 1")
            return True
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False
    
    def get_table_columns(self, table_name: str) -> List[str]:
        """
        Get column names for a table (database-agnostic).
        """
        inspector = inspect(self.engine)
        columns = inspector.get_columns(table_name)
        return [col["name"] for col in columns]
    
    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        inspector = inspect(self.engine)
        return table_name in inspector.get_table_names()


# Global instance
_storage_backend: Optional[StorageBackend] = None


def init_storage() -> StorageBackend:
    """
    Initialize and return the global storage backend instance.
    """
    global _storage_backend

    if _storage_backend is None:
        _storage_backend = StorageBackend()
        _storage_backend.initialize()

    return _storage_backend


def get_storage() -> StorageBackend:
    """Get the initialized storage backend instance."""
    global _storage_backend

    if _storage_backend is None:
        return init_storage()

    return _storage_backend


def get_db_session() -> Session:
    """Dependency injection for FastAPI endpoints: get new database session."""
    storage = get_storage()
    db = storage.get_session()
    try:
        yield db
    finally:
        db.close()


if __name__ == "__main__":
    # Debug: test storage initialization
    storage = init_storage()
    print(f"✓ Storage backend initialized")
    print(f"✓ Health check: {storage.health_check()}")

    # List tables
    inspector = inspect(storage.get_engine())
    tables = inspector.get_table_names()
    print(f"✓ Tables: {tables}")
