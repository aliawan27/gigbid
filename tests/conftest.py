import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("GIGBID_FAKE_LLM", "1")  # deterministic fallbacks; no API keys needed in CI
os.environ.setdefault("GIGSIM_ERROR_RATE", "0")
os.environ.setdefault("GIGSIM_CLIENT_LLM", "0")
