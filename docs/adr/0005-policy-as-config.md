# ADR 0005 — Policy and prompts as configuration
**Decision.** Compliance rules live in `data/policy_pack/rules.yaml` (forbid_regex / require_phrase / verified_claims),
prompts in `agent/prompts/*.md`, thresholds and models in `agent/config.yaml`.
**Why.** The 2 Nov change request was absorbed with a rules entry plus a 4-line scoping change (see README, change request).
