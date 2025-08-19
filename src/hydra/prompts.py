"""Optimized prompt templates for minimal token usage."""

from typing import Any, Dict, List, Optional

try:
    import tiktoken
except ImportError:
    tiktoken = None


class PromptTemplates:
    """Concise prompt templates optimized for token efficiency."""

    # Core system prompts - extremely concise
    SYSTEM_PROMPTS = {
        "code": "Expert coder. Clean code only.",
        "json": "Return valid JSON only.",
        "analysis": "Analyze and report concisely.",
        "fix": "Fix issues efficiently.",
    }

    # Task templates - minimal instructions
    TASK_TEMPLATES = {
        "ticket": """Ticket {id}: {title}
{description}
Criteria: {criteria}
Dir: {dir}
{deps}
Implement now.""",
        "verify": """Check Ticket {id} criteria:
{criteria}
Fix unmet items. Update status.""",
        "code_gen": "{task}\nReturn code only.",
        "json_gen": "{task}\nJSON only.",
        "test": "Write tests for:\n{code}\nPytest format.",
        "fix_error": "Error: {error}\nFile: {file}\nFix it.",
        "review": "Review:\n{code}\nIssues only.",
    }

    @staticmethod
    def format_criteria(criteria: List[str]) -> str:
        """Format acceptance criteria minimally."""
        return "\n".join(f"- {c}" for c in criteria)

    @staticmethod
    def format_deps(deps: Dict[str, Any]) -> str:
        """Format dependencies minimally."""
        if not deps:
            return ""
        return f"Deps: {', '.join(deps.keys())}"


class TokenCounter:
    """Count tokens for prompts to track reduction."""

    def __init__(self, model: str = "gpt-4"):
        """Initialize token counter with model encoding."""
        try:
            # Map model names to encoding
            encoding_map = {
                "gpt-4": "cl100k_base",
                "gpt-3.5": "cl100k_base",
                "claude": "cl100k_base",  # Approximate
                "llama": "cl100k_base",  # Approximate
            }

            # Get encoding name
            encoding_name = "cl100k_base"  # Default
            for key in encoding_map:
                if key in model.lower():
                    encoding_name = encoding_map[key]
                    break

            self.encoding = tiktoken.get_encoding(encoding_name)
        except Exception:
            # Fallback to approximate counting
            self.encoding = None

    def count(self, text: str) -> int:
        """Count tokens in text."""
        if self.encoding:
            return len(self.encoding.encode(text))
        # Fallback: approximate 4 chars per token
        return len(text) // 4

    def compare(self, old: str, new: str) -> Dict[str, Any]:
        """Compare token counts between old and new prompts."""
        old_tokens = self.count(old)
        new_tokens = self.count(new)
        reduction = (
            (old_tokens - new_tokens) / old_tokens * 100 if old_tokens > 0 else 0
        )

        return {
            "old_tokens": old_tokens,
            "new_tokens": new_tokens,
            "reduction_percent": round(reduction, 1),
            "tokens_saved": old_tokens - new_tokens,
        }


class PromptOptimizer:
    """Optimize prompts for minimal token usage."""

    def __init__(self):
        self.templates = PromptTemplates()
        self.counter = TokenCounter()
        self.stats = {
            "total_old_tokens": 0,
            "total_new_tokens": 0,
            "prompts_optimized": 0,
        }

    def optimize(self, prompt: str, prompt_type: str = "general") -> str:
        """Optimize a prompt for minimal tokens.

        Args:
            prompt: Original verbose prompt
            prompt_type: Type of prompt (ticket, verify, code_gen, etc.)

        Returns:
            Optimized prompt with minimal tokens

        """
        # Track original
        self.stats["total_old_tokens"] += self.counter.count(prompt)

        # Apply optimizations
        optimized = self._apply_optimizations(prompt, prompt_type)

        # Track optimized
        self.stats["total_new_tokens"] += self.counter.count(optimized)
        self.stats["prompts_optimized"] += 1

        return optimized

    def _apply_optimizations(self, prompt: str, prompt_type: str) -> str:
        """Apply optimization techniques to reduce tokens."""
        # Remove verbose phrases
        replacements = {
            # Verbose -> Concise
            "You are an expert": "",
            "You are a": "",
            "Please ensure": "Ensure",
            "Please make sure": "Ensure",
            "Make sure to": "",
            "Always remember to": "",
            "Don't forget to": "",
            "It's important to": "",
            "You should": "",
            "You must": "Must",
            "You need to": "",
            "Be careful to": "",
            "Remember that": "",
            "Keep in mind": "",
            "Note that": "",
            "IMPORTANT:": "",
            "WARNING:": "",
            "CRITICAL:": "",
            "REQUIREMENTS:": "",
            "Please provide": "Provide",
            "Please write": "Write",
            "Please create": "Create",
            "Please implement": "Implement",
            "with the following": ":",
            "according to": "per",
            "in order to": "to",
            "make use of": "use",
            "a number of": "several",
            "the majority of": "most",
            "at this point in time": "now",
            "due to the fact that": "because",
            "in the event that": "if",
            "for the purpose of": "to",
            "with regard to": "about",
            "it is necessary to": "must",
            "there is a need to": "must",
            "has the ability to": "can",
            "is able to": "can",
            "in close proximity to": "near",
            "a large number of": "many",
            "the reason why": "why",
            "Clean, well-structured code": "Clean code",
            "clean, well-documented code": "clean code",
            "Respond with ONLY": "Only",
            "Python programmer": "Python dev",
            "software engineer": "dev",
            "Complete, working code": "Working code",
            "proper error handling": "error handling",
            "Include comments for complex logic": "Comment complex parts",
            "Focus on clarity, maintainability, and performance": "Clean, fast code",
            "Follow best practices and modern design patterns": "Best practices",
            "Write clean, efficient, and well-documented code": "Clean code",
        }

        optimized = prompt
        for verbose, concise in replacements.items():
            optimized = optimized.replace(verbose, concise)

        # Remove redundant whitespace and blank lines
        lines = [line.strip() for line in optimized.split("\n")]
        lines = [line for line in lines if line]  # Remove empty lines
        optimized = "\n".join(lines)

        # Remove redundant punctuation
        optimized = optimized.replace("..", ".")
        optimized = optimized.replace("!!", "!")
        optimized = optimized.replace("??", "?")

        return optimized

    def get_template(self, template_type: str, **kwargs) -> str:
        """Get an optimized prompt template.

        Args:
            template_type: Type of template (ticket, verify, code_gen, etc.)
            **kwargs: Template variables

        Returns:
            Formatted prompt from template

        """
        if template_type not in self.templates.TASK_TEMPLATES:
            return ""

        template = self.templates.TASK_TEMPLATES[template_type]

        # Format criteria if present
        if "criteria" in kwargs and isinstance(kwargs["criteria"], list):
            kwargs["criteria"] = self.templates.format_criteria(kwargs["criteria"])

        # Format deps if present
        if "deps" in kwargs and isinstance(kwargs["deps"], dict):
            kwargs["deps"] = self.templates.format_deps(kwargs["deps"])

        # Fill template
        try:
            return template.format(**kwargs)
        except KeyError:
            # Return template as-is if missing keys
            return template

    def get_system_prompt(self, prompt_type: str) -> str:
        """Get optimized system prompt.

        Args:
            prompt_type: Type of system prompt (code, json, analysis, fix)

        Returns:
            Optimized system prompt

        """
        return self.templates.SYSTEM_PROMPTS.get(prompt_type, "")

    def get_stats(self) -> Dict[str, Any]:
        """Get optimization statistics.

        Returns:
            Dictionary with token savings statistics

        """
        if self.stats["total_old_tokens"] == 0:
            reduction = 0
        else:
            reduction = (
                (self.stats["total_old_tokens"] - self.stats["total_new_tokens"])
                / self.stats["total_old_tokens"]
                * 100
            )

        return {
            "prompts_optimized": self.stats["prompts_optimized"],
            "total_old_tokens": self.stats["total_old_tokens"],
            "total_new_tokens": self.stats["total_new_tokens"],
            "tokens_saved": (
                self.stats["total_old_tokens"] - self.stats["total_new_tokens"]
            ),
            "reduction_percent": round(reduction, 1),
        }

    def reset_stats(self):
        """Reset optimization statistics."""
        self.stats = {
            "total_old_tokens": 0,
            "total_new_tokens": 0,
            "prompts_optimized": 0,
        }


# Global optimizer instance
_optimizer: Optional[PromptOptimizer] = None


def get_optimizer() -> PromptOptimizer:
    """Get or create the global prompt optimizer."""
    global _optimizer
    if _optimizer is None:
        _optimizer = PromptOptimizer()
    return _optimizer


def optimize_prompt(prompt: str, prompt_type: str = "general") -> str:
    """Optimize a prompt for minimal token usage.

    Args:
        prompt: Original verbose prompt
        prompt_type: Type of prompt

    Returns:
        Optimized prompt

    """
    optimizer = get_optimizer()
    return optimizer.optimize(prompt, prompt_type)


def get_prompt_template(template_type: str, **kwargs) -> str:
    """Get an optimized prompt template.

    Args:
        template_type: Type of template
        **kwargs: Template variables

    Returns:
        Formatted prompt from template

    """
    optimizer = get_optimizer()
    return optimizer.get_template(template_type, **kwargs)


def get_system_prompt(prompt_type: str) -> str:
    """Get optimized system prompt.

    Args:
        prompt_type: Type of system prompt

    Returns:
        Optimized system prompt

    """
    optimizer = get_optimizer()
    return optimizer.get_system_prompt(prompt_type)


def get_optimization_stats() -> Dict[str, Any]:
    """Get prompt optimization statistics.

    Returns:
        Dictionary with token savings statistics

    """
    optimizer = get_optimizer()
    return optimizer.get_stats()
