"""Database models and configuration for Hydra dashboard."""

import os
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.pool import StaticPool

Base = declarative_base()


class Project(Base):
    """Project model for managing multiple Hydra projects."""

    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True, nullable=False)
    description = Column(Text)
    repository_url = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    settings = Column(JSON, default=dict)

    tickets = relationship(
        "Ticket", back_populates="project", cascade="all, delete-orphan"
    )
    sessions = relationship(
        "Session", back_populates="project", cascade="all, delete-orphan"
    )


class Ticket(Base):
    """Ticket model for tracking work items."""

    __tablename__ = "tickets"

    # Add table-level constraints and indexes for performance
    __table_args__ = (
        UniqueConstraint("project_id", "ticket_number", name="uq_project_ticket"),
        Index("idx_ticket_status", "status"),
        Index("idx_ticket_priority", "priority"),
        Index("idx_ticket_model", "model"),
        Index("idx_ticket_dates", "created_at", "completed_at"),
        Index("idx_ticket_project_status", "project_id", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    ticket_number = Column(String(20), index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    status = Column(String(50), default="TODO", index=True)
    priority = Column(Integer, default=5)
    complexity = Column(String(50))
    model = Column(String(50))
    dependencies = Column(JSON, default=list)
    acceptance_criteria = Column(JSON, default=list)
    artifacts = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    ticket_metadata = Column(JSON, default=dict)

    project = relationship("Project", back_populates="tickets")
    executions = relationship(
        "Execution", back_populates="ticket", cascade="all, delete-orphan"
    )

    # Enhanced relationships for dependencies and artifacts
    dependencies_as_parent = relationship(
        "TicketDependency",
        foreign_keys="TicketDependency.parent_ticket_id",
        back_populates="parent_ticket",
        cascade="all, delete-orphan",
    )
    dependencies_as_child = relationship(
        "TicketDependency",
        foreign_keys="TicketDependency.depends_on_ticket_id",
        back_populates="depends_on_ticket",
        cascade="all, delete-orphan",
    )
    ticket_artifacts = relationship(
        "TicketArtifact", back_populates="ticket", cascade="all, delete-orphan"
    )


class Session(Base):
    """Session model for tracking agent execution sessions."""

    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    session_id = Column(String(100), unique=True, index=True)
    agent_type = Column(String(50))
    status = Column(String(50), default="active")
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime)
    context = Column(JSON, default=dict)
    metrics = Column(JSON, default=dict)

    project = relationship("Project", back_populates="sessions")
    executions = relationship(
        "Execution", back_populates="session", cascade="all, delete-orphan"
    )


class Execution(Base):
    """Execution model for tracking individual ticket executions."""

    __tablename__ = "executions"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"))
    status = Column(String(50), default="running")
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    duration_seconds = Column(Integer)
    tokens_used = Column(Integer)
    cost_estimate = Column(String(20))
    output = Column(Text)
    error = Column(Text)
    commands_executed = Column(JSON, default=list)
    files_modified = Column(JSON, default=list)

    ticket = relationship("Ticket", back_populates="executions")
    session = relationship("Session", back_populates="executions")


class User(Base):
    """User model for authentication and authorization."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    api_key = Column(String(255), unique=True, index=True)
    settings = Column(JSON, default=dict)

    audit_logs = relationship(
        "AuditLog", back_populates="user", cascade="all, delete-orphan"
    )


class AuditLog(Base):
    """Audit log for tracking user actions."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50))
    resource_id = Column(Integer)
    details = Column(JSON, default=dict)
    ip_address = Column(String(50))
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    user = relationship("User", back_populates="audit_logs")


class TicketDependency(Base):
    """Model for tracking ticket dependencies."""

    __tablename__ = "ticket_dependencies"

    # Add table-level constraints and indexes
    __table_args__ = (
        UniqueConstraint(
            "parent_ticket_id", "depends_on_ticket_id", name="uq_ticket_dependency_pair"
        ),
        Index("idx_dependency_type", "dependency_type"),
        Index("idx_parent_depends", "parent_ticket_id", "depends_on_ticket_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    parent_ticket_id = Column(
        Integer, ForeignKey("tickets.id"), nullable=False, index=True
    )
    depends_on_ticket_id = Column(
        Integer, ForeignKey("tickets.id"), nullable=False, index=True
    )
    dependency_type = Column(String(50), default="blocks")  # blocks, requires, suggests
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    parent_ticket = relationship(
        "Ticket",
        foreign_keys=[parent_ticket_id],
        back_populates="dependencies_as_parent",
    )
    depends_on_ticket = relationship(
        "Ticket",
        foreign_keys=[depends_on_ticket_id],
        back_populates="dependencies_as_child",
    )


class TicketArtifact(Base):
    """Model for tracking artifacts created by tickets."""

    __tablename__ = "ticket_artifacts"

    # Add table-level indexes for better query performance
    __table_args__ = (
        Index("idx_artifact_type", "artifact_type"),
        Index("idx_artifact_name", "name"),
        Index("idx_ticket_artifact", "ticket_id", "artifact_type"),
        Index("idx_artifact_created", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False, index=True)
    artifact_type = Column(String(50), nullable=False)  # file, document, config, data
    name = Column(String(255), nullable=False)
    path = Column(String(500))  # File path or URL
    content = Column(Text)  # Optional inline content storage
    artifact_metadata = Column(JSON, default=dict)  # Additional metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    ticket = relationship("Ticket", back_populates="ticket_artifacts")


class DatabaseManager:
    """Database connection and session management."""

    def __init__(self, database_url: Optional[str] = None):
        """Initialize database manager."""
        self.database_url = database_url or os.getenv(
            "DATABASE_URL", "sqlite:///.hydra/dashboard/hydra.db"
        )

        # Handle SQLite in-memory for testing
        if "sqlite" in self.database_url:
            if ":memory:" in self.database_url:
                self.engine = create_engine(
                    self.database_url,
                    connect_args={"check_same_thread": False},
                    poolclass=StaticPool,
                )
            else:
                # Ensure directory exists for file-based SQLite
                db_path = self.database_url.replace("sqlite:///", "")
                if db_path:
                    db_dir = os.path.dirname(db_path)
                    if db_dir:
                        os.makedirs(db_dir, exist_ok=True)
                self.engine = create_engine(
                    self.database_url, connect_args={"check_same_thread": False}
                )
        else:
            # PostgreSQL or other databases
            self.engine = create_engine(self.database_url, pool_pre_ping=True)

        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )

    def create_tables(self):
        """Create all database tables."""
        Base.metadata.create_all(bind=self.engine)

    def get_session(self):
        """Get a new database session."""
        return self.SessionLocal()

    def close(self):
        """Close database connection."""
        self.engine.dispose()


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """Get or create database manager singleton."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
        _db_manager.create_tables()
    return _db_manager


def get_db():
    """Dependency for FastAPI to get database session."""
    db_manager = get_db_manager()
    db = db_manager.get_session()
    try:
        yield db
    finally:
        db.close()
