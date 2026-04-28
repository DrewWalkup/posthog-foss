# Repo-root FOSS stack

This repository now includes a repo-root FOSS compose target for local image builds.

`docker-compose.hobby.yml` is not the target for this workflow.
Use `docker-compose.foss.yml` from the repository root instead.

## Build and boot

```bash
docker build -t local/posthog-foss:local -f Dockerfile .
docker compose --env-file .env.foss.example -f docker-compose.foss.yml build
docker compose --env-file .env.foss.example -f docker-compose.foss.yml up migrate
docker compose --env-file .env.foss.example -f docker-compose.foss.yml up proxy web worker plugins ingestion-general ingestion-sessionreplay recording-api capture replay-capture feature-flags property-defs-rs
```

## Notes

- The compose file builds the Django image from `Dockerfile` and the Node services image from `Dockerfile.node`.
- Rust services are built from `rust/` with their existing `BIN` build args.
- The default environment in `.env.foss.example` is intentionally minimal and avoids hobby-only or telemetry-specific settings.
- The proxy service exposes the unified local entrypoint on `http://localhost:8000` so web, capture, feature flags, and object storage routes behave like a single stack.
