"""Capability negotiation system for dynamic provider feature discovery and selection.

This module implements capability negotiation that discovers and adapts to different AI
provider features, enabling dynamic provider selection based on task requirements and
available capabilities.
"""
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Union

from .interactive_base import InteractiveAIProvider, ProviderCapability


@dataclass
class TaskRequirement:
    """Represents requirements for a specific task."""

    required_capabilities: Set[ProviderCapability]
    preferred_capabilities: Set[ProviderCapability] = field(default_factory=set)
    minimum_providers: int = 1
    task_type: str = "general"
    metadata: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            'required_capabilities': [cap.value for cap in self.required_capabilities],
            'preferred_capabilities': [
                cap.value for cap in self.preferred_capabilities
            ],
            'minimum_providers': self.minimum_providers,
            'task_type': self.task_type,
            'metadata': self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'TaskRequirement':
        """Create from dictionary."""
        return cls(
            required_capabilities={
                ProviderCapability(cap) for cap in data['required_capabilities']
            },
            preferred_capabilities={
                ProviderCapability(cap)
                for cap in data.get('preferred_capabilities', [])
            },
            minimum_providers=data.get('minimum_providers', 1),
            task_type=data.get('task_type', 'general'),
            metadata=data.get('metadata', {})
        )


@dataclass
class ProviderScore:
    """Score and metadata for a provider's suitability for a task."""

    provider_name: str
    capability_score: float
    preference_score: float
    total_score: float
    missing_required: Set[ProviderCapability] = field(default_factory=set)
    has_preferred: Set[ProviderCapability] = field(default_factory=set)
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class CapabilityCache:
    """Cache for provider capabilities to avoid repeated probing."""

    provider_name: str
    capabilities: Set[ProviderCapability]
    last_probed: float
    probe_count: int = 0
    cache_ttl: float = 300.0  # 5 minutes default TTL

    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        return time.time() - self.last_probed > self.cache_ttl

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            'provider_name': self.provider_name,
            'capabilities': [cap.value for cap in self.capabilities],
            'last_probed': self.last_probed,
            'probe_count': self.probe_count,
            'cache_ttl': self.cache_ttl
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'CapabilityCache':
        """Create from dictionary."""
        return cls(
            provider_name=data['provider_name'],
            capabilities={ProviderCapability(cap) for cap in data['capabilities']},
            last_probed=data['last_probed'],
            probe_count=data.get('probe_count', 0),
            cache_ttl=data.get('cache_ttl', 300.0)
        )


class FallbackStrategy:
    """Base class for capability fallback strategies."""

    def __init__(self, name: str):
        self.name = name

    def apply(
        self,
        missing_capabilities: Set[ProviderCapability],
        available_providers: List[InteractiveAIProvider],
        task_requirements: TaskRequirement
    ) -> Optional[List[InteractiveAIProvider]]:
        """Apply fallback strategy to handle missing capabilities."""
        raise NotImplementedError


class CapabilitySubstitution(FallbackStrategy):
    """Fallback strategy that substitutes missing capabilities with alternatives."""

    def __init__(self):
        super().__init__("capability_substitution")
        self.substitutions = {
            ProviderCapability.STREAMING_RESPONSE: [ProviderCapability.TASK_EXECUTION],
            ProviderCapability.CONCURRENT_SESSIONS: [
                ProviderCapability.SESSION_PERSISTENCE
            ],
        }

    def apply(
        self,
        missing_capabilities: Set[ProviderCapability],
        available_providers: List[InteractiveAIProvider],
        task_requirements: TaskRequirement
    ) -> Optional[List[InteractiveAIProvider]]:
        """Find providers that have substitute capabilities."""
        suitable_providers = []

        for provider in available_providers:
            provider_caps = provider.get_capabilities()
            can_substitute = True

            for missing_cap in missing_capabilities:
                if missing_cap in self.substitutions:
                    substitutes = self.substitutions[missing_cap]
                    if not any(sub_cap in provider_caps for sub_cap in substitutes):
                        can_substitute = False
                        break
                else:
                    can_substitute = False
                    break

            if can_substitute:
                suitable_providers.append(provider)

        return suitable_providers if suitable_providers else None


class ProviderComposition(FallbackStrategy):
    """Fallback strategy that composes multiple providers to meet requirements."""

    def __init__(self):
        super().__init__("provider_composition")

    def apply(
        self,
        missing_capabilities: Set[ProviderCapability],
        available_providers: List[InteractiveAIProvider],
        task_requirements: TaskRequirement
    ) -> Optional[List[InteractiveAIProvider]]:
        """Compose multiple providers to collectively meet requirements."""
        if task_requirements.minimum_providers == 1:
            return None

        # Find combination of providers that together have all required capabilities
        all_required = task_requirements.required_capabilities
        combined_providers = []
        covered_capabilities = set()

        for provider in available_providers:
            if len(combined_providers) >= 5:  # Limit composition complexity
                break

            provider_caps = provider.get_capabilities()
            new_coverage = provider_caps - covered_capabilities

            if new_coverage:  # Only add if provider adds new capabilities
                combined_providers.append(provider)
                covered_capabilities.update(provider_caps)

                if all_required.issubset(covered_capabilities):
                    return combined_providers

        return None


class CapabilityManager:
    """Manages capability negotiation and provider selection for tasks."""

    def __init__(self, cache_ttl: float = 300.0):
        """Initialize the capability manager.

        Args:
            cache_ttl: Cache time-to-live in seconds.

        """
        self.cache_ttl = cache_ttl
        self._capability_cache: Dict[str, CapabilityCache] = {}
        self._providers: List[InteractiveAIProvider] = []
        self._fallback_strategies: List[FallbackStrategy] = [
            CapabilitySubstitution(),
            ProviderComposition()
        ]
        self._probe_stats = defaultdict(int)

    def register_provider(self, provider: InteractiveAIProvider) -> None:
        """Register a provider with the capability manager.

        Args:
            provider: The provider to register.

        """
        if provider not in self._providers:
            self._providers.append(provider)

    def unregister_provider(self, provider: InteractiveAIProvider) -> None:
        """Unregister a provider from the capability manager.

        Args:
            provider: The provider to unregister.

        """
        if provider in self._providers:
            self._providers.remove(provider)

        # Remove from cache if present
        if provider.name in self._capability_cache:
            del self._capability_cache[provider.name]

    def probe_provider_capabilities(
        self,
        provider: InteractiveAIProvider,
        force_refresh: bool = False
    ) -> Set[ProviderCapability]:
        """Probe a provider's capabilities, using cache when possible.

        Args:
            provider: The provider to probe.
            force_refresh: Whether to bypass cache and force fresh probe.

        Returns:
            Set of capabilities the provider supports.

        """
        provider_name = provider.name

        # Check cache first
        if not force_refresh and provider_name in self._capability_cache:
            cache_entry = self._capability_cache[provider_name]
            if not cache_entry.is_expired():
                self._probe_stats['cache_hits'] += 1
                return cache_entry.capabilities

        # Perform fresh probe
        self._probe_stats['cache_misses'] += 1
        self._probe_stats['total_probes'] += 1

        try:
            capabilities = provider.detect_capabilities()
        except Exception:
            # If probing fails, return empty set and cache it briefly
            capabilities = set()

        # Update cache
        cache_entry = CapabilityCache(
            provider_name=provider_name,
            capabilities=capabilities,
            last_probed=time.time(),
            probe_count=(
                self._capability_cache.get(
                    provider_name, CapabilityCache("", set(), 0)
                ).probe_count + 1
            ),
            cache_ttl=self.cache_ttl
        )
        self._capability_cache[provider_name] = cache_entry

        return capabilities

    def score_provider(self, provider: InteractiveAIProvider,
                      task_requirements: TaskRequirement) -> ProviderScore:
        """Score a provider's suitability for a task.

        Args:
            provider: The provider to score.
            task_requirements: The task requirements to match against.

        Returns:
            Provider score with detailed breakdown.

        """
        capabilities = self.probe_provider_capabilities(provider)
        required_caps = task_requirements.required_capabilities
        preferred_caps = task_requirements.preferred_capabilities

        # Calculate capability score (0-100)
        if not required_caps:
            capability_score = 100.0
            missing_required = set()
        else:
            has_required = capabilities & required_caps
            missing_required = required_caps - capabilities
            capability_score = (len(has_required) / len(required_caps)) * 100.0

        # Calculate preference score (0-50)
        if not preferred_caps:
            preference_score = 0.0
            has_preferred = set()
        else:
            has_preferred = capabilities & preferred_caps
            preference_score = (len(has_preferred) / len(preferred_caps)) * 50.0

        total_score = capability_score + preference_score

        return ProviderScore(
            provider_name=provider.name,
            capability_score=capability_score,
            preference_score=preference_score,
            total_score=total_score,
            missing_required=missing_required,
            has_preferred=has_preferred
        )

    def select_providers(
        self, task_requirements: TaskRequirement
    ) -> List[InteractiveAIProvider]:
        """Select the best providers for a task based on requirements.

        Args:
            task_requirements: The requirements for the task.

        Returns:
            List of selected providers, ordered by suitability score.

        Raises:
            RuntimeError: If no suitable providers can be found.

        """
        if not self._providers:
            raise RuntimeError("No providers registered")

        # Score all providers
        provider_scores = []
        for provider in self._providers:
            score = self.score_provider(provider, task_requirements)
            provider_scores.append((provider, score))

        # Sort by total score (descending)
        provider_scores.sort(key=lambda x: x[1].total_score, reverse=True)

        # Find providers that meet all required capabilities
        suitable_providers = []
        for provider, score in provider_scores:
            if not score.missing_required:  # Has all required capabilities
                suitable_providers.append(provider)

        # If we have enough suitable providers, return them
        if len(suitable_providers) >= task_requirements.minimum_providers:
            return suitable_providers[:task_requirements.minimum_providers]

        # Apply fallback strategies
        missing_capabilities = set()
        if provider_scores:
            _, best_score = provider_scores[0]
            missing_capabilities = best_score.missing_required

        for strategy in self._fallback_strategies:
            fallback_providers = strategy.apply(
                missing_capabilities,
                self._providers,
                task_requirements
            )
            if (fallback_providers and
                len(fallback_providers) >= task_requirements.minimum_providers):
                return fallback_providers[:task_requirements.minimum_providers]

        # If no fallback worked, return best available providers
        if suitable_providers:
            return suitable_providers
        elif provider_scores:
            # Return the best provider even if it doesn't meet all requirements
            return [provider_scores[0][0]]

        raise RuntimeError("No providers available for task requirements")

    def get_provider_capabilities(
        self, provider_name: str
    ) -> Optional[Set[ProviderCapability]]:
        """Get cached capabilities for a provider by name.

        Args:
            provider_name: Name of the provider.

        Returns:
            Set of capabilities or None if provider not found.

        """
        if provider_name in self._capability_cache:
            cache_entry = self._capability_cache[provider_name]
            if not cache_entry.is_expired():
                return cache_entry.capabilities

        # Try to find provider and probe it
        for provider in self._providers:
            if provider.name == provider_name:
                return self.probe_provider_capabilities(provider)

        return None

    def refresh_all_capabilities(self) -> None:
        """Refresh capabilities for all registered providers."""
        for provider in self._providers:
            self.probe_provider_capabilities(provider, force_refresh=True)

    def get_cache_stats(self) -> Dict[str, Union[int, Dict[str, int]]]:
        """Get cache performance statistics.

        Returns:
            Dictionary with cache statistics.

        """
        active_entries = sum(
            1 for entry in self._capability_cache.values()
            if not entry.is_expired()
        )
        expired_entries = len(self._capability_cache) - active_entries

        return {
            'total_entries': len(self._capability_cache),
            'active_entries': active_entries,
            'expired_entries': expired_entries,
            'probe_stats': dict(self._probe_stats),
            'cache_hit_rate': (
                self._probe_stats['cache_hits'] /
                max(
                    1,
                    self._probe_stats['cache_hits'] + self._probe_stats['cache_misses']
                )
            ) * 100
        }

    def clear_expired_cache(self) -> int:
        """Clear expired cache entries.

        Returns:
            Number of entries cleared.

        """
        expired_keys = [
            key for key, entry in self._capability_cache.items()
            if entry.is_expired()
        ]

        for key in expired_keys:
            del self._capability_cache[key]

        return len(expired_keys)

    def serialize_cache(self) -> Dict:
        """Serialize capability cache for persistence.

        Returns:
            Serializable cache data.

        """
        return {
            'cache_data': {
                key: entry.to_dict() for key, entry in self._capability_cache.items()
            },
            'cache_ttl': self.cache_ttl,
            'probe_stats': dict(self._probe_stats)
        }

    def deserialize_cache(self, data: Dict) -> None:
        """Deserialize capability cache from persistence.

        Args:
            data: Serialized cache data.

        """
        if 'cache_data' in data:
            self._capability_cache = {
                key: CapabilityCache.from_dict(entry_data)
                for key, entry_data in data['cache_data'].items()
            }

        if 'cache_ttl' in data:
            self.cache_ttl = data['cache_ttl']

        if 'probe_stats' in data:
            self._probe_stats.update(data['probe_stats'])

    def add_fallback_strategy(self, strategy: FallbackStrategy) -> None:
        """Add a custom fallback strategy.

        Args:
            strategy: The fallback strategy to add.

        """
        self._fallback_strategies.append(strategy)

    def remove_fallback_strategy(self, strategy_name: str) -> bool:
        """Remove a fallback strategy by name.

        Args:
            strategy_name: Name of the strategy to remove.

        Returns:
            True if strategy was found and removed.

        """
        for i, strategy in enumerate(self._fallback_strategies):
            if strategy.name == strategy_name:
                del self._fallback_strategies[i]
                return True
        return False
