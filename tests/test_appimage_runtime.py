import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dtw_appimage_runtime


class BundledTclTkRuntimeTests(unittest.TestCase):
    def test_appimage_configures_bundled_tcl_and_tk_script_directories(self):
        with tempfile.TemporaryDirectory() as tempdir:
            library = Path(tempdir) / "lib"
            tcl_dir = library / "tcl8.6"
            tk_dir = library / "tk8.6"
            tcl_dir.mkdir(parents=True)
            tk_dir.mkdir(parents=True)
            (tcl_dir / "init.tcl").write_text("# bundled Tcl fixture", encoding="utf-8")
            (tk_dir / "tk.tcl").write_text("# bundled Tk fixture", encoding="utf-8")

            with patch.object(dtw_appimage_runtime.sys, "prefix", tempdir):
                with patch.dict(os.environ, {"APPDIR": "/tmp/test-appdir"}, clear=False):
                    os.environ.pop("TCL_LIBRARY", None)
                    os.environ.pop("TK_LIBRARY", None)
                    try:
                        dtw_appimage_runtime.configure_bundled_tcl_tk()
                        self.assertEqual(os.environ["TCL_LIBRARY"], str(tcl_dir))
                        self.assertEqual(os.environ["TK_LIBRARY"], str(tk_dir))
                    finally:
                        os.environ.pop("TCL_LIBRARY", None)
                        os.environ.pop("TK_LIBRARY", None)

    def test_system_launch_does_not_override_host_tcl_paths(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("APPDIR", None)
            os.environ["TCL_LIBRARY"] = "/host/tcl"
            os.environ["TK_LIBRARY"] = "/host/tk"
            try:
                dtw_appimage_runtime.configure_bundled_tcl_tk()
                self.assertEqual(os.environ["TCL_LIBRARY"], "/host/tcl")
                self.assertEqual(os.environ["TK_LIBRARY"], "/host/tk")
            finally:
                os.environ.pop("TCL_LIBRARY", None)
                os.environ.pop("TK_LIBRARY", None)


if __name__ == "__main__":
    unittest.main()
