# MCP tool surface

Agents never call GigSim, Upwork, a database or a file directly: every capability is an MCP tool with a schema, an owner and a test
(`tests/unit/test_mcp_inmemory.py`, schema snapshots in `tests/contract/`). Per-agent allowlists live in `agent/mcp_client.py`.

## Our servers

| Tool | Server | R/W | Annotations | Auth | Notes |
|---|---|---|---|---|---|
| `search_evidence(requirement, k, filters)` | portfolio | read | readOnly, idempotent | none (stdio) / network-local HTTP | items with type, source, date, outcome; deployed RAG variant chosen by config |
| `search_past_proposals(query, k, outcome)` | portfolio | read | readOnly, idempotent | — | phrasing that won / got replies (outcome-aware) |
| `get_case_study(id)` | portfolio | read | readOnly, idempotent | — | full item text + metadata |
| `list_skills()` | portfolio | read | readOnly, idempotent | — | skill → evidence count (named + implied in code) |
| resources `portfolio://case/{id}`, `portfolio://proposal/{id}`, `portfolio://cv/{owner}` | portfolio | read | — | — | full items for a host |
| prompts `answer_screening_question`, `cover_letter_from_portfolio` | portfolio | — | — | — | prompts a freelancer would pick in Claude Desktop/Cursor |
| `search_jobs(user_id, query, category, since, limit)` | marketplace | read | readOnly, idempotent, openWorld | bearer token | rate-limited per user, audited |
| `get_job(user_id, job_id)` | marketplace | read | readOnly, idempotent | bearer | |
| `get_client_history(user_id, client_id)` | marketplace | read | readOnly, idempotent | bearer | |
| `get_market_stats(user_id, category, complexity)` | marketplace | read | readOnly, idempotent | bearer | p25/median/p75 from 1,500 historical jobs |
| `get_connects_balance(user_id)` | marketplace | read | readOnly, idempotent | bearer | |
| `list_messages(user_id)` / `list_proposals(user_id)` | marketplace | read | readOnly, idempotent | bearer | pipeline sync |
| `get_platform_policy(user_id)` | marketplace | read | readOnly, idempotent | bearer | versioned policy (change request) |
| `create_proposal_draft(p: ProposalIn)` | marketplace | write (draft) | idempotent, non-destructive | bearer | stores a draft; returns the **dry_run** preview + Connects cost |
| `submit_proposal(p: ProposalIn)` | marketplace | **write** | destructive, idempotent | bearer | spends Connects; **idempotency_key** required; `dry_run=true` previews only |
| `send_message(m: MessageIn)` | marketplace | **write** | destructive, idempotent | bearer | idempotency_key + dry_run |
| `free_slots(user_id, days, duration_minutes)` | workspace | read | readOnly, idempotent | — | mock calendar (local JSON) |
| `create_tentative_hold(user_id, start, title, idempotency_key)` | workspace | write | idempotent, non-destructive | — | tentative only |
| `create_email_draft(user_id, to, subject, body, idempotency_key)` | workspace | write | idempotent, non-destructive | — | never sent automatically |

Every marketplace call is appended to `logs/audit.jsonl` (user, tool, PII-masked arguments, result, trace id). Write tools
take Pydantic input models with real constraints (`cover_letter` 50–5000 chars, `bid_amount` > 0, key ≥ 8 chars) and declare
output schemas (`ProposalOut`, `MessageOut`).

## Third-party servers (A5)

| Server | Used for | Trust rationale (one line) |
|---|---|---|
| Upwork official MCP (`https://mcp.upwork.com/mcp`, OAuth 2.1) | live mode behind the same marketplace port (`mcp_servers/marketplace/adapters/upwork_live.py`) | First-party server of the platform itself; every write is a draft the user confirms on Upwork, so GigBid cannot act beyond what Upwork allows. |
| GitHub official MCP (`https://api.githubcopilot.com/mcp/`) | repo ingestion for portfolios (`rag/ingest/github_mcp.py`) | Maintained by GitHub; we call only read tools (`search_repositories`, `get_file_contents`) with a read-only token. |

## Tool-design study (R&D question A)
See `evals/results/tool_granularity.json` and the README: 40 tasks with known correct calls, three tool sets (19 fine-grained,
2 coarse, 9 shipped tools with rewritten descriptions).
