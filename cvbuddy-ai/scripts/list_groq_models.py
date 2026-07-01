#!/usr/bin/env python3
"""
List available Groq models for the current API key.

Run (from cvbuddy-ai root):
  .venv\\Scripts\\python.exe scripts\\list_groq_models.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402


def main() -> int:
    key = (settings.groq_api_key or os.getenv("GROQ_API_KEY") or "").strip()
    if not key:
        print("GROQ_API_KEY is empty. Set it in .env first.")
        return 1

    headers = {"Authorization": f"Bearer {key}"}
    url = "https://api.groq.com/openai/v1/models"
    r = httpx.get(url, headers=headers, timeout=30)
    if r.status_code >= 400:
        print(f"Groq HTTP {r.status_code}: {r.text[:400]}")
        return 2

    data = r.json()
    models = [m.get("id") for m in data.get("data", []) if m.get("id")]
    models.sort()

    print("Available Groq model ids:")
    print("-" * 60)
    for mid in models:
        print(mid)
    print("-" * 60)
    print("Set one of the ids above as GROQ_MODEL in your .env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

