"""Test configuration: isolated SQLite DB, NO external API access, DEMO mode.

Environment is pinned BEFORE app modules import (settings are read at import).
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMP_DB = os.path.join(tempfile.gettempdir(), f"railcast_test_{os.getpid()}.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ["RAILRADAR_API_KEY"] = ""       # tests must never hit RailRadar
os.environ["WEATHER_API_KEY"] = ""         # tests must never hit OpenWeather
os.environ["DATA_MODE"] = "DEMO"
os.environ["DEMO_TIME_SCALE"] = "60"
os.environ["DEMO_TICK_SECONDS"] = "45"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as c:  # runs lifespan: init_db + seed + first refresh
        yield c
    try:
        os.remove(_TMP_DB)
    except OSError:
        pass
