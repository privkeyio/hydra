"""Provider performance benchmarks."""

import pytest
import time
from typing import Dict, Any

from hydra.providers.base import LLMConfig
from tests.mocks import MockLLMProvider, get_mock_providers
from .benchmark_runner import BenchmarkRunner


class ProviderBenchmark:
    """Benchmark LLM providers."""
    
    def __init__(self):
        self.runner = BenchmarkRunner(warmup_iterations=3)
    
    def benchmark_basic_generation(self, iterations: int = 100) -> Dict[str, Any]:
        """Benchmark basic text generation."""
        providers = get_mock_providers()
        results = {}
        
        for name, provider in providers.items():
            def generate_text():
                return provider.generate("Generate a hello world function in Python")
            
            result = self.runner.run_benchmark(
                name=f"{name}_basic_generation",
                func=generate_text,
                iterations=iterations
            )
            results[name] = result
        
        return results
    
    def benchmark_json_generation(self, iterations: int = 100) -> Dict[str, Any]:
        """Benchmark JSON response generation."""
        providers = get_mock_providers()
        results = {}
        
        for name, provider in providers.items():
            def generate_json():
                return provider.generate_json("Create a JSON response with plan and code")
            
            result = self.runner.run_benchmark(
                name=f"{name}_json_generation",
                func=generate_json,
                iterations=iterations
            )
            results[name] = result
        
        return results
    
    def benchmark_concurrent_requests(self, iterations: int = 50) -> Dict[str, Any]:
        """Benchmark concurrent provider requests."""
        import threading
        from concurrent.futures import ThreadPoolExecutor
        
        providers = get_mock_providers()
        results = {}
        
        for name, provider in providers.items():
            def concurrent_generate():
                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = []
                    for i in range(10):
                        future = executor.submit(
                            provider.generate, 
                            f"Generate function #{i}"
                        )
                        futures.append(future)
                    
                    # Wait for all to complete
                    for future in futures:
                        future.result()
            
            result = self.runner.run_benchmark(
                name=f"{name}_concurrent_requests",
                func=concurrent_generate,
                iterations=iterations
            )
            results[name] = result
        
        return results
    
    def benchmark_error_handling(self, iterations: int = 100) -> Dict[str, Any]:
        """Benchmark provider error handling performance."""
        config = LLMConfig(provider_type="test")
        
        # Test with different error rates
        error_rates = [0.0, 0.1, 0.3, 0.5]
        results = {}
        
        for error_rate in error_rates:
            provider = MockLLMProvider(config)
            provider.set_error_rate(error_rate)
            
            def generate_with_errors():
                try:
                    return provider.generate("Test error handling")
                except Exception:
                    pass  # Expected errors
            
            result = self.runner.run_benchmark(
                name=f"error_rate_{error_rate}",
                func=generate_with_errors,
                iterations=iterations
            )
            results[f"error_rate_{error_rate}"] = result
        
        return results
    
    def benchmark_response_sizes(self, iterations: int = 100) -> Dict[str, Any]:
        """Benchmark performance with different response sizes."""
        config = LLMConfig(provider_type="test")
        results = {}
        
        # Test with different response lengths
        response_sizes = {
            "short": "Short response",
            "medium": "Medium " * 50 + " response",
            "long": "Long " * 500 + " response",
            "very_long": "Very long " * 2000 + " response"
        }
        
        for size_name, mock_response in response_sizes.items():
            provider = MockLLMProvider(config, responses={"test": mock_response})
            
            def generate_sized_response():
                return provider.generate("test prompt")
            
            result = self.runner.run_benchmark(
                name=f"response_size_{size_name}",
                func=generate_sized_response,
                iterations=iterations
            )
            results[size_name] = result
        
        return results
    
    def benchmark_memory_usage(self, iterations: int = 50) -> Dict[str, Any]:
        """Benchmark memory usage patterns."""
        import gc
        
        config = LLMConfig(provider_type="test")
        provider = MockLLMProvider(config)
        results = {}
        
        # Test memory usage with different patterns
        def memory_intensive():
            # Generate multiple large responses
            responses = []
            for i in range(20):
                response = provider.generate(f"Generate large response #{i}")
                responses.append(response)
            return responses
        
        def memory_efficient():
            # Generate and immediately discard
            for i in range(20):
                provider.generate(f"Generate response #{i}")
            gc.collect()  # Force cleanup
        
        result1 = self.runner.run_benchmark(
            name="memory_intensive",
            func=memory_intensive,
            iterations=iterations
        )
        results["intensive"] = result1
        
        result2 = self.runner.run_benchmark(
            name="memory_efficient", 
            func=memory_efficient,
            iterations=iterations
        )
        results["efficient"] = result2
        
        return results
    
    def benchmark_session_management(self, iterations: int = 50) -> Dict[str, Any]:
        """Benchmark session creation and management."""
        from tests.mocks import MockClaudeProvider
        
        config = LLMConfig(provider_type="claude")
        results = {}
        
        # Session creation benchmark
        provider = MockClaudeProvider(config)
        
        def create_session():
            session_id = provider.start_session()
            provider.end_session()
            return session_id
        
        result1 = self.runner.run_benchmark(
            name="session_creation",
            func=create_session,
            iterations=iterations
        )
        results["session_creation"] = result1
        
        # Session reuse benchmark
        provider.start_session()
        
        def reuse_session():
            return provider.execute_command("test command")
        
        def cleanup_session():
            provider.end_session()
        
        result2 = self.runner.run_benchmark(
            name="session_reuse",
            func=reuse_session,
            iterations=iterations,
            teardown=None  # Don't cleanup each time
        )
        results["session_reuse"] = result2
        
        cleanup_session()  # Final cleanup
        
        return results
    
    def run_all_benchmarks(self, iterations: int = 50) -> Dict[str, Any]:
        """Run all provider benchmarks."""
        all_results = {}
        
        print("Running basic generation benchmark...")
        all_results["basic_generation"] = self.benchmark_basic_generation(iterations)
        
        print("Running JSON generation benchmark...")
        all_results["json_generation"] = self.benchmark_json_generation(iterations)
        
        print("Running concurrent requests benchmark...")
        all_results["concurrent_requests"] = self.benchmark_concurrent_requests(iterations)
        
        print("Running error handling benchmark...")
        all_results["error_handling"] = self.benchmark_error_handling(iterations)
        
        print("Running response sizes benchmark...")
        all_results["response_sizes"] = self.benchmark_response_sizes(iterations)
        
        print("Running memory usage benchmark...")
        all_results["memory_usage"] = self.benchmark_memory_usage(iterations)
        
        print("Running session management benchmark...")
        all_results["session_management"] = self.benchmark_session_management(iterations)
        
        return all_results
    
    def get_summary(self) -> Dict[str, Any]:
        """Get benchmark summary."""
        return self.runner.get_summary()
    
    def save_results(self, filename: str):
        """Save benchmark results."""
        self.runner.save_results(filename)