# Data card

## Sources
| Data | Origin | Real or synthetic | Licence |
|---|---|---|---|
| Three freelancer personas (CV, 15 case studies each, repo READMEs + code for 10 projects each, client reviews, 150 past proposals with outcomes) | `scripts/generate_data.py` (deterministic, seed 4016) | **Synthetic** — every persona file is marked "SYNTHETIC" | MIT (this repo) |
| GigSim job pool (120 jobs), live stream (30 incl. reposts), 60 clients with public history + hidden preferences | same generator | **Synthetic** | MIT |
| Historical pricing (1,500 jobs → p25/median/p75 per category × complexity) | same generator, log-normal around category base rates | **Synthetic**, base rates loosely informed by the public Kaggle Upwork job-postings datasets listed by the TA | MIT |
| Dev evaluation sets `evals/datasets/dev_<persona>.json` (40 jobs each, gold bid/skip, scam flag, gold evidence ids, fair price band, job kind) | generated with the jobs, labels follow from how each job was built | **Synthetic** | MIT |
| Policy pack `data/policy_pack/` | written for this project (v1.0 + the 2 Nov v1.1 update) | — | MIT |
| User uploads (`data/uploads/`) and GitHub repos ingested via the GitHub MCP server | the user | real, user-owned | git-ignored; never committed |

No real client data, hidden test data or tokens are in the repository (enforced by `scripts/ci_checks.py`).

## How the corpus is made hard (B)
* **Same project described three ways**: case study (prose, skills named), README (2 skills only), code (implied skills such as
  `Celery`, `dbt`, `TensorRT` appear only as imports) — retrieval must connect them.
* **Skills implied rather than named**: 1 in 5 jobs requires a skill that only the code file proves.
* **Outcome matters more than wording**: 150 proposals per persona; specific, evidence-led proposals win ~30%, generic ones ~4%.
* **Vague posts** (~1 in 7) say only "help with my <industry> business".
* **Off-domain, low-ball, scam and prompt-injection jobs** in every dev set (6/4/3/3 of 40).

## Preprocessing
Markdown is split by heading (structural chunking); V0 uses fixed 400-character chunks with 50 overlap; V5 indexes a summary
view, README sections and code separately and returns one item per project. Every chunk carries persona, item id, type, project,
skills, date, industry and (proposals) outcome. Embeddings (BGE-small-en-v1.5) are cached by content hash, so adding a file
re-embeds only the new chunks.

## Limitations
* Synthetic text is more regular than real portfolios; absolute retrieval scores (MRR ≈ 1.0) are optimistic and the corpus is
  small (≈ 190 items per persona). Relative comparisons between variants are the useful signal.
* Gold evidence is project-level; a relevant item from a different project counts as a miss.
* GigSim clients are an LLM (gpt-oss-20b) with hidden preferences — reply rates measure "what this simulated client likes", not
  the real market.
* Dev sets are 40 jobs per persona (the brief suggests ~200) because of free-tier API limits; confidence intervals are wide.
