# Signature extension — X2 Proposal experiments

**What.** GigBid can run two proposal strategies as an A/B test against GigSim's simulated clients and test whether the
difference in reply rate is real.

* **A — evidence-led** (`agent/prompts/writer.md`, the shipped writer): open with the client's problem, prove fit with cited
  evidence, short plan.
* **B — question-led** (`agent/prompts/writer_b.md`): open with one sharp question about the client's project, then the single
  strongest proof, a 3-step plan and a clear next step.

**How it is built.** The strategy is a versioned prompt chosen by configuration (`writer.prompt` in `agent/config.yaml`, or the
`WRITER_PROMPT` environment variable), so switching strategies or adding a third one needs no code. Everything else in the graph —
retrieval, claim verification, critic, compliance, approval — is identical for both arms, so the only difference is the writing
strategy.

**How it is measured.** `evals/runners/gigsim_outcomes.py` runs both arms (`best_open` = A, `best_open_B` = B) on the same fixed
job set, with proposals auto-approved by the harness and submitted to fresh GigSim instances whose LLM clients have hidden
preferences (must-have skills, dislike of generic openings, budget ceilings). `evals/runners/make_tables.py` computes a two-sided
Fisher exact test on replies vs. no replies and writes `evals/results/ab_test.json`.

**Result.** See `evals/results/ab_test.json` and the README results section (reply counts per arm and the p-value). With the
sample sizes affordable on free-tier models, the test is underpowered: it can detect only large differences, so a
non-significant result means "no evidence of a difference", not "no difference". In production the same harness would run on
the user's real outcomes (outcome memory), accumulating samples per job category.
