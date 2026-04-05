import logging
from pathlib import Path


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"

VALID_IMAGE_EXTENSIONS = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".webp",
        ".svg",
        ".tiff",
        ".ico",
        ".avif",
    }
)

COMMON_IMAGE_EXTENSIONS = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
    }
)

CONVERTIBLE_IMAGE_EXTENSIONS = frozenset(
    {
        ".webp",
        ".avif",
        ".tiff",
        ".bmp",
        ".svg",
    }
)

CONTENT_TYPE_TO_EXTENSION = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/tiff": ".tiff",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
    "image/avif": ".avif",
}

IMAGE_CATEGORY_MAP = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".gif": "GIF",
    ".webp": "WEBP",
    ".svg": "SVG",
    ".bmp": "BMP",
    ".tiff": "TIFF",
    ".ico": "ICO",
    ".avif": "AVIF",
}

UNWANTED_IMAGE_KEYWORDS = (
    "icon",
    "logo",
    "avatar",
    "favicon",
    "sprite",
    "badge",
    "thumb",
    "thumbnail",
)

UNWANTED_IMAGE_SIZE_HINTS = (
    "16x16",
    "24x24",
    "32x32",
    "48x48",
    "64x64",
    "96x96",
    "128x128",
)


def get_log_dir() -> Path:
    LOG_DIR.mkdir(exist_ok=True)
    return LOG_DIR


def setup_logger():
    logger = logging.getLogger("image_scraper")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    file_handler = logging.FileHandler(
        get_log_dir() / "app.log",
        encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    return logger


def append_failed_image_log(image_url: str, error: Exception) -> None:
    failed_images_log = get_log_dir() / "failed_images.txt"
    with failed_images_log.open("a", encoding="utf-8") as file_obj:
        file_obj.write(f"{image_url}\n|{error}\n")


def append_failed_conversion_log(image_path: str, error: Exception) -> None:
    failed_conversions_log = get_log_dir() / "failed_conversions.txt"
    with failed_conversions_log.open("a", encoding="utf-8") as file_obj:
        file_obj.write(f"{image_path}\n|{error}\n")
