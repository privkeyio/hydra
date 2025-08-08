import json
import tempfile
import time
import unittest
from pathlib import Path

from hydra.state.project_state import (
    ProjectState, ProjectStateManager, ProjectStatus, CheckpointType,
    Checkpoint, Operation, StateSerializer, StateStorage
)


class TestStateSerializer(unittest.TestCase):
    def setUp(self):
        self.state = ProjectState(
            project_id="test_project",
            name="Test Project",
            status=ProjectStatus.RUNNING,
            created_at=time.time(),
            updated_at=time.time(),
            total_operations=10,
            success_rate=0.8,
            metadata={"version": "1.0"}
        )

    def test_serialize_deserialize(self):
        serialized = StateSerializer.serialize_state(self.state)
        deserialized = StateSerializer.deserialize_state(serialized)
        
        self.assertEqual(deserialized.project_id, self.state.project_id)
        self.assertEqual(deserialized.name, self.state.name)
        self.assertEqual(deserialized.status, self.state.status)
        self.assertEqual(deserialized.total_operations, self.state.total_operations)

    def test_export_import_json(self):
        json_str = StateSerializer.export_json(self.state)
        imported_state = StateSerializer.import_json(json_str)
        
        self.assertEqual(imported_state.project_id, self.state.project_id)
        self.assertEqual(imported_state.status, self.state.status)
        self.assertEqual(imported_state.metadata, self.state.metadata)

    def test_json_format(self):
        json_str = StateSerializer.export_json(self.state)
        data = json.loads(json_str)
        
        self.assertIn('project_id', data)
        self.assertIn('created_at', data)
        self.assertIn('status', data)
        self.assertEqual(data['status'], 'running')


class TestStateStorage(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.storage = StateStorage(self.temp_db.name)
        
        self.state = ProjectState(
            project_id="test_project",
            name="Test Project", 
            status=ProjectStatus.RUNNING,
            created_at=time.time(),
            updated_at=time.time()
        )

    def tearDown(self):
        Path(self.temp_db.name).unlink(missing_ok=True)

    def test_save_load_state(self):
        self.storage.save_state(self.state)
        loaded_state = self.storage.load_state("test_project")
        
        self.assertIsNotNone(loaded_state)
        self.assertEqual(loaded_state.project_id, self.state.project_id)
        self.assertEqual(loaded_state.status, self.state.status)

    def test_load_nonexistent_state(self):
        loaded_state = self.storage.load_state("nonexistent")
        self.assertIsNone(loaded_state)

    def test_save_load_checkpoint(self):
        checkpoint = Checkpoint(
            id="test_checkpoint",
            timestamp=time.time(),
            checkpoint_type=CheckpointType.MANUAL,
            state_hash="abc123",
            description="Test checkpoint",
            operations_count=5,
            metadata={"project_id": "test_project"}
        )
        
        self.storage.save_checkpoint(checkpoint)
        checkpoints = self.storage.load_checkpoints("test_project")
        
        self.assertEqual(len(checkpoints), 1)
        self.assertEqual(checkpoints[0].id, "test_checkpoint")
        self.assertEqual(checkpoints[0].checkpoint_type, CheckpointType.MANUAL)

    def test_save_load_operation(self):
        operation = Operation(
            id="test_op",
            timestamp=time.time(),
            operation_type="test",
            details={"action": "test_action"},
            success=True,
            duration_ms=100
        )
        
        self.storage.save_operation(operation, "test_project")
        operations = self.storage.load_operations("test_project")
        
        self.assertEqual(len(operations), 1)
        self.assertEqual(operations[0].id, "test_op")
        self.assertTrue(operations[0].success)
        self.assertEqual(operations[0].details["action"], "test_action")

    def test_operations_limit(self):
        for i in range(15):
            operation = Operation(
                id=f"op_{i}",
                timestamp=time.time(),
                operation_type="test",
                details={"index": i},
                success=True
            )
            self.storage.save_operation(operation, "test_project")
        
        operations = self.storage.load_operations("test_project", limit=10)
        self.assertEqual(len(operations), 10)


class TestProjectStateManager(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.manager = ProjectStateManager(self.temp_db.name)

    def tearDown(self):
        Path(self.temp_db.name).unlink(missing_ok=True)

    def test_create_project(self):
        state = self.manager.create_project(
            "test_project", 
            "Test Project",
            {"version": "1.0"}
        )
        
        self.assertEqual(state.project_id, "test_project")
        self.assertEqual(state.status, ProjectStatus.INITIALIZED)
        self.assertEqual(state.metadata["version"], "1.0")

    def test_get_project_state(self):
        self.manager.create_project("test_project", "Test Project")
        
        state = self.manager.get_project_state("test_project")
        self.assertIsNotNone(state)
        self.assertEqual(state.project_id, "test_project")

    def test_get_nonexistent_project(self):
        state = self.manager.get_project_state("nonexistent")
        self.assertIsNone(state)

    def test_update_project_status(self):
        self.manager.create_project("test_project", "Test Project")
        self.manager.update_project_status("test_project", ProjectStatus.COMPLETED)
        
        state = self.manager.get_project_state("test_project")
        self.assertEqual(state.status, ProjectStatus.COMPLETED)

    def test_record_operation(self):
        self.manager.create_project("test_project", "Test Project")
        
        self.manager.record_operation(
            "test_project",
            "test_operation",
            {"action": "test"},
            success=True,
            duration_ms=150
        )
        
        state = self.manager.get_project_state("test_project")
        self.assertEqual(state.total_operations, 1)
        self.assertEqual(state.success_rate, 1.0)

    def test_record_failed_operation(self):
        self.manager.create_project("test_project", "Test Project")
        
        self.manager.record_operation(
            "test_project",
            "test_operation",
            {"action": "test"},
            success=False,
            error_message="Test error"
        )
        
        state = self.manager.get_project_state("test_project")
        self.assertEqual(state.total_operations, 1)
        self.assertEqual(state.success_rate, 0.0)

    def test_create_checkpoint(self):
        self.manager.create_project("test_project", "Test Project")
        
        checkpoint = self.manager.create_checkpoint(
            "test_project",
            CheckpointType.MANUAL,
            "Manual checkpoint"
        )
        
        self.assertEqual(checkpoint.checkpoint_type, CheckpointType.MANUAL)
        self.assertEqual(checkpoint.description, "Manual checkpoint")
        
        state = self.manager.get_project_state("test_project")
        self.assertEqual(state.current_checkpoint, checkpoint.id)

    def test_resume_from_checkpoint(self):
        self.manager.create_project("test_project", "Test Project")
        
        checkpoint = self.manager.create_checkpoint(
            "test_project",
            CheckpointType.MANUAL,
            "Before resume"
        )
        
        success = self.manager.resume_from_checkpoint("test_project", checkpoint.id)
        self.assertTrue(success)
        
        state = self.manager.get_project_state("test_project")
        self.assertEqual(state.status, ProjectStatus.RUNNING)
        self.assertEqual(state.current_checkpoint, checkpoint.id)

    def test_resume_nonexistent_checkpoint(self):
        self.manager.create_project("test_project", "Test Project")
        
        success = self.manager.resume_from_checkpoint("test_project", "nonexistent")
        self.assertFalse(success)

    def test_get_project_history(self):
        self.manager.create_project("test_project", "Test Project")
        
        self.manager.record_operation(
            "test_project", "test_op", {"action": "test"}, success=True
        )
        
        self.manager.create_checkpoint(
            "test_project", CheckpointType.MANUAL, "Test checkpoint"
        )
        
        history = self.manager.get_project_history("test_project")
        
        self.assertIsNotNone(history['state'])
        self.assertGreater(len(history['checkpoints']), 0)
        self.assertGreater(len(history['recent_operations']), 0)
        self.assertGreater(history['uptime_hours'], 0)

    def test_export_import_project(self):
        self.manager.create_project("test_project", "Test Project", {"key": "value"})
        
        self.manager.record_operation(
            "test_project", "test_op", {"action": "test"}, success=True
        )
        
        self.manager.create_checkpoint(
            "test_project", CheckpointType.MANUAL, "Export checkpoint"
        )
        
        exported_data = self.manager.export_project("test_project")
        
        self.assertIn('state', exported_data)
        self.assertIn('checkpoints', exported_data)
        self.assertIn('operations', exported_data)
        
        new_project_id = self.manager.import_project(exported_data)
        self.assertEqual(new_project_id, "test_project")
        
        imported_state = self.manager.get_project_state("test_project")
        self.assertEqual(imported_state.metadata["key"], "value")

    def test_export_nonexistent_project(self):
        with self.assertRaises(ValueError):
            self.manager.export_project("nonexistent")

    def test_visualize_progress(self):
        self.manager.create_project("test_project", "Test Project")
        
        for i in range(3):
            self.manager.record_operation(
                "test_project", f"op_{i}", {"index": i}, success=i % 2 == 0
            )
        
        self.manager.create_checkpoint(
            "test_project", CheckpointType.AUTO, "Auto checkpoint"
        )
        
        visualization = self.manager.visualize_progress("test_project")
        
        self.assertEqual(visualization['project_id'], "test_project")
        self.assertIn('progress', visualization)
        self.assertIn('timeline', visualization)
        self.assertGreater(len(visualization['timeline']), 0)

    def test_visualize_nonexistent_project(self):
        visualization = self.manager.visualize_progress("nonexistent")
        self.assertIn('error', visualization)

    def test_success_rate_calculation(self):
        self.manager.create_project("test_project", "Test Project")
        
        # Add 3 successful and 1 failed operation
        for i in range(4):
            self.manager.record_operation(
                "test_project", f"op_{i}", {"index": i}, success=i != 1
            )
        
        state = self.manager.get_project_state("test_project")
        self.assertEqual(state.total_operations, 4)
        self.assertEqual(state.success_rate, 0.75)  # 3/4 success

    def test_auto_checkpoint_creation(self):
        # Mock auto checkpoint interval to be very short
        self.manager._auto_checkpoint_interval = 0.1  # 100ms
        
        self.manager.create_project("test_project", "Test Project")
        
        # Wait for auto checkpoint interval
        time.sleep(0.2)
        
        self.manager.record_operation(
            "test_project", "trigger_auto_checkpoint", {"test": True}, success=True
        )
        
        checkpoints = self.manager.storage.load_checkpoints("test_project")
        auto_checkpoints = [c for c in checkpoints if c.checkpoint_type == CheckpointType.AUTO]
        
        # Should have at least one auto checkpoint
        self.assertGreaterEqual(len(auto_checkpoints), 1)


if __name__ == '__main__':
    unittest.main()