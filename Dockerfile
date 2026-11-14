# Single image for every GigBid Python service (API, worker, MCP servers, GigSim) + the built web UI.
# docker compose (infra/docker-compose.yml) runs one container per service from this image;
# the public deployment (Render free web service) runs all of them in one process via apps/api/allinone.py.
FROM node:20-slim AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
RUN npx vite build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app GIGBID_CACHE=/app/data/processed HF_HOME=/app/data/processed/hf PORT=7860
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
RUN uv pip install --system --no-cache -r pyproject.toml
COPY . .
COPY --from=web /web/dist apps/web/dist
# bake the open embedding + reranker models into the image (CPU, no GPU needed)
RUN python -c "from rag.index.store import embedder, reranker; embedder(); reranker()" \
 && python -c "from rag.variants.base import get_index; [get_index(p, c) for p in ('ai_ml','fullstack','data_analyst') for c in ('structural', 'multivector')]" \
 && mkdir -p logs && chmod -R 777 /app/data /app/logs
EXPOSE 7860
# all services in one process for 512 MB free hosts; compose overrides the command per service
CMD ["python", "-m", "apps.api.allinone"]
