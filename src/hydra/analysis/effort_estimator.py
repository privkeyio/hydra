"""Effort estimation for tickets based on codebase analysis."""

from typing import Dict, List


class EffortEstimator:
    """Estimates effort for tickets based on code complexity and scope."""

    def __init__(self, codebase_analysis: Dict):
        """Initialize estimator with codebase analysis.

        Args:
            codebase_analysis: Analysis results from CodebaseAnalyzer

        """
        self.analysis = codebase_analysis
        self.base_velocity = self._calculate_base_velocity()

    def _calculate_base_velocity(self) -> float:
        """Calculate base development velocity from codebase metrics.

        Returns:
            Base velocity factor

        """
        # Factors that affect velocity
        velocity = 1.0

        # Adjust based on project size
        total_loc = self.analysis['size_metrics']['total_loc']
        if total_loc < 1000:
            velocity *= 1.2  # Small project, faster iteration
        elif total_loc > 10000:
            velocity *= 0.8  # Large project, slower due to complexity
        elif total_loc > 50000:
            velocity *= 0.6  # Very large, significant overhead

        # Adjust based on test coverage
        test_count = self.analysis['existing_tests']['test_count']
        if test_count > 20:
            velocity *= 1.1  # Good test coverage, safer changes
        elif test_count == 0:
            velocity *= 0.9  # No tests, riskier changes

        # Adjust based on documentation
        if self.analysis['documentation']['has_readme']:
            velocity *= 1.05
        if self.analysis['documentation']['docstring_coverage'] > 0.5:
            velocity *= 1.05

        # Adjust based on CI/CD
        if self.analysis['ci_cd']['automated_tests']:
            velocity *= 1.1

        return velocity

    def estimate_ticket_effort(self, ticket: Dict, complexity_score: int) -> Dict[str, any]:
        """Estimate effort for a single ticket.

        Args:
            ticket: Ticket dictionary with title, description, criteria
            complexity_score: Complexity score from AST analysis

        Returns:
            Effort estimation with hours and confidence

        """
        # Base hours by complexity
        base_hours = {
            1: 0.5,   # Trivial
            2: 1,     # Simple
            3: 2,     # Easy
            5: 4,     # Moderate
            8: 8,     # Complex
            13: 16,   # Very complex
            21: 32,   # Extremely complex
        }

        # Map complexity score to nearest Fibonacci number
        fib_complexity = min(base_hours.keys(),
                            key=lambda x: abs(x - complexity_score))

        hours = base_hours[fib_complexity]

        # Adjust based on ticket characteristics
        criteria_count = len(ticket.get('criteria', []))
        hours *= (1 + criteria_count * 0.1)  # Each criterion adds 10%

        # Adjust for dependencies
        dep_count = len(ticket.get('dependencies', []))
        if dep_count > 0:
            hours *= (1 + dep_count * 0.05)  # Each dependency adds 5%

        # Adjust based on ticket type
        title = ticket.get('title', '').lower()
        description = ticket.get('description', '').lower()

        if 'refactor' in title or 'refactor' in description:
            hours *= 1.3  # Refactoring takes longer
        elif 'bug' in title or 'fix' in title:
            hours *= 0.8  # Bugs often quicker than features
        elif 'test' in title or 'test' in description:
            hours *= 0.7  # Writing tests is usually faster
        elif 'documentation' in title or 'docs' in title:
            hours *= 0.5  # Documentation is quicker

        # Apply velocity factor
        hours /= self.base_velocity

        # Calculate confidence based on analysis quality
        confidence = self._calculate_confidence(ticket, complexity_score)

        # Round to sensible values
        if hours < 1:
            hours = round(hours * 2) / 2  # Round to 0.5
        else:
            hours = round(hours)

        return {
            'hours': hours,
            'range': (hours * 0.7, hours * 1.5),  # -30% to +50%
            'confidence': confidence,
            'complexity_level': self._get_complexity_label(fib_complexity),
            'factors': self._get_estimation_factors(ticket, complexity_score)
        }

    def _calculate_confidence(self, ticket: Dict, complexity_score: int) -> str:
        """Calculate confidence level for estimate.

        Args:
            ticket: Ticket dictionary
            complexity_score: Complexity score

        Returns:
            Confidence level (high/medium/low)

        """
        confidence_score = 0

        # Clear acceptance criteria increase confidence
        if len(ticket.get('criteria', [])) > 3:
            confidence_score += 2
        elif len(ticket.get('criteria', [])) > 0:
            confidence_score += 1

        # Known complexity increases confidence
        if complexity_score > 0:
            confidence_score += 1

        # Clear description increases confidence
        if len(ticket.get('description', '')) > 50:
            confidence_score += 1

        # Files identified increases confidence
        if any(f in str(ticket) for f in ['.py', '.js', '.ts']):
            confidence_score += 1

        if confidence_score >= 4:
            return 'high'
        elif confidence_score >= 2:
            return 'medium'
        else:
            return 'low'

    def _get_complexity_label(self, score: int) -> str:
        """Get human-readable complexity label.

        Args:
            score: Fibonacci complexity score

        Returns:
            Complexity label

        """
        labels = {
            1: 'trivial',
            2: 'simple',
            3: 'easy',
            5: 'moderate',
            8: 'complex',
            13: 'very_complex',
            21: 'extremely_complex'
        }
        return labels.get(score, 'unknown')

    def _get_estimation_factors(self, ticket: Dict, complexity_score: int) -> List[str]:
        """Get factors that influenced the estimation.

        Args:
            ticket: Ticket dictionary
            complexity_score: Complexity score

        Returns:
            List of influencing factors

        """
        factors = []

        if complexity_score > 10:
            factors.append('high_code_complexity')
        elif complexity_score > 5:
            factors.append('moderate_code_complexity')

        if len(ticket.get('dependencies', [])) > 2:
            factors.append('multiple_dependencies')

        if len(ticket.get('criteria', [])) > 5:
            factors.append('many_acceptance_criteria')

        title = ticket.get('title', '').lower()
        if 'refactor' in title:
            factors.append('refactoring_task')
        if 'migration' in title:
            factors.append('data_migration')
        if 'api' in title:
            factors.append('api_changes')

        if self.analysis['size_metrics']['total_loc'] > 10000:
            factors.append('large_codebase')

        if self.analysis['existing_tests']['test_count'] == 0:
            factors.append('no_test_coverage')

        return factors

    def estimate_project_timeline(self, tickets: List[Dict]) -> Dict[str, any]:
        """Estimate overall project timeline.

        Args:
            tickets: List of all tickets

        Returns:
            Project timeline estimation

        """
        total_hours = 0
        estimates = []

        for ticket in tickets:
            # Simple complexity estimation based on model
            complexity_map = {
                'fast': 3,
                'balanced': 5,
                'smart': 8,
                'coder': 13
            }
            complexity = complexity_map.get(ticket.get('model', 'balanced'), 5)

            estimate = self.estimate_ticket_effort(ticket, complexity)
            estimates.append(estimate)
            total_hours += estimate['hours']

        # Calculate parallel execution potential
        dependency_graph = self._build_dependency_graph(tickets)
        critical_path_hours = self._calculate_critical_path(dependency_graph, estimates)

        # Estimate with different team sizes
        timelines = {
            'sequential': {
                'hours': total_hours,
                'days': total_hours / 8,
                'weeks': total_hours / 40
            },
            'parallel_2_devs': {
                'hours': max(critical_path_hours, total_hours / 2),
                'days': max(critical_path_hours, total_hours / 2) / 8,
                'weeks': max(critical_path_hours, total_hours / 2) / 40
            },
            'parallel_3_devs': {
                'hours': max(critical_path_hours, total_hours / 3),
                'days': max(critical_path_hours, total_hours / 3) / 8,
                'weeks': max(critical_path_hours, total_hours / 3) / 40
            }
        }

        # Add buffer for coordination overhead
        for timeline in timelines.values():
            timeline['with_buffer'] = {
                'hours': timeline['hours'] * 1.2,
                'days': timeline['days'] * 1.2,
                'weeks': timeline['weeks'] * 1.2
            }

        return {
            'total_effort_hours': total_hours,
            'critical_path_hours': critical_path_hours,
            'timelines': timelines,
            'ticket_count': len(tickets),
            'average_ticket_hours': total_hours / len(tickets) if tickets else 0,
            'complexity_distribution': self._get_complexity_distribution(estimates)
        }

    def _build_dependency_graph(self, tickets: List[Dict]) -> Dict[str, List[str]]:
        """Build dependency graph from tickets.

        Args:
            tickets: List of tickets

        Returns:
            Dependency graph

        """
        graph = {}
        for i, ticket in enumerate(tickets):
            ticket_id = str(i)
            deps = []
            for dep in ticket.get('dependencies', []):
                if isinstance(dep, str) and dep.isdigit():
                    dep_idx = int(dep) - 1
                    if 0 <= dep_idx < len(tickets):
                        deps.append(str(dep_idx))
            graph[ticket_id] = deps
        return graph

    def _calculate_critical_path(self, graph: Dict[str, List[str]],
                                 estimates: List[Dict]) -> float:
        """Calculate critical path through dependency graph.

        Args:
            graph: Dependency graph
            estimates: Effort estimates for each ticket

        Returns:
            Critical path duration in hours

        """
        if not graph:
            return 0

        # Simple critical path calculation
        path_lengths = {}

        def calculate_path_length(node: str) -> float:
            if node in path_lengths:
                return path_lengths[node]

            node_idx = int(node)
            node_hours = estimates[node_idx]['hours'] if node_idx < len(estimates) else 0

            deps = graph.get(node, [])
            if not deps:
                path_lengths[node] = node_hours
            else:
                max_dep_path = max(calculate_path_length(dep) for dep in deps)
                path_lengths[node] = node_hours + max_dep_path

            return path_lengths[node]

        # Calculate path length for all nodes
        max_path = 0
        for node in graph:
            path_length = calculate_path_length(node)
            max_path = max(max_path, path_length)

        return max_path

    def _get_complexity_distribution(self, estimates: List[Dict]) -> Dict[str, int]:
        """Get distribution of complexity levels.

        Args:
            estimates: List of effort estimates

        Returns:
            Complexity distribution

        """
        distribution = {
            'trivial': 0,
            'simple': 0,
            'easy': 0,
            'moderate': 0,
            'complex': 0,
            'very_complex': 0,
            'extremely_complex': 0
        }

        for estimate in estimates:
            level = estimate.get('complexity_level', 'unknown')
            if level in distribution:
                distribution[level] += 1

        return distribution
