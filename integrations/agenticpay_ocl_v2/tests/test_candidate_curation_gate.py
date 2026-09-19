from types import SimpleNamespace

import pytest

from aocl_core.candidate_curation_gate import (
    CandidateCurationGate,
    CurationGateError,
    GateDecision,
)
from aocl_core.learning import CandidateDiagnosis
from aocl_core.library import (
    ConstraintResponse,
    ConstraintStatus,
    FrozenConstraintLibrary,
    SoftConstraint,
)


def make_trace(
    *,
    episode_id: str = "episode_1",
    scenario_id: str = "scenario_1",
):
    return SimpleNamespace(
        episode_id=episode_id,
        scenario_id=scenario_id,
    )


def make_candidate(
    *,
    constraint_id: str = "candidate_1",
    instruction: str = (
        "Do not repeat an action after the same hard boundary is enforced."
    ),
    trigger_pattern: str = "repeated action after hard boundary",
    scope: str = "task_specific",
    source_episode_ids: tuple[str, ...] = ("episode_1",),
    scenario_id: str = "scenario_1",
) -> SoftConstraint:
    return SoftConstraint(
        constraint_id=constraint_id,
        action_types=("proposal",),
        tactic_type="boundary",
        trigger_pattern=trigger_pattern,
        keywords=("boundary", "repeat"),
        instruction=instruction,
        response=ConstraintResponse.BLOCK,
        status=ConstraintStatus.CANDIDATE,
        source_episode_ids=source_episode_ids,
        metadata={
            "scenario_id": scenario_id,
            "scope": scope,
        },
    )


def make_diagnosis(candidate: SoftConstraint) -> CandidateDiagnosis:
    return CandidateDiagnosis(
        constraint=candidate,
        earliest_detectable_step=1,
        visible_evidence=("hard boundary already enforced",),
        rationale="Repeated blocked action was observed.",
    )


def test_accepts_grounded_unique_task_specific_candidate():
    raw_candidate = make_candidate()
    diagnosis = make_diagnosis(raw_candidate)
    verified_candidate = raw_candidate.approved_copy()

    result = CandidateCurationGate().evaluate(
        candidate=verified_candidate,
        diagnosis=diagnosis,
        trace=make_trace(),
        bank=FrozenConstraintLibrary(),
    )

    assert result.decision is GateDecision.ACCEPT
    assert result.accepted
    assert result.reasons == ()
    assert result.duplicate_of is None


def test_rejects_candidate_not_grounded_in_current_episode():
    raw_candidate = make_candidate(
        source_episode_ids=("different_episode",),
    )
    diagnosis = make_diagnosis(raw_candidate)
    verified_candidate = raw_candidate.approved_copy()

    result = CandidateCurationGate().evaluate(
        candidate=verified_candidate,
        diagnosis=diagnosis,
        trace=make_trace(episode_id="episode_1"),
        bank=FrozenConstraintLibrary(),
    )

    assert result.decision is GateDecision.REJECT
    assert any(
        "current failure trajectory" in reason
        for reason in result.reasons
    )


def test_rejects_candidate_with_scenario_mismatch():
    raw_candidate = make_candidate(
        scenario_id="different_scenario",
    )
    diagnosis = make_diagnosis(raw_candidate)
    verified_candidate = raw_candidate.approved_copy()

    result = CandidateCurationGate().evaluate(
        candidate=verified_candidate,
        diagnosis=diagnosis,
        trace=make_trace(scenario_id="scenario_1"),
        bank=FrozenConstraintLibrary(),
    )

    assert result.decision is GateDecision.REJECT
    assert any(
        "scenario does not match" in reason
        for reason in result.reasons
    )


def test_rejects_exact_duplicate():
    existing = make_candidate(
        constraint_id="existing_1",
    ).approved_copy()

    raw_candidate = make_candidate(
        constraint_id="candidate_2",
    )
    diagnosis = make_diagnosis(raw_candidate)
    verified_candidate = raw_candidate.approved_copy()

    result = CandidateCurationGate().evaluate(
        candidate=verified_candidate,
        diagnosis=diagnosis,
        trace=make_trace(),
        bank=FrozenConstraintLibrary((existing,)),
    )

    assert result.decision is GateDecision.REJECT
    assert result.duplicate_of == "existing_1"


def test_defers_near_duplicate():
    existing = make_candidate(
        constraint_id="existing_1",
        instruction=(
            "Do not repeat an action after the same hard boundary has been enforced."
        ),
    ).approved_copy()

    raw_candidate = make_candidate(
        constraint_id="candidate_2",
        instruction=(
            "Do not repeat an action after the same hard boundary is enforced."
        ),
    )
    diagnosis = make_diagnosis(raw_candidate)
    verified_candidate = raw_candidate.approved_copy()

    result = CandidateCurationGate(
        near_duplicate_threshold=0.85
    ).evaluate(
        candidate=verified_candidate,
        diagnosis=diagnosis,
        trace=make_trace(),
        bank=FrozenConstraintLibrary((existing,)),
    )

    assert result.decision is GateDecision.DEFER
    assert result.duplicate_of == "existing_1"


def test_accepts_grounded_general_candidate_with_single_source():
    raw_candidate = make_candidate(
        scope="general",
        source_episode_ids=("episode_1",),
    )
    diagnosis = make_diagnosis(raw_candidate)
    verified_candidate = raw_candidate.approved_copy()

    result = CandidateCurationGate().evaluate(
        candidate=verified_candidate,
        diagnosis=diagnosis,
        trace=make_trace(),
        bank=FrozenConstraintLibrary(),
    )

    assert result.decision is GateDecision.ACCEPT
    assert result.accepted
    assert result.reasons == ()


def test_rejects_candidate_without_source_grounding():
    raw_candidate = make_candidate(
        source_episode_ids=(),
    )
    diagnosis = make_diagnosis(raw_candidate)
    verified_candidate = raw_candidate.approved_copy()

    result = CandidateCurationGate().evaluate(
        candidate=verified_candidate,
        diagnosis=diagnosis,
        trace=make_trace(),
        bank=FrozenConstraintLibrary(),
    )

    assert result.decision is GateDecision.REJECT
    assert any(
        "current failure trajectory" in reason
        for reason in result.reasons
    )


def test_requires_verifier_approved_candidate():
    raw_candidate = make_candidate()
    diagnosis = make_diagnosis(raw_candidate)

    with pytest.raises(CurationGateError):
        CandidateCurationGate().evaluate(
            candidate=raw_candidate,
            diagnosis=diagnosis,
            trace=make_trace(),
            bank=FrozenConstraintLibrary(),
        )
