import base64
import io

from PIL import Image

from commerce_images.order_workflow import CheckoutRequest, OrderState, process_checkout


class RecordingStorage:
    def __init__(self) -> None:
        self.uploaded = b""
        self.max_bytes = 0

    def presign_put(
        self, bucket: str, key: str, content_type: str, max_bytes: int, idempotency_key: str
    ) -> str:
        assert bucket == "test-images"
        assert key.startswith("products/vital-monitor/")
        assert content_type == "image/jpeg"
        assert idempotency_key.startswith("image-")
        self.max_bytes = max_bytes
        return "https://upload.example.test/signed"

    def put_signed(self, url: str, content: bytes, content_type: str) -> None:
        assert url == "https://upload.example.test/signed"
        assert content_type == "image/jpeg"
        self.uploaded = content


def source_image() -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (2400, 1200), "white").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_paid_allocated_checkout_resizes_and_enters_fulfillment() -> None:
    storage = RecordingStorage()
    request = CheckoutRequest(
        customer_id="customer-7",
        sku="vital-monitor",
        quantity=1,
        paid=True,
        inventory_allocated=True,
        image_base64=source_image(),
    )

    result = process_checkout(request, storage, "test-images")

    assert result.state is OrderState.READY_FOR_FULFILLMENT
    assert (result.image.width, result.image.height) == (1200, 600)
    assert result.receipt_id.startswith("receipt-")
    assert result.customer_update.message == "Order accepted for fulfillment."
    assert len(storage.uploaded) == storage.max_bytes


def test_unpaid_checkout_stays_in_payment_review() -> None:
    storage = RecordingStorage()
    request = CheckoutRequest(
        customer_id="customer-8",
        sku="vital-monitor",
        quantity=1,
        paid=False,
        inventory_allocated=True,
        image_base64=source_image(),
    )

    result = process_checkout(request, storage, "test-images")

    assert result.state is OrderState.PAYMENT_REVIEW
    assert result.customer_update.message == "Order received and payment review started."

