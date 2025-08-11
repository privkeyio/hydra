"""Abstract interface for the Action Executor system."""

from abc import ABC, abstractmethod
from typing import List, Optional, Protocol, runtime_checkable

from .types import Action, ActionBatch, ActionResult, ExecutionContext


class ActionExecutor(ABC):
    """Abstract base class for action executors.

    This defines the interface that all action executors must implement
    to ensure consistent behavior across different execution strategies.
    """

    def __init__(self, context: ExecutionContext) -> None:
        """Initialize the executor with an execution context.

        Args:
            context: The execution context containing configuration

        """
        self.context = context
        self.executed_actions: List[ActionResult] = []
        self.rollback_stack: List[ActionResult] = []

    @abstractmethod
    def execute(self, action: Action) -> ActionResult:
        """Execute a single action.

        Args:
            action: The action to execute

        Returns:
            Result of the execution

        Raises:
            ExecutionError: If the action fails and cannot be recovered

        """
        pass

    @abstractmethod
    def validate(self, action: Action) -> bool:
        """Validate an action before execution.

        Args:
            action: The action to validate

        Returns:
            True if the action is valid and can be executed

        Raises:
            ValidationError: If the action is invalid

        """
        pass

    def execute_batch(self, batch: ActionBatch) -> List[ActionResult]:
        """Execute a batch of actions.

        Args:
            batch: The batch of actions to execute

        Returns:
            List of results for each action

        """
        results = []
        execution_order = batch.get_execution_order()

        for idx in execution_order:
            action = batch.actions[idx]

            # Validate before execution
            if not self.validate(action):
                result = ActionResult(
                    action=action,
                    success=False,
                    error="Action failed validation",
                )
                results.append(result)
                if self.context.rollback_on_failure:
                    self.rollback()
                    break
                continue

            # Execute the action
            result = self.execute(action)
            results.append(result)

            # Track for potential rollback
            if result.success and action.requires_rollback:
                self.rollback_stack.append(result)

            # Handle failure
            if not result.success:
                if self.context.rollback_on_failure:
                    self.rollback()
                    break

        return results

    def rollback(self) -> None:
        """Rollback executed actions in reverse order.

        This method attempts to undo actions that have been
        successfully executed, using the rollback data stored
        in each ActionResult.
        """
        while self.rollback_stack:
            result = self.rollback_stack.pop()
            try:
                self._perform_rollback(result)
            except Exception as e:
                # Log rollback failure but continue
                print(f"Rollback failed for action {result.action.type}: {e}")

    @abstractmethod
    def _perform_rollback(self, result: ActionResult) -> None:
        """Perform rollback for a specific action result.

        Args:
            result: The action result to rollback

        Raises:
            RollbackError: If rollback fails

        """
        pass

    def can_execute(self, action: Action) -> bool:
        """Check if an action can be executed in the current context.

        Args:
            action: The action to check

        Returns:
            True if the action can be executed

        """
        # Check if dry run mode
        if self.context.dry_run and not action.is_safe:
            return False

        # Additional checks can be added here
        return True


@runtime_checkable
class ActionParser(Protocol):
    """Protocol for parsing LLM responses into actions.

    Implementations should handle different response formats
    and extract structured actions from text.
    """

    def parse(self, response: str) -> List[Action]:
        """Parse an LLM response into a list of actions.

        Args:
            response: The raw LLM response text

        Returns:
            List of parsed actions

        Raises:
            ParseError: If the response cannot be parsed

        """
        ...

    def supports_format(self, response: str) -> bool:
        """Check if this parser can handle the response format.

        Args:
            response: The response to check

        Returns:
            True if this parser can handle the format

        """
        ...


@runtime_checkable
class ActionValidator(Protocol):
    """Protocol for validating actions before execution.

    Validators ensure actions are safe and appropriate
    for the current context.
    """

    def validate(self, action: Action, context: ExecutionContext) -> bool:
        """Validate an action in the given context.

        Args:
            action: The action to validate
            context: The execution context

        Returns:
            True if the action is valid

        Raises:
            ValidationError: If validation fails with details

        """
        ...

    def get_validation_errors(
        self, action: Action, context: ExecutionContext
    ) -> List[str]:
        """Get detailed validation errors for an action.

        Args:
            action: The action to validate
            context: The execution context

        Returns:
            List of validation error messages

        """
        ...


class CompositeExecutor(ActionExecutor):
    """Executor that delegates to specialized executors based on action type.

    This allows different action types to be handled by specialized
    implementations while presenting a unified interface.
    """

    def __init__(
        self,
        context: ExecutionContext,
        executors: Optional[dict] = None,
    ) -> None:
        """Initialize with a mapping of action types to executors.

        Args:
            context: The execution context
            executors: Optional mapping of ActionType to executor instances

        """
        super().__init__(context)
        self.executors = executors or {}

    def register_executor(
        self, action_type: type, executor: ActionExecutor
    ) -> None:
        """Register an executor for a specific action type.

        Args:
            action_type: The action type to handle
            executor: The executor instance

        """
        self.executors[action_type] = executor

    def execute(self, action: Action) -> ActionResult:
        """Execute an action using the appropriate specialized executor.

        Args:
            action: The action to execute

        Returns:
            Result of the execution

        Raises:
            ExecutionError: If no executor is registered for the action type

        """
        executor = self.executors.get(action.type)
        if not executor:
            return ActionResult(
                action=action,
                success=False,
                error=f"No executor registered for action type: {action.type}",
            )

        return executor.execute(action)

    def validate(self, action: Action) -> bool:
        """Validate an action using the appropriate specialized executor.

        Args:
            action: The action to validate

        Returns:
            True if the action is valid

        """
        executor = self.executors.get(action.type)
        if not executor:
            return False

        return executor.validate(action)

    def _perform_rollback(self, result: ActionResult) -> None:
        """Perform rollback using the appropriate specialized executor.

        Args:
            result: The action result to rollback

        """
        executor = self.executors.get(result.action.type)
        if executor:
            executor._perform_rollback(result)

