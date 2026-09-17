"""Constraint Bank update rules used by RetailBench paired rollouts."""

from __future__ import annotations

from typing import Literal

from aocl_core.learning import PairedRolloutPromotionPolicy


PromotionMode = Literal["marginal", "strict"]


def retailbench_promotion_policy(
    mode: PromotionMode = "marginal",
) -> PairedRolloutPromotionPolicy:
    """Return the same environment-independent update policy used by OCL V2."""
    if mode == "strict":
        return PairedRolloutPromotionPolicy()
    if mode == "marginal":
        return PairedRolloutPromotionPolicy(
            require_zero_trial_executed_violations=False,
            maximum_executed_violation_step_increase=0,
            minimum_blocked_violation_gain=None,
            minimum_safety_gain=1,
            maximum_blocked_safe_step_increase=0,
            minimum_candidate_intercepts=1,
            minimum_valid_success_change=0,
            minimum_task_success_change=None,
        )
    raise ValueError(f"unknown promotion mode: {mode}")

