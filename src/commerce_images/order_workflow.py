from __future__ import annotations

import base64
import binascii
import io
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Any
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field, field_validator


class OrderState(StrEnum):
    CHECKOUT_RECEIVED = "checkout_received"
    READY_FOR_FULFILLMENT = "ready_for_fulfillment"
    PAYMENT_REVIEW = "payment_review"


class CheckoutRequest(BaseModel):
    customer_id: str = Field(min_length=1, max_length=80)
    sku: str = Field(min_length=1, max_length=80)
    quantity: int = Field(ge=1, le=20)
    paid: bool
    inventory_allocated: bool
    image_base64: str

    @field_validator("image_base64")
    @classmethod
    def valid_base64(cls, value: str) -> str:
        try:
            base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("image_base64 must be valid base64") from exc
        return value


class ImageAsset(BaseModel):
    object_key: str
    width: int
    height: int
    content_type: str


class CustomerUpdate(BaseModel):
    channel: str
    message: str


class CheckoutResult(BaseModel):
    order_id: str
    state: OrderState
    image: ImageAsset
    receipt_id: str
    customer_update: CustomerUpdate


@dataclass(frozen=True)
class PreparedImage:
    content: bytes
    width: int
    height: int
    content_type: str = "image/jpeg"


def resize_product_image(raw: bytes, max_edge: int = 1200) -> PreparedImage:
    try:
        with Image.open(io.BytesIO(raw)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=85, optimize=True)
            return PreparedImage(output.getvalue(), image.width, image.height)
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("image payload is not a supported image") from exc


def process_checkout(request: CheckoutRequest, storage: Any, bucket: str) -> CheckoutResult:
    order_id = uuid4().hex
    prepared = resize_product_image(base64.b64decode(request.image_base64, validate=True))
    digest = sha256(prepared.content).hexdigest()[:16]
    object_key = f"products/{request.sku}/{digest}.jpg"
    signed_url = storage.presign_put(
        bucket=bucket,
        key=object_key,
        content_type=prepared.content_type,
        max_bytes=len(prepared.content),
        idempotency_key=f"image-{order_id}",
    )
    storage.put_signed(signed_url, prepared.content, prepared.content_type)

    ready = request.paid and request.inventory_allocated
    state = OrderState.READY_FOR_FULFILLMENT if ready else OrderState.PAYMENT_REVIEW
    message = "Order accepted for fulfillment." if ready else "Order received and payment review started."
    return CheckoutResult(
        order_id=order_id,
        state=state,
        image=ImageAsset(
            object_key=object_key,
            width=prepared.width,
            height=prepared.height,
            content_type=prepared.content_type,
        ),
        receipt_id=f"receipt-{order_id}",
        customer_update=CustomerUpdate(channel="email", message=message),
    )
