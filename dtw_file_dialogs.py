"""Make Tk's built-in Linux file dialogs accept directly pasted directory paths.

Tk 8.6 renders the Directory control as a ttk menubutton. This module replaces
that control with an editable ttk.Entry while preserving Tk's file-list,
filter, filename, open/save, and directory-selection behavior.
"""
from __future__ import annotations


_TCL_INSTALL_SCRIPT = r"""
if {![llength [info commands ::tk::dialog::file::Create]]} {
    catch {auto_load ::tk::dialog::file::Create}
}
if {![llength [info commands ::tk::dialog::file::Create]]} {
    error "Tk file dialog implementation is unavailable"
}

namespace eval ::dtw {}

proc ::dtw::ApplyFileDialogDirectory {w showError} {
    if {![winfo exists $w]} {
        return 0
    }
    set dataName [winfo name $w]
    upvar ::tk::dialog::file::$dataName data
    if {![info exists data(dirMenuBtn)] || ![winfo exists $data(dirMenuBtn)]} {
        return 0
    }

    set candidate [string trim [$data(dirMenuBtn) get]]
    if {$candidate eq ""} {
        set candidate $data(dtwLastValidPath)
    }

    if {[file isdirectory $candidate]} {
        set normalized [file normalize $candidate]
        set data(selectPath) $normalized
        set data(dtwLastValidPath) $normalized
        if {[winfo class $w] eq "TkChooseDir" && [info exists data(ent)] && [winfo exists $data(ent)]} {
            $data(ent) delete 0 end
            $data(ent) insert 0 $normalized
        }
        ::tk::dialog::file::UpdateWhenIdle $w
        return 1
    }

    # A complete file path is also useful in Open/Save dialogs: navigate to
    # its parent and put the basename in the normal File name field.
    if {[winfo class $w] eq "TkFDialog" && [file isfile $candidate]} {
        set normalized [file normalize $candidate]
        set parent [file dirname $normalized]
        set data(selectPath) $parent
        set data(dtwLastValidPath) $parent
        set data(selectFile) [file tail $normalized]
        if {[info exists data(ent)] && [winfo exists $data(ent)]} {
            $data(ent) delete 0 end
            $data(ent) insert 0 $data(selectFile)
        }
        ::tk::dialog::file::UpdateWhenIdle $w
        return 1
    }

    # Don't leave an invalid/partially typed path in Tk's current-directory
    # variable. On Enter, explain the problem; on focus change, restore quietly.
    set data(selectPath) $data(dtwLastValidPath)
    if {$showError && $candidate ne ""} {
        tk_messageBox -type ok -icon warning -parent $w \
            -title "Directory not found" \
            -message "This directory or file path does not exist:\n\n$candidate"
    }
    return 0
}

# Preserve Tk's regular directory-change behavior, except while the user is
# editing the path field. Updating the file list on every typed character
# would make partially entered paths unusable.
if {![llength [info commands ::tk::dialog::file::DTWOriginalSetPath]]} {
    rename ::tk::dialog::file::SetPath ::tk::dialog::file::DTWOriginalSetPath
    proc ::tk::dialog::file::SetPath {w name1 name2 op} {
        if {[winfo exists $w]} {
            set dataName [winfo name $w]
            upvar ::tk::dialog::file::$dataName data
            if {[info exists data(dirMenuBtn)] && [winfo exists $data(dirMenuBtn)]} {
                if {[focus] eq $data(dirMenuBtn)} {
                    return
                }
            }
            if {[info exists data(selectPath)] && [file isdirectory $data(selectPath)]} {
                set data(dtwLastValidPath) [file normalize $data(selectPath)]
            }
        }
        ::tk::dialog::file::DTWOriginalSetPath $w $name1 $name2 $op
    }
}

# Config runs for both first-time and reused dialogs, so refresh the safe
# fallback directory whenever Tk initializes a dialog.
if {![llength [info commands ::tk::dialog::file::DTWOriginalConfig]]} {
    rename ::tk::dialog::file::Config ::tk::dialog::file::DTWOriginalConfig
    proc ::tk::dialog::file::Config {dataName type argList} {
        ::tk::dialog::file::DTWOriginalConfig $dataName $type $argList
        upvar ::tk::dialog::file::$dataName data
        if {[info exists data(selectPath)] && [file isdirectory $data(selectPath)]} {
            set data(dtwLastValidPath) [file normalize $data(selectPath)]
        }
    }
}

# Tk creates the standard Directory menubutton first. Replace it at the same
# widget path with an Entry so Tk's own dialog code can keep using dirMenuBtn.
if {![llength [info commands ::tk::dialog::file::DTWOriginalCreate]]} {
    rename ::tk::dialog::file::Create ::tk::dialog::file::DTWOriginalCreate
    proc ::tk::dialog::file::Create {w class} {
        ::tk::dialog::file::DTWOriginalCreate $w $class
        if {$class ni {TkFDialog TkChooseDir}} {
            return
        }

        set dataName [winfo name $w]
        upvar ::tk::dialog::file::$dataName data
        set entry $data(dirMenuBtn)
        set menuPath $data(dirMenu)
        set pathVariable ::tk::dialog::file::${dataName}(selectPath)

        destroy $entry
        ttk::entry $entry -textvariable $pathVariable -width 48
        $entry configure -takefocus 1 -cursor xterm

        # Tk's update routine expects this history menu even though the new
        # editable path field no longer displays it.
        menu $menuPath -tearoff 0

        pack $entry -expand yes -fill both -padx 4
        set data(dtwLastValidPath) $data(selectPath)

        bind $entry <Return> [list ::dtw::ApplyFileDialogDirectory $w 1]
        bind $entry <Return> +break
        bind $entry <FocusOut> [list ::dtw::ApplyFileDialogDirectory $w 0]
        bind $entry <Control-a> {%W selection range 0 end; %W icursor end; break}
        bind $entry <Control-A> {%W selection range 0 end; %W icursor end; break}
        bind $entry <Control-v> {event generate %W <<Paste>>; break}
        bind $entry <Control-V> {event generate %W <<Paste>>; break}
    }
}
"""


def install_editable_file_dialog_paths(root) -> None:
    """Enable editable Directory fields in Tk Open, Save, and Choose Directory dialogs."""
    root.tk.eval(_TCL_INSTALL_SCRIPT)
