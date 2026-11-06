"""Regression checks for editable directory fields in Tk file dialogs."""
import tkinter
import unittest
from unittest.mock import Mock

import dtw_file_dialogs


class EditableFileDialogPathTests(unittest.TestCase):
    def test_installer_applies_the_tk_dialog_patch(self):
        root = Mock()
        dtw_file_dialogs.install_editable_file_dialog_paths(root)
        root.tk.eval.assert_called_once_with(dtw_file_dialogs._TCL_INSTALL_SCRIPT)

    def test_tcl_patch_is_syntactically_complete(self):
        interpreter = tkinter.Tcl()
        self.assertEqual(
            int(interpreter.call("info", "complete", dtw_file_dialogs._TCL_INSTALL_SCRIPT)),
            1,
        )

    def test_directory_field_supports_select_all_and_clipboard_paste(self):
        script = dtw_file_dialogs._TCL_INSTALL_SCRIPT
        self.assertIn("ttk::entry $entry", script)
        self.assertIn("bind $entry <Control-a>", script)
        self.assertIn("bind $entry <Control-v>", script)
        self.assertIn("event generate %W <<Paste>>", script)

    def test_return_applies_directory_and_file_paths(self):
        script = dtw_file_dialogs._TCL_INSTALL_SCRIPT
        self.assertIn("file isdirectory $candidate", script)
        self.assertIn("file isfile $candidate", script)
        self.assertIn("file dirname $normalized", script)
        self.assertIn("file tail $normalized", script)

    def test_invalid_typed_path_restores_last_valid_directory(self):
        script = dtw_file_dialogs._TCL_INSTALL_SCRIPT
        self.assertIn("set data(selectPath) $data(dtwLastValidPath)", script)
        self.assertIn('if {$showError && $candidate ne ""}', script)


if __name__ == "__main__":
    unittest.main()
