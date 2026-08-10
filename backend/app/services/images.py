import io

from PIL import Image, ImageOps

ALLOWED_FORMATS = {"JPEG", "PNG", "GIF"}
MAX_AI_EDGE_PX = 1568  # Anthropic's recommended long-edge cap for vision inputs


class InvalidImageError(ValueError):
    pass


def validate_and_normalize(raw_bytes: bytes) -> tuple[bytes, str, str, int, int]:
    """Sniffs real content, strips EXIF/metadata, re-encodes.

    Returns (clean_bytes, mime_type, extension, width, height). Raises InvalidImageError
    for anything that isn't a genuine, decodable JPEG/PNG/GIF — this is the security
    boundary against disguised/malformed uploads, not just an extension check.
    """
    try:
        image = Image.open(io.BytesIO(raw_bytes))
        image.verify()
        image = Image.open(io.BytesIO(raw_bytes))  # verify() consumes the parser, reopen
    except Exception as exc:
        raise InvalidImageError("File is not a readable image") from exc

    if image.format not in ALLOWED_FORMATS:
        raise InvalidImageError(f"Unsupported image format: {image.format}")

    image = ImageOps.exif_transpose(image)  # bake in rotation before we drop EXIF
    if image.mode not in ("RGB", "RGBA") and image.format != "GIF":
        image = image.convert("RGB")

    buffer = io.BytesIO()
    save_format = "JPEG" if image.format != "GIF" else "GIF"
    if save_format == "JPEG" and image.mode == "RGBA":
        image = image.convert("RGB")
    image.save(buffer, format=save_format)  # no exif kwarg => metadata dropped
    clean_bytes = buffer.getvalue()

    mime_type = "image/jpeg" if save_format == "JPEG" else "image/gif"
    extension = "jpg" if save_format == "JPEG" else "gif"
    return clean_bytes, mime_type, extension, image.width, image.height


def downscale_for_ai(raw_bytes: bytes, mime_type: str) -> bytes:
    """Downsizes to Anthropic's recommended long edge to keep vision calls fast/cheap."""
    image = Image.open(io.BytesIO(raw_bytes))
    if max(image.size) <= MAX_AI_EDGE_PX:
        return raw_bytes

    image.thumbnail((MAX_AI_EDGE_PX, MAX_AI_EDGE_PX))
    buffer = io.BytesIO()
    fmt = "JPEG" if mime_type == "image/jpeg" else "PNG"
    if fmt == "JPEG" and image.mode == "RGBA":
        image = image.convert("RGB")
    image.save(buffer, format=fmt)
    return buffer.getvalue()
