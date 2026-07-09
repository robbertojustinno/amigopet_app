#!/usr/bin/env bash
cd /app && alembic upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port 10000
