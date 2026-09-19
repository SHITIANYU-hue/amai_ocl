from types import SimpleNamespace

from aocl_core.learning import CandidateDiagnosis
from aocl_core.library import (
    ConstraintResponse,
    ConstraintStatus,
    FrozenConstraintLibrary,
    SoftConstraint,
)
from agenticpay_ocl_v2.batch_experiment import (
    _run_candidate_curation_gate,
    build_parser,
)


def make_candidate(
    *,
    constraint_id="candidate_1",
    instruction="Do not repeat an action after a hard boundary is enforced.",
):
    return SoftConstraint(
        constraint_id=constraint_id,
        action_types=("proposal",),
        tactic_type="boundary",
        trigger_pattern="repeated action after hard boundary",
        keywords=("repeat", "boundary"),
        instruction=instruction,
        response=ConstraintResponse.BLOCK,
        status=ConstraintStatus.CANDIDATE,
        source_episode_ids=("episode_1",),
        metadata={
            "scenario_id": "scenario_1",
            "scope": "task_specific",
        },
    )


def make_diagnosis(candidate):
    return CandidateDiagnosis(
        constraint=candidate,
        earliest_detectable_step=1,
        visible_evidence=("hard boundary already enforced",),
        rationale="Repeated blocked action.",
    )


def make_trace():
    return SimpleNamespace(
        episode_id="episode_1",
        scenario_id="scenario_1",
    )


def make_parent(library=None):
    return SimpleNamespace(
        library=library or FrozenConstraintLibrary(),
    )


def test_batch_gate_flag_defaults_off():
    args = build_parser().parse_args([])
    assert args.candidate_curation_gate is False


def test_batch_gate_flag_can_be_enabled():
    args = build_parser().parse_args(
        ["--candidate-curation-gate"]
    )
    assert args.candidate_curation_gate is True


def test_batch_gate_bypass_returns_none():
    raw = make_candidate()

    result = _run_candidate_curation_gate(
        enabled=False,
        candidate=raw.approved_copy(),
        diagnosis=make_diagnosis(raw),
        trace=make_trace(),
        parent=make_parent(),
    )

    assert result is None


def test_batch_gate_accepts_unique_verified_candidate():
    raw = make_candidate()

    result = _run_candidate_curation_gate(
        enabled=True,
        candidate=raw.approved_copy(),
        diagnosis=make_diagnosis(raw),
        trace=make_trace(),
        parent=make_parent(),
    )

    assert result is not None
    assert result.accepted


def test_batch_gate_blocks_existing_duplicate():
    existing = make_candidate(
        constraint_id="existing_1",
    ).approved_copy()

    raw = make_candidate(
        constraint_id="candidate_2",
    )

    result = _run_candidate_curation_gate(
        enabled=True,
        candidate=raw.approved_copy(),
        diagnosis=make_diagnosis(raw),
        trace=make_trace(),
        parent=make_parent(
            FrozenConstraintLibrary((existing,))
        ),
    )

    assert result is not None
    assert not result.accepted
    assert result.duplicate_of == "existing_1"
