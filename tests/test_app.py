import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200


def test_create_user_success(client):
    response = client.post(
        "/api/users",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "password123"
        },
    )
    assert response.status_code in [200, 201]


def test_create_user_invalid_email(client):
    response = client.post(
        "/api/users",
        json={
            "username": "testuser",
            "email": "invalid-email",
            "password": "password123"
        },
    )
    assert response.status_code == 400


def test_login_fail(client):
    # invalid login should fail
    response = client.post(
        "/api/login",
        json={
            "username": "wrong",
            "password": "wrong"
        },
    )
    assert response.status_code in [400, 401]

#def test_deliberate_failure():
#    """This test will fail — demonstrating pipeline failure."""
#    assert 1 == 2, "Deliberate failure for CI demo"