import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import launch_app


class LaunchAppTests(unittest.TestCase):
    def test_get_project_root_returns_repo_root(self):
        self.assertEqual(launch_app.get_project_root(), PROJECT_ROOT)

    def test_ensure_project_root_on_sys_path_inserts_root_once(self):
        sentinel_root = Path("/tmp/project-root")

        with patch.object(sys, "path", ["existing"]):
            launch_app.ensure_project_root_on_sys_path(sentinel_root)
            launch_app.ensure_project_root_on_sys_path(sentinel_root)

            self.assertEqual(sys.path[0], str(sentinel_root))
            self.assertEqual(sys.path.count(str(sentinel_root)), 1)

    def test_detect_qt_plugin_path_returns_first_existing_candidate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            purelib = Path(temp_dir)
            first_candidate = purelib / "PyQt5" / "Qt5" / "plugins" / "platforms"
            second_candidate = purelib / "PyQt5" / "Qt" / "plugins" / "platforms"
            second_candidate.mkdir(parents=True)
            first_candidate.mkdir(parents=True)

            detected = launch_app.detect_qt_plugin_path(purelib)

            self.assertEqual(detected, first_candidate)

    def test_configure_qt_plugin_path_preserves_existing_env(self):
        with patch.dict(os.environ, {"QT_QPA_PLATFORM_PLUGIN_PATH": "/tmp/custom"}, clear=False):
            detected = launch_app.configure_qt_plugin_path()

        self.assertEqual(detected, Path("/tmp/custom"))

    def test_configure_qt_plugin_path_sets_detected_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            purelib = Path(temp_dir)
            plugin_dir = purelib / "PyQt5" / "Qt5" / "plugins" / "platforms"
            plugin_dir.mkdir(parents=True)

            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("QT_QPA_PLATFORM_PLUGIN_PATH", None)
                detected = launch_app.configure_qt_plugin_path(purelib)
                configured = os.environ.get("QT_QPA_PLATFORM_PLUGIN_PATH")

            self.assertEqual(detected, plugin_dir)
            self.assertEqual(configured, str(plugin_dir))

    def test_main_delegates_to_application_entrypoint(self):
        calls = []

        def fake_app_main():
            calls.append("app_main")
            return 123

        fake_main_module = types.SimpleNamespace(main=fake_app_main)

        with patch.object(launch_app, "ensure_project_root_on_sys_path") as ensure_root:
            with patch.object(launch_app, "configure_qt_plugin_path") as configure_qt:
                with patch.dict(sys.modules, {"main": fake_main_module}, clear=False):
                    result = launch_app.main()

        ensure_root.assert_called_once_with()
        configure_qt.assert_called_once_with()
        self.assertEqual(calls, ["app_main"])
        self.assertEqual(result, 123)


if __name__ == "__main__":
    unittest.main()
