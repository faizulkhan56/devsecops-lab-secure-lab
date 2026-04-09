import os

import pytest


def _db_e2e_enabled():
    return (
        os.environ.get("GITHUB_ACTIONS") == "true"
        or os.environ.get("RUN_DB_E2E") == "1"
    )


requires_db = pytest.mark.skipif(
    not _db_e2e_enabled(),
    reason="DB E2E: set RUN_DB_E2E=1 with local Postgres, or run in GitHub Actions",
)


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_database():
    if not _db_e2e_enabled() or not os.environ.get("DB_PASSWORD"):
        return
    from app import init_db, seed_initial_user

    init_db()
    seed_initial_user()
