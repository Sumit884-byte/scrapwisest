from __future__ import annotations

import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)
