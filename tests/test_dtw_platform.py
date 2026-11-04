import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dtw_platform


class PlatformHelpersTests(unittest.TestCase):
    def test_application_root_uses_module_location(self):
        result = dtw_platform.application_root("/opt/dtw/main.py")
        self.assertEqual(result, Path("/opt/dtw"))

    def test_resource_path_is_relative_to_root(self):
        result = dtw_platform.resource_path("imgs/appIcon.png", "/opt/dtw")
        self.assertEqual(result, Path("/opt/dtw/imgs/appIcon.png"))

    def test_find_executable_prefers_executable_bundled_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "pngquant"
            candidate.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            candidate.chmod(0o755)
            with mock.patch.object(
                dtw_platform.shutil, "which", return_value="/usr/bin/pngquant"
            ):
                found = dtw_platform.find_executable("pngquant", [candidate])
            self.assertEqual(found, str(candidate.resolve()))

    def test_find_executable_ignores_non_executable_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "pngquant"
            candidate.write_text("not executable", encoding="utf-8")
            with mock.patch.object(
                dtw_platform.shutil, "which", return_value="/usr/bin/pngquant"
            ):
                found = dtw_platform.find_executable("pngquant", [candidate])
            self.assertEqual(found, "/usr/bin/pngquant")

    def test_popen_drops_windows_creationflags_on_linux(self):
        with mock.patch.object(dtw_platform.sys, "platform", "linux"), \
             mock.patch.object(dtw_platform.subprocess, "Popen") as popen_mock:
            dtw_platform.popen(["true"], creationflags=123, stdout=subprocess.PIPE)
        self.assertNotIn("creationflags", popen_mock.call_args.kwargs)
        self.assertEqual(popen_mock.call_args.kwargs["stdout"], subprocess.PIPE)

    def test_popen_adds_no_window_flag_on_windows(self):
        with mock.patch.object(dtw_platform.sys, "platform", "win32"), \
             mock.patch.object(dtw_platform.subprocess, "Popen") as popen_mock:
            dtw_platform.popen(["cmd", "/c", "exit", "0"])
        self.assertIn("creationflags", popen_mock.call_args.kwargs)

    def test_set_toolwindow_is_skipped_on_linux(self):
        window = mock.Mock()
        with mock.patch.object(dtw_platform.sys, "platform", "linux"):
            self.assertFalse(dtw_platform.set_toolwindow_if_supported(window))
        window.attributes.assert_not_called()

    def test_set_toolwindow_is_applied_on_windows(self):
        window = mock.Mock()
        with mock.patch.object(dtw_platform.sys, "platform", "win32"):
            self.assertTrue(dtw_platform.set_toolwindow_if_supported(window))
        window.attributes.assert_called_once_with("-toolwindow", 1)


    def test_find_executable_prefers_environment_override(self):
        import os
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "custom-pngquant"
            candidate.write_text("#!/bin/sh\\nexit 0\\n", encoding="utf-8")
            candidate.chmod(0o755)
            with mock.patch.dict(os.environ, {"DTW_PNGQUANT": str(candidate)}):
                found = dtw_platform.find_executable(
                    "pngquant", ["/missing/pngquant"], env_var="DTW_PNGQUANT"
                )
            self.assertEqual(found, str(candidate.resolve()))

    def test_application_root_uses_executable_when_frozen(self):
        with mock.patch.object(dtw_platform.sys, "frozen", True, create=True), \\
             mock.patch.object(dtw_platform.sys, "executable", "/opt/dtw/DtwApp"):
            result = dtw_platform.application_root("/ignored/source.py")
        self.assertEqual(result, Path("/opt/dtw"))

    def test_open_path_uses_xdg_open_and_safe_argument_list(self):
        target = Path("/tmp/folder with spaces; do-not-run")
        with mock.patch.object(dtw_platform.sys, "platform", "linux"), \\
             mock.patch.object(dtw_platform.shutil, "which", return_value="/usr/bin/xdg-open"), \\
             mock.patch.object(dtw_platform.subprocess, "Popen") as popen_mock:
            dtw_platform.open_path(target)
        args, kwargs = popen_mock.call_args
        self.assertEqual(args[0], ["/usr/bin/xdg-open", str(target.resolve())])
        self.assertNotIn("shell", kwargs)
        self.assertEqual(kwargs["stdin"], dtw_platform.subprocess.DEVNULL)


if __name__ == "__main__":
    unittest.main()
