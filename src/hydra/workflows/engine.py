"""Engine module."""

import logging
from typing import Any, Dict, List, TypedDict

try:
    from langgraph.graph import END, StateGraph

    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    END = None
    StateGraph = None

from hydra.agents.base import CodeAgent
from hydra.exceptions import RecursionLimitError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WorkflowState(TypedDict):
    task: str
    depth: int
    results: Dict[str, Any]
    agents: List[str]
    current_agent: str
    subtasks: List[str]
    plan: str


def plan_node(state: WorkflowState) -> WorkflowState:
    try:
        agent = CodeAgent(state["current_agent"], depth=state["depth"])
    except RecursionLimitError as e:
        logger.warning(f"Depth limit reached during agent creation: {e}")
        state["subtasks"] = []
        state["plan"] = f"Depth limit reached at level {state['depth']}"
        return state

    try:
        # For simple tasks, complete directly instead of planning
        task = state["task"]

        # Check if task is simple (doesn't need decomposition)
        is_simple_task = len(task.split()) < 10 and any(
            keyword in task.lower()
            for keyword in [
                "write a function",
                "create a function",
                "implement",
                "calculate",
                "compute",
                "generate code",
            ]
        )

        if is_simple_task or state["depth"] >= 1:
            # Complete the task directly
            result = agent.complete_task(task)
            state["results"][agent.agent_id] = result
            state["plan"] = result.get("generated_code", "No code generated")
            state["subtasks"] = []
            logger.info(f"Agent {agent.name} completed task directly (simple task)")
        else:
            # Complex task - create plan and subtasks
            reasoning = agent.reason(task)
            state["plan"] = reasoning.get("plan", "")
            state["subtasks"] = reasoning.get("subtasks", [])
            subtask_count = len(state["subtasks"])
            logger.info(
                f"Agent {agent.name} created plan with {subtask_count} subtasks"
            )
    except (RecursionError, RecursionLimitError) as e:
        logger.warning(f"Depth limit reached: {e}")
        state["subtasks"] = []
        state["plan"] = f"Depth limit reached at level {state['depth']}"
    except Exception as e:
        logger.error(f"Planning failed: {e}")
        # Fallback: try to complete task directly
        try:
            result = agent.complete_task(task)
            state["results"][agent.agent_id] = result
            fallback = f"Fallback execution: {str(e)}"
            state["plan"] = result.get("generated_code", fallback)
            state["subtasks"] = []
        except Exception as fallback_e:
            state["plan"] = f"Task failed: {fallback_e}"
            state["subtasks"] = []

    return state


def spawn_node(state: WorkflowState) -> WorkflowState:
    parent_agent = CodeAgent(state["current_agent"], depth=state["depth"])

    for i, subtask in enumerate(state["subtasks"]):
        employee_name = f"{state['current_agent']}_employee_{i}"
        state["agents"].append(employee_name)

        logger.info(f"Spawning employee {employee_name} for subtask: {subtask[:50]}...")

        try:
            # Create employee agent directly
            employee = CodeAgent(
                employee_name, parent=parent_agent, depth=state["depth"] + 1
            )

            # Complete the subtask
            result = employee.complete_task(subtask)
            state["results"][employee_name] = result

            if result["success"]:
                logger.info(f"Successfully completed subtask with {employee_name}")
            else:
                error = result.get("error", "Unknown error")
                logger.error(f"Employee {employee_name} failed: {error}")

        except RecursionError as e:
            state["results"][employee_name] = {
                "error": f"Recursion limit exceeded: {str(e)}",
                "task": subtask,
                "success": False,
            }
            logger.error(f"Recursion limit exceeded for {employee_name}: {e}")

        except Exception as e:
            state["results"][employee_name] = {
                "error": f"Employee creation failed: {str(e)}",
                "task": subtask,
                "success": False,
            }
            logger.error(f"Exception spawning {employee_name}: {e}")

    return state


def aggregate_node(state: WorkflowState) -> WorkflowState:
    logger.info(f"Aggregating results from {len(state['agents'])} agents")

    # Collect all generated code and results
    all_code = []
    all_outputs = []
    successful_results = []
    failed_results = []

    for agent_name, result in state["results"].items():
        if isinstance(result, dict):
            if result.get("success", True) and "error" not in result:
                successful_results.append(result)
                if "generated_code" in result:
                    all_code.append(f"# {agent_name}\n{result['generated_code']}")
                if "output" in result:
                    output = f"# Output from {agent_name}\n{result['output']}"
                    all_outputs.append(output)
            else:
                failed_results.append(result)

    # Combine all generated code
    if all_code:
        state["final_code"] = "\n\n".join(all_code)

    if all_outputs:
        state["execution_outputs"] = "\n\n".join(all_outputs)

    state["results"]["summary"] = {
        "total_agents": len(state["agents"]),
        "successful": len(successful_results),
        "failed": len(failed_results),
        "max_depth": state["depth"],
        "code_generated": len(all_code) > 0,
        "has_outputs": len(all_outputs) > 0,
    }

    return state


def should_spawn(state: WorkflowState) -> str:
    if state["subtasks"] and state["depth"] < 2:
        return "spawn"
    else:
        return "aggregate"


def create_workflow():
    if not LANGGRAPH_AVAILABLE:
        return None
    workflow = StateGraph(WorkflowState)

    workflow.add_node("plan", plan_node)
    workflow.add_node("spawn", spawn_node)
    workflow.add_node("aggregate", aggregate_node)

    workflow.set_entry_point("plan")

    workflow.add_conditional_edges(
        "plan", should_spawn, {"spawn": "spawn", "aggregate": "aggregate"}
    )

    workflow.add_edge("spawn", "aggregate")
    workflow.add_edge("aggregate", END)

    return workflow.compile()


def execute_workflow(
    task: str, agent_name: str = "boss", depth: int = 0
) -> Dict[str, Any]:
    initial_state = {
        "task": task,
        "depth": depth,
        "results": {},
        "agents": [agent_name],
        "current_agent": agent_name,
        "subtasks": [],
        "plan": "",
    }

    if not LANGGRAPH_AVAILABLE:
        # Fallback when langgraph is not available (e.g., in tests)
        logger.warning("Langgraph not available, using simplified workflow")
        initial_state["plan"] = f"Mock execution of: {task}"
        initial_state["results"][agent_name] = {
            "success": True,
            "task": task,
            "generated_code": f"# Mock code for: {task}",
        }
        return initial_state

    workflow = create_workflow()

    initial_state_typed = WorkflowState(
        task=task,
        depth=depth,
        results={},
        agents=[agent_name],
        current_agent=agent_name,
        subtasks=[],
        plan="",
    )

    try:
        final_state = workflow.invoke(initial_state_typed)
        # Ensure the state is a proper dict (not TypedDict instance)
        if final_state is None:
            # Return initial state if workflow returns None
            return dict(initial_state_typed)
        return dict(final_state)
    except Exception as e:
        logger.error(f"Workflow execution failed: {e}")
        return {
            "error": str(e),
            "task": task,
            "agents": [agent_name],
            "initial_state": dict(initial_state_typed),
        }
