from types import SimpleNamespace

from aocl_core.candidate_curation_gate import GateDecision
from aocl_core.learning import (
    CandidateDiagnosis,
    PromotionPolicy,
    ValidationReport,
)
from aocl_core.library import (
    ConstraintResponse,
    ConstraintStatus,
    FrozenConstraintLibrary,
    SoftConstraint,
)
from aocl_core.pipeline import AdaptiveLearningPipeline
from aocl_core.versioning import VersionedLibraryStore


class StubDiagnoser:
    def __init__(self, diagnosis):
        self.diagnosis = diagnosis

    def diagnose(self, trace, label):
        return self.diagnosis


class StubValidator:
    def __init__(self, report):
        self.report = report

    def validate(self, candidate, cases):
        assert candidate.constraint_id == self.report.candidate_id
        return self.report


def make_candidate(
    *,
    constraint_id="candidate_1",
    instruction="Do not repeat an action after the same hard boundary is enforced.",
    scope="task_specific",
    source_episode_ids=("episode_1",),
):
    return SoftConstraint(
        constraint_id=constraint_id,
        action_types=("proposal",),
        tactic_type="boundary",
        trigger_pattern="repeated action after hard boundary",
        keywords=("boundary", "repeat"),
        instruction=instruction,
        response=ConstraintResponse.BLOCK,
        status=ConstraintStatus.CANDIDATE,
        source_episode_ids=source_episode_ids,
        metadata={
            "scenario_id": "scenario_1",
            "scope": scope,
        },
    )


def make_diagnosis(candidate):
    return CandidateDiagnosis(
        constraint=candidate,
        earliest_detectable_step=1,
        visible_evidence=("hard boundary already enforced",),
        rationale="Repeated blocked action was observed.",
    )


def make_validation_report(candidate_id, *, passes=True):
    if passes:
        return ValidationReport(
            candidate_id=candidate_id,
            cases=2,
            positive_cases=1,
            negative_cases=1,
            true_positives=1,
            false_positives=0,
            true_negatives=1,
            false_negatives=0,
            recall=1.0,
            precision=1.0,
            false_positive_rate=0.0,
            case_results=(),
        )

    return ValidationReport(
        candidate_id=candidate_id,
        cases=2,
        positive_cases=1,
        negative_cases=1,
        true_positives=0,
        false_positives=0,
        true_negatives=1,
        false_negatives=1,
        recall=0.0,
        precision=0.0,
        false_positive_rate=0.0,
        case_results=(),
    )


def make_pipeline(tmp_path, candidate, report):
    store = VersionedLibraryStore(tmp_path / "libraries")

    pipeline = AdaptiveLearningPipeline(
        diagnoser=StubDiagnoser(make_diagnosis(candidate)),
        validator=StubValidator(report),
        promotion_policy=PromotionPolicy(),
        library_store=store,
    )

    return pipeline, store


def test_verifier_then_gate_accept_writes_constraint_bank(tmp_path):
    candidate = make_candidate()
    report = make_validation_report(candidate.constraint_id, passes=True)

    pipeline, store = make_pipeline(tmp_path, candidate, report)
    parent = store.create_initial(version_id="L000")

    result = pipeline.process_failure(
        trace=SimpleNamespace(
            episode_id="episode_1",
            scenario_id="scenario_1",
        ),
        label=object(),
        replay_cases=(),
        parent_version=parent,
        child_version_id="L001",
    )

    assert result.promotion.approved
    assert result.curation is not None
    assert result.curation.decision is GateDecision.ACCEPT
    assert result.library_version is not None
    assert result.library_version.version_id == "L001"

    approved = result.library_version.library.approved
    assert len(approved) == 1
    assert approved[0].constraint_id == candidate.constraint_id


def test_gate_reject_prevents_constraint_bank_update(tmp_path):
    existing = make_candidate(
        constraint_id="existing_1",
    ).approved_copy()

    candidate = make_candidate(
        constraint_id="candidate_2",
    )
    report = make_validation_report(candidate.constraint_id, passes=True)

    pipeline, store = make_pipeline(tmp_path, candidate, report)

    parent = store.create_initial(
        FrozenConstraintLibrary((existing,)),
        version_id="L000",
    )

    result = pipeline.process_failure(
        trace=SimpleNamespace(
            episode_id="episode_1",
            scenario_id="scenario_1",
        ),
        label=object(),
        replay_cases=(),
        parent_version=parent,
        child_version_id="L001",
    )

    assert result.promotion.approved
    assert result.curation is not None
    assert result.curation.decision is GateDecision.REJECT
    assert result.library_version is None
    assert not (tmp_path / "libraries" / "L001").exists()


def test_gate_near_duplicate_defer_prevents_constraint_bank_update(tmp_path):
    existing = make_candidate(
        constraint_id="existing_1",
        instruction=(
            "Do not repeat an action after the same hard boundary "
            "has been enforced."
        ),
    ).approved_copy()

    candidate = make_candidate(
        constraint_id="candidate_2",
        instruction=(
            "Do not repeat an action after the same hard boundary "
            "is enforced."
        ),
    )
    report = make_validation_report(candidate.constraint_id, passes=True)

    pipeline, store = make_pipeline(tmp_path, candidate, report)
    parent = store.create_initial(
        FrozenConstraintLibrary((existing,)),
        version_id="L000",
    )

    result = pipeline.process_failure(
        trace=SimpleNamespace(
            episode_id="episode_1",
            scenario_id="scenario_1",
        ),
        label=object(),
        replay_cases=(),
        parent_version=parent,
        child_version_id="L001",
    )

    assert result.promotion.approved
    assert result.curation is not None
    assert result.curation.decision is GateDecision.DEFER
    assert result.curation.duplicate_of == "existing_1"
    assert result.library_version is None
    assert not (tmp_path / "libraries" / "L001").exists()


def test_verifier_failure_does_not_run_gate_or_update_bank(tmp_path):
    candidate = make_candidate()
    report = make_validation_report(candidate.constraint_id, passes=False)

    pipeline, store = make_pipeline(tmp_path, candidate, report)
    parent = store.create_initial(version_id="L000")

    result = pipeline.process_failure(
        trace=SimpleNamespace(
            episode_id="episode_1",
            scenario_id="scenario_1",
        ),
        label=object(),
        replay_cases=(),
        parent_version=parent,
        child_version_id="L001",
    )

    assert not result.promotion.approved
    assert result.curation is None
    assert result.library_version is None
    assert not (tmp_path / "libraries" / "L001").exists()
