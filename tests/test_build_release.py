import unittest
from pathlib import Path
from unittest import mock

import build_release
from build_release import (
    build_exe_name,
    determine_artifact_suffix,
    infer_app_basename,
    should_bundle_playwright_browser_dir_name,
)


class BuildReleaseTests(unittest.TestCase):
    def test_build_exe_name(self):
        self.assertEqual(build_exe_name("AQUA EDGE AI", "0.3.1"), "AQUA EDGE AI_v0.3.1")

    def test_infer_app_basename_defaults_to_product_name(self):
        self.assertEqual(infer_app_basename(Path("kyoutei_auto_entry.spec"), ""), "AQUA EDGE AI")

    def test_determine_artifact_suffix_keeps_numeric_version_suffix_from_becoming_extension(self):
        artifact = Path("AQUA EDGE AI_v0.3.1")
        with mock.patch.object(build_release.os, "name", "posix"):
            self.assertEqual(determine_artifact_suffix(artifact), "")

    def test_determine_artifact_suffix_returns_exe_on_windows(self):
        artifact = Path("AQUA EDGE AI_v0.3.1")
        with mock.patch.object(build_release.os, "name", "nt"):
            self.assertEqual(determine_artifact_suffix(artifact), ".exe")

    def test_should_bundle_playwright_browser_dir_name_includes_headless_shell(self):
        self.assertTrue(should_bundle_playwright_browser_dir_name("chromium-1208"))
        self.assertTrue(should_bundle_playwright_browser_dir_name("chromium_headless_shell-1208"))
        self.assertTrue(should_bundle_playwright_browser_dir_name("ffmpeg-1011"))
        self.assertTrue(should_bundle_playwright_browser_dir_name("winldd-1007"))
        self.assertFalse(should_bundle_playwright_browser_dir_name("firefox-1509"))


if __name__ == "__main__":
    unittest.main()
