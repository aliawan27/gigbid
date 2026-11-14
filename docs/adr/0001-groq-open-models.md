# ADR 0001 — Open-weight models through Groq, routed per node
**Decision.** The `open` profile uses gpt-oss-20b for cheap nodes (analyst, risk, verifier, intent) and gpt-oss-120b for the
writer, critic and liaison; `open_qwen` swaps the strong model for qwen3.8-27b. Keys rotate automatically on 429.
**Why.** No GPU on free hosts; Groq hosts open-weight models with free tiers. Per-node routing keeps cost per job near zero.
**Evidence.** `evals/results/gigsim_outcomes.json` compares both profiles on the same jobs.
