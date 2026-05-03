import unittest
from pathlib import Path
from unittest import mock

import build_release
from build_release import (
    build_exe_name,
    build_trial_package,
    determine_artifact_suffix,
    infer_app_basename,
    normalize_build_plan,
    normalize_build_ui_variant,
    should_bundle_playwright_browser_dir_name,
)
from product_profile import build_plan_app_name, build_trial_app_name


class BuildReleaseTests(unittest.TestCase):
    def test_normalize_build_plan(self):
        self.assertEqual(normalize_build_plan("gold"), "gold")
        self.assertEqual(normalize_build_plan("SILVER"), "silver")
        self.assertEqual(normalize_build_plan("invalid"), "")

    def test_plan_app_name(self):
        self.assertEqual(build_plan_app_name("bronze"), "KYOUTEI AI ZERO BRONZE")
        self.assertEqual(build_plan_app_name("silver"), "KYOUTEI AI ZERO SILVER")
        self.assertEqual(build_plan_app_name("gold"), "KYOUTEI AI ZERO GOLD")
        self.assertEqual(build_trial_app_name(), "kyoutei_auto_entry_trial")

    def test_build_exe_name(self):
        self.assertEqual(build_exe_name("KYOUTEI AI ZERO BRONZE", "0.3.1"), "KYOUTEI AI ZERO BRONZE_v0.3.1")

    def test_infer_app_basename_defaults_to_product_name(self):
        self.assertEqual(infer_app_basename(Path("kyoutei_auto_entry.spec"), ""), "KYOUTEI AI ZERO")

    def test_normalize_build_ui_variant(self):
        self.assertEqual(normalize_build_ui_variant("classic_trial"), "classic_trial")
        self.assertEqual(normalize_build_ui_variant("CLASSIC_TRIAL"), "classic_trial")
        self.assertEqual(normalize_build_ui_variant("product"), "")

    def test_determine_artifact_suffix_keeps_numeric_version_suffix_from_becoming_extension(self):
        artifact = Path("KYOUTEI AI ZERO BRONZE_v0.3.1")
        with mock.patch.object(build_release.os, "name", "posix"):
            self.assertEqual(determine_artifact_suffix(artifact), "")

    def test_determine_artifact_suffix_returns_exe_on_windows(self):
        artifact = Path("KYOUTEI AI ZERO BRONZE_v0.3.1")
        with mock.patch.object(build_release.os, "name", "nt"):
            self.assertEqual(determine_artifact_suffix(artifact), ".exe")

    def test_build_trial_package_uses_gold_and_classic_ui(self):
        with mock.patch.object(build_release, "build_single_plan", return_value=Path("dist/kyoutei_auto_entry_trial_v0.3.3.exe")) as mocked:
            result = build_trial_package(
                spec_file=Path("kyoutei_auto_entry.spec"),
                version_file=Path("VERSION.txt"),
                changelog_file=Path("docs/CHANGELOG_CUSTOMER.md"),
                clean=True,
                dry_run=True,
                bundle_browser=False,
            )
        self.assertEqual(result, Path("dist/kyoutei_auto_entry_trial_v0.3.3.exe"))
        mocked.assert_called_once()
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs["fixed_plan_tier"], "gold")
        self.assertEqual(kwargs["ui_variant"], "classic_trial")
        self.assertEqual(kwargs["app_basename_override"], "kyoutei_auto_entry_trial")

    def test_should_bundle_playwright_browser_dir_name_includes_headless_shell(self):
        self.assertTrue(should_bundle_playwright_browser_dir_name("chromium-1208"))
        self.assertTrue(should_bundle_playwright_browser_dir_name("chromium_headless_shell-1208"))
        self.assertTrue(should_bundle_playwright_browser_dir_name("ffmpeg-1011"))
        self.assertTrue(should_bundle_playwright_browser_dir_name("winldd-1007"))
        self.assertFalse(should_bundle_playwright_browser_dir_name("firefox-1509"))


if __name__ == "__main__":
    unittest.main()
