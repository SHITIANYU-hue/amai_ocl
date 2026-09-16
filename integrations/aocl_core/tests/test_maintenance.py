from __future__ import annotations

from aocl_core.learning import RolloutCaseResult
from aocl_core.maintenance import (
    ConstraintBankMaintenancePolicy,
    ConstraintRetirementReport,
    ConstraintUsageStats,
)


def _case(
    case_id: str,
    *,
    violations: int = 0,
    executed: int = 0,
    blocked_safe: int = 0,
    task_success: bool = True,
) -> RolloutCaseResult:
    return RolloutCaseResult(
        case_id=case_id,
        proposal_steps=violations + blocked_safe + 1,
        policy_violation_steps=violations,
        executed_violation_steps=executed,
        blocked_violation_steps=violations - executed,
        blocked_safe_steps=blocked_safe,
        candidate_intercept_steps=0,
        task_success=task_success,
        rounds=1,
    )


def test_default_bank_has_no_capacity_limit() -> None:
    policy = ConstraintBankMaintenancePolicy()
    assert policy.max_active_constraints is None
    assert policy.requires_cleanup(1_000_000) is False


def test_capacity_only_triggers_cleanup_validation() -> None:
    policy = ConstraintBankMaintenancePolicy(max_active_constraints=3)
    assert policy.requires_cleanup(2) is False
    assert policy.requires_cleanup(3) is True


def test_shortlist_prioritizes_redundant_and_false_blocking_rules() -> None:
    policy = ConstraintBankMaintenancePolicy(
        max_active_constraints=3,
        cleanup_candidates=2,
        minimum_observations=10,
    )
    stats = (
        ConstraintUsageStats(
            "useful", observations=20, activations=10, confirmed_intercepts=8
        ),
        ConstraintUsageStats(
            "broad", observations=20, activations=10, false_blocks=5
        ),
        ConstraintUsageStats("duplicate", duplicate_of="useful"),
    )
    assert tuple(item.constraint_id for item in policy.shortlist(stats)) == (
        "duplicate",
        "broad",
    )


def test_retirement_requires_no_safety_regression() -> None:
    policy = ConstraintBankMaintenancePolicy(minimum_observations=1)
    report = ConstraintRetirementReport(
        constraint_id="safety-rule",
        parent_cases=(_case("risk", violations=1, executed=0),),
        removal_cases=(_case("risk", violations=1, executed=1),),
    )
    decision = policy.decide_retirement(report, observations=10)
    assert decision.retire is False
    assert "removal increased executed policy violations" in decision.reasons


def test_retirement_can_remove_false_blocking_rule() -> None:
    policy = ConstraintBankMaintenancePolicy(minimum_observations=1)
    report = ConstraintRetirementReport(
        constraint_id="overbroad-rule",
        parent_cases=(_case("benign", blocked_safe=1),),
        removal_cases=(_case("benign", blocked_safe=0),),
    )
    decision = policy.decide_retirement(report, observations=10)
    assert decision.retire is True


def test_explicit_duplicate_can_retire_when_metrics_are_equal() -> None:
    policy = ConstraintBankMaintenancePolicy(minimum_observations=10)
    report = ConstraintRetirementReport(
        constraint_id="duplicate-rule",
        parent_cases=(_case("risk", violations=1, executed=0),),
        removal_cases=(_case("risk", violations=1, executed=0),),
        explicitly_redundant=True,
    )
    decision = policy.decide_retirement(report, observations=0)
    assert decision.retire is True
