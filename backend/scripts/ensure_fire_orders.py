"""DEPRECATED wrapper — use Alembic for schema.

  cd backend && alembic upgrade head

Kept so old runbooks / muscle memory do not apply ad-hoc DDL that diverges
from alembic_version. This script only runs ``alembic upgrade head``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    backend = Path(__file__).resolve().parents[1]
    print(
        "DEPRECATED: backend/scripts/ensure_fire_orders.py — "
        "prefer `cd backend && alembic upgrade head`",
        file=sys.stderr,
    )
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend,
        check=False,
    )
    if result.returncode == 0:
        print("OK: alembic upgrade head")
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
