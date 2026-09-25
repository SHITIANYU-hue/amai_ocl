import csv
import json
import time
from pathlib import Path
from statistics import mean

from aocl_core.versioning import VersionedLibraryStore

from agenticpay_ocl_v2.batch_experiment import (
    ModelProvider,
    _profiles,
    _evaluate_version,
    _rollout_case,
    _evaluation_record,
)

from agenticpay_ocl_v2.adaptive_demo import (
    _read_json,
    _outcome_label_from_dict,
    _episode_summary,
)

from agenticpay_ocl_v2.claude_executor import ClaudeLLM


ROOT = Path.cwd()

OLD_RUN = ROOT / (
    "integrations/agenticpay_ocl_v2/results/"
    "verifier_gate_bank_large_v1/run"
)

OUT = ROOT / (
    "integrations/agenticpay_ocl_v2/results/"
    "eval60_cross_model_claude_v1"
)

OUT.mkdir(parents=True, exist_ok=True)


# ============================================================
# Retry wrappers
# ============================================================

def retryable_error(exc: Exception) -> bool:
    text = str(exc).lower()

    markers = (
        "timeout",
        "timed out",
        "connection",
        "temporarily",
        "rate limit",
        "429",
        "502",
        "503",
        "504",
    )

    return any(marker in text for marker in markers)


class RetryLLM:
    def __init__(self, inner, attempts=3):
        self.inner = inner
        self.attempts = attempts

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def generate(self, *args, **kwargs):
        last = None

        for attempt in range(1, self.attempts + 1):
            try:
                return self.inner.generate(*args, **kwargs)

            except Exception as exc:
                last = exc

                if not retryable_error(exc):
                    raise

                print(
                    f"[retry executor] attempt "
                    f"{attempt}/{self.attempts}: {exc}",
                    flush=True,
                )

                if attempt < self.attempts:
                    time.sleep(3 * attempt)

        raise last


class RetryGenerator:
    def __init__(self, inner, attempts=3):
        self.inner = inner
        self.attempts = attempts

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def generate(self, *args, **kwargs):
        last = None

        for attempt in range(1, self.attempts + 1):
            try:
                return self.inner.generate(*args, **kwargs)

            except Exception as exc:
                last = exc

                if not retryable_error(exc):
                    raise

                print(
                    f"[retry gate/judge] attempt "
                    f"{attempt}/{self.attempts}: {exc}",
                    flush=True,
                )

                if attempt < self.attempts:
                    time.sleep(3 * attempt)

        raise last


# ============================================================
# Split provider
#
# client()         -> Claude executor
# json_generator() -> frozen Qwen gate/judge
# ============================================================

class SplitProvider:
    def __init__(self, judge_gate_provider):
        self.judge_gate_provider = judge_gate_provider

    def client(self):
        return RetryLLM(
            ClaudeLLM(model="claude-sonnet-5"),
            attempts=3,
        )

    def json_generator(self, *, max_tokens=800):
        return RetryGenerator(
            self.judge_gate_provider.json_generator(
                max_tokens=max_tokens
            ),
            attempts=3,
        )


# ============================================================
# Frozen configuration from Experiment 1
# ============================================================

base_config = json.load(
    open(OLD_RUN / "config.json")
)

base_config["adversarial_profiles"] = (
    "/Users/liuyiou/amai_ocl/configs/"
    "adversarial_buyers_expanded.json"
)

base_config["benign_profiles"] = str(
    ROOT
    / "integrations/agenticpay_ocl_v2/data/"
    "benign_buyers_eval60.json"
)

base_config["split_manifest"] = str(
    ROOT
    / "integrations/agenticpay_ocl_v2/data/"
    "split_manifest_eval60.json"
)

# Evaluation only.
base_config["derivation_profile_ids"] = []
base_config["derivation_groups"] = []
base_config["validation_attack_profile_ids"] = []
base_config["validation_benign_profile_ids"] = []

manifest = json.load(
    open(base_config["split_manifest"])
)

# ------------------------------------------------------------
# Deterministic, outcome-independent reduced cross-model subset
# 18 risky = 6 per attack family
# 12 benign
# ------------------------------------------------------------

import hashlib


def stable_key(profile_id):
    payload = (
        "claude-cross-model-v1::"
        + profile_id
    ).encode("utf-8")

    return hashlib.sha256(payload).hexdigest()


attack_groups = {
    "privacy": [],
    "role_hijacker": [],
    "time_waster": [],
}

for profile_id in manifest["evaluation"]:
    lower = profile_id.lower()

    if "privacy" in lower:
        attack_groups["privacy"].append(profile_id)

    elif "role" in lower or "hijack" in lower:
        attack_groups["role_hijacker"].append(profile_id)

    elif "time" in lower or "waster" in lower:
        attack_groups["time_waster"].append(profile_id)

    else:
        raise ValueError(
            "Unable to classify attack profile: "
            + profile_id
        )


selected_attack_ids = []

for family in (
    "privacy",
    "role_hijacker",
    "time_waster",
):
    candidates = sorted(
        attack_groups[family],
        key=stable_key,
    )

    assert len(candidates) >= 6, (
        family,
        len(candidates),
    )

    selected_attack_ids.extend(
        candidates[:6]
    )


selected_benign_ids = sorted(
    manifest["benign"],
    key=stable_key,
)[:12]


base_config[
    "evaluation_attack_profile_ids"
] = selected_attack_ids

base_config[
    "evaluation_benign_profile_ids"
] = selected_benign_ids


assert len(selected_attack_ids) == 18
assert len(selected_benign_ids) == 12
assert (
    len(selected_attack_ids)
    + len(selected_benign_ids)
    == 30
)


selection = {
    "selection_method":
        "SHA256 deterministic ordering; "
        "independent of model outcomes",
    "privacy":
        sorted(
            attack_groups["privacy"],
            key=stable_key,
        )[:6],
    "role_hijacker":
        sorted(
            attack_groups["role_hijacker"],
            key=stable_key,
        )[:6],
    "time_waster":
        sorted(
            attack_groups["time_waster"],
            key=stable_key,
        )[:6],
    "benign":
        selected_benign_ids,
}

with open(
    OUT / "selected_profiles.json",
    "w",
) as f:
    json.dump(
        selection,
        f,
        indent=2,
    )


# ============================================================
# Gate and judge remain Qwen-plus
# ============================================================

assert base_config["model"] == "qwen-plus"
assert (
    base_config["api_key_env"]
    == "DASHSCOPE_API_KEY"
)

qwen_provider = ModelProvider(base_config)

provider = SplitProvider(qwen_provider)


# ============================================================
# Frozen Bank conditions
# ============================================================

old_store = VersionedLibraryStore(
    OLD_RUN / "libraries"
)

all26_store = VersionedLibraryStore(
    ROOT
    / "integrations/agenticpay_ocl_v2/results/"
    "eval60_banks"
)

conditions = [
    (
        "EMPTY",
        old_store.load("L000"),
    ),
    (
        "ALL26",
        all26_store.load("ALL26"),
    ),
    (
        "VALIDATED3",
        old_store.load("L003"),
    ),
]

assert (
    len(conditions[0][1].library.approved)
    == 0
)

assert (
    len(conditions[1][1].library.approved)
    == 26
)

assert (
    len(conditions[2][1].library.approved)
    == 3
)


# ============================================================
# Experiment manifest
# ============================================================

experiment_manifest = {
    "experiment": "agenticpay_cross_model_claude_reduced",
    "executor_model": "claude-sonnet-5",
    "executor_provider": "anthropic",
    "gate_model": "qwen-plus",
    "judge_model": "qwen-plus",
    "attack_cases": 18,
    "benign_cases": 12,
    "cases_per_condition": 30,
    "conditions": [
        "EMPTY",
        "ALL26",
        "VALIDATED3",
    ],
    "repeats": 2,
    "episodes_total": 180,
    "split_manifest":
        base_config["split_manifest"],
    "banks": {
        name: {
            "size":
                len(version.library.approved),
            "digest":
                version.library.digest,
        }
        for name, version in conditions
    },
}

with open(
    OUT / "experiment_manifest.json",
    "w",
) as f:
    json.dump(
        experiment_manifest,
        f,
        indent=2,
    )


# ============================================================
# Helper: save CSV incrementally
# ============================================================

def save_csv(path, rows):
    if not rows:
        return

    with open(
        path,
        "w",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(rows[0].keys()),
        )

        writer.writeheader()
        writer.writerows(rows)


# ============================================================
# Main experiment
# ============================================================

repeat_rows = []
case_rows = []

profiles = _profiles(base_config)


for repeat in range(1, 3):

    repeat_dir = (
        OUT / f"repeat_{repeat}"
    )

    repeat_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    run_config = dict(base_config)

    run_config.update({
        "executor_model":
            "claude-sonnet-5",
        "executor_provider":
            "anthropic",
        "gate_model":
            "qwen-plus",
        "judge_model":
            "qwen-plus",
        "repeat":
            repeat,
    })

    with open(
        repeat_dir / "config.json",
        "w",
    ) as f:
        json.dump(
            run_config,
            f,
            indent=2,
        )

    for condition_name, version in conditions:

        print(
            "\n======================================"
        )

        print(
            f"CLAUDE | REPEAT {repeat} | "
            f"{condition_name} | "
            f"rules={len(version.library.approved)}"
        )

        print(
            "======================================"
        )

        metrics = _evaluate_version(
            repeat_dir,
            provider=provider,
            config=base_config,
            profiles=profiles,
            version=version,
            condition_id=condition_name,
        )

        repeat_row = {
            "executor_model":
                "claude-sonnet-5",
            "gate_model":
                "qwen-plus",
            "judge_model":
                "qwen-plus",
            "repeat":
                repeat,
            "condition":
                condition_name,
            "library_size":
                metrics["library_size"],
            "episodes":
                metrics["episodes"],
            "violation_rate":
                metrics["policy_failure_rate"],
            "false_block_rate":
                metrics[
                    "benign_false_positive_rate"
                ],
            "deal_rate":
                metrics["task_progress_rate"],
            "valid_success_rate":
                metrics["valid_success_rate"],
            "executed_violation_steps":
                metrics[
                    "executed_violation_steps"
                ],
            "blocked_violation_steps":
                metrics[
                    "blocked_violation_steps"
                ],
            "blocked_safe_steps":
                metrics[
                    "blocked_safe_steps"
                ],
        }

        repeat_rows.append(
            repeat_row
        )

        save_csv(
            OUT / "repeat_results.csv",
            repeat_rows,
        )

        # ----------------------------------------------------
        # Recover case-level records from saved artifacts.
        # These are retained for CI / bootstrap analysis.
        # ----------------------------------------------------

        evaluation_dir = (
            repeat_dir
            / "evaluations"
            / condition_name
        )

        groups = (
            (
                "attack",
                base_config[
                    "evaluation_attack_profile_ids"
                ],
            ),
            (
                "benign",
                base_config[
                    "evaluation_benign_profile_ids"
                ],
            ),
        )

        for group, profile_ids in groups:

            for profile_id in profile_ids:

                episode_path = (
                    evaluation_dir
                    / f"{group}_{profile_id}_episode.json"
                )

                label_path = (
                    evaluation_dir
                    / f"{group}_{profile_id}_label.json"
                )

                artifact = _read_json(
                    episode_path
                )

                label_artifact = _read_json(
                    label_path
                )

                label = _outcome_label_from_dict(
                    label_artifact["label"]
                )

                rollout = _rollout_case(
                    group=group,
                    profile_id=profile_id,
                    artifact=artifact,
                    label=label,
                )

                record = _evaluation_record(
                    group=group,
                    profile=profiles[profile_id],
                    summary=_episode_summary(
                        artifact,
                        label,
                    ),
                    rollout=rollout,
                )

                case_rows.append({
                    "executor_model":
                        "claude-sonnet-5",
                    "gate_model":
                        "qwen-plus",
                    "judge_model":
                        "qwen-plus",
                    "repeat":
                        repeat,
                    "condition":
                        condition_name,
                    "library_size":
                        len(
                            version.library.approved
                        ),
                    "library_digest":
                        version.library.digest,
                    "group":
                        group,
                    "profile_id":
                        profile_id,
                    "persona_type":
                        record.get(
                            "persona_type"
                        ),
                    "policy_failure":
                        int(
                            bool(
                                record.get(
                                    "policy_failure"
                                )
                            )
                        ),
                    "false_positive_intervention":
                        int(
                            bool(
                                record.get(
                                    "false_positive_intervention"
                                )
                            )
                        ),
                    "task_progress":
                        int(
                            bool(
                                record.get(
                                    "task_progress"
                                )
                            )
                        ),
                    "valid_success":
                        int(
                            bool(
                                record.get(
                                    "valid_success"
                                )
                            )
                        ),
                    "proposal_steps":
                        record.get(
                            "proposal_steps",
                            0,
                        ),
                    "policy_violation_steps":
                        record.get(
                            "policy_violation_steps",
                            0,
                        ),
                    "executed_violation_steps":
                        record.get(
                            "executed_violation_steps",
                            0,
                        ),
                    "blocked_violation_steps":
                        record.get(
                            "blocked_violation_steps",
                            0,
                        ),
                    "blocked_safe_steps":
                        record.get(
                            "blocked_safe_steps",
                            0,
                        ),
                    "candidate_intercept_steps":
                        record.get(
                            "candidate_intercept_steps",
                            0,
                        ),
                })

        save_csv(
            OUT / "case_results.csv",
            case_rows,
        )

        print(
            "violation={:.3f} | "
            "false_block={:.3f} | "
            "deal={:.3f} | "
            "valid_success={:.3f}".format(
                repeat_row[
                    "violation_rate"
                ],
                repeat_row[
                    "false_block_rate"
                ],
                repeat_row[
                    "deal_rate"
                ],
                repeat_row[
                    "valid_success_rate"
                ],
            )
        )


# ============================================================
# Aggregate means
# ============================================================

summary_rows = []

for condition_name, _ in conditions:

    selected = [
        row
        for row in repeat_rows
        if row["condition"]
        == condition_name
    ]

    summary_rows.append({
        "executor_model":
            "claude-sonnet-5",
        "gate_model":
            "qwen-plus",
        "judge_model":
            "qwen-plus",
        "condition":
            condition_name,
        "library_size":
            selected[0][
                "library_size"
            ],
        "repeats":
            len(selected),
        "episodes_per_repeat":
            selected[0]["episodes"],
        "violation_rate_mean":
            mean(
                row["violation_rate"]
                for row in selected
            ),
        "false_block_rate_mean":
            mean(
                row["false_block_rate"]
                for row in selected
            ),
        "deal_rate_mean":
            mean(
                row["deal_rate"]
                for row in selected
            ),
        "valid_success_rate_mean":
            mean(
                row["valid_success_rate"]
                for row in selected
            ),
        "executed_violation_steps_mean":
            mean(
                row[
                    "executed_violation_steps"
                ]
                for row in selected
            ),
        "blocked_safe_steps_mean":
            mean(
                row[
                    "blocked_safe_steps"
                ]
                for row in selected
            ),
    })


save_csv(
    OUT / "summary.csv",
    summary_rows,
)


print(
    "\n======================================"
)
print(
    "CLAUDE CROSS-MODEL FINAL RESULTS"
)
print(
    "Executor: claude-sonnet-5"
)
print(
    "Gate/Judge: qwen-plus"
)
print(
    "======================================"
)

for row in summary_rows:
    print(
        f"{row['condition']:12s} "
        f"| violation="
        f"{row['violation_rate_mean']:.3f} "
        f"| false_block="
        f"{row['false_block_rate_mean']:.3f} "
        f"| deal="
        f"{row['deal_rate_mean']:.3f} "
        f"| valid_success="
        f"{row['valid_success_rate_mean']:.3f}"
    )


print(
    "\ncase results:",
    OUT / "case_results.csv",
)

print(
    "repeat results:",
    OUT / "repeat_results.csv",
)

print(
    "summary:",
    OUT / "summary.csv",
)

print(
    "manifest:",
    OUT / "experiment_manifest.json",
)
