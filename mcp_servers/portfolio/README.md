# GigBid Portfolio MCP server

A read-only MCP server that lets any MCP host (Claude Desktop, Cursor, your own agent) **search a freelancer's portfolio for
evidence** before claiming anything in a proposal. Built with the official MCP Python SDK. Retrieval is hybrid BM25 + dense
(BGE-small, runs on CPU) over multi-vector items (summary, README sections and code indexed separately, returned as one project).

## Install / run (no clone needed)
```bash
# stdio (for Claude Desktop / Cursor)
uvx --python 3.12 --from git+https://github.com/aliawan27/gigbid gigbid-portfolio-mcp
# your own portfolio: a folder of .md / .pdf / .py / .ts files (CV, case studies, READMEs, code)
GIGBID_PORTFOLIO_DIR=~/my-portfolio uvx --python 3.12 --from git+https://github.com/aliawan27/gigbid gigbid-portfolio-mcp --owner me
# streamable HTTP
uvx --python 3.12 --from git+https://github.com/aliawan27/gigbid gigbid-portfolio-mcp --http 8091
```

Claude Desktop (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "portfolio": {
      "command": "uvx",
      "args": ["--python", "3.12", "--from", "git+https://github.com/aliawan27/gigbid", "gigbid-portfolio-mcp", "--owner", "me"],
      "env": { "GIGBID_PORTFOLIO_DIR": "/path/to/my-portfolio" }
    }
  }
}
```
Without `GIGBID_PORTFOLIO_DIR` it serves one of three bundled **synthetic** demo personas (`--owner ai_ml | fullstack | data_analyst`).

## Tools
| Tool | What it returns |
|---|---|
| `search_evidence(requirement, k=5, filters={types, since})` | evidence items with id, type, title, source, date, outcome, snippet, score |
| `search_past_proposals(query, k=3, outcome)` | past proposals with their outcome (won / replied / ignored) |
| `get_case_study(id)` | full text + metadata of one item |
| `list_skills()` | skills and how many items prove each one |

All tools are annotated `readOnlyHint=true, idempotentHint=true`.

## Resources and prompts
* `portfolio://case/{id}`, `portfolio://proposal/{id}`, `portfolio://cv/{owner}`
* `answer_screening_question(question)` — answer from the portfolio only, citing ids, or say there is no evidence
* `cover_letter_from_portfolio(job_post)` — short, cited cover letter; job post treated as untrusted data

## Tested
`tests/unit/test_mcp_inmemory.py` (in-memory MCP client) and a schema snapshot in `tests/contract/snapshots/portfolio.json`.
