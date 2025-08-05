"""Cost tracking and billing functionality for Hydra."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from hydra.models.db import APIKey, Usage, get_db


@dataclass
class ModelPricing:
    """Pricing configuration for different models."""

    input_cost_per_1k: Decimal
    output_cost_per_1k: Decimal
    provider: str


PROVIDER_PRICING: Dict[str, ModelPricing] = {
    "gpt-4": ModelPricing(
        input_cost_per_1k=Decimal("0.03"),
        output_cost_per_1k=Decimal("0.06"),
        provider="openai"
    ),
    "gpt-4-turbo": ModelPricing(
        input_cost_per_1k=Decimal("0.01"),
        output_cost_per_1k=Decimal("0.03"),
        provider="openai"
    ),
    "gpt-3.5-turbo": ModelPricing(
        input_cost_per_1k=Decimal("0.001"),
        output_cost_per_1k=Decimal("0.002"),
        provider="openai"
    ),
    "claude-3-opus": ModelPricing(
        input_cost_per_1k=Decimal("0.015"),
        output_cost_per_1k=Decimal("0.075"),
        provider="anthropic"
    ),
    "claude-3-sonnet": ModelPricing(
        input_cost_per_1k=Decimal("0.003"),
        output_cost_per_1k=Decimal("0.015"),
        provider="anthropic"
    ),
    "claude-3-haiku": ModelPricing(
        input_cost_per_1k=Decimal("0.00025"),
        output_cost_per_1k=Decimal("0.00125"),
        provider="anthropic"
    ),
}


@dataclass
class TokenUsage:
    """Token usage information."""

    input_tokens: int
    output_tokens: int
    model: str

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class CostBreakdown:
    """Cost breakdown for a request."""

    input_cost: Decimal
    output_cost: Decimal
    total_cost: Decimal
    model: str
    provider: str
    tokens_used: int


class TokenCounter:
    """Token counting utilities."""

    @staticmethod
    def count_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
        """Estimate token count for text."""
        # Rough estimation: ~4 characters per token
        return len(text) // 4

    @staticmethod
    def count_request_tokens(prompt: str, response: str, model: str) -> TokenUsage:
        """Count tokens for a complete request/response."""
        input_tokens = TokenCounter.count_tokens(prompt, model)
        output_tokens = TokenCounter.count_tokens(response, model)
        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model
        )


class CostCalculator:
    """Calculate costs based on token usage and model pricing."""

    @staticmethod
    def calculate_cost(token_usage: TokenUsage) -> CostBreakdown:
        """Calculate cost for token usage."""
        model_key = token_usage.model.lower()
        pricing = PROVIDER_PRICING.get(model_key)

        if not pricing:
            # Default pricing for unknown models
            pricing = ModelPricing(
                input_cost_per_1k=Decimal("0.001"),
                output_cost_per_1k=Decimal("0.002"),
                provider="unknown"
            )

        input_cost = (
            Decimal(token_usage.input_tokens) / 1000
        ) * pricing.input_cost_per_1k
        output_cost = (
            Decimal(token_usage.output_tokens) / 1000
        ) * pricing.output_cost_per_1k
        total_cost = input_cost + output_cost

        return CostBreakdown(
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=total_cost,
            model=token_usage.model,
            provider=pricing.provider,
            tokens_used=token_usage.total_tokens
        )


class BillingService:
    """Service for tracking costs and generating billing reports."""

    def __init__(self, db_session: Optional[Session] = None):
        self.db = db_session or get_db()

    def track_usage(self, api_key_id: int, endpoint: str,
                   prompt: str, response: str, model: str,
                   task_id: Optional[str] = None) -> CostBreakdown:
        """Track usage and calculate costs for a request."""
        token_usage = TokenCounter.count_request_tokens(prompt, response, model)
        cost_breakdown = CostCalculator.calculate_cost(token_usage)

        # Store usage in database with detailed cost tracking
        usage_record = Usage(
            api_key_id=api_key_id,
            endpoint=endpoint,
            timestamp=datetime.utcnow(),
            tokens_used=token_usage.total_tokens,
            task_id=task_id,
            model=model,
            provider=cost_breakdown.provider,
            input_tokens=token_usage.input_tokens,
            output_tokens=token_usage.output_tokens,
            cost=cost_breakdown.total_cost
        )

        self.db.add(usage_record)
        self.db.commit()

        return cost_breakdown

    def get_usage_for_api_key(self, api_key: str,
                             start_date: Optional[datetime] = None,
                             end_date: Optional[datetime] = None) -> List[Dict]:
        """Get usage records for an API key."""
        query = (self.db.query(Usage)
                .join(APIKey)
                .filter(APIKey.key == api_key))

        if start_date:
            query = query.filter(Usage.timestamp >= start_date)
        if end_date:
            query = query.filter(Usage.timestamp <= end_date)

        usage_records = query.order_by(desc(Usage.timestamp)).all()

        results = []
        for record in usage_records:
            # Use stored cost if available, otherwise estimate
            if record.cost is not None:
                cost_value = float(record.cost)
            else:
                # Fallback for legacy records
                token_usage = TokenUsage(
                    input_tokens=record.input_tokens or record.tokens_used // 2,
                    output_tokens=record.output_tokens or record.tokens_used // 2,
                    model=record.model or "gpt-3.5-turbo"
                )
                cost = CostCalculator.calculate_cost(token_usage)
                cost_value = float(cost.total_cost)

            results.append({
                "timestamp": record.timestamp,
                "endpoint": record.endpoint,
                "tokens_used": record.tokens_used,
                "estimated_cost": cost_value,
                "task_id": record.task_id,
                "model": record.model,
                "provider": record.provider
            })

        return results

    def get_monthly_report(self, api_key: str, year: int, month: int) -> Dict:
        """Generate monthly usage report for an API key."""
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)

        usage_records = self.get_usage_for_api_key(api_key, start_date, end_date)

        total_tokens = sum(record["tokens_used"] for record in usage_records)
        total_cost = sum(record["estimated_cost"] for record in usage_records)

        endpoint_breakdown = {}
        for record in usage_records:
            endpoint = record["endpoint"]
            if endpoint not in endpoint_breakdown:
                endpoint_breakdown[endpoint] = {
                    "requests": 0,
                    "tokens": 0,
                    "cost": 0.0
                }
            endpoint_breakdown[endpoint]["requests"] += 1
            endpoint_breakdown[endpoint]["tokens"] += record["tokens_used"]
            endpoint_breakdown[endpoint]["cost"] += record["estimated_cost"]

        return {
            "api_key": api_key,
            "period": f"{year}-{month:02d}",
            "total_requests": len(usage_records),
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "endpoint_breakdown": endpoint_breakdown,
            "usage_records": usage_records
        }

    def check_usage_limits(
        self, api_key: str, monthly_limit: Optional[Decimal] = None
    ) -> Dict:
        """Check if API key is approaching usage limits."""
        current_date = datetime.now()
        monthly_report = self.get_monthly_report(
            api_key, current_date.year, current_date.month
        )

        current_cost = Decimal(str(monthly_report["total_cost"]))

        alerts = []
        if monthly_limit:
            usage_percentage = (current_cost / monthly_limit) * 100

            if usage_percentage >= 90:
                alerts.append({
                    "level": "critical",
                    "message": (
                        f"Usage at {usage_percentage:.1f}% of monthly limit"
                    )
                })
            elif usage_percentage >= 75:
                alerts.append({
                    "level": "warning",
                    "message": (
                        f"Usage at {usage_percentage:.1f}% of monthly limit"
                    )
                })

        return {
            "current_cost": float(current_cost),
            "monthly_limit": float(monthly_limit) if monthly_limit else None,
            "alerts": alerts
        }


    def send_usage_alert(self, api_key: str, alert_info: Dict) -> None:
        """Send usage alert (placeholder for notification system)."""
        # This would integrate with a notification system
        # For now, just log the alert
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(
            f"Usage alert for API key {api_key[:8]}...: "
            f"{alert_info['level']} - {alert_info['message']}"
        )


def get_billing_service() -> BillingService:
    """Get billing service instance."""
    return BillingService()

