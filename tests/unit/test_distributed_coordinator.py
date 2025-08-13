"""Tests for distributed execution coordinator."""

import asyncio
import json
import pytest
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from hydra.distributed.coordinator import (
    DistributedCoordinator,
    DistributedState,
    DistributedTask,
    InstanceInfo,
    InstanceRole,
    TaskStatus,
    LoadBalancer
)


@pytest.fixture
def temp_state_dir(tmp_path):
    """Create temporary state directory."""
    return str(tmp_path / "distributed_state")


@pytest.fixture
def coordinator(temp_state_dir):
    """Create test coordinator."""
    return DistributedCoordinator(
        instance_id="test-instance-1",
        cluster_id="test-cluster",
        port=8090,
        state_dir=temp_state_dir,
        heartbeat_interval=1.0,
        election_timeout=5.0
    )


@pytest.fixture
def mock_resource_tracker():
    """Mock resource tracker."""
    tracker = MagicMock()
    tracker.get_current_metrics.return_value = {
        'cpu_percent': 25.0,
        'memory_percent': 40.0
    }
    return tracker


class TestDistributedCoordinator:
    """Test distributed coordinator functionality."""
    
    @pytest.mark.asyncio
    async def test_initialization(self, coordinator, temp_state_dir):
        """Test coordinator initialization."""
        assert coordinator.instance_id == "test-instance-1"
        assert coordinator.cluster_id == "test-cluster"
        assert coordinator.port == 8090
        assert coordinator.role == InstanceRole.FOLLOWER
        assert coordinator.state_dir == Path(temp_state_dir)
        assert not coordinator.running
    
    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self, coordinator):
        """Test starting and stopping coordinator."""
        with patch.object(coordinator, '_start_http_server', AsyncMock()):
            with patch.object(coordinator, '_start_background_tasks', AsyncMock()):
                with patch.object(coordinator, '_start_discovery', AsyncMock()):
                    await coordinator.start()
                    assert coordinator.running
                    
                    await coordinator.stop()
                    assert not coordinator.running
    
    @pytest.mark.asyncio
    async def test_leader_election_trigger(self, coordinator):
        """Test triggering leader election."""
        coordinator.last_leader_contact = time.time() - 20  # Simulate timeout
        
        await coordinator._trigger_election()
        
        assert coordinator.role == InstanceRole.CANDIDATE
        assert coordinator.term > 0
        assert coordinator.votes_received == 1  # Vote for self
    
    @pytest.mark.asyncio
    async def test_become_leader(self, coordinator):
        """Test becoming cluster leader."""
        coordinator.role = InstanceRole.CANDIDATE
        coordinator.term = 1
        
        with patch.object(coordinator, '_announce_leadership', AsyncMock()):
            await coordinator._become_leader()
        
        assert coordinator.role == InstanceRole.LEADER
        assert coordinator.distributed_state.leader_instance == coordinator.instance_id
        assert coordinator.distributed_state.term == coordinator.term
    
    @pytest.mark.asyncio
    async def test_task_submission_as_leader(self, coordinator):
        """Test submitting tasks as leader."""
        coordinator.role = InstanceRole.LEADER
        
        task_id = await coordinator.submit_task(
            ticket_id="001",
            description="Test task",
            priority=1
        )
        
        assert task_id in coordinator.distributed_state.tasks
        task = coordinator.distributed_state.tasks[task_id]
        assert task.ticket_id == "001"
        assert task.description == "Test task"
        assert task.priority == 1
        assert task.status == TaskStatus.PENDING
    
    @pytest.mark.asyncio
    async def test_task_submission_as_follower(self, coordinator):
        """Test submitting tasks as follower (should forward to leader)."""
        coordinator.role = InstanceRole.FOLLOWER
        coordinator.distributed_state.leader_instance = "leader-instance"
        
        # Mock leader instance
        leader_instance = InstanceInfo(
            instance_id="leader-instance",
            hostname="localhost",
            port=8091,
            role=InstanceRole.LEADER,
            last_heartbeat=time.time(),
            cpu_usage=30.0,
            memory_usage=50.0,
            available_workers=5,
            running_tasks=2,
            version="1.0.0",
            cluster_id="test-cluster"
        )
        coordinator.distributed_state.instances["leader-instance"] = leader_instance
        
        # Mock HTTP session response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={'task_id': 'forwarded-task-123'})
        
        coordinator.session = AsyncMock()
        coordinator.session.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        coordinator.session.post.return_value.__aexit__ = AsyncMock(return_value=None)
        
        task_id = await coordinator.submit_task("002", "Forwarded task")
        
        assert task_id == "forwarded-task-123"
        coordinator.session.post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_distributed_lock_acquisition(self, coordinator):
        """Test acquiring distributed locks."""
        coordinator.role = InstanceRole.LEADER
        
        # Test successful lock acquisition
        success = await coordinator._acquire_lock_locally("resource-1", 300)
        assert success
        assert "resource-1" in coordinator.distributed_state.locks
        
        lock = coordinator.distributed_state.locks["resource-1"]
        assert lock.owner_instance == coordinator.instance_id
        assert lock.expires_at > time.time()
        
        # Test lock conflict
        success = await coordinator._acquire_lock_locally("resource-1", 300)
        assert not success  # Already locked
    
    @pytest.mark.asyncio
    async def test_distributed_lock_release(self, coordinator):
        """Test releasing distributed locks."""
        coordinator.role = InstanceRole.LEADER
        
        # Acquire a lock first
        await coordinator._acquire_lock_locally("resource-2", 300)
        
        # Test successful release
        success = await coordinator.release_distributed_lock("resource-2")
        assert success
        assert "resource-2" not in coordinator.distributed_state.locks
        
        # Test releasing non-existent lock
        success = await coordinator.release_distributed_lock("resource-nonexistent")
        assert not success
    
    @pytest.mark.asyncio
    async def test_lock_cleanup(self, coordinator):
        """Test cleanup of expired locks."""
        coordinator.role = InstanceRole.LEADER
        
        # Create expired lock
        from hydra.distributed.coordinator import DistributedLock
        expired_lock = DistributedLock(
            resource_id="expired-resource",
            owner_instance=coordinator.instance_id,
            acquired_at=time.time() - 600,
            expires_at=time.time() - 300  # Expired 5 minutes ago
        )
        coordinator.distributed_state.locks["expired-resource"] = expired_lock
        
        # Create valid lock
        valid_lock = DistributedLock(
            resource_id="valid-resource",
            owner_instance=coordinator.instance_id,
            acquired_at=time.time(),
            expires_at=time.time() + 300
        )
        coordinator.distributed_state.locks["valid-resource"] = valid_lock
        
        await coordinator._cleanup_expired_locks()
        
        # Expired lock should be removed
        assert "expired-resource" not in coordinator.distributed_state.locks
        # Valid lock should remain
        assert "valid-resource" in coordinator.distributed_state.locks
    
    @pytest.mark.asyncio
    async def test_task_distribution(self, coordinator):
        """Test distributing tasks to available instances."""
        coordinator.role = InstanceRole.LEADER
        
        # Add some tasks
        task1 = DistributedTask(
            task_id="task-1",
            ticket_id="001",
            description="High priority task",
            assigned_instance=None,
            status=TaskStatus.PENDING,
            priority=10,
            created_at=time.time()
        )
        task2 = DistributedTask(
            task_id="task-2", 
            ticket_id="002",
            description="Low priority task",
            assigned_instance=None,
            status=TaskStatus.PENDING,
            priority=1,
            created_at=time.time()
        )
        
        coordinator.distributed_state.tasks["task-1"] = task1
        coordinator.distributed_state.tasks["task-2"] = task2
        
        # Add available instance
        instance = InstanceInfo(
            instance_id="worker-1",
            hostname="worker1.local",
            port=8090,
            role=InstanceRole.FOLLOWER,
            last_heartbeat=time.time(),
            cpu_usage=30.0,
            memory_usage=40.0,
            available_workers=2,
            running_tasks=0,
            version="1.0.0",
            cluster_id="test-cluster"
        )
        coordinator.distributed_state.instances["worker-1"] = instance
        
        with patch.object(coordinator, '_notify_task_assignment', AsyncMock()):
            await coordinator._distribute_pending_tasks()
        
        # High priority task should be assigned first
        assert task1.status == TaskStatus.ASSIGNED
        assert task1.assigned_instance == "worker-1"
        assert task2.status == TaskStatus.ASSIGNED
        assert task2.assigned_instance == "worker-1"
        
        # Instance load should be updated
        assert instance.available_workers == 0  # 2 - 2 = 0
        assert instance.running_tasks == 2
    
    @pytest.mark.asyncio
    async def test_network_partition_detection(self, coordinator):
        """Test network partition detection and handling."""
        coordinator.role = InstanceRole.FOLLOWER
        coordinator.distributed_state.leader_instance = "leader-1"
        
        # Add leader instance
        leader = InstanceInfo(
            instance_id="leader-1",
            hostname="leader.local",
            port=8090,
            role=InstanceRole.LEADER,
            last_heartbeat=time.time() - 100,  # Old heartbeat
            cpu_usage=50.0,
            memory_usage=60.0,
            available_workers=3,
            running_tasks=1,
            version="1.0.0",
            cluster_id="test-cluster"
        )
        coordinator.distributed_state.instances["leader-1"] = leader
        
        # Mock unreachable leader
        coordinator.session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 500  # Connection failed
        coordinator.session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        coordinator.session.get.return_value.__aexit__ = AsyncMock(return_value=None)
        
        with patch.object(coordinator, '_trigger_election', AsyncMock()) as mock_election:
            await coordinator.handle_network_partition()
            mock_election.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_state_persistence(self, coordinator, temp_state_dir):
        """Test saving and loading distributed state."""
        # Set up some state
        coordinator.distributed_state.leader_instance = "leader-1"
        coordinator.distributed_state.term = 5
        
        # Add a task
        task = DistributedTask(
            task_id="persist-task",
            ticket_id="999",
            description="Persistence test",
            assigned_instance=None,
            status=TaskStatus.PENDING,
            priority=5,
            created_at=time.time()
        )
        coordinator.distributed_state.tasks["persist-task"] = task
        
        # Save state
        await coordinator._save_state()
        
        # Verify file was created
        state_file = Path(temp_state_dir) / "cluster_state.json"
        assert state_file.exists()
        
        # Create new coordinator and load state
        new_coordinator = DistributedCoordinator(
            instance_id="test-instance-2",
            cluster_id="test-cluster",
            state_dir=temp_state_dir
        )
        
        await new_coordinator._load_state()
        
        # Verify state was loaded
        assert new_coordinator.distributed_state.leader_instance == "leader-1"
        assert new_coordinator.distributed_state.term == 5
        assert "persist-task" in new_coordinator.distributed_state.tasks
        
        loaded_task = new_coordinator.distributed_state.tasks["persist-task"]
        assert loaded_task.ticket_id == "999"
        assert loaded_task.description == "Persistence test"
    
    def test_get_cluster_info(self, coordinator):
        """Test getting cluster information."""
        # Add some state
        coordinator.role = InstanceRole.LEADER
        coordinator.term = 3
        coordinator.distributed_state.leader_instance = coordinator.instance_id
        
        # Add tasks
        for i in range(5):
            task = DistributedTask(
                task_id=f"task-{i}",
                ticket_id=f"00{i}",
                description=f"Task {i}",
                assigned_instance=None,
                status=TaskStatus.PENDING if i < 2 else (
                    TaskStatus.RUNNING if i < 4 else TaskStatus.COMPLETED
                ),
                priority=i,
                created_at=time.time()
            )
            coordinator.distributed_state.tasks[f"task-{i}"] = task
        
        info = coordinator.get_cluster_info()
        
        assert info['instance_id'] == coordinator.instance_id
        assert info['cluster_id'] == "test-cluster"
        assert info['role'] == "leader"
        assert info['term'] == 3
        assert info['leader'] == coordinator.instance_id
        assert info['tasks']['total'] == 5
        assert info['tasks']['pending'] == 2
        assert info['tasks']['running'] == 2
        assert info['tasks']['completed'] == 1


class TestLoadBalancer:
    """Test load balancer functionality."""
    
    def test_instance_selection(self):
        """Test selecting best instance for task."""
        balancer = LoadBalancer()
        
        # Create instances with different loads
        instance1 = InstanceInfo(
            instance_id="worker-1",
            hostname="worker1.local",
            port=8090,
            role=InstanceRole.FOLLOWER,
            last_heartbeat=time.time(),
            cpu_usage=90.0,  # High CPU
            memory_usage=40.0,
            available_workers=1,
            running_tasks=5,
            version="1.0.0",
            cluster_id="test-cluster"
        )
        
        instance2 = InstanceInfo(
            instance_id="worker-2",
            hostname="worker2.local", 
            port=8090,
            role=InstanceRole.FOLLOWER,
            last_heartbeat=time.time(),
            cpu_usage=20.0,  # Low CPU
            memory_usage=30.0,
            available_workers=3,
            running_tasks=1,
            version="1.0.0",
            cluster_id="test-cluster"
        )
        
        task = DistributedTask(
            task_id="test-task",
            ticket_id="001",
            description="Test task",
            assigned_instance=None,
            status=TaskStatus.PENDING,
            priority=1,
            created_at=time.time()
        )
        
        instances = [instance1, instance2]
        selected = balancer.select_instance(instances, task)
        
        # Should select instance2 due to better resource availability
        assert selected == instance2
    
    def test_instance_scoring(self):
        """Test instance scoring algorithm."""
        balancer = LoadBalancer()
        
        instance = InstanceInfo(
            instance_id="test-worker",
            hostname="test.local",
            port=8090,
            role=InstanceRole.FOLLOWER,
            last_heartbeat=time.time(),
            cpu_usage=50.0,
            memory_usage=60.0,
            available_workers=4,
            running_tasks=2,
            version="1.0.0",
            cluster_id="test-cluster"
        )
        
        task = DistributedTask(
            task_id="test-task",
            ticket_id="001",
            description="Test task",
            assigned_instance=None,
            status=TaskStatus.PENDING,
            priority=1,
            created_at=time.time()
        )
        
        score = balancer._calculate_instance_score(instance, task)
        
        # Score should be a float between 0 and 1
        assert 0.0 <= score <= 1.0
        assert isinstance(score, float)
    
    def test_empty_instance_list(self):
        """Test handling empty instance list."""
        balancer = LoadBalancer()
        
        task = DistributedTask(
            task_id="test-task",
            ticket_id="001", 
            description="Test task",
            assigned_instance=None,
            status=TaskStatus.PENDING,
            priority=1,
            created_at=time.time()
        )
        
        selected = balancer.select_instance([], task)
        assert selected is None


@pytest.mark.asyncio
async def test_http_handlers(coordinator, temp_state_dir):
    """Test HTTP API handlers."""
    from aiohttp.test_utils import make_mocked_request
    
    # Mock resource tracker
    coordinator.resource_tracker = MagicMock()
    coordinator.resource_tracker.get_current_metrics.return_value = {
        'cpu_percent': 35.0,
        'memory_percent': 45.0
    }
    
    # Test health handler
    request = make_mocked_request('GET', '/health')
    response = await coordinator._handle_health(request)
    
    assert response.status == 200
    data = json.loads(response.text)
    assert data['instance_id'] == coordinator.instance_id
    assert data['cluster_id'] == coordinator.cluster_id
    assert 'cpu_usage' in data
    assert 'memory_usage' in data
    
    # Test heartbeat handler
    heartbeat_data = {
        'instance_id': 'sender-123',
        'role': 'leader',
        'term': 1,
        'timestamp': time.time()
    }
    request = make_mocked_request('POST', '/heartbeat')
    request.json = AsyncMock(return_value=heartbeat_data)
    response = await coordinator._handle_heartbeat(request)
    
    assert response.status == 200
    data = json.loads(response.text)
    assert data['status'] == 'ok'
    
    # Test vote request handler
    vote_data = {
        'candidate_id': 'candidate-456',
        'term': 2,
        'timestamp': time.time()
    }
    request = make_mocked_request('POST', '/vote_request')
    request.json = AsyncMock(return_value=vote_data)
    response = await coordinator._handle_vote_request(request)
    
    assert response.status == 200
    data = json.loads(response.text)
    assert 'vote_granted' in data
    assert isinstance(data['vote_granted'], bool)


@pytest.mark.asyncio
async def test_discovery_loop(coordinator):
    """Test instance discovery functionality."""
    coordinator.running = True
    
    # Mock network scanning
    with patch.object(coordinator, '_scan_for_instances', AsyncMock()) as mock_scan:
        with patch('asyncio.sleep', AsyncMock(side_effect=[None, Exception("Stop")])):
            try:
                await coordinator._discovery_loop()
            except Exception:
                pass  # Expected to exit loop
            
            mock_scan.assert_called()
    

if __name__ == '__main__':
    pytest.main([__file__])