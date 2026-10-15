"""
    A deliberately small IIIF Image API 3.0 implementation, using Pillow directly.
    It's enough for this demo (level 2) and not intended for production use.
    https://iiif.io/api/image/3.0/
"""

import io
import math
import re

from PIL import Image

import iiifauth.terms

TILE_SIZE = 512
FORMATS = {
    "jpg": ("JPEG", "image/jpeg"),
    "png": ("PNG", "image/png")
}
QUALITIES = ["default", "color", "gray", "bitonal"]


class ImageRequestError(Exception):
    """An Image API request we can't fulfil; status is the HTTP status to return"""
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def info_json(service_id, image_path):
    """The Image API 3 info.json for the image at image_path (auth services are added elsewhere)"""
    with Image.open(image_path) as image:
        width, height = image.size

    # Keep adding scale factors until a single tile covers the whole image
    scale_factors = [1]
    while max(width, height) / scale_factors[-1] > TILE_SIZE:
        scale_factors.append(scale_factors[-1] * 2)

    return {
        "@context": iiifauth.terms.CONTEXT_IMAGE_3,
        "id": service_id,
        "type": "ImageService3",
        "protocol": "http://iiif.io/api/image",
        "profile": "level2",
        "width": width,
        "height": height,
        "tiles": [
            {"width": TILE_SIZE, "scaleFactors": scale_factors}
        ]
    }


def render(image_path, region, size, rotation, quality, fmt, max_width=None):
    """
        Returns (BytesIO, mimetype) for an Image API request.
        Raises ImageRequestError for requests that are invalid or unsupported.
    """
    if fmt not in FORMATS:
        raise ImageRequestError(f"Unsupported format {fmt}")
    if quality not in QUALITIES:
        raise ImageRequestError(f"Unsupported quality {quality}")
    mirror, degrees = parse_rotation(rotation)

    with Image.open(image_path) as image:
        full_w, full_h = image.size
        x, y, region_w, region_h = parse_region(region, full_w, full_h)
        width, height = parse_size(size, region_w, region_h, max_width)

        # For JPEGs, let Pillow decode at a reduced scale when we're downsizing.
        # This is much quicker than decoding a large image just to make a small tile.
        scale = max(width / region_w, height / region_h)
        if image.format == "JPEG" and scale < 1:
            image.draft("RGB", (math.ceil(full_w * scale), math.ceil(full_h * scale)))
        sx = image.size[0] / full_w
        sy = image.size[1] / full_h
        box = (round(x * sx), round(y * sy), round((x + region_w) * sx), round((y + region_h) * sy))

        output = image.crop(box).resize((width, height), Image.Resampling.LANCZOS)

    if mirror:
        output = output.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if degrees:
        # Pillow rotates anticlockwise, IIIF rotates clockwise
        output = output.rotate(-degrees, expand=True)

    if quality == "gray":
        output = output.convert("L")
    elif quality == "bitonal":
        output = output.convert("1")
    elif output.mode not in ("RGB", "L"):
        output = output.convert("RGB")

    pil_format, mimetype = FORMATS[fmt]
    buffer = io.BytesIO()
    output.save(buffer, pil_format)
    buffer.seek(0)
    return buffer, mimetype


def parse_region(region, full_w, full_h):
    """Returns x, y, w, h of the requested region, clipped to the image"""
    if region == "full":
        return 0, 0, full_w, full_h

    if region == "square":
        side = min(full_w, full_h)
        return (full_w - side) // 2, (full_h - side) // 2, side, side

    if region.startswith("pct:"):
        values = parse_numbers(region[4:], 4, float)
        x, y, w, h = (round(values[0] * full_w / 100), round(values[1] * full_h / 100),
                      round(values[2] * full_w / 100), round(values[3] * full_h / 100))
    else:
        x, y, w, h = parse_numbers(region, 4, int)

    if w <= 0 or h <= 0 or x >= full_w or y >= full_h:
        raise ImageRequestError(f"Region {region} is empty or outside the image")
    return x, y, min(w, full_w - x), min(h, full_h - y)


def parse_size(size, region_w, region_h, max_width=None):
    """Returns the pixel w, h of the requested size, given the dimensions of the region"""
    # If maxHeight isn't given it is the same as maxWidth
    max_height = max_width
    upscale = size.startswith("^")
    if upscale:
        size = size[1:]

    if size == "max":
        scale = 1.0
        if max_width is not None:
            limit = min(max_width / region_w, max_height / region_h)
            scale = limit if upscale else min(scale, limit)
        width, height = round(region_w * scale), round(region_h * scale)

    elif size.startswith("pct:"):
        pct = parse_numbers(size[4:], 1, float)[0]
        width, height = round(region_w * pct / 100), round(region_h * pct / 100)

    else:
        confined = size.startswith("!")
        match = re.fullmatch(r"(\d*),(\d*)", size[1:] if confined else size)
        if not match or not (match.group(1) or match.group(2)):
            raise ImageRequestError(f"Invalid size {size}")
        req_w = int(match.group(1)) if match.group(1) else None
        req_h = int(match.group(2)) if match.group(2) else None

        if confined:
            if req_w is None or req_h is None:
                raise ImageRequestError(f"Invalid size {size}")
            scale = min(req_w / region_w, req_h / region_h)
            width, height = round(region_w * scale), round(region_h * scale)
        elif req_h is None:
            width, height = req_w, round(region_h * req_w / region_w)
        elif req_w is None:
            width, height = round(region_w * req_h / region_h), req_h
        else:
            width, height = req_w, req_h

    if width <= 0 or height <= 0:
        raise ImageRequestError(f"Size {size} results in an empty image")
    if not upscale and (width > region_w or height > region_h):
        raise ImageRequestError(f"Size {size} is larger than the region; use ^ to request upscaling")
    if max_width is not None and (width > max_width or height > max_height):
        raise ImageRequestError(f"Requested size too large, maxWidth is {max_width}")
    return width, height


def parse_rotation(rotation):
    """Returns (mirror, degrees); only multiples of 90 are supported"""
    mirror = rotation.startswith("!")
    try:
        degrees = float(rotation[1:] if mirror else rotation)
    except ValueError:
        raise ImageRequestError(f"Invalid rotation {rotation}")
    if degrees % 90 != 0 or not 0 <= degrees <= 360:
        raise ImageRequestError(f"Rotation {rotation} is not supported, only multiples of 90", status=501)
    return mirror, int(degrees) % 360


def parse_numbers(s, count, number_type):
    try:
        values = [number_type(v) for v in s.split(",")]
    except ValueError:
        raise ImageRequestError(f"Invalid parameter {s}")
    if len(values) != count or any(v < 0 for v in values):
        raise ImageRequestError(f"Invalid parameter {s}")
    return values
