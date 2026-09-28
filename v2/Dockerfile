FROM node:22-slim AS web
WORKDIR /web
COPY v2/web/package*.json ./
RUN npm ci
COPY v2/web/ ./
RUN npm run build
FROM python:3.12-slim
WORKDIR /app
COPY v2/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock && useradd --create-home app
COPY kwangsung_agent/ kwangsung_agent/
COPY sample_docs/ sample_docs/
COPY v2/__init__.py v2/api.py v2/
COPY --from=web /web/dist v2/web/dist
RUN mkdir -p /app/data && chown -R app:app /app
USER app
EXPOSE 8514
CMD ["uvicorn", "v2.api:app", "--host", "0.0.0.0", "--port", "8514", "--no-proxy-headers"]
