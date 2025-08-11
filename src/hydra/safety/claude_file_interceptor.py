"""Claude Code File Operation Interceptor.

Intercepts file operations from Claude Code sessions and applies file locking
to prevent concurrent modification conflicts in parallel execution.
"""

import re
import threading
import time
from collections import defaultdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from hydra.safety.file_lock import get_file_lock_manager


class OperationType(Enum):
    """Types of file operations."""

    READ = "read"
    WRITE = "write"
    EDIT = "edit"
    CREATE = "create"
    DELETE = "delete"


class ConflictType(Enum):
    """Types of file conflicts."""

    NONE = "none"
    COMPATIBLE = "compatible"  # Can be done concurrently
    INCOMPATIBLE = "incompatible"  # Requires exclusive access
    DEADLOCK = "deadlock"  # Circular dependency


class ResolutionStrategy(Enum):
    """Conflict resolution strategies."""

    WAIT = "wait"  # Wait for lock
    SKIP = "skip"  # Skip conflicting file
    MERGE = "merge"  # Attempt merge after completion
    ABORT = "abort"  # Abort operation


class FileModification:
    """Represents a file modification request."""

    def __init__(self, agent_id: str, file_path: str, operation: OperationType,
                 ticket_content: str = "", priority: int = 1):
        self.agent_id = agent_id
        self.file_path = str(Path(file_path).resolve())
        self.operation = operation
        self.ticket_content = ticket_content
        self.priority = priority
        self.timestamp = time.time()
        self.predicted_changes = self._analyze_changes()

    def _analyze_changes(self) -> Set[str]:
        """Analyze what parts of file will be modified."""
        changes = set()
        content = self.ticket_content.lower()

        # Detect specific changes with more granular analysis
        if 'import' in content or 'from' in content:
            # Make import changes more specific to avoid false conflicts
            import_words = set()
            words = content.split()
            for i, word in enumerate(words):
                if word == 'import' and i + 1 < len(words):
                    import_words.add(f'import_{words[i+1]}')
                elif word == 'from' and i + 1 < len(words):
                    import_words.add(f'from_{words[i+1]}')

            if import_words:
                changes.update(import_words)
            else:
                changes.add('imports')

        if 'class' in content or 'def' in content:
            changes.add('definitions')
        if 'config' in content or 'setting' in content:
            changes.add('configuration')
        if 'test' in content:
            changes.add('tests')
        if 'style' in content or 'format' in content:
            changes.add('formatting')

        return changes

    def is_compatible_with(self, other: 'FileModification') -> bool:
        """Check if this modification is compatible with another."""
        if self.file_path != other.file_path:
            return True

        # Read operations are compatible with everything
        if (self.operation == OperationType.READ or
            other.operation == OperationType.READ):
            return True

        # Check for non-overlapping changes
        if self.predicted_changes and other.predicted_changes:
            if not (self.predicted_changes & other.predicted_changes):
                return True

        # Different sections of the same file
        if self._affects_different_sections(other):
            return True

        # If both have empty predicted changes, assume they might be compatible
        # This handles the case where content analysis didn't detect specific change types
        if not self.predicted_changes and not other.predicted_changes:
            # Use a simple heuristic: if ticket content is very different, assume compatible
            if self._has_low_content_similarity(other):
                return True

        return False

    def _has_low_content_similarity(self, other: 'FileModification') -> bool:
        """Check if ticket content has low similarity, suggesting different modifications."""
        # Simple word-based similarity check
        self_words = set(self.ticket_content.lower().split())
        other_words = set(other.ticket_content.lower().split())

        if not self_words and not other_words:
            return False

        if not self_words or not other_words:
            return True

        intersection = self_words & other_words
        union = self_words | other_words

        similarity = len(intersection) / len(union) if union else 0
        return similarity < 0.3  # Less than 30% similarity suggests different modifications

    def _affects_different_sections(self, other: 'FileModification') -> bool:
        """Check if modifications affect different file sections."""
        # Simple heuristic based on line numbers mentioned
        self_lines = set(re.findall(r'line\s+(\d+)',
                                   self.ticket_content, re.IGNORECASE))
        other_lines = set(re.findall(r'line\s+(\d+)',
                                    other.ticket_content, re.IGNORECASE))

        if self_lines and other_lines:
            # Check if line ranges don't overlap (with buffer)
            self_nums = {int(x) for x in self_lines}
            other_nums = {int(x) for x in other_lines}
            return (max(self_nums) + 5 < min(other_nums) or
                   max(other_nums) + 5 < min(self_nums))

        return False


class ClaudeFileInterceptor:
    """Intercepts and manages file operations from Claude Code sessions."""

    def __init__(self):
        self.file_lock_manager = get_file_lock_manager()
        self.operation_patterns = {
            'read': [
                r'Reading[:\s]+([^\s]+)',
                r'opening[:\s]+([^\s]+)',
                r'checking[:\s]+([^\s]+)'
            ],
            'write': [
                r'Writing[:\s]+([^\s]+)',
                r'Creating[:\s]+([^\s]+)',
                r'saving[:\s]+([^\s]+)'
            ],
            'edit': [
                r'Editing[:\s]+([^\s]+)',
                r'modifying[:\s]+([^\s]+)',
                r'updating[:\s]+([^\s]+)'
            ]
        }
        self.active_locks: Dict[str, Set[str]] = {}  # agent_id -> set of locked files

    def detect_file_operation(
        self, output: str, agent_id: str
    ) -> Optional[Tuple[str, str]]:
        """Detect file operations in Claude Code output.
        
        Args:
            output: The output from Claude Code session
            agent_id: The agent/session identifier
            
        Returns:
            Tuple of (operation_type, file_path) or None

        """
        for op_type, patterns in self.operation_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, output, re.IGNORECASE)
                if match:
                    file_path = match.group(1)
                    return (op_type, file_path)
        return None

    def acquire_file_lock(self, agent_id: str, file_path: str, operation: str) -> bool:
        """Acquire a file lock before operation.
        
        Args:
            agent_id: The agent requesting the lock
            file_path: Path to the file
            operation: Type of operation (read/write/edit)
            
        Returns:
            True if lock acquired, False otherwise

        """
        # For read operations, we don't need exclusive locks
        if operation == 'read':
            return True

        try:
            # Try to acquire lock with shorter timeout for better responsiveness
            success = self.file_lock_manager.acquire_lock(
                agent_id, file_path, timeout=10
            )

            if success:
                # Track active locks for this agent
                if agent_id not in self.active_locks:
                    self.active_locks[agent_id] = set()
                self.active_locks[agent_id].add(file_path)

                print(f"🔒 Lock acquired: {agent_id} -> {file_path}")
                return True
            else:
                print(f"⏳ Waiting for lock: {agent_id} -> {file_path}")
                # Implement retry with exponential backoff
                for attempt in range(3):
                    time.sleep(2 ** attempt)  # 1s, 2s, 4s
                    if self.file_lock_manager.acquire_lock(
                        agent_id, file_path, timeout=5
                    ):
                        if agent_id not in self.active_locks:
                            self.active_locks[agent_id] = set()
                        self.active_locks[agent_id].add(file_path)
                        print(f"🔓 Lock acquired after retry: {agent_id} -> {file_path}")
                        return True

                print(f"❌ Failed to acquire lock: {agent_id} -> {file_path}")
                return False

        except Exception as e:
            print(f"⚠️ Lock acquisition error: {e}")
            return False

    def release_agent_locks(self, agent_id: str):
        """Release all locks held by an agent.
        
        Args:
            agent_id: The agent whose locks should be released

        """
        if agent_id in self.active_locks:
            for file_path in self.active_locks[agent_id]:
                self.file_lock_manager.release_lock(agent_id, file_path)
                print(f"🔓 Lock released: {agent_id} -> {file_path}")
            del self.active_locks[agent_id]

        # Also use the file lock manager's release all method
        self.file_lock_manager.release_all_locks(agent_id)

    def get_lock_status(self) -> Dict[str, any]:
        """Get current lock status for monitoring.
        
        Returns:
            Dictionary with lock statistics

        """
        return {
            'total_locks': sum(len(files) for files in self.active_locks.values()),
            'active_agents': len(self.active_locks),
            'locked_files': self.file_lock_manager.get_locked_files(),
            'lock_holders': self.file_lock_manager.lock_holders
        }


class SmartFileLockManager:
    """Advanced file locking with intelligent conflict prediction and resolution."""

    def __init__(self, max_wait_time: int = 60, deadlock_check_interval: int = 5):
        self.interceptor = ClaudeFileInterceptor()
        self.file_dependencies: Dict[str, Set[str]] = {}
        self.modification_history: Dict[str, List[FileModification]] = defaultdict(list)
        self.pending_requests: Dict[str, FileModification] = {}
        self.active_modifications: Dict[str, FileModification] = {}
        self.wait_graph: Dict[str, Set[str]] = defaultdict(set)  # For deadlock detection

        # Configuration
        self.max_wait_time = max_wait_time
        self.deadlock_check_interval = deadlock_check_interval
        self.resolution_strategies: Dict[str, ResolutionStrategy] = {
            'default': ResolutionStrategy.WAIT,
            'compatible': ResolutionStrategy.WAIT,
            'incompatible': ResolutionStrategy.WAIT,
            'deadlock': ResolutionStrategy.ABORT
        }

        # Statistics for reducing false conflicts
        self.conflict_stats = {
            'predicted_conflicts': 0,
            'actual_conflicts': 0,
            'false_conflicts': 0,
            'resolved_conflicts': 0
        }

        # Start deadlock detection thread
        self._deadlock_thread = threading.Thread(target=self._deadlock_monitor, daemon=True)
        self._deadlock_thread.start()

    def predict_file_modifications(self, agent_id: str, ticket_content: str) -> List[FileModification]:
        """Predict file modifications from ticket description with high accuracy."""
        modifications = []

        # Enhanced file pattern matching
        file_patterns = [
            # Explicit file operations
            r'(?:create|write|edit|modify|update|delete)\s+([^\s]+\.(?:py|js|ts|jsx|tsx|css|html|json|yaml|yml|md|txt|sh))',
            r'(?:in|at|to)\s+([^\s]+/[^\s]+\.(?:py|js|ts|jsx|tsx|css|html|json|yaml|yml|md|txt|sh))',
            # Path-like patterns
            r'(src/[^\s]+\.(?:py|js|ts|jsx|tsx|css|html|json|yaml|yml|md|txt|sh))',
            r'(tests?/[^\s]+\.(?:py|js|ts|jsx|tsx|css|html|json|yaml|yml|md|txt|sh))',
            r'(docs?/[^\s]+\.(?:py|js|ts|jsx|tsx|css|html|json|yaml|yml|md|txt|sh))',
            # Configuration files
            r'((?:config|setup|package)\.(?:py|js|json|yaml|yml|toml|ini))',
        ]

        predicted_files = set()
        for pattern in file_patterns:
            matches = re.findall(pattern, ticket_content, re.IGNORECASE)
            predicted_files.update(matches)

        # Predict based on content analysis
        content_lower = ticket_content.lower()

        # Module/component mapping
        module_mappings = {
            'provider': 'src/hydra/providers/',
            'safety': 'src/hydra/safety/',
            'security': 'src/hydra/safety/',
            'config': 'src/hydra/config/',
            'monitoring': 'src/hydra/monitoring/',
            'parallel': 'src/hydra/parallel/',
            'cli': 'src/hydra/cli.py',
            'test': 'tests/',
        }

        for keyword, path in module_mappings.items():
            if keyword in content_lower:
                if path.endswith('/'):
                    # Directory - add likely files
                    predicted_files.add(f"{path}__init__.py")
                    predicted_files.add(f"{path}manager.py")
                else:
                    predicted_files.add(path)

        # Create FileModification objects
        for file_path in predicted_files:
            # Determine operation type from context
            operation = OperationType.EDIT  # Default
            if 'create' in content_lower and file_path in ticket_content:
                operation = OperationType.CREATE
            elif 'delete' in content_lower and file_path in ticket_content:
                operation = OperationType.DELETE
            elif 'read' in content_lower and file_path in ticket_content:
                operation = OperationType.READ

            modification = FileModification(
                agent_id=agent_id,
                file_path=file_path,
                operation=operation,
                ticket_content=ticket_content
            )
            modifications.append(modification)

        return modifications

    def analyze_conflict(self, mod1: FileModification, mod2: FileModification) -> ConflictType:
        """Analyze conflict type between two modifications."""
        if mod1.file_path != mod2.file_path:
            return ConflictType.NONE

        # Check for compatibility
        if mod1.is_compatible_with(mod2):
            return ConflictType.COMPATIBLE

        # Check for circular dependency (deadlock)
        if self._check_circular_dependency(mod1.agent_id, mod2.agent_id):
            return ConflictType.DEADLOCK

        return ConflictType.INCOMPATIBLE

    def request_file_lock(self, agent_id: str, file_path: str, ticket_content: str = "") -> bool:
        """Request a file lock with intelligent conflict resolution."""
        file_path = str(Path(file_path).resolve())

        # Create modification request
        modification = FileModification(
            agent_id=agent_id,
            file_path=file_path,
            operation=OperationType.EDIT,
            ticket_content=ticket_content
        )

        # Check for conflicts with active modifications
        conflicts = []
        for active_mod in self.active_modifications.values():
            conflict_type = self.analyze_conflict(modification, active_mod)
            if conflict_type != ConflictType.NONE:
                conflicts.append((active_mod, conflict_type))

        # Handle conflicts based on type
        if not conflicts:
            # No conflicts, proceed
            return self._acquire_lock(modification)

        # Apply resolution strategy
        compatible_conflicts = [c for c in conflicts if c[1] == ConflictType.COMPATIBLE]
        incompatible_conflicts = [c for c in conflicts if c[1] == ConflictType.INCOMPATIBLE]
        deadlock_conflicts = [c for c in conflicts if c[1] == ConflictType.DEADLOCK]

        if deadlock_conflicts:
            strategy = self.resolution_strategies.get('deadlock', ResolutionStrategy.ABORT)
            return self._handle_conflict(modification, deadlock_conflicts, strategy)

        if compatible_conflicts and not incompatible_conflicts:
            # Allow compatible concurrent access
            self.conflict_stats['predicted_conflicts'] += 1
            return self._acquire_lock(modification)

        if incompatible_conflicts:
            strategy = self.resolution_strategies.get('incompatible', ResolutionStrategy.WAIT)
            return self._handle_conflict(modification, incompatible_conflicts, strategy)

        return False

    def _acquire_lock(self, modification: FileModification) -> bool:
        """Acquire lock for a modification."""
        success = self.interceptor.acquire_file_lock(
            modification.agent_id,
            modification.file_path,
            modification.operation.value
        )

        if success:
            self.active_modifications[f"{modification.agent_id}:{modification.file_path}"] = modification
            self.modification_history[modification.file_path].append(modification)

        return success

    def _handle_conflict(self, modification: FileModification, conflicts: List, strategy: ResolutionStrategy) -> bool:
        """Handle conflicts based on resolution strategy."""
        if strategy == ResolutionStrategy.WAIT:
            # Add to pending and wait
            self.pending_requests[f"{modification.agent_id}:{modification.file_path}"] = modification
            self._update_wait_graph(modification, conflicts)
            return self._wait_for_resolution(modification)

        elif strategy == ResolutionStrategy.SKIP:
            print(f"⏩ Skipping {modification.file_path} for {modification.agent_id} due to conflict")
            return False

        elif strategy == ResolutionStrategy.ABORT:
            print(f"🛑 Aborting {modification.file_path} for {modification.agent_id} due to deadlock")
            return False

        elif strategy == ResolutionStrategy.MERGE:
            # For future implementation - merge changes post-execution
            return self._schedule_merge(modification, conflicts)

        return False

    def _wait_for_resolution(self, modification: FileModification, timeout: Optional[int] = None) -> bool:
        """Wait for conflict resolution with timeout."""
        wait_time = timeout or self.max_wait_time
        start_time = time.time()

        while time.time() - start_time < wait_time:
            # Check if conflict resolved
            current_conflicts = []
            for active_mod in self.active_modifications.values():
                conflict_type = self.analyze_conflict(modification, active_mod)
                if conflict_type == ConflictType.INCOMPATIBLE:
                    current_conflicts.append(active_mod)

            if not current_conflicts:
                # Conflict resolved, try to acquire lock
                return self._acquire_lock(modification)

            time.sleep(0.5)  # Wait and retry

        # Timeout reached
        self.conflict_stats['actual_conflicts'] += 1
        return False

    def _update_wait_graph(self, modification: FileModification, conflicts: List):
        """Update wait graph for deadlock detection."""
        for conflict_mod, _ in conflicts:
            self.wait_graph[modification.agent_id].add(conflict_mod.agent_id)

    def _check_circular_dependency(self, agent1: str, agent2: str) -> bool:
        """Check for circular dependency between agents."""
        def has_path(start: str, target: str) -> bool:
            if start == target:
                return True
            visited = set()
            stack = [start]

            while stack:
                current = stack.pop()
                if current == target:
                    return True
                if current in visited:
                    continue
                visited.add(current)
                stack.extend(self.wait_graph.get(current, set()))
            return False

        # Check if agent1 waits for agent2 AND agent2 waits for agent1
        return has_path(agent1, agent2) and has_path(agent2, agent1)

    def _deadlock_monitor(self):
        """Monitor for deadlocks and resolve them."""
        while True:
            time.sleep(self.deadlock_check_interval)

            # Check for cycles in wait graph
            all_agents = set(self.wait_graph.keys())
            for start_agent in all_agents:
                if self._detect_cycle(start_agent):
                    self._resolve_deadlock(start_agent)

    def _detect_cycle(self, start_agent: str) -> bool:
        """Detect cycle in wait graph using DFS."""
        visited = set()
        rec_stack = set()

        def dfs(agent: str) -> bool:
            visited.add(agent)
            rec_stack.add(agent)

            for neighbor in self.wait_graph.get(agent, set()):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(agent)
            return False

        return dfs(start_agent)

    def _resolve_deadlock(self, involved_agent: str):
        """Resolve deadlock by aborting lowest priority agent."""
        print(f"🔥 Deadlock detected involving {involved_agent}")

        # Find all agents in the cycle
        cycle_agents = self._find_cycle_agents(involved_agent)

        # Find lowest priority pending request
        lowest_priority = None
        lowest_mod = None

        for agent in cycle_agents:
            for key, mod in self.pending_requests.items():
                if key.startswith(f"{agent}:"):
                    if lowest_priority is None or mod.priority < lowest_priority:
                        lowest_priority = mod.priority
                        lowest_mod = mod

        if lowest_mod:
            # Abort the lowest priority request
            key = f"{lowest_mod.agent_id}:{lowest_mod.file_path}"
            if key in self.pending_requests:
                del self.pending_requests[key]
                print(f"🛑 Aborted {lowest_mod.agent_id}'s request for {lowest_mod.file_path}")

            # Clean up wait graph
            self._cleanup_wait_graph(lowest_mod.agent_id)

    def _find_cycle_agents(self, start_agent: str) -> Set[str]:
        """Find all agents involved in a deadlock cycle."""
        visited = set()
        rec_stack = set()
        cycle_agents = set()

        def dfs(agent: str, path: List[str]) -> bool:
            visited.add(agent)
            rec_stack.add(agent)
            path.append(agent)

            for neighbor in self.wait_graph.get(agent, set()):
                if neighbor in path:
                    # Found cycle - add all agents in the cycle
                    cycle_start = path.index(neighbor)
                    cycle_agents.update(path[cycle_start:])
                    cycle_agents.add(neighbor)
                    return True
                elif neighbor not in visited and dfs(neighbor, path):
                    return True

            rec_stack.remove(agent)
            path.pop()
            return False

        dfs(start_agent, [])

        # If no cycle found starting from start_agent, check all connected agents
        if not cycle_agents:
            for agent in self.wait_graph:
                if agent not in visited:
                    dfs(agent, [])

        return cycle_agents

    def _cleanup_wait_graph(self, agent_id: str):
        """Clean up wait graph after agent is removed."""
        # Remove agent from wait graph
        if agent_id in self.wait_graph:
            del self.wait_graph[agent_id]

        # Remove references to agent
        for _agent, waiting_for in self.wait_graph.items():
            waiting_for.discard(agent_id)

    def _schedule_merge(self, modification: FileModification, conflicts: List) -> bool:
        """Schedule merge operation for later (future enhancement)."""
        # Placeholder for merge strategy implementation
        return self._wait_for_resolution(modification)

    def release_file_lock(self, agent_id: str, file_path: str):
        """Release file lock and process pending requests."""
        file_path = str(Path(file_path).resolve())
        key = f"{agent_id}:{file_path}"

        # Release through interceptor
        self.interceptor.file_lock_manager.release_lock(agent_id, file_path)

        # Remove from active modifications
        if key in self.active_modifications:
            del self.active_modifications[key]

        # Process pending requests for this file
        self._process_pending_requests(file_path)

    def _process_pending_requests(self, file_path: str):
        """Process pending requests for a recently released file."""
        pending_for_file = []

        for key, mod in list(self.pending_requests.items()):
            if mod.file_path == file_path:
                pending_for_file.append((key, mod))

        # Sort by priority and timestamp
        pending_for_file.sort(key=lambda x: (x[1].priority, x[1].timestamp))

        # Try to satisfy pending requests
        for key, mod in pending_for_file:
            if self._acquire_lock(mod):
                del self.pending_requests[key]
                self._cleanup_wait_graph(mod.agent_id)

    def get_conflict_statistics(self) -> Dict[str, any]:
        """Get statistics on conflict prediction accuracy."""
        total_predicted = self.conflict_stats['predicted_conflicts']
        false_conflicts = self.conflict_stats['false_conflicts']

        if total_predicted > 0:
            false_conflict_rate = (false_conflicts / total_predicted * 100)
            accuracy = 100 - false_conflict_rate
        else:
            false_conflict_rate = 0
            accuracy = 0

        return {
            'predicted_conflicts': total_predicted,
            'actual_conflicts': self.conflict_stats['actual_conflicts'],
            'false_conflicts': false_conflicts,
            'resolved_conflicts': self.conflict_stats['resolved_conflicts'],
            'false_conflict_rate_percent': round(false_conflict_rate, 1),
            'prediction_accuracy_percent': round(accuracy, 1),
            'active_modifications': len(self.active_modifications),
            'pending_requests': len(self.pending_requests)
        }

    def configure_resolution_strategy(self, conflict_type: str, strategy: ResolutionStrategy):
        """Configure resolution strategy for a conflict type."""
        valid_types = ['default', 'compatible', 'incompatible', 'deadlock']
        if conflict_type in valid_types:
            self.resolution_strategies[conflict_type] = strategy
        else:
            raise ValueError(f"Invalid conflict type. Must be one of: {valid_types}")

    def analyze_ticket_requirements(self, ticket_content: str) -> Set[str]:
        """Analyze ticket to predict which files will be modified (legacy method)."""
        modifications = self.predict_file_modifications("temp", ticket_content)
        return {mod.file_path for mod in modifications}

    def check_conflict_potential(self, ticket1_files: Set[str], ticket2_files: Set[str]) -> float:
        """Calculate conflict potential between ticket file sets (legacy method)."""
        if not ticket1_files or not ticket2_files:
            return 0.0

        # Check for exact file matches
        exact_matches = ticket1_files & ticket2_files
        if exact_matches:
            return 1.0

        # Check for directory-level conflicts
        ticket1_dirs = {str(Path(f).parent) for f in ticket1_files}
        ticket2_dirs = {str(Path(f).parent) for f in ticket2_files}

        dir_overlap = ticket1_dirs & ticket2_dirs
        if dir_overlap:
            return 0.6

        return 0.0

    def schedule_tickets_smartly(self, tickets: Dict[str, str]) -> List[List[str]]:
        """Schedule tickets to minimize conflicts using enhanced prediction."""
        ticket_modifications = {}

        # Predict modifications for each ticket
        for ticket_id, content in tickets.items():
            modifications = self.predict_file_modifications(ticket_id, content)
            ticket_modifications[ticket_id] = modifications

        # Build enhanced conflict graph
        conflicts = {}
        for t1 in tickets:
            conflicts[t1] = set()
            for t2 in tickets:
                if t1 != t2:
                    # Check for any incompatible modifications
                    has_conflict = False
                    for mod1 in ticket_modifications[t1]:
                        for mod2 in ticket_modifications[t2]:
                            conflict_type = self.analyze_conflict(mod1, mod2)
                            if conflict_type == ConflictType.INCOMPATIBLE:
                                has_conflict = True
                                break
                        if has_conflict:
                            break

                    if has_conflict:
                        conflicts[t1].add(t2)

        # Graph coloring for optimal scheduling
        waves = []
        scheduled = set()

        while len(scheduled) < len(tickets):
            wave = []
            for ticket_id in tickets:
                if ticket_id in scheduled:
                    continue

                # Check if ticket conflicts with any in current wave
                can_add = True
                for other in wave:
                    if other in conflicts[ticket_id]:
                        can_add = False
                        break

                if can_add:
                    wave.append(ticket_id)
                    scheduled.add(ticket_id)

            if wave:
                waves.append(wave)
            else:
                # Add remaining tickets individually
                for ticket_id in tickets:
                    if ticket_id not in scheduled:
                        waves.append([ticket_id])
                        scheduled.add(ticket_id)
                break

        return waves
