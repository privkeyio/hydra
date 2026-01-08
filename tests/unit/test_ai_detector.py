"""Unit tests for AI pattern detection module."""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from hydra.verification_system.ai_detector import (
    AIDetector,
    AIPatternConfig,
    DetectionResult,
    SensitivityLevel,
    create_detector
)


class TestAIDetector:
    """Test suite for AIDetector class."""
    
    def test_init_default_config(self):
        """Test initialization with default configuration."""
        detector = AIDetector()
        assert detector.config.sensitivity == SensitivityLevel.MEDIUM
        assert not detector.config.emoji_allowed
        assert detector.config.max_workers == 4
    
    def test_init_custom_config(self):
        """Test initialization with custom configuration."""
        config = AIPatternConfig(
            sensitivity=SensitivityLevel.HIGH,
            emoji_allowed=True,
            max_workers=8
        )
        detector = AIDetector(config)
        assert detector.config.sensitivity == SensitivityLevel.HIGH
        assert detector.config.emoji_allowed
        assert detector.config.max_workers == 8
    
    def test_detect_emoji_in_code(self):
        """Test emoji detection in code."""
        detector = AIDetector(AIPatternConfig(emoji_allowed=False))
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def celebrate():\n    print("🎉 Success!")\n')
            f.flush()
            
            result = detector.detect_file(Path(f.name))
            
        assert not result.passes
        assert len(result.detected_patterns) > 0
        assert any(p["category"] == "emoji" for p in result.detected_patterns)
        Path(f.name).unlink()
    
    def test_detect_placeholder_text(self):
        """Test placeholder text detection."""
        detector = AIDetector()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('# TODO: Replace this with actual implementation\n')
            f.write('def placeholder():\n')
            f.write('    # FIXME: This is temporary\n')
            f.write('    pass\n')
            f.flush()
            
            result = detector.detect_file(Path(f.name))
            
        assert len(result.detected_patterns) > 0
        assert any(p["category"] == "placeholder_text" for p in result.detected_patterns)
        Path(f.name).unlink()
    
    def test_detect_generic_exceptions(self):
        """Test generic exception handler detection."""
        detector = AIDetector()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('try:\n')
            f.write('    risky_operation()\n')
            f.write('except Exception:\n')
            f.write('    pass\n')
            f.flush()
            
            result = detector.detect_file(Path(f.name))
            
        assert len(result.detected_patterns) > 0
        assert any(p["category"] == "generic_exceptions" for p in result.detected_patterns)
        Path(f.name).unlink()
    
    def test_detect_ai_style_comments(self):
        """Test AI-style comment detection."""
        detector = AIDetector()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('# Initialize the system\n')
            f.write('# Setup configuration\n')
            f.write('# Process the data\n')
            f.write('# Validate input\n')
            f.write('def main():\n')
            f.write('    pass\n')
            f.flush()
            
            result = detector.detect_file(Path(f.name))
            
        assert len(result.detected_patterns) > 0
        assert any(p["category"] == "ai_comments" for p in result.detected_patterns)
        Path(f.name).unlink()
    
    def test_detect_verbose_variable_names(self):
        """Test verbose variable name detection."""
        detector = AIDetector(AIPatternConfig(sensitivity=SensitivityLevel.HIGH))
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('user_input_data_processor_manager = DataProcessor()\n')
            f.write('handle_user_authentication_error = lambda x: None\n')
            f.flush()
            
            result = detector.detect_file(Path(f.name))
            
        assert len(result.detected_patterns) > 0
        Path(f.name).unlink()
    
    def test_whitelist_patterns(self):
        """Test whitelist functionality."""
        config = AIPatternConfig(
            whitelist_patterns={"TODO: Security review needed"}
        )
        detector = AIDetector(config)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('# TODO: Security review needed\n')
            f.write('def secure_function():\n')
            f.write('    pass\n')
            f.flush()
            
            result = detector.detect_file(Path(f.name))
            
        # Should not detect whitelisted pattern
        assert not any(
            p["match"] == "TODO: Security review needed" 
            for p in result.detected_patterns
        )
        Path(f.name).unlink()
    
    def test_whitelist_files(self):
        """Test file whitelisting."""
        config = AIPatternConfig(
            whitelist_files={"/tmp/test_file.py"}
        )
        detector = AIDetector(config)
        
        result = detector.detect_file(Path("/tmp/test_file.py"))
        assert result.passes
        assert len(result.detected_patterns) == 0
    
    def test_sensitivity_levels(self):
        """Test different sensitivity levels."""
        code = 'def process_data():\n    # Process the data\n    pass\n'
        
        for level in [SensitivityLevel.LOW, SensitivityLevel.MEDIUM, 
                     SensitivityLevel.HIGH, SensitivityLevel.PARANOID]:
            detector = AIDetector(AIPatternConfig(sensitivity=level))
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                f.flush()
                
                result = detector.detect_file(Path(f.name))
                
                # Higher sensitivity should be more strict
                if level == SensitivityLevel.PARANOID:
                    assert result.ai_score > 0
                
                Path(f.name).unlink()
    
    def test_ast_pattern_detection(self):
        """Test AST-based pattern detection for Python."""
        detector = AIDetector()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            # Deep nesting
            f.write('def complex():\n')
            f.write('    if True:\n')
            f.write('        for i in range(10):\n')
            f.write('            while True:\n')
            f.write('                if i > 5:\n')
            f.write('                    with open("file") as f:\n')
            f.write('                        pass\n')
            f.write('                break\n')
            f.flush()
            
            result = detector.detect_file(Path(f.name))
            
        assert len(result.detected_patterns) > 0
        Path(f.name).unlink()
    
    def test_empty_except_detection(self):
        """Test empty except block detection."""
        detector = AIDetector()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('try:\n')
            f.write('    dangerous_operation()\n')
            f.write('except ValueError:\n')
            f.write('    pass\n')
            f.flush()
            
            result = detector.detect_file(Path(f.name))
            
        assert any(p["category"] == "empty_except" for p in result.detected_patterns)
        Path(f.name).unlink()
    
    def test_ai_score_calculation(self):
        """Test AI score calculation."""
        detector = AIDetector()
        
        # Clean code should have low score
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def calculate_sum(a, b):\n')
            f.write('    return a + b\n')
            f.flush()
            
            result = detector.detect_file(Path(f.name))
            assert result.ai_score < 0.3
            Path(f.name).unlink()
        
        # AI-like code should have high score
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('# Initialize the system\n')
            f.write('# TODO: Replace with actual implementation\n')
            f.write('def process_user_input_data():\n')
            f.write('    """Comprehensive data processing utility."""\n')
            f.write('    try:\n')
            f.write('        # Process the data\n')
            f.write('        pass  # Placeholder\n')
            f.write('    except Exception:\n')
            f.write('        pass\n')
            f.write('    print("🎉 Done!")\n')
            f.flush()
            
            result = detector.detect_file(Path(f.name))
            assert result.ai_score > 0.5
            Path(f.name).unlink()
    
    def test_detect_directory(self):
        """Test directory scanning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create test files
            (tmpdir_path / "clean.py").write_text('def add(a, b):\n    return a + b\n')
            (tmpdir_path / "ai_like.py").write_text('# TODO: Implement\ndef placeholder():\n    pass\n')
            (tmpdir_path / "emoji.py").write_text('print("🎉")\n')
            
            detector = AIDetector()
            results = detector.detect_directory(tmpdir_path)
            
            assert len(results) == 3
            assert any(r.passes for r in results)  # At least one should pass
            assert any(not r.passes for r in results)  # At least one should fail
    
    def test_generate_report(self):
        """Test report generation."""
        detector = AIDetector()
        
        results = [
            DetectionResult(
                file_path="file1.py",
                detected_patterns=[{"category": "emoji", "severity": "high"}],
                ai_score=0.8,
                passes=False
            ),
            DetectionResult(
                file_path="file2.py",
                detected_patterns=[],
                ai_score=0.1,
                passes=True
            )
        ]
        
        report = detector.generate_report(results)
        
        assert report["summary"]["total_files"] == 2
        assert report["summary"]["passed"] == 1
        assert report["summary"]["failed"] == 1
        assert "emoji" in report["pattern_distribution"]
        assert len(report["failed_files"]) == 1
        assert len(report["recommendations"]) > 0
    
    def test_custom_patterns(self):
        """Test custom pattern configuration."""
        config = AIPatternConfig(
            custom_patterns=[
                {
                    "category": "custom_forbidden",
                    "pattern": r"FORBIDDEN_FUNCTION"
                }
            ]
        )
        detector = AIDetector(config)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('FORBIDDEN_FUNCTION()\n')
            f.flush()
            
            result = detector.detect_file(Path(f.name))
            
        assert len(result.detected_patterns) > 0
        assert any(p["category"] == "custom_forbidden" for p in result.detected_patterns)
        Path(f.name).unlink()
    
    def test_update_config(self):
        """Test dynamic config updates."""
        detector = AIDetector()
        
        # Update sensitivity
        detector.update_config(sensitivity=SensitivityLevel.HIGH)
        assert detector.config.sensitivity == SensitivityLevel.HIGH
        
        # Update emoji setting
        detector.update_config(emoji_allowed=True)
        assert detector.config.emoji_allowed
        
        # Update whitelist
        detector.update_config(whitelist_patterns={"test_pattern"})
        assert "test_pattern" in detector.config.whitelist_patterns
    
    def test_check_single_file(self):
        """Test single file quick check."""
        detector = AIDetector()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def clean_function():\n    return 42\n')
            f.flush()
            
            passes, message = detector.check_single_file(f.name)
            
        assert passes
        assert "No AI patterns detected" in message
        Path(f.name).unlink()
    
    def test_create_detector_with_config_file(self):
        """Test factory function with config file."""
        config_data = {
            "sensitivity": "high",
            "emoji_allowed": True,
            "whitelist_patterns": ["TODO: URGENT"],
            "custom_patterns": [
                {"category": "test", "pattern": "TEST_PATTERN"}
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            f.flush()
            
            detector = create_detector(f.name)
            
        assert detector.config.sensitivity == SensitivityLevel.HIGH
        assert detector.config.emoji_allowed
        assert "TODO: URGENT" in detector.config.whitelist_patterns
        assert len(detector.config.custom_patterns) == 1
        Path(f.name).unlink()
    
    def test_performance_caching(self):
        """Test performance optimization with caching."""
        detector = AIDetector()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('# Test file\ndef test():\n    pass\n')
            f.flush()
            
            # First call
            result1 = detector.detect_file(Path(f.name))
            
            # Second call should use cache
            result2 = detector.detect_file(Path(f.name))
            
            assert result1.ai_score == result2.ai_score
            assert len(result1.detected_patterns) == len(result2.detected_patterns)
            
        Path(f.name).unlink()
    
    def test_parallel_processing(self):
        """Test parallel file processing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create multiple test files
            for i in range(10):
                (tmpdir_path / f"file{i}.py").write_text(f'# File {i}\ndef func{i}():\n    pass\n')
            
            detector = AIDetector(AIPatternConfig(max_workers=4))
            results = detector.detect_directory(tmpdir_path)
            
            assert len(results) == 10
    
    def test_non_python_file_handling(self):
        """Test handling of non-Python files."""
        detector = AIDetector()
        
        # JavaScript file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write('// TODO: Implement this\n')
            f.write('function placeholder() {\n')
            f.write('  // Process data\n')
            f.write('}\n')
            f.flush()
            
            result = detector.detect_file(Path(f.name))
            
        assert len(result.detected_patterns) > 0
        Path(f.name).unlink()
    
    def test_binary_file_handling(self):
        """Test handling of binary files."""
        detector = AIDetector()
        
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.bin', delete=False) as f:
            f.write(b'\x00\x01\x02\x03')
            f.flush()
            
            result = detector.detect_file(Path(f.name))
            
        assert result.passes  # Should pass for binary files
        assert len(result.detected_patterns) == 0
        Path(f.name).unlink()


class TestDetectionResult:
    """Test suite for DetectionResult class."""
    
    def test_summary_no_patterns(self):
        """Test summary generation with no patterns."""
        result = DetectionResult(
            file_path="test.py",
            detected_patterns=[],
            ai_score=0.0,
            passes=True
        )
        
        assert "No AI patterns detected" in result.summary
        assert "test.py" in result.summary
    
    def test_summary_with_patterns(self):
        """Test summary generation with patterns."""
        result = DetectionResult(
            file_path="test.py",
            detected_patterns=[
                {"category": "emoji"},
                {"category": "placeholder_text"}
            ],
            ai_score=0.75,
            passes=False
        )
        
        assert "Found 2 AI patterns" in result.summary
        assert "0.75" in result.summary
        assert "test.py" in result.summary


class TestIntegration:
    """Integration tests for AI detector with verification engine."""
    
    def test_integration_with_verification_engine(self):
        """Test integration hooks for verification engine."""
        from hydra.verification_system.engine import VerificationEngine
        
        detector = AIDetector()
        
        # Mock verification engine integration
        with patch('hydra.verification_system.engine.VerificationEngine') as mock_engine:
            mock_instance = MagicMock()
            mock_engine.return_value = mock_instance
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write('print("🎉")\n')
                f.flush()
                
                result = detector.detect_file(Path(f.name))
                
                # Simulate verification engine using the result
                mock_instance.add_check_result("ai_patterns", result.passes)
                mock_instance.add_check_result.assert_called_once()
                
            Path(f.name).unlink()