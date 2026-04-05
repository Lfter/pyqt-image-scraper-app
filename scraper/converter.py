import os
from pathlib import Path

from utils.helpers import CONVERTIBLE_IMAGE_EXTENSIONS, setup_logger


class ImageConverter:
    def __init__(self, keep_original: bool = True):
        self.keep_original = keep_original
        self.logger = setup_logger()

    def should_convert(self, file_path: str) -> bool:
        return Path(file_path).suffix.lower() in CONVERTIBLE_IMAGE_EXTENSIONS

    def convert_file(self, file_path: str, make_unique_path=None) -> str | None:
        if not self.should_convert(file_path):
            return None

        image_module, unidentified_error = self.load_pillow()

        try:
            with image_module.open(file_path) as image:
                if getattr(image, "is_animated", False):
                    self.logger.info("跳过动画图片转码：%s", file_path)
                    return None

                target_ext = ".png" if self.has_transparency(image) else ".jpg"
                target_format = "PNG" if target_ext == ".png" else "JPEG"
                output_path = self.build_output_path(file_path, target_ext)
                if make_unique_path is not None:
                    output_path = make_unique_path(output_path)

                converted = image.convert("RGBA" if target_ext == ".png" else "RGB")
                save_kwargs = self.build_save_kwargs(target_format)
                converted.save(output_path, target_format, **save_kwargs)
        except unidentified_error as exc:
            raise RuntimeError(f"无法识别图片内容：{file_path}") from exc

        if not self.keep_original and output_path != file_path:
            os.remove(file_path)

        return output_path

    def load_pillow(self):
        try:
            from PIL import Image, UnidentifiedImageError
        except ImportError as exc:
            raise RuntimeError(
                "自动生成兼容格式副本依赖 Pillow，请先执行 `pip install -r requirements.txt`。"
            ) from exc

        return Image, UnidentifiedImageError

    def has_transparency(self, image) -> bool:
        if image.mode in {"RGBA", "LA"}:
            alpha = image.getchannel("A")
            minimum_alpha, _ = alpha.getextrema()
            return minimum_alpha < 255

        if image.mode == "P":
            return "transparency" in image.info

        return False

    def build_output_path(self, file_path: str, target_ext: str) -> str:
        file_path_obj = Path(file_path)
        output_name = f"{file_path_obj.stem}_compatible{target_ext}"
        return str(file_path_obj.with_name(output_name))

    def build_save_kwargs(self, target_format: str) -> dict:
        if target_format == "JPEG":
            return {"quality": 92}
        return {}
