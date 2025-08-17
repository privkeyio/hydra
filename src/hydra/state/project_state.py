"""Project State module."""

import hashlib
import json
import pickle
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class ProjectStatus(Enum):
    INITIALIZED = "initialized"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CheckpointType(Enum):
    MANUAL = "manual"
    AUTO = "auto"
    MILESTONE = "milestone"
    ERROR = "error"


@dataclass
class Operation:
    id: str
    timestamp: float
    operation_type: str
    details: Dict[str, Any]
    success: bool
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None


@dataclass
class Checkpoint:
    id: str
    timestamp: float
    checkpoint_type: CheckpointType
    state_hash: str
    description: str
    operations_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectState:
    project_id: str
    name: str
    status: ProjectStatus
    created_at: float
    updated_at: float
    current_checkpoint: Optional[str] = None
    total_operations: int = 0
    success_rate: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class StateSerializer:
    @staticmethod
    def serialize_state(state: ProjectState) -> bytes:
        return pickle.dumps(asdict(state))

    @staticmethod
    def deserialize_state(data: bytes) -> ProjectState:
        state_dict = pickle.loads(data)
        state_dict["status"] = ProjectStatus(state_dict["status"])
        return ProjectState(**state_dict)

    @staticmethod
    def export_json(state: ProjectState) -> str:
        state_dict = asdict(state)
        state_dict["status"] = state.status.value
        state_dict["created_at"] = datetime.fromtimestamp(state.created_at).isoformat()
        state_dict["updated_at"] = datetime.fromtimestamp(state.updated_at).isoformat()
        return json.dumps(state_dict, indent=2)

    @staticmethod
    def import_json(json_str: str) -> ProjectState:
        data = json.loads(json_str)
        data["status"] = ProjectStatus(data["status"])
        data["created_at"] = datetime.fromisoformat(data["created_at"]).timestamp()
        data["updated_at"] = datetime.fromisoformat(data["updated_at"]).timestamp()
        return ProjectState(**data)


class StateStorage:
    def __init__(self, db_path: str = "hydra_state.db"):
        self.db_path = Path(db_path)
        self._init_database()

    def _init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    state_data BLOB NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    checkpoint_type TEXT NOT NULL,
                    state_hash TEXT NOT NULL,
                    description TEXT NOT NULL,
                    operations_count INTEGER NOT NULL,
                    metadata TEXT,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects (project_id)
                )
            """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS operations (
                    operation_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    operation_type TEXT NOT NULL,
                    details TEXT NOT NULL,
                    success BOOLEAN NOT NULL,
                    duration_ms INTEGER,
                    error_message TEXT,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects (project_id)
                )
            """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_operations_project_time
                ON operations (project_id, timestamp)
            """
            )

    def save_state(self, state: ProjectState):
        state_data = StateSerializer.serialize_state(state)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO projects
                (project_id, name, status, state_data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    state.project_id,
                    state.name,
                    state.status.value,
                    state_data,
                    state.created_at,
                    state.updated_at,
                ),
            )

    def load_state(self, project_id: str) -> Optional[ProjectState]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT state_data FROM projects WHERE project_id = ?", (project_id,)
            )
            row = cursor.fetchone()

            if row:
                return StateSerializer.deserialize_state(row[0])
        return None

    def save_checkpoint(self, checkpoint: Checkpoint):
        metadata_json = json.dumps(checkpoint.metadata)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO checkpoints
                (checkpoint_id, project_id, checkpoint_type, state_hash,
                 description, operations_count, metadata, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    checkpoint.id,
                    checkpoint.metadata.get("project_id", ""),
                    checkpoint.checkpoint_type.value,
                    checkpoint.state_hash,
                    checkpoint.description,
                    checkpoint.operations_count,
                    metadata_json,
                    checkpoint.timestamp,
                ),
            )

    def load_checkpoints(self, project_id: str) -> List[Checkpoint]:
        checkpoints = []

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT checkpoint_id, checkpoint_type, state_hash, description,
                       operations_count, metadata, timestamp
                FROM checkpoints
                WHERE project_id = ?
                ORDER BY timestamp DESC
            """,
                (project_id,),
            )

            for row in cursor:
                metadata = json.loads(row[5]) if row[5] else {}
                checkpoint = Checkpoint(
                    id=row[0],
                    checkpoint_type=CheckpointType(row[1]),
                    state_hash=row[2],
                    description=row[3],
                    operations_count=row[4],
                    metadata=metadata,
                    timestamp=row[6],
                )
                checkpoints.append(checkpoint)

        return checkpoints

    def save_operation(self, operation: Operation, project_id: str):
        details_json = json.dumps(operation.details)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO operations
                (operation_id, project_id, operation_type, details, success,
                 duration_ms, error_message, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    operation.id,
                    project_id,
                    operation.operation_type,
                    details_json,
                    operation.success,
                    operation.duration_ms,
                    operation.error_message,
                    operation.timestamp,
                ),
            )

    def load_operations(self, project_id: str, limit: int = 1000) -> List[Operation]:
        operations = []

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT operation_id, operation_type, details, success,
                       duration_ms, error_message, timestamp
                FROM operations
                WHERE project_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """,
                (project_id, limit),
            )

            for row in cursor:
                details = json.loads(row[2])
                operation = Operation(
                    id=row[0],
                    timestamp=row[6],
                    operation_type=row[1],
                    details=details,
                    success=bool(row[3]),
                    duration_ms=row[4],
                    error_message=row[5],
                )
                operations.append(operation)

        return operations


class ProjectStateManager:
    def __init__(self, storage_path: Optional[str] = None):
        self.storage = StateStorage(storage_path or "hydra_state.db")
        self._current_states: Dict[str, ProjectState] = {}
        self._auto_checkpoint_interval = 300  # 5 minutes
        self._last_auto_checkpoint: Dict[str, float] = {}

    def create_project(
        self, project_id: str, name: str, metadata: Dict = None
    ) -> ProjectState:
        now = time.time()
        state = ProjectState(
            project_id=project_id,
            name=name,
            status=ProjectStatus.INITIALIZED,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )

        self._current_states[project_id] = state
        self.storage.save_state(state)

        self.create_checkpoint(
            project_id=project_id,
            checkpoint_type=CheckpointType.MILESTONE,
            description="Project initialized",
        )

        return state

    def get_project_state(self, project_id: str) -> Optional[ProjectState]:
        if project_id in self._current_states:
            return self._current_states[project_id]

        state = self.storage.load_state(project_id)
        if state:
            self._current_states[project_id] = state

        return state

    def update_project_status(self, project_id: str, status: ProjectStatus):
        state = self.get_project_state(project_id)
        if state:
            state.status = status
            state.updated_at = time.time()
            self.storage.save_state(state)

    def record_operation(
        self,
        project_id: str,
        operation_type: str,
        details: Dict,
        success: bool = True,
        duration_ms: Optional[int] = None,
        error_message: Optional[str] = None,
    ):

        operation = Operation(
            id=f"{project_id}_{int(time.time() * 1000)}_{len(details)}",
            timestamp=time.time(),
            operation_type=operation_type,
            details=details,
            success=success,
            duration_ms=duration_ms,
            error_message=error_message,
        )

        self.storage.save_operation(operation, project_id)

        state = self.get_project_state(project_id)
        if state:
            state.total_operations += 1
            state.updated_at = time.time()

            operations = self.storage.load_operations(project_id, 100)
            if operations:
                successful = sum(1 for op in operations if op.success)
                state.success_rate = successful / len(operations)

            self.storage.save_state(state)

            self._check_auto_checkpoint(project_id)

    def create_checkpoint(
        self,
        project_id: str,
        checkpoint_type: CheckpointType,
        description: str,
        metadata: Dict = None,
    ) -> Checkpoint:

        state = self.get_project_state(project_id)
        if not state:
            raise ValueError(f"Project {project_id} not found")

        state_data = StateSerializer.serialize_state(state)
        state_hash = hashlib.sha256(state_data).hexdigest()[:16]

        checkpoint = Checkpoint(
            id=f"{project_id}_checkpoint_{int(time.time())}",
            timestamp=time.time(),
            checkpoint_type=checkpoint_type,
            state_hash=state_hash,
            description=description,
            operations_count=state.total_operations,
            metadata={**(metadata or {}), "project_id": project_id},
        )

        self.storage.save_checkpoint(checkpoint)

        state.current_checkpoint = checkpoint.id
        self.storage.save_state(state)

        return checkpoint

    def resume_from_checkpoint(self, project_id: str, checkpoint_id: str) -> bool:
        checkpoints = self.storage.load_checkpoints(project_id)
        target_checkpoint = next(
            (c for c in checkpoints if c.id == checkpoint_id), None
        )

        if not target_checkpoint:
            return False

        state = self.get_project_state(project_id)
        if state:
            state.status = ProjectStatus.RUNNING
            state.current_checkpoint = checkpoint_id
            state.updated_at = time.time()
            self.storage.save_state(state)

            self.record_operation(
                project_id=project_id,
                operation_type="resume",
                details={
                    "checkpoint_id": checkpoint_id,
                    "description": target_checkpoint.description,
                },
            )

            return True

        return False

    def _check_auto_checkpoint(self, project_id: str):
        now = time.time()
        last_checkpoint = self._last_auto_checkpoint.get(project_id, 0)

        if now - last_checkpoint > self._auto_checkpoint_interval:
            self.create_checkpoint(
                project_id=project_id,
                checkpoint_type=CheckpointType.AUTO,
                description=f"Auto-checkpoint at "
                f"{datetime.fromtimestamp(now).strftime('%H:%M:%S')}",
            )
            self._last_auto_checkpoint[project_id] = now

    def get_project_history(self, project_id: str) -> Dict[str, Any]:
        state = self.get_project_state(project_id)
        checkpoints = self.storage.load_checkpoints(project_id)
        operations = self.storage.load_operations(project_id, 100)

        return {
            "state": state,
            "checkpoints": checkpoints,
            "recent_operations": operations,
            "total_checkpoints": len(checkpoints),
            "uptime_hours": (time.time() - state.created_at) / 3600 if state else 0,
        }

    def export_project(self, project_id: str) -> Dict[str, Any]:
        state = self.get_project_state(project_id)
        if not state:
            raise ValueError(f"Project {project_id} not found")

        return {
            "state": StateSerializer.export_json(state),
            "checkpoints": [
                asdict(c) for c in self.storage.load_checkpoints(project_id)
            ],
            "operations": [
                asdict(op) for op in self.storage.load_operations(project_id)
            ],
        }

    def import_project(self, project_data: Dict[str, Any]) -> str:
        state = StateSerializer.import_json(project_data["state"])
        project_id = state.project_id

        self._current_states[project_id] = state
        self.storage.save_state(state)

        for checkpoint_data in project_data.get("checkpoints", []):
            checkpoint_data["checkpoint_type"] = CheckpointType(
                checkpoint_data["checkpoint_type"]
            )
            checkpoint = Checkpoint(**checkpoint_data)
            self.storage.save_checkpoint(checkpoint)

        for operation_data in project_data.get("operations", []):
            operation = Operation(**operation_data)
            self.storage.save_operation(operation, project_id)

        return project_id

    def visualize_progress(self, project_id: str) -> Dict[str, Any]:
        history = self.get_project_history(project_id)

        if not history["state"]:
            return {"error": "Project not found"}

        checkpoints = history["checkpoints"]
        operations = history["recent_operations"]

        timeline = []
        for checkpoint in checkpoints:
            timeline.append(
                {
                    "timestamp": checkpoint.timestamp,
                    "type": "checkpoint",
                    "description": checkpoint.description,
                    "checkpoint_type": checkpoint.checkpoint_type.value,
                }
            )

        for op in operations[-20:]:
            timeline.append(
                {
                    "timestamp": op.timestamp,
                    "type": "operation",
                    "description": f"{op.operation_type}: {op.success}",
                    "success": op.success,
                }
            )

        timeline.sort(key=lambda x: x["timestamp"])

        return {
            "project_id": project_id,
            "status": history["state"].status.value,
            "progress": {
                "total_operations": history["state"].total_operations,
                "success_rate": history["state"].success_rate,
                "uptime_hours": round(history["uptime_hours"], 2),
                "checkpoints_count": history["total_checkpoints"],
            },
            "timeline": timeline,
        }
