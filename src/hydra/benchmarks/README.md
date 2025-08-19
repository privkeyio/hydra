# Hydra Performance Benchmark Suite

This directory contains a comprehensive performance benchmark suite for the Hydra project, designed to measure and track performance improvements across different components.

## Quick Start

```bash
# Run all benchmarks
python src/hydra/benchmarks/run_all_benchmarks.py

# Run individual benchmark suites
python src/hydra/benchmarks/ticket_execution_benchmark.py      # Ticket workflow performance
python src/hydra/benchmarks/provider_response_benchmark.py     # Provider response times
python src/hydra/benchmarks/performance_benchmarks.py          # System optimizations
python src/hydra/benchmarks/async_performance_benchmark.py     # Async vs sync comparison
```

## Benchmark Categories

### 1. Ticket Execution Benchmarks (`ticket_execution_benchmark.py`)

Tests the performance of Hydra's core ticket execution workflow:

- **Single Ticket Execution**: Time to execute individual tickets
- **Parallel Ticket Execution**: Efficiency of concurrent ticket processing
- **Success Rates**: Reliability of ticket execution
- **Resource Usage**: Memory and CPU utilization

**Key Metrics**:
- Mean execution time per ticket
- Parallel speedup factor
- Success rate percentage
- Provider response times

### 2. Provider Response Benchmarks (`provider_response_benchmark.py`)

Measures the performance and reliability of different LLM providers:

- **Response Times**: Latency for different prompt complexities
- **Throughput**: Requests per second capability
- **Concurrent Performance**: Behavior under concurrent load
- **Connection Pooling**: Efficiency of connection reuse
- **Error Rates**: Provider reliability metrics

**Key Metrics**:
- Mean/min/max response times
- Throughput (RPS)
- Success and error rates
- Concurrent request handling
- Connection pool efficiency

### 3. Performance Optimizations (`performance_benchmarks.py`)

Validates the impact of system-level performance optimizations:

- **Event Loop Performance**: uvloop vs standard asyncio
- **Connection Pooling**: Connection reuse efficiency
- **Request Batching**: Batch processing improvements
- **Response Caching**: Cache hit rates and performance
- **Parallel Execution**: Concurrent vs sequential performance

**Key Metrics**:
- Performance improvement percentages
- Throughput improvements
- Cache hit rates
- Optimization effectiveness

### 4. Async Performance Comparison (`async_performance_benchmark.py`)

Compares async/await implementation against synchronous approaches:

- **HTTP Requests**: aiohttp vs requests performance
- **Database Operations**: Async vs sync database calls
- **Parallel Task Execution**: asyncio.gather vs ThreadPoolExecutor
- **LLM Operations**: Concurrent API calls

**Key Metrics**:
- Speedup factors (async vs sync)
- Performance improvement percentages
- Concurrency efficiency
- Resource utilization

## Configuration

### Environment Variables

```bash
# Provider configuration
export LLM_PROVIDER=mock          # Use mock provider for benchmarks
export REDIS_URL=redis://localhost:6379/0
export DATABASE_URL=sqlite:///test.db
export TESTING=1

# Benchmark configuration
export CI=true                    # Reduce iterations for CI
export PYTHONPATH=src              # Python path for imports
```

### Benchmark Parameters

Benchmarks can be customized by modifying these parameters in each script:

```python
# ticket_execution_benchmark.py
benchmark = TicketExecutionBenchmark(
    iterations=5,           # Number of test iterations
    test_tickets_count=6    # Number of test tickets to create
)

# provider_response_benchmark.py
benchmark = ProviderResponseBenchmark(
    iterations=10,          # Number of test iterations per provider
    concurrent_requests=5   # Number of concurrent requests for load testing
)
```

## CI Integration

Benchmarks run automatically in GitHub Actions CI:

1. **Execution**: Runs after all tests pass
2. **Artifacts**: Results uploaded as GitHub artifacts
3. **PR Comments**: Performance summaries posted to pull requests
4. **Retention**: Results kept for 30 days for trend analysis

### CI Configuration

See `.github/workflows/ci.yml` for the complete CI setup:

```yaml
- name: Run performance benchmarks
  run: python src/hydra/benchmarks/run_all_benchmarks.py
  continue-on-error: true

- name: Upload benchmark results
  uses: actions/upload-artifact@v4
  with:
    name: performance-benchmarks-${{ github.sha }}
    path: benchmark_results/
```

## Output Formats

### JSON Reports

Detailed machine-readable results for automated analysis:

```json
{
  "summary": {
    "performance_score": 85,
    "baseline_compliance": true,
    "iterations": 5
  },
  "single_ticket_execution": {
    "mean_execution_time": 2.45,
    "success_rate": 1.0
  },
  "recommendations": [
    "✅ Single ticket execution meets baseline performance"
  ]
}
```

### Markdown Summaries

Human-readable reports for GitHub PR comments:

```markdown
# Performance Benchmark Report

## Overall Status: ✅ PASSED

### Summary
- **Total Execution Time**: 120.5s
- **Benchmarks Run**: 4
- **Success Rate**: 100%

### Key Metrics
- Single Ticket Execution: ✅ PASSED (2.45s avg)
- Parallel Execution: ✅ PASSED (3.2x speedup)
- Provider Response: ✅ PASSED (1.8s avg response)
```

## Performance Baselines

See [PERFORMANCE_BASELINES.md](./PERFORMANCE_BASELINES.md) for detailed baseline definitions:

| Component | Baseline | Rationale |
|-----------|----------|-----------|
| Single Ticket | ≤60s execution | User experience |
| Parallel Speedup | ≥2.0x | Efficiency requirement |
| Provider Response | ≤10s | Acceptable latency |
| Success Rate | ≥90% | Reliability requirement |

## Troubleshooting

### Common Issues

1. **Import Errors**
   ```bash
   # Ensure correct Python path
   export PYTHONPATH=src
   python src/hydra/benchmarks/run_all_benchmarks.py
   ```

2. **Provider Failures**
   ```bash
   # Use mock provider for testing
   export LLM_PROVIDER=mock
   ```

3. **Slow Execution**
   ```bash
   # Reduce iterations for faster testing
   export CI=true  # This reduces iterations automatically
   ```

4. **Resource Issues**
   ```bash
   # Ensure sufficient resources
   ulimit -n 4096  # Increase file descriptor limit
   ```

### Debug Mode

Enable detailed logging for troubleshooting:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Run benchmarks with debug logging
benchmark = TicketExecutionBenchmark(iterations=1)
```

## Development

### Adding New Benchmarks

1. Create a new benchmark class inheriting from a base pattern
2. Implement required methods (`run_benchmark`, `generate_report`)
3. Add baseline definitions
4. Update the comprehensive runner
5. Add documentation

Example structure:

```python
class NewBenchmark:
    def __init__(self, iterations: int = 5):
        self.iterations = iterations
        self.baselines = {'metric': 10.0}
    
    async def run_benchmark(self) -> Dict[str, Any]:
        # Implement benchmark logic
        pass
    
    def generate_report(self, results: Dict) -> Dict[str, Any]:
        # Generate formatted report
        pass
```

### Testing Benchmarks

```bash
# Test individual benchmarks
python -m pytest tests/unit/test_benchmarks.py

# Test with minimal iterations
python src/hydra/benchmarks/ticket_execution_benchmark.py --iterations 1
```

## Files

- `run_all_benchmarks.py` - Comprehensive benchmark runner
- `ticket_execution_benchmark.py` - Ticket workflow performance tests
- `provider_response_benchmark.py` - Provider performance and reliability tests
- `performance_benchmarks.py` - System optimization validation
- `async_performance_benchmark.py` - Async vs sync performance comparison
- `PERFORMANCE_BASELINES.md` - Detailed baseline documentation
- `README.md` - This file

## Contributing

When contributing to benchmarks:

1. Ensure new benchmarks follow existing patterns
2. Add appropriate baselines and validation
3. Update documentation
4. Test both locally and in CI environments
5. Consider statistical significance of measurements

---

For questions or issues with benchmarks, see the main project documentation or create an issue in the repository.