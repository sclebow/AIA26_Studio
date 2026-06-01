# Sensi — single-container deploy. Stage 1 builds the React SPA; stage 2 runs the
# FastAPI backend which also serves the built static files (one shareable origin).
FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json ./
RUN npm install --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY python/requirements.txt ./python/requirements.txt
RUN pip install --no-cache-dir -r python/requirements.txt
COPY python/ /app/python/
COPY personas/ /app/personas/
COPY randomized_layouts/ /app/randomized_layouts/
COPY resulting_layout/ /app/resulting_layout/
COPY --from=web /web/dist /app/web/dist
ENV PYTHONUNBUFFERED=1
WORKDIR /app/python
EXPOSE 8000
# LLM credentials must be supplied at runtime, e.g. `docker run --env-file .env ...`
CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
