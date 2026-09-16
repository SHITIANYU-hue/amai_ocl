"""Deterministic retrieval over observable host-action context."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Protocol, Sequence

from .contracts import ObservableContext, ProposedAction
from .library import FrozenConstraintLibrary, SoftConstraint


_TOKEN_RE = re.compile(r"\w+", flags=re.UNICODE)


def normalize_text(value: str) -> str:
    return " ".join(_TOKEN_RE.findall(value.casefold().replace("_", " ")))


def tokens(value: str) -> frozenset[str]:
    return frozenset(_TOKEN_RE.findall(value.casefold().replace("_", " ")))


def _visible_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        result: list[str] = []
        for key in sorted(value):
            result.append(str(key))
            result.extend(_visible_strings(value[key]))
        return result
    if isinstance(value, (tuple, list)):
        result = []
        for item in value:
            result.extend(_visible_strings(item))
        return result
    return []


def observable_query(action: ProposedAction, context: ObservableContext) -> str:
    parts: list[str] = [action.action_type]
    parts.extend(_visible_strings(context.dialogue))
    parts.extend(_visible_strings(context.visible_state))
    if action.visible_text:
        parts.append(action.visible_text)
    parts.extend(_visible_strings(action.payload))
    return normalize_text(" ".join(parts))


@dataclass(frozen=True, slots=True)
class RetrievedConstraint:
    constraint: SoftConstraint
    score: float
    rank: int


class ConstraintRetriever(Protocol):
    def retrieve(
        self,
        action: ProposedAction,
        context: ObservableContext,
        library: FrozenConstraintLibrary,
    ) -> Sequence[RetrievedConstraint]: ...


@dataclass(frozen=True, slots=True)
class DeterministicLexicalRetriever:
    top_k: int = 3

    def __post_init__(self) -> None:
        if self.top_k <= 0:
            raise ValueError("top_k must be greater than zero")

    def retrieve(
        self,
        action: ProposedAction,
        context: ObservableContext,
        library: FrozenConstraintLibrary,
    ) -> Sequence[RetrievedConstraint]:
        query = observable_query(action, context)
        query_tokens = tokens(query)
        scored: list[tuple[float, SoftConstraint]] = []
        for constraint in library.approved:
            if action.action_type not in constraint.action_types and "*" not in constraint.action_types:
                continue
            keyword_hits = sum(
                1
                for keyword in constraint.keywords
                if normalize_text(keyword) and normalize_text(keyword) in query
            )
            tactic_overlap = len(tokens(constraint.tactic_type) & query_tokens)
            trigger_overlap = len(tokens(constraint.trigger_pattern) & query_tokens)
            score = float(keyword_hits * 4 + trigger_overlap * 2 + tactic_overlap)
            if score > 0:
                scored.append((score, constraint))
        scored.sort(key=lambda item: (-item[0], item[1].constraint_id))
        return tuple(
            RetrievedConstraint(constraint=constraint, score=score, rank=index + 1)
            for index, (score, constraint) in enumerate(scored[: self.top_k])
        )
