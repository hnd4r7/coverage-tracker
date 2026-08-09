import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

if os.environ.get("COVERAGE_LIVE"):
    from coverage_tracker.middleware import install as install_coverage

    install_coverage(app, source="sample_api")


class Item(BaseModel):
    name: str
    price: float
    in_stock: bool = True


db: dict[int, Item] = {}
next_id = 1


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/items", status_code=201)
def create_item(item: Item):
    global next_id
    item_id = next_id
    db[item_id] = item
    next_id += 1
    return {"id": item_id, **item.model_dump()}


@app.get("/items/{item_id}")
def get_item(item_id: int):
    if item_id not in db:
        raise HTTPException(status_code=404, detail="Item not found")
    return db[item_id]


@app.get("/items")
def list_items(in_stock: bool | None = None):
    items = db
    if in_stock is not None:
        items = {i: it for i, it in db.items() if it.in_stock == in_stock}
    return items


@app.put("/items/{item_id}")
def update_item(item_id: int, item: Item):
    if item_id not in db:
        raise HTTPException(status_code=404, detail="Item not found")
    db[item_id] = item
    return {"id": item_id, **item.model_dump()}


@app.delete("/items/{item_id}")
def delete_item(item_id: int):
    if item_id not in db:
        raise HTTPException(status_code=404, detail="Item not found")
    del db[item_id]
    return {"deleted": item_id}


@app.post("/items/{item_id}/discount")
def apply_discount(item_id: int, percent: float):
    if item_id not in db:
        raise HTTPException(status_code=404, detail="Item not found")
    if not 0 <= percent <= 100:
        raise HTTPException(status_code=400, detail="Invalid percent")
    item = db[item_id]
    item.price = round(item.price * (1 - percent / 100), 2)
    return {"id": item_id, **item.model_dump()}
