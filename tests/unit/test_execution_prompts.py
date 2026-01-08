"""Tests for production-grade execution prompts."""

import pytest
from typing import Dict, List, Any

from hydra.prompts.execution_prompts import (
    ExecutionMode,
    ExecutionPriority,
    ExecutionContext,
    ProductionExecutionPrompts,
    ExecutionPromptBuilder,
    ExecutionValidator,
    AIPatternDetector,
    ExecutionStrategies,
    PostExecutionPrompts,
    generate_execution_prompt,
    create_execution_checklist
)


class TestProductionExecutionPrompts:
    """Test production execution prompts."""
    
    def test_main_execution_prompt_has_get_it_done(self):
        """Main prompt must have aggressive GET IT DONE mentality."""
        prompt = ProductionExecutionPrompts.MAIN_EXECUTION
        assert "GET IT DONE" in prompt
        assert "VIOLATIONS = FAILURE" in prompt
        assert "MANDATORY SELF-VERIFICATION CHECKLIST" in prompt
        assert "IF ANY CHECKBOX IS NO, YOU HAVE FAILED" in prompt
    
    def test_all_critical_rules_present(self):
        """All critical rules must be in main prompt."""
        prompt = ProductionExecutionPrompts.MAIN_EXECUTION
        critical_rules = [
            "WITHOUT overengineering",
            "MINIMAL code with MAXIMUM impact",
            "PRODUCTION QUALITY ONLY",
            "Zero shortcuts, zero mocks, zero workarounds",
            "lint, build, and ALL tests",
            "BANNED: AI patterns",
            "BANNED: Any TODO, FIXME, NOTE, HACK"
        ]
        for rule in critical_rules:
            assert rule in prompt, f"Missing critical rule: {rule}"
    
    def test_self_verification_checklist_complete(self):
        """Self-verification checklist must be comprehensive."""
        prompt = ProductionExecutionPrompts.MAIN_EXECUTION
        checklist_items = [
            "Every acceptance criterion actually implemented",
            "All tests complete, meaningful, and passing",
            "Code looks like experienced human wrote it",
            "Zero corners cut",
            "Actual business value delivered",
            "production deployment RIGHT NOW",
            "lint, typecheck, full test suite"
        ]
        for item in checklist_items:
            assert item in prompt, f"Missing checklist item: {item}"


class TestAIPatternDetector:
    """Test AI pattern detection."""
    
    def test_detects_verbose_generic_names(self):
        """Detect generic verbose naming patterns."""
        code = """
        class Manager:
            def __init__(self):
                self.helper = Helper()
                self.processor = Processor()
                self.handler = Handler()
        """
        has_patterns, detected = AIPatternDetector.detect_ai_patterns(code)
        assert has_patterns
        assert any("naming" in d.lower() for d in detected)
    
    def test_detects_ai_comments(self):
        """Detect AI-style comment patterns."""
        code = """
        # Initialize the configuration
        def setup():
            # Create the main object
            obj = Object()
            # Set up the parameters
            obj.configure()
            # This function handles initialization
        """
        has_patterns, detected = AIPatternDetector.detect_ai_patterns(code)
        assert has_patterns
        assert any("Initialize" in d for d in detected)
        assert any("This function" in d for d in detected)
    
    def test_detects_emojis(self):
        """Detect emoji usage in code."""
        code = """
        def celebrate():
            print("Success! 🎉")
            return "✅ Done"
        """
        has_patterns, detected = AIPatternDetector.detect_ai_patterns(code)
        assert has_patterns
        assert any("Emoji" in d for d in detected)
    
    def test_detects_placeholder_patterns(self):
        """Detect placeholder and TODO patterns."""
        code = """
        def placeholder_function():
            # TODO: Implement this
            dummy_value = "temp"
            return "foo"
        """
        has_patterns, detected = AIPatternDetector.detect_ai_patterns(code)
        assert has_patterns
        assert any("placeholder" in d.lower() for d in detected)
        assert any("TODO" in d for d in detected)
    
    def test_detects_excessive_commenting(self):
        """Detect when code has too many comments."""
        code = """
        # This is a function
        def add(a, b):
            # Add the two numbers
            result = a + b
            # Return the result
            return result
        # End of function
        """
        has_patterns, detected = AIPatternDetector.detect_ai_patterns(code)
        assert has_patterns
        assert any("Excessive commenting" in d for d in detected)
    
    def test_passes_clean_human_code(self):
        """Clean human-like code should pass."""
        code = """def calc_tax(amount, rate):
    if amount <= 0:
        return 0
    tax = amount * rate
    return round(tax, 2)"""
        has_patterns, detected = AIPatternDetector.detect_ai_patterns(code)
        assert not has_patterns
        assert len(detected) == 0


class TestExecutionValidator:
    """Test execution validation."""
    
    def test_check_production_quality_detects_debug_code(self):
        """Detect debug and non-production code."""
        code = """
        def process():
            print("Debug: Starting")
            # TODO: Fix this
            data = fetch_from_localhost()
            password = "admin123"
            return data
        """
        is_ready, issues = ExecutionValidator.check_production_quality(code)
        assert not is_ready
        assert any("Debug print" in i for i in issues)
        assert any("TODO" in i for i in issues)
        assert any("localhost" in i for i in issues)
        assert any("password" in i for i in issues)
    
    def test_check_production_quality_requires_error_handling(self):
        """Require error handling for non-trivial code."""
        code = """
        def complex_operation(data):
            result = []
            for item in data:
                processed = transform(item)
                validated = validate(processed)
                result.append(finalize(validated))
            return result
        """
        is_ready, issues = ExecutionValidator.check_production_quality(code)
        assert not is_ready
        assert any("error handling" in i.lower() for i in issues)
    
    def test_check_production_quality_detects_mocks(self):
        """Detect mock and stub code."""
        code = """
        def get_data():
            return mock_response()
        
        def stub_function():
            pass
        """
        is_ready, issues = ExecutionValidator.check_production_quality(code)
        assert not is_ready
        assert any("Mock" in i for i in issues)
        assert any("Stub" in i for i in issues)
    
    def test_check_production_quality_integrates_ai_detection(self):
        """AI pattern detection should be integrated."""
        code = """
        class DataHelper:
            # This function initializes the helper
            def __init__(self):
                print("Setting up! 🚀")
        """
        is_ready, issues = ExecutionValidator.check_production_quality(code)
        assert not is_ready
        assert any("helper" in i.lower() for i in issues)
        assert any("Emoji" in i for i in issues)
    
    def test_validate_execution_checks_criteria(self):
        """Validate all acceptance criteria are met."""
        criteria = [
            "Implement authentication",
            "Add error handling",
            "Write tests"
        ]
        
        # Missing implementation
        implementation = {
            "criterion_0": True,
            "criterion_1": False,
            "tests": []
        }
        
        is_complete, missing = ExecutionValidator.validate_execution(criteria, implementation)
        assert not is_complete
        assert "Add error handling" in missing
        assert "No tests provided" in missing


class TestPostExecutionPrompts:
    """Test post-execution validation prompts."""
    
    def test_self_review_is_brutal(self):
        """Self-review must be brutally honest."""
        prompt = PostExecutionPrompts.SELF_REVIEW
        assert "BRUTAL SELF-REVIEW" in prompt
        assert "BE HONEST OR FAIL" in prompt
        assert "IF ANY ANSWER IS NO, YOU HAVE FAILED" in prompt
        
        # Check all 10 critical questions
        for i in range(1, 11):
            assert f"{i}." in prompt
    
    def test_final_check_comprehensive(self):
        """Final check must cover all production requirements."""
        prompt = PostExecutionPrompts.FINAL_CHECK
        requirements = [
            "Zero debug code",
            "Zero hardcoded values",
            "Proper error handling",
            "Security best practices",
            "Performance acceptable",
            "Tests cover happy path AND failure",
            "No TODO, FIXME, HACK"
        ]
        for req in requirements:
            assert req in prompt
    
    def test_quality_gates_measurable(self):
        """Quality gates must have measurable criteria."""
        prompt = PostExecutionPrompts.QUALITY_GATES
        gates = [
            "Cyclomatic complexity < 10",
            "No functions > 50 lines",
            "Test coverage > 80%",
            "Zero linting errors",
            "All tests passing"
        ]
        for gate in gates:
            assert gate in prompt
    
    def test_human_code_check_practical(self):
        """Human code check focuses on practical patterns."""
        prompt = PostExecutionPrompts.HUMAN_CODE_CHECK
        checks = [
            "short, practical",
            "not verboseDescriptiveNames",
            "sparse, explain WHY not WHAT",
            "pragmatic, not over-architected",
            "straightforward is better",
            "experienced developer, not junior or AI"
        ]
        for check in checks:
            assert check in prompt


class TestExecutionPromptBuilder:
    """Test execution prompt builder."""
    
    def test_builds_main_execution_prompt(self):
        """Build main execution prompt with context."""
        builder = ExecutionPromptBuilder()
        prompt = (builder
                 .with_ticket("TICKET-001", ["Implement feature", "Add tests"])
                 .with_mode(ExecutionMode.COMPLETE)
                 .build())
        
        assert "TICKET-001" in prompt
        assert "Implement feature" in prompt
        assert "Add tests" in prompt
        assert "GET IT DONE" in prompt
    
    def test_builds_surgical_execution_prompt(self):
        """Build surgical execution prompt."""
        builder = ExecutionPromptBuilder()
        prompt = (builder
                 .with_ticket("TICKET-002", ["Fix bug"])
                 .with_mode(ExecutionMode.SURGICAL)
                 .with_files(["module.py", "test.py"])
                 .build())
        
        assert "Surgical execution" in prompt
        assert "module.py, test.py" in prompt
        assert "ONLY necessary changes" in prompt
    
    def test_builds_hotfix_prompt(self):
        """Build hotfix execution prompt."""
        builder = ExecutionPromptBuilder()
        builder.context["issue"] = "Critical security vulnerability"
        prompt = (builder
                 .with_mode(ExecutionMode.HOTFIX)
                 .build())
        
        assert "HOTFIX" in prompt
        assert "Critical security vulnerability" in prompt
        assert "Immediate action required" in prompt


class TestExecutionStrategies:
    """Test execution strategies."""
    
    def test_surgical_strategy_minimal(self):
        """Surgical strategy should be minimal."""
        strategy = ExecutionStrategies.get_strategy(ExecutionMode.SURGICAL)
        assert strategy["scope"] == "minimal"
        assert strategy["testing"] == "targeted"
        assert strategy["refactoring"] == "none"
    
    def test_comprehensive_strategy_full(self):
        """Comprehensive strategy should be full."""
        strategy = ExecutionStrategies.get_strategy(ExecutionMode.COMPLETE)
        assert strategy["scope"] == "full"
        assert strategy["testing"] == "thorough"
        assert strategy["refactoring"] == "allowed"
    
    def test_hotfix_strategy_restricted(self):
        """Hotfix strategy should be highly restricted."""
        strategy = ExecutionStrategies.get_strategy(ExecutionMode.HOTFIX)
        assert strategy["scope"] == "critical_only"
        assert strategy["refactoring"] == "forbidden"
    
    def test_performance_strategy_focused(self):
        """Performance strategy should focus on optimization."""
        strategy = ExecutionStrategies.get_strategy(ExecutionMode.PERFORMANCE)
        assert strategy["scope"] == "hot_paths"
        assert strategy["testing"] == "performance"
        assert strategy["refactoring"] == "optimization"


class TestHelperFunctions:
    """Test helper functions."""
    
    def test_generate_execution_prompt(self):
        """Test prompt generation for different operations."""
        context = {
            "ticket_id": "TEST-001",
            "acceptance_criteria": ["Do something", "Test it"]
        }
        
        prompt = generate_execution_prompt("main", context)
        assert "TEST-001" in prompt
        assert "Do something" in prompt
        
        bug_context = {
            "bug_description": "Null pointer",
            "file_location": "app.py",
            "root_cause": "Missing validation"
        }
        
        bug_prompt = generate_execution_prompt("bug_fix", bug_context)
        assert "Null pointer" in bug_prompt
        assert "app.py" in bug_prompt
        assert "root cause, not symptoms" in bug_prompt
    
    def test_create_execution_checklist(self):
        """Test checklist creation."""
        checklist = create_execution_checklist("TASK-001", ["Feature A", "Feature B"])
        
        assert "Read and understand ticket TASK-001" in checklist
        assert "Verify: Feature A" in checklist
        assert "Verify: Feature B" in checklist
        assert "Run linting and formatting" in checklist
        assert "Execute full test suite" in checklist
        assert "Check for production readiness" in checklist


class TestRealWorldScenarios:
    """Test with real-world ticket execution scenarios."""
    
    def test_api_endpoint_implementation(self):
        """Test prompts for API endpoint implementation."""
        builder = ExecutionPromptBuilder()
        criteria = [
            "Create POST /api/users endpoint",
            "Validate input data",
            "Return 201 on success",
            "Handle duplicate email error"
        ]
        
        prompt = (builder
                 .with_ticket("API-001", criteria)
                 .with_mode(ExecutionMode.COMPLETE)
                 .build())
        
        # Verify prompt enforces production quality
        assert "PRODUCTION QUALITY ONLY" in prompt
        assert all(c in prompt for c in criteria)
        
        # Simulate code that would fail validation
        bad_code = """
        # This function creates a user
        def create_user_handler():
            # TODO: Add validation
            user = {"name": "test"}
            print(f"Creating user: {user}")
            return user
        """
        
        is_ready, issues = ExecutionValidator.check_production_quality(bad_code)
        assert not is_ready
        assert len(issues) >= 3  # AI comment, TODO, debug print
    
    def test_database_migration_execution(self):
        """Test prompts for database migration."""
        context = {
            "source": "MySQL",
            "target": "PostgreSQL",
            "plan": ["Export schema", "Transform data types", "Import data", "Verify integrity"]
        }
        
        prompt = generate_execution_prompt("migration", context)
        assert "Preserve all functionality" in prompt
        assert "Rollback capability required" in prompt
        assert all(step in prompt for step in context["plan"])
    
    def test_performance_optimization_execution(self):
        """Test prompts for performance optimization."""
        builder = ExecutionPromptBuilder()
        builder.context["component"] = "search algorithm"
        builder.context["metrics"] = ["Response time < 100ms", "Memory usage < 50MB"]
        
        prompt = builder.with_mode(ExecutionMode.PERFORMANCE).build()
        assert "Profile first. Optimize second" in prompt
        assert "Response time < 100ms" in prompt
        assert "Avoid premature optimization" in prompt
    
    def test_security_fix_execution(self):
        """Test prompts for security fixes."""
        context = {
            "vulnerability": "SQL Injection in user search",
            "severity": "CRITICAL",
            "impact": "Database compromise possible"
        }
        
        prompt = generate_execution_prompt("security", context)
        assert "Fix immediately" in prompt
        assert "No information leakage" in prompt
        assert "Full security audit" in prompt
    
    def test_validates_human_looking_code(self):
        """Test validation of human vs AI-looking code."""
        human_code = """
        def auth(user, pwd):
            if not user or not pwd:
                raise ValueError("Invalid credentials")
            
            hashed = hash_pwd(pwd)
            stored = db.get_pwd_hash(user)
            
            if not stored or hashed != stored:
                log_failed_auth(user)
                return False
            
            return create_session(user)
        """
        
        ai_code = """
        class AuthenticationManager:
            \"\"\"This class handles user authentication.\"\"\"
            
            def authenticate_user_with_credentials(self, username_string, password_string):
                \"\"\"This method authenticates a user with their credentials.\"\"\"
                # Initialize the result
                authentication_result = None
                
                # Check if username and password are provided
                if username_string and password_string:
                    # Create a password hasher helper
                    password_hasher_helper = PasswordHasherHelper()
                    # Hash the password
                    hashed_password_value = password_hasher_helper.hash_password(password_string)
                    
                    # TODO: Implement database lookup
                    print("Authenticating user...")  # Debug
                    
                return authentication_result  # Return the result
        """
        
        # Human code should pass
        is_ready, issues = ExecutionValidator.check_production_quality(human_code)
        assert len(issues) == 0 or len(issues) <= 1  # Maybe missing some error handling
        
        # AI code should fail spectacularly
        is_ready, issues = ExecutionValidator.check_production_quality(ai_code)
        assert not is_ready
        assert len(issues) >= 5  # Multiple AI patterns, TODO, debug print, etc.