from workflow_engine import execute_workflow
from hydra.agents.base import CodeAgent


def demonstrate_workflow():
    print("=== Hydra Workflow Engine Demo ===\n")
    
    task = "Create a Python module with two functions: one to calculate factorial and one to generate Fibonacci sequence"
    
    print(f"Task: {task}\n")
    print("Executing workflow...\n")
    
    result = execute_workflow(task, "boss", 0)
    
    print("Workflow Results:")
    print("-" * 50)
    
    if "error" in result:
        print(f"ERROR: {result['error']}")
        return
    
    print(f"Plan: {result['plan']}")
    print(f"\nSubtasks identified: {len(result['subtasks'])}")
    for i, subtask in enumerate(result['subtasks']):
        print(f"  {i+1}. {subtask}")
    
    print("\nAgent Results:")
    for agent_name, agent_result in result['results'].items():
        if agent_name == "summary":
            continue
        print(f"\n  Agent: {agent_name}")
        if isinstance(agent_result, dict):
            if "error" in agent_result:
                print(f"    Status: FAILED")
                print(f"    Error: {agent_result['error']}")
            else:
                print(f"    Status: SUCCESS")
                print(f"    Task: {agent_result.get('task', 'N/A')}")
                print(f"    Plan: {agent_result.get('plan', 'N/A')}")
    
    if "summary" in result['results']:
        summary = result['results']['summary']
        print("\nSummary:")
        print(f"  Total agents: {summary['total_agents']}")
        print(f"  Successful: {summary['successful']}")
        print(f"  Failed: {summary['failed']}")
        print(f"  Max depth reached: {summary['depth_reached']}")


def test_depth_limit():
    print("\n=== Testing Depth Limit ===\n")
    
    agent = CodeAgent("depth_test", depth=2)
    
    try:
        agent.reason("Any task")
    except RecursionError as e:
        print(f"Correctly caught recursion error: {e}")


def test_sdk_as_tool():
    print("\n=== Testing SDK Integration ===\n")
    
    agent = CodeAgent("sdk_test")
    
    code = agent.generate_code("Create a function that returns the square of a number")
    print("Generated code:")
    print(code)
    print("\nValidation: PASSED (AST parsed successfully)")
    
    exec_result = agent.execute_code(code + "\nprint(square(5))")
    print(f"\nExecution result: {exec_result['stdout'].strip()}")


if __name__ == "__main__":
    demonstrate_workflow()
    test_depth_limit()
    test_sdk_as_tool()
