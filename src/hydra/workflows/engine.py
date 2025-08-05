import logging
from typing import Any, Dict, List, TypedDict

from langgraph.graph import END, StateGraph

from hydra.agents.base import CodeAgent

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
    agent = CodeAgent(state["current_agent"], depth=state["depth"])

    try:
        reasoning = agent.reason(state["task"])
        state["plan"] = reasoning.get("plan", "")
        state["subtasks"] = reasoning.get("subtasks", [])
        logger.info(
            f"Agent {agent.name} created plan with {len(state['subtasks'])} subtasks"
        )
    except RecursionError as e:
        logger.warning(f"Depth limit reached: {e}")
        state["subtasks"] = []
        state["plan"] = f"Depth limit reached at level {state['depth']}"

    return state


def spawn_node(state: WorkflowState) -> WorkflowState:
    parent_agent = CodeAgent(state["current_agent"], depth=state["depth"])

    for i, subtask in enumerate(state["subtasks"]):
        employee_name = f"{state['current_agent']}_employee_{i}"
        state["agents"].append(employee_name)

        spawn_code = f"""
from hydra.agents.base import CodeAgent

employee = CodeAgent("{employee_name}", depth={state['depth'] + 1})
reasoning = employee.reason("{subtask}")
result = {{
    "agent": "{employee_name}",
    "task": "{subtask}",
    "plan": reasoning.get("plan", ""),
    "subtasks": reasoning.get("subtasks", [])
}}
print(result)
"""

        try:
            exec_result = parent_agent.execute_code(spawn_code)
            if exec_result["success"]:
                import ast
                result_data = ast.literal_eval(exec_result["stdout"].strip())
                state["results"][employee_name] = result_data
                logger.info(f"Successfully spawned {employee_name}")
            else:
                state["results"][employee_name] = {
                    "error": exec_result["stderr"],
                    "task": subtask
                }
                logger.error(
                    f"Failed to spawn {employee_name}: {exec_result['stderr']}"
                )
        except Exception as e:
            state["results"][employee_name] = {
                "error": str(e),
                "task": subtask
            }
            logger.error(f"Exception spawning {employee_name}: {e}")

    return state


def aggregate_node(state: WorkflowState) -> WorkflowState:
    logger.info(f"Aggregating results from {len(state['agents'])} agents")

    state["results"]["summary"] = {
        "total_agents": len(state["agents"]),
        "successful": len([r for r in state["results"].values() if "error" not in r]),
        "failed": len([r for r in state["results"].values() if "error" in r]),
        "depth_reached": state["depth"]
    }

    return state


def should_spawn(state: WorkflowState) -> str:
    if state["subtasks"] and state["depth"] < 2:
        return "spawn"
    else:
        return "aggregate"


def create_workflow():
    workflow = StateGraph(WorkflowState)

    workflow.add_node("plan", plan_node)
    workflow.add_node("spawn", spawn_node)
    workflow.add_node("aggregate", aggregate_node)

    workflow.set_entry_point("plan")

    workflow.add_conditional_edges(
        "plan",
        should_spawn,
        {
            "spawn": "spawn",
            "aggregate": "aggregate"
        }
    )

    workflow.add_edge("spawn", "aggregate")
    workflow.add_edge("aggregate", END)

    return workflow.compile()


def execute_workflow(
    task: str, agent_name: str = "boss", depth: int = 0
) -> Dict[str, Any]:
    workflow = create_workflow()

    initial_state = WorkflowState(
        task=task,
        depth=depth,
        results={},
        agents=[agent_name],
        current_agent=agent_name,
        subtasks=[],
        plan=""
    )

    try:
        final_state = workflow.invoke(initial_state)
        return final_state
    except Exception as e:
        logger.error(f"Workflow execution failed: {e}")
        return {
            "error": str(e),
            "initial_state": initial_state
        }
