"""GUI 的无屏幕基础检查；未安装 PySide6 时自动跳过。"""

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


PYSIDE_AVAILABLE = importlib.util.find_spec("PySide6") is not None


@unittest.skipUnless(PYSIDE_AVAILABLE, "需要 PySide6")
class GuiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication

        cls.settings_directory = tempfile.TemporaryDirectory()
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            cls.settings_directory.name,
        )
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.settings_directory.cleanup()

    def test_main_window_can_be_created(self) -> None:
        from analyzer_gui import MainWindow

        window = MainWindow()
        self.assertEqual(window.windowTitle(), "文件分析工具")
        self.assertEqual(window.tabs.count(), 4)
        self.assertFalse(window.export_button.isEnabled())
        window.close()

    def test_worker_scans_and_detects_duplicates(self) -> None:
        from analyzer_gui import ScanWorker

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            (root / "a.txt").write_bytes(b"same")
            (root / "b.txt").write_bytes(b"same")
            completed = []
            failures = []
            worker = ScanWorker(root, find_duplicates=True)
            worker.finished.connect(completed.append)
            worker.failed.connect(failures.append)

            worker.run()

            self.assertEqual(failures, [])
            self.assertEqual(len(completed), 1)
            self.assertEqual(completed[0].total_files, 2)
            self.assertEqual(len(completed[0].duplicate_groups), 1)


if __name__ == "__main__":
    unittest.main()
