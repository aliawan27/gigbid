# Docker
One image (repo-root `Dockerfile`) is used for every Python service; `infra/docker-compose.yml` runs one
container per service (gigsim, portfolio, marketplace, workspace, worker, api) plus Postgres and an optional
Ollama service (`--profile local`). The public deployment runs the same image as a single container
(`scripts/start_all.py`) on a Hugging Face Docker Space.
