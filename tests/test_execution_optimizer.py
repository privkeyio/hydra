"""Tests for the parallel execution optimizer."""

import os
import tempfile
import unittest

from src.hydra.parallel.execution_optimizer import (
    ExecutionOptimizer,
)
from src.hydra.parallel.group_analyzer import GroupAnalyzer
from src.hydra.validation.dependency_validator import FileFlow


class TestExecutionOptimizer(unittest.TestCase):
    """Test cases for ExecutionOptimizer."""

    def setUp(self):
        """Set up test fixtures."""
        self.optimizer = ExecutionOptimizer()
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def create_test_tickets_file(self, content: str) -> str:
        """Create a test tickets file with given content.

        Args:
            content: Markdown content for tickets file

        Returns:
            Path to created file

        """
        file_path = os.path.join(self.test_dir, "tickets.md")
        with open(file_path, "w") as f:
            f.write(content)
        return file_path

    def test_simple_linear_dependencies(self):
        """Test optimization with simple linear dependencies."""
        content = """
## Ticket 001: First ticket
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** First ticket in chain

**Required Input Files:**
- None

**Output Files:**
- output1.txt

**Acceptance Criteria:**
- [ ] Create output1.txt

---

## Ticket 002: Second ticket
**Status:** TODO
**Model:** balanced
**Dependencies:** 001
**Description:** Depends on first ticket

**Required Input Files:**
- output1.txt (from Ticket 001)

**Output Files:**
- output2.txt

**Acceptance Criteria:**
- [ ] Create output2.txt

---

## Ticket 003: Third ticket
**Status:** TODO
**Model:** balanced
**Dependencies:** 002
**Description:** Depends on second ticket

**Required Input Files:**
- output2.txt (from Ticket 002)

**Output Files:**
- output3.txt

**Acceptance Criteria:**
- [ ] Create output3.txt
"""
        file_path = self.create_test_tickets_file(content)
        plan = self.optimizer.optimize_execution(file_path)

        # Should have 3 sequential phases
        self.assertEqual(plan.total_phases, 3)
        self.assertEqual(plan.parallel_speedup, 1.0)
        self.assertEqual(len(plan.critical_path), 3)
        self.assertEqual(plan.critical_path, ["001", "002", "003"])

    def test_parallel_independent_tickets(self):
        """Test optimization with independent tickets that can run in parallel."""
        content = """
## Ticket 001: Independent A
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** Independent ticket A

**Required Input Files:**
- None

**Output Files:**
- outputA.txt

**Acceptance Criteria:**
- [ ] Create outputA.txt

---

## Ticket 002: Independent B
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** Independent ticket B

**Required Input Files:**
- None

**Output Files:**
- outputB.txt

**Acceptance Criteria:**
- [ ] Create outputB.txt

---

## Ticket 003: Independent C
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** Independent ticket C

**Required Input Files:**
- None

**Output Files:**
- outputC.txt

**Acceptance Criteria:**
- [ ] Create outputC.txt
"""
        file_path = self.create_test_tickets_file(content)
        plan = self.optimizer.optimize_execution(file_path)

        # Should have 1 phase with 3 parallel tickets
        self.assertEqual(plan.total_phases, 1)
        self.assertGreater(plan.parallel_speedup, 1.0)
        self.assertEqual(len(plan.groups[0].tickets), 3)
        self.assertTrue(plan.groups[0].can_parallel)

    def test_diamond_dependency_pattern(self):
        """Test optimization with diamond dependency pattern."""
        content = """
## Ticket 001: Base
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** Base ticket

**Required Input Files:**
- None

**Output Files:**
- base.txt

**Acceptance Criteria:**
- [ ] Create base.txt

---

## Ticket 002: Branch A
**Status:** TODO
**Model:** balanced
**Dependencies:** 001
**Description:** First branch

**Required Input Files:**
- base.txt (from Ticket 001)

**Output Files:**
- branchA.txt

**Acceptance Criteria:**
- [ ] Create branchA.txt

---

## Ticket 003: Branch B
**Status:** TODO
**Model:** balanced
**Dependencies:** 001
**Description:** Second branch

**Required Input Files:**
- base.txt (from Ticket 001)

**Output Files:**
- branchB.txt

**Acceptance Criteria:**
- [ ] Create branchB.txt

---

## Ticket 004: Merge
**Status:** TODO
**Model:** balanced
**Dependencies:** 002,003
**Description:** Merge branches

**Required Input Files:**
- branchA.txt (from Ticket 002)
- branchB.txt (from Ticket 003)

**Output Files:**
- merged.txt

**Acceptance Criteria:**
- [ ] Create merged.txt
"""
        file_path = self.create_test_tickets_file(content)
        plan = self.optimizer.optimize_execution(file_path)

        # Should have 3 phases: 001, then 002+003 parallel, then 004
        self.assertEqual(plan.total_phases, 3)
        self.assertGreater(plan.parallel_speedup, 1.0)

        # Check phase structure
        phase_tickets = [set(g.tickets) for g in plan.groups]
        self.assertIn({"001"}, phase_tickets)
        self.assertIn({"002", "003"}, phase_tickets)
        self.assertIn({"004"}, phase_tickets)

    def test_complex_mixed_dependencies(self):
        """Test optimization with complex mixed dependency patterns."""
        content = """
## Ticket 001: Setup
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** Setup

**Required Input Files:**
- None

**Output Files:**
- setup.txt

**Acceptance Criteria:**
- [ ] Setup complete

---

## Ticket 002: Feature A
**Status:** TODO
**Model:** balanced
**Dependencies:** 001
**Description:** Feature A

**Required Input Files:**
- setup.txt (from Ticket 001)

**Output Files:**
- featureA.txt

**Acceptance Criteria:**
- [ ] Feature A complete

---

## Ticket 003: Feature B
**Status:** TODO
**Model:** balanced
**Dependencies:** 001
**Description:** Feature B

**Required Input Files:**
- setup.txt (from Ticket 001)

**Output Files:**
- featureB.txt

**Acceptance Criteria:**
- [ ] Feature B complete

---

## Ticket 004: Feature C
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** Independent feature C

**Required Input Files:**
- None

**Output Files:**
- featureC.txt

**Acceptance Criteria:**
- [ ] Feature C complete

---

## Ticket 005: Integration
**Status:** TODO
**Model:** balanced
**Dependencies:** 002,003,004
**Description:** Integrate all features

**Required Input Files:**
- featureA.txt (from Ticket 002)
- featureB.txt (from Ticket 003)
- featureC.txt (from Ticket 004)

**Output Files:**
- integration.txt

**Acceptance Criteria:**
- [ ] Integration complete

---

## Ticket 006: Testing
**Status:** TODO
**Model:** balanced
**Dependencies:** 005
**Description:** Test integration

**Required Input Files:**
- integration.txt (from Ticket 005)

**Output Files:**
- test_results.txt

**Acceptance Criteria:**
- [ ] Tests pass
"""
        file_path = self.create_test_tickets_file(content)
        plan = self.optimizer.optimize_execution(file_path)

        # Should identify parallel opportunities
        self.assertGreater(plan.parallel_speedup, 1.0)
        self.assertIn("optimization_report", plan.__dict__)

        # Check that independent tickets can run in parallel
        parallel_groups = [
            g for g in plan.groups
            if g.can_parallel and len(g.tickets) > 1
        ]
        self.assertGreater(len(parallel_groups), 0)

    def test_max_parallel_constraint(self):
        """Test that max_parallel constraint is respected."""
        content = """
## Ticket 001: Task 1
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Output Files:**
- file1.txt
**Acceptance Criteria:**
- [ ] Complete

---

## Ticket 002: Task 2
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Output Files:**
- file2.txt
**Acceptance Criteria:**
- [ ] Complete

---

## Ticket 003: Task 3
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Output Files:**
- file3.txt
**Acceptance Criteria:**
- [ ] Complete

---

## Ticket 004: Task 4
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Output Files:**
- file4.txt
**Acceptance Criteria:**
- [ ] Complete

---

## Ticket 005: Task 5
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Output Files:**
- file5.txt
**Acceptance Criteria:**
- [ ] Complete

---

## Ticket 006: Task 6
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Output Files:**
- file6.txt
**Acceptance Criteria:**
- [ ] Complete
"""
        file_path = self.create_test_tickets_file(content)
        plan = self.optimizer.optimize_execution(file_path, max_parallel=3)

        # Check that no group has more than 3 tickets
        for group in plan.groups:
            self.assertLessEqual(len(group.tickets), 3)

    def test_circular_dependency_handling(self):
        """Test handling of circular dependencies."""
        content = """
## Ticket 001: First
**Status:** TODO
**Model:** balanced
**Dependencies:** 003
**Description:** Has circular dependency

**Output Files:**
- file1.txt

**Acceptance Criteria:**
- [ ] Complete

---

## Ticket 002: Second
**Status:** TODO
**Model:** balanced
**Dependencies:** 001
**Description:** Part of chain

**Output Files:**
- file2.txt

**Acceptance Criteria:**
- [ ] Complete

---

## Ticket 003: Third
**Status:** TODO
**Model:** balanced
**Dependencies:** 002
**Description:** Creates circle

**Output Files:**
- file3.txt

**Acceptance Criteria:**
- [ ] Complete
"""
        file_path = self.create_test_tickets_file(content)
        plan = self.optimizer.optimize_execution(file_path)

        # Should create fallback plan
        self.assertEqual(plan.total_phases, 0)
        self.assertIn("validation errors", plan.optimization_report.lower())

    def test_bottleneck_identification(self):
        """Test identification of execution bottlenecks."""
        content = """
## Ticket 001: Start
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Output Files:**
- start.txt
**Acceptance Criteria:**
- [ ] Complete

---

## Ticket 002: Bottleneck
**Status:** TODO
**Model:** smart
**Dependencies:** 001
**Description:** Complex task that takes long
**Output Files:**
- bottleneck.txt
**Acceptance Criteria:**
- [ ] Complex processing
- [ ] Multiple validations
- [ ] Performance testing
- [ ] Documentation

---

## Ticket 003: Quick A
**Status:** TODO
**Model:** balanced
**Dependencies:** 002
**Output Files:**
- quickA.txt
**Acceptance Criteria:**
- [ ] Simple task

---

## Ticket 004: Quick B
**Status:** TODO
**Model:** balanced
**Dependencies:** 002
**Output Files:**
- quickB.txt
**Acceptance Criteria:**
- [ ] Simple task
"""
        file_path = self.create_test_tickets_file(content)
        plan = self.optimizer.optimize_execution(file_path)

        # Identify bottlenecks
        _ = self.optimizer.identify_bottlenecks(plan)

        # Should identify ticket 002 as part of critical path
        self.assertIn("002", plan.critical_path)

    def test_optimization_suggestions(self):
        """Test generation of optimization suggestions."""
        content = """
## Ticket 001: A
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Output Files:**
- a.txt
**Acceptance Criteria:**
- [ ] Complete

---

## Ticket 002: B
**Status:** TODO
**Model:** balanced
**Dependencies:** 001
**Output Files:**
- b.txt
**Acceptance Criteria:**
- [ ] Complete

---

## Ticket 003: C
**Status:** TODO
**Model:** balanced
**Dependencies:** 002
**Output Files:**
- c.txt
**Acceptance Criteria:**
- [ ] Complete

---

## Ticket 004: D
**Status:** TODO
**Model:** balanced
**Dependencies:** 003
**Output Files:**
- d.txt
**Acceptance Criteria:**
- [ ] Complete
"""
        file_path = self.create_test_tickets_file(content)
        plan = self.optimizer.optimize_execution(file_path)

        # Get suggestions
        suggestions = self.optimizer.suggest_optimizations(plan)
        self.assertIsInstance(suggestions, list)
        self.assertGreater(len(suggestions), 0)

        # Should suggest breaking dependencies for low speedup
        if plan.parallel_speedup < 1.5:
            suggestion_text = " ".join(suggestions)
            self.assertIn("parallel", suggestion_text.lower())


class TestGroupAnalyzer(unittest.TestCase):
    """Test cases for GroupAnalyzer."""

    def setUp(self):
        """Set up test fixtures."""
        self.analyzer = GroupAnalyzer()

    def test_dependency_level_calculation(self):
        """Test calculation of dependency levels."""
        dependency_graph = {
            "001": [],
            "002": ["001"],
            "003": ["001"],
            "004": ["002", "003"],
        }
        file_flows = []
        topological_order = ["001", "002", "003", "004"]

        analysis = self.analyzer.analyze_dependencies(
            dependency_graph, file_flows, topological_order
        )

        # Check levels
        self.assertEqual(analysis.dependency_levels["001"], 0)
        self.assertEqual(analysis.dependency_levels["002"], 1)
        self.assertEqual(analysis.dependency_levels["003"], 1)
        self.assertEqual(analysis.dependency_levels["004"], 2)

    def test_parallel_opportunity_identification(self):
        """Test identification of parallel execution opportunities."""
        dependency_graph = {
            "001": [],
            "002": [],
            "003": [],
            "004": ["001", "002", "003"],
        }
        file_flows = []
        topological_order = ["001", "002", "003", "004"]

        analysis = self.analyzer.analyze_dependencies(
            dependency_graph, file_flows, topological_order
        )

        # Should identify 001, 002, 003 as parallel
        parallel_tickets = set()
        for opportunity in analysis.parallel_opportunities:
            parallel_tickets.update(opportunity)

        self.assertIn("001", parallel_tickets)
        self.assertIn("002", parallel_tickets)
        self.assertIn("003", parallel_tickets)

    def test_file_conflict_detection(self):
        """Test detection of file conflicts between tickets."""
        dependency_graph = {
            "001": [],
            "002": [],
            "003": ["001", "002"],
        }
        file_flows = [
            FileFlow(source_ticket="001", target_ticket="003", file_path="file1.txt"),
            FileFlow(source_ticket="002", target_ticket="003", file_path="file2.txt"),
        ]
        topological_order = ["001", "002", "003"]

        analysis = self.analyzer.analyze_dependencies(
            dependency_graph, file_flows, topological_order
        )

        # Check that file flows are considered
        self.assertEqual(len(analysis.groups), 2)

    def test_dependency_chain_finding(self):
        """Test finding dependency chains."""
        self.analyzer.dependency_graph = {
            "001": [],
            "002": ["001"],
            "003": ["002"],
            "004": ["003"],
        }
        self.analyzer.topological_order = ["001", "002", "003", "004"]
        self.analyzer._build_reverse_graph()

        chains = self.analyzer.find_dependency_chains()

        # Should find the chain 001 -> 002 -> 003 -> 004
        self.assertGreater(len(chains), 0)
        longest_chain = max(chains, key=len)
        self.assertEqual(len(longest_chain), 4)

    def test_parallelism_metrics(self):
        """Test calculation of parallelism metrics."""
        dependency_graph = {
            "001": [],
            "002": [],
            "003": ["001"],
            "004": ["002"],
            "005": ["003", "004"],
        }
        file_flows = []
        topological_order = ["001", "002", "003", "004", "005"]

        analysis = self.analyzer.analyze_dependencies(
            dependency_graph, file_flows, topological_order
        )

        metrics = self.analyzer.calculate_parallelism_metrics(analysis)

        self.assertEqual(metrics["total_tickets"], 5)
        self.assertGreater(metrics["parallelization_ratio"], 0)
        self.assertGreater(metrics["max_parallelism"], 1)

    def test_visualization_generation(self):
        """Test generation of text visualization."""
        dependency_graph = {
            "001": [],
            "002": ["001"],
            "003": ["001"],
            "004": ["002", "003"],
        }
        file_flows = []
        topological_order = ["001", "002", "003", "004"]

        analysis = self.analyzer.analyze_dependencies(
            dependency_graph, file_flows, topological_order
        )

        visualization = self.analyzer.visualize_groups(analysis)

        self.assertIsInstance(visualization, str)
        self.assertIn("Phase", visualization)
        self.assertIn("parallel", visualization.lower())

    def test_dependency_change_recommendations(self):
        """Test generation of dependency change recommendations."""
        # Create a long chain that could be parallelized
        dependency_graph = {
            "001": [],
            "002": ["001"],
            "003": ["002"],
            "004": ["003"],
            "005": ["004"],
        }
        file_flows = []
        topological_order = ["001", "002", "003", "004", "005"]

        analysis = self.analyzer.analyze_dependencies(
            dependency_graph, file_flows, topological_order
        )

        recommendations = self.analyzer.recommend_dependency_changes(analysis)

        self.assertIsInstance(recommendations, list)
        self.assertGreater(len(recommendations), 0)

        # Should recommend breaking long chains
        rec_text = " ".join(recommendations)
        self.assertIn("chain", rec_text.lower())


if __name__ == "__main__":
    unittest.main()

