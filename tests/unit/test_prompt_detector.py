"""Unit tests for the prompt detection system."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

from hydra.providers.prompt_detector import (
    DetectionResult,
    MatchType,
    PromptDetector,
    PromptHandler,
    PromptPattern,
    ResponseStrategy
)


class TestPromptPattern(unittest.TestCase):
    """Test PromptPattern data class."""
    
    def test_pattern_creation(self):
        """Test creating a PromptPattern with all fields."""
        pattern = PromptPattern(
            name="test_pattern",
            pattern="test.*pattern",
            match_type=MatchType.REGEX,
            response_strategy=ResponseStrategy.AUTO_APPROVE,
            response_text="yes",
            confidence_threshold=0.8,
            tags={"test", "regex"},
            metadata={"tool": "test"},
            safety_override=True
        )
        
        self.assertEqual(pattern.name, "test_pattern")
        self.assertEqual(pattern.pattern, "test.*pattern")
        self.assertEqual(pattern.match_type, MatchType.REGEX)
        self.assertEqual(pattern.response_strategy, ResponseStrategy.AUTO_APPROVE)
        self.assertEqual(pattern.response_text, "yes")
        self.assertEqual(pattern.confidence_threshold, 0.8)
        self.assertEqual(pattern.tags, {"test", "regex"})
        self.assertEqual(pattern.metadata, {"tool": "test"})
        self.assertTrue(pattern.safety_override)
    
    def test_pattern_post_init_conversion(self):
        """Test automatic conversion of string enums."""
        pattern = PromptPattern(
            name="test",
            pattern="test",
            match_type="regex",
            response_strategy="auto_approve",
            tags=["test", "conversion"]
        )
        
        self.assertEqual(pattern.match_type, MatchType.REGEX)
        self.assertEqual(pattern.response_strategy, ResponseStrategy.AUTO_APPROVE)
        self.assertEqual(pattern.tags, {"test", "conversion"})


class TestDetectionResult(unittest.TestCase):
    """Test DetectionResult data class."""
    
    def test_detection_result_creation(self):
        """Test creating a DetectionResult."""
        pattern = PromptPattern(
            name="test",
            pattern="test",
            match_type=MatchType.LITERAL,
            response_strategy=ResponseStrategy.PROMPT_USER
        )
        
        result = DetectionResult(
            matched=True,
            pattern=pattern,
            confidence=0.9,
            match_groups=["group1", "group2"],
            suggested_response="test response",
            requires_user_input=True,
            safety_blocked=False
        )
        
        self.assertTrue(result.matched)
        self.assertEqual(result.pattern, pattern)
        self.assertEqual(result.confidence, 0.9)
        self.assertEqual(result.match_groups, ["group1", "group2"])
        self.assertEqual(result.suggested_response, "test response")
        self.assertTrue(result.requires_user_input)
        self.assertFalse(result.safety_blocked)


class TestPromptDetector(unittest.TestCase):
    """Test PromptDetector class."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create temporary directory for patterns
        self.temp_dir = tempfile.TemporaryDirectory()
        self.patterns_dir = Path(self.temp_dir.name)
        
        # Create mock config manager
        self.mock_config = Mock()
        self.mock_config.get.return_value = []
        
        # Create detector with temporary directory
        self.detector = PromptDetector(
            config_manager=self.mock_config,
            patterns_dir=self.patterns_dir,
            enable_learning=True
        )
    
    def tearDown(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()
    
    def test_detector_initialization(self):
        """Test PromptDetector initialization."""
        self.assertEqual(self.detector.patterns_dir, self.patterns_dir)
        self.assertTrue(self.detector.enable_learning)
        self.assertEqual(self.detector.config_manager, self.mock_config)
        
        # Check that built-in patterns are loaded
        self.assertGreater(len(self.detector._patterns), 0)
        self.assertIn('claude_permission_request', self.detector._patterns)
    
    def test_regex_pattern_matching(self):
        """Test regex pattern matching."""
        result = self.detector.detect_prompt("Do you want me to proceed?")
        
        self.assertTrue(result.matched)
        self.assertEqual(result.pattern.name, 'claude_permission_request')
        self.assertEqual(result.confidence, 1.0)
        self.assertTrue(result.requires_user_input)
    
    def test_literal_pattern_matching(self):
        """Test literal string pattern matching."""
        # Add a test pattern
        pattern = PromptPattern(
            name="test_literal",
            pattern="exact match",
            match_type=MatchType.LITERAL,
            response_strategy=ResponseStrategy.AUTO_APPROVE,
            response_text="yes"
        )
        self.detector.add_pattern(pattern)
        
        result = self.detector.detect_prompt("This is an exact match test")
        
        self.assertTrue(result.matched)
        self.assertEqual(result.pattern.name, 'test_literal')
        self.assertEqual(result.suggested_response, "yes")
        self.assertFalse(result.requires_user_input)
    
    def test_substring_pattern_matching(self):
        """Test substring pattern matching."""
        pattern = PromptPattern(
            name="test_substring",
            pattern="substring",
            match_type=MatchType.SUBSTRING,
            response_strategy=ResponseStrategy.DENY,
            response_text="no"
        )
        self.detector.add_pattern(pattern)
        
        result = self.detector.detect_prompt("This contains a substring test")
        
        self.assertTrue(result.matched)
        self.assertEqual(result.pattern.name, 'test_substring')
        self.assertEqual(result.suggested_response, "no")
    
    def test_startswith_pattern_matching(self):
        """Test startswith pattern matching."""
        pattern = PromptPattern(
            name="test_startswith",
            pattern="start",
            match_type=MatchType.STARTSWITH,
            response_strategy=ResponseStrategy.AUTO_APPROVE
        )
        self.detector.add_pattern(pattern)
        
        result = self.detector.detect_prompt("Start with this text")
        
        self.assertTrue(result.matched)
        self.assertEqual(result.pattern.name, 'test_startswith')
    
    def test_endswith_pattern_matching(self):
        """Test endswith pattern matching."""
        pattern = PromptPattern(
            name="test_endswith",
            pattern="end",
            match_type=MatchType.ENDSWITH,
            response_strategy=ResponseStrategy.AUTO_APPROVE
        )
        self.detector.add_pattern(pattern)
        
        result = self.detector.detect_prompt("This text should end")
        
        self.assertTrue(result.matched)
        self.assertEqual(result.pattern.name, 'test_endswith')
    
    def test_safety_blocking(self):
        """Test safety blocking functionality."""
        # Add a dangerous pattern
        pattern = PromptPattern(
            name="dangerous_test",
            pattern="dangerous operation",
            match_type=MatchType.LITERAL,
            response_strategy=ResponseStrategy.AUTO_APPROVE,
            tags={"dangerous"},
            safety_override=False
        )
        self.detector.add_pattern(pattern)
        
        result = self.detector.detect_prompt("Execute dangerous operation")
        
        self.assertTrue(result.matched)
        self.assertTrue(result.safety_blocked)
        self.assertIsNone(result.suggested_response)
    
    def test_safety_override(self):
        """Test safety override functionality."""
        pattern = PromptPattern(
            name="safe_dangerous",
            pattern="override test",
            match_type=MatchType.LITERAL,
            response_strategy=ResponseStrategy.AUTO_APPROVE,
            response_text="approved",
            tags={"dangerous"},
            safety_override=True
        )
        self.detector.add_pattern(pattern)
        
        result = self.detector.detect_prompt("Execute override test")
        
        self.assertTrue(result.matched)
        self.assertFalse(result.safety_blocked)
        self.assertEqual(result.suggested_response, "approved")
    
    def test_learning_mode(self):
        """Test learning mode functionality."""
        # Clear existing learning data
        self.detector.clear_learning_data()
        
        # Detect unknown prompt
        result = self.detector.detect_prompt("This is an unknown prompt")
        
        self.assertFalse(result.matched)
        
        # Check learning data
        learning_data = self.detector.get_learning_data()
        self.assertEqual(len(learning_data['unknown_prompts']), 1)
        self.assertIn("This is an unknown prompt", learning_data['unknown_prompts'])
        self.assertEqual(learning_data['statistics']['learning_captures'], 1)
    
    def test_pattern_suggestions(self):
        """Test pattern suggestion generation."""
        # Clear learning data first
        self.detector.clear_learning_data()
        
        # Add multiple instances of the same unknown prompt
        unknown_prompt = "Repeat this unknown pattern"
        for _ in range(5):
            self.detector.detect_prompt(unknown_prompt)
        
        suggestions = self.detector.generate_pattern_suggestions(min_frequency=3)
        
        self.assertGreater(len(suggestions), 0)
        suggestion = suggestions[0]
        self.assertEqual(suggestion['frequency'], 5)
        self.assertIn('suggested_name', suggestion)
        self.assertIn('pattern', suggestion)
    
    def test_load_pattern_from_yaml_file(self):
        """Test loading patterns from YAML file."""
        # Create test YAML file
        yaml_file = self.patterns_dir / "test_patterns.yaml"
        test_patterns = {
            'patterns': [
                {
                    'name': 'yaml_test_pattern',
                    'pattern': 'yaml test',
                    'match_type': 'literal',
                    'response_strategy': 'auto_approve',
                    'response_text': 'yaml response',
                    'tags': ['yaml', 'test']
                }
            ]
        }
        
        with open(yaml_file, 'w') as f:
            yaml.dump(test_patterns, f)
        
        # Reload patterns
        self.detector._load_pattern_file(yaml_file)
        
        # Test the loaded pattern
        result = self.detector.detect_prompt("This is a yaml test")
        
        self.assertTrue(result.matched)
        self.assertEqual(result.pattern.name, 'yaml_test_pattern')
        self.assertEqual(result.suggested_response, 'yaml response')
    
    def test_load_pattern_from_json_file(self):
        """Test loading patterns from JSON file."""
        # Create test JSON file
        json_file = self.patterns_dir / "test_patterns.json"
        test_patterns = {
            'patterns': [
                {
                    'name': 'json_test_pattern',
                    'pattern': 'json test',
                    'match_type': 'literal',
                    'response_strategy': 'custom_response',
                    'response_text': 'json response',
                    'tags': ['json', 'test']
                }
            ]
        }
        
        with open(json_file, 'w') as f:
            json.dump(test_patterns, f)
        
        # Reload patterns
        self.detector._load_pattern_file(json_file)
        
        # Test the loaded pattern
        result = self.detector.detect_prompt("This is a json test")
        
        self.assertTrue(result.matched)
        self.assertEqual(result.pattern.name, 'json_test_pattern')
        self.assertEqual(result.suggested_response, 'json response')
    
    def test_save_patterns(self):
        """Test saving patterns to file."""
        # Add a custom pattern
        pattern = PromptPattern(
            name="save_test",
            pattern="save pattern test",
            match_type=MatchType.LITERAL,
            response_strategy=ResponseStrategy.AUTO_APPROVE,
            tags={"save", "test"}
        )
        self.detector.add_pattern(pattern)
        
        # Save patterns
        self.detector.save_patterns("saved_patterns.yaml")
        
        # Check if file was created
        saved_file = self.patterns_dir / "saved_patterns.yaml"
        self.assertTrue(saved_file.exists())
        
        # Load and verify content
        with open(saved_file, 'r') as f:
            saved_data = yaml.safe_load(f)
        
        self.assertIn('patterns', saved_data)
        pattern_names = [p['name'] for p in saved_data['patterns']]
        self.assertIn('save_test', pattern_names)
    
    def test_add_remove_pattern(self):
        """Test adding and removing patterns."""
        pattern = PromptPattern(
            name="add_remove_test",
            pattern="test pattern",
            match_type=MatchType.LITERAL,
            response_strategy=ResponseStrategy.AUTO_APPROVE
        )
        
        # Add pattern
        success = self.detector.add_pattern(pattern)
        self.assertTrue(success)
        self.assertIn('add_remove_test', self.detector._patterns)
        
        # Remove pattern
        success = self.detector.remove_pattern('add_remove_test')
        self.assertTrue(success)
        self.assertNotIn('add_remove_test', self.detector._patterns)
        
        # Try to remove non-existent pattern
        success = self.detector.remove_pattern('non_existent')
        self.assertFalse(success)
    
    def test_list_patterns(self):
        """Test listing patterns with optional tag filter."""
        # Add test patterns with different tags
        pattern1 = PromptPattern(
            name="pattern1",
            pattern="test1",
            match_type=MatchType.LITERAL,
            response_strategy=ResponseStrategy.AUTO_APPROVE,
            tags={"tag1", "common"}
        )
        pattern2 = PromptPattern(
            name="pattern2", 
            pattern="test2",
            match_type=MatchType.LITERAL,
            response_strategy=ResponseStrategy.AUTO_APPROVE,
            tags={"tag2", "common"}
        )
        
        self.detector.add_pattern(pattern1)
        self.detector.add_pattern(pattern2)
        
        # List all patterns
        all_patterns = self.detector.list_patterns()
        pattern_names = [p.name for p in all_patterns]
        self.assertIn('pattern1', pattern_names)
        self.assertIn('pattern2', pattern_names)
        
        # List patterns with tag filter
        filtered_patterns = self.detector.list_patterns(tag_filter='tag1')
        filtered_names = [p.name for p in filtered_patterns]
        self.assertIn('pattern1', filtered_names)
        self.assertNotIn('pattern2', filtered_names)
        
        # List patterns with common tag
        common_patterns = self.detector.list_patterns(tag_filter='common')
        common_names = [p.name for p in common_patterns]
        self.assertIn('pattern1', common_names)
        self.assertIn('pattern2', common_names)
    
    def test_statistics(self):
        """Test statistics tracking."""
        # Reset stats
        self.detector._stats = {
            'total_detections': 0,
            'successful_matches': 0,
            'learning_captures': 0,
            'safety_blocks': 0
        }
        
        # Perform some detections
        self.detector.detect_prompt("Do you want me to proceed?")  # Should match
        self.detector.detect_prompt("Unknown prompt")  # Should not match
        
        stats = self.detector.get_statistics()
        
        self.assertEqual(stats['total_detections'], 2)
        self.assertEqual(stats['successful_matches'], 1)
        self.assertEqual(stats['success_rate'], 0.5)
        self.assertGreater(stats['pattern_count'], 0)


class TestPromptHandler(unittest.TestCase):
    """Test PromptHandler class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.patterns_dir = Path(self.temp_dir.name)
        
        self.mock_config = Mock()
        self.mock_config.get.return_value = []
        
        self.detector = PromptDetector(
            config_manager=self.mock_config,
            patterns_dir=self.patterns_dir,
            enable_learning=True
        )
        self.handler = PromptHandler(self.detector)
    
    def tearDown(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()
    
    @patch('builtins.input', return_value='user response')
    @patch('builtins.print')
    def test_handle_unknown_prompt(self, mock_print, mock_input):
        """Test handling unknown prompts."""
        response = self.handler.handle_prompt("Unknown test prompt")
        
        self.assertEqual(response, 'user response')
        mock_print.assert_called()
        mock_input.assert_called_once()
    
    def test_handle_auto_approve_prompt(self):
        """Test handling auto-approve prompts."""
        # Add auto-approve pattern
        pattern = PromptPattern(
            name="auto_test",
            pattern="auto approve this",
            match_type=MatchType.LITERAL,
            response_strategy=ResponseStrategy.AUTO_APPROVE,
            response_text="approved"
        )
        self.detector.add_pattern(pattern)
        
        response = self.handler.handle_prompt("Please auto approve this request")
        
        self.assertEqual(response, 'approved')
    
    def test_handle_safety_blocked_prompt(self):
        """Test handling safety-blocked prompts."""
        # Add dangerous pattern without safety override
        pattern = PromptPattern(
            name="dangerous_test",
            pattern="dangerous operation",
            match_type=MatchType.LITERAL,
            response_strategy=ResponseStrategy.AUTO_APPROVE,
            tags={"dangerous"},
            safety_override=False
        )
        self.detector.add_pattern(pattern)
        
        response = self.handler.handle_prompt("Execute dangerous operation")
        
        self.assertEqual(response, "Operation blocked for safety reasons.")
    
    @patch('builtins.input', return_value='manual response')
    @patch('builtins.print')
    def test_handle_prompt_user_strategy(self, mock_print, mock_input):
        """Test handling prompts that require user input."""
        # Built-in claude_permission_request pattern uses PROMPT_USER strategy
        response = self.handler.handle_prompt("Do you want me to proceed?")
        
        self.assertEqual(response, 'manual response')
        mock_print.assert_called()
        mock_input.assert_called_once()
    
    def test_custom_response_callback(self):
        """Test custom response callback functionality."""
        # Add pattern
        pattern = PromptPattern(
            name="callback_test",
            pattern="callback test",
            match_type=MatchType.LITERAL,
            response_strategy=ResponseStrategy.CUSTOM_RESPONSE
        )
        self.detector.add_pattern(pattern)
        
        # Set custom callback
        def custom_callback(text, result):
            return f"Custom response for: {text[:10]}"
        
        self.handler.set_response_callback("callback_test", custom_callback)
        
        # The handler doesn't currently use callbacks in handle_prompt,
        # but we can test that the callback is set correctly
        self.assertIn("callback_test", self.handler._response_callbacks)
        self.assertEqual(
            self.handler._response_callbacks["callback_test"],
            custom_callback
        )


class TestBuiltinPatterns(unittest.TestCase):
    """Test built-in patterns work correctly."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.patterns_dir = Path(self.temp_dir.name)
        
        self.mock_config = Mock()
        self.mock_config.get.return_value = []
        
        self.detector = PromptDetector(
            config_manager=self.mock_config,
            patterns_dir=self.patterns_dir,
            enable_learning=True
        )
    
    def tearDown(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()
    
    def test_claude_permission_patterns(self):
        """Test Claude permission request patterns."""
        test_cases = [
            "Do you want me to proceed?",
            "Should I continue with this task?",
            "Would you like me to continue?",
            "May I proceed with the operation?"
        ]
        
        for test_case in test_cases:
            result = self.detector.detect_prompt(test_case)
            self.assertTrue(result.matched, f"Failed to match: {test_case}")
            self.assertEqual(result.pattern.name, 'claude_permission_request')
            self.assertTrue(result.requires_user_input)
    
    def test_git_safety_patterns(self):
        """Test git operation safety patterns."""
        dangerous_git_prompts = [
            "Commit changes?",
            "Push to remote repository?",
            "Merge feature branch?",
            "Reset changes permanently?"
        ]
        
        for prompt in dangerous_git_prompts:
            result = self.detector.detect_prompt(prompt)
            if result.matched:
                self.assertTrue(result.safety_blocked or result.pattern.safety_override)
    
    def test_generic_yes_no_patterns(self):
        """Test generic yes/no patterns."""
        test_cases = [
            "Continue? (y/n)",
            "Proceed [Y/n]?",
            "Are you sure [y/N]?"
        ]
        
        for test_case in test_cases:
            result = self.detector.detect_prompt(test_case)
            self.assertTrue(result.matched, f"Failed to match: {test_case}")
            self.assertTrue(result.requires_user_input)


if __name__ == '__main__':
    unittest.main()