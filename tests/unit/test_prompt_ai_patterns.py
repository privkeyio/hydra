"""Tests to validate no AI-like patterns in generated prompts."""

import pytest
import re
from typing import List, Tuple

from hydra.prompts.system_prompts import SystemPrompts, PromptCategory
from hydra.prompts.ticket_prompts import TicketGenerationPrompts, generate_ticket_prompt
from hydra.prompts.execution_prompts import ProductionExecutionPrompts, generate_execution_prompt
from hydra.prompts.verification_prompts import BrutalVerificationPrompts, create_verification_prompt
from hydra.prompts.injection import validate_no_ai_patterns


class TestPromptAIPatterns:
    """Test all prompts for AI-like patterns."""
    
    # Common AI patterns to check for
    AI_PATTERNS = [
        "certainly", "absolutely", "definitely", "surely",
        "delighted", "happy to help", "glad to assist",
        "wonderful", "excellent", "fantastic", "amazing",
        "please note", "it's important to note", "kindly note",
        "feel free", "don't hesitate", "let me know",
        "i'd be happy", "i'll be glad", "i would love",
        "great question", "excellent choice", "good point",
        "thank you for", "thanks for asking", "appreciate"
    ]
    
    # Emoji pattern
    EMOJI_PATTERN = re.compile("["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags
        u"\U0001F900-\U0001F9FF"  # additional emoticons
        u"\U00002600-\U000027BF"  # misc symbols
        "]+", flags=re.UNICODE)
    
    def check_ai_patterns(self, text: str) -> List[str]:
        """Check text for AI patterns.
        
        Args:
            text: Text to check
            
        Returns:
            List of detected patterns
        """
        detected = []
        text_lower = text.lower()
        
        # Check for AI language patterns
        for pattern in self.AI_PATTERNS:
            if pattern in text_lower:
                detected.append(f"AI pattern: '{pattern}'")
        
        # Check for emojis
        if self.EMOJI_PATTERN.search(text):
            detected.append("Emoji detected")
        
        # Check for overly polite language
        polite_patterns = [
            r"\bplease\s+\w+",  # "please do", "please note"
            r"\bkindly\s+\w+",  # "kindly check"
            r"\bwould you\b",  # "would you mind"
            r"\bcould you\b",  # "could you please"
        ]
        
        for pattern in polite_patterns:
            if re.search(pattern, text_lower):
                detected.append(f"Overly polite: '{pattern}'")
        
        # Check for verbose explanations
        if "in order to" in text_lower:
            detected.append("Verbose: 'in order to' -> use 'to'")
        if "due to the fact that" in text_lower:
            detected.append("Verbose: 'due to the fact that' -> use 'because'")
        
        return detected
    
    def test_system_prompts_no_ai_patterns(self):
        """Test system prompts have no AI patterns."""
        failures = []
        
        # Check all prompts in SystemPrompts.PROMPTS
        for category in PromptCategory:
            prompts = SystemPrompts.get_all_prompts_for_category(category)
            for subtype, prompt in prompts.items():
                patterns = self.check_ai_patterns(prompt)
                if patterns:
                    failures.append(f"{category.value}.{subtype}: {patterns}")
        
        # Check provider overrides
        for provider, overrides in SystemPrompts.PROVIDER_OVERRIDES.items():
            for key, prompt in overrides.items():
                patterns = self.check_ai_patterns(prompt)
                if patterns:
                    failures.append(f"Provider {provider}.{key}: {patterns}")
        
        assert len(failures) == 0, f"AI patterns found:\n" + "\n".join(failures)
    
    def test_ticket_prompts_no_ai_patterns(self):
        """Test ticket prompts have no AI patterns."""
        failures = []
        prompts_obj = TicketGenerationPrompts()
        
        # Check all class attributes that are prompts
        prompt_attrs = [
            attr for attr in dir(prompts_obj) 
            if not attr.startswith('_') and isinstance(getattr(prompts_obj, attr), str)
        ]
        
        for attr in prompt_attrs:
            prompt = getattr(prompts_obj, attr)
            patterns = self.check_ai_patterns(prompt)
            if patterns:
                failures.append(f"TicketGenerationPrompts.{attr}: {patterns}")
        
        assert len(failures) == 0, f"AI patterns found:\n" + "\n".join(failures)
    
    def test_execution_prompts_no_ai_patterns(self):
        """Test execution prompts have no AI patterns."""
        failures = []
        prompts_obj = ProductionExecutionPrompts()
        
        # Check all class attributes that are prompts
        prompt_attrs = [
            attr for attr in dir(prompts_obj) 
            if not attr.startswith('_') and isinstance(getattr(prompts_obj, attr), str)
        ]
        
        for attr in prompt_attrs:
            prompt = getattr(prompts_obj, attr)
            patterns = self.check_ai_patterns(prompt)
            if patterns:
                failures.append(f"ProductionExecutionPrompts.{attr}: {patterns}")
        
        assert len(failures) == 0, f"AI patterns found:\n" + "\n".join(failures)
    
    def test_verification_prompts_no_ai_patterns(self):
        """Test verification prompts have no AI patterns."""
        failures = []
        prompts_obj = BrutalVerificationPrompts()
        
        # Check all class attributes that are prompts
        prompt_attrs = [
            attr for attr in dir(prompts_obj) 
            if not attr.startswith('_') and isinstance(getattr(prompts_obj, attr), str)
        ]
        
        for attr in prompt_attrs:
            prompt = getattr(prompts_obj, attr)
            patterns = self.check_ai_patterns(prompt)
            if patterns:
                failures.append(f"BrutalVerificationPrompts.{attr}: {patterns}")
        
        assert len(failures) == 0, f"AI patterns found:\n" + "\n".join(failures)
    
    def test_generated_prompts_no_ai_patterns(self):
        """Test dynamically generated prompts have no AI patterns."""
        failures = []
        
        # Test ticket generation
        ticket_prompt = generate_ticket_prompt("generate", {
            "project_description": "Test project"
        })
        patterns = self.check_ai_patterns(ticket_prompt)
        if patterns:
            failures.append(f"Generated ticket prompt: {patterns}")
        
        # Test execution prompt
        exec_prompt = generate_execution_prompt("main", {
            "ticket_id": "001",
            "acceptance_criteria": ["Test"]
        })
        patterns = self.check_ai_patterns(exec_prompt)
        if patterns:
            failures.append(f"Generated execution prompt: {patterns}")
        
        # Test verification prompt
        verify_prompt = create_verification_prompt("boss", {
            "ticket_id": "001",
            "implementation_summary": "Test"
        })
        patterns = self.check_ai_patterns(verify_prompt)
        if patterns:
            failures.append(f"Generated verification prompt: {patterns}")
        
        assert len(failures) == 0, f"AI patterns found:\n" + "\n".join(failures)
    
    def test_validate_no_ai_patterns_function(self):
        """Test the validate_no_ai_patterns function works correctly."""
        # Test valid prompts
        valid_prompts = [
            "Execute the task",
            "Get it done",
            "Check all criteria",
            "Run tests and verify",
            "Production quality required"
        ]
        
        for prompt in valid_prompts:
            valid, msg = validate_no_ai_patterns(prompt)
            assert valid, f"False positive for: '{prompt}' - {msg}"
        
        # Test invalid prompts
        invalid_prompts = [
            ("I'll be delighted to help", "delighted"),
            ("Certainly! Let's do this", "certainly"),
            ("Great work! 👍", "Emoji"),
            ("Please feel free to ask", "feel free"),
            ("This is absolutely wonderful", "absolutely")
        ]
        
        for prompt, expected_pattern in invalid_prompts:
            valid, msg = validate_no_ai_patterns(prompt)
            assert not valid, f"Missed AI pattern in: '{prompt}'"
            assert expected_pattern.lower() in msg.lower(), f"Wrong pattern detected: {msg}"


class TestPromptMinimalism:
    """Test prompts follow minimalistic principles."""
    
    def test_prompt_conciseness(self):
        """Test prompts are concise."""
        failures = []
        
        # Check system prompts
        for category in PromptCategory:
            prompts = SystemPrompts.get_all_prompts_for_category(category)
            for subtype, prompt in prompts.items():
                lines = prompt.split('\n')
                for line in lines:
                    # Check for overly long lines (except lists/criteria)
                    if len(line) > 100 and not line.startswith('-') and not line.startswith('*'):
                        failures.append(f"{category.value}.{subtype}: Line too long ({len(line)} chars)")
                
                # Check for excessive newlines
                if '\n\n\n' in prompt:
                    failures.append(f"{category.value}.{subtype}: Excessive newlines")
        
        assert len(failures) == 0, f"Verbosity issues found:\n" + "\n".join(failures)
    
    def test_no_unnecessary_words(self):
        """Test prompts don't use unnecessary words."""
        unnecessary_phrases = [
            "in order to",  # use "to"
            "due to the fact that",  # use "because"
            "at this point in time",  # use "now"
            "in the event that",  # use "if"
            "for the purpose of",  # use "for" or "to"
            "with regard to",  # use "about"
            "in spite of the fact that",  # use "although"
        ]
        
        failures = []
        
        # Check all prompts
        for category in PromptCategory:
            prompts = SystemPrompts.get_all_prompts_for_category(category)
            for subtype, prompt in prompts.items():
                prompt_lower = prompt.lower()
                for phrase in unnecessary_phrases:
                    if phrase in prompt_lower:
                        failures.append(f"{category.value}.{subtype}: Unnecessary phrase '{phrase}'")
        
        assert len(failures) == 0, f"Unnecessary phrases found:\n" + "\n".join(failures)


class TestPromptEffectiveness:
    """Test prompts are effective and actionable."""
    
    def test_prompts_are_actionable(self):
        """Test prompts contain actionable instructions."""
        # Key action words that should appear in prompts
        action_words = [
            "check", "verify", "test", "run", "execute",
            "implement", "create", "fix", "ensure", "validate",
            "generate", "build", "review", "assess", "analyze"
        ]
        
        failures = []
        
        # Check execution prompts have action words
        exec_prompts = ProductionExecutionPrompts()
        for attr in dir(exec_prompts):
            if not attr.startswith('_') and isinstance(getattr(exec_prompts, attr), str):
                prompt = getattr(exec_prompts, attr)
                prompt_lower = prompt.lower()
                
                has_action = any(word in prompt_lower for word in action_words)
                if not has_action and len(prompt) > 50:  # Skip very short prompts
                    failures.append(f"ProductionExecutionPrompts.{attr}: No action words")
        
        assert len(failures) == 0, f"Non-actionable prompts found:\n" + "\n".join(failures)
    
    def test_prompts_have_clear_outcomes(self):
        """Test prompts specify clear outcomes."""
        outcome_indicators = [
            "return:", "output:", "result:", "format:",
            "must", "should", "required", "ensure",
            "verify", "check", "confirm"
        ]
        
        failures = []
        
        # Check verification prompts have clear outcomes
        verify_prompts = BrutalVerificationPrompts()
        for attr in dir(verify_prompts):
            if not attr.startswith('_') and isinstance(getattr(verify_prompts, attr), str):
                prompt = getattr(verify_prompts, attr)
                prompt_lower = prompt.lower()
                
                has_outcome = any(indicator in prompt_lower for indicator in outcome_indicators)
                if not has_outcome and len(prompt) > 100:  # Only check substantial prompts
                    failures.append(f"BrutalVerificationPrompts.{attr}: No clear outcome specified")
        
        # Allow some flexibility - not all prompts need explicit outcomes
        assert len(failures) <= 2, f"Too many prompts without clear outcomes:\n" + "\n".join(failures)


class TestPromptConsistency:
    """Test prompts are consistent in style and format."""
    
    def test_consistent_terminology(self):
        """Test prompts use consistent terminology."""
        # Terms that should be used consistently
        term_variations = {
            "acceptance criteria": ["acceptance criterion", "accept criteria"],
            "production": ["prod"],
            "test": ["tests", "testing"],  # These are acceptable variations
        }
        
        failures = []
        
        for category in PromptCategory:
            prompts = SystemPrompts.get_all_prompts_for_category(category)
            for subtype, prompt in prompts.items():
                prompt_lower = prompt.lower()
                
                for preferred, variations in term_variations.items():
                    for variant in variations:
                        # Skip if it's a valid variation (like test/tests)
                        if variant in ["tests", "testing"]:
                            continue
                        
                        if variant in prompt_lower and preferred not in prompt_lower:
                            failures.append(
                                f"{category.value}.{subtype}: "
                                f"Uses '{variant}' instead of '{preferred}'"
                            )
        
        assert len(failures) == 0, f"Inconsistent terminology found:\n" + "\n".join(failures)
    
    def test_consistent_formatting(self):
        """Test prompts use consistent formatting."""
        failures = []
        
        for category in PromptCategory:
            prompts = SystemPrompts.get_all_prompts_for_category(category)
            for subtype, prompt in prompts.items():
                # Check for consistent list formatting
                if '- ' in prompt and '* ' in prompt:
                    failures.append(f"{category.value}.{subtype}: Mixed list markers (- and *)")
                
                # Check for consistent checkbox formatting
                if '[ ]' in prompt and '[x]' in prompt.lower():
                    # This might be intentional for examples
                    pass
                
                # Check for trailing whitespace
                lines = prompt.split('\n')
                for i, line in enumerate(lines):
                    if line.endswith(' '):
                        failures.append(
                            f"{category.value}.{subtype}: Trailing whitespace on line {i+1}"
                        )
        
        assert len(failures) == 0, f"Formatting inconsistencies found:\n" + "\n".join(failures)