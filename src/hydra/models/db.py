"""Db module."""

import os
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, relationship, sessionmaker
from sqlalchemy.pool import QueuePool

Base = declarative_base()


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    max_requests_per_minute = Column(Integer, default=60, nullable=False)
    max_tokens_per_month = Column(Integer, default=1000000, nullable=False)
    max_concurrent_tasks = Column(Integer, default=10, nullable=False)

    api_keys = relationship("APIKey", back_populates="tenant")
    tasks = relationship("Task", back_populates="tenant")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    status = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    input = Column(Text, nullable=False)
    output = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    agent_count = Column(Integer, default=1, nullable=False)

    tenant = relationship("Tenant", back_populates="tasks")
    usage_records = relationship("Usage", back_populates="task")


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    key = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    rate_limit = Column(Integer, nullable=True)
    monthly_cost_limit = Column(Numeric(10, 2), nullable=True)

    tenant = relationship("Tenant", back_populates="api_keys")
    usage_records = relationship("Usage", back_populates="api_key")


class Usage(Base):
    __tablename__ = "usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    api_key_id = Column(Integer, ForeignKey("api_keys.id"), nullable=False, index=True)
    endpoint = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    tokens_used = Column(Integer, nullable=False)
    task_id = Column(String, ForeignKey("tasks.id"), nullable=True, index=True)
    model = Column(String, nullable=True, index=True)
    provider = Column(String, nullable=True, index=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    cost = Column(Numeric(10, 6), nullable=True)

    api_key = relationship("APIKey", back_populates="usage_records")
    task = relationship("Task", back_populates="usage_records")


Index("ix_usage_api_key_timestamp", Usage.api_key_id, Usage.timestamp)
Index("ix_usage_endpoint_timestamp", Usage.endpoint, Usage.timestamp)
Index("ix_tasks_status_created", Task.status, Task.created_at)
Index("ix_tasks_tenant_status", Task.tenant_id, Task.status)
Index("ix_api_keys_tenant", APIKey.tenant_id)
# Performance optimization indexes
Index("ix_usage_task_id", Usage.task_id)
Index("ix_usage_model_provider", Usage.model, Usage.provider)
Index("ix_tasks_tenant_created", Task.tenant_id, Task.created_at.desc())
Index(
    "ix_usage_cost_timestamp",
    Usage.cost,
    Usage.timestamp,
    postgresql_where=Usage.cost.isnot(None),
)
Index("ix_api_keys_active", APIKey.is_active, APIKey.key)


class DatabaseManager:
    def __init__(self, database_url: Optional[str] = None):
        if database_url is None:
            database_url = os.getenv(
                "DATABASE_URL", "postgresql://hydra:hydra@localhost/hydra"
            )

        self.engine = create_engine(
            database_url,
            poolclass=QueuePool,
            pool_size=20,  # Increased for better concurrency
            max_overflow=40,  # Increased overflow capacity
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=os.getenv("SQL_DEBUG", "false").lower() == "true",
            connect_args=(
                {
                    "connect_timeout": 10,
                    "application_name": "hydra_api",
                    "options": "-c statement_timeout=30000",  # 30 second statement timeout
                }
                if "postgresql" in database_url
                else {}
            ),
        )

        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )

    def create_tables(self):
        Base.metadata.create_all(bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()


_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def get_db() -> Session:
    return get_db_manager().get_session()
