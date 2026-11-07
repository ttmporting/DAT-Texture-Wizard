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

    def test_appimage_uses_original_icon_asset(self):
        with (ROOT / "pyproject.toml").open("rb") as stream:
            config = tomllib.load(stream)
        self.assertEqual(config["tool"]["appimage"]["icon"], "imgs/appIcon.png")
        icon = ROOT / "imgs" / "appIcon.png"
        self.assertTrue(icon.is_file())
        payload = icon.read_bytes()
        self.assertTrue(payload.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(int.from_bytes(payload[16:20], "big"), 48)
        self.assertEqual(int.from_bytes(payload[20:24], "big"), 48)

    def test_desktop_entry_matches_window_class_and_icon_name(self):
        desktop = (ROOT / "packaging" / "DATTextureWizard.desktop").read_text(encoding="utf-8")
        self.assertIn("Icon=DATTextureWizard\n", desktop)
        self.assertIn("StartupWMClass=DATTextureWizard\n", desktop)
        self.assertIn("Categories=Graphics;\n", desktop)
        self.assertNotIn("Categories=Graphics;Utility;Game;", desktop)

    def test_gui_sets_matching_window_class_and_uses_bundled_icon(self):
        gui = (ROOT / "dtw_gui.py").read_text(encoding="utf-8")
        self.assertIn('self.root.tk.call("wm", "class", self.root._w, "DATTextureWizard")', gui)
        self.assertIn('Path(appdir) / "DATTextureWizard.png"', gui)
        self.assertIn('self.root.iconphoto(True, self._application_icon)', gui)


if __name__ == "__main__":
    unittest.main()
