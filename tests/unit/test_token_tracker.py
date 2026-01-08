"""Unit tests for token tracking functionality."""

import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

from hydra.token_tracker import (
    Provider,
    TokenCost,
    TokenTracker,
    UsageMetrics,
    get_token_tracker,
    reset_token_tracker,
)


class TestTokenCost:
    """Test token cost configuration."""

    def test_token_cost_initialization(self):
        """Test TokenCost dataclass initialization."""
        cost = TokenCost(
            provider=Provider.ANTHROPIC,
            model="claude-3-5-sonnet",
            input_cost_per_1k=0.003,
            output_cost_per_1k=0.015,
            context_window=200000,
            max_output=8192,
        )

        assert cost.provider == Provider.ANTHROPIC
        assert cost.model == "claude-3-5-sonnet"
        assert cost.input_cost_per_1k == 0.003
        assert cost.output_cost_per_1k == 0.015
        assert cost.context_window == 200000
        assert cost.max_output == 8192


class TestUsageMetrics:
    """Test usage metrics tracking."""

    def test_usage_metrics_initialization(self):
        """Test UsageMetrics initialization."""
        metrics = UsageMetrics()

        assert metrics.total_input_tokens == 0
        assert metrics.total_output_tokens == 0
        assert metrics.total_cost == 0.0
        assert metrics.request_count == 0
        assert metrics.by_model == {}
        assert metrics.by_provider == {}

    def test_add_usage(self):
        """Test adding usage to metrics."""
        metrics = UsageMetrics()

        metrics.add_usage(
            provider="anthropic",
            model="claude-3-5-sonnet",
            input_tokens=1000,
            output_tokens=500,
            cost=0.01,
        )

        assert metrics.total_input_tokens == 1000
        assert metrics.total_output_tokens == 500
        assert metrics.total_cost == 0.01
        assert metrics.request_count == 1

        assert "claude-3-5-sonnet" in metrics.by_model
        assert metrics.by_model["claude-3-5-sonnet"]["input_tokens"] == 1000
        assert metrics.by_model["claude-3-5-sonnet"]["output_tokens"] == 500
        assert metrics.by_model["claude-3-5-sonnet"]["cost"] == 0.01
        assert metrics.by_model["claude-3-5-sonnet"]["requests"] == 1

        assert "anthropic" in metrics.by_provider
        assert metrics.by_provider["anthropic"]["input_tokens"] == 1000
        assert metrics.by_provider["anthropic"]["output_tokens"] == 500
        assert metrics.by_provider["anthropic"]["cost"] == 0.01
        assert metrics.by_provider["anthropic"]["requests"] == 1

    def test_add_multiple_usage(self):
        """Test adding multiple usage records."""
        metrics = UsageMetrics()

        # Add first usage
        metrics.add_usage("anthropic", "claude-3-5-sonnet", 1000, 500, 0.01)

        # Add second usage for same model
        metrics.add_usage("anthropic", "claude-3-5-sonnet", 2000, 1000, 0.02)

        # Add usage for different model
        metrics.add_usage("openai", "gpt-4", 500, 250, 0.005)

        assert metrics.total_input_tokens == 3500
        assert metrics.total_output_tokens == 1750
        assert abs(metrics.total_cost - 0.035) < 0.0001  # Allow for float precision
        assert metrics.request_count == 3

        assert metrics.by_model["claude-3-5-sonnet"]["input_tokens"] == 3000
        assert metrics.by_model["claude-3-5-sonnet"]["requests"] == 2

        assert metrics.by_model["gpt-4"]["input_tokens"] == 500
        assert metrics.by_model["gpt-4"]["requests"] == 1

        assert metrics.by_provider["anthropic"]["requests"] == 2
        assert metrics.by_provider["openai"]["requests"] == 1


class TestTokenTracker:
    """Test TokenTracker functionality."""

    @patch("hydra.token_tracker.get_cache")
    @patch("hydra.dashboard.database.get_db_manager")
    def test_initialization(self, mock_db_manager, mock_cache):
        """Test TokenTracker initialization."""
        tracker = TokenTracker(budget_limit=100.0, warning_threshold=0.8)

        assert tracker.budget_limit == 100.0
        assert tracker.warning_threshold == 0.8
        assert tracker._warned is False
        assert isinstance(tracker._current_usage, UsageMetrics)

    @patch("hydra.token_tracker.get_cache")
    @patch("hydra.dashboard.database.get_db_manager")
    def test_initialization_from_env(self, mock_db_manager, mock_cache):
        """Test TokenTracker initialization from environment."""
        with patch.dict(os.environ, {"TOKEN_BUDGET_LIMIT": "200.0"}):
            tracker = TokenTracker()
            assert tracker.budget_limit == 200.0

    @patch("hydra.token_tracker.get_cache")
    @patch("hydra.dashboard.database.get_db_manager")
    def test_count_tokens_with_tokenizer(self, mock_db_manager, mock_cache):
        """Test token counting with tokenizer."""
        tracker = TokenTracker()

        # Mock tokenizer
        mock_tokenizer = MagicMock()
        mock_tokenizer.encode.return_value = [1, 2, 3, 4, 5]
        tracker._tokenizers["anthropic"] = mock_tokenizer

        count = tracker.count_tokens("Test prompt", Provider.ANTHROPIC)

        assert count == 5
        mock_tokenizer.encode.assert_called_once_with("Test prompt")

    @patch("hydra.token_tracker.get_cache")
    @patch("hydra.dashboard.database.get_db_manager")
    def test_count_tokens_fallback(self, mock_db_manager, mock_cache):
        """Test token counting with fallback estimation."""
        tracker = TokenTracker()
        tracker._tokenizers = {}  # No tokenizers available

        # Should estimate 4 characters per token
        count = tracker.count_tokens("Test prompt here!", Provider.ANTHROPIC)
        assert count == len("Test prompt here!") // 4

    @patch("hydra.token_tracker.get_cache")
    @patch("hydra.dashboard.database.get_db_manager")
    def test_calculate_cost_known_model(self, mock_db_manager, mock_cache):
        """Test cost calculation for known model."""
        tracker = TokenTracker()

        input_cost, output_cost, total_cost = tracker.calculate_cost(
            "claude-3-5-sonnet-20241022", input_tokens=1000, output_tokens=500
        )

        # From TOKEN_COSTS: 0.003 per 1k input, 0.015 per 1k output
        assert input_cost == 0.003
        assert output_cost == 0.0075
        assert abs(total_cost - 0.0105) < 0.0001  # Allow for float precision

    @patch("hydra.token_tracker.get_cache")
    @patch("hydra.dashboard.database.get_db_manager")
    def test_calculate_cost_unknown_model(self, mock_db_manager, mock_cache):
        """Test cost calculation for unknown model."""
        tracker = TokenTracker()

        input_cost, output_cost, total_cost = tracker.calculate_cost(
            "unknown-model", input_tokens=1000, output_tokens=500
        )

        # Default pricing: 0.001 per 1k input, 0.002 per 1k output
        assert input_cost == 0.001
        assert output_cost == 0.001
        assert total_cost == 0.002

    @patch("hydra.token_tracker.get_cache")
    @patch("hydra.dashboard.database.get_db_manager")
    def test_track_usage(self, mock_db_manager, mock_cache):
        """Test tracking token usage."""
        mock_session = MagicMock()
        mock_db_manager.return_value.get_session.return_value.__enter__.return_value = (
            mock_session
        )

        tracker = TokenTracker(budget_limit=100.0)
        tracker._tokenizers = {}  # Use fallback counting

        result = tracker.track_usage(
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            prompt="Test prompt",
            response="Test response",
            ticket_id=1,
            session_id=2,
            metadata={"test": "data"},
        )

        assert "input_tokens" in result
        assert "output_tokens" in result
        assert "total_tokens" in result
        assert "input_cost" in result
        assert "output_cost" in result
        assert "total_cost" in result
        assert "cumulative_cost" in result
        assert "budget_remaining" in result
        assert "budget_percentage" in result

        # Check that database record was created
        assert mock_session.add.called
        assert mock_session.commit.called

    @patch("hydra.token_tracker.get_cache")
    @patch("hydra.dashboard.database.get_db_manager")
    def test_budget_warning(self, mock_db_manager, mock_cache):
        """Test budget warning at threshold."""
        mock_session = MagicMock()
        mock_db_manager.return_value.get_session.return_value.__enter__.return_value = (
            mock_session
        )

        tracker = TokenTracker(budget_limit=10.0, warning_threshold=0.8)
        tracker._tokenizers = {}

        # Add usage that exceeds warning threshold
        tracker._current_usage.total_cost = 7.5  # 75% of budget

        with patch("hydra.token_tracker.logger") as mock_logger:
            tracker._check_budget_warning()
            assert not mock_logger.warning.called  # Below threshold

        tracker._current_usage.total_cost = 8.5  # 85% of budget

        with patch("hydra.token_tracker.logger") as mock_logger:
            tracker._check_budget_warning()
            assert mock_logger.warning.called  # Above threshold
            assert tracker._warned is True

    @patch("hydra.token_tracker.get_cache")
    @patch("hydra.dashboard.database.get_db_manager")
    def test_check_budget_available(self, mock_db_manager, mock_cache):
        """Test checking budget availability."""
        # Initialize with a reasonable budget
        tracker = TokenTracker(budget_limit=10.0)

        # Ensure _current_usage is properly initialized
        assert tracker._current_usage is not None
        assert tracker._current_usage.total_cost == 0.0
        assert tracker.budget_limit == 10.0

        # Budget should be available for small request (1000 tokens)
        # With known model, estimated cost: 800 * 0.003/1000 + 200 * 0.015/1000 = 0.0054
        available, message = tracker.check_budget_available(
            estimated_tokens=1000, model="claude-3-5-sonnet-20241022"
        )
        # Should be available since 0.0054 < 10.0
        if not available:
            # Debug output
            _, _, cost = tracker.calculate_cost("claude-3-5-sonnet-20241022", 800, 200)
            print(
                f"DEBUG: Calculated cost: {cost}, Budget: {tracker.budget_limit}, Usage: {tracker._current_usage.total_cost}"
            )
        assert (
            available == True
        ), f"Expected budget to be available. Message: {message}, Type: {type(available)}"
        assert "available" in message.lower() or "no budget limit" in message.lower()

        # Exceed budget
        # Set usage close to limit, then request would exceed
        tracker._current_usage.total_cost = 9.95  # Only $0.05 left
        # 10000 tokens costs ~$0.054, which exceeds remaining budget
        available, message = tracker.check_budget_available(
            estimated_tokens=10000, model="claude-3-5-sonnet-20241022"
        )
        assert available is False, f"Expected budget to be exceeded. Message: {message}"
        assert "Insufficient budget" in message

    @patch("hydra.token_tracker.get_cache")
    @patch("hydra.dashboard.database.get_db_manager")
    def test_get_usage_report(self, mock_db_manager, mock_cache):
        """Test generating usage report."""
        mock_session = MagicMock()
        mock_db_manager.return_value.get_session.return_value.__enter__.return_value = (
            mock_session
        )

        # Mock usage data
        mock_usage = MagicMock()
        mock_usage.input_tokens = 1000
        mock_usage.output_tokens = 500
        mock_usage.total_tokens = 1500
        mock_usage.total_cost = 0.01
        mock_usage.provider = "anthropic"
        mock_usage.model = "claude-3-5-sonnet"
        mock_usage.ticket_id = 1
        mock_usage.timestamp = datetime.utcnow()

        mock_session.query.return_value.filter.return_value.all.return_value = [
            mock_usage
        ]
        (
            mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value
        ) = [mock_usage]

        tracker = TokenTracker()
        report = tracker.get_usage_report()

        assert "period" in report
        assert "summary" in report
        assert "by_provider" in report
        assert "by_model" in report
        assert "by_ticket" in report
        assert "top_expensive_requests" in report

        assert report["summary"]["total_requests"] == 1
        assert report["summary"]["total_input_tokens"] == 1000
        assert report["summary"]["total_output_tokens"] == 500
        assert report["summary"]["total_cost"] == 0.01

    @patch("hydra.token_tracker.get_cache")
    @patch("hydra.dashboard.database.get_db_manager")
    def test_export_usage_csv(self, mock_db_manager, mock_cache):
        """Test exporting usage to CSV."""
        mock_session = MagicMock()
        mock_db_manager.return_value.get_session.return_value.__enter__.return_value = (
            mock_session
        )

        # Mock usage data
        mock_usage = MagicMock()
        mock_usage.timestamp = datetime.utcnow()
        mock_usage.provider = "anthropic"
        mock_usage.model = "claude-3-5-sonnet"
        mock_usage.ticket_id = 1
        mock_usage.input_tokens = 1000
        mock_usage.output_tokens = 500
        mock_usage.total_tokens = 1500
        mock_usage.input_cost = 0.003
        mock_usage.output_cost = 0.0075
        mock_usage.total_cost = 0.0105

        (
            mock_session.query.return_value.filter.return_value.order_by.return_value.all.return_value
        ) = [mock_usage]

        tracker = TokenTracker()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as tmp:
            tracker.export_usage_csv(tmp.name)

            # Check file was created
            assert os.path.exists(tmp.name)

            # Read and verify content
            with open(tmp.name, "r") as f:
                content = f.read()
                assert "timestamp" in content
                assert "provider" in content
                assert "model" in content
                assert "anthropic" in content
                assert "claude-3-5-sonnet" in content

            # Clean up
            os.unlink(tmp.name)

    @patch("hydra.token_tracker.get_cache")
    @patch("hydra.dashboard.database.get_db_manager")
    def test_reset_budget(self, mock_db_manager, mock_cache):
        """Test resetting budget."""
        tracker = TokenTracker(budget_limit=100.0)

        # Add some usage
        tracker._current_usage.total_cost = 50.0
        tracker._current_usage.request_count = 10
        tracker._warned = True

        # Reset
        tracker.reset_budget()

        assert tracker._current_usage.total_cost == 0.0
        assert tracker._current_usage.request_count == 0
        assert tracker._warned is False

    @patch("hydra.token_tracker.get_cache")
    @patch("hydra.dashboard.database.get_db_manager")
    def test_get_current_usage(self, mock_db_manager, mock_cache):
        """Test getting current usage statistics."""
        tracker = TokenTracker(budget_limit=100.0)

        # Add some usage
        tracker._current_usage.add_usage(
            provider="anthropic",
            model="claude-3-5-sonnet",
            input_tokens=1000,
            output_tokens=500,
            cost=0.01,
        )

        usage = tracker.get_current_usage()

        assert usage["total_input_tokens"] == 1000
        assert usage["total_output_tokens"] == 500
        assert usage["total_tokens"] == 1500
        assert usage["total_cost"] == 0.01
        assert usage["request_count"] == 1
        assert usage["budget_limit"] == 100.0
        assert usage["budget_remaining"] == 99.99
        assert usage["budget_percentage"] == 0.01
        assert "by_model" in usage
        assert "by_provider" in usage


class TestGlobalInstances:
    """Test global instance management."""

    @patch("hydra.token_tracker.get_cache")
    @patch("hydra.dashboard.database.get_db_manager")
    def test_get_token_tracker_singleton(self, mock_db_manager, mock_cache):
        """Test get_token_tracker returns singleton."""
        tracker1 = get_token_tracker()
        tracker2 = get_token_tracker()

        assert tracker1 is tracker2

    @patch("hydra.token_tracker.get_cache")
    @patch("hydra.dashboard.database.get_db_manager")
    def test_reset_token_tracker(self, mock_db_manager, mock_cache):
        """Test reset_token_tracker creates new instance."""
        tracker1 = get_token_tracker()
        tracker2 = reset_token_tracker(budget_limit=200.0)
        tracker3 = get_token_tracker()

        assert tracker1 is not tracker2
        assert tracker2 is tracker3
        assert tracker3.budget_limit == 200.0
