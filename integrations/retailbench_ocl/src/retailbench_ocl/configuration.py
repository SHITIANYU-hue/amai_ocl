"""V2 runtime configuration for the RetailBench host adapter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from aocl_core.audit import AuditSink
from aocl_core.evaluators import (
    ConstraintEvaluator,
    LexicalConstraintEvaluator,
    PromptedSemanticConstraintEvaluator,
    SemanticTextGenerator,
)
from aocl_core.library import FrozenConstraintLibrary
from aocl_core.policies import ControlMode
from aocl_core.retrieval import DeterministicLexicalRetriever
from aocl_core.runtime import IntegrationOCLRuntime

from .validators import RetailActionHardValidator
from .policy import RetailGovernancePolicy
from .validators import RetailOrganizationalPolicyValidator


EvaluatorMode = Literal["semantic", "lexical"]


@dataclass(frozen=True, slots=True)
class RetailBenchV2Config:
    """Configuration shared by short runs and later paired-rollout experiments."""

    constraint_bank: str | Path | None = None
    control_mode: ControlMode = ControlMode.BLOCKING
    evaluator_mode: EvaluatorMode = "semantic"
    retrieval_top_k: int = 3
    organizational_policy: RetailGovernancePolicy = RetailGovernancePolicy()

    def __post_init__(self) -> None:
        if not isinstance(self.control_mode, ControlMode):
            object.__setattr__(self, "control_mode", ControlMode(self.control_mode))
        if self.evaluator_mode not in {"semantic", "lexical"}:
            raise ValueError("evaluator_mode must be semantic or lexical")
        if self.retrieval_top_k <= 0:
            raise ValueError("retrieval_top_k must be greater than zero")


def load_constraint_bank(path: str | Path | None) -> FrozenConstraintLibrary:
    """Load one frozen Bank snapshot; omitted paths intentionally mean an empty Bank."""
    if path is None:
        return FrozenConstraintLibrary()
    source = Path(path).expanduser().resolve()
    if source.is_dir():
        source = source / "constraints.jsonl"
    return FrozenConstraintLibrary.from_jsonl(source)


def build_retailbench_v2_runtime(
    config: RetailBenchV2Config,
    *,
    semantic_generator: SemanticTextGenerator | None = None,
    audit_sink: AuditSink | None = None,
) -> IntegrationOCLRuntime:
    """Build execution-time governance from one fixed Constraint Bank snapshot."""
    library = load_constraint_bank(config.constraint_bank)
    evaluator: ConstraintEvaluator
    if config.evaluator_mode == "semantic":
        if semantic_generator is None:
            raise ValueError("semantic evaluator mode requires a semantic_generator")
        evaluator = PromptedSemanticConstraintEvaluator(semantic_generator)
    else:
        evaluator = LexicalConstraintEvaluator()

    kwargs = {}
    if audit_sink is not None:
        kwargs["audit_sink"] = audit_sink
    return IntegrationOCLRuntime(
        mode=config.control_mode,
        validators=(
            RetailActionHardValidator(),
            RetailOrganizationalPolicyValidator(config.organizational_policy),
        ),
        constraint_library=library,
        retriever=DeterministicLexicalRetriever(top_k=config.retrieval_top_k),
        constraint_evaluator=evaluator,
        **kwargs,
    )
