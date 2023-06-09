"""
Generate training data based on conversations

Usage: python -m ochat.data.generate_data --in-file sharegpt_gpt4.json --tokenizer-name HF_REPO_NAME --out-dir .
"""

from typing import Optional
from dataclasses import dataclass
import argparse
import json
import os
import random

import numpy as np
import transformers


@dataclass
class ModelDataConfig:
    name: str

    # Prompt
    system: str

    role_prefix: dict
    ai_role: str
    eot_token: str
    bos_token: Optional[str]

    # Tokenize
    max_tokens: int


CONFIG = ModelDataConfig(
    name="OChat",

    # Prompt
    system="",

    role_prefix={
        "human": "Human: ",
        "gpt": "Assistant: "
    },
    ai_role="gpt",
    eot_token="<|end_of_turn|>",
    bos_token="<s>",

    # Tokenize
    max_tokens=4096
)


TOKENIZER: transformers.AutoTokenizer = None


def convert_single_conversation(c):
    def _tokenize(text):
        """Tokenize text-only, ignoring all special tokens."""
        return TOKENIZER.convert_tokens_to_ids(TOKENIZER._tokenize(text))

    tokens = []
    masks = []

    # begin of sentence (bos)
    if CONFIG.bos_token:
        t = TOKENIZER.convert_tokens_to_ids(CONFIG.bos_token)
        tokens.append(t)
        masks.append(False)

    # System
    if CONFIG.system:
        t = _tokenize(CONFIG.system) + [TOKENIZER.convert_tokens_to_ids(CONFIG.eot_token)]
        tokens.extend(t)
        masks.extend([False] * len(t))

    # Messages
    for message in c["items"]:
        # Prefix
        t = _tokenize(CONFIG.role_prefix[message["from"]])
        tokens.extend(t)
        masks.extend([False] * len(t))

        # Message
        t = _tokenize(message["value"]) + [TOKENIZER.convert_tokens_to_ids(CONFIG.eot_token)]
        tokens.extend(t)
        masks.extend([message["from"] == CONFIG.ai_role] * len(t))

    # Truncate to specified tokens
    tokens = tokens[:CONFIG.max_tokens]
    masks  = masks[:CONFIG.max_tokens]

    return tokens, masks


def generate_split(conversations: list, split_name: str, out_dir: str):
    # FIXME: Tokenizer have GIL, build faster multiprocessing
    converted = list(map(convert_single_conversation, conversations))

    # Output dataset
    with open(os.path.join(out_dir, f"ochat.{split_name}.json"), "w") as f:
        json.dump(converted, f)

    # Output plain texts
    all_plain_texts = TOKENIZER.batch_decode([tokens for (tokens, masks) in converted], spaces_between_special_tokens=False)

    with open(os.path.join(out_dir, f"ochat.{split_name}.text.json"), "w") as f:
        json.dump(all_plain_texts, f, indent="\t")


def generate_dataset(seed, in_file, tokenizer_name, out_dir, eval_ratio):
    # Load tokenizer
    global TOKENIZER
    TOKENIZER = transformers.AutoTokenizer.from_pretrained(tokenizer_name, use_auth_token=True, use_fast=False)

    # Load conversations
    with open(in_file, "r") as f:
        conversations = json.load(f)

    # Train-test split
    random.seed(seed)
    random.shuffle(conversations)
    eval_num = int(eval_ratio * len(conversations))

    train_conversations = conversations[eval_num:]
    eval_conversations  = conversations[:eval_num]

    generate_split(train_conversations, "train", out_dir)
    generate_split(eval_conversations, "eval", out_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--in-file", type=str, required=True)
    parser.add_argument("--tokenizer-name", type=str, required=True)
    parser.add_argument("--out-dir", type=str, default=".")
    parser.add_argument("--eval-ratio", type=float, default=0.01)
    args = parser.parse_args()

    generate_dataset(**vars(args))
