"""Automatic dependency detection for ticket generation."""

import ast
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set


class DependencyDetector:
    """Detects dependencies between components for intelligent ticket ordering."""

    def __init__(self, project_path: str):
        """Initialize detector with project path.

        Args:
            project_path: Root path of the project

        """
        self.project_path = Path(project_path)
        self.module_graph: Dict[str, Set[str]] = defaultdict(set)
        self.database_operations: Dict[str, List[str]] = defaultdict(list)
        self.api_endpoints: Dict[str, List[str]] = defaultdict(list)
        self.config_dependencies: Set[str] = set()

    def detect_dependencies(self, tasks: List[Dict]) -> Dict[str, List[str]]:
        """Detect dependencies between tasks based on code analysis.

        Args:
            tasks: List of task dictionaries with file/component info

        Returns:
            Mapping of task IDs to their dependencies

        """
        dependencies = {}

        # Build component map
        component_map = {}
        for i, task in enumerate(tasks):
            task_id = f"{i+1:03d}"
            components = self._extract_components(task)
            component_map[task_id] = components
            dependencies[task_id] = []

        # Analyze dependencies
        for task_id, components in component_map.items():
            for other_id, other_components in component_map.items():
                if task_id == other_id:
                    continue

                if self._has_dependency(components, other_components):
                    dependencies[task_id].append(other_id)

        # Remove circular dependencies
        dependencies = self._resolve_circular_dependencies(dependencies)

        # Order by logical progression
        dependencies = self._apply_logical_ordering(dependencies, tasks)

        return dependencies

    def _extract_components(self, task: Dict) -> Dict[str, Set[str]]:
        """Extract components mentioned in a task.

        Args:
            task: Task dictionary

        Returns:
            Components dictionary with types and names

        """
        components = {
            "files": set(),
            "modules": set(),
            "functions": set(),
            "classes": set(),
            "database": set(),
            "api": set(),
            "config": set(),
        }

        text = f"{task.get('title', '')} {task.get('description', '')} {' '.join(task.get('criteria', []))}"

        # Extract file paths
        file_patterns = [
            r'(?:src/|tests/|lib/)[a-zA-Z0-9_/]+\.(?:py|js|ts|jsx|tsx)',
            r'[a-zA-Z0-9_]+\.(?:py|js|ts|jsx|tsx)',
        ]
        for pattern in file_patterns:
            matches = re.findall(pattern, text)
            components["files"].update(matches)

        # Extract Python modules
        module_pattern = r'(?:from|import)\s+([a-zA-Z0-9_.]+)'
        matches = re.findall(module_pattern, text)
        components["modules"].update(matches)

        # Extract function/class names
        func_pattern = r'(?:def|function|class)\s+([a-zA-Z0-9_]+)'
        matches = re.findall(func_pattern, text)
        components["functions"].update(matches)

        # Extract database operations
        db_patterns = [
            r'(?:CREATE|ALTER|DROP|UPDATE|INSERT|DELETE)\s+(?:TABLE|INDEX|DATABASE)',
            r'migration',
            r'schema',
            r'database',
        ]
        for pattern in db_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                components["database"].add(pattern.lower())

        # Extract API endpoints
        api_patterns = [
            r'(?:GET|POST|PUT|DELETE|PATCH)\s+/[a-zA-Z0-9_/]+',
            r'@app\.(?:get|post|put|delete)',
            r'router\.(?:get|post|put|delete)',
        ]
        for pattern in api_patterns:
            matches = re.findall(pattern, text)
            components["api"].update(matches)

        # Extract configuration
        config_patterns = [
            r'(?:config|settings|env|environment)',
            r'\.env',
            r'config\.(?:json|yaml|yml|toml)',
        ]
        for pattern in config_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                components["config"].add(pattern.lower())

        return components

    def _has_dependency(self, components1: Dict, components2: Dict) -> bool:
        """Check if components1 depends on components2.

        Args:
            components1: First component set
            components2: Second component set

        Returns:
            True if dependency exists

        """
        # Database migrations must happen before code changes
        if components2["database"] and components1["files"]:
            if "migration" in str(components2["database"]):
                return True

        # Config must be set up before using it
        if components2["config"] and (components1["api"] or components1["modules"]):
            return True

        # Base classes/interfaces before implementations
        if components2["classes"]:
            for cls in components2["classes"]:
                if "base" in cls.lower() or "interface" in cls.lower() or "abstract" in cls.lower():
                    if components1["classes"] and any(cls.lower() in c.lower() for c in components1["classes"]):
                        return True

        # Shared modules before dependent modules
        shared_indicators = ["utils", "common", "shared", "core", "base"]
        for module in components2["modules"]:
            if any(ind in module.lower() for ind in shared_indicators):
                if components1["modules"] and module in str(components1["modules"]):
                    return True

        # API setup before API usage
        if "router" in str(components2["api"]) and "endpoint" in str(components1["api"]):
            return True

        # File creation before file modification
        for file2 in components2["files"]:
            for file1 in components1["files"]:
                if file2 == file1:
                    # Check if one creates and other modifies
                    if "create" in str(components2) and "modify" in str(components1):
                        return True

        return False

    def _resolve_circular_dependencies(self, dependencies: Dict[str, List[str]]) -> Dict[str, List[str]]:
        """Resolve circular dependencies by breaking cycles.

        Args:
            dependencies: Original dependency map

        Returns:
            Cleaned dependency map without cycles

        """
        # Detect cycles using DFS
        def has_cycle(node: str, visited: Set[str], rec_stack: Set[str]) -> bool:
            visited.add(node)
            rec_stack.add(node)

            for neighbor in dependencies.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor, visited, rec_stack):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        # Find and break cycles
        cleaned = {k: list(v) for k, v in dependencies.items()}

        for node in list(dependencies.keys()):
            visited = set()
            rec_stack = set()
            if has_cycle(node, visited, rec_stack):
                # Break cycle by removing the back edge
                for dep in dependencies[node]:
                    if dep in dependencies and node in dependencies[dep]:
                        # Remove the dependency with higher ID to maintain order
                        if int(node) > int(dep):
                            cleaned[node].remove(dep)
                        else:
                            cleaned[dep].remove(node)

        return cleaned

    def _apply_logical_ordering(self, dependencies: Dict[str, List[str]], tasks: List[Dict]) -> Dict[str, List[str]]:
        """Apply logical ordering rules to dependencies.

        Args:
            dependencies: Current dependency map
            tasks: Original task list

        Returns:
            Updated dependency map with logical ordering

        """
        ordered = {k: list(v) for k, v in dependencies.items()}

        # Define task types and their typical order
        task_types = {
            "setup": 0,
            "config": 1,
            "database": 2,
            "migration": 2,
            "model": 3,
            "schema": 3,
            "core": 4,
            "api": 5,
            "service": 5,
            "ui": 6,
            "frontend": 6,
            "test": 7,
            "documentation": 8,
        }

        # Categorize tasks
        task_categories = {}
        for i, task in enumerate(tasks):
            task_id = f"{i+1:03d}"
            text = f"{task.get('title', '')} {task.get('description', '')}".lower()

            category = "general"
            min_priority = 999
            for task_type, priority in task_types.items():
                if task_type in text and priority < min_priority:
                    category = task_type
                    min_priority = priority

            task_categories[task_id] = (category, min_priority)

        # Add dependencies based on logical ordering
        for task_id in ordered:
            task_cat, task_priority = task_categories[task_id]

            for other_id in ordered:
                if task_id == other_id:
                    continue

                other_cat, other_priority = task_categories[other_id]

                # Tasks with higher priority should be dependencies
                if other_priority < task_priority - 1:  # Allow some parallelism
                    if other_id not in ordered[task_id]:
                        # Only add if it makes sense
                        if self._is_logical_dependency(task_cat, other_cat):
                            ordered[task_id].append(other_id)

        # Remove redundant dependencies (transitive reduction)
        for task_id in ordered:
            direct_deps = set(ordered[task_id])
            indirect_deps = set()

            for dep in direct_deps:
                indirect_deps.update(ordered.get(dep, []))

            # Remove dependencies that are indirect
            ordered[task_id] = [d for d in direct_deps if d not in indirect_deps]

        return ordered

    def _is_logical_dependency(self, task_type: str, dep_type: str) -> bool:
        """Check if dependency makes logical sense.

        Args:
            task_type: Type of the task
            dep_type: Type of the potential dependency

        Returns:
            True if dependency is logical

        """
        logical_deps = {
            "test": ["api", "service", "model", "core"],
            "ui": ["api", "service"],
            "frontend": ["api", "service"],
            "api": ["model", "schema", "database", "core"],
            "service": ["model", "schema", "database", "core"],
            "model": ["database", "migration"],
            "schema": ["database", "migration"],
            "core": ["config", "setup"],
            "database": ["config", "setup"],
            "migration": ["setup"],
            "config": ["setup"],
        }

        return dep_type in logical_deps.get(task_type, [])

    def analyze_file_dependencies(self, file_path: str) -> Set[str]:
        """Analyze dependencies for a specific file.

        Args:
            file_path: Path to analyze

        Returns:
            Set of dependent file paths

        """
        deps = set()
        full_path = self.project_path / file_path

        if not full_path.exists():
            return deps

        try:
            content = full_path.read_text()

            if full_path.suffix == '.py':
                tree = ast.parse(content)

                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            # Convert module to potential file path
                            potential_path = alias.name.replace('.', '/') + '.py'
                            if (self.project_path / potential_path).exists():
                                deps.add(potential_path)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module and not node.level:  # Not relative import
                            potential_path = node.module.replace('.', '/') + '.py'
                            if (self.project_path / potential_path).exists():
                                deps.add(potential_path)

            elif full_path.suffix in ['.js', '.ts', '.jsx', '.tsx']:
                # JavaScript/TypeScript imports
                import_patterns = [
                    r'import\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]',
                    r'require\s*\([\'"]([^\'"]+)[\'"]\)',
                ]

                for pattern in import_patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        if match.startswith('.'):
                            # Relative import
                            resolved = (full_path.parent / match).resolve()
                            if resolved.exists():
                                deps.add(str(resolved.relative_to(self.project_path)))

        except Exception:
            pass

        return deps

    def suggest_ticket_grouping(self, components: List[str]) -> List[List[str]]:
        """Suggest how to group components into tickets.

        Args:
            components: List of components/files to work on

        Returns:
            Suggested groupings of components

        """
        groups = []

        # Analyze component relationships
        component_deps = {}
        for component in components:
            component_deps[component] = self.analyze_file_dependencies(component)

        # Group tightly coupled components
        processed = set()
        for component in components:
            if component in processed:
                continue

            group = [component]
            processed.add(component)

            # Find components that are tightly coupled
            for other in components:
                if other in processed:
                    continue

                # Check if they depend on each other
                if (other in component_deps.get(component, set()) or
                    component in component_deps.get(other, set())):
                    group.append(other)
                    processed.add(other)

            groups.append(group)

        # Merge small groups if they're related
        if len(groups) > 5:
            merged_groups = []
            processed_indices = set()

            for i, group1 in enumerate(groups):
                if i in processed_indices:
                    continue

                merged = list(group1)
                processed_indices.add(i)

                if len(merged) == 1:  # Try to merge single-item groups
                    for j, group2 in enumerate(groups):
                        if j <= i or j in processed_indices:
                            continue
                        if len(group2) == 1:
                            # Check if they should be merged
                            if self._should_merge_groups(merged, group2):
                                merged.extend(group2)
                                processed_indices.add(j)
                                if len(merged) >= 3:
                                    break

                merged_groups.append(merged)

            groups = merged_groups

        return groups

    def _should_merge_groups(self, group1: List[str], group2: List[str]) -> bool:
        """Check if two groups should be merged.

        Args:
            group1: First group of components
            group2: Second group of components

        Returns:
            True if groups should be merged

        """
        # Check if they're in the same directory
        if group1 and group2:
            dir1 = Path(group1[0]).parent
            dir2 = Path(group2[0]).parent
            if dir1 == dir2:
                return True

        # Check if they share common patterns
        patterns = ["test", "model", "view", "controller", "service", "api"]
        for pattern in patterns:
            if any(pattern in g for g in group1) and any(pattern in g for g in group2):
                return True

        return False
