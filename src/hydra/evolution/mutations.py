"""
Code mutation strategies for evolutionary improvement.

Implements various mutation operators for code transformation,
including refactoring, optimization, and quality improvements.
"""

import ast
import asyncio
import random
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from hydra.evolution.core import CodeVariant

import logging

logger = logging.getLogger(__name__)


class MutationType(Enum):
    """Types of code mutations."""
    
    REFACTOR = "refactor"
    OPTIMIZE = "optimize"
    ADD_TESTS = "add_tests"
    IMPROVE_DOCS = "improve_docs"
    FIX_TYPES = "fix_types"
    EXTRACT_METHOD = "extract_method"
    INLINE_VARIABLE = "inline_variable"
    RENAME_VARIABLE = "rename_variable"
    ADD_CACHING = "add_caching"
    PARALLELIZE = "parallelize"


@dataclass
class MutationStrategy:
    """Configuration for a mutation strategy."""
    
    name: str
    mutation_type: MutationType
    probability: float = 0.1
    severity: str = "minor"  # minor, moderate, major
    target_patterns: List[str] = None
    
    def should_apply(self) -> bool:
        """Determine if mutation should be applied."""
        return random.random() < self.probability


class CodeMutator:
    """
    Applies mutations to code and configurations.
    
    Implements safe, intelligent code transformations for
    evolutionary improvement.
    """
    
    def __init__(self, mutation_rate: float = 0.3):
        self.mutation_rate = mutation_rate
        self.strategies = self._initialize_strategies()
        
    def _initialize_strategies(self) -> Dict[MutationType, MutationStrategy]:
        """Initialize mutation strategies."""
        return {
            MutationType.REFACTOR: MutationStrategy(
                name="Refactoring",
                mutation_type=MutationType.REFACTOR,
                probability=0.2,
                severity="moderate",
            ),
            MutationType.OPTIMIZE: MutationStrategy(
                name="Performance Optimization",
                mutation_type=MutationType.OPTIMIZE,
                probability=0.15,
                severity="major",
            ),
            MutationType.ADD_TESTS: MutationStrategy(
                name="Test Generation",
                mutation_type=MutationType.ADD_TESTS,
                probability=0.25,
                severity="minor",
            ),
            MutationType.IMPROVE_DOCS: MutationStrategy(
                name="Documentation",
                mutation_type=MutationType.IMPROVE_DOCS,
                probability=0.2,
                severity="minor",
            ),
            MutationType.FIX_TYPES: MutationStrategy(
                name="Type Annotations",
                mutation_type=MutationType.FIX_TYPES,
                probability=0.2,
                severity="minor",
            ),
        }
    
    async def create_variant(
        self,
        target_files: List[str],
        parent: Optional[CodeVariant] = None,
        generation: int = 0,
    ) -> CodeVariant:
        """
        Create a new variant with mutations applied.
        
        Args:
            target_files: Files to potentially mutate
            parent: Parent variant to mutate from
            generation: Generation number
            
        Returns:
            New CodeVariant with mutations
        """
        code_changes = {}
        config_changes = {}
        metadata = {"mutations": []}
        
        # Select files to mutate
        num_files = random.randint(1, min(3, len(target_files)))
        selected_files = random.sample(target_files, num_files)
        
        for file_path in selected_files:
            # Select mutation type
            mutation_type = self._select_mutation_type()
            
            # Apply mutation
            try:
                mutated_code = await self.mutate_file(file_path, mutation_type)
                if mutated_code:
                    code_changes[file_path] = mutated_code
                    metadata["mutations"].append({
                        "file": file_path,
                        "type": mutation_type.value,
                    })
            except Exception as e:
                logger.warning(f"Mutation failed for {file_path}: {e}")
        
        # Occasionally mutate configuration
        if random.random() < 0.2:
            config_changes = self._mutate_config(parent.config_changes if parent else {})
        
        return CodeVariant(
            id=uuid4(),
            parent_ids=[parent.id] if parent else [],
            generation=generation,
            code_changes=code_changes,
            config_changes=config_changes,
            metadata=metadata,
        )
    
    async def mutate_file(
        self,
        file_path: str,
        mutation_type: MutationType,
    ) -> Optional[str]:
        """
        Apply mutation to a single file.
        
        Args:
            file_path: Path to file to mutate
            mutation_type: Type of mutation to apply
            
        Returns:
            Mutated code or None if mutation failed
        """
        try:
            # Read file content
            with open(file_path, "r") as f:
                original_code = f.read()
            
            # Apply mutation based on type
            if mutation_type == MutationType.REFACTOR:
                return await self._refactor_mutation(original_code)
            elif mutation_type == MutationType.OPTIMIZE:
                return await self._optimize_mutation(original_code)
            elif mutation_type == MutationType.ADD_TESTS:
                return await self._test_generation_mutation(file_path, original_code)
            elif mutation_type == MutationType.IMPROVE_DOCS:
                return await self._documentation_mutation(original_code)
            elif mutation_type == MutationType.FIX_TYPES:
                return await self._type_annotation_mutation(original_code)
            else:
                return None
                
        except Exception as e:
            logger.error(f"Failed to mutate {file_path}: {e}")
            return None
    
    async def _refactor_mutation(self, code: str) -> str:
        """
        Apply refactoring mutations to code.
        
        Includes:
        - Extract long methods
        - Reduce cyclomatic complexity
        - Improve naming
        """
        try:
            tree = ast.parse(code)
            
            # Extract long functions
            class RefactorTransformer(ast.NodeTransformer):
                def visit_FunctionDef(self, node):
                    # If function is too long, consider extracting parts
                    if len(node.body) > 20:
                        # Add TODO comment for now
                        comment = ast.Expr(
                            value=ast.Constant(
                                value="TODO: Consider extracting this long function"
                            )
                        )
                        node.body.insert(0, comment)
                    return node
            
            transformer = RefactorTransformer()
            modified_tree = transformer.visit(tree)
            return ast.unparse(modified_tree)
            
        except Exception:
            # Return original if parsing fails
            return code
    
    async def _optimize_mutation(self, code: str) -> str:
        """
        Apply performance optimization mutations.
        
        Includes:
        - Add caching decorators
        - Use list comprehensions
        - Optimize loops
        """
        optimized = code
        
        # Add caching to functions without side effects
        cache_pattern = r"def (\w+)\(([^)]*)\):"
        matches = re.finditer(cache_pattern, code)
        
        for match in matches:
            func_name = match.group(1)
            # Only cache pure functions (heuristic: no "save", "write", "update")
            if not any(word in func_name.lower() for word in ["save", "write", "update", "delete"]):
                if "@lru_cache" not in code:
                    # Add import if needed
                    if "from functools import lru_cache" not in code:
                        optimized = "from functools import lru_cache\n" + optimized
                    # Add decorator
                    optimized = optimized.replace(
                        match.group(0),
                        f"@lru_cache(maxsize=128)\n{match.group(0)}"
                    )
                    break  # Only add one per mutation
        
        return optimized
    
    async def _test_generation_mutation(self, file_path: str, code: str) -> str:
        """
        Generate test code for functions.
        
        Creates basic test skeletons for untested functions.
        """
        # Extract module name from path
        module_path = Path(file_path)
        module_name = module_path.stem
        
        # Find functions to test
        try:
            tree = ast.parse(code)
            functions = [
                node.name for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
            ]
        except Exception:
            functions = []
        
        if not functions:
            return code
        
        # Generate test file content
        test_code = f'''"""
Tests for {module_name} module.
Auto-generated by evolution system.
"""

import pytest
from unittest.mock import Mock, patch

from {module_path.parent.name}.{module_name} import {", ".join(functions[:3])}


'''
        
        # Generate test stubs for first few functions
        for func in functions[:3]:
            test_code += f'''
def test_{func}_basic():
    """Test basic functionality of {func}."""
    # TODO: Implement test
    pass


def test_{func}_edge_cases():
    """Test edge cases for {func}."""
    # TODO: Implement test
    pass

'''
        
        return test_code
    
    async def _documentation_mutation(self, code: str) -> str:
        """
        Improve code documentation.
        
        Adds or enhances docstrings and comments.
        """
        try:
            tree = ast.parse(code)
            
            class DocstringAdder(ast.NodeTransformer):
                def visit_FunctionDef(self, node):
                    # Add docstring if missing
                    if not ast.get_docstring(node):
                        docstring = f'"""TODO: Add documentation for {node.name}."""'
                        node.body.insert(
                            0,
                            ast.Expr(value=ast.Constant(value=docstring))
                        )
                    return node
                
                def visit_ClassDef(self, node):
                    # Add docstring if missing
                    if not ast.get_docstring(node):
                        docstring = f'"""TODO: Add documentation for {node.name} class."""'
                        node.body.insert(
                            0,
                            ast.Expr(value=ast.Constant(value=docstring))
                        )
                    return node
            
            transformer = DocstringAdder()
            modified_tree = transformer.visit(tree)
            return ast.unparse(modified_tree)
            
        except Exception:
            return code
    
    async def _type_annotation_mutation(self, code: str) -> str:
        """
        Add type annotations to functions.
        
        Infers basic types and adds annotations.
        """
        try:
            tree = ast.parse(code)
            
            class TypeAnnotator(ast.NodeTransformer):
                def visit_FunctionDef(self, node):
                    # Add return type hint if missing
                    if not node.returns:
                        # Simple heuristic: if function name suggests boolean
                        if node.name.startswith(("is_", "has_", "can_", "should_")):
                            node.returns = ast.Name(id="bool", ctx=ast.Load())
                        # If it's a getter
                        elif node.name.startswith("get_"):
                            node.returns = ast.Name(id="Any", ctx=ast.Load())
                    
                    # Add parameter type hints if missing
                    for arg in node.args.args:
                        if not arg.annotation and arg.arg != "self":
                            # Default to Any for now
                            arg.annotation = ast.Name(id="Any", ctx=ast.Load())
                    
                    return node
            
            # Ensure typing import exists
            if "from typing import" not in code:
                code = "from typing import Any, Optional, List, Dict\n" + code
                tree = ast.parse(code)
            
            transformer = TypeAnnotator()
            modified_tree = transformer.visit(tree)
            return ast.unparse(modified_tree)
            
        except Exception:
            return code
    
    async def crossover(
        self,
        parent1: CodeVariant,
        parent2: CodeVariant,
    ) -> CodeVariant:
        """
        Perform crossover between two parent variants.
        
        Args:
            parent1: First parent variant
            parent2: Second parent variant
            
        Returns:
            Offspring variant combining features from both parents
        """
        # Combine code changes from both parents
        code_changes = {}
        
        # Take files from both parents
        all_files = set(parent1.code_changes.keys()) | set(parent2.code_changes.keys())
        
        for file_path in all_files:
            # Randomly choose which parent to inherit from
            if file_path in parent1.code_changes and file_path in parent2.code_changes:
                # Both parents modified this file - choose randomly
                if random.random() < 0.5:
                    code_changes[file_path] = parent1.code_changes[file_path]
                else:
                    code_changes[file_path] = parent2.code_changes[file_path]
            elif file_path in parent1.code_changes:
                # Only parent1 modified this file
                if random.random() < 0.7:  # Higher chance to inherit
                    code_changes[file_path] = parent1.code_changes[file_path]
            elif file_path in parent2.code_changes:
                # Only parent2 modified this file
                if random.random() < 0.7:  # Higher chance to inherit
                    code_changes[file_path] = parent2.code_changes[file_path]
        
        # Combine config changes
        config_changes = {}
        config_changes.update(parent1.config_changes)
        config_changes.update(parent2.config_changes)
        
        # Apply occasional mutation
        if random.random() < self.mutation_rate:
            # Mutate one random file
            if code_changes:
                file_to_mutate = random.choice(list(code_changes.keys()))
                mutation_type = self._select_mutation_type()
                mutated = await self.mutate_file(file_to_mutate, mutation_type)
                if mutated:
                    code_changes[file_to_mutate] = mutated
        
        return CodeVariant(
            id=uuid4(),
            parent_ids=[parent1.id, parent2.id],
            generation=max(parent1.generation, parent2.generation) + 1,
            code_changes=code_changes,
            config_changes=config_changes,
            metadata={
                "crossover_type": "uniform",
                "mutation_applied": random.random() < self.mutation_rate,
            },
        )
    
    def _select_mutation_type(self) -> MutationType:
        """Select a mutation type based on probabilities."""
        # Weight selection by strategy probabilities
        types = list(self.strategies.keys())
        weights = [self.strategies[t].probability for t in types]
        
        return random.choices(types, weights=weights)[0]
    
    def _mutate_config(self, base_config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply mutations to configuration."""
        config = base_config.copy()
        
        # Mutate numeric parameters
        for key, value in config.items():
            if isinstance(value, (int, float)):
                # Apply small random change
                factor = random.uniform(0.8, 1.2)
                config[key] = type(value)(value * factor)
            elif isinstance(value, bool):
                # Occasionally flip boolean
                if random.random() < 0.1:
                    config[key] = not value
        
        # Add new configuration option
        if random.random() < 0.1:
            new_options = [
                ("enable_cache", True),
                ("parallel_workers", random.randint(2, 8)),
                ("timeout_seconds", random.randint(30, 300)),
                ("batch_size", random.randint(10, 100)),
            ]
            key, value = random.choice(new_options)
            config[key] = value
        
        return config