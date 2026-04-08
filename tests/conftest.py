"""Pytest loads this before test modules so env is set before `app` is imported."""
import os

os.environ.setdefault("SKIP_DB_INIT", "1")
