"""Token usage tracking and budget management for LLM providers."""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, Optional, Tuple

import tiktoken
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.declarative import declarative_base

from hydra.cache import get_cache
# Delayed import to avoid circular imports
# from hydra.dashboard.database import get_db_manager

logger = logging.getLogger(__name__)

Base = declarative_base()


class Provider(str, Enum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    VENICE = "venice"
    MOCK = "mock"


@dataclass
class TokenCost:
    """Token cost configuration for different models."""

    provider: Provider
    model: str
    input_cost_per_1k: float
    output_cost_per_1k: float
    context_window: int = 200000
    max_output: int = 8192


# Pricing as of January 2025
TOKEN_COSTS = {
    "claude-3-5-sonnet-20241022": TokenCost(
        Provider.ANTHROPIC, "claude-3-5-sonnet-20241022", 0.003, 0.015, 200000, 8192
    ),
    "claude-opus-4-1-20250805": TokenCost(
        Provider.ANTHROPIC, "claude-opus-4-1-20250805", 0.015, 0.075, 200000, 4096
    ),
    "claude-3-sonnet-20240229": TokenCost(
        Provider.ANTHROPIC, "claude-3-sonnet-20240229", 0.003, 0.015, 200000, 4096
    ),
    "gpt-4-turbo-preview": TokenCost(
        Provider.OPENAI, "gpt-4-turbo-preview", 0.01, 0.03, 128000, 4096
    ),
    "gpt-4": TokenCost(
        Provider.OPENAI, "gpt-4", 0.03, 0.06, 8192, 4096
    ),
    "gpt-3.5-turbo": TokenCost(
        Provider.OPENAI, "gpt-3.5-turbo", 0.0005, 0.0015, 16385, 4096
    ),
}


class TokenUsage(Base):
    """Database model for token usage tracking."""

    __tablename__ = "token_usage"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    provider = Column(String(50), nullable=False, index=True)
    model = Column(String(100), nullable=False)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)
    total_tokens = Column(Integer, nullable=False)
    input_cost = Column(Float, nullable=False)
    output_cost = Column(Float, nullable=False)
    total_cost = Column(Float, nullable=False)
    prompt = Column(Text, nullable=True)
    response = Column(Text, nullable=True)
    request_metadata = Column(Text, nullable=True)  # JSON string


@dataclass
class UsageMetrics:
    """Container for usage metrics."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0
    request_count: int = 0
    by_model: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    by_provider: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def add_usage(self, provider: str, model: str, input_tokens: int,
                  output_tokens: int, cost: float):
        """Add usage to metrics."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost += cost
        self.request_count += 1

        # Update by model
        if model not in self.by_model:
            self.by_model[model] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0,
                "requests": 0
            }
        self.by_model[model]["input_tokens"] += input_tokens
        self.by_model[model]["output_tokens"] += output_tokens
        self.by_model[model]["cost"] += cost
        self.by_model[model]["requests"] += 1

        # Update by provider
        if provider not in self.by_provider:
            self.by_provider[provider] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0,
                "requests": 0
            }
        self.by_provider[provider]["input_tokens"] += input_tokens
        self.by_provider[provider]["output_tokens"] += output_tokens
        self.by_provider[provider]["cost"] += cost
        self.by_provider[provider]["requests"] += 1


class TokenTracker:
    """Tracks token usage and manages budgets for LLM operations."""

    def __init__(self, budget_limit: Optional[float] = None,
                 warning_threshold: float = 0.8):
        """Initialize token tracker.
        
        Args:
            budget_limit: Maximum budget in USD (None for unlimited)
            warning_threshold: Fraction of budget to trigger warning (0.8 = 80%)

        """
        self.budget_limit = budget_limit or float(
            os.getenv("TOKEN_BUDGET_LIMIT", "100.0")
        )
        self.warning_threshold = warning_threshold
        self._current_usage = UsageMetrics()
        self._cache = get_cache()
        # Delayed import to avoid circular imports
        try:
            from hydra.dashboard.database import get_db_manager
            self._db_manager = get_db_manager()
        except ImportError:
            self._db_manager = None
        self._warned = False

        # Initialize tokenizers for different providers
        self._tokenizers = {}
        self._init_tokenizers()

        logger.info(f"Token tracker initialized with budget: ${self.budget_limit:.2f}")

    def _init_tokenizers(self):
        """Initialize tokenizers for token counting."""
        try:
            # Claude uses cl100k_base encoding similar to GPT
            self._tokenizers["anthropic"] = tiktoken.get_encoding("cl100k_base")
            self._tokenizers["openai"] = tiktoken.get_encoding("cl100k_base")
            self._tokenizers["default"] = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.warning(f"Failed to initialize tokenizers: {e}")
            self._tokenizers["default"] = None

    def count_tokens(self, text: str, provider: Provider = Provider.ANTHROPIC) -> int:
        """Count tokens in text for given provider.
        
        Args:
            text: Text to count tokens for
            provider: LLM provider
            
        Returns:
            Number of tokens

        """
        if not text:
            return 0

        tokenizer = self._tokenizers.get(
            provider.value, self._tokenizers.get("default")
        )

        if tokenizer:
            try:
                return len(tokenizer.encode(text))
            except Exception as e:
                logger.warning(f"Token counting failed: {e}")

        # Fallback: estimate 4 characters per token
        return len(text) // 4

    def calculate_cost(self, model: str, input_tokens: int,
                      output_tokens: int) -> Tuple[float, float, float]:
        """Calculate cost for token usage.
        
        Args:
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            
        Returns:
            Tuple of (input_cost, output_cost, total_cost) in USD

        """
        cost_info = TOKEN_COSTS.get(model)

        if not cost_info:
            # Default pricing for unknown models
            logger.warning(f"Unknown model {model}, using default pricing")
            input_cost = input_tokens * 0.001 / 1000  # $0.001 per 1k tokens
            output_cost = output_tokens * 0.002 / 1000  # $0.002 per 1k tokens
        else:
            input_cost = input_tokens * cost_info.input_cost_per_1k / 1000
            output_cost = output_tokens * cost_info.output_cost_per_1k / 1000

        total_cost = input_cost + output_cost
        return input_cost, output_cost, total_cost

    def track_usage(self, provider: str, model: str, prompt: str,
                   response: str, ticket_id: Optional[int] = None,
                   session_id: Optional[int] = None,
                   metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Track token usage for a request.
        
        Args:
            provider: Provider name
            model: Model name
            prompt: Input prompt
            response: Model response
            ticket_id: Optional ticket ID
            session_id: Optional session ID
            metadata: Optional metadata
            
        Returns:
            Usage statistics dictionary

        """
        # Count tokens
        input_tokens = self.count_tokens(prompt, Provider(provider))
        output_tokens = self.count_tokens(response, Provider(provider))
        total_tokens = input_tokens + output_tokens

        # Calculate costs
        input_cost, output_cost, total_cost = self.calculate_cost(
            model, input_tokens, output_tokens
        )

        # Update current usage
        self._current_usage.add_usage(
            provider, model, input_tokens, output_tokens, total_cost
        )

        # Store in database
        try:
            with self._db_manager.get_session() as session:
                usage_record = TokenUsage(
                    provider=provider,
                    model=model,
                    ticket_id=ticket_id,
                    session_id=session_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    input_cost=input_cost,
                    output_cost=output_cost,
                    total_cost=total_cost,
                    # Truncate long prompts
                    prompt=prompt[:5000] if len(prompt) > 5000 else prompt,
                    response=response[:5000] if len(response) > 5000 else response,
                    request_metadata=json.dumps(metadata) if metadata else None
                )
                session.add(usage_record)
                session.commit()
        except Exception as e:
            logger.error(f"Failed to store token usage: {e}")

        # Check budget and warn if needed
        self._check_budget_warning()

        # Cache usage stats
        cache_key = f"token_usage:{datetime.utcnow().strftime('%Y%m%d')}"
        self._cache.set_api_response(
            "token_usage",
            cache_key,
            self._current_usage.__dict__,
            ttl=3600
        )

        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "input_cost": input_cost,
            "output_cost": output_cost,
            "total_cost": total_cost,
            "cumulative_cost": self._current_usage.total_cost,
            "budget_remaining": self.budget_limit - self._current_usage.total_cost,
            "budget_percentage": (
                self._current_usage.total_cost / self.budget_limit * 100
                if self.budget_limit > 0 else 0
            )
        }

    def _check_budget_warning(self):
        """Check if budget warning should be issued."""
        if self._warned or not self.budget_limit:
            return

        usage_percentage = self._current_usage.total_cost / self.budget_limit

        if usage_percentage >= self.warning_threshold:
            self._warned = True
            remaining = self.budget_limit - self._current_usage.total_cost
            logger.warning(
                f"⚠️  Token budget warning: {usage_percentage:.1%} used "
                f"(${self._current_usage.total_cost:.2f} of ${self.budget_limit:.2f}). "
                f"${remaining:.2f} remaining."
            )

    def check_budget_available(self, estimated_tokens: int,
                              model: str) -> Tuple[bool, str]:
        """Check if budget is available for estimated usage.
        
        Args:
            estimated_tokens: Estimated total tokens
            model: Model to use
            
        Returns:
            Tuple of (is_available, message)

        """
        if not self.budget_limit:
            return True, "No budget limit set"

        # Estimate cost (assuming 80% input, 20% output)
        input_tokens = int(estimated_tokens * 0.8)
        output_tokens = int(estimated_tokens * 0.2)
        _, _, estimated_cost = self.calculate_cost(model, input_tokens, output_tokens)

        remaining = self.budget_limit - self._current_usage.total_cost

        if estimated_cost > remaining:
            return False, (
                f"Insufficient budget: ${estimated_cost:.2f} needed, "
                f"${remaining:.2f} available"
            )

        return True, f"Budget available: ${remaining:.2f}"

    def get_usage_report(self, start_date: Optional[datetime] = None,
                        end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """Generate usage report for specified period.
        
        Args:
            start_date: Start of period (default: 24 hours ago)
            end_date: End of period (default: now)
            
        Returns:
            Detailed usage report

        """
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=1)
        if not end_date:
            end_date = datetime.utcnow()

        report = {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "summary": {
                "total_requests": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_tokens": 0,
                "total_cost": 0.0
            },
            "by_provider": {},
            "by_model": {},
            "by_ticket": {},
            "hourly_usage": [],
            "top_expensive_requests": []
        }

        try:
            with self._db_manager.get_session() as session:
                # Query usage data
                usage_data = session.query(TokenUsage).filter(
                    TokenUsage.timestamp >= start_date,
                    TokenUsage.timestamp <= end_date
                ).all()

                for usage in usage_data:
                    # Update summary
                    report["summary"]["total_requests"] += 1
                    report["summary"]["total_input_tokens"] += usage.input_tokens
                    report["summary"]["total_output_tokens"] += usage.output_tokens
                    report["summary"]["total_tokens"] += usage.total_tokens
                    report["summary"]["total_cost"] += usage.total_cost

                    # By provider
                    if usage.provider not in report["by_provider"]:
                        report["by_provider"][usage.provider] = {
                            "requests": 0,
                            "tokens": 0,
                            "cost": 0.0
                        }
                    report["by_provider"][usage.provider]["requests"] += 1
                    report["by_provider"][usage.provider]["tokens"] += (
                        usage.total_tokens
                    )
                    report["by_provider"][usage.provider]["cost"] += usage.total_cost

                    # By model
                    if usage.model not in report["by_model"]:
                        report["by_model"][usage.model] = {
                            "requests": 0,
                            "tokens": 0,
                            "cost": 0.0
                        }
                    report["by_model"][usage.model]["requests"] += 1
                    report["by_model"][usage.model]["tokens"] += usage.total_tokens
                    report["by_model"][usage.model]["cost"] += usage.total_cost

                    # By ticket
                    if usage.ticket_id:
                        ticket_key = f"ticket_{usage.ticket_id}"
                        if ticket_key not in report["by_ticket"]:
                            report["by_ticket"][ticket_key] = {
                                "requests": 0,
                                "tokens": 0,
                                "cost": 0.0
                            }
                        report["by_ticket"][ticket_key]["requests"] += 1
                        report["by_ticket"][ticket_key]["tokens"] += usage.total_tokens
                        report["by_ticket"][ticket_key]["cost"] += usage.total_cost

                # Get top expensive requests
                top_requests = session.query(TokenUsage).filter(
                    TokenUsage.timestamp >= start_date,
                    TokenUsage.timestamp <= end_date
                ).order_by(TokenUsage.total_cost.desc()).limit(10).all()

                report["top_expensive_requests"] = [
                    {
                        "timestamp": req.timestamp.isoformat(),
                        "model": req.model,
                        "tokens": req.total_tokens,
                        "cost": req.total_cost,
                        "ticket_id": req.ticket_id
                    }
                    for req in top_requests
                ]

        except Exception as e:
            logger.error(f"Failed to generate usage report: {e}")

        return report

    def export_usage_csv(self, filepath: str, start_date: Optional[datetime] = None,
                        end_date: Optional[datetime] = None):
        """Export usage data to CSV file.
        
        Args:
            filepath: Path to output CSV file
            start_date: Start of period
            end_date: End of period

        """
        import csv

        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()

        try:
            with self._db_manager.get_session() as session:
                usage_data = session.query(TokenUsage).filter(
                    TokenUsage.timestamp >= start_date,
                    TokenUsage.timestamp <= end_date
                ).order_by(TokenUsage.timestamp).all()

                with open(filepath, 'w', newline='') as csvfile:
                    fieldnames = [
                        'timestamp', 'provider', 'model', 'ticket_id',
                        'input_tokens', 'output_tokens', 'total_tokens',
                        'input_cost', 'output_cost', 'total_cost'
                    ]
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                    writer.writeheader()
                    for usage in usage_data:
                        writer.writerow({
                            'timestamp': usage.timestamp.isoformat(),
                            'provider': usage.provider,
                            'model': usage.model,
                            'ticket_id': usage.ticket_id,
                            'input_tokens': usage.input_tokens,
                            'output_tokens': usage.output_tokens,
                            'total_tokens': usage.total_tokens,
                            'input_cost': f"{usage.input_cost:.6f}",
                            'output_cost': f"{usage.output_cost:.6f}",
                            'total_cost': f"{usage.total_cost:.6f}"
                        })

                logger.info(f"Exported {len(usage_data)} usage records to {filepath}")

        except Exception as e:
            logger.error(f"Failed to export usage data: {e}")

    def reset_budget(self):
        """Reset budget tracking (e.g., for monthly reset)."""
        self._current_usage = UsageMetrics()
        self._warned = False
        logger.info("Token budget reset")

    def get_current_usage(self) -> Dict[str, Any]:
        """Get current usage statistics.
        
        Returns:
            Current usage metrics

        """
        return {
            "total_input_tokens": self._current_usage.total_input_tokens,
            "total_output_tokens": self._current_usage.total_output_tokens,
            "total_tokens": self._current_usage.total_input_tokens +
                          self._current_usage.total_output_tokens,
            "total_cost": self._current_usage.total_cost,
            "request_count": self._current_usage.request_count,
            "budget_limit": self.budget_limit,
            "budget_remaining": self.budget_limit - self._current_usage.total_cost,
            "budget_percentage": (
                self._current_usage.total_cost / self.budget_limit * 100
                if self.budget_limit > 0 else 0
            ),
            "by_model": self._current_usage.by_model,
            "by_provider": self._current_usage.by_provider
        }


# Global token tracker instance
_token_tracker: Optional[TokenTracker] = None


def get_token_tracker(budget_limit: Optional[float] = None) -> TokenTracker:
    """Get or create global token tracker instance.
    
    Args:
        budget_limit: Optional budget limit override
        
    Returns:
        TokenTracker instance

    """
    global _token_tracker
    if _token_tracker is None:
        _token_tracker = TokenTracker(budget_limit=budget_limit)
    return _token_tracker


def reset_token_tracker(budget_limit: Optional[float] = None) -> TokenTracker:
    """Reset global token tracker instance.
    
    Args:
        budget_limit: Optional new budget limit
        
    Returns:
        New TokenTracker instance

    """
    global _token_tracker
    _token_tracker = TokenTracker(budget_limit=budget_limit)
    return _token_tracker
