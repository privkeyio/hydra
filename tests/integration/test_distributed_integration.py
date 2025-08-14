"""Integration tests for distributed execution system."""

import asyncio
import json
import pytest
import pytest_asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from hydra.distributed.coordinator import (
    DistributedCoordinator,
    InstanceRole,
    TaskStatus
)


@pytest.fixture
def temp_dirs(tmp_path):
    """Create temporary directories for multiple instances."""
    return {
        'instance1': str(tmp_path / "instance1"),
        'instance2': str(tmp_path / "instance2"),
        'instance3': str(tmp_path / "instance3")
    }


@pytest_asyncio.fixture
async def coordinator_cluster(temp_dirs):
    """Create a cluster of coordinators for testing."""
    coordinators = {}
    
    # Create multiple coordinators
    for i, (name, temp_dir) in enumerate(temp_dirs.items(), 1):
        coordinator = DistributedCoordinator(
            instance_id=f"test-instance-{i}",
            cluster_id="test-cluster",
            port=8090 + i,
            state_dir=temp_dir,
            heartbeat_interval=1.0,
            election_timeout=3.0
        )
        coordinators[name] = coordinator
    
    yield coordinators
    
    # Cleanup
    for coordinator in coordinators.values():
        if coordinator.running:
            await coordinator.stop()


class TestDistributedIntegration:
    """Integration tests for distributed coordination."""
    
    @pytest.mark.asyncio
    async def test_single_instance_leader_election(self, coordinator_cluster):
        """Test that single instance becomes leader."""
        coordinator = list(coordinator_cluster.values())[0]
        
        # Mock HTTP server setup and background tasks
        with patch.object(coordinator, '_start_http_server', AsyncMock()):
            with patch.object(coordinator, '_start_discovery', AsyncMock()):
                with patch.object(coordinator, '_start_background_tasks', AsyncMock()):
                    await coordinator.start()
                    
                    # Manually trigger election for single instance
                    await coordinator._become_leader()
                    
                    # Single instance should become leader
                    assert coordinator.role == InstanceRole.LEADER
                    assert coordinator.distributed_state.leader_instance == coordinator.instance_id
                    
                    await coordinator.stop()
    
    @pytest.mark.asyncio
    @pytest.mark.stress
    async def test_multi_instance_cluster_formation(self, coordinator_cluster):
        """Test cluster formation with multiple instances."""
        coordinators = list(coordinator_cluster.values())
        
        # Mock network communication between instances
        for coordinator in coordinators:
            coordinator.session = AsyncMock()
            
            # Mock successful health checks
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                'instance_id': 'mock-instance',
                'cluster_id': 'test-cluster',
                'role': 'follower'
            })
            coordinator.session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            
            # Mock discovery of other instances
            coordinator.known_instances = {
                c.instance_id for c in coordinators if c != coordinator
            }
        
        # Start all coordinators
        start_tasks = []
        for coordinator in coordinators:
            with patch.object(coordinator, '_start_http_server', AsyncMock()):
                with patch.object(coordinator, '_start_discovery', AsyncMock()):
                    start_tasks.append(coordinator.start())
        
        await asyncio.gather(*start_tasks)
        
        # Wait for leader election
        await asyncio.sleep(2)
        
        # Exactly one should be leader
        leaders = [c for c in coordinators if c.role == InstanceRole.LEADER]
        followers = [c for c in coordinators if c.role == InstanceRole.FOLLOWER]
        
        assert len(leaders) == 1, f"Expected 1 leader, got {len(leaders)}"
        assert len(followers) == len(coordinators) - 1
        
        # Stop all coordinators
        for coordinator in coordinators:
            await coordinator.stop()
    
    @pytest.mark.asyncio
    async def test_task_distribution_workflow(self, coordinator_cluster):
        """Test end-to-end task distribution workflow."""
        coordinators = list(coordinator_cluster.values())
        leader = coordinators[0]
        followers = coordinators[1:]
        
        # Set up cluster roles
        leader.role = InstanceRole.LEADER
        leader.distributed_state.leader_instance = leader.instance_id
        
        for follower in followers:
            follower.role = InstanceRole.FOLLOWER
            follower.distributed_state.leader_instance = leader.instance_id
            
            # Add follower to leader's known instances
            from hydra.distributed.coordinator import InstanceInfo
            instance_info = InstanceInfo(
                instance_id=follower.instance_id,
                hostname="localhost",
                port=follower.port,
                role=InstanceRole.FOLLOWER,
                last_heartbeat=time.time(),
                cpu_usage=30.0,
                memory_usage=40.0,
                available_workers=3,
                running_tasks=0,
                version="1.0.0",
                cluster_id="test-cluster"
            )
            leader.distributed_state.instances[follower.instance_id] = instance_info
        
        # Mock task assignment notification
        for coordinator in coordinators:
            coordinator.session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status = 200
            coordinator.session.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        
        # Submit tasks to leader
        task_ids = []
        for i in range(3):
            task_id = await leader.submit_task(
                ticket_id=f"00{i+1}",
                description=f"Test task {i+1}",
                priority=i
            )
            task_ids.append(task_id)
        
        # Trigger task distribution
        await leader._distribute_pending_tasks()
        
        # Verify tasks were assigned
        for task_id in task_ids:
            task = leader.distributed_state.tasks[task_id]
            assert task.status == TaskStatus.ASSIGNED
            assert task.assigned_instance in [f.instance_id for f in followers]
    
    @pytest.mark.asyncio
    async def test_distributed_locking_workflow(self, coordinator_cluster):
        """Test distributed locking across instances."""
        coordinators = list(coordinator_cluster.values())
        leader = coordinators[0]
        follower = coordinators[1]
        
        # Set up cluster roles
        leader.role = InstanceRole.LEADER
        follower.role = InstanceRole.FOLLOWER
        follower.distributed_state.leader_instance = leader.instance_id
        
        # Mock network communication
        for coordinator in coordinators:
            coordinator.session = AsyncMock()
        
        # Test lock acquisition by leader
        success = await leader.acquire_distributed_lock("shared-resource", 300)
        assert success
        assert "shared-resource" in leader.distributed_state.locks
        
        lock = leader.distributed_state.locks["shared-resource"]
        assert lock.owner_instance == leader.instance_id
        
        # Test lock conflict
        success = await leader.acquire_distributed_lock("shared-resource", 300)
        assert not success  # Already locked
        
        # Test lock release
        success = await leader.release_distributed_lock("shared-resource")
        assert success
        assert "shared-resource" not in leader.distributed_state.locks
    
    @pytest.mark.asyncio
    @pytest.mark.stress
    async def test_leader_failover_scenario(self, coordinator_cluster):
        """Test leader failover and re-election."""
        coordinators = list(coordinator_cluster.values())
        original_leader = coordinators[0]
        followers = coordinators[1:]
        
        # Set up initial cluster state
        original_leader.role = InstanceRole.LEADER
        original_leader.distributed_state.leader_instance = original_leader.instance_id
        original_leader.term = 1
        
        for follower in followers:
            follower.role = InstanceRole.FOLLOWER
            follower.distributed_state.leader_instance = original_leader.instance_id
            follower.term = 1
            
            # Add to leader's known instances
            follower.known_instances.add(original_leader.instance_id)
            for other in followers:
                if other != follower:
                    follower.known_instances.add(other.instance_id)
        
        # Simulate leader failure by triggering election on followers
        for follower in followers:
            # Simulate timeout - no heartbeat from leader
            follower.last_leader_contact = time.time() - 10
            
            # Mock vote responses
            follower.session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={'vote_granted': True})
            follower.session.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        
        # Trigger election on one follower
        candidate = followers[0]
        await candidate._trigger_election()
        await candidate._conduct_election()
        
        # Candidate should become new leader
        assert candidate.role == InstanceRole.LEADER
        assert candidate.term > 1
    
    @pytest.mark.asyncio
    async def test_state_synchronization(self, coordinator_cluster):
        """Test state synchronization between instances."""
        coordinators = list(coordinator_cluster.values())
        leader = coordinators[0]
        follower = coordinators[1]
        
        # Set up cluster roles
        leader.role = InstanceRole.LEADER
        follower.role = InstanceRole.FOLLOWER
        follower.distributed_state.leader_instance = leader.instance_id
        
        # Mock HTTP communication
        leader.session = AsyncMock()
        follower.session = AsyncMock()
        
        # Add a task to leader's state
        task_id = await leader.submit_task("001", "Sync test task")
        
        # Simulate state sync from leader to follower
        state_data = {
            'cluster_id': leader.cluster_id,
            'leader_instance': leader.instance_id,
            'instances': {},
            'tasks': {
                task_id: {
                    'task_id': task_id,
                    'ticket_id': '001',
                    'description': 'Sync test task',
                    'assigned_instance': None,
                    'status': 'pending',
                    'priority': 0,
                    'created_at': time.time(),
                    'started_at': None,
                    'completed_at': None,
                    'result': None,
                    'error': None
                }
            },
            'locks': {},
            'last_updated': time.time(),
            'term': 1
        }
        
        await follower._update_local_state(state_data)
        
        # Verify follower has the synced task
        assert task_id in follower.distributed_state.tasks
        synced_task = follower.distributed_state.tasks[task_id]
        assert synced_task.ticket_id == "001"
        assert synced_task.description == "Sync test task"
    
    @pytest.mark.asyncio
    async def test_network_partition_recovery(self, coordinator_cluster):
        """Test recovery from network partitions."""
        coordinators = list(coordinator_cluster.values())
        leader = coordinators[0]
        follower = coordinators[1]
        
        # Set up initial cluster state
        leader.role = InstanceRole.LEADER
        follower.role = InstanceRole.FOLLOWER
        follower.distributed_state.leader_instance = leader.instance_id
        
        # Add instances to each other's knowledge
        from hydra.distributed.coordinator import InstanceInfo
        follower_info = InstanceInfo(
            instance_id=follower.instance_id,
            hostname="localhost",
            port=follower.port,
            role=InstanceRole.FOLLOWER,
            last_heartbeat=time.time(),
            cpu_usage=30.0,
            memory_usage=40.0,
            available_workers=3,
            running_tasks=0,
            version="1.0.0",
            cluster_id="test-cluster"
        )
        leader.distributed_state.instances[follower.instance_id] = follower_info
        
        # Mock network partition - leader can't reach followers
        leader.session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 500  # Connection failed
        leader.session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        
        # Trigger partition handling
        await leader.handle_network_partition()
        
        # Leader should step down due to losing majority
        assert leader.role == InstanceRole.FOLLOWER
        assert leader.distributed_state.leader_instance is None
        
        # Mock follower detecting partition
        follower.session = AsyncMock()
        follower.session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        
        with patch.object(follower, '_trigger_election', AsyncMock()) as mock_election:
            await follower.handle_network_partition()
            mock_election.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_load_balancing_across_instances(self, coordinator_cluster):
        """Test load balancing of tasks across instances."""
        coordinators = list(coordinator_cluster.values())
        leader = coordinators[0]
        
        # Set up leader
        leader.role = InstanceRole.LEADER
        
        # Add multiple worker instances with different loads
        from hydra.distributed.coordinator import InstanceInfo
        
        # High-load instance
        high_load_instance = InstanceInfo(
            instance_id="high-load-worker",
            hostname="high-load.local",
            port=8091,
            role=InstanceRole.FOLLOWER,
            last_heartbeat=time.time(),
            cpu_usage=80.0,  # High CPU usage
            memory_usage=70.0,
            available_workers=1,
            running_tasks=5,
            version="1.0.0",
            cluster_id="test-cluster"
        )
        
        # Low-load instance
        low_load_instance = InstanceInfo(
            instance_id="low-load-worker",
            hostname="low-load.local",
            port=8092,
            role=InstanceRole.FOLLOWER,
            last_heartbeat=time.time(),
            cpu_usage=20.0,  # Low CPU usage
            memory_usage=30.0,
            available_workers=4,
            running_tasks=1,
            version="1.0.0",
            cluster_id="test-cluster"
        )
        
        leader.distributed_state.instances["high-load-worker"] = high_load_instance
        leader.distributed_state.instances["low-load-worker"] = low_load_instance
        
        # Mock task notification
        leader.session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        leader.session.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        
        # Submit multiple tasks
        task_ids = []
        for i in range(3):
            task_id = await leader.submit_task(f"00{i+1}", f"Load balance test {i+1}")
            task_ids.append(task_id)
        
        # Distribute tasks
        await leader._distribute_pending_tasks()
        
        # Check task assignments - should prefer low-load instance
        low_load_assignments = 0
        high_load_assignments = 0
        
        for task_id in task_ids:
            task = leader.distributed_state.tasks[task_id]
            if task.assigned_instance == "low-load-worker":
                low_load_assignments += 1
            elif task.assigned_instance == "high-load-worker":
                high_load_assignments += 1
        
        # Low-load instance should get more tasks
        assert low_load_assignments > high_load_assignments
    
    @pytest.mark.asyncio
    @pytest.mark.stress
    async def test_persistent_state_across_restarts(self, temp_dirs):
        """Test that state persists across coordinator restarts."""
        temp_dir = temp_dirs['instance1']
        
        # Create first coordinator instance
        coordinator1 = DistributedCoordinator(
            instance_id="persistent-test",
            cluster_id="test-cluster",
            state_dir=temp_dir
        )
        
        # Add some state
        coordinator1.role = InstanceRole.LEADER
        coordinator1.term = 5
        coordinator1.distributed_state.leader_instance = "persistent-test"
        
        # Submit a task
        task_id = await coordinator1.submit_task("999", "Persistence test task", priority=10)
        
        # Save state
        await coordinator1._save_state()
        
        # Create second coordinator instance (simulating restart)
        coordinator2 = DistributedCoordinator(
            instance_id="persistent-test-2",
            cluster_id="test-cluster", 
            state_dir=temp_dir
        )
        
        # Load state
        await coordinator2._load_state()
        
        # Verify state was restored
        assert coordinator2.distributed_state.leader_instance == "persistent-test"
        assert coordinator2.distributed_state.term == 5
        assert task_id in coordinator2.distributed_state.tasks
        
        restored_task = coordinator2.distributed_state.tasks[task_id]
        assert restored_task.ticket_id == "999"
        assert restored_task.description == "Persistence test task"
        assert restored_task.priority == 10


if __name__ == '__main__':
    pytest.main([__file__])