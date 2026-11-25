"""Refresh every data source, then export the hosted page's data files.

Usage: python -m backend.refresh_site OUT_DIR
Used by the scheduled task that keeps the hosted portal up to date.
"""
import os
import sys

os.environ.setdefault("RUN_JOBS", "false")

from backend.app import jobs  # noqa: E402
from backend.app.db import init_db  # noqa: E402


def main() -> None:
    init_db()
    jobs.refresh_all()
    jobs.refresh_macro()
    for k, v in jobs.job_status.items():
        print(f"{k}: {'ok' if v['ok'] else 'FAILED'} - {v['detail'][:150]}")
    from backend import export_snapshot
    sys.argv = ["export_snapshot", *sys.argv[1:]]
    export_snapshot.main()


if __name__ == "__main__":
    main()
