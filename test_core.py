from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core import FileRecord, normalize_directory, scan_directory, suggested_export_name


class CoreTests(unittest.TestCase):
    def test_current_directory_only(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "B.txt").write_text("b", encoding="utf-8")
            (root / "a.txt").write_text("a", encoding="utf-8")
            child = root / "child"
            child.mkdir()
            (child / "nested.txt").write_text("n", encoding="utf-8")
            result = scan_directory(folder, recursive=False)
            self.assertEqual([item.file_name for item in result.records], ["a.txt", "B.txt"])
            self.assertFalse(result.cancelled)

    def test_recursive_scan_and_progress(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            nested = root / "nested"
            nested.mkdir()
            for index in range(251):
                (nested / f"file-{index:03}.dat").write_text("x", encoding="utf-8")
            updates: list[int] = []
            result = scan_directory(folder, recursive=True, progress=updates.append)
            self.assertEqual(len(result.records), 251)
            self.assertEqual(updates, [250])

    def test_cancelled_scan(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "one.txt").write_text("1", encoding="utf-8")
            result = scan_directory(folder, recursive=False, cancelled=lambda: True)
            self.assertTrue(result.cancelled)
            self.assertEqual(result.records, [])

    def test_display_name_and_validation(self) -> None:
        item = FileRecord("C:/demo/report.final.pdf", "report.final.pdf")
        self.assertEqual(item.display_name(True), "report.final")
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(normalize_directory(folder), str(Path(folder).resolve()))
            self.assertTrue(suggested_export_name(folder, "csv").endswith("_文件清单.csv"))


if __name__ == "__main__":
    unittest.main()
