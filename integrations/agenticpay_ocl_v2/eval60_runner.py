import json
from pathlib import Path

from aocl_core.versioning import VersionedLibraryStore
from agenticpay_ocl_v2.batch_experiment import (
    ModelProvider,
    _profiles,
    _evaluate_version,
)

ROOT = Path.cwd()

old_run = ROOT / (
    "integrations/agenticpay_ocl_v2/results/"
    "verifier_gate_bank_large_v1/run"
)

# 复用原 large_v1 的模型和运行配置
config = json.load(open(old_run / "config.json"))

# 换成新的 held-out 数据
config["adversarial_profiles"] = (
    "/Users/liuyiou/amai_ocl/configs/adversarial_buyers_expanded.json"
)
config["benign_profiles"] = str(
    ROOT / "integrations/agenticpay_ocl_v2/data/benign_buyers_eval60.json"
)
config["split_manifest"] = str(
    ROOT / "integrations/agenticpay_ocl_v2/data/split_manifest_eval60.json"
)

# Smoke test 不做 learning / validation
config["derivation_profile_ids"] = []
config["derivation_groups"] = []
config["validation_attack_profile_ids"] = []
config["validation_benign_profile_ids"] = []

# 三类攻击各1个 + benign 1个
config["evaluation_attack_profile_ids"] = [
    "privacy_phisher_077",
    "role_hijacker_077",
    "time_waster_077",
]
config["evaluation_benign_profile_ids"] = [
    "benign_buyer_011",
]

run_dir = (
    ROOT
    / "integrations/agenticpay_ocl_v2/results/eval60_smoke_v1"
)
run_dir.mkdir(parents=True, exist_ok=True)

with open(run_dir / "config.json", "w") as f:
    json.dump(config, f, indent=2)

provider = ModelProvider(config)
profiles = _profiles(config)

old_store = VersionedLibraryStore(old_run / "libraries")
all26_store = VersionedLibraryStore(
    ROOT / "integrations/agenticpay_ocl_v2/results/eval60_banks"
)

conditions = [
    ("EMPTY", old_store.load("L000")),
    ("ALL26", all26_store.load("ALL26")),
    ("VALIDATED3", old_store.load("L003")),
]

for name, version in conditions:
    print(f"\n=== {name} | rules={len(version.library.approved)} ===")

    m = _evaluate_version(
        run_dir,
        provider=provider,
        config=config,
        profiles=profiles,
        version=version,
        condition_id=name,
    )

    print("episodes:", m["episodes"])
    print("executed violations:", m["executed_violation_steps"])
    print("blocked safe:", m["blocked_safe_steps"])
    print("policy failure rate:", m["policy_failure_rate"])
    print("benign false positive:", m["benign_false_positive_rate"])
    print("task progress rate:", m["task_progress_rate"])
    print("valid success rate:", m["valid_success_rate"])

print("\nSMOKE TEST COMPLETE")
