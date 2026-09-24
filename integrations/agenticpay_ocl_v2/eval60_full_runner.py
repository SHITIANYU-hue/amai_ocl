import csv
import json
from pathlib import Path
from statistics import mean

from aocl_core.versioning import VersionedLibraryStore
from agenticpay_ocl_v2.batch_experiment import (
    ModelProvider,
    _profiles,
    _evaluate_version,
)

ROOT = Path.cwd()

OLD_RUN = ROOT / (
    "integrations/agenticpay_ocl_v2/results/"
    "verifier_gate_bank_large_v1/run"
)

OUT = ROOT / (
    "integrations/agenticpay_ocl_v2/results/"
    "eval60_full_v1"
)
OUT.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------
# Base configuration: keep model/settings from large_v1
# --------------------------------------------------
base_config = json.load(open(OLD_RUN / "config.json"))

base_config["adversarial_profiles"] = (
    "/Users/liuyiou/amai_ocl/configs/adversarial_buyers_expanded.json"
)

base_config["benign_profiles"] = str(
    ROOT /
    "integrations/agenticpay_ocl_v2/data/"
    "benign_buyers_eval60.json"
)

base_config["split_manifest"] = str(
    ROOT /
    "integrations/agenticpay_ocl_v2/data/"
    "split_manifest_eval60.json"
)

# No learning or promotion in this experiment.
base_config["derivation_profile_ids"] = []
base_config["derivation_groups"] = []
base_config["validation_attack_profile_ids"] = []
base_config["validation_benign_profile_ids"] = []

# Read the frozen 60-case held-out set.
manifest = json.load(open(base_config["split_manifest"]))

base_config["evaluation_attack_profile_ids"] = manifest["evaluation"]
base_config["evaluation_benign_profile_ids"] = manifest["benign"]

assert len(base_config["evaluation_attack_profile_ids"]) == 45
assert len(base_config["evaluation_benign_profile_ids"]) == 15
assert (
    len(base_config["evaluation_attack_profile_ids"])
    + len(base_config["evaluation_benign_profile_ids"])
    == 60
)

# --------------------------------------------------
# Load the three frozen Bank conditions
# --------------------------------------------------
old_store = VersionedLibraryStore(OLD_RUN / "libraries")

all26_store = VersionedLibraryStore(
    ROOT /
    "integrations/agenticpay_ocl_v2/results/"
    "eval60_banks"
)

conditions = [
    ("EMPTY", old_store.load("L000")),
    ("ALL26", all26_store.load("ALL26")),
    ("VALIDATED3", old_store.load("L003")),
]

assert len(conditions[0][1].library.approved) == 0
assert len(conditions[1][1].library.approved) == 26
assert len(conditions[2][1].library.approved) == 3

# --------------------------------------------------
# Three independent repeats
# --------------------------------------------------
rows = []

for repeat in range(1, 4):

    repeat_dir = OUT / f"repeat_{repeat}"
    repeat_dir.mkdir(parents=True, exist_ok=True)

    config = dict(base_config)

    with open(repeat_dir / "config.json", "w") as f:
        json.dump(config, f, indent=2)

    provider = ModelProvider(config)
    profiles = _profiles(config)

    for condition_name, version in conditions:

        print(
            f"\n=== REPEAT {repeat} | "
            f"{condition_name} | "
            f"rules={len(version.library.approved)} ==="
        )

        metrics = _evaluate_version(
            repeat_dir,
            provider=provider,
            config=config,
            profiles=profiles,
            version=version,
            condition_id=condition_name,
        )

        row = {
            "repeat": repeat,
            "condition": condition_name,
            "library_size": metrics["library_size"],
            "episodes": metrics["episodes"],

            # Teacher-requested four metrics
            "violation_rate": metrics["policy_failure_rate"],
            "false_block_rate": metrics["benign_false_positive_rate"],
            "deal_rate": metrics["task_progress_rate"],
            "valid_success_rate": metrics["valid_success_rate"],

            # Secondary audit counts
            "executed_violation_steps":
                metrics["executed_violation_steps"],
            "blocked_violation_steps":
                metrics["blocked_violation_steps"],
            "blocked_safe_steps":
                metrics["blocked_safe_steps"],
        }

        rows.append(row)

        print(
            "violation={:.3f} | false_block={:.3f} | "
            "deal={:.3f} | valid_success={:.3f}".format(
                row["violation_rate"],
                row["false_block_rate"],
                row["deal_rate"],
                row["valid_success_rate"],
            )
        )

# --------------------------------------------------
# Save repeat-level results
# --------------------------------------------------
repeat_csv = OUT / "repeat_results.csv"

with open(repeat_csv, "w", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=list(rows[0].keys())
    )
    writer.writeheader()
    writer.writerows(rows)

# --------------------------------------------------
# Aggregate three repeats
# --------------------------------------------------
summary = []

for condition_name, _ in conditions:

    selected = [
        r for r in rows
        if r["condition"] == condition_name
    ]

    summary.append({
        "condition": condition_name,
        "library_size": selected[0]["library_size"],
        "repeats": len(selected),
        "episodes_per_repeat": selected[0]["episodes"],

        "violation_rate_mean":
            mean(r["violation_rate"] for r in selected),

        "false_block_rate_mean":
            mean(r["false_block_rate"] for r in selected),

        "deal_rate_mean":
            mean(r["deal_rate"] for r in selected),

        "valid_success_rate_mean":
            mean(r["valid_success_rate"] for r in selected),

        "executed_violation_steps_mean":
            mean(r["executed_violation_steps"] for r in selected),

        "blocked_safe_steps_mean":
            mean(r["blocked_safe_steps"] for r in selected),
    })

summary_csv = OUT / "summary.csv"

with open(summary_csv, "w", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=list(summary[0].keys())
    )
    writer.writeheader()
    writer.writerows(summary)

print("\n==============================")
print("FINAL AGGREGATE RESULTS")
print("==============================")

for r in summary:
    print(
        f"{r['condition']:12s} "
        f"| violation={r['violation_rate_mean']:.3f} "
        f"| false_block={r['false_block_rate_mean']:.3f} "
        f"| deal={r['deal_rate_mean']:.3f} "
        f"| valid_success={r['valid_success_rate_mean']:.3f}"
    )

print("\nrepeat results:", repeat_csv)
print("summary:", summary_csv)
