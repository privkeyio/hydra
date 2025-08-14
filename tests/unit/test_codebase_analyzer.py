"""Unit tests for codebase analyzer."""

import tempfile
import unittest
from pathlib import Path

from hydra.analysis.codebase_analyzer import CodebaseAnalyzer


class TestCodebaseAnalyzer(unittest.TestCase):
    """Test codebase analysis functionality."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.analyzer = CodebaseAnalyzer(self.temp_dir)

    def test_detect_project_type(self):
        """Test project type detection."""
        # Create test files
        test_file = Path(self.temp_dir) / "app.py"
        test_file.write_text("from flask import Flask\napp = Flask(__name__)")
        
        project_type = self.analyzer._detect_project_type()
        self.assertIn(project_type, ["web", "api"])

    def test_detect_framework(self):
        """Test framework detection."""
        # Create package.json
        pkg_file = Path(self.temp_dir) / "package.json"
        pkg_file.write_text('{"dependencies": {"react": "^18.0.0"}}')
        
        framework = self.analyzer._detect_framework()
        self.assertEqual(framework, "react")

    def test_analyze_complexity(self):
        """Test complexity analysis."""
        # Create a Python file with known complexity
        test_file = Path(self.temp_dir) / "test.py"
        test_file.write_text("""
def simple_function():
    if True:
        return 1
    else:
        return 2
        
def complex_function(x):
    if x > 0:
        if x > 10:
            return "large"
        else:
            return "small"
    elif x < 0:
        return "negative"
    else:
        return "zero"
""")
        
        complexity = self.analyzer._analyze_complexity()
        self.assertIn("test.py", complexity)
        self.assertGreater(complexity["test.py"], 1)

    def test_calculate_size_metrics(self):
        """Test size metrics calculation."""
        # Create test files
        py_file = Path(self.temp_dir) / "test.py"
        py_file.write_text("# Line 1\n# Line 2\n# Line 3")
        
        js_file = Path(self.temp_dir) / "test.js"
        js_file.write_text("// Line 1\n// Line 2")
        
        metrics = self.analyzer._calculate_size_metrics()
        self.assertEqual(metrics["python_files"], 1)
        self.assertEqual(metrics["javascript_files"], 1)
        self.assertEqual(metrics["python_loc"], 3)
        self.assertEqual(metrics["javascript_loc"], 2)
        self.assertEqual(metrics["total_loc"], 5)

    def test_analyze_structure(self):
        """Test project structure analysis."""
        # Create directory structure
        (Path(self.temp_dir) / "src").mkdir()
        (Path(self.temp_dir) / "tests").mkdir()
        (Path(self.temp_dir) / "docs").mkdir()
        
        structure = self.analyzer._analyze_structure()
        self.assertIn("src", str(structure["directories"]))
        self.assertIn("tests", str(structure["directories"]))
        self.assertIn("separate-tests", structure["patterns"])

    def test_detect_tech_stack(self):
        """Test technology stack detection."""
        # Create Dockerfile
        docker_file = Path(self.temp_dir) / "Dockerfile"
        docker_file.write_text("FROM python:3.9")
        
        # Create Python file
        py_file = Path(self.temp_dir) / "app.py"
        py_file.write_text("import fastapi")
        
        tech_stack = self.analyzer._detect_tech_stack()
        self.assertIn("Python", tech_stack)
        self.assertIn("Docker", tech_stack)

    def test_find_existing_tests(self):
        """Test finding existing test files."""
        # Create test files
        test_file1 = Path(self.temp_dir) / "test_main.py"
        test_file1.write_text("def test_something(): pass")
        
        test_file2 = Path(self.temp_dir) / "tests" 
        test_file2.mkdir(exist_ok=True)
        (test_file2 / "test_utils.py").write_text("def test_util(): pass")
        
        test_info = self.analyzer._find_existing_tests()
        self.assertEqual(test_info["test_count"], 2)
        self.assertIn("test_main.py", str(test_info["test_files"]))
        self.assertIn("tests", str(test_info["test_directories"]))

    def test_full_analysis(self):
        """Test full codebase analysis."""
        # Create a mini project
        (Path(self.temp_dir) / "src").mkdir()
        (Path(self.temp_dir) / "tests").mkdir()
        
        main_file = Path(self.temp_dir) / "src" / "main.py"
        main_file.write_text("""
def main():
    '''Main function.'''
    print("Hello World")
    
if __name__ == "__main__":
    main()
""")
        
        test_file = Path(self.temp_dir) / "tests" / "test_main.py"
        test_file.write_text("""
import pytest

def test_main():
    assert True
""")
        
        readme = Path(self.temp_dir) / "README.md"
        readme.write_text("# Test Project")
        
        analysis = self.analyzer.analyze()
        
        # Check all major sections are present
        self.assertIn("project_type", analysis)
        self.assertIn("structure", analysis)
        self.assertIn("dependencies", analysis)
        self.assertIn("complexity", analysis)
        self.assertIn("size_metrics", analysis)
        self.assertIn("tech_stack", analysis)
        self.assertIn("existing_tests", analysis)
        self.assertIn("documentation", analysis)
        
        # Check specific values
        self.assertTrue(analysis["documentation"]["has_readme"])
        self.assertGreater(analysis["size_metrics"]["python_loc"], 0)
        self.assertEqual(analysis["existing_tests"]["test_count"], 1)


if __name__ == "__main__":
    unittest.main()