import argparse
import hashlib
import json
import os
import re
from collections import defaultdict
from pathlib import Path

import agenticpay
from agenticpay.agents.buyer_agent import BuyerAgent
from agenticpay.agents.seller_agent import SellerAgent
from agenticpay.models.openai_llm import OpenAILLM
from loguru import logger


# Keep terminal clean: AgenticPay mental-model logs are not part of the dataset.
logger.remove()


def normalize_dialogue(turns):
    parts = []
    for turn in turns:
        buyer = re.sub(r"\s+", " ", turn["buyer_message"] or "").strip().lower()
        seller = re.sub(r"\s+", " ", turn["seller_message"] or "").strip().lower()
        parts.append(f"buyer:{buyer}")
        parts.append(f"seller:{seller}")
    return "\n".join(parts)


def dialogue_hash(turns):
    text = normalize_dialogue(turns)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def existing_state(path):
    completed_ids = set()
    hashes = set()

    if not path.exists():
        return completed_ids, hashes

    text = path.read_text(encoding="utf-8")

    completed_ids.update(
        re.findall(r"^Profile ID:\s*(.+)$", text, flags=re.MULTILINE)
    )

    hashes.update(
        re.findall(r"^Dialogue SHA256:\s*([0-9a-f]{64})$", text, flags=re.MULTILINE)
    )

    return completed_ids, hashes


def run_episode(profile, model_name, max_rounds):
    api_key = os.environ["DASHSCOPE_API_KEY"]

    buyer_model = OpenAILLM(
        model=model_name,
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    seller_model = OpenAILLM(
        model=model_name,
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    buyer = BuyerAgent(
        model=buyer_model,
        buyer_max_price=120.0,
    )

    seller = SellerAgent(
        model=seller_model,
        seller_min_price=90.0,
    )

    env = agenticpay.make(
        "Task1_basic_price_negotiation-v0",
        buyer_agent=buyer,
        seller_agent=seller,
        max_rounds=max_rounds,
        initial_seller_price=180.0,
        buyer_max_price=120.0,
        seller_min_price=90.0,
    )

    observation, _ = env.reset(
        user_requirement="I need a winter jacket",
        product_info={
            "name": "Winter Jacket",
            "price": 180.0,
        },
        user_profile=profile["description"],
    )

    turns = []
    done = False
    info = {}

    while not done:
        round_id = int(observation.get("current_round", len(turns)))

        buyer_action = buyer.respond(
            conversation_history=observation["conversation_history"],
            current_state=observation,
        )

        buyer_text = (
            buyer_action.strip()
            if isinstance(buyer_action, str)
            else str(buyer_action)
        )

        seller_history = observation["conversation_history"].copy()
        seller_history.append(
            {
                "role": "buyer",
                "content": buyer_text,
                "round": round_id,
            }
        )

        seller_action = seller.respond(
            conversation_history=seller_history,
            current_state=observation,
        )

        seller_text = (
            seller_action.strip()
            if isinstance(seller_action, str)
            else str(seller_action)
        )

        turns.append(
            {
                "round_id": round_id,
                "buyer_message": buyer_text,
                "seller_message": seller_text,
            }
        )

        observation, _, terminated, truncated, info = env.step(
            buyer_action=buyer_text,
            seller_action=seller_text,
        )

        done = terminated or truncated

    env.close()
    return turns, info


def write_episode(path, profile_id, profile, turns, info, hash_value):
    with path.open("a", encoding="utf-8") as f:
        f.write("=" * 90 + "\n")
        f.write(f"Profile ID: {profile_id}\n")
        f.write(f"Buyer: {profile.get('name', '')}\n")
        f.write(f"Persona: {profile['persona_type']}\n")
        f.write("Control: none\n\n")

        for turn in turns:
            f.write(f"ROUND {turn['round_id']}\n")
            f.write(f"Buyer: {turn['buyer_message']}\n")
            f.write(f"Seller: {turn['seller_message']}\n\n")

        f.write(f"[FINAL STATUS] {info.get('status')}\n")
        f.write(f"[TURN COUNT] {len(turns)}\n")
        f.write(f"Dialogue SHA256: {hash_value}\n")
        f.write("=" * 90 + "\n\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profiles",
        default="configs/adversarial_buyers_expanded.json",
    )
    parser.add_argument(
        "--output",
        default="outputs/conversation_logs2.txt",
    )
    parser.add_argument(
        "--model",
        default="qwen-plus",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
    )
    args = parser.parse_args()

    if not os.getenv("DASHSCOPE_API_KEY"):
        raise RuntimeError("DASHSCOPE_API_KEY is not set.")

    profiles = json.loads(
        Path(args.profiles).read_text(encoding="utf-8")
    )

    counters = defaultdict(int)
    indexed = []

    for profile in profiles:
        persona = profile["persona_type"]
        counters[persona] += 1
        profile_id = f"expanded_{persona}_{counters[persona]:03d}"
        indexed.append((profile_id, profile))

    if args.limit is not None:
        indexed = indexed[:args.limit]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    completed_ids, known_hashes = existing_state(output_path)

    print("Profiles requested:", len(indexed))
    print("Already completed:", len(completed_ids))
    print()

    for n, (profile_id, profile) in enumerate(indexed, 1):

        if profile_id in completed_ids:
            print(f"[{n}/{len(indexed)}] SKIP {profile_id}")
            continue

        for attempt in range(1, 4):
            print(
                f"[{n}/{len(indexed)}] "
                f"{profile_id} attempt {attempt}"
            )

            turns, info = run_episode(
                profile,
                args.model,
                args.max_rounds,
            )

            h = dialogue_hash(turns)

            if h in known_hashes:
                print("  exact duplicate dialogue -> regenerate")
                continue

            write_episode(
                output_path,
                profile_id,
                profile,
                turns,
                info,
                h,
            )

            known_hashes.add(h)
            completed_ids.add(profile_id)

            print(
                f"  saved: turns={len(turns)}, "
                f"status={info.get('status')}"
            )
            break
        else:
            raise RuntimeError(
                f"Failed to produce unique dialogue for {profile_id}"
            )

    print()
    print("Completed profiles:", len(completed_ids))
    print("Unique dialogues:", len(known_hashes))
    print("Saved to:", output_path)


if __name__ == "__main__":
    main()
