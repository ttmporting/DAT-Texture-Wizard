import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class NativePackagingMetadataTests(unittest.TestCase):
    def test_python2_windows_setup_is_not_discovered_by_pep517(self):
        self.assertFalse(
            (ROOT / "setup.py").exists(),
            "The Python 2 cx_Freeze setup.py would be executed by setuptools.",
        )
        self.assertTrue((ROOT / "legacy" / "windows-setup-cxfreeze.py").is_file())

    def test_pyproject_declares_native_setuptools_backend(self):
        with (ROOT / "pyproject.toml").open("rb") as stream:
            config = tomllib.load(stream)
        self.assertEqual(config["build-system"]["build-backend"], "setuptools.build_meta")
        self.assertIn("dtw_gui", config["tool"]["setuptools"]["py-modules"])
        self.assertIn("dtw_appimage_runtime", config["tool"]["setuptools"]["py-modules"])


if __name__ == "__main__":
    unittest.main()
