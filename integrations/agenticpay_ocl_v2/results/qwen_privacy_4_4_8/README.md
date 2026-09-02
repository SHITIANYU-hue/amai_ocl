# Qwen Privacy Constraint-Bank Experiment

Model: `qwen-plus`

Experiment protocol:

- Tactic: `privacy_phisher`
- Training / derivation: 4 attack profiles
- Validation: 2 attack + 2 benign profiles
- Test / evaluation: 4 attack + 4 benign profiles
- Independent runs: 3
- Max negotiation rounds: 4

Each run contains:

- `config.json`: experiment configuration
- `report.json`: main constraint-bank learning experiment
- `growth_curve.csv`: bank/evaluation checkpoints
- `ablation_report.json`: ablation results

The three runs correspond to the Qwen experiments used for comparison with the GPT-based Privacy 4/4/8 experiment.

Note: the later 12-train / 8-validation / 16-test integrated exploratory run is not included here.

## Reproduction

`run_qwen_ablation.sh` reproduces the configuration used for the three
existing Qwen runs.

Important configuration details:

- Model: `qwen-plus`
- Ablation evaluation: enabled
- Candidate instruction skill: not supplied (`None`)
- Source code used for the original runs: commit `ddbe107`
- The later repository update to `78963e7` only added the experiment notebook;
  the underlying batch experiment implementation was unchanged.

The 12/8/16 multi-tactic exploratory run is not part of this result set.
