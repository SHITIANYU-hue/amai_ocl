"""Capacity and verified-retirement policy for active Constraint Banks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .learning import LearningError, RolloutCaseResult, RolloutMetrics


@dataclass(frozen=True, slots=True)
class ConstraintUsageStats:
    """Observable maintenance statistics for one active soft constraint."""

    constraint_id: str
    observations: int = 0
    retrievals: int = 0
    activations: int = 0
    confirmed_intercepts: int = 0
    false_blocks: int = 0
    inactive_versions: int = 0
    duplicate_of: str | None = None
    superseded_by: str | None = None

    def __post_init__(self) -> None:
        if not self.constraint_id.strip():
            raise ValueError("constraint_id must not be empty")
        values = (
            self.observations,
            self.retrievals,
            self.activations,
            self.confirmed_intercepts,
            self.false_blocks,
            self.inactive_versions,
        )
        if any(value < 0 for value in values):
            raise ValueError("constraint usage counts must be non-negative")
        if self.false_blocks > self.activations:
            raise ValueError("false_blocks cannot exceed activations")
        if self.confirmed_intercepts > self.activations:
            raise ValueError("confirmed_intercepts cannot exceed activations")

    @property
    def false_block_rate(self) -> float:
        return self.false_blocks / self.activations if self.activations else 0.0

    @property
    def explicitly_redundant(self) -> bool:
        return self.duplicate_of is not None or self.superseded_by is not None


@dataclass(frozen=True, slots=True)
class ConstraintRetirementReport:
    """Paired fresh-rollout evidence for Bank B versus Bank B without one rule."""

    constraint_id: str
    parent_cases: tuple[RolloutCaseResult, ...]
    removal_cases: tuple[RolloutCaseResult, ...]
    explicitly_redundant: bool = False

    def __post_init__(self) -> None:
        if not self.constraint_id.strip():
            raise LearningError("constraint_id must not be empty")
        parent_ids = {case.case_id for case in self.parent_cases}
        removal_ids = {case.case_id for case in self.removal_cases}
        if not self.parent_cases or not self.removal_cases:
            raise LearningError("retirement validation requires paired rollout cases")
        if len(parent_ids) != len(self.parent_cases):
            raise LearningError("parent retirement case IDs must be unique")
        if len(removal_ids) != len(self.removal_cases):
            raise LearningError("removal retirement case IDs must be unique")
        if parent_ids != removal_ids:
            raise LearningError("parent and removal must use the same rollout cases")

    @property
    def parent(self) -> RolloutMetrics:
        return RolloutMetrics.from_cases(self.parent_cases)

    @property
    def removal(self) -> RolloutMetrics:
        return RolloutMetrics.from_cases(self.removal_cases)


@dataclass(frozen=True, slots=True)
class ConstraintRetirementDecision:
    retire: bool
    constraint_id: str
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ConstraintBankMaintenancePolicy:
    """Configurable limit whose default leaves Bank growth uncapped.

    Reaching capacity only starts validation.  It never authorizes an
    unverified deletion; if no safe retirement is found, the new Candidate must
    be rejected or deferred by the host update runner.
    """

    max_active_constraints: int | None = None
    cleanup_candidates: int = 3
    minimum_observations: int = 10
    false_block_threshold: float = 0.2
    inactive_versions: int = 5
    allow_safety_regression: bool = False

    def __post_init__(self) -> None:
        if self.max_active_constraints is not None and self.max_active_constraints <= 0:
            raise ValueError("max_active_constraints must be positive or None")
        if self.cleanup_candidates <= 0:
            raise ValueError("cleanup_candidates must be positive")
        if self.minimum_observations < 0:
            raise ValueError("minimum_observations must be non-negative")
        if not 0 <= self.false_block_threshold <= 1:
            raise ValueError("false_block_threshold must be between zero and one")
        if self.inactive_versions < 0:
            raise ValueError("inactive_versions must be non-negative")

    def requires_cleanup(self, active_count: int, *, incoming: int = 1) -> bool:
        if active_count < 0 or incoming < 0:
            raise ValueError("constraint counts must be non-negative")
        return (
            self.max_active_constraints is not None
            and active_count + incoming > self.max_active_constraints
        )

    def shortlist(
        self,
        stats: Sequence[ConstraintUsageStats],
    ) -> tuple[ConstraintUsageStats, ...]:
        """Choose rules worth testing for retirement, never rules to delete."""
        eligible = []
        for item in stats:
            enough_evidence = item.observations >= self.minimum_observations
            high_false_blocks = (
                enough_evidence
                and item.activations > 0
                and item.false_block_rate >= self.false_block_threshold
            )
            inactive_without_confirmed_value = (
                enough_evidence
                and item.confirmed_intercepts == 0
                and item.inactive_versions >= self.inactive_versions
            )
            if item.explicitly_redundant or high_false_blocks or inactive_without_confirmed_value:
                eligible.append(item)

        def priority(
            item: ConstraintUsageStats,
        ) -> tuple[float, float, float, float, str]:
            return (
                0.0 if item.explicitly_redundant else 1.0,
                -item.false_block_rate,
                float(item.confirmed_intercepts),
                -float(item.inactive_versions),
                item.constraint_id,
            )

        return tuple(sorted(eligible, key=priority)[: self.cleanup_candidates])

    def decide_retirement(
        self,
        report: ConstraintRetirementReport,
        *,
        observations: int,
    ) -> ConstraintRetirementDecision:
        """Retire only after removal is safe and provides a justified benefit."""
        reasons: list[str] = []
        parent = report.parent
        removal = report.removal
        if observations < self.minimum_observations and not report.explicitly_redundant:
            reasons.append("insufficient observations for retirement")
        if (
            not self.allow_safety_regression
            and removal.executed_violation_steps > parent.executed_violation_steps
        ):
            reasons.append("removal increased executed policy violations")
        if removal.task_successes < parent.task_successes:
            reasons.append("removal reduced task successes")
        if removal.valid_successes < parent.valid_successes:
            reasons.append("removal reduced valid successes")

        false_block_improvement = (
            removal.blocked_safe_steps < parent.blocked_safe_steps
        )
        metric_equivalence = (
            removal.executed_violation_steps == parent.executed_violation_steps
            and removal.blocked_safe_steps == parent.blocked_safe_steps
            and removal.task_successes == parent.task_successes
            and removal.valid_successes == parent.valid_successes
        )
        if not false_block_improvement and not (
            report.explicitly_redundant and metric_equivalence
        ):
            reasons.append(
                "removal neither reduced false blocks nor proved redundant"
            )
        return ConstraintRetirementDecision(
            retire=not reasons,
            constraint_id=report.constraint_id,
            reasons=tuple(reasons),
        )
