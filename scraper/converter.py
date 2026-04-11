from __future__ import annotations

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

        source_ext = Path(file_path).suffix.lower()
        if source_ext == ".svg":
            output_path = self.render_svg_to_png(file_path, make_unique_path=make_unique_path)
        else:
            output_path = self.convert_raster_image(file_path, make_unique_path=make_unique_path)

        if output_path and not self.keep_original and output_path != file_path:
            os.remove(file_path)

        return output_path

    def convert_raster_image(self, file_path: str, make_unique_path=None) -> str | None:
        image_module, unidentified_error = self.load_pillow(file_path)

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
                return output_path
        except unidentified_error as exc:
            suffix = Path(file_path).suffix.lower()
            if suffix == ".avif":
                raise RuntimeError(
                    f"无法解码 AVIF 图片：{file_path}。请确认已安装 `pillow-avif-plugin`。"
                ) from exc
            raise RuntimeError(f"无法识别图片内容：{file_path}") from exc

    def render_svg_to_png(self, file_path: str, make_unique_path=None) -> str:
        try:
            from PyQt5.QtCore import QRectF, Qt
            from PyQt5.QtGui import QImage, QPainter
            from PyQt5.QtSvg import QSvgRenderer
        except ImportError as exc:
            raise RuntimeError("SVG 渲染依赖 PyQt5.QtSvg，请确认 PyQt5 已正确安装。") from exc

        renderer = QSvgRenderer(file_path)
        if not renderer.isValid():
            raise RuntimeError(f"SVG 渲染失败，文件内容无效：{file_path}")

        width, height = self.resolve_svg_canvas_size(renderer)
        output_path = self.build_output_path(file_path, ".png")
        if make_unique_path is not None:
            output_path = make_unique_path(output_path)

        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(Qt.transparent)

        painter = QPainter(image)
        try:
            renderer.render(painter, QRectF(0, 0, width, height))
        finally:
            painter.end()

        if not image.save(output_path, "PNG"):
            raise RuntimeError(f"SVG 渲染完成，但 PNG 写入失败：{output_path}")

        return output_path

    def load_pillow(self, file_path: str):
        try:
            from PIL import Image, UnidentifiedImageError
        except ImportError as exc:
            raise RuntimeError(
                "自动生成兼容格式副本依赖 Pillow，请先执行 `pip install -r requirements.txt`。"
            ) from exc

        if Path(file_path).suffix.lower() == ".avif":
            self.ensure_avif_support()

        return Image, UnidentifiedImageError

    def ensure_avif_support(self) -> None:
        try:
            import pillow_avif  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "AVIF 转码依赖 `pillow-avif-plugin`，请先执行 `pip install -r requirements.txt`。"
            ) from exc

        register_opener = getattr(pillow_avif, "register_avif_opener", None)
        if callable(register_opener):
            register_opener()

    def has_transparency(self, image) -> bool:
        if image.mode in {"RGBA", "LA"}:
            alpha = image.getchannel("A")
            minimum_alpha, _ = alpha.getextrema()
            return minimum_alpha < 255

        if image.mode == "P":
            return "transparency" in image.info

        return False

    def resolve_svg_canvas_size(self, renderer) -> tuple[int, int]:
        default_size = renderer.defaultSize()
        if default_size.isValid() and default_size.width() > 0 and default_size.height() > 0:
            return default_size.width(), default_size.height()

        view_box = renderer.viewBoxF()
        if view_box.isValid() and view_box.width() > 0 and view_box.height() > 0:
            return max(1, int(view_box.width())), max(1, int(view_box.height()))

        return 1024, 1024

    def build_output_path(self, file_path: str, target_ext: str) -> str:
        file_path_obj = Path(file_path)
        output_name = f"{file_path_obj.stem}_compatible{target_ext}"
        return str(file_path_obj.with_name(output_name))

    def build_save_kwargs(self, target_format: str) -> dict:
        if target_format == "JPEG":
            return {"quality": 92}
        return {}
