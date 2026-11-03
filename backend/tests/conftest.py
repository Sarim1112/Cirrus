import os
import tempfile
from datetime import date

import pytest

_folder = tempfile.mkdtemp(prefix="cirrus-tests-")
os.environ["CIRRUS_DATABASE_URL"] = os.environ.get(
    "CIRRUS_TEST_DATABASE_URL", f"sqlite:///{_folder}/test.db"
)
os.environ["CIRRUS_AI_ENABLED"] = "false"
os.environ["CIRRUS_ENV"] = "test"

from fastapi.testclient import TestClient  # noqa: E402

from app.advisor.providers import NoProvider, set_provider  # noqa: E402
from app.db import Base, get_engine  # noqa: E402
from app.engine.core import Txn  # noqa: E402
from app.main import app  # noqa: E402
from app.security import limiter  # noqa: E402

TODAY = date(2026, 6, 15)


@pytest.fixture(autouse=True)
def _clean_state():
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    limiter.reset()
    set_provider(NoProvider())
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def second_client():
    with TestClient(app) as test_client:
        yield test_client


PASSWORD = "correct horse battery"


def register(client, email="ada@example.com", password=PASSWORD):
    response = client.post("/api/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return response.json()


_counter = {"n": 0}


def txn(day, amount, merchant="Shop", category="Shopping") -> Txn:
    _counter["n"] += 1
    return Txn(
        f"t{_counter['n']}", date.fromisoformat(day), round(amount * 100), merchant, category
    )


def fmt(cents):
    return f"${cents / 100:,.2f}"
