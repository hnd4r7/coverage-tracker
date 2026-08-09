from fastapi.testclient import TestClient

from sample_api.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200


def test_create_item():
    resp = client.post("/items", json={"name": "Widget", "price": 9.99})
    assert resp.status_code == 201


def test_get_item():
    created = client.post("/items", json={"name": "Gadget", "price": 5.0}).json()
    resp = client.get(f"/items/{created['id']}")
    assert resp.status_code == 200


def test_get_item_not_found():
    resp = client.get("/items/9999")
    assert resp.status_code == 404


def test_list_items():
    resp = client.get("/items")
    assert resp.status_code == 200


def test_list_items_filtered():
    resp = client.get("/items", params={"in_stock": True})
    assert resp.status_code == 200


def test_update_item():
    created = client.post("/items", json={"name": "Thing", "price": 1.0}).json()
    resp = client.put(f"/items/{created['id']}", json={"name": "Thing2", "price": 2.0})
    assert resp.status_code == 200


def test_apply_discount():
    created = client.post("/items", json={"name": "Sale", "price": 100.0}).json()
    resp = client.post(f"/items/{created['id']}/discount", params={"percent": 10})
    assert resp.status_code == 200
