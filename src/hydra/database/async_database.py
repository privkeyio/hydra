"""Async database operations using asyncpg for PostgreSQL and aiosqlite for SQLite."""

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Try to import database drivers
try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False
    logger.warning("asyncpg not installed, PostgreSQL support disabled")

try:
    import aiosqlite
    AIOSQLITE_AVAILABLE = True
except ImportError:
    AIOSQLITE_AVAILABLE = False
    logger.warning("aiosqlite not installed, SQLite support disabled")


class AsyncDatabasePool:
    """Async database connection pool manager."""

    def __init__(
        self,
        database_url: str,
        min_connections: int = 10,
        max_connections: int = 20
    ):
        self.database_url = database_url
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.pool = None
        self.db_type = self._determine_db_type(database_url)

    def _determine_db_type(self, url: str) -> str:
        """Determine database type from URL."""
        if url.startswith("postgresql://") or url.startswith("postgres://"):
            return "postgresql"
        elif url.startswith("sqlite://"):
            return "sqlite"
        else:
            raise ValueError(f"Unsupported database URL: {url}")

    async def connect(self):
        """Create connection pool."""
        if self.db_type == "postgresql":
            if not ASYNCPG_AVAILABLE:
                raise RuntimeError("asyncpg is required for PostgreSQL support")

            # Parse PostgreSQL URL
            import urllib.parse
            parsed = urllib.parse.urlparse(self.database_url)

            self.pool = await asyncpg.create_pool(
                host=parsed.hostname,
                port=parsed.port or 5432,
                user=parsed.username,
                password=parsed.password,
                database=parsed.path[1:],  # Remove leading /
                min_size=self.min_connections,
                max_size=self.max_connections,
                command_timeout=60
            )
        elif self.db_type == "sqlite":
            if not AIOSQLITE_AVAILABLE:
                raise RuntimeError("aiosqlite is required for SQLite support")

            # For SQLite, we'll manage connections differently
            db_path = self.database_url.replace("sqlite:///", "")
            self.pool = db_path  # Store path, create connections on demand

    async def close(self):
        """Close connection pool."""
        if self.db_type == "postgresql" and self.pool:
            await self.pool.close()

    @asynccontextmanager
    async def acquire(self):
        """Acquire a database connection."""
        if self.db_type == "postgresql":
            async with self.pool.acquire() as conn:
                yield AsyncPostgreSQLConnection(conn)
        elif self.db_type == "sqlite":
            # For SQLite, create a new connection each time
            conn = await aiosqlite.connect(self.pool)
            try:
                yield AsyncSQLiteConnection(conn)
            finally:
                await conn.close()


class AsyncPostgreSQLConnection:
    """Wrapper for asyncpg connection with common operations."""

    def __init__(self, conn):
        self.conn = conn

    async def execute(self, query: str, *args) -> str:
        """Execute a query that doesn't return results."""
        return await self.conn.execute(query, *args)

    async def fetch(self, query: str, *args) -> List[Dict[str, Any]]:
        """Fetch multiple rows."""
        rows = await self.conn.fetch(query, *args)
        return [dict(row) for row in rows]

    async def fetchone(self, query: str, *args) -> Optional[Dict[str, Any]]:
        """Fetch a single row."""
        row = await self.conn.fetchrow(query, *args)
        return dict(row) if row else None

    async def fetchval(self, query: str, *args) -> Any:
        """Fetch a single value."""
        return await self.conn.fetchval(query, *args)

    async def transaction(self):
        """Start a transaction."""
        return self.conn.transaction()


class AsyncSQLiteConnection:
    """Wrapper for aiosqlite connection with common operations."""

    def __init__(self, conn):
        self.conn = conn
        self.conn.row_factory = aiosqlite.Row

    async def execute(self, query: str, *args) -> None:
        """Execute a query that doesn't return results."""
        await self.conn.execute(query, args)
        await self.conn.commit()

    async def fetch(self, query: str, *args) -> List[Dict[str, Any]]:
        """Fetch multiple rows."""
        cursor = await self.conn.execute(query, args)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def fetchone(self, query: str, *args) -> Optional[Dict[str, Any]]:
        """Fetch a single row."""
        cursor = await self.conn.execute(query, args)
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def fetchval(self, query: str, *args) -> Any:
        """Fetch a single value."""
        cursor = await self.conn.execute(query, args)
        row = await cursor.fetchone()
        return row[0] if row else None

    @asynccontextmanager
    async def transaction(self):
        """Start a transaction."""
        await self.conn.execute("BEGIN")
        try:
            yield
            await self.conn.commit()
        except Exception:
            await self.conn.rollback()
            raise


class AsyncTicketDatabase:
    """Async database operations for tickets."""

    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or os.getenv(
            "DATABASE_URL",
            "sqlite:///hydra.db"
        )
        self.pool = AsyncDatabasePool(self.database_url)

    async def connect(self):
        """Initialize database connection."""
        await self.pool.connect()
        await self._create_tables()

    async def close(self):
        """Close database connection."""
        await self.pool.close()

    async def _create_tables(self):
        """Create tables if they don't exist."""
        async with self.pool.acquire() as conn:
            # Create projects table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) UNIQUE NOT NULL,
                    description TEXT,
                    repository_url VARCHAR(500),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    settings JSON DEFAULT '{}'
                )
            """)

            # Create tickets table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    id SERIAL PRIMARY KEY,
                    project_id INTEGER REFERENCES projects(id),
                    ticket_number VARCHAR(20),
                    title VARCHAR(500) NOT NULL,
                    description TEXT,
                    status VARCHAR(50) DEFAULT 'TODO',
                    priority INTEGER DEFAULT 5,
                    complexity VARCHAR(50),
                    model VARCHAR(50),
                    dependencies JSON DEFAULT '[]',
                    acceptance_criteria JSON DEFAULT '[]',
                    artifacts JSON DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    metadata JSON DEFAULT '{}',
                    UNIQUE(project_id, ticket_number)
                )
            """)

            # Create indexes
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ticket_status ON tickets(status)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ticket_priority ON tickets(priority)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ticket_project_status "
                "ON tickets(project_id, status)"
            )

    async def create_ticket(self, ticket_data: Dict[str, Any]) -> int:
        """Create a new ticket."""
        async with self.pool.acquire() as conn:
            query = """
                INSERT INTO tickets (
                    project_id, ticket_number, title, description, 
                    status, priority, complexity, model,
                    dependencies, acceptance_criteria, artifacts, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                RETURNING id
            """

            ticket_id = await conn.fetchval(
                query,
                ticket_data.get("project_id", 1),
                ticket_data["ticket_number"],
                ticket_data["title"],
                ticket_data.get("description", ""),
                ticket_data.get("status", "TODO"),
                ticket_data.get("priority", 5),
                ticket_data.get("complexity"),
                ticket_data.get("model"),
                json.dumps(ticket_data.get("dependencies", [])),
                json.dumps(ticket_data.get("acceptance_criteria", [])),
                json.dumps(ticket_data.get("artifacts", [])),
                json.dumps(ticket_data.get("metadata", {}))
            )

            return ticket_id

    async def update_ticket_status(
        self,
        ticket_number: str,
        status: str,
        project_id: int = 1
    ):
        """Update ticket status."""
        async with self.pool.acquire() as conn:
            query = """
                UPDATE tickets 
                SET status = $1, updated_at = $2
                WHERE ticket_number = $3 AND project_id = $4
            """

            await conn.execute(
                query,
                status,
                datetime.utcnow(),
                ticket_number,
                project_id
            )

    async def get_ticket(
        self,
        ticket_number: str,
        project_id: int = 1
    ) -> Optional[Dict[str, Any]]:
        """Get a ticket by number."""
        async with self.pool.acquire() as conn:
            query = """
                SELECT * FROM tickets 
                WHERE ticket_number = $1 AND project_id = $2
            """

            return await conn.fetchone(query, ticket_number, project_id)

    async def get_all_tickets(
        self,
        project_id: int = 1,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all tickets, optionally filtered by status."""
        async with self.pool.acquire() as conn:
            if status:
                query = """
                    SELECT * FROM tickets 
                    WHERE project_id = $1 AND status = $2
                    ORDER BY priority, created_at
                """
                return await conn.fetch(query, project_id, status)
            else:
                query = """
                    SELECT * FROM tickets 
                    WHERE project_id = $1
                    ORDER BY priority, created_at
                """
                return await conn.fetch(query, project_id)

    async def batch_update_tickets(
        self,
        updates: List[Dict[str, Any]]
    ):
        """Batch update multiple tickets efficiently."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for update in updates:
                    query = """
                        UPDATE tickets 
                        SET status = $1, updated_at = $2
                        WHERE ticket_number = $3 AND project_id = $4
                    """

                    await conn.execute(
                        query,
                        update["status"],
                        datetime.utcnow(),
                        update["ticket_number"],
                        update.get("project_id", 1)
                    )
