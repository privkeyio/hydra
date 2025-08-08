"""Session Persistence Manager for Hydra.

Saves and restores Claude Code sessions for continuity.
"""

import json
import os
import pickle
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from hydra.orchestrator.claude_code_orchestrator import ClaudeCodeTask, TaskStatus


@dataclass
class SessionState:
    """Represents the state of a Claude Code session."""
    session_id: str
    project_path: str
    created_at: float
    last_accessed: float
    tasks: List[ClaudeCodeTask]
    environment: Dict[str, str]
    git_branch: Optional[str]
    git_commit: Optional[str]
    metadata: Dict[str, Any]


class SessionManager:
    """Manages persistent Claude Code sessions."""
    
    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = Path(storage_dir or os.path.expanduser("~/.hydra/sessions"))
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.storage_dir / "index.json"
        self._load_index()
    
    def _load_index(self):
        """Load the session index."""
        if self.index_file.exists():
            with open(self.index_file, 'r') as f:
                self.index = json.load(f)
        else:
            self.index = {}
    
    def _save_index(self):
        """Save the session index."""
        with open(self.index_file, 'w') as f:
            json.dump(self.index, f, indent=2)
    
    def save_session(
        self,
        session_id: str,
        project_path: str,
        tasks: List[ClaudeCodeTask],
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Save a Claude Code session state."""
        
        session_dir = self.storage_dir / session_id
        session_dir.mkdir(exist_ok=True)
        
        # Get git information
        git_branch = None
        git_commit = None
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                cwd=project_path
            )
            if result.returncode == 0:
                git_branch = result.stdout.strip()
            
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=project_path
            )
            if result.returncode == 0:
                git_commit = result.stdout.strip()
        except Exception:
            pass
        
        # Create session state
        state = SessionState(
            session_id=session_id,
            project_path=project_path,
            created_at=time.time(),
            last_accessed=time.time(),
            tasks=tasks,
            environment=dict(os.environ),
            git_branch=git_branch,
            git_commit=git_commit,
            metadata=metadata or {}
        )
        
        # Save state
        state_file = session_dir / "state.pkl"
        with open(state_file, 'wb') as f:
            pickle.dump(state, f)
        
        # Save human-readable summary
        summary_file = session_dir / "summary.json"
        summary = {
            "session_id": session_id,
            "project_path": project_path,
            "created_at": datetime.fromtimestamp(state.created_at).isoformat(),
            "last_accessed": datetime.fromtimestamp(state.last_accessed).isoformat(),
            "task_count": len(tasks),
            "completed_tasks": sum(1 for t in tasks if t.status == TaskStatus.COMPLETED),
            "git_branch": git_branch,
            "git_commit": git_commit,
            "metadata": metadata
        }
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        # Save file snapshots
        self._save_file_snapshots(session_dir, project_path)
        
        # Update index
        self.index[session_id] = {
            "project_path": project_path,
            "created_at": state.created_at,
            "last_accessed": state.last_accessed,
            "task_count": len(tasks)
        }
        self._save_index()
        
        return str(session_dir)
    
    def restore_session(self, session_id: str) -> Optional[SessionState]:
        """Restore a Claude Code session state."""
        
        session_dir = self.storage_dir / session_id
        if not session_dir.exists():
            return None
        
        state_file = session_dir / "state.pkl"
        if not state_file.exists():
            return None
        
        # Load state
        with open(state_file, 'rb') as f:
            state = pickle.load(f)
        
        # Update last accessed time
        state.last_accessed = time.time()
        
        # Save updated state
        with open(state_file, 'wb') as f:
            pickle.dump(state, f)
        
        # Update index
        if session_id in self.index:
            self.index[session_id]["last_accessed"] = state.last_accessed
            self._save_index()
        
        return state
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all saved sessions."""
        sessions = []
        
        for session_id, info in self.index.items():
            session_dir = self.storage_dir / session_id
            if session_dir.exists():
                sessions.append({
                    "session_id": session_id,
                    "project_path": info["project_path"],
                    "created_at": datetime.fromtimestamp(info["created_at"]).isoformat(),
                    "last_accessed": datetime.fromtimestamp(info["last_accessed"]).isoformat(),
                    "task_count": info.get("task_count", 0)
                })
        
        # Sort by last accessed
        sessions.sort(key=lambda x: x["last_accessed"], reverse=True)
        
        return sessions
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a saved session."""
        
        session_dir = self.storage_dir / session_id
        
        if session_dir.exists():
            shutil.rmtree(session_dir)
        
        if session_id in self.index:
            del self.index[session_id]
            self._save_index()
            return True
        
        return False
    
    def _save_file_snapshots(self, session_dir: Path, project_path: str):
        """Save snapshots of modified files."""
        
        snapshots_dir = session_dir / "snapshots"
        snapshots_dir.mkdir(exist_ok=True)
        
        # Get list of modified files
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=project_path
            )
            
            if result.returncode == 0:
                modified_files = []
                for line in result.stdout.strip().split('\n'):
                    if line:
                        parts = line.strip().split(maxsplit=1)
                        if len(parts) > 1:
                            file_path = parts[1]
                            if not file_path.endswith('.pyc') and not '/__pycache__/' in file_path:
                                modified_files.append(file_path)
                
                # Save snapshots of modified files
                for file_path in modified_files[:50]:  # Limit to 50 files
                    source_file = Path(project_path) / file_path
                    if source_file.exists() and source_file.is_file():
                        dest_file = snapshots_dir / file_path.replace('/', '_')
                        try:
                            shutil.copy2(source_file, dest_file)
                        except:
                            pass
        except Exception:
            pass
    
    def restore_file_snapshots(self, session_id: str, project_path: str) -> int:
        """Restore file snapshots from a session."""
        
        session_dir = self.storage_dir / session_id
        snapshots_dir = session_dir / "snapshots"
        
        if not snapshots_dir.exists():
            return 0
        
        restored_count = 0
        
        for snapshot_file in snapshots_dir.iterdir():
            if snapshot_file.is_file():
                # Reconstruct original path
                original_path = snapshot_file.name.replace('_', '/')
                dest_file = Path(project_path) / original_path
                
                try:
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(snapshot_file, dest_file)
                    restored_count += 1
                except:
                    pass
        
        return restored_count
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a session."""
        
        session_dir = self.storage_dir / session_id
        summary_file = session_dir / "summary.json"
        
        if summary_file.exists():
            with open(summary_file, 'r') as f:
                return json.load(f)
        
        return None
    
    def export_session(self, session_id: str, export_path: str) -> bool:
        """Export a session to an archive."""
        
        session_dir = self.storage_dir / session_id
        
        if not session_dir.exists():
            return False
        
        try:
            shutil.make_archive(export_path, 'zip', session_dir)
            return True
        except:
            return False
    
    def import_session(self, archive_path: str) -> Optional[str]:
        """Import a session from an archive."""
        
        if not Path(archive_path).exists():
            return None
        
        try:
            # Extract to temp directory
            import tempfile
            with tempfile.TemporaryDirectory() as temp_dir:
                shutil.unpack_archive(archive_path, temp_dir)
                
                # Find session ID from extracted files
                state_file = Path(temp_dir) / "state.pkl"
                if state_file.exists():
                    with open(state_file, 'rb') as f:
                        state = pickle.load(f)
                    
                    session_id = state.session_id
                    session_dir = self.storage_dir / session_id
                    
                    # Copy to sessions directory
                    if session_dir.exists():
                        shutil.rmtree(session_dir)
                    shutil.copytree(temp_dir, session_dir)
                    
                    # Update index
                    self.index[session_id] = {
                        "project_path": state.project_path,
                        "created_at": state.created_at,
                        "last_accessed": time.time(),
                        "task_count": len(state.tasks)
                    }
                    self._save_index()
                    
                    return session_id
        except Exception:
            pass
        
        return None
    
    def cleanup_old_sessions(self, days: int = 30) -> int:
        """Clean up sessions older than specified days."""
        
        cutoff_time = time.time() - (days * 24 * 3600)
        deleted_count = 0
        
        sessions_to_delete = []
        for session_id, info in self.index.items():
            if info["last_accessed"] < cutoff_time:
                sessions_to_delete.append(session_id)
        
        for session_id in sessions_to_delete:
            if self.delete_session(session_id):
                deleted_count += 1
        
        return deleted_count