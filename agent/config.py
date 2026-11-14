from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((Path(__file__).parent / "config.yaml").read_text())


def profile() -> dict:
    name = os.getenv("MODEL_PROFILE", CONFIG["models"]["profile"])
    return CONFIG["models"]["profiles"][name]


def model_for(node: str) -> str:
    return profile()[CONFIG["models"]["nodes"].get(node, "small")]


def fallback_model() -> str:
    return profile()["fallback"]


def policy_rules() -> dict:
    return yaml.safe_load((ROOT / CONFIG["policy"]["rules_file"]).read_text())


def prompt(name: str) -> str:
    """Every prompt lives in agent/prompts/<name>.md (versioned, no inline prompts)."""
    return (Path(__file__).parent / "prompts" / f"{name}.md").read_text(encoding="utf-8")
