# The clever parts of my RAG pipeline lost to the boring ones

*What building a multi-agent freelancing copilot taught me about measuring before shipping.*

For a university R&D project I built GigBid: a team of LangGraph agents that scouts freelance jobs, decides which ones are worth
bidding on, writes proposals where every claim has to point at real portfolio evidence, and waits for a human to approve
anything before it leaves the system. The brief was explicit that the retrieval design had to be *chosen by evaluation, not by
default*. I am glad it was, because if I had shipped what I believed on day one, I would have shipped the worse system.

## The setup

Each freelancer persona has a messy portfolio: about fifteen projects, each described three different ways — a prose case study
that names the skills, a README that names two of them, and a code file where some skills only appear as imports (a project
"uses" Celery only because `import celery` is in `main.py`). There are 150 past proposals per persona labelled won, replied or
ignored, and a few hundred jobs, some vague, some asking for five different things, some scams, some with planted prompt
injections.

The question I care about is narrow: when a job arrives, does retrieval put the evidence that proves the freelancer can do it in
the top five? I measured Recall@5, MRR and nDCG@10 against gold evidence for 465 jobs, across seven retrieval variants.

## What I expected

My hypothesis, written down before running anything, was: **requirement decomposition plus hybrid retrieval raises Recall@5 by
at least 15 points over naive dense retrieval on jobs with four or more requirements.** It felt obviously true. A job that asks for
"PyTorch, OCR, Docker and a REST API" is four questions, so ask four questions. I also expected the fancier variants — a
cross-encoder reranker, outcome-aware ranking that boosts projects whose proposals won, and a corrective RAG loop that grades
evidence and re-queries — to stack on top.

## What happened

Naive dense retrieval (fixed 400-character chunks, cosine similarity on the whole job post) scored Recall@5 0.790. The variant
that won was the boring one: BM25 and dense retrieval fused with reciprocal rank fusion, over an index where each project's
summary, README sections and code are stored as separate vectors but returned as one project. Recall@5 0.851, nDCG@10 0.916.

Requirement decomposition, my favourite idea, barely moved recall on exactly the jobs it was supposed to help: 0.600 against
0.586 for the naive baseline on jobs with four or more requirements, while plain hybrid retrieval reached 0.657. The whole
pipeline gained 7.2 points, half of what I predicted, so the hypothesis was not supported. Adding decomposition to the
winning pipeline made it worse.

The reason, once I read the failures, is almost embarrassing. Real job posts contain generic requirements — "Python",
"documentation and handover", "tests". When you split a post into one query per requirement and merge the result lists, every
generic requirement gets an equal vote, and its nearest neighbours are *other* projects that also mention Python. The specific
requirement that actually identifies the right project ("NER on clinical notes") is outvoted. A single query over the whole post
keeps the rare, discriminative terms in context. Decomposition is a good idea when requirements are independent and equally
informative; in freelance posts they are neither.

The other "smart" variants told the same story:

- The **cross-encoder reranker** added about three seconds per query on a CPU and did not raise recall. On a small corpus where the
  first stage already finds the right project, there is little left to rerank.
- **Corrective RAG** (grade the evidence with a small LLM, rewrite the query if it is weak, refuse if nothing is relevant) was the
  best variant on vague posts — 0.863 versus 0.833 — and worse everywhere else, because the grader sometimes throws away good
  evidence. That is a routing result, not a shipping result: use it when the post is vague.
- **Outcome-aware ranking** gave the best recall on multi-requirement jobs but the worst MRR, because boosting projects whose
  proposals *won* pulls a winning project above the item that actually matches the job. What worked is not always what is
  relevant.

The single most valuable component was the least glamorous: adding BM25 to dense retrieval. Removing it cost 5.9 nDCG points.
Embeddings blur exact tool names; "dbt", "Celery" and "PEFT" are precisely the tokens a lexical index is good at.

## The same lesson, in tools

I ran a second experiment on the MCP tool layer that rhymes with the first. Forty tasks with a known correct tool call, three
tool sets offered to the same small model: nineteen fine-grained tools (`get_job_budget`, `get_job_skills`, …), two catch-all
tools with an `action` argument, and the nine tools I shipped, whose descriptions I rewrote to include an example argument.

The shipped set got 95% of tool selections and 95% of arguments right. The fine-grained set got 80% and 72.5%: the model split one
intent ("is this job worth the Connects?") across several narrow tools and picked the wrong one. The catch-all set was the
cheapest in tokens and got the arguments right only 10% of the time, because the model has to invent the schema of a free-form
`params` object. The improvement that mattered was not the number of tools; it was a one-line example in each description.

## Did better retrieval win more clients?

This is where the story got its second twist. I generated proposals for the same twelve jobs with the naive pipeline and with
the shipped one, let the system's own critic and claim verifier clean both, and submitted them to GigSim, the marketplace
simulator, where each client is a small LLM with hidden preferences: must-have skills, a dislike of generic openings, a budget
ceiling. The naive pipeline got 7 replies out of 10 proposals. The shipped pipeline got 5 out of 11.

I do not believe the naive pipeline writes better proposals; with about ten proposals per arm, that gap is well inside the noise.
But I also cannot claim that better retrieval *wins more work*, and once I looked at why, it made sense. Both pipelines end with
claim verification — every sentence that claims experience is checked against the retrieved evidence and removed or rewritten if
unsupported — so both arms ended with zero unsupported claims. Once every proposal is honest and relevant, the client's decision
moves to things retrieval does not touch: the first sentence, whether the must-have skill is named, and the price.

So I changed the thing the client actually reads. A second writer strategy opens with one sharp question about the client's
project instead of a summary of my fit. On the same jobs it got 10 replies out of 12 against 5 out of 11 — and a Fisher exact
test still says p = 0.089. Suggestive, not proven. I shipped it anyway, because it was at least as good on every other measure
(fewer unsupported claims before verification, lower latency, same judge score), and I kept the experiment running on real
outcomes instead of declaring victory.

One more humbling detail: the LLM judge I used to score proposal quality gave almost everything 5 out of 5. A judge that cannot
tell your variants apart is not measuring anything, which is why the project calibrates it against thirty human labels before
trusting a single judge score.

## What I would tell myself on day one

1. **Write the hypothesis down before you run anything.** Mine was wrong, and I only know that because I had committed to a
   number.
2. **Ablate the pipeline you want to ship, one component at a time.** The ablation table, not the leaderboard, told me which part
   was doing the work.
3. **Read the failures.** The decomposition result made sense in five minutes once I looked at which items each sub-query
   retrieved.
4. **Prefer the boring baseline plus one well-understood fix.** Hybrid lexical + dense retrieval is ten years old. It beat
   everything I added on top of it.

The code, the evaluation runners and every number in this post are in the repository: github.com/aliawan27/gigbid
(`evals/results/rag_variants.json`, `evals/results/tool_granularity.json`).
