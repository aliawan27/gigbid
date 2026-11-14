"""Repository rules enforced in CI:
1. no secrets in the repo; 2. nothing under gigsim/ changed versus the base branch (PRs);
3. every prompt lives in agent/prompts/ (no long inline system prompts in node code);
4. every number cited in README.md's results section traces to a file in evals/results/."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
fail = []

SECRET = re.compile(r"(gsk_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|lsv2_pt_[a-f0-9]{20,}|sk-[A-Za-z0-9]{20,}|postgres(ql)?://[^\s:]+:[^\s@]+@[a-z0-9.-]+\.neon\.tech)")
tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
for f in tracked:
    p = ROOT / f
    if p.suffix in (".png", ".zip", ".pdf", ".npz", ".ico") or not p.is_file() or "node_modules" in f:
        continue
    try:
        if SECRET.search(p.read_text(encoding="utf-8", errors="ignore")):
            fail.append(f"secret-like string in {f}")
    except OSError:
        pass

base = os.getenv("GITHUB_BASE_REF")
if base:
    diff = subprocess.run(["git", "diff", "--name-only", f"origin/{base}...HEAD", "--", "gigsim/"], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()
    if diff:
        fail.append(f"gigsim/ must not change in PRs: {diff}")

for f in (ROOT / "agent" / "nodes").glob("*.py"):
    for m in re.finditer(r'"""(.*?)"""|"([^"\n]{400,})"', f.read_text(encoding="utf-8"), re.S):
        if m.group(2):
            fail.append(f"long inline string (prompt?) in {f.name}; move it to agent/prompts/")

readme = (ROOT / "README.md").read_text(encoding="utf-8") if (ROOT / "README.md").exists() else ""
sec = readme.split("<!-- results:start -->")[1].split("<!-- results:end -->")[0] if "<!-- results:start -->" in readme else ""
blob = " ".join((p.read_text(encoding="utf-8") for p in (ROOT / "evals" / "results").glob("*.json")))
for num in set(re.findall(r"(?<![\w.])\d+\.\d+(?![\w.])", sec)):
    if num not in blob:
        fail.append(f"README number {num} not found in evals/results/*.json")

if fail:
    print("\n".join(fail))
    sys.exit(1)
print("ci checks ok")
_ = json
