from __future__ import annotations

import os
import sys
import sysconfig
from pathlib import Path


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_project_root_on_sys_path(project_root: Path | None = None) -> Path:
    root = project_root or get_project_root()
    root_str = str(root)

    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    return root


def get_qt_plugin_candidates(purelib_path: str | Path | None = None) -> list[Path]:
    purelib = Path(purelib_path or sysconfig.get_path("purelib"))
    return [
        purelib / "PyQt5" / "Qt5" / "plugins" / "platforms",
        purelib / "PyQt5" / "Qt" / "plugins" / "platforms",
    ]


def detect_qt_plugin_path(purelib_path: str | Path | None = None) -> Path | None:
    for candidate in get_qt_plugin_candidates(purelib_path):
        if candidate.is_dir():
            return candidate
    return None


def configure_qt_plugin_path(purelib_path: str | Path | None = None) -> Path | None:
    existing = os.environ.get("QT_QPA_PLATFORM_PLUGIN_PATH")
    if existing:
        return Path(existing)

    plugin_path = detect_qt_plugin_path(purelib_path)
    if plugin_path is not None:
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(plugin_path)
    return plugin_path


def main():
    ensure_project_root_on_sys_path()
    configure_qt_plugin_path()

    from main import main as app_main

    return app_main()


if __name__ == "__main__":
    main()
