from __future__ import annotations

import unittest

from updater import compare_versions, normalize_tag, parse_version


class TestVersionCompare(unittest.TestCase):
    def test_normalize_tag_strips_prefix(self) -> None:
        self.assertEqual(normalize_tag("v1.2.3"), "1.2.3")
        self.assertEqual(normalize_tag("V1.2.3"), "1.2.3")
        self.assertEqual(normalize_tag("1.2.3"), "1.2.3")

    def test_parse_version_int_tuple(self) -> None:
        self.assertEqual(parse_version("1.2.3"), (1, 2, 3))
        self.assertEqual(parse_version("v2.0"), (2, 0))

    def test_equal(self) -> None:
        self.assertEqual(compare_versions("1.0.0", "1.0.0"), 0)
        self.assertEqual(compare_versions("v1.0.0", "1.0.0"), 0)

    def test_newer_available(self) -> None:
        # 当前旧于线上 -> -1
        self.assertEqual(compare_versions("1.0.0", "1.2.0"), -1)
        self.assertEqual(compare_versions("1.0.0", "v1.0.1"), -1)
        self.assertEqual(compare_versions("1.9.0", "1.10.0"), -1)  # 数值比较而非字典序

    def test_current_newer(self) -> None:
        self.assertEqual(compare_versions("1.2.0", "1.0.0"), 1)

    def test_missing_segment(self) -> None:
        self.assertEqual(compare_versions("2.0", "2.0.0"), 0)
        self.assertEqual(compare_versions("2.0", "2.1.0"), -1)

    def test_non_numeric_suffix_ignored(self) -> None:
        self.assertEqual(compare_versions("1.0.0", "1.0.0-beta"), 0)


if __name__ == "__main__":
    unittest.main()
