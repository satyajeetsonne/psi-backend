"""
PostgreSQL Database Module for Neon
Handles connection pooling and schema initialization
"""

import os
import logging
import psycopg2
from psycopg2 import sql, pool
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Get DATABASE_URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")

# Create connection pool
try:
    connection_pool = psycopg2.pool.SimpleConnectionPool(
        1,  # min connection
        20,  # max connection for serverless
        DATABASE_URL,
        connect_timeout=5
    )
except Exception as e:
    logger.error(f"Failed to create connection pool: {e}")
    raise


@contextmanager
def get_db_connection():
    """Get a connection from the pool."""
    conn = None
    try:
        conn = connection_pool.getconn()
        yield conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        if conn:
            connection_pool.putconn(conn, close=True)
        raise
    finally:
        if conn:
            connection_pool.putconn(conn)


def init_db():
    """Initialize database tables."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Create outfits table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS outfits (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    image_path TEXT NOT NULL,
                    image_filename TEXT,
                    name TEXT,
                    tags TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    analysis_status TEXT DEFAULT 'pending',
                    analysis_results TEXT
                );
            """)
            
            # Create index for user_id
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_outfits_user_id 
                ON outfits(user_id);
            """)
            
            # Create favorites table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS favorites (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    outfit_id TEXT NOT NULL REFERENCES outfits(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, outfit_id)
                );
            """)
            
            # Create index for favorites
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_favorites_user_id 
                ON favorites(user_id);
            """)
            
            conn.commit()
            logger.info("Database tables initialized successfully")
            
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


def execute_query(query: str, params: tuple = None, fetch: bool = False):
    """Execute a database query."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            
            if fetch:
                result = cursor.fetchall()
            else:
                result = None
            
            conn.commit()
            return result
            
    except Exception as e:
        logger.error(f"Database query error: {e}")
        raise


def execute_query_one(query: str, params: tuple = None):
    """Execute a query and fetch one result."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            result = cursor.fetchone()
            return result
            
    except Exception as e:
        logger.error(f"Database query error: {e}")
        raise
