import pytest
from unittest.mock import patch
from main import my_app, db, User, ChatHistory

@pytest.fixture
def client():
    my_app.config['TESTING'] = True
    my_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'  # Use in-memory DB for tests

    with my_app.app_context():
        db.create_all()

    client = my_app.test_client()

    yield client

    # Cleanup
    with my_app.app_context():
        db.drop_all()


def test_register_and_login(client):
    # Test /register
    response = client.post('/register', json={
        "username": "testuser",
        "password": "testpass"
    })
    assert response.status_code == 200
    assert response.get_json()['success'] == True

    # Test /login with correct credentials
    response = client.post('/login', json={
        "username": "testuser",
        "password": "testpass"
    })
    assert response.status_code == 200
    assert response.get_json()['success'] == True

    # Test /login with wrong credentials
    response = client.post('/login', json={
        "username": "testuser",
        "password": "wrongpass"
    })
    assert response.status_code == 401
    assert response.get_json()['success'] == False


def test_chat_route(client):
    # Create a test user first
    with my_app.app_context():
        user = User(username="mockuser", password_hash="fakehash")
        db.session.add(user)
        db.session.commit()

    # Patch ollama.chat
    with patch("main.ollama.chat") as mock_chat:
        mock_chat.return_value = {
            "message": {"content": "This is a mocked bot reply!"}
        }

        # Make request
        response = client.post("/chat", json={
            "username": "mockuser",
            "message": "Hi there!"
        })

        data = response.get_json()

        assert response.status_code == 200
        assert "reply" in data
        assert data["reply"] == "This is a mocked bot reply!"