"""One-call orchestration of the offline adaptive constraint loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .candidate_curation_gate import (
    CandidateCurationGate,
    CandidateCurationResult,
)
from .learning import (
    CandidateDiagnosis,
    CandidateValidator,
    ConstraintDiagnoser,
    LearningTrace,
    OutcomeLabel,
    PromotionPolicy,
    PromotionResult,
    ReplayCase,
    ValidationReport,
    promote_candidate,
)
from .versioning import LibraryVersion, VersionedLibraryStore


@dataclass(frozen=True, slots=True)
class AdaptiveLearningResult:
    diagnosis: CandidateDiagnosis
    validation: ValidationReport
    promotion: PromotionResult
    curation: CandidateCurationResult | None
    library_version: LibraryVersion | None


@dataclass(frozen=True, slots=True)
class AdaptiveLearningPipeline:
    diagnoser: ConstraintDiagnoser
    validator: CandidateValidator
    promotion_policy: PromotionPolicy
    library_store: VersionedLibraryStore
    curation_gate: CandidateCurationGate = field(
        default_factory=CandidateCurationGate
    )

    def process_failure(
        self,
        *,
        trace: LearningTrace,
        label: OutcomeLabel,
        replay_cases: Sequence[ReplayCase],
        parent_version: LibraryVersion,
        child_version_id: str,
    ) -> AdaptiveLearningResult:
        diagnosis = self.diagnoser.diagnose(trace, label)
        validation = self.validator.validate(diagnosis.constraint, replay_cases)
        promotion = promote_candidate(
            diagnosis.constraint,
            validation,
            self.promotion_policy,
        )
        # promote_candidate() records the verifier/promotion-policy decision.
        # The Constraint Bank itself is not updated until the Candidate
        # Curation Gate has accepted the verifier-approved candidate.
        curation = None
        child = None

        if promotion.approved:
            curation = self.curation_gate.evaluate(
                candidate=promotion.constraint,
                diagnosis=diagnosis,
                trace=trace,
                bank=parent_version.library,
            )

            if curation.accepted:
                child = self.library_store.promote(
                    parent=parent_version,
                    result=promotion,
                    policy=self.promotion_policy,
                    version_id=child_version_id,
                )

        return AdaptiveLearningResult(
            diagnosis=diagnosis,
            validation=validation,
            promotion=promotion,
            curation=curation,
            library_version=child,
        )
