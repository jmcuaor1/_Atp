import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(mock_ml_resources):
    with TestClient(app) as test_client:
        yield test_client


def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["model_loaded"] is True
    assert data["players_count"] == 2


def test_list_surfaces(client):
    response = client.get("/surfaces")
    assert response.status_code == 200
    assert "Hard" in response.json()["surfaces"]


def test_search_players(client):
    response = client.get("/players/search", params={"q": "djok"})
    assert response.status_code == 200
    results = response.json()
    assert len(results) >= 1
    assert results[0]["id"] == 104925


def test_get_player(client):
    response = client.get("/players/207989")
    assert response.status_code == 200
    assert response.json()["name"] == "C. Alcaraz"


def test_get_player_not_found(client):
    response = client.get("/players/999999")
    assert response.status_code == 404


def test_model_info(client):
    response = client.get("/model/info")
    assert response.status_code == 200
    data = response.json()
    assert data["feature_count"] == 17
    assert "accuracy" in data["metadata"]


def test_predict_success(client):
    response = client.post(
        "/predict",
        json={
            "player1": {"id": 104925},
            "player2": {"id": 207989},
            "surface": "Clay",
            "best_of": 5,
            "tourney_level": "G",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["player1_name"] == "N. Djokovic"
    assert data["player2_name"] == "C. Alcaraz"
    assert data["predicted_winner_id"] in (104925, 207989)
    assert abs(
        data["player1_win_probability"] + data["player2_win_probability"] - 1.0
    ) < 0.01


def test_predict_same_player_rejected(client):
    response = client.post(
        "/predict",
        json={
            "player1": {"id": 104925},
            "player2": {"id": 104925},
            "surface": "Hard",
        },
    )
    assert response.status_code == 422


def test_predict_invalid_surface(client):
    response = client.post(
        "/predict",
        json={
            "player1": {"id": 104925},
            "player2": {"id": 207989},
            "surface": "Sand",
        },
    )
    assert response.status_code == 422


def test_predict_unknown_player(client):
    response = client.post(
        "/predict",
        json={
            "player1": {"id": 104925},
            "player2": {"id": 1},
            "surface": "Hard",
        },
    )
    assert response.status_code == 404
