#!/usr/bin/env bash
set -euo pipefail

# Qwen Privacy 4/4/8 experiment with ablation enabled.
#
# Train / derivation:
#   4 privacy_phisher profiles
#
# Validation:
#   2 privacy_phisher + 2 benign profiles
#
# Test / evaluation:
#   4 privacy_phisher + 4 benign profiles
#
# Model:
#   qwen-plus
#
# Ablation:
#   enabled (no --skip-ablation)

: "${DASHSCOPE_API_KEY:?Please export DASHSCOPE_API_KEY first}"

for RUN in 1 2 3; do
  agenticpay-ocl-v2-batch-experiment \
    --model qwen-plus \
    --api-key-env DASHSCOPE_API_KEY \
    --base-url https://dashscope.aliyuncs.com/compatible-mode/v1 \
    --tactics privacy_phisher \
    --derivation-limit 4 \
    --validation-limit 2 \
    --evaluation-limit 4 \
    --max-rounds 4 \
    --maximum-revision-attempts 1 \
    --initial-price 180 \
    --buyer-max-price 120 \
    --seller-min-price 90 \
    --output-root "outputs/qwen_privacy_4_4_8_run${RUN}"
done
