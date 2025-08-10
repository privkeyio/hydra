"""Agent Pool Manager for Hydra.

Manages a pool of Claude Code agents, spawning and destroying them as needed.
Each agent runs in its own isolated terminal session.
"""

import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    """Status of an agent in the pool."""

    IDLE = "idle"
    BUSY = "busy"
    TERMINATING = "terminating"


@dataclass
class Agent:
    """Represents a Claude Code agent."""

    agent_id: str
    session_name: str
    ticket_id: Optional[str]
    status: AgentStatus
    created_at: float
    last_active: float


class AgentPool:
    """Manages a pool of Claude Code agents."""

    def __init__(self, max_agents: int = 4, idle_timeout: int = 300):
        """Initialize agent pool.
        
        Args:
            max_agents: Maximum number of concurrent agents
            idle_timeout: Seconds before idle agents are terminated

        """
        self.max_agents = max_agents
        self.idle_timeout = idle_timeout
        self.agents: Dict[str, Agent] = {}
        self.lock = threading.Lock()
        self._cleanup_thread = None
        self._running = False

    def start(self):
        """Start the agent pool manager."""
        self._running = True
        self._cleanup_thread = threading.Thread(target=self._cleanup_idle_agents)
        self._cleanup_thread.daemon = True
        self._cleanup_thread.start()
        logger.info(f"Agent pool started with max {self.max_agents} agents")

    def stop(self):
        """Stop the agent pool and terminate all agents."""
        self._running = False
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)

        # Terminate all agents
        with self.lock:
            for agent_id in list(self.agents.keys()):
                self._terminate_agent(agent_id)

        logger.info("Agent pool stopped")

    def spawn_agent(self, ticket_id: str) -> Optional[str]:
        """Spawn a new agent for a ticket.
        
        Args:
            ticket_id: Ticket the agent will work on
            
        Returns:
            Agent ID if spawned, None if pool is full

        """
        with self.lock:
            # First, check if this specific ticket already has an agent
            agent_id = f"agent_{ticket_id}"
            if agent_id in self.agents:
                logger.info(f"Reusing existing agent {agent_id}")
                agent = self.agents[agent_id]
                agent.status = AgentStatus.BUSY
                agent.ticket_id = ticket_id
                agent.last_active = time.time()
                return agent_id

            # Try to find an idle agent to reuse
            for existing_id, agent in self.agents.items():
                if agent.status == AgentStatus.IDLE:
                    # Terminate the old idle session
                    try:
                        subprocess.run(
                            ["tmux", "kill-session", "-t", agent.session_name],
                            capture_output=True,
                            timeout=5
                        )
                    except:
                        pass

                    # Remove the old agent
                    del self.agents[existing_id]
                    logger.info(f"Removed idle agent {existing_id} to make room")
                    break

            # Check if we're at capacity after cleanup
            active_count = sum(1 for a in self.agents.values()
                             if a.status != AgentStatus.TERMINATING)
            if active_count >= self.max_agents:
                logger.warning(f"Agent pool full ({active_count}/{self.max_agents})")
                print(f"⚠️  Agent pool full ({active_count}/{self.max_agents})")
                return None

            # Create unique agent ID and session name
            session_name = f"hydra_claude_{ticket_id}"

            # Create new agent
            agent = Agent(
                agent_id=agent_id,
                session_name=session_name,
                ticket_id=ticket_id,
                status=AgentStatus.BUSY,
                created_at=time.time(),
                last_active=time.time()
            )

            self.agents[agent_id] = agent
            logger.info(f"Spawned agent {agent_id} for ticket {ticket_id}")

            return agent_id

    def release_agent(self, agent_id: str):
        """Mark an agent as idle after completing a task.
        
        Args:
            agent_id: Agent to release

        """
        with self.lock:
            if agent_id in self.agents:
                agent = self.agents[agent_id]
                agent.status = AgentStatus.IDLE
                agent.ticket_id = None
                agent.last_active = time.time()
                logger.info(f"Released agent {agent_id}")

    def terminate_agent(self, agent_id: str):
        """Terminate an agent immediately.
        
        Args:
            agent_id: Agent to terminate

        """
        with self.lock:
            self._terminate_agent(agent_id)

    def _terminate_agent(self, agent_id: str):
        """Internal method to terminate an agent (assumes lock is held).
        
        Args:
            agent_id: Agent to terminate

        """
        if agent_id not in self.agents:
            return

        agent = self.agents[agent_id]
        agent.status = AgentStatus.TERMINATING

        # Kill the tmux session
        try:
            subprocess.run(
                ["tmux", "kill-session", "-t", agent.session_name],
                capture_output=True,
                timeout=5
            )
            logger.info(f"Terminated tmux session {agent.session_name}")
        except Exception as e:
            logger.error(f"Failed to terminate session {agent.session_name}: {e}")

        # Remove from pool
        del self.agents[agent_id]
        logger.info(f"Removed agent {agent_id} from pool")

    def _cleanup_idle_agents(self):
        """Background thread to clean up idle agents."""
        while self._running:
            time.sleep(30)  # Check every 30 seconds

            with self.lock:
                current_time = time.time()
                idle_agents = [
                    agent_id for agent_id, agent in self.agents.items()
                    if agent.status == AgentStatus.IDLE
                    and (current_time - agent.last_active) > self.idle_timeout
                ]

                for agent_id in idle_agents:
                    logger.info(f"Terminating idle agent {agent_id}")
                    self._terminate_agent(agent_id)

    def get_status(self) -> Dict:
        """Get current pool status.
        
        Returns:
            Dictionary with pool statistics

        """
        with self.lock:
            total = len(self.agents)
            busy = sum(1 for a in self.agents.values()
                      if a.status == AgentStatus.BUSY)
            idle = sum(1 for a in self.agents.values()
                      if a.status == AgentStatus.IDLE)

            return {
                "max_agents": self.max_agents,
                "total_agents": total,
                "busy_agents": busy,
                "idle_agents": idle,
                "available_slots": self.max_agents - total,
                "agents": {
                    agent_id: {
                        "status": agent.status.value,
                        "ticket_id": agent.ticket_id,
                        "created_at": agent.created_at,
                        "last_active": agent.last_active
                    }
                    for agent_id, agent in self.agents.items()
                }
            }
