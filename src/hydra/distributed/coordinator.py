"""Distributed execution coordinator for multi-instance Hydra deployments.

Provides task distribution, state synchronization, leader election, and
distributed locking capabilities for coordinating multiple Hydra instances.
"""

import asyncio
import json
import logging
import socket
import time
import uuid
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import aiofiles
import aiohttp

from hydra.monitoring_resources.resource_tracker import ResourceTracker
from hydra.persistence.hydra_state import HydraStateManager

logger = logging.getLogger(__name__)


class InstanceRole(Enum):
    """Roles that an instance can have in the cluster."""

    LEADER = "leader"
    FOLLOWER = "follower"
    CANDIDATE = "candidate"


class TaskStatus(Enum):
    """Status of distributed tasks."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class InstanceInfo:
    """Information about a Hydra instance in the cluster."""

    instance_id: str
    hostname: str
    port: int
    role: InstanceRole
    last_heartbeat: float
    cpu_usage: float
    memory_usage: float
    available_workers: int
    running_tasks: int
    version: str
    cluster_id: str


@dataclass
class DistributedTask:
    """Represents a task in the distributed system."""

    task_id: str
    ticket_id: str
    description: str
    assigned_instance: Optional[str]
    status: TaskStatus
    priority: int
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class DistributedLock:
    """Represents a distributed lock on a resource."""

    resource_id: str
    owner_instance: str
    acquired_at: float
    expires_at: float
    renewable: bool = True


@dataclass
class DistributedState:
    """Global state shared across all instances."""

    cluster_id: str
    leader_instance: Optional[str]
    instances: Dict[str, InstanceInfo]
    tasks: Dict[str, DistributedTask]
    locks: Dict[str, DistributedLock]
    last_updated: float
    term: int = 0


class DistributedCoordinator:
    """Coordinates distributed execution across multiple Hydra instances."""

    def __init__(
        self,
        instance_id: Optional[str] = None,
        cluster_id: Optional[str] = None,
        port: int = 8090,
        discovery_port: int = 8091,
        state_dir: Optional[str] = None,
        heartbeat_interval: float = 5.0,
        election_timeout: float = 15.0,
    ):

        self.instance_id = instance_id or str(uuid.uuid4())[:8]
        self.cluster_id = cluster_id or "default"
        self.port = port
        self.discovery_port = discovery_port
        self.hostname = socket.getfqdn()

        # State management
        self.state_dir = Path(state_dir or ".hydra/distributed")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "cluster_state.json"

        # Instance state
        self.role = InstanceRole.FOLLOWER
        self.term = 0
        self.last_heartbeat = 0
        self.votes_received = 0

        # Timing
        self.heartbeat_interval = heartbeat_interval
        self.election_timeout = election_timeout
        self.last_leader_contact = time.time()

        # Distributed state
        self.distributed_state = DistributedState(
            cluster_id=self.cluster_id,
            leader_instance=None,
            instances={},
            tasks={},
            locks={},
            last_updated=time.time(),
            term=0,
        )

        # Background tasks
        self.running = False
        self.background_tasks: Set[asyncio.Task] = set()

        # HTTP server and client session
        self.app = None
        self.server = None
        self.session: Optional[aiohttp.ClientSession] = None

        # Resource monitoring
        self.resource_tracker = ResourceTracker(update_interval=2.0)
        # Don't start monitoring in __init__ to avoid thread creation issues in tests
        self._monitoring_started = False

        # State persistence
        self.state_manager = HydraStateManager(self.state_dir.parent)

        # Discovery
        self.known_instances: Set[str] = set()
        self.discovery_lock = asyncio.Lock()

        # Load balancing
        self.load_balancer = LoadBalancer()

        logger.info(
            f"Initialized distributed coordinator {self.instance_id} on {self.hostname}:{self.port}"
        )

    async def start(self):
        """Start the distributed coordinator."""
        if self.running:
            return

        self.running = True

        # Start resource monitoring if not already started
        if not self._monitoring_started:
            self.resource_tracker.start_monitoring()
            self._monitoring_started = True

        # Create HTTP session
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))

        # Start HTTP server
        await self._start_http_server()

        # Load existing state
        await self._load_state()

        # Start background tasks
        await self._start_background_tasks()

        # Begin discovery
        await self._start_discovery()

        logger.info(f"Distributed coordinator started on {self.hostname}:{self.port}")

    async def stop(self):
        """Stop the distributed coordinator."""
        if not self.running:
            return

        self.running = False

        # Cancel background tasks
        for task in self.background_tasks:
            task.cancel()

        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)

        # Stop HTTP server
        if self.server:
            await self.server.cleanup()

        # Close HTTP session
        if self.session:
            await self.session.close()

        # Stop resource monitoring
        self.resource_tracker.stop_monitoring()

        # Save final state
        await self._save_state()

        logger.info("Distributed coordinator stopped")

    async def _start_http_server(self):
        """Start the HTTP API server."""
        from aiohttp import web

        self.app = web.Application()

        # API routes
        self.app.router.add_get("/health", self._handle_health)
        self.app.router.add_post("/heartbeat", self._handle_heartbeat)
        self.app.router.add_post("/vote_request", self._handle_vote_request)
        self.app.router.add_get("/state", self._handle_get_state)
        self.app.router.add_post("/state", self._handle_update_state)
        self.app.router.add_post("/tasks", self._handle_submit_task)
        self.app.router.add_get("/tasks/{task_id}", self._handle_get_task)
        self.app.router.add_post("/locks/{resource_id}", self._handle_acquire_lock)
        self.app.router.add_delete("/locks/{resource_id}", self._handle_release_lock)

        # Start web server
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self.port)
        await site.start()

        # Store the runner for cleanup
        self.server = runner

    async def _start_background_tasks(self):
        """Start background tasks for coordination."""
        tasks = [
            self._heartbeat_loop(),
            self._election_loop(),
            self._state_sync_loop(),
            self._task_distribution_loop(),
            self._lock_maintenance_loop(),
        ]

        for coro in tasks:
            task = asyncio.create_task(coro)
            self.background_tasks.add(task)

    async def _start_discovery(self):
        """Start instance discovery."""
        # Try to discover other instances through multicast or configuration
        discovery_task = asyncio.create_task(self._discovery_loop())
        self.background_tasks.add(discovery_task)

    async def _discovery_loop(self):
        """Continuously discover other instances."""
        while self.running:
            try:
                # Simple discovery: scan local network for other instances
                await self._scan_for_instances()
                await asyncio.sleep(30)  # Discovery every 30 seconds
            except Exception as e:
                logger.error(f"Error in discovery loop: {e}")
                await asyncio.sleep(5)

    async def _scan_for_instances(self):
        """Scan for other instances in the network."""
        # Get local network subnet
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)

        # Extract subnet (simple assumption)
        subnet_parts = local_ip.split(".")
        subnet_base = ".".join(subnet_parts[:3])

        # Scan common ports in subnet
        scan_tasks = []
        for host_num in range(1, 255):
            target_ip = f"{subnet_base}.{host_num}"
            if target_ip != local_ip:
                scan_tasks.append(self._try_contact_instance(target_ip))

        # Limit concurrent scans
        semaphore = asyncio.Semaphore(20)

        async def bounded_scan(target_ip):
            async with semaphore:
                return await self._try_contact_instance(target_ip)

        results = await asyncio.gather(
            *[bounded_scan(f"{subnet_base}.{i}") for i in range(1, 255)],
            return_exceptions=True,
        )

        # Process discovered instances
        for result in results:
            if isinstance(result, dict) and result.get("instance_id"):
                await self._register_discovered_instance(result)

    async def _try_contact_instance(self, target_ip: str) -> Optional[Dict]:
        """Try to contact an instance at the given IP."""
        try:
            async with self.session.get(
                f"http://{target_ip}:{self.port}/health",
                timeout=aiohttp.ClientTimeout(total=2),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("cluster_id") == self.cluster_id:
                        return data
        except Exception:
            pass
        return None

    async def _register_discovered_instance(self, instance_data: Dict):
        """Register a discovered instance."""
        instance_id = instance_data["instance_id"]

        if instance_id != self.instance_id and instance_id not in self.known_instances:
            self.known_instances.add(instance_id)
            logger.info(f"Discovered instance: {instance_id}")

    async def _heartbeat_loop(self):
        """Send heartbeats to maintain cluster membership."""
        while self.running:
            try:
                await self._send_heartbeat()
                await asyncio.sleep(self.heartbeat_interval)
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")
                await asyncio.sleep(1)

    async def _send_heartbeat(self):
        """Send heartbeat to other instances."""
        if self.role == InstanceRole.LEADER:
            # Leader sends heartbeats to all followers
            for instance_id in self.known_instances:
                if instance_id != self.instance_id:
                    await self._send_heartbeat_to_instance(instance_id)
        else:
            # Followers check for leader heartbeats
            if time.time() - self.last_leader_contact > self.election_timeout:
                await self._trigger_election()

    async def _send_heartbeat_to_instance(self, instance_id: str):
        """Send heartbeat to specific instance."""
        instance_info = self.distributed_state.instances.get(instance_id)
        if not instance_info:
            return

        heartbeat_data = {
            "instance_id": self.instance_id,
            "term": self.term,
            "role": self.role.value,
            "timestamp": time.time(),
        }

        try:
            url = f"http://{instance_info.hostname}:{instance_info.port}/heartbeat"
            async with self.session.post(url, json=heartbeat_data) as response:
                if response.status == 200:
                    instance_info.last_heartbeat = time.time()
        except Exception as e:
            logger.warning(f"Failed to send heartbeat to {instance_id}: {e}")

    async def _election_loop(self):
        """Handle leader election process."""
        while self.running:
            try:
                if self.role == InstanceRole.CANDIDATE:
                    await self._conduct_election()
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error in election loop: {e}")
                await asyncio.sleep(1)

    async def _trigger_election(self):
        """Trigger a new leader election."""
        if self.role != InstanceRole.LEADER:
            logger.info("Starting leader election")
            self.role = InstanceRole.CANDIDATE
            self.term += 1
            self.votes_received = 1  # Vote for self
            self.last_leader_contact = time.time()

    async def _conduct_election(self):
        """Conduct leader election by requesting votes."""
        vote_requests = []

        for instance_id in self.known_instances:
            if instance_id != self.instance_id:
                vote_requests.append(self._request_vote(instance_id))

        if vote_requests:
            votes = await asyncio.gather(*vote_requests, return_exceptions=True)
            vote_count = sum(1 for vote in votes if vote is True)
            self.votes_received += vote_count

        # Check if we have majority
        total_instances = len(self.known_instances) + 1  # Include self
        majority = (total_instances // 2) + 1

        if self.votes_received >= majority:
            await self._become_leader()
        else:
            # Election failed, return to follower
            self.role = InstanceRole.FOLLOWER
            logger.info("Election failed, returning to follower state")

    async def _request_vote(self, instance_id: str) -> bool:
        """Request vote from an instance."""
        instance_info = self.distributed_state.instances.get(instance_id)
        if not instance_info:
            return False

        vote_request = {
            "candidate_id": self.instance_id,
            "term": self.term,
            "timestamp": time.time(),
        }

        try:
            url = f"http://{instance_info.hostname}:{instance_info.port}/vote_request"
            async with self.session.post(url, json=vote_request) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("vote_granted", False)
        except Exception as e:
            logger.warning(f"Failed to request vote from {instance_id}: {e}")

        return False

    async def _become_leader(self):
        """Become the cluster leader."""
        self.role = InstanceRole.LEADER
        self.distributed_state.leader_instance = self.instance_id
        self.distributed_state.term = self.term
        self.last_leader_contact = time.time()

        logger.info(f"Became leader for term {self.term}")

        # Announce leadership to all instances
        await self._announce_leadership()

    async def _announce_leadership(self):
        """Announce leadership to all instances."""
        announcement = {
            "new_leader": self.instance_id,
            "term": self.term,
            "timestamp": time.time(),
        }

        for instance_id in self.known_instances:
            if instance_id != self.instance_id:
                await self._send_leadership_announcement(instance_id, announcement)

    async def _send_leadership_announcement(self, instance_id: str, announcement: Dict):
        """Send leadership announcement to specific instance."""
        instance_info = self.distributed_state.instances.get(instance_id)
        if not instance_info:
            return

        try:
            url = f"http://{instance_info.hostname}:{instance_info.port}/heartbeat"
            async with self.session.post(url, json=announcement) as response:
                if response.status == 200:
                    logger.debug(f"Announced leadership to {instance_id}")
        except Exception as e:
            logger.warning(f"Failed to announce leadership to {instance_id}: {e}")

    async def _state_sync_loop(self):
        """Synchronize distributed state across instances."""
        while self.running:
            try:
                if self.role == InstanceRole.LEADER:
                    await self._sync_state_to_followers()
                else:
                    await self._sync_state_from_leader()

                await asyncio.sleep(2)  # Sync every 2 seconds
            except Exception as e:
                logger.error(f"Error in state sync loop: {e}")
                await asyncio.sleep(1)

    async def _sync_state_to_followers(self):
        """Sync state from leader to followers."""
        state_data = asdict(self.distributed_state)
        state_data["last_updated"] = time.time()

        for instance_id in self.known_instances:
            if instance_id != self.instance_id:
                await self._send_state_to_instance(instance_id, state_data)

    async def _send_state_to_instance(self, instance_id: str, state_data: Dict):
        """Send state data to specific instance."""
        instance_info = self.distributed_state.instances.get(instance_id)
        if not instance_info:
            return

        try:
            url = f"http://{instance_info.hostname}:{instance_info.port}/state"
            async with self.session.post(url, json=state_data) as response:
                if response.status == 200:
                    logger.debug(f"Synced state to {instance_id}")
        except Exception as e:
            logger.warning(f"Failed to sync state to {instance_id}: {e}")

    async def _sync_state_from_leader(self):
        """Sync state from leader (if we're a follower)."""
        if not self.distributed_state.leader_instance:
            return

        leader_info = self.distributed_state.instances.get(
            self.distributed_state.leader_instance
        )

        if not leader_info:
            return

        try:
            url = f"http://{leader_info.hostname}:{leader_info.port}/state"
            async with self.session.get(url) as response:
                if response.status == 200:
                    state_data = await response.json()
                    await self._update_local_state(state_data)
        except Exception as e:
            logger.warning(f"Failed to sync state from leader: {e}")

    async def _update_local_state(self, state_data: Dict):
        """Update local state with data from leader."""
        try:
            # Convert dictionaries back to dataclass instances
            instances = {}
            for instance_id, instance_data in state_data.get("instances", {}).items():
                # Handle role enum conversion
                if "role" in instance_data and isinstance(instance_data["role"], str):
                    instance_data["role"] = InstanceRole(instance_data["role"])
                instances[instance_id] = InstanceInfo(**instance_data)

            tasks = {}
            for task_id, task_data in state_data.get("tasks", {}).items():
                # Make a copy to avoid modifying original data
                task_copy = task_data.copy()
                if "status" in task_copy:
                    if isinstance(task_copy["status"], str):
                        task_copy["status"] = TaskStatus(task_copy["status"])
                tasks[task_id] = DistributedTask(**task_copy)

            locks = {}
            for resource_id, lock_data in state_data.get("locks", {}).items():
                locks[resource_id] = DistributedLock(**lock_data)

            self.distributed_state = DistributedState(
                cluster_id=state_data["cluster_id"],
                leader_instance=state_data.get("leader_instance"),
                instances=instances,
                tasks=tasks,
                locks=locks,
                last_updated=state_data["last_updated"],
                term=state_data.get("term", 0),
            )

        except Exception as e:
            logger.error(f"Failed to update local state: {e}")

    async def _task_distribution_loop(self):
        """Distribute tasks to available instances."""
        while self.running:
            try:
                if self.role == InstanceRole.LEADER:
                    await self._distribute_pending_tasks()

                await asyncio.sleep(5)  # Check every 5 seconds
            except Exception as e:
                logger.error(f"Error in task distribution loop: {e}")
                await asyncio.sleep(1)

    async def _distribute_pending_tasks(self):
        """Distribute pending tasks to available instances."""
        pending_tasks = [
            task
            for task in self.distributed_state.tasks.values()
            if task.status == TaskStatus.PENDING
        ]

        if not pending_tasks:
            return

        # Sort tasks by priority
        pending_tasks.sort(key=lambda t: t.priority, reverse=True)

        # Get available instances
        available_instances = self._get_available_instances()

        for task in pending_tasks:
            if not available_instances:
                break

            # Select best instance using load balancer
            selected_instance = self.load_balancer.select_instance(
                available_instances, task
            )

            if selected_instance:
                await self._assign_task(task, selected_instance)
                # Only remove if instance has no more capacity
                if selected_instance.available_workers <= 0:
                    available_instances.remove(selected_instance)

    def _get_available_instances(self) -> List[InstanceInfo]:
        """Get instances that can accept new tasks."""
        available = []

        for instance in self.distributed_state.instances.values():
            # Check if instance is healthy and has capacity
            if (
                time.time() - instance.last_heartbeat < self.heartbeat_interval * 2
                and instance.available_workers > 0
            ):
                available.append(instance)

        return available

    async def _assign_task(self, task: DistributedTask, instance: InstanceInfo):
        """Assign a task to an instance."""
        task.assigned_instance = instance.instance_id
        task.status = TaskStatus.ASSIGNED

        # Update instance load
        instance.available_workers -= 1
        instance.running_tasks += 1

        logger.info(f"Assigned task {task.task_id} to instance {instance.instance_id}")

        # Notify the instance about the new task assignment
        await self._notify_task_assignment(task, instance)

    async def _notify_task_assignment(
        self, task: DistributedTask, instance: InstanceInfo
    ):
        """Notify an instance about task assignment."""
        task_data = asdict(task)
        task_data["status"] = task.status.value

        try:
            url = f"http://{instance.hostname}:{instance.port}/tasks"
            async with self.session.post(url, json=task_data) as response:
                if response.status == 200:
                    logger.debug(
                        f"Notified {instance.instance_id} about task {task.task_id}"
                    )
        except Exception as e:
            logger.warning(
                f"Failed to notify {instance.instance_id} about task {task.task_id}: {e}"
            )

    async def _lock_maintenance_loop(self):
        """Maintain distributed locks and handle expiration."""
        while self.running:
            try:
                await self._cleanup_expired_locks()
                await asyncio.sleep(10)  # Check every 10 seconds
            except Exception as e:
                logger.error(f"Error in lock maintenance loop: {e}")
                await asyncio.sleep(1)

    async def _cleanup_expired_locks(self):
        """Clean up expired locks."""
        current_time = time.time()
        expired_locks = []

        for resource_id, lock in self.distributed_state.locks.items():
            if lock.expires_at <= current_time:
                expired_locks.append(resource_id)

        for resource_id in expired_locks:
            del self.distributed_state.locks[resource_id]
            logger.info(f"Cleaned up expired lock for resource {resource_id}")

    # HTTP request handlers

    async def _handle_health(self, request):
        """Handle health check requests."""
        from aiohttp import web

        metrics = self.resource_tracker.get_current_metrics()

        health_data = {
            "instance_id": self.instance_id,
            "cluster_id": self.cluster_id,
            "hostname": self.hostname,
            "port": self.port,
            "role": self.role.value,
            "term": self.term,
            "cpu_usage": metrics.get("cpu_percent", 0),
            "memory_usage": metrics.get("memory_percent", 0),
            "available_workers": 5,  # TODO: Make configurable
            "running_tasks": len(
                [
                    t
                    for t in self.distributed_state.tasks.values()
                    if t.assigned_instance == self.instance_id
                    and t.status == TaskStatus.RUNNING
                ]
            ),
            "timestamp": time.time(),
        }

        return web.json_response(health_data)

    async def _handle_heartbeat(self, request):
        """Handle heartbeat requests."""
        from aiohttp import web

        data = await request.json()
        sender_id = data.get("instance_id")

        if sender_id and sender_id in self.distributed_state.instances:
            instance = self.distributed_state.instances[sender_id]
            instance.last_heartbeat = time.time()

        # If this is from the leader, update our last leader contact
        if data.get("role") == "leader":
            self.last_leader_contact = time.time()
            if self.distributed_state.leader_instance != sender_id:
                self.distributed_state.leader_instance = sender_id
                self.role = InstanceRole.FOLLOWER

        return web.json_response({"status": "ok"})

    async def _handle_vote_request(self, request):
        """Handle vote requests during leader election."""
        from aiohttp import web

        data = await request.json()
        candidate_id = data.get("candidate_id")
        candidate_term = data.get("term", 0)

        # Grant vote if term is newer and we haven't voted yet
        vote_granted = (
            candidate_term > self.term
            and self.role != InstanceRole.LEADER
            and candidate_id != self.instance_id
        )

        if vote_granted:
            self.term = candidate_term
            logger.info(f"Granted vote to {candidate_id} for term {candidate_term}")

        return web.json_response({"vote_granted": vote_granted})

    async def _handle_get_state(self, request):
        """Handle requests to get distributed state."""
        from aiohttp import web

        state_data = asdict(self.distributed_state)
        return web.json_response(state_data)

    async def _handle_update_state(self, request):
        """Handle state update requests."""
        from aiohttp import web

        state_data = await request.json()
        await self._update_local_state(state_data)

        return web.json_response({"status": "updated"})

    async def _handle_submit_task(self, request):
        """Handle task submission requests."""
        from aiohttp import web

        task_data = await request.json()

        # Only leader can accept task submissions
        if self.role != InstanceRole.LEADER:
            return web.json_response({"error": "Not leader"}, status=400)

        task = DistributedTask(
            task_id=task_data.get("task_id", str(uuid.uuid4())),
            ticket_id=task_data["ticket_id"],
            description=task_data["description"],
            assigned_instance=None,
            status=TaskStatus.PENDING,
            priority=task_data.get("priority", 0),
            created_at=time.time(),
        )

        self.distributed_state.tasks[task.task_id] = task

        logger.info(f"Submitted task {task.task_id} for ticket {task.ticket_id}")

        return web.json_response({"task_id": task.task_id})

    async def _handle_get_task(self, request):
        """Handle task status requests."""
        from aiohttp import web

        task_id = request.match_info["task_id"]
        task = self.distributed_state.tasks.get(task_id)

        if not task:
            return web.json_response({"error": "Task not found"}, status=404)

        task_data = asdict(task)
        task_data["status"] = task.status.value

        return web.json_response(task_data)

    async def _handle_acquire_lock(self, request):
        """Handle distributed lock acquisition."""
        from aiohttp import web

        resource_id = request.match_info["resource_id"]
        data = await request.json()

        duration = data.get("duration", 300)  # 5 minutes default
        current_time = time.time()

        # Check if resource is already locked
        if resource_id in self.distributed_state.locks:
            existing_lock = self.distributed_state.locks[resource_id]
            if existing_lock.expires_at > current_time:
                return web.json_response(
                    {"error": "Resource already locked"}, status=409
                )

        # Create new lock
        lock = DistributedLock(
            resource_id=resource_id,
            owner_instance=self.instance_id,
            acquired_at=current_time,
            expires_at=current_time + duration,
            renewable=data.get("renewable", True),
        )

        self.distributed_state.locks[resource_id] = lock

        logger.info(f"Acquired lock for resource {resource_id}")

        return web.json_response({"status": "acquired", "expires_at": lock.expires_at})

    async def _handle_release_lock(self, request):
        """Handle distributed lock release."""
        from aiohttp import web

        resource_id = request.match_info["resource_id"]

        if resource_id not in self.distributed_state.locks:
            return web.json_response({"error": "Lock not found"}, status=404)

        lock = self.distributed_state.locks[resource_id]

        # Only owner can release lock
        if lock.owner_instance != self.instance_id:
            return web.json_response({"error": "Not lock owner"}, status=403)

        del self.distributed_state.locks[resource_id]

        logger.info(f"Released lock for resource {resource_id}")

        return web.json_response({"status": "released"})

    # Public API methods

    async def submit_task(
        self, ticket_id: str, description: str, priority: int = 0
    ) -> str:
        """Submit a task for distributed execution."""
        if self.role != InstanceRole.LEADER:
            # Forward to leader
            if self.distributed_state.leader_instance:
                leader = self.distributed_state.instances.get(
                    self.distributed_state.leader_instance
                )
                if leader:
                    return await self._forward_task_to_leader(
                        leader, ticket_id, description, priority
                    )
            raise Exception("No leader available")

        task = DistributedTask(
            task_id=str(uuid.uuid4()),
            ticket_id=ticket_id,
            description=description,
            assigned_instance=None,
            status=TaskStatus.PENDING,
            priority=priority,
            created_at=time.time(),
        )

        self.distributed_state.tasks[task.task_id] = task

        return task.task_id

    async def _forward_task_to_leader(
        self, leader: InstanceInfo, ticket_id: str, description: str, priority: int
    ) -> str:
        """Forward task submission to leader."""
        task_data = {
            "ticket_id": ticket_id,
            "description": description,
            "priority": priority,
        }

        url = f"http://{leader.hostname}:{leader.port}/tasks"
        async with self.session.post(url, json=task_data) as response:
            if response.status == 200:
                result = await response.json()
                return result["task_id"]
            else:
                raise Exception(f"Failed to submit task: {response.status}")

    async def get_task_status(self, task_id: str) -> Optional[DistributedTask]:
        """Get the status of a distributed task."""
        return self.distributed_state.tasks.get(task_id)

    async def acquire_distributed_lock(
        self, resource_id: str, duration: int = 300
    ) -> bool:
        """Acquire a distributed lock on a resource."""
        if self.role == InstanceRole.LEADER:
            return await self._acquire_lock_locally(resource_id, duration)
        else:
            # Forward to leader
            leader = self.distributed_state.instances.get(
                self.distributed_state.leader_instance
            )
            if leader:
                return await self._request_lock_from_leader(
                    leader, resource_id, duration
                )
            return False

    async def _acquire_lock_locally(self, resource_id: str, duration: int) -> bool:
        """Acquire lock locally (as leader)."""
        current_time = time.time()

        # Check if already locked
        if resource_id in self.distributed_state.locks:
            existing_lock = self.distributed_state.locks[resource_id]
            if existing_lock.expires_at > current_time:
                return False

        # Create new lock
        lock = DistributedLock(
            resource_id=resource_id,
            owner_instance=self.instance_id,
            acquired_at=current_time,
            expires_at=current_time + duration,
        )

        self.distributed_state.locks[resource_id] = lock
        return True

    async def _request_lock_from_leader(
        self, leader: InstanceInfo, resource_id: str, duration: int
    ) -> bool:
        """Request lock from leader."""
        lock_data = {"duration": duration}

        url = f"http://{leader.hostname}:{leader.port}/locks/{resource_id}"

        try:
            async with self.session.post(url, json=lock_data) as response:
                return response.status == 200
        except Exception as e:
            logger.warning(f"Failed to request lock from leader: {e}")
            return False

    async def release_distributed_lock(self, resource_id: str) -> bool:
        """Release a distributed lock."""
        if resource_id not in self.distributed_state.locks:
            return False

        lock = self.distributed_state.locks[resource_id]

        if lock.owner_instance == self.instance_id:
            # We own the lock, release it directly
            del self.distributed_state.locks[resource_id]
            return True
        elif self.role == InstanceRole.LEADER:
            # As leader, we can force release
            del self.distributed_state.locks[resource_id]
            return True
        else:
            # Forward to leader
            leader = self.distributed_state.instances.get(
                self.distributed_state.leader_instance
            )
            if leader:
                return await self._request_lock_release_from_leader(leader, resource_id)

        return False

    async def _request_lock_release_from_leader(
        self, leader: InstanceInfo, resource_id: str
    ) -> bool:
        """Request lock release from leader."""
        url = f"http://{leader.hostname}:{leader.port}/locks/{resource_id}"

        try:
            async with self.session.delete(url) as response:
                return response.status == 200
        except Exception as e:
            logger.warning(f"Failed to request lock release from leader: {e}")
            return False

    def get_cluster_info(self) -> Dict[str, Any]:
        """Get information about the cluster."""
        return {
            "instance_id": self.instance_id,
            "cluster_id": self.cluster_id,
            "role": self.role.value,
            "term": self.term,
            "leader": self.distributed_state.leader_instance,
            "instances": len(self.distributed_state.instances),
            "tasks": {
                "total": len(self.distributed_state.tasks),
                "pending": sum(
                    1
                    for t in self.distributed_state.tasks.values()
                    if t.status == TaskStatus.PENDING
                ),
                "running": sum(
                    1
                    for t in self.distributed_state.tasks.values()
                    if t.status == TaskStatus.RUNNING
                ),
                "completed": sum(
                    1
                    for t in self.distributed_state.tasks.values()
                    if t.status == TaskStatus.COMPLETED
                ),
            },
            "locks": len(self.distributed_state.locks),
        }

    async def handle_network_partition(self):
        """Handle network partition scenarios."""
        # Check if we can contact the leader
        leader_reachable = await self._check_leader_reachability()

        if not leader_reachable and self.role == InstanceRole.FOLLOWER:
            # Potential partition detected
            logger.warning("Network partition detected, initiating election")
            await self._trigger_election()
        elif self.role == InstanceRole.LEADER:
            # As leader, check if we can reach majority of instances
            reachable_instances = await self._check_instances_reachability()
            total_instances = len(self.distributed_state.instances) + 1

            if len(reachable_instances) < (total_instances // 2):
                # We don't have majority, step down
                logger.warning("Lost majority contact, stepping down as leader")
                self.role = InstanceRole.FOLLOWER
                self.distributed_state.leader_instance = None

    async def _check_leader_reachability(self) -> bool:
        """Check if the leader is reachable."""
        if not self.distributed_state.leader_instance:
            return False

        leader = self.distributed_state.instances.get(
            self.distributed_state.leader_instance
        )

        if not leader:
            return False

        try:
            url = f"http://{leader.hostname}:{leader.port}/health"
            async with self.session.get(
                url, timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                return response.status == 200
        except Exception:
            return False

    async def _check_instances_reachability(self) -> List[str]:
        """Check which instances are reachable."""
        reachable = []

        for instance_id, instance in self.distributed_state.instances.items():
            if instance_id == self.instance_id:
                reachable.append(instance_id)
                continue

            try:
                url = f"http://{instance.hostname}:{instance.port}/health"
                async with self.session.get(
                    url, timeout=aiohttp.ClientTimeout(total=2)
                ) as response:
                    if response.status == 200:
                        reachable.append(instance_id)
            except Exception:
                continue

        return reachable

    async def _load_state(self):
        """Load persistent state from disk."""
        if self.state_file.exists():
            try:
                async with aiofiles.open(self.state_file, "r") as f:
                    content = await f.read()
                    state_data = json.loads(content)
                    await self._update_local_state(state_data)
                    logger.info("Loaded distributed state from disk")
            except Exception as e:
                logger.error(f"Failed to load state: {e}")

    async def _save_state(self):
        """Save distributed state to disk."""
        try:
            state_data = asdict(self.distributed_state)
            state_data["last_updated"] = time.time()

            # Convert enums to values for JSON serialization
            if "tasks" in state_data:
                for task_id, task in state_data["tasks"].items():
                    if "status" in task and hasattr(task["status"], "value"):
                        task["status"] = task["status"].value

            if "instances" in state_data:
                for instance_id, instance in state_data["instances"].items():
                    if "role" in instance and hasattr(instance["role"], "value"):
                        instance["role"] = instance["role"].value

            async with aiofiles.open(self.state_file, "w") as f:
                await f.write(json.dumps(state_data, indent=2, default=str))

            logger.debug("Saved distributed state to disk")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")


class LoadBalancer:
    """Load balancer for distributing tasks across instances."""

    def select_instance(
        self, instances: List[InstanceInfo], task: DistributedTask
    ) -> Optional[InstanceInfo]:
        """Select the best instance for a task."""
        if not instances:
            return None

        # Score instances based on load and capabilities
        scored_instances = []

        for instance in instances:
            score = self._calculate_instance_score(instance, task)
            scored_instances.append((score, instance))

        # Sort by score (higher is better), use instance_id as tiebreaker
        scored_instances.sort(key=lambda x: (x[0], x[1].instance_id), reverse=True)

        return scored_instances[0][1]

    def _calculate_instance_score(
        self, instance: InstanceInfo, task: DistributedTask
    ) -> float:
        """Calculate score for an instance."""
        # Base score from available capacity
        capacity_score = instance.available_workers / max(1, instance.running_tasks + 1)

        # Resource utilization score (lower usage = higher score)
        cpu_score = (100 - instance.cpu_usage) / 100
        memory_score = (100 - instance.memory_usage) / 100

        # Combine scores
        total_score = capacity_score * 0.4 + cpu_score * 0.3 + memory_score * 0.3

        return total_score
