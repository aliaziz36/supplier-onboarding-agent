"""Paths, env and policy loading. One place so every module agrees."""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

CASES_DIR = Path(os.getenv("CASES_DIR", ROOT / "data" / "cases"))   # point elsewhere to generate and run fresh cases
CACHE_DIR = ROOT / "cache" / "llm"
RESULTS_DIR = ROOT / "results"
DB_PATH = Path(os.getenv("DB_PATH", ROOT / "data" / "app.db"))
MODEL = os.getenv("MODEL", "claude-sonnet-5-5")


def env_flag(name: str) -> bool:
    return os.getenv(name, "0").strip().lower() in ("1", "true", "yes")


def load_policy(path: Path | None = None) -> dict:
    with open(path or os.getenv("POLICY_PATH", ROOT / "policy.yaml")) as f:
        return yaml.safe_load(f)
