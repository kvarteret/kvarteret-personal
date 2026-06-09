from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

try:
    from PIL import Image, ImageOps, UnidentifiedImageError
except ImportError:  # pragma: no cover - exercised only in broken runtime environments
    Image = None
    ImageOps = None
    UnidentifiedImageError = ValueError


class PhotoProcessingError(RuntimeError):
    pass


class PhotoUploadTooLargeError(PhotoProcessingError):
    pass


class InvalidPhotoError(PhotoProcessingError):
    pass


@dataclass(slots=True)
class ProcessedPhoto:
    content: bytes
    content_type: str
    extension: str
    width: int
    height: int


def process_uploaded_photo(
    content: bytes,
    *,
    max_upload_bytes: int,
    max_dimension: int,
) -> ProcessedPhoto:
    if len(content) > max_upload_bytes:
        raise PhotoUploadTooLargeError(
            f"Photos must be {max_upload_bytes // (1024 * 1024)} MB or smaller."
        )
    return _render_photo(content, max_dimension=max_dimension, quality=82)


def render_photo_variant(content: bytes, *, max_dimension: int) -> ProcessedPhoto:
    return _render_photo(content, max_dimension=max_dimension, quality=78)


def _render_photo(
    content: bytes, *, max_dimension: int, quality: int
) -> ProcessedPhoto:
    image_module = _require_pillow()
    if max_dimension < 32:
        raise InvalidPhotoError("Photo size must be at least 32 pixels.")

    try:
        with image_module.open(BytesIO(content)) as image:
            normalized = _normalize_image(image)
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidPhotoError("Uploaded file is not a valid image.") from exc

    resampling = getattr(image_module, "Resampling", image_module)
    normalized.thumbnail((max_dimension, max_dimension), resampling.LANCZOS)

    output = BytesIO()
    normalized.save(
        output, format="JPEG", quality=quality, optimize=True, progressive=True
    )
    rendered = ProcessedPhoto(
        content=output.getvalue(),
        content_type="image/jpeg",
        extension="jpg",
        width=normalized.width,
        height=normalized.height,
    )
    normalized.close()
    return rendered


def _normalize_image(image) -> "Image.Image":
    assert ImageOps is not None
    normalized = ImageOps.exif_transpose(image)
    normalized.load()

    has_alpha = normalized.mode in {"RGBA", "LA"} or (
        normalized.mode == "P" and "transparency" in normalized.info
    )
    if has_alpha:
        alpha_image = normalized.convert("RGBA")
        flattened = _require_pillow().new("RGB", alpha_image.size, (255, 255, 255))
        flattened.paste(alpha_image, mask=alpha_image.getchannel("A"))
        alpha_image.close()
        normalized.close()
        return flattened

    if normalized.mode != "RGB":
        converted = normalized.convert("RGB")
        normalized.close()
        return converted
    return normalized


def _require_pillow():
    if Image is None:
        raise RuntimeError("Pillow is required for photo processing.")
    return Image
