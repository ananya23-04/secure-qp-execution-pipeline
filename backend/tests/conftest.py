import os, sys
os.environ["SAFEEXAM_DATABASE_URL"] = "sqlite:///./test.db"
os.environ["SAFEEXAM_ADMIN_EMAILS"] = "admin@juit.ac.in,admin2@juit.ac.in,admin3@juit.ac.in"
os.environ["SAFEEXAM_REVIEWER_EMAILS"] = "r1@juit.ac.in,r2@juit.ac.in,r3@juit.ac.in"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return TestClient(app)


def make_headers(client, email):
    client.post("/auth/register", json={"email": email, "password": "supersecret123", "institution": "JUIT"})
    tok = client.post("/auth/login", json={"email": email, "password": "supersecret123"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture()
def auth_headers(client):
    return make_headers(client, "a@juit.ac.in")


@pytest.fixture()
def admin_headers(client):
    return make_headers(client, "admin@juit.ac.in")


def sample_question(**kw):
    q = {"qtype": "mcq", "stem": "What is the derivative of $x^2$?", "options": ["$x$", "$2x$", "$x^2$"],
         "correct_option": 1, "subject": "Maths", "unit": 1, "bloom": "remember", "difficulty": 0.2, "marks": 1}
    q.update(kw)
    return q
