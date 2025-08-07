import unittest
import json
import tempfile
from pathlib import Path

from hydra.routing.model_router import (
    ModelRouter, ModelType, ComplexityLevel, TaskComplexityAnalyzer,
    CostEstimator, RoutingDecision
)


class TestTaskComplexityAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = TaskComplexityAnalyzer()

    def test_simple_tasks(self):
        tasks = [
            "read the config file",
            "list all files in directory", 
            "show current status",
            "print the results"
        ]
        
        for task in tasks:
            complexity = self.analyzer.analyze_task(task)
            self.assertEqual(complexity, ComplexityLevel.SIMPLE)

    def test_moderate_tasks(self):
        tasks = [
            "create a new function",
            "add error handling", 
            "implement security authentication"
        ]
        
        for task in tasks:
            complexity = self.analyzer.analyze_task(task)
            self.assertEqual(complexity, ComplexityLevel.MODERATE)

    def test_complex_tasks(self):
        complexity = self.analyzer.analyze_task("design system architecture")
        self.assertEqual(complexity, ComplexityLevel.COMPLEX)

    def test_critical_tasks(self):
        tasks = [
            "prepare for production deployment",
            "handle critical system failure"
        ]
        
        for task in tasks:
            complexity = self.analyzer.analyze_task(task)
            self.assertEqual(complexity, ComplexityLevel.CRITICAL)

    def test_context_influence(self):
        task = "modify the code"
        
        simple_context = {"file_count": 1}
        complexity = self.analyzer.analyze_task(task, simple_context)
        self.assertEqual(complexity, ComplexityLevel.MODERATE)
        
        complex_context = {"file_count": 15, "involves_database": True}
        complexity = self.analyzer.analyze_task(task, complex_context)
        self.assertIn(complexity, [ComplexityLevel.MODERATE, ComplexityLevel.COMPLEX])

    def test_empty_task(self):
        complexity = self.analyzer.analyze_task("")
        self.assertEqual(complexity, ComplexityLevel.SIMPLE)


class TestCostEstimator(unittest.TestCase):
    def setUp(self):
        self.estimator = CostEstimator()

    def test_token_estimation(self):
        text = "This is a simple test with ten words total"
        tokens = self.estimator.estimate_tokens(text)
        self.assertGreater(tokens, 8)
        self.assertLess(tokens, 15)

    def test_sonnet_cost_calculation(self):
        input_text = "create a simple function"
        cost = self.estimator.estimate_cost(ModelType.SONNET, input_text, 100)
        self.assertGreater(cost, 0)
        self.assertLess(cost, 1.0)

    def test_opus_cost_calculation(self):
        input_text = "create a simple function"
        cost = self.estimator.estimate_cost(ModelType.OPUS, input_text, 100)
        self.assertGreater(cost, 0)
        self.assertLess(cost, 1.0)

    def test_opus_more_expensive_than_sonnet(self):
        input_text = "create a complex system architecture"
        sonnet_cost = self.estimator.estimate_cost(ModelType.SONNET, input_text, 500)
        opus_cost = self.estimator.estimate_cost(ModelType.OPUS, input_text, 500)
        
        self.assertGreater(opus_cost, sonnet_cost)


class TestModelRouter(unittest.TestCase):
    def setUp(self):
        self.router = ModelRouter()

    def test_simple_task_routing(self):
        decision = self.router.route_task("list all files")
        self.assertEqual(decision.selected_model, ModelType.SONNET)
        self.assertEqual(decision.complexity, ComplexityLevel.SIMPLE)
        self.assertFalse(decision.manual_override)

    def test_complex_task_routing(self):
        decision = self.router.route_task("design system architecture") 
        self.assertEqual(decision.complexity, ComplexityLevel.COMPLEX)
        self.assertFalse(decision.manual_override)

    def test_manual_override(self):
        decision = self.router.route_task(
            "simple task", 
            manual_model=ModelType.OPUS
        )
        self.assertEqual(decision.selected_model, ModelType.OPUS)
        self.assertTrue(decision.manual_override)

    def test_metrics_tracking(self):
        initial_requests = self.router.metrics.total_requests
        
        self.router.route_task("simple task")
        self.router.route_task("prepare for production deployment", manual_model=ModelType.OPUS)
        
        self.assertEqual(
            self.router.metrics.total_requests, 
            initial_requests + 2
        )
        self.assertGreater(self.router.metrics.sonnet_requests, 0)
        self.assertGreater(self.router.metrics.opus_requests, 0)

    def test_cost_estimation_included(self):
        decision = self.router.route_task("create a function")
        self.assertGreater(decision.estimated_cost, 0)
        self.assertIn("cost", decision.reasoning.lower())

    def test_routing_stats(self):
        self.router.route_task("simple task")  # Sonnet
        self.router.route_task("complex architecture")  # Opus
        
        stats = self.router.get_routing_stats()
        
        self.assertIn('total_requests', stats)
        self.assertIn('sonnet_percentage', stats)
        self.assertIn('opus_percentage', stats)
        self.assertIn('estimated_total_cost', stats)

    def test_config_loading(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config = {
                "routing_rules": {
                    "simple": "claude-3-opus-20240229",
                    "moderate": "claude-3-opus-20240229",
                    "complex": "claude-3-opus-20240229",
                    "critical": "claude-3-opus-20240229"
                }
            }
            json.dump(config, f)
            config_path = f.name

        try:
            router = ModelRouter(config_path)
            decision = router.route_task("simple task")
            self.assertEqual(decision.complexity, ComplexityLevel.SIMPLE)
        finally:
            Path(config_path).unlink()

    def test_confidence_calculation(self):
        decision = self.router.route_task("create a new authentication system")
        self.assertGreater(decision.confidence, 0)
        self.assertLessEqual(decision.confidence, 1.0)

    def test_batch_recommendations(self):
        tasks = [
            "list files",
            "design architecture", 
            "fix authentication bug"
        ]
        
        recommendations = self.router.get_model_recommendations(tasks)
        self.assertEqual(len(recommendations), 3)
        
        for rec in recommendations:
            self.assertIsInstance(rec, RoutingDecision)

    def test_cost_savings_calculation(self):
        self.router.route_task("simple task 1")
        self.router.route_task("simple task 2")
        
        stats = self.router.get_routing_stats()
        self.assertGreaterEqual(stats['estimated_cost_savings'], 0)

    def test_export_config(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_path = f.name

        try:
            self.router.export_config(config_path)
            self.assertTrue(Path(config_path).exists())
            
            with open(config_path) as f:
                exported_config = json.load(f)
            
            self.assertIn('routing_rules', exported_config)
            self.assertIn('confidence_threshold', exported_config)
        finally:
            if Path(config_path).exists():
                Path(config_path).unlink()

    def test_fallback_for_low_confidence(self):
        router = ModelRouter()
        router.config['confidence_threshold'] = 0.9
        
        decision = router.route_task("ambiguous task description")
        
        self.assertEqual(decision.selected_model, ModelType.SONNET)

    def test_context_aware_routing(self):
        context = {
            "file_count": 20,
            "involves_database": True,
            "has_tests": True
        }
        
        decision = self.router.route_task("modify the code", context=context)
        
        self.assertIn(decision.complexity, [ComplexityLevel.MODERATE, ComplexityLevel.COMPLEX])


if __name__ == '__main__':
    unittest.main()