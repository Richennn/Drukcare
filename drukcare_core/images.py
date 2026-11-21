"""Local image manager: load your own photos, never crash if one is missing.

Every function here accepts a path like "assets/home_banner.jpg" (relative to
the DrukCare folder) or an absolute path.  If the file does not exist, is not
a supported format, or is damaged, a clean placeholder is drawn instead.
"""
import base64
import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, UnidentifiedImageError

from . import config


def resolve(path) -> Path:
    """Turn 'assets/x.jpg' into an absolute path inside the DrukCare folder."""
    p = Path(str(path))
    return p if p.is_absolute() else config.BASE_DIR / p


def find_image(path):
    """Return the real file for a path, or None.

    Also accepts a different extension: if you configured 'assets/home_banner.jpg'
    but saved 'assets/home_banner.png', that file is still found.
    """
    p = resolve(path)
    if p.is_file() and p.suffix.lower() in config.SUPPORTED_IMAGE_TYPES:
        return p
    for ext in config.SUPPORTED_IMAGE_TYPES:
        alt = p.with_suffix(ext)
        if alt.is_file():
            return alt
    return None


def _font(size):
    for name in ("segoeui.ttf", "DejaVuSans.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def make_placeholder(size, label="Add your photo", circle_text=None) -> Image.Image:
    """A calm navy-to-green gradient with a faint mountain outline and a hint."""
    w, h = max(int(size[0]), 2), max(int(size[1]), 2)
    gradient = Image.linear_gradient("L").resize((w, h))
    img = ImageOps.colorize(gradient, black=config.NAVY, white="#3C8F7A").convert("RGBA")
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    base = h
    pts = [(0, base), (0, h * .72), (w * .14, h * .52), (w * .24, h * .66), (w * .38, h * .36),
           (w * .52, h * .64), (w * .66, h * .44), (w * .80, h * .66), (w * .92, h * .54),
           (w, h * .68), (w, base)]
    d.polygon(pts, fill=(255, 255, 255, 38))
    img = Image.alpha_composite(img, layer)
    d = ImageDraw.Draw(img)
    if circle_text:
        font = _font(int(min(w, h) * 0.42))
        box = d.textbbox((0, 0), circle_text, font=font)
        d.text(((w - (box[2] - box[0])) / 2 - box[0], (h - (box[3] - box[1])) / 2 - box[1]),
               circle_text, fill="white", font=font)
    elif label and h >= 60:
        font = _font(max(11, min(18, h // 9)))
        box = d.textbbox((0, 0), label, font=font)
        d.text((w - (box[2] - box[0]) - 14, h - (box[3] - box[1]) - 12), label,
               fill=(255, 255, 255, 190), font=font)
    return img.convert("RGB")


def _cover(img: Image.Image, size, focus=(0.5, 0.5)) -> Image.Image:
    return ImageOps.fit(img, (int(size[0]), int(size[1])), Image.LANCZOS, centering=focus)


def _circle(img: Image.Image) -> Image.Image:
    img = img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, img.size[0] - 1, img.size[1] - 1), fill=255)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def load_image(path, size=None, label=None, circle=False, initials=None, contain=False) -> Image.Image:
    """Load a local image as a PIL image (cropped to `size`) or a placeholder.

    path     - e.g. config.HOME_BANNER
    size     - (width, height) in pixels; None keeps the original size
    label    - hint text drawn on the placeholder
    circle   - crop to a circle (profile photos)
    initials - letters drawn on a placeholder circle, e.g. "SP"
    contain  - fit inside size (no cropping), used for the logo
    """
    found = find_image(path) if path else None
    img = None
    if found:
        try:
            with Image.open(found) as raw:
                img = ImageOps.exif_transpose(raw).convert("RGBA" if contain or circle else "RGB")
                img.load()
        except (UnidentifiedImageError, OSError, ValueError):
            img = None
    target = size or (img.size if img else (800, 300))
    if img is None:
        hint = label or f"Add your photo: {path}"
        img = make_placeholder(target, hint, circle_text=initials)
    elif contain:
        img.thumbnail((int(target[0]), int(target[1])), Image.LANCZOS)
    elif size:
        img = _cover(img, size)
    return _circle(img) if circle else img


# ----------------------------------------------------------- profile photos
def profile_photo_path(user_id: str) -> str:
    """The user's uploaded photo if there is one, otherwise assets/profile.jpg."""
    for ext in config.SUPPORTED_IMAGE_TYPES:
        p = config.PHOTO_DIR / f"{user_id}{ext}"
        if p.exists():
            return str(p)
    return config.PROFILE_IMAGE


def save_profile_photo(user_id: str, source) -> str:
    """Save an uploaded photo (path, bytes or file object) as data/profile_photos/<id>.png."""
    try:
        if isinstance(source, (str, Path)):
            img = Image.open(source)
        elif isinstance(source, (bytes, bytearray)):
            img = Image.open(io.BytesIO(source))
        else:
            img = Image.open(source)
        img = ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValueError("That file is not a valid image. Use JPG, PNG or WEBP.")
    img = ImageOps.fit(img, (480, 480), Image.LANCZOS)
    config.PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    for ext in config.SUPPORTED_IMAGE_TYPES:  # remove an older photo with another extension
        old = config.PHOTO_DIR / f"{user_id}{ext}"
        if old.exists():
            old.unlink()
    dest = config.PHOTO_DIR / f"{user_id}.png"
    img.save(dest, "PNG")
    return str(dest)


def remove_profile_photo(user_id: str):
    for ext in config.SUPPORTED_IMAGE_TYPES:
        old = config.PHOTO_DIR / f"{user_id}{ext}"
        if old.exists():
            old.unlink()


# ---------------------------------------------------------- web (data URI)
@lru_cache(maxsize=64)
def _data_uri_cached(path, mtime, size, circle, initials, label, quality):
    img = load_image(path, size=size, circle=circle, initials=initials, label=label)
    buf = io.BytesIO()
    if circle:
        img.save(buf, "PNG")
        mime = "image/png"
    else:
        img.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True)
        mime = "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(buf.getvalue()).decode()


def data_uri(path, size, circle=False, initials=None, label=None, quality=82) -> str:
    """Base64 'data:' URL for HTML/CSS (used by Streamlit and Gradio)."""
    found = find_image(path) if path else None
    mtime = found.stat().st_mtime if found else 0
    return _data_uri_cached(str(path), mtime, tuple(size), circle, initials, label, quality)


# ------------------------------------------------------------------ logo
def logo_image(size):
    """The DrukCare logo (assets/logo.png) as a transparent PIL image, or None if missing."""
    found = find_image(config.LOGO)
    if not found:
        return None
    try:
        with Image.open(found) as raw:
            img = raw.convert("RGBA")
            img.thumbnail((int(size), int(size)), Image.LANCZOS)
            return img.copy()
    except (UnidentifiedImageError, OSError, ValueError):
        return None


def logo_uri(size):
    """Logo as a PNG data: URL for HTML, or '' if there is no logo file."""
    img = logo_image(size * 2)
    if img is None:
        return ""
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@lru_cache(maxsize=16)
def _png_uri_cached(path, mtime, max_w):
    with Image.open(path) as raw:
        img = raw.convert("RGBA")
    if img.width > max_w:
        img = img.resize((max_w, int(img.height * max_w / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def png_uri(path, max_w=500) -> str:
    """Transparent PNG as a data: URL (for the logo and sidebar decoration). '' if the file is missing."""
    found = find_image(path) if path else None
    if not found:
        return ""
    try:
        return _png_uri_cached(str(found), found.stat().st_mtime, int(max_w))
    except (UnidentifiedImageError, OSError, ValueError):
        return ""


# ------------------------------------------------- whole-photo banners (no crop)
_bg_cache = {}


def banner_background(size, centering=(0.5, 0.62)) -> Image.Image:
    """The teal dzong landscape (config.BANNER_BACKGROUND) cropped to `size`, never stretched."""
    w, h = int(size[0]), int(size[1])
    if "src" not in _bg_cache:
        _bg_cache["src"] = load_image(config.BANNER_BACKGROUND, None, label="")
    return ImageOps.fit(_bg_cache["src"].convert("RGB"), (w, h), Image.LANCZOS, centering=centering)


def photo_card(src: Image.Image, size, align="right", radius=18) -> Image.Image:
    """Show the WHOLE photo, sharp and in full colour, inside `size`.

    The photo is fitted to the frame height and placed on the right. The rest of the frame
    shows the teal dzong landscape (config.BANNER_BACKGROUND), and the photo's left edge is
    softly blended into it, so every banner is one frame in the same DrukCare colours.
    """
    w, h = int(size[0]), int(size[1])
    src = src.convert("RGB")
    scale = min(w / src.width, h / src.height)
    pw, ph = max(1, round(src.width * scale)), max(1, round(src.height * scale))
    if pw >= w * 0.92:                      # photo already fills (almost) the whole width
        return ImageOps.fit(src, (w, h), Image.LANCZOS).convert("RGBA")
    pic = src.resize((pw, ph), Image.LANCZOS)
    x = w - pw if align == "right" else (w - pw) // 2
    y = (h - ph) // 2
    canvas = banner_background((w, h))
    feather = max(10, pw // 5)
    ramp = Image.linear_gradient("L").rotate(90).resize((feather, ph))   # dark -> light, left to right
    if ramp.getpixel((0, 0)) > 128:
        ramp = ImageOps.invert(ramp)
    mask = Image.new("L", (pw, ph), 255)
    mask.paste(ramp, (0, 0))
    canvas.paste(pic, (x, y), mask)
    return canvas.convert("RGBA")


@lru_cache(maxsize=32)
def _full_uri_cached(path, mtime, max_w, blur):
    with Image.open(path) as raw:
        img = ImageOps.exif_transpose(raw).convert("RGB")
    if blur:
        edge = img.crop((0, 0, max(2, img.width // 40), img.height)).resize((1, 120), Image.BOX)
        img = edge.resize((240, 120), Image.BILINEAR).filter(ImageFilter.GaussianBlur(3))
    elif img.width > max_w:
        img = img.resize((max_w, int(img.height * max_w / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def full_uri(path, max_w=1600, blur=False) -> str:
    """The WHOLE photo (not cropped) as a data: URL; blur=True gives a tiny blurred copy for backgrounds."""
    found = find_image(path) if path else None
    if not found:
        return data_uri(path, (max_w, int(max_w * 0.3)))
    try:
        return _full_uri_cached(str(found), found.stat().st_mtime, int(max_w), bool(blur))
    except (UnidentifiedImageError, OSError, ValueError):
        return data_uri(path, (max_w, int(max_w * 0.3)))


def image_ratio(path, default=16 / 9) -> float:
    """Width / height of a photo (used to size banners so the whole photo shows)."""
    found = find_image(path) if path else None
    try:
        with Image.open(found) as raw:
            return raw.width / raw.height
    except Exception:
        return default


@lru_cache(maxsize=32)
def _card_uri_cached(path, mtime, size):
    img = photo_card(load_image(path, None, label=""), size).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=86, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def card_uri(path, size=(1600, 340)) -> str:
    """photo_card() as a data: URL - the web banners look the same as the desktop ones."""
    found = find_image(path) if path else None
    return _card_uri_cached(str(path), found.stat().st_mtime if found else 0, tuple(size))
