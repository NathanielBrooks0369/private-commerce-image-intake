from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from .infrai_storage import InfraiError, InfraiStorage
from .order_workflow import CheckoutRequest, CheckoutResult, process_checkout


BUCKET = os.environ.get("IMAGE_BUCKET", "commerce-product-images")
storage: InfraiStorage | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global storage
    storage = InfraiStorage()
    storage.create_bucket(BUCKET)
    try:
        yield
    finally:
        storage.close()
        storage = None


app = FastAPI(title="Private commerce image intake", lifespan=lifespan)


@app.post("/checkout", response_model=CheckoutResult)
def checkout(request: CheckoutRequest) -> CheckoutResult:
    if storage is None:
        raise HTTPException(status_code=503, detail="Service is starting")
    try:
        return process_checkout(request, storage, BUCKET)
    except InfraiError as exc:
        status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(status_code=status, detail={"code": exc.code, "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

