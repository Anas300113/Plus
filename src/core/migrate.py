"""Run Plus schema preparation; review src.core.migrations before targeting managed data."""
from __future__ import annotations
import os
from src.core.database import get_engine
from src.core.migrations import ensure_schema

def main() -> int:
    url = os.environ.get("DATABASE_URL") or os.environ.get("PLUS_DATABASE_URL")
    if not url:
        raise SystemExit("Set DATABASE_URL (or PLUS_DATABASE_URL) before migrating.")
    engine = get_engine(url)
    try:
        applied = ensure_schema(engine)
        print(f"Schema is ready. Applied {len(applied)} additive migration action(s).")
        for migration_id in applied:
            print(f"  + {migration_id}")
    finally:
        engine.dispose()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
