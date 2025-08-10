"""File locking mechanism for parallel agent execution.

Prevents multiple agents from modifying the same files simultaneously.
"""

import fcntl
import os
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Set


class FileLockManager:
    """Manages file locks across parallel agents."""
    
    def __init__(self):
        """Initialize the file lock manager."""
        self.locks: Dict[str, threading.Lock] = {}
        self.lock_holders: Dict[str, str] = {}  # file -> agent_id
        self.agent_files: Dict[str, Set[str]] = {}  # agent_id -> set of files
        self.global_lock = threading.Lock()
        
    def acquire_lock(self, agent_id: str, file_path: str, timeout: float = 30) -> bool:
        """Acquire a lock on a file for an agent.
        
        Args:
            file_path: Path to the file to lock
            agent_id: ID of the agent requesting the lock
            timeout: Maximum time to wait for lock in seconds
            
        Returns:
            True if lock acquired, False if timeout
        """
        file_path = str(Path(file_path).resolve())
        
        with self.global_lock:
            # Create lock if it doesn't exist
            if file_path not in self.locks:
                self.locks[file_path] = threading.Lock()
                
        # Try to acquire the lock with timeout
        acquired = self.locks[file_path].acquire(timeout=timeout)
        
        if acquired:
            with self.global_lock:
                self.lock_holders[file_path] = agent_id
                if agent_id not in self.agent_files:
                    self.agent_files[agent_id] = set()
                self.agent_files[agent_id].add(file_path)
                print(f"🔒 Agent {agent_id} acquired lock on {Path(file_path).name}")
                
        return acquired
        
    def release_lock(self, agent_id: str, file_path: str):
        """Release a lock on a file.
        
        Args:
            file_path: Path to the file to unlock
            agent_id: ID of the agent releasing the lock
        """
        file_path = str(Path(file_path).resolve())
        
        with self.global_lock:
            # Check if this agent holds the lock
            if file_path in self.lock_holders and self.lock_holders[file_path] == agent_id:
                self.locks[file_path].release()
                del self.lock_holders[file_path]
                
                if agent_id in self.agent_files:
                    self.agent_files[agent_id].discard(file_path)
                    
                print(f"🔓 Agent {agent_id} released lock on {Path(file_path).name}")
                
    def release_all_locks(self, agent_id: str):
        """Release all locks held by an agent.
        
        Args:
            agent_id: ID of the agent
        """
        files_to_release = []
        with self.global_lock:
            if agent_id in self.agent_files:
                # Copy the set to avoid modification during iteration
                files_to_release = list(self.agent_files[agent_id])
                
        # Release locks outside the global lock to avoid deadlock
        for file_path in files_to_release:
            self.release_lock(agent_id, file_path)
            
    def is_locked(self, file_path: str) -> bool:
        """Check if a file is currently locked.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file is locked
        """
        file_path = str(Path(file_path).resolve())
        
        with self.global_lock:
            return file_path in self.lock_holders
            
    def get_lock_holder(self, file_path: str) -> Optional[str]:
        """Get the agent holding a lock on a file.
        
        Args:
            file_path: Path to check
            
        Returns:
            Agent ID or None if not locked
        """
        file_path = str(Path(file_path).resolve())
        
        with self.global_lock:
            return self.lock_holders.get(file_path)
            
    def get_agent_locks(self, agent_id: str) -> Set[str]:
        """Get all files locked by an agent.
        
        Args:
            agent_id: Agent to check
            
        Returns:
            Set of locked file paths
        """
        with self.global_lock:
            return self.agent_files.get(agent_id, set()).copy()
    
    def get_locked_files(self) -> Set[str]:
        """Get all currently locked files.
        
        Returns:
            Set of all locked file paths
        """
        with self.global_lock:
            return set(self.lock_holders.keys())


# Global instance
_file_lock_manager = FileLockManager()


def get_file_lock_manager() -> FileLockManager:
    """Get the global file lock manager instance."""
    return _file_lock_manager