"""Build bootstrap confidence-interval tables from benchmark_results.json.

The bootstrap unit is one profile/episode_index. For each resample, the script
samples profiles with replacement and recomputes arm-level means. This keeps
the paired profile design intact and avoids treating arms from the same profile
as independent observations.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any


DEFAULT_METRICS = (
    ("has_executed_violation", "exec_viol", "executed_violation_rate"),
    ("unsafe_success", "unsafe_success", "unsafe_success_rate"),
    ("valid_success", "valid_success", "valid_success_rate"),
    ("success", "success", "success_rate"),
    ("round", "avg_round", "avg_round"),
)

CSV_METRICS = (
    ("has_executed_violation", "executed_violation_rate"),
    ("unsafe_success", "unsafe_success_rate"),
    ("valid_success", "valid_success_rate"),
    ("success", "success_rate"),
    ("round", "avg_round"),
    ("seller_reward", "avg_seller_reward"),
    ("latency_sec", "avg_latency_sec"),
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize benchmark results with profile-level bootstrap CI."
    )
    parser.add_argument("results_json", help="Path to benchmark_results.json")
    parser.add_argument("--samples", type=int, default=5000, help="Bootstrap samples")
    parser.add_argument("--seed", type=int, default=123, help="Bootstrap RNG seed")
    parser.add_argument(
        "--by-persona",
        action="store_true",
        help="Also print one arm table per persona_type.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional markdown output path. Defaults to stdout only.",
    )
    parser.add_argument(
        "--csv-prefix",
        default=None,
        help=(
            "Optional CSV output prefix. Writes <prefix>_summary_ci.csv, "
            "<prefix>_persona_ci.csv when --by-persona is set, and "
            "<prefix>_records.csv."
        ),
    )
    args = parser.parse_args()

    records = _load_records(Path(args.results_json))
    if not records:
        raise SystemExit("No records found.")

    sections = [
        _render_table(
            title="Overall",
            records=records,
            samples=args.samples,
            seed=args.seed,
        )
    ]
    if args.by_persona:
        for persona in sorted({str(r.get("persona_type", "unknown")) for r in records}):
            rows = [r for r in records if str(r.get("persona_type", "unknown")) == persona]
            sections.append(
                _render_table(
                    title=f"Persona: {persona}",
                    records=rows,
                    samples=args.samples,
                    seed=args.seed + _stable_string_seed(persona),
                )
            )

    output = "\n\n".join(sections)
    print(output)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output + "\n", encoding="utf-8")
    if args.csv_prefix:
        _write_csv_outputs(
            records=records,
            prefix=Path(args.csv_prefix),
            samples=args.samples,
            seed=args.seed,
            by_persona=args.by_persona,
        )
    return 0


def _load_records(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    records = payload.get("records", []) if isinstance(payload, dict) else []
    if not isinstance(records, list):
        return []
    return [r for r in records if isinstance(r, dict)]


def _render_table(
    *,
    title: str,
    records: list[dict[str, Any]],
    samples: int,
    seed: int,
) -> str:
    arms = sorted({str(r.get("arm", "")) for r in records if r.get("arm")})
    lines = [
        f"### {title}",
        "",
        f"Bootstrap unit: profile/episode_index; samples={samples}; CI=95%.",
        "",
        "| arm | n_profiles | exec_viol | unsafe_success | valid_success | success | avg_round |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for arm in arms:
        arm_rows = [r for r in records if str(r.get("arm", "")) == arm]
        profile_count = len({int(r["episode_index"]) for r in arm_rows if "episode_index" in r})
        cells = [
            f"`{arm}`",
            str(profile_count),
        ]
        for metric_key, _label, _csv_label in DEFAULT_METRICS:
            estimate, lower, upper = bootstrap_mean_ci(
                arm_rows,
                metric_key=metric_key,
                samples=samples,
                seed=seed + sum(ord(ch) for ch in arm + metric_key),
            )
            cells.append(_fmt_ci(estimate, lower, upper))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _write_csv_outputs(
    *,
    records: list[dict[str, Any]],
    prefix: Path,
    samples: int,
    seed: int,
    by_persona: bool,
) -> None:
    prefix.parent.mkdir(parents=True, exist_ok=True)
    _write_summary_csv(
        prefix.with_name(prefix.name + "_summary_ci.csv"),
        records=records,
        group_name="overall",
        samples=samples,
        seed=seed,
    )
    if by_persona:
        persona_rows: list[dict[str, Any]] = []
        for persona in sorted({str(r.get("persona_type", "unknown")) for r in records}):
            rows = [r for r in records if str(r.get("persona_type", "unknown")) == persona]
            persona_rows.extend(
                _summary_rows(
                    records=rows,
                    group_name=persona,
                    samples=samples,
                    seed=seed + _stable_string_seed(persona),
                )
            )
        _write_csv_rows(prefix.with_name(prefix.name + "_persona_ci.csv"), persona_rows)
    _write_records_csv(prefix.with_name(prefix.name + "_records.csv"), records)


def _write_summary_csv(
    path: Path,
    *,
    records: list[dict[str, Any]],
    group_name: str,
    samples: int,
    seed: int,
) -> None:
    rows = _summary_rows(records=records, group_name=group_name, samples=samples, seed=seed)
    _write_csv_rows(path, rows)


def _summary_rows(
    *,
    records: list[dict[str, Any]],
    group_name: str,
    samples: int,
    seed: int,
) -> list[dict[str, Any]]:
    rows = []
    for arm in sorted({str(r.get("arm", "")) for r in records if r.get("arm")}):
        arm_rows = [r for r in records if str(r.get("arm", "")) == arm]
        row: dict[str, Any] = {
            "group": group_name,
            "arm": arm,
            "n_profiles": len(
                {int(r["episode_index"]) for r in arm_rows if "episode_index" in r}
            ),
            "n_records": len(arm_rows),
        }
        for metric_key, label in CSV_METRICS:
            estimate, lower, upper = bootstrap_mean_ci(
                arm_rows,
                metric_key=metric_key,
                samples=samples,
                seed=seed + sum(ord(ch) for ch in arm + metric_key),
            )
            row[label] = round(estimate, 4)
            row[f"{label}_ci95_low"] = round(lower, 4)
            row[f"{label}_ci95_high"] = round(upper, 4)
        row["executed_violation_type_counts_json"] = json.dumps(
            _sum_count_dicts(arm_rows, "executed_violation_type_counts"),
            sort_keys=True,
        )
        row["guard_violation_type_counts_json"] = json.dumps(
            _sum_count_dicts(arm_rows, "violation_type_counts"),
            sort_keys=True,
        )
        rows.append(row)
    return rows


def _write_csv_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_records_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fieldnames = sorted({key for row in records for key in row})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in records:
            writer.writerow(
                {
                    key: json.dumps(value, sort_keys=True)
                    if isinstance(value, (dict, list))
                    else value
                    for key, value in row.items()
                }
            )


def _sum_count_dicts(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    totals: defaultdict[str, int] = defaultdict(int)
    for row in records:
        counts = row.get(field)
        if not isinstance(counts, dict):
            continue
        for key, value in counts.items():
            totals[str(key)] += int(value)
    return dict(sorted(totals.items()))


def bootstrap_mean_ci(
    records: list[dict[str, Any]],
    *,
    metric_key: str,
    samples: int,
    seed: int,
) -> tuple[float, float, float]:
    """Return (mean, lower, upper) for a metric using profile bootstrap."""
    by_profile: dict[int, dict[str, Any]] = {}
    for row in records:
        if "episode_index" not in row:
            continue
        by_profile[int(row["episode_index"])] = row

    profile_ids = sorted(by_profile)
    values = [_to_float(by_profile[idx].get(metric_key)) for idx in profile_ids]
    estimate = _mean(values)
    if not profile_ids or samples <= 0:
        return estimate, estimate, estimate

    rng = random.Random(seed)
    boot_means: list[float] = []
    for _ in range(samples):
        boot_values = [
            _to_float(by_profile[rng.choice(profile_ids)].get(metric_key))
            for _idx in profile_ids
        ]
        boot_means.append(_mean(boot_values))

    boot_means.sort()
    lo_idx = int(0.025 * (samples - 1))
    hi_idx = int(0.975 * (samples - 1))
    return estimate, boot_means[lo_idx], boot_means[hi_idx]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fmt_ci(estimate: float, lower: float, upper: float) -> str:
    return f"{estimate:.2f} [{lower:.2f}, {upper:.2f}]"


def _stable_string_seed(text: str) -> int:
    return sum((idx + 1) * ord(ch) for idx, ch in enumerate(text)) % 100_000


if __name__ == "__main__":
    raise SystemExit(main())
