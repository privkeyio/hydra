"""Integration hooks for boss agent with ticket workflow."""

import logging
from typing import Any, Callable, Dict, Optional

from .boss_agent import (
    BossAgent,
    StrictnessLevel,
    VerificationConfig,
    VerificationStatus,
)

logger = logging.getLogger(__name__)


class VerificationHook:
    """Hook for integrating boss agent verification into ticket workflow."""

    def __init__(
        self,
        config: Optional[VerificationConfig] = None,
        auto_retry: bool = True,
        verbose: bool = False
    ):
        self.boss = BossAgent(config or VerificationConfig())
        self.auto_retry = auto_retry
        self.verbose = verbose
        self.executor_callback = None

    def set_executor_callback(self, callback: Callable):
        """Set the callback for re-executing tickets."""
        self.executor_callback = callback

    def post_execution_hook(
        self,
        ticket_id: str,
        ticket_data: Dict[str, Any],
        project_path: str,
        execution_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Hook called after ticket execution completes.
        
        Returns verification result and potentially triggers re-execution.
        """
        logger.info(f"Running boss agent verification for ticket {ticket_id}")

        # Run verification
        verification_result = self.boss.verify_ticket_completion(
            ticket_id,
            ticket_data,
            project_path,
            context=execution_result
        )

        # Handle result
        if verification_result.status == VerificationStatus.PASS:
            logger.info(f"Ticket {ticket_id} PASSED verification with score {verification_result.score:.1f}")
            return {
                'verified': True,
                'score': verification_result.score,
                'status': 'VERIFIED',
                'message': f"Verification passed with score {verification_result.score:.1f}"
            }

        elif verification_result.status == VerificationStatus.FAIL:
            logger.warning(f"Ticket {ticket_id} FAILED verification")

            if self.verbose:
                print(f"\n❌ Verification FAILED for ticket {ticket_id}")
                print(f"Score: {verification_result.score:.1f}")
                print("\nFailure reasons:")
                for reason in verification_result.failure_reasons:
                    print(f"  - {reason}")

                if verification_result.suggestions:
                    print("\nSuggestions:")
                    for suggestion in verification_result.suggestions:
                        print(f"  - {suggestion}")

            # Trigger re-execution if enabled and callback available
            if self.auto_retry and self.executor_callback:
                retry_result = self.boss.trigger_re_execution(
                    ticket_id,
                    verification_result,
                    self.executor_callback
                )

                if retry_result is None:
                    logger.info(f"Re-execution triggered for ticket {ticket_id}")
                    return {
                        'verified': False,
                        'score': verification_result.score,
                        'status': 'RETRYING',
                        'message': 'Verification failed, retrying execution',
                        'failures': verification_result.failure_reasons
                    }

            return {
                'verified': False,
                'score': verification_result.score,
                'status': 'FAILED',
                'message': 'Verification failed',
                'failures': verification_result.failure_reasons,
                'suggestions': verification_result.suggestions
            }

        else:  # ERROR status
            logger.error(f"Verification error for ticket {ticket_id}")
            return {
                'verified': False,
                'score': 0.0,
                'status': 'ERROR',
                'message': 'Verification encountered an error',
                'failures': verification_result.failure_reasons
            }

    def pre_execution_hook(
        self,
        ticket_id: str,
        ticket_data: Dict[str, Any],
        retry_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Hook called before ticket execution starts.
        
        Can inject failure context from previous attempts.
        """
        if retry_context:
            logger.info(f"Injecting retry context for ticket {ticket_id}")

            # Enhance ticket data with failure context
            enhanced_data = ticket_data.copy()

            # Add context to description
            if retry_context.get('previous_failures'):
                enhanced_data['retry_context'] = {
                    'attempt': retry_context.get('retry_number', 1),
                    'previous_failures': retry_context['previous_failures'],
                    'must_fix': retry_context.get('failed_criteria', []),
                    'suggestions': retry_context.get('suggestions', [])
                }

                # Prepend context to description
                original_desc = enhanced_data.get('description', '')
                context_desc = f"RETRY ATTEMPT {retry_context['retry_number']}:\n"
                context_desc += "Previous attempt failed. MUST fix:\n"
                for failure in retry_context['previous_failures']:
                    context_desc += f"- {failure}\n"
                context_desc += f"\n{original_desc}"

                enhanced_data['description'] = context_desc

            return enhanced_data

        return ticket_data


def register_verification_hooks(workflow_manager: Any, config: Optional[VerificationConfig] = None):
    """Register boss agent hooks with the ticket workflow manager.
    
    Usage:
        from hydra.verification_system.workflow_hooks import register_verification_hooks
        from hydra.ticket_workflow import WorkflowManager
        
        workflow = WorkflowManager()
        register_verification_hooks(workflow)
    """
    hook = VerificationHook(config)

    # Register post-execution hook
    if hasattr(workflow_manager, 'register_post_execution_hook'):
        workflow_manager.register_post_execution_hook(hook.post_execution_hook)

    # Register pre-execution hook
    if hasattr(workflow_manager, 'register_pre_execution_hook'):
        workflow_manager.register_pre_execution_hook(hook.pre_execution_hook)

    # Set executor callback if workflow has execute method
    if hasattr(workflow_manager, 'execute_ticket'):
        hook.set_executor_callback(workflow_manager.execute_ticket)

    logger.info("Boss agent verification hooks registered with workflow")

    return hook


def create_standalone_verifier(
    strictness: str = "strict",
    min_coverage: float = 80.0,
    min_quality: float = 7.0
) -> BossAgent:
    """Create a standalone boss agent for manual verification.
    
    Usage:
        from hydra.verification_system.workflow_hooks import create_standalone_verifier
        
        verifier = create_standalone_verifier(strictness="brutal")
        result = verifier.verify_ticket_completion(
            ticket_id="001",
            ticket_data=ticket,
            project_path="."
        )
    """
    strictness_map = {
        'lenient': StrictnessLevel.LENIENT,
        'moderate': StrictnessLevel.MODERATE,
        'strict': StrictnessLevel.STRICT,
        'brutal': StrictnessLevel.BRUTAL
    }

    config = VerificationConfig(
        strictness=strictness_map.get(strictness, StrictnessLevel.STRICT),
        min_test_coverage=min_coverage,
        min_quality_score=min_quality
    )

    return BossAgent(config)
