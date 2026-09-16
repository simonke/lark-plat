"""Regenerate docs/openapi.json contract artifact from the app (no DB needed)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.main import app

schema = app.openapi()

out = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"
out.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")

paths = schema["paths"]
print(f"paths: {len(paths)}")
print(f"mine present: {'/api/v1/transfer/tasks/mine' in paths}")
print(f"written: {out}")