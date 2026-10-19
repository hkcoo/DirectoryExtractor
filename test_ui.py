from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import app  # noqa: E402
from app import MainWindow  # noqa: E402


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_window_builds_and_scans(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "first.txt").write_text("1", encoding="utf-8")
            Path(folder, "second.csv").write_text("2", encoding="utf-8")
            window = MainWindow()
            window.path_edit.setText(folder)
            window.start_scan(False)

            loop = QEventLoop()
            if window.scan_thread:
                window.scan_thread.finished.connect(loop.quit)
            QTimer.singleShot(5000, loop.quit)
            loop.exec()
            self.assertFalse(window.is_scanning)
            self.assertEqual(window.model.rowCount(), 2)
            self.assertEqual(window.proxy.rowCount(), 2)

            window.search_edit.setText("first")
            self.assertEqual(window.proxy.rowCount(), 1)
            window.hide_extension.setChecked(True)
            self.assertEqual(window.model.index(0, 1).data(), "first")
            window.close()

    def test_scan_callbacks_run_in_main_thread(self) -> None:
        """回归测试：扫描回调必须回到主线程执行。

        历史 bug：worker.completed 曾连接到一个 lambda，PySide6 会把这种
        无接收者的可调用对象当作直接连接，于是在子线程里更新
        QAbstractTableModel，造成 QBasicTimer 跨线程警告并最终访问违例
        （0xC0000005）崩溃。

        探针挂在 FileTableModel 上（该类没有 @Slot 基类方法，覆盖是安全的），
        因为它正是 _scan_completed 里被调用的对象，能真实反映槽函数所在线程。
        """
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "only.txt").write_text("x", encoding="utf-8")
            seen: list[str] = []

            class ProbeModel(app.FileTableModel):
                def set_records(self, records) -> None:
                    seen.append(threading.current_thread().name)
                    super().set_records(records)

            original_model_class = app.FileTableModel
            app.FileTableModel = ProbeModel
            try:
                window = MainWindow()
            finally:
                app.FileTableModel = original_model_class

            window.path_edit.setText(folder)
            window.start_scan(False)

            loop = QEventLoop()
            if window.scan_thread:
                window.scan_thread.finished.connect(loop.quit)
            QTimer.singleShot(5000, loop.quit)
            loop.exec()

            self.assertEqual(window.model.rowCount(), 1)
            self.assertTrue(seen)
            self.assertEqual(set(seen), {"MainThread"})
            self.assertFalse(window.is_scanning)
            window.close()


if __name__ == "__main__":
    unittest.main()
