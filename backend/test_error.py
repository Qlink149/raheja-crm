import asyncio
from fastapi.testclient import TestClient
from main import app
from app.core.security import get_current_user

def test_api():
    app.dependency_overrides[get_current_user] = lambda: {"id": "test_user"}
    with TestClient(app) as client:
        response = client.get("/api/call-history?page=1&size=50&disposition=interested")
        print("Status code:", response.status_code)
        print("Response JSON:", response.json())

if __name__ == "__main__":
    test_api()
