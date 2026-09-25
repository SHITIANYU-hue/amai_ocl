from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(
    "integrations/agenticpay_ocl_v2/results/"
    "eval60_cross_model_claude_v1"
)

df = pd.read_csv(ROOT / "case_results.csv")

# ============================================================
# Integrity checks
# ============================================================

assert len(df) == 180
assert df["profile_id"].nunique() == 30

for condition in ["EMPTY", "ALL26", "VALIDATED3"]:
    assert len(df[df["condition"] == condition]) == 60

    for repeat in [1, 2]:
        assert len(
            df[
                (df["condition"] == condition)
                & (df["repeat"] == repeat)
            ]
        ) == 30

assert (
    df[df["group"] == "attack"]["profile_id"].nunique()
    == 18
)

assert (
    df[df["group"] == "benign"]["profile_id"].nunique()
    == 12
)

CONDITIONS = [
    "EMPTY",
    "ALL26",
    "VALIDATED3",
]

METRICS = {
    "violation_rate": {
        "column": "policy_failure",
        "group": "attack",
    },
    "false_block_rate": {
        "column": "false_positive_intervention",
        "group": "benign",
    },
    "deal_rate": {
        "column": "task_progress",
        "group": None,
    },
    "valid_success_rate": {
        "column": "valid_success",
        "group": None,
    },
}

N_BOOT = 10000
SEED = 20260925
rng = np.random.default_rng(SEED)


def metric_subset(spec):
    if spec["group"] is None:
        return df.copy()

    return df[
        df["group"] == spec["group"]
    ].copy()


def profile_condition_values(data, condition, column):
    """
    One value per profile.
    The two repeats are averaged within profile first.
    """
    x = (
        data[data["condition"] == condition]
        .groupby("profile_id")[column]
        .mean()
        .sort_index()
    )

    return x


def bootstrap_mean(values):
    values = np.asarray(values, dtype=float)

    n = len(values)

    indices = rng.integers(
        0,
        n,
        size=(N_BOOT, n),
    )

    boot_means = values[indices].mean(axis=1)

    return (
        float(values.mean()),
        float(np.quantile(boot_means, 0.025)),
        float(np.quantile(boot_means, 0.975)),
    )


# ============================================================
# Condition-level estimates and 95% CI
# ============================================================

summary_rows = []

for condition in CONDITIONS:

    for metric_name, spec in METRICS.items():

        data = metric_subset(spec)

        values = profile_condition_values(
            data,
            condition,
            spec["column"],
        )

        estimate, lo, hi = bootstrap_mean(
            values.to_numpy()
        )

        summary_rows.append({
            "condition": condition,
            "metric": metric_name,
            "n_profiles": len(values),
            "estimate": estimate,
            "estimate_percent": estimate * 100,
            "ci_low": lo,
            "ci_high": hi,
            "ci_low_percent": lo * 100,
            "ci_high_percent": hi * 100,
            "ci_method":
                "profile-cluster bootstrap",
        })


summary = pd.DataFrame(summary_rows)

summary.to_csv(
    ROOT / "reduced_summary_ci.csv",
    index=False,
)


# ============================================================
# Paired difference versus EMPTY
# ============================================================

difference_rows = []

for comparison in [
    "ALL26",
    "VALIDATED3",
]:

    for metric_name, spec in METRICS.items():

        data = metric_subset(spec)

        empty = profile_condition_values(
            data,
            "EMPTY",
            spec["column"],
        )

        other = profile_condition_values(
            data,
            comparison,
            spec["column"],
        )

        # Exact same profiles are required for paired comparison.
        common = empty.index.intersection(
            other.index
        )

        empty = empty.loc[common]
        other = other.loc[common]

        paired_diff = (
            other.to_numpy()
            - empty.to_numpy()
        )

        n = len(paired_diff)

        indices = rng.integers(
            0,
            n,
            size=(N_BOOT, n),
        )

        boot_diffs = (
            paired_diff[indices]
            .mean(axis=1)
        )

        observed = float(
            paired_diff.mean()
        )

        lo = float(
            np.quantile(
                boot_diffs,
                0.025,
            )
        )

        hi = float(
            np.quantile(
                boot_diffs,
                0.975,
            )
        )

        difference_rows.append({
            "comparison":
                f"{comparison} - EMPTY",
            "metric":
                metric_name,
            "n_profiles":
                n,
            "difference":
                observed,
            "difference_pp":
                observed * 100,
            "ci_low":
                lo,
            "ci_high":
                hi,
            "ci_low_pp":
                lo * 100,
            "ci_high_pp":
                hi * 100,
            "ci_method":
                "paired profile-cluster bootstrap",
        })


differences = pd.DataFrame(
    difference_rows
)

differences.to_csv(
    ROOT / "paired_differences_ci.csv",
    index=False,
)


# ============================================================
# Statistical metadata
# ============================================================

with open(
    ROOT / "statistics_manifest.json",
    "w",
) as f:

    json.dump(
        {
            "confidence_level": 0.95,
            "bootstrap_iterations": N_BOOT,
            "random_seed": SEED,
            "cluster_unit": "profile_id",
            "repeats_per_profile": 2,
            "condition_ci_method":
                "profile-cluster bootstrap",
            "difference_ci_method":
                "paired profile-cluster bootstrap",
        },
        f,
        indent=2,
    )


# ============================================================
# Print results
# ============================================================

print(
    "\n=== CLAUDE CROSS-MODEL: 95% CI ==="
)

for condition in CONDITIONS:

    print(f"\n{condition}")

    temp = summary[
        summary["condition"] == condition
    ]

    for _, row in temp.iterrows():

        print(
            f"{row['metric']:22s} "
            f"{row['estimate_percent']:6.1f}% "
            f"[95% CI "
            f"{row['ci_low_percent']:.1f}%, "
            f"{row['ci_high_percent']:.1f}%]"
        )


print(
    "\n=== PAIRED DIFFERENCE VS EMPTY ==="
)

for _, row in differences.iterrows():

    print(
        f"{row['comparison']:20s} "
        f"{row['metric']:22s} "
        f"{row['difference_pp']:+6.1f} pp "
        f"[95% CI "
        f"{row['ci_low_pp']:+.1f}, "
        f"{row['ci_high_pp']:+.1f}]"
    )


print("\nSaved:")
print(ROOT / "reduced_summary_ci.csv")
print(ROOT / "paired_differences_ci.csv")
print(ROOT / "statistics_manifest.json")
