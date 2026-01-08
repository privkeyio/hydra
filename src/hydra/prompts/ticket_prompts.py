"""Task-oriented ticket generation prompts for Hydra.

Focused on creating actionable, testable tickets for Claude Code execution.
All prompts use minimalistic, surgical language without AI patterns.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class TicketComplexity(Enum):
    """Ticket complexity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ModelSelection(Enum):
    """Model selection for tickets."""

    BALANCED = "balanced"  # Standard tasks
    SMART = "smart"  # Complex/critical tasks


@dataclass
class TicketTemplate:
    """Template for ticket generation."""

    id: str
    title: str
    description: str
    acceptance_criteria: List[str]
    dependencies: List[str]
    model: str
    priority: str
    status: str = "TODO"


class TicketGenerationPrompts:
    """Prompts for generating implementation tickets."""

    BASE_GENERATION = """Generate implementation tickets for Claude Code execution.

CRITICAL: Create tickets that result in real, functional code files.
Each acceptance criterion MUST produce actual implementation.

Requirements:
- Use task language only - what to do, not how
- Acceptance criteria as [ ] checklist items that are specific and testable
- Each criterion must create actual files with working functionality
- Dependencies listed by ticket ID
- Model selection: balanced for standard tasks, smart for complex/critical tasks
- Use minimalistic, surgical language - no fluff, no AI patterns, no emojis
- Focus on concrete deliverables that provide value

Input: {project_description}

Analyze project and generate tickets that:
1. Break down into logical, independent tasks
2. Create working code files with real functionality
3. Include complete test coverage
4. Have clear dependency chains
5. Use appropriate model selection based on complexity

Smart model selection rules:
- Use 'smart' for: complex algorithms, critical path features, high-risk components, system architecture
- Use 'balanced' for: standard CRUD operations, simple utilities, configuration, basic tests

Each ticket must be:
- Completable in 1-4 hours
- Independently testable
- Production-ready when finished

Output format: YAML
```yaml
tickets:
  - id: '001'
    title: Brief descriptive title (5-10 words)
    description: Clear task with specific implementation focus
    status: TODO
    model: balanced/smart
    priority: low/medium/high/critical
    acceptance_criteria:
      - [ ] Create [specific file] implementing [specific functionality]
      - [ ] Add [specific tests] verifying [specific behavior]
      - [ ] Implement [feature] that handles [specific cases]
    dependencies: []
```"""

    FEATURE_DECOMPOSITION = """Break down feature into implementation tickets.

Feature: {feature_description}
Constraints: {constraints}

Split into logical, independent tickets with clear boundaries.
Each ticket should be completable in 1-4 hours.
Order by dependency chain."""

    COMPLEXITY_ESTIMATION = """Estimate complexity for ticket.

Title: {title}
Description: {description}
Criteria: {acceptance_criteria}

Consider:
- Lines of code required
- Number of files affected
- Testing complexity
- External dependencies
- Risk of breaking changes

Return: low/medium/high/critical with brief reasoning."""

    DEPENDENCY_MAPPING = """Analyze and map ticket dependencies for optimal execution order.

Tickets:
{tickets_list}

Analyze each ticket and identify:

1. Hard dependencies (must complete before):
   - Code that other tickets rely on
   - Infrastructure/setup requirements
   - Database schemas, APIs, core modules

2. Soft dependencies (beneficial but not required):
   - Shared utilities that could be helpful
   - Similar patterns or approaches
   - Common test frameworks

3. Parallel execution opportunities:
   - Independent features
   - Different components/modules
   - Separate test suites

Output dependency graph in YAML format:
```yaml
dependencies:
  ticket_001: []  # No dependencies
  ticket_002: ["001"]  # Depends on 001
  ticket_003: ["001"]  # Depends on 001, can run parallel with 002
  ticket_004: ["002", "003"]  # Depends on both 002 and 003
```

Include reasoning for each dependency relationship."""

    ACCEPTANCE_CRITERIA_GENERATION = """Generate specific, testable acceptance criteria checklist.

Task: {task_description}
Context: {context}

Create 3-7 concrete criteria that:
1. Specify exact files to create with functionality
2. Define specific tests to implement 
3. Describe measurable outcomes
4. Can be verified through code execution
5. Result in production-ready implementation

Format as actionable [ ] checklist items:
- [ ] Create [specific file.py] implementing [exact functionality]
- [ ] Add [specific test] verifying [exact behavior with input/output]
- [ ] Implement [feature] handling [specific edge cases/error conditions]

Avoid vague requirements. Each criterion must produce real code."""

    MODEL_SELECTION = """Select appropriate model for ticket execution.

Ticket Analysis:
- Complexity: {complexity}
- Risk: {risk_level}
- Dependencies: {dependency_count}
- Critical path: {is_critical}
- Lines of code estimate: {code_estimate}
- Testing complexity: {test_complexity}

Model Selection Rules:

Use 'smart' for:
- Complex algorithms or data structures
- Critical path features affecting system reliability
- High-risk components with security implications
- System architecture and core infrastructure
- Integration with external APIs/services
- Performance-critical code requiring optimization
- Complex business logic with multiple edge cases
- Code requiring careful error handling

Use 'balanced' for:
- Standard CRUD operations
- Simple utilities and helper functions
- Configuration and setup code
- Basic unit tests and fixtures
- Straightforward file operations
- Simple data transformations
- Standard REST API endpoints
- Basic validation logic

Decision Matrix:
- High complexity + High risk = smart
- Medium complexity + Critical path = smart
- Low complexity + Low risk = balanced
- Standard patterns + Low risk = balanced

Return: balanced or smart with specific reasoning based on ticket characteristics."""

    TICKET_VALIDATION = """Validate ticket for production readiness and execution quality.

Ticket:
{ticket_content}

Validation Checklist:

1. Title Quality:
   - 5-10 words maximum
   - Action-oriented (Create, Implement, Add, Build)
   - No vague terms ("Enhance", "Improve", "Optimize")
   - Clear scope boundary

2. Description Quality:
   - Specific implementation focus
   - No AI language patterns or excessive enthusiasm
   - No emojis or excessive punctuation
   - Surgical, minimalistic language
   - Clear success criteria

3. Acceptance Criteria:
   - 3-7 concrete [ ] checklist items
   - Each creates specific files with functionality
   - All testable and measurable
   - No empty directories or structure-only tasks
   - Production-ready outcomes

4. Technical Validity:
   - Appropriate model selection (balanced/smart)
   - Accurate dependency references
   - Realistic scope (1-4 hours completion)
   - No ambiguous requirements

5. Anti-Patterns Check:
   - No AI-like verbose naming
   - No placeholder text
   - No "TODO" comments in criteria
   - No boilerplate requirements

Return: PRODUCTION_READY, NEEDS_REVISION, or INVALID with specific issues list."""

    BATCH_GENERATION = """Generate all tickets for project.

Project: {project_name}
Description: {project_description}
Requirements:
{requirements_list}

Generate complete ticket set with:
- Logical task breakdown
- Proper dependency chain
- Appropriate model selection
- Testable criteria for each
- Priority ordering

Maximum {max_tickets} tickets."""

    TICKET_REFINEMENT = """Refine ticket for clarity and execution.

Original ticket:
{original_ticket}

Improve:
- Title precision
- Description clarity
- Criteria specificity
- Remove ambiguity
- Ensure testability

Maintain technical accuracy."""

    SPRINT_PLANNING = """Plan ticket execution order.

Available tickets:
{tickets}

Resources: {available_resources}
Timeline: {sprint_duration}

Optimize for:
- Dependency satisfaction
- Risk mitigation
- Value delivery
- Resource utilization

Return ordered execution plan."""


class TicketPromptBuilder:
    """Builder for constructing ticket generation prompts."""

    def __init__(self):
        self.context = {}
        self.prompts = TicketGenerationPrompts()

    def with_project(self, name: str, description: str) -> "TicketPromptBuilder":
        """Add project context."""
        self.context["project_name"] = name
        self.context["project_description"] = description
        return self

    def with_requirements(self, requirements: List[str]) -> "TicketPromptBuilder":
        """Add requirements list."""
        self.context["requirements_list"] = "\n".join(f"- {req}" for req in requirements)
        return self

    def with_constraints(self, constraints: Dict[str, Any]) -> "TicketPromptBuilder":
        """Add constraints."""
        self.context["constraints"] = constraints
        return self

    def with_max_tickets(self, max_tickets: int) -> "TicketPromptBuilder":
        """Set maximum number of tickets."""
        self.context["max_tickets"] = max_tickets
        return self

    def build_generation_prompt(self) -> str:
        """Build complete generation prompt."""
        base = self.prompts.BASE_GENERATION
        for key, value in self.context.items():
            base = base.replace(f"{{{key}}}", str(value))
        return base

    def build_batch_prompt(self) -> str:
        """Build batch generation prompt."""
        batch = self.prompts.BATCH_GENERATION
        for key, value in self.context.items():
            batch = batch.replace(f"{{{key}}}", str(value))
        return batch


class TicketValidator:
    """Validator for generated tickets."""

    @staticmethod
    def validate_ticket(ticket: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate single ticket.
        
        Args:
            ticket: Ticket dictionary
            
        Returns:
            Tuple of (is_valid, issues_list)

        """
        issues = []

        # Required fields
        required = ["id", "title", "description", "acceptance_criteria", "model", "status"]
        for field in required:
            if field not in ticket:
                issues.append(f"Missing required field: {field}")

        # Title length
        if "title" in ticket:
            title_words = len(ticket["title"].split())
            if title_words < 3 or title_words > 15:
                issues.append(f"Title should be 3-15 words, got {title_words}")

        # Acceptance criteria
        if "acceptance_criteria" in ticket:
            criteria = ticket["acceptance_criteria"]
            if not isinstance(criteria, list):
                issues.append("Acceptance criteria must be a list")
            elif len(criteria) < 1:
                issues.append("At least one acceptance criterion required")
            else:
                for criterion in criteria:
                    if not criterion.strip().startswith("- [ ]"):
                        issues.append(f"Invalid criterion format: {criterion}")

        # Model validation
        if "model" in ticket:
            if ticket["model"] not in ["balanced", "smart"]:
                issues.append(f"Invalid model: {ticket['model']}")

        # Check for AI patterns
        ai_patterns = [
            "delighted", "certainly", "absolutely", "wonderful", "excellent",
            "fantastic", "amazing", "pleased", "happy to", "feel free",
            "don't hesitate", "please note", "it's important", "keep in mind",
            "bear in mind", "worth noting", "great question", "good point",
            "perfect", "brilliant", "outstanding", "remarkable", "impressive"
        ]
        text_to_check = f"{ticket.get('title', '')} {ticket.get('description', '')} {' '.join(ticket.get('acceptance_criteria', []))}"
        for pattern in ai_patterns:
            if pattern.lower() in text_to_check.lower():
                issues.append(f"AI pattern detected: {pattern}")

        # Check for emojis
        import re
        emoji_pattern = re.compile("["
            u"\U0001F600-\U0001F64F"  # emoticons
            u"\U0001F300-\U0001F5FF"  # symbols & pictographs
            u"\U0001F680-\U0001F6FF"  # transport & map symbols
            u"\U0001F1E0-\U0001F1FF"  # flags
            "]+", flags=re.UNICODE)

        if emoji_pattern.search(text_to_check):
            issues.append("Emoji usage detected")

        # Check for vague terms
        vague_terms = ["enhance", "improve", "optimize", "better", "upgrade", "refactor"]
        title_lower = ticket.get('title', '').lower()
        for term in vague_terms:
            if term in title_lower:
                issues.append(f"Vague term in title: {term}")

        return len(issues) == 0, issues

    @staticmethod
    def validate_batch(tickets: List[Dict[str, Any]]) -> tuple[bool, Dict[str, List[str]]]:
        """Validate batch of tickets.
        
        Args:
            tickets: List of ticket dictionaries
            
        Returns:
            Tuple of (all_valid, dict of ticket_id to issues)

        """
        all_issues = {}
        all_valid = True

        # Check individual tickets
        for ticket in tickets:
            ticket_id = ticket.get("id", "unknown")
            is_valid, issues = TicketValidator.validate_ticket(ticket)
            if not is_valid:
                all_valid = False
                all_issues[ticket_id] = issues

        # Check dependencies
        ticket_ids = {t.get("id") for t in tickets}
        for ticket in tickets:
            deps = ticket.get("dependencies", [])
            for dep in deps:
                if dep not in ticket_ids and dep:
                    ticket_id = ticket.get("id", "unknown")
                    if ticket_id not in all_issues:
                        all_issues[ticket_id] = []
                    all_issues[ticket_id].append(f"Invalid dependency: {dep}")
                    all_valid = False

        return all_valid, all_issues


def generate_ticket_prompt(operation: str, context: Dict[str, Any]) -> str:
    """Generate appropriate ticket prompt.
    
    Args:
        operation: Ticket operation type
        context: Context for prompt generation
        
    Returns:
        Generated prompt string

    """
    prompts = TicketGenerationPrompts()

    operation_map = {
        "generate": prompts.BASE_GENERATION,
        "decompose": prompts.FEATURE_DECOMPOSITION,
        "estimate": prompts.COMPLEXITY_ESTIMATION,
        "dependencies": prompts.DEPENDENCY_MAPPING,
        "criteria": prompts.ACCEPTANCE_CRITERIA_GENERATION,
        "select_model": prompts.MODEL_SELECTION,
        "validate": prompts.TICKET_VALIDATION,
        "batch": prompts.BATCH_GENERATION,
        "refine": prompts.TICKET_REFINEMENT,
        "plan": prompts.SPRINT_PLANNING
    }

    prompt_template = operation_map.get(operation, prompts.BASE_GENERATION)

    # Substitute context variables
    for key, value in context.items():
        prompt_template = prompt_template.replace(f"{{{key}}}", str(value))

    return prompt_template


def test_ticket_generation_with_real_projects() -> Dict[str, Any]:
    """Test ticket generation with real project descriptions.
    
    Returns:
        Test results and quality metrics

    """
    test_projects = [
        {
            "name": "Simple Calculator API",
            "description": "Create REST API for basic math operations with user authentication"
        },
        {
            "name": "File Upload Service",
            "description": "Build microservice for secure file uploads with virus scanning"
        },
        {
            "name": "Chat Application",
            "description": "Real-time chat app with React frontend and WebSocket backend"
        }
    ]

    results = {}
    validator = TicketValidator()

    for project in test_projects:
        # Test ticket generation
        context = {
            "project_description": project["description"],
            "max_tickets": 5
        }

        prompt = generate_ticket_prompt("generate", context)

        # Mock validation (in real implementation, this would call LLM)
        results[project["name"]] = {
            "prompt_length": len(prompt),
            "contains_ai_patterns": any(pattern in prompt.lower() for pattern in [
                "delighted", "certainly", "absolutely", "wonderful"
            ]),
            "has_clear_structure": "YAML" in prompt and "acceptance_criteria" in prompt,
            "actionable": "[ ]" in prompt and "Create" in prompt
        }

    return results


def validate_ticket_actionability(ticket: Dict[str, Any]) -> tuple[bool, List[str]]:
    """Validate that ticket is actionable without ambiguity.
    
    Args:
        ticket: Ticket dictionary to validate
        
    Returns:
        Tuple of (is_actionable, list_of_ambiguities)

    """
    ambiguities = []

    # Check for specific file creation
    criteria = ticket.get("acceptance_criteria", [])
    file_creation_count = sum(1 for c in criteria if "Create" in c and ".py" in c)
    if file_creation_count == 0:
        ambiguities.append("No specific file creation criteria")

    # Check for test specification
    test_count = sum(1 for c in criteria if "test" in c.lower())
    if test_count == 0:
        ambiguities.append("No test requirements specified")

    # Check for vague language
    vague_phrases = ["as needed", "if necessary", "when appropriate", "possibly", "maybe"]
    description = ticket.get("description", "")
    for phrase in vague_phrases:
        if phrase in description.lower():
            ambiguities.append(f"Vague language: {phrase}")

    # Check for measurable outcomes
    measurable_words = ["implement", "create", "add", "build", "write", "test"]
    has_measurable = any(word in description.lower() for word in measurable_words)
    if not has_measurable:
        ambiguities.append("No measurable action words in description")

    return len(ambiguities) == 0, ambiguities


def create_ticket_from_template(
    title: str,
    description: str,
    criteria: List[str],
    complexity: TicketComplexity = TicketComplexity.MEDIUM,
    dependencies: Optional[List[str]] = None
) -> TicketTemplate:
    """Create ticket from template.
    
    Args:
        title: Ticket title
        description: Task description
        criteria: Acceptance criteria list
        complexity: Task complexity
        dependencies: Optional dependency list
        
    Returns:
        TicketTemplate instance

    """
    # Auto-select model based on complexity
    model = ModelSelection.SMART.value if complexity in [
        TicketComplexity.HIGH,
        TicketComplexity.CRITICAL
    ] else ModelSelection.BALANCED.value

    # Format criteria
    formatted_criteria = [f"- [ ] {c}" if not c.startswith("- [ ]") else c for c in criteria]

    return TicketTemplate(
        id=f"{hash(title) % 1000:03d}",  # Simple ID generation
        title=title,
        description=description,
        acceptance_criteria=formatted_criteria,
        dependencies=dependencies or [],
        model=model,
        priority=complexity.value,
        status="TODO"
    )
