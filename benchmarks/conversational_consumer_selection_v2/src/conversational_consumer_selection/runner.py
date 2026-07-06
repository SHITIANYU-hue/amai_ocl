"""Lightweight rollout helpers for the standalone benchmark."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from conversational_consumer_selection.env import BestOfferSelectionEnv
from conversational_consumer_selection.metrics import build_episode_record, summarize_records
from conversational_consumer_selection.policies import Policy
from conversational_consumer_selection.schemas import SelectionTask


def run_episode(
    task: SelectionTask,
    policy: Policy,
    *,
    env: BestOfferSelectionEnv | None = None,
) -> dict[str, Any]:
    """Run one decision policy on one task until termination.

    Inputs are a `SelectionTask`, a policy implementing `act(observation)`, and
    optionally a preconfigured environment. The returned dictionary is the
    terminal episode summary emitted by the environment.
    """

    active_env = env or BestOfferSelectionEnv()
    observation, info = active_env.reset(task=task)
    while not observation.terminated:
        action = policy.act(observation)
        observation, _, _, _, info = active_env.step(action)
    return info


def run_benchmark(
    tasks: Iterable[SelectionTask],
    policies: Mapping[str, Policy],
    *,
    output_dir: str | Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run a set of decision policies across tasks and optionally write summaries.

    Inputs are an iterable of tasks, named policies, and an optional output
    directory. The function returns per-episode records and grouped summary
    rows; if `output_dir` is provided, both are also written to disk.
    """

    records: list[dict[str, Any]] = []
    for task in tasks:
        for arm, policy in policies.items():
            info = run_episode(task, policy)
            records.append(
                build_episode_record(
                    info,
                    arm=arm,
                    setting=task.level.value,
                )
            )
    summaries = summarize_records(records)
    if output_dir is not None:
        write_summary_files(output_dir=output_dir, records=records, summaries=summaries)
    return records, summaries


def write_summary_files(
    *,
    output_dir: str | Path,
    records: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
) -> None:
    """Write per-episode and summary outputs to JSON and CSV.

    Inputs are an output directory plus already-normalized record and summary
    dictionaries. The function creates the directory if needed and returns
    nothing.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    (output_path / "records.json").write_text(
        json.dumps(records, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_path / "summary.json").write_text(
        json.dumps(summaries, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_csv(output_path / "summary.csv", summaries)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write homogeneous dictionaries to a CSV file at `path`."""

    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
