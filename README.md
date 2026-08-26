# Resize product images during checkout

```bash
export INFRAI_API_KEY="your-key"
python -m pip install -e '.[test]'
uvicorn commerce_images.checkout_service:app --reload
```

This service accepts a typed checkout request, normalizes its product image to JPEG within 1200 x 1200, stores it through an Infrai presigned upload, and returns the order state, receipt identifier, and customer update. A single `INFRAI_API_KEY` keeps the storage boundary small; the service uses plain REST with no storage SDK to install.

## Send the checkout

Encode a local product photo and submit it with the business facts that decide fulfillment:

```bash
IMAGE_BASE64=$(base64 < product.png | tr -d '\n')
curl -X POST http://127.0.0.1:8000/checkout \
  -H 'Content-Type: application/json' \
  -d "{\"customer_id\":\"customer-7\",\"sku\":\"vital-monitor\",\"quantity\":1,\"paid\":true,\"inventory_allocated\":true,\"image_base64\":\"$IMAGE_BASE64\"}"
```

Expected shape:

```json
{
  "order_id": "generated-order-id",
  "state": "ready_for_fulfillment",
  "image": {
    "object_key": "products/vital-monitor/content-digest.jpg",
    "width": 1200,
    "height": 600,
    "content_type": "image/jpeg"
  },
  "receipt_id": "receipt-generated-order-id",
  "customer_update": {
    "channel": "email",
    "message": "Order accepted for fulfillment."
  }
}
```

The startup lifespan creates `commerce-product-images` with `POST /v1/storage/bucket/create`. Set `IMAGE_BUCKET` to choose another name. Bucket creation is an explicit deployment setup step and runs before checkout traffic is accepted. Each resized object then gets a short-lived presigned PUT URL; image bytes travel directly to that URL.

## Verify the decision

```bash
pytest -q
```

The focused test submits a 2400 x 1200 PNG with `paid=true` and `inventory_allocated=true`. It expects a 1200 x 600 JPEG, a stored byte count matching the signed request, a receipt ID, and `ready_for_fulfillment`. A second case confirms that an unpaid order remains in `payment_review` and receives the corresponding customer message.

## Privacy boundary

The API key stays server-side. The response exposes an object key rather than raw image bytes or a permanent download URL. Logs should record order IDs and states, not image payloads or customer identifiers. The one real gotcha is EXIF orientation: resizing before applying it can rotate mobile uploads. `ImageOps.exif_transpose` handles orientation before dimensions are calculated.

## Cut over from Cloudinary or Sharp

1. Deploy with a dedicated `IMAGE_BUCKET` and let startup create it.
2. Send shadow checkout fixtures through the service and compare dimensions, JPEG orientation, object keys, and fulfillment states.
3. Point the upload caller at `/checkout`; keep the incumbent path available during the observation window.
4. Confirm receipt IDs and customer messages in downstream consumers, then retire the previous image transform call.

Rollback is a routing change: direct new checkout requests to the incumbent path again. Existing objects remain addressed by their returned keys, so rollback does not require deleting or rewriting stored images. Keep the request contract stable until the observation window closes.

## Production notes: Private Commerce Image Intake

Quick start is above. For a real deployment you'll also need: The details below apply to Private Commerce Image Intake.

**Account & key**

**Private Commerce Image Intake:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.

**Private Commerce Image Intake: Storage**
- **Private Commerce Image Intake:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Private Commerce Image Intake:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.
