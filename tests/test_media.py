from io import BytesIO

from PIL import Image

from app.models import GenerateVideoRequest
from app.services import media


class DummyImageResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        return None


def test_cover_image_uses_first_available_product_image(monkeypatch, tmp_path):
    product_image = Image.new("RGB", (80, 80), "#e11919")
    buffer = BytesIO()
    product_image.save(buffer, format="PNG")

    def fake_get(url, timeout):
        assert url == "https://img.example/product.png"
        assert timeout == 20.0
        return DummyImageResponse(buffer.getvalue())

    monkeypatch.setattr(media.httpx, "get", fake_get)
    request = GenerateVideoRequest(
        task_id="cover-product-image",
        product={
            "title": {"value": "Portable Blender"},
            "main_image_url": "https://img.example/product.png",
        },
        short_video_script={"script": "这款便携榨汁杯适合通勤和旅行。"},
    )

    path = media._create_cover_image(request, tmp_path)

    assert _cover_contains_red_product_area(path)


def test_cover_image_tries_image_candidates_when_main_image_fails(monkeypatch, tmp_path):
    product_image = Image.new("RGB", (80, 80), "#e11919")
    buffer = BytesIO()
    product_image.save(buffer, format="PNG")
    requested_urls = []

    def fake_get(url, timeout):
        requested_urls.append(url)
        assert timeout == 20.0
        if url == "https://img.example/broken.png":
            raise RuntimeError("image blocked")
        return DummyImageResponse(buffer.getvalue())

    monkeypatch.setattr(media.httpx, "get", fake_get)
    request = GenerateVideoRequest(
        task_id="cover-product-image-candidate",
        product={
            "title": {"value": "Portable Blender"},
            "main_image_url": "https://img.example/broken.png",
            "image_candidates": ["https://img.example/broken.png", "https://img.example/fallback.png"],
        },
        short_video_script={"script": "这款便携榨汁杯适合通勤和旅行。"},
    )

    path = media._create_cover_image(request, tmp_path)

    assert requested_urls == ["https://img.example/broken.png", "https://img.example/fallback.png"]
    assert _cover_contains_red_product_area(path)


def _cover_contains_red_product_area(path):
    cover = Image.open(path).convert("RGB")
    sampled_pixels = [cover.getpixel((x, y)) for x in range(200, 880, 80) for y in range(360, 900, 80)]
    return any(red > 180 and green < 80 and blue < 80 for red, green, blue in sampled_pixels)
