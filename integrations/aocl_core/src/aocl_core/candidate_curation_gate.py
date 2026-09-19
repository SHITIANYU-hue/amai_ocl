"""Deterministic Candidate Curation Gate for verifier-approved constraints."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum
import re

from .learning import CandidateDiagnosis, LearningTrace
from .library import (
    ConstraintScope,
    ConstraintStatus,
    FrozenConstraintLibrary,
    SoftConstraint,
)


class CurationGateError(ValueError):
    """Raised when the Candidate Curation Gate receives invalid input."""


class GateDecision(str, Enum):
    ACCEPT = "accept"
    DEFER = "defer"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class CandidateCurationResult:
    decision: GateDecision
    reasons: tuple[str, ...] = ()
    duplicate_of: str | None = None

    @property
    def accepted(self) -> bool:
        return self.decision is GateDecision.ACCEPT


@dataclass(frozen=True, slots=True)
class CandidateCurationGate:
    """Curate verifier-approved candidates before Constraint Bank insertion.

    The gate performs three learning-time checks:

    1. grounding,
    2. non-duplication,
    3. appropriate scope.

    The gate does not repeat empirical verification.
    """

    near_duplicate_threshold: float = 0.90

    def __post_init__(self) -> None:
        if not 0.0 <= self.near_duplicate_threshold <= 1.0:
            raise CurationGateError(
                "near_duplicate_threshold must be between 0 and 1"
            )

    def evaluate(
        self,
        *,
        candidate: SoftConstraint,
        diagnosis: CandidateDiagnosis,
        trace: LearningTrace,
        bank: FrozenConstraintLibrary,
    ) -> CandidateCurationResult:
        if candidate.status is not ConstraintStatus.APPROVED:
            raise CurationGateError(
                "Candidate Curation Gate requires a verifier-approved candidate"
            )

        if candidate.constraint_id != diagnosis.constraint.constraint_id:
            raise CurationGateError(
                "candidate and diagnosis constraint IDs do not match"
            )

        grounding_reasons: list[str] = []

        if not diagnosis.visible_evidence:
            grounding_reasons.append(
                "candidate has no visible failure evidence"
            )

        if trace.episode_id not in candidate.source_episode_ids:
            grounding_reasons.append(
                "candidate source episodes do not include the current failure trajectory"
            )

        candidate_scenario = candidate.metadata.get("scenario_id")
        if candidate_scenario != trace.scenario_id:
            grounding_reasons.append(
                "candidate scenario does not match the current failure trajectory"
            )

        if grounding_reasons:
            return CandidateCurationResult(
                decision=GateDecision.REJECT,
                reasons=tuple(grounding_reasons),
            )

        exact_duplicate = self._find_exact_duplicate(candidate, bank)
        if exact_duplicate is not None:
            return CandidateCurationResult(
                decision=GateDecision.REJECT,
                reasons=("candidate duplicates an existing Bank constraint",),
                duplicate_of=exact_duplicate.constraint_id,
            )

        near_duplicate = self._find_near_duplicate(candidate, bank)

        scope_reasons: list[str] = []

        if (
            candidate.scope is ConstraintScope.TASK_SPECIFIC
            and not candidate.metadata.get("scenario_id")
        ):
            scope_reasons.append(
                "task-specific candidate has no scenario grounding"
            )

        defer_reasons: list[str] = []

        if near_duplicate is not None:
            defer_reasons.append(
                "candidate is highly similar to an existing Bank constraint"
            )

        defer_reasons.extend(scope_reasons)

        if defer_reasons:
            return CandidateCurationResult(
                decision=GateDecision.DEFER,
                reasons=tuple(defer_reasons),
                duplicate_of=(
                    near_duplicate.constraint_id
                    if near_duplicate is not None
                    else None
                ),
            )

        return CandidateCurationResult(
            decision=GateDecision.ACCEPT,
        )

    def _find_exact_duplicate(
        self,
        candidate: SoftConstraint,
        bank: FrozenConstraintLibrary,
    ) -> SoftConstraint | None:
        candidate_signature = self._signature(candidate)

        for existing in bank.approved:
            if existing.constraint_id == candidate.constraint_id:
                return existing

            if self._signature(existing) == candidate_signature:
                return existing

        return None

    def _find_near_duplicate(
        self,
        candidate: SoftConstraint,
        bank: FrozenConstraintLibrary,
    ) -> SoftConstraint | None:
        candidate_text = self._comparison_text(candidate)

        for existing in bank.approved:
            if existing.response is not candidate.response:
                continue

            if not set(existing.action_types).intersection(candidate.action_types):
                continue

            score = SequenceMatcher(
                None,
                candidate_text,
                self._comparison_text(existing),
            ).ratio()

            if score >= self.near_duplicate_threshold:
                return existing

        return None

    @staticmethod
    def _signature(constraint: SoftConstraint) -> tuple[object, ...]:
        return (
            tuple(sorted(item.casefold() for item in constraint.action_types)),
            constraint.tactic_type.casefold(),
            CandidateCurationGate._normalize(constraint.trigger_pattern),
            CandidateCurationGate._normalize(constraint.instruction),
            constraint.response.value,
            constraint.scope.value,
        )

    @staticmethod
    def _comparison_text(constraint: SoftConstraint) -> str:
        return " ".join(
            (
                CandidateCurationGate._normalize(constraint.trigger_pattern),
                CandidateCurationGate._normalize(constraint.instruction),
            )
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(
            re.findall(r"[a-z0-9]+", value.casefold())
        )
