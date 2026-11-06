#!/usr/bin/env python3
"""Native Tk GUI preview: Melee-oriented GameCube file tree and DAT navigation."""
from __future__ import annotations

import argparse
import os
import struct
import sys
from pathlib import Path


def _configure_bundled_tcl_tk() -> None:
    """Point bundled Python/Tk at the Tcl scripts shipped inside an AppImage."""
    if not os.environ.get("APPDIR"):
        return
    library_root = Path(sys.prefix) / "lib"
    tcl_dirs = sorted(library_root.glob("tcl*"))
    tk_dirs = sorted(library_root.glob("tk*"))
    tcl_dir = next((path for path in tcl_dirs if (path / "init.tcl").is_file()), None)
    tk_dir = next((path for path in tk_dirs if (path / "tk.tcl").is_file()), None)
    if tcl_dir:
        os.environ["TCL_LIBRARY"] = str(tcl_dir)
    if tk_dir:
        os.environ["TK_LIBRARY"] = str(tk_dir)


# Configure paths before tkinter imports _tkinter and initializes Tcl/Tk.
_configure_bundled_tcl_tk()

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from dtw_dat_probe import DatFormatError
from dtw_dat_tree import DatTreeModel, TreeRecord
from dtw_character_tree import CharacterGroup, build_character_groups
from dtw_disc_labels import disc_file_description
from dtw_stage_tree import StageGroup, build_stage_groups
from dtw_gx_texture import (
    GXTextureError, TexturePreview, TextureScanReport, encode_rgba_png, png_data_uri,
    replace_texture_in_dat, resize_rgba_nearest, scan_gx_textures,
)
from dtw_gamecube import GameCubeFormatError, GameCubeIso, ReplacementError, FstEntry


class DatTextureWizardPreview:
    def __init__(self, root: tk.Tk, initial_file: str | None = None):
        self.root = root
        self.iso: GameCubeIso | None = None
        self.dat_model: DatTreeModel | None = None
        self.texture_scan_report: TextureScanReport | None = None
        self.texture_photo_refs: list[tk.PhotoImage] = []
        self.texture_cards: list[tuple[ttk.Frame, TexturePreview]] = []
        self.selected_texture: TexturePreview | None = None
        self.texture_preview_photo: tk.PhotoImage | None = None
        self.dat_original_data: bytes | None = None
        self.dat_working_data: bytes | None = None
        self.dat_modified = False
        self.records: dict[str, TreeRecord] = {}
        self.loaded: set[str] = set()
        self.disc_iids: dict[int, str] = {}
        self.disc_loaded: set[int] = set()
        self.character_groups: dict[str, CharacterGroup] = {}
        self.character_root_iid: str | None = None
        self.character_group_iids: dict[str, str] = {}
        self.character_group_code_by_iid: dict[str, str] = {}
        self.character_file_entries: dict[str, FstEntry] = {}
        self.character_file_iids: dict[int, str] = {}
        self.character_tree_loaded = False
        self.character_group_loaded: set[str] = set()
        self.stage_groups: dict[str, StageGroup] = {}
        self.stage_root_iid: str | None = None
        self.stage_categories: dict[str, list[StageGroup]] = {}
        self.stage_category_iids: dict[str, str] = {}
        self.stage_category_by_iid: dict[str, str] = {}
        self.stage_group_iids: dict[str, str] = {}
        self.stage_group_key_by_iid: dict[str, str] = {}
        self.stage_file_entries: dict[str, FstEntry] = {}
        self.stage_file_iids: dict[int, str] = {}
        self.stage_tree_loaded = False
        self.stage_category_loaded: set[str] = set()
        self.stage_group_loaded: set[str] = set()
        self.staged: dict[int, str] = {}
        self.selected_disc_entry: FstEntry | None = None
        self.search_hits: list[int] = []
        self.search_index = -1

        self.root.title("DAT Texture Wizard — Linux Preview")
        self.root.geometry("1380x820")
        self.root.minsize(1020, 640)
        self._build_menu()
        self._build_toolbar()
        self._build_tabs()
        self.status = tk.StringVar(value="Ready — open a Melee GameCube ISO or a standalone DAT")
        ttk.Separator(root).pack(fill="x")
        ttk.Label(root, textvariable=self.status, anchor="w", padding=(8, 4)).pack(fill="x")
        root.bind("<Control-o>", lambda _e: self.open_iso())
        root.bind("<Control-d>", lambda _e: self.open_dat())
        root.bind("<Control-f>", lambda _e: self.search_entry.focus_set())
        root.bind("<F5>", lambda _e: self.reload_current())
        if initial_file:
            suffix = Path(initial_file).suffix.casefold()
            root.after(120, lambda: self.load_iso(initial_file) if suffix in {".iso", ".gcm"} else self.load_file(initial_file))

    # ------------------------------------------------------------------ menus
    def _build_menu(self):
        menu = tk.Menu(self.root)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Open GameCube ISO / GCM…", accelerator="Ctrl+O", command=self.open_iso)
        file_menu.add_command(label="Open Standalone DAT…", accelerator="Ctrl+D", command=self.open_dat)
        file_menu.add_command(label="Reload", accelerator="F5", command=self.reload_current)
        file_menu.add_separator()
        file_menu.add_command(label="Rebuild / Save ISO As…", command=self.save_patched_iso, state="disabled")
        self.save_menu_index = 4
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.destroy)
        menu.add_cascade(label="File", menu=file_menu)
        self.file_menu = file_menu
        tools_menu = tk.Menu(menu, tearoff=False)
        tools_menu.add_command(label="Find in Melee Disc…", accelerator="Ctrl+F", command=self.focus_search)
        tools_menu.add_command(label="Export Selected File / Folder", command=self.export_selected)
        tools_menu.add_command(label="Import Replacement File…", command=self.import_replacement)
        menu.add_cascade(label="Tools", menu=tools_menu)
        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="About", command=self.show_about)
        menu.add_cascade(label="Help", menu=help_menu)
        self.root.configure(menu=menu)

    # --------------------------------------------------------------- toolbar
    def _build_toolbar(self):
        bar = ttk.Frame(self.root, padding=(10, 8))
        bar.pack(fill="x")
        ttk.Button(bar, text="Open Melee ISO", command=self.open_iso).pack(side="left")
        ttk.Button(bar, text="Open DAT", command=self.open_dat).pack(side="left", padx=(6, 14))
        ttk.Label(bar, text="Find in disc:").pack(side="left")
        self.query = tk.StringVar()
        self.search_entry = ttk.Entry(bar, textvariable=self.query, width=28)
        self.search_entry.pack(side="left", padx=6)
        self.search_entry.bind("<Return>", lambda _e: self.search_disc_next())
        ttk.Button(bar, text="Find next", command=self.search_disc_next).pack(side="left")
        self.filename = tk.StringVar(value="No disc or DAT loaded")
        ttk.Label(bar, textvariable=self.filename, anchor="e").pack(side="right", fill="x", expand=True, padx=12)

    # ------------------------------------------------------------------ tabs
    def _build_tabs(self):
        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.disc_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.disc_tab, text="Melee File Tree")
        self._build_disc_view()

        self.sa_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.sa_tab, text="Structural Analysis")
        self._build_structure_view()

        self.texture_tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(self.texture_tab, text="DAT Texture Tree")
        self._build_texture_view()

    def _build_texture_view(self):
        top = ttk.Frame(self.texture_tab)
        top.pack(fill="x", pady=(0, 8))
        self.texture_heading = ttk.Label(top, text="DAT Texture Tree", font=("TkDefaultFont", 14, "bold"))
        self.texture_heading.pack(side="left", padx=(2, 14))
        self.texture_scan_button = ttk.Button(
            top, text="Scan DAT / Refresh PNGs", command=self.scan_current_dat_textures, state="disabled"
        )
        self.texture_scan_button.pack(side="left")
        ttk.Label(top, text="Filter:").pack(side="left", padx=(14, 4))
        self.texture_filter_var = tk.StringVar()
        self.texture_filter_entry = ttk.Entry(top, textvariable=self.texture_filter_var, width=24)
        self.texture_filter_entry.pack(side="left")
        self.texture_filter_entry.bind("<KeyRelease>", lambda _event: self._populate_texture_gallery())

        self.texture_status = tk.StringVar(value="Open a DAT/USD file, then scan it to generate PNG previews.")
        ttk.Label(self.texture_tab, textvariable=self.texture_status, anchor="w").pack(fill="x", pady=(0, 6))

        panes = ttk.Panedwindow(self.texture_tab, orient="horizontal")
        panes.pack(fill="both", expand=True)
        gallery_side = ttk.Frame(panes, padding=(2, 2, 8, 2))
        preview_side = ttk.Frame(panes, padding=(8, 2, 2, 2), width=410)
        panes.add(gallery_side, weight=5)
        panes.add(preview_side, weight=3)

        self.texture_canvas = tk.Canvas(gallery_side, highlightthickness=0, borderwidth=0)
        self.texture_scrollbar = ttk.Scrollbar(
            gallery_side, orient="vertical", command=self.texture_canvas.yview
        )
        self.texture_canvas.configure(yscrollcommand=self.texture_scrollbar.set)
        self.texture_canvas.pack(side="left", fill="both", expand=True)
        self.texture_scrollbar.pack(side="right", fill="y")
        self.texture_gallery_frame = ttk.Frame(self.texture_canvas)
        self.texture_gallery_window = self.texture_canvas.create_window(
            (0, 0), window=self.texture_gallery_frame, anchor="nw"
        )
        self.texture_gallery_frame.bind(
            "<Configure>",
            lambda _event: self.texture_canvas.configure(
                scrollregion=self.texture_canvas.bbox("all")
            ),
        )
        self.texture_canvas.bind(
            "<Configure>",
            lambda event: self.texture_canvas.itemconfigure(
                self.texture_gallery_window, width=event.width
            ),
        )

        ttk.Label(
            preview_side, text="Selected Texture Preview",
            font=("TkDefaultFont", 12, "bold")
        ).pack(anchor="w")
        self.texture_preview_label = ttk.Label(
            preview_side, text="Select a thumbnail to inspect the decoded image.",
            anchor="center", justify="center"
        )
        self.texture_preview_label.pack(fill="both", expand=True, pady=(10, 10))
        self.texture_details = tk.Text(
            preview_side, height=11, wrap="word", borderwidth=0, state="disabled"
        )
        self.texture_details.pack(fill="x", pady=(0, 8))
        self.texture_save_png_button = ttk.Button(
            preview_side, text="Save Selected PNG…",
            command=self.save_selected_texture_png, state="disabled"
        )
        self.texture_save_png_button.pack(fill="x", pady=(0, 4))
        self.texture_import_png_button = ttk.Button(
            preview_side, text="Import PNG into Selected Texture…",
            command=self.import_png_into_selected_texture, state="disabled"
        )
        self.texture_import_png_button.pack(fill="x", pady=4)
        self.texture_save_dat_button = ttk.Button(
            preview_side, text="Save Modified DAT As…",
            command=self.save_modified_dat_as, state="disabled"
        )
        self.texture_save_dat_button.pack(fill="x", pady=4)
        ttk.Label(
            self.texture_tab,
            text="Previews decode the DAT's GX images. Import replaces a texture in the in-memory DAT; "
                 "Save Modified DAT As… writes a separate copy and leaves the source untouched.",
            foreground="#536274",
        ).pack(anchor="w", pady=(7, 0))

    def _clear_texture_gallery(self):
        if not hasattr(self, "texture_gallery_frame"):
            return
        for child in self.texture_gallery_frame.winfo_children():
            child.destroy()
        self.texture_photo_refs.clear()
        self.texture_cards.clear()
        self.selected_texture = None
        self.texture_preview_photo = None
        self.texture_preview_label.configure(image="", text="Select a thumbnail to inspect the decoded image.")
        self.texture_details.configure(state="normal")
        self.texture_details.delete("1.0", "end")
        self.texture_details.configure(state="disabled")
        self.texture_save_png_button.configure(state="disabled")
        self.texture_import_png_button.configure(state="disabled")
        self._update_texture_edit_buttons()

    def _update_texture_edit_buttons(self):
        if not hasattr(self, "texture_import_png_button"):
            return
        self.texture_import_png_button.configure(
            state="normal" if self.dat_model and self.selected_texture else "disabled"
        )
        self.texture_save_dat_button.configure(
            state="normal" if self.dat_modified and self.dat_working_data else "disabled"
        )

    def scan_current_dat_textures(self):
        if not self.dat_model:
            self.texture_status.set("Open a DAT/USD file first.")
            return
        self.texture_scan_button.configure(state="disabled")
        self.texture_status.set("Scanning HSD texture headers and decoding GX images…")
        self.root.update_idletasks()
        try:
            self.texture_scan_report = scan_gx_textures(self.dat_model)
        except (OSError, ValueError, struct.error) as exc:
            self.texture_scan_report = None
            self._clear_texture_gallery()
            self.texture_status.set("Texture scan failed: {}".format(exc))
            self.texture_scan_button.configure(state="normal")
            return
        finally:
            self.texture_scan_button.configure(state="normal")

        count = len(self.texture_scan_report.textures)
        warning_count = len(self.texture_scan_report.warnings)
        status = "{} PNG preview(s) decoded from {}.".format(count, self.dat_model.file_name)
        if warning_count:
            status += " {} candidate/warning message(s); see details when no preview is available.".format(warning_count)
        self.texture_status.set(status)
        self._populate_texture_gallery()
        if count == 0:
            details = "\n".join(self.texture_scan_report.warnings) or "No GX image records were found."
            self.set_text(self.texture_details, details)
            self.texture_preview_label.configure(
                image="", text="No decodable textures found. See scan details below."
            )

    def _populate_texture_gallery(self):
        if not hasattr(self, "texture_gallery_frame"):
            return
        for child in self.texture_gallery_frame.winfo_children():
            child.destroy()
        self.texture_photo_refs.clear()
        self.texture_cards.clear()
        if not self.texture_scan_report:
            return
        query = self.texture_filter_var.get().strip().casefold()
        matches = [
            texture for texture in self.texture_scan_report.textures
            if not query or query in texture.name.casefold()
            or query in texture.image_format.casefold()
            or query in "{}x{}".format(texture.width, texture.height)
        ]
        columns = 3
        for index, texture in enumerate(matches):
            thumb_w, thumb_h, thumb_rgba = resize_rgba_nearest(
                texture.rgba, texture.width, texture.height, 128, 96
            )
            thumb_png = encode_rgba_png(thumb_w, thumb_h, thumb_rgba)
            photo = tk.PhotoImage(data=png_data_uri(thumb_png))
            self.texture_photo_refs.append(photo)
            card = ttk.Frame(self.texture_gallery_frame, relief="ridge", padding=6)
            card.grid(
                row=index // columns, column=index % columns,
                sticky="nsew", padx=5, pady=5
            )
            image_label = ttk.Label(card, image=photo, anchor="center")
            image_label.pack(fill="both", expand=True)
            name_label = ttk.Label(
                card, text=texture.name, anchor="center", justify="center",
                wraplength=140
            )
            name_label.pack(fill="x", pady=(4, 1))
            info_label = ttk.Label(
                card, text="{}×{}  ·  {}".format(texture.width, texture.height, texture.image_format),
                anchor="center"
            )
            info_label.pack(fill="x")
            for widget in (card, image_label, name_label, info_label):
                widget.bind(
                    "<Button-1>",
                    lambda _event, selected=texture: self.select_texture_preview(selected)
                )
                widget.configure(cursor="hand2")
            self.texture_cards.append((card, texture))
        for column in range(columns):
            self.texture_gallery_frame.columnconfigure(column, weight=1, uniform="texture-card")
        if query and not matches:
            ttk.Label(
                self.texture_gallery_frame, text="No textures match the current filter."
            ).grid(row=0, column=0, sticky="w", padx=8, pady=8)

    def select_texture_preview(self, texture: TexturePreview):
        self.selected_texture = texture
        preview_w, preview_h, preview_rgba = resize_rgba_nearest(
            texture.rgba, texture.width, texture.height, 420, 360
        )
        preview_png = encode_rgba_png(preview_w, preview_h, preview_rgba)
        self.texture_preview_photo = tk.PhotoImage(data=png_data_uri(preview_png))
        self.texture_preview_label.configure(image=self.texture_preview_photo, text="")
        palette_line = (
            "Palette: type {} · {:,} colors · data 0x{:X}".format(
                texture.palette_type, texture.palette_color_count, texture.palette_data_offset or 0
            )
            if texture.palette_type is not None else "Palette: none"
        )
        details = [
            texture.name,
            "Dimensions: {} × {} pixels".format(texture.width, texture.height),
            "GX format: {} (type {})".format(texture.image_format, texture.image_type),
            "Texture object: 0x{:X}".format(texture.texture_offset + 0x20),
            "Image header: 0x{:X}".format(texture.image_header_offset + 0x20),
            "Image data: 0x{:X} ({:,} bytes)".format(
                texture.image_data_offset + 0x20, texture.image_data_length
            ),
            palette_line,
        ]
        if texture.palette_header_offset is not None:
            details.insert(5, "Palette header: 0x{:X}".format(texture.palette_header_offset + 0x20))
        details.extend([
            "",
            (
                "This preview reflects in-memory DAT edits. Save Modified DAT As… to keep them; "
                "the original file on disk is still untouched."
                if self.dat_modified else
                "PNG preview is a decoded view of this DAT image payload. The source DAT has not been modified."
            ),
            "Import a PNG with exactly the same dimensions to replace this image.",
            "The image is encoded in the existing GX format and block allocation.",
        ])
        self.set_text(self.texture_details, "\n".join(details))
        self.texture_save_png_button.configure(state="normal")
        self._update_texture_edit_buttons()

    def import_png_into_selected_texture(self):
        if not self.dat_model or not self.dat_working_data or not self.selected_texture:
            return
        texture = self.selected_texture
        source = filedialog.askopenfilename(
            title="Choose PNG for {}".format(texture.name),
            filetypes=[("PNG images", "*.png"), ("All files", "*.*")],
        )
        if not source:
            return
        try:
            png_path = Path(source)
            if png_path.stat().st_size > 64 * 1024 * 1024:
                raise GXTextureError("PNG file is larger than the 64 MiB import limit.")
            png_bytes = png_path.read_bytes()
            updated_data = replace_texture_in_dat(self.dat_working_data, texture, png_bytes)
            updated_model = DatTreeModel(self.dat_model.path, data=updated_data)
        except (OSError, DatFormatError, GXTextureError, ValueError, struct.error) as exc:
            messagebox.showerror("Texture import failed", str(exc), parent=self.root)
            return

        texture_offset = texture.texture_offset
        self._set_dat_model(updated_model, modified=True)
        self.scan_current_dat_textures()
        replacement = next(
            (item for item in (self.texture_scan_report.textures if self.texture_scan_report else ())
             if item.texture_offset == texture_offset),
            None,
        )
        if replacement:
            self.select_texture_preview(replacement)
        self.texture_status.set(
            "Imported {} into {}. Save the modified DAT as a new file.".format(
                png_path.name, self.dat_model.file_name
            )
        )
        self.status.set("Texture imported in memory; the source DAT has not been changed.")
        messagebox.showinfo(
            "Texture imported",
            "{} was encoded as {} ({}×{}).\n\n"
            "Save Modified DAT As… to create a new DAT. You can then use the Melee File Tree's "
            "Import action to stage that DAT into your ISO and Rebuild / Save ISO As…".format(
                texture.name, texture.image_format, texture.width, texture.height
            ),
            parent=self.root,
        )

    def save_modified_dat_as(self):
        if not self.dat_model or not self.dat_working_data or not self.dat_modified:
            return
        source_path = self.dat_model.path
        initial_name = source_path.stem + "-edited" + (source_path.suffix or ".dat")
        destination = filedialog.asksaveasfilename(
            title="Save modified DAT as a new file",
            initialfile=initial_name,
            defaultextension=".dat",
            filetypes=[("DAT files", "*.dat *.usd"), ("All files", "*.*")],
            confirmoverwrite=True,
        )
        if not destination:
            return
        target = Path(destination).expanduser()
        temporary = target.with_name(target.name + ".dtw-tmp")
        try:
            if source_path.exists() and target.resolve() == source_path.resolve():
                raise OSError("Choose a new filename; the original DAT must remain untouched.")
            temporary.write_bytes(self.dat_working_data)
            os.replace(temporary, target)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            messagebox.showerror("Could not save DAT", str(exc), parent=self.root)
            return
        self.texture_status.set("Modified DAT saved: {}".format(target))
        self.status.set("Saved modified DAT copy: {}".format(target))
        messagebox.showinfo(
            "Modified DAT saved",
            "Saved a new DAT copy to:\n{}\n\n"
            "To use it in your ISO, select the original DAT in the Melee File Tree, "
            "click Import, choose this saved file, then use Rebuild / Save ISO As…".format(target),
            parent=self.root,
        )

    def save_selected_texture_png(self):
        if not self.selected_texture:
            return
        texture = self.selected_texture
        safe_name = "".join(
            ch if ch.isalnum() or ch in "-_ ." else "_" for ch in texture.name
        ).strip(" .")
        if not safe_name:
            safe_name = "texture-{:02d}".format(texture.index)
        destination = filedialog.asksaveasfilename(
            title="Save decoded texture preview as PNG",
            initialfile=safe_name + ".png",
            defaultextension=".png",
            filetypes=[("PNG image", "*.png")],
        )
        if not destination:
            return
        try:
            Path(destination).write_bytes(texture.png_data)
        except OSError as exc:
            messagebox.showerror("Could not save PNG", str(exc), parent=self.root)
            return
        self.status.set("Saved PNG preview: {}".format(destination))

    def _build_disc_view(self):
        panes = ttk.Panedwindow(self.disc_tab, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left = ttk.Frame(panes, padding=(5, 6, 4, 4))
        right = ttk.Frame(panes, padding=(12, 12, 12, 6), width=280)
        panes.add(left, weight=5)
        panes.add(right, weight=2)

        shortcuts = ttk.Frame(left)
        shortcuts.pack(fill="x", pady=(0, 5))
        ttk.Label(shortcuts, text="Melee shortcuts:").pack(side="left", padx=(2, 7))
        for label, key in (("System", "system"), ("Characters", "characters"), ("Menus", "menus"), ("Stages", "stages")):
            ttk.Button(shortcuts, text=label, width=11, command=lambda value=key: self.disc_quick_link(value)).pack(side="left", padx=2)

        self.disc_tree = ttk.Treeview(
            left, columns=("description", "size", "offset"), show="tree headings", selectmode="browse"
        )
        self.disc_tree.heading("#0", text="Disc File Tree (FST order)", anchor="center")
        self.disc_tree.heading("description", text="Affects / Description", anchor="center")
        self.disc_tree.heading("size", text="Size", anchor="center")
        self.disc_tree.heading("offset", text="Disc Offset", anchor="center")
        self.disc_tree.column("#0", width=270, minwidth=190, stretch=True)
        self.disc_tree.column("description", width=225, minwidth=150, stretch=False)
        self.disc_tree.column("size", width=90, minwidth=78, stretch=False, anchor="e")
        self.disc_tree.column("offset", width=105, minwidth=95, stretch=False, anchor="e")
        dy = ttk.Scrollbar(left, orient="vertical", command=self.disc_tree.yview)
        dx = ttk.Scrollbar(left, orient="horizontal", command=self.disc_tree.xview)
        self.disc_tree.configure(yscrollcommand=dy.set, xscrollcommand=dx.set)
        self.disc_tree.pack(side="left", fill="both", expand=True)
        dy.pack(side="right", fill="y")
        dx.pack(side="bottom", fill="x")
        self.disc_tree.tag_configure("directory", foreground="#285b83")
        self.disc_tree.tag_configure("changed", foreground="#b35b12")
        self.disc_tree.bind("<<TreeviewOpen>>", self.on_disc_open)
        self.disc_tree.bind("<<TreeviewSelect>>", self.on_disc_select)
        self.disc_tree.bind("<Double-1>", self.on_disc_double_click)

        ttk.Label(right, text="Selected Disc Item", font=("TkDefaultFont", 12, "bold")).pack(anchor="w")
        self.disc_details = tk.Text(right, height=12, wrap="word", borderwidth=0, state="disabled")
        self.disc_details.pack(fill="x", pady=(8, 12))
        self.export_button = ttk.Button(right, text="Export", command=self.export_selected, state="disabled")
        self.import_button = ttk.Button(right, text="Import", command=self.import_replacement, state="disabled")
        self.browse_button = ttk.Button(right, text="Browse Textures", command=self.browse_textures, state="disabled")
        self.analyze_button = ttk.Button(right, text="Analyze Structure", command=self.analyze_structure, state="disabled")
        for button in (self.export_button, self.import_button, self.browse_button, self.analyze_button):
            button.pack(fill="x", pady=4)
        ttk.Separator(right).pack(fill="x", pady=10)
        self.save_copy_button = ttk.Button(right, text="Rebuild / Save ISO As…", command=self.save_patched_iso, state="disabled")
        self.save_copy_button.pack(fill="x", pady=4)
        self.staged_label = ttk.Label(right, text="No staged replacements", wraplength=255, foreground="#536274")
        self.staged_label.pack(anchor="w", pady=(8, 0))
        self.disc_info_label = ttk.Label(right, text="Open a GameCube ISO to browse its Melee files.", wraplength=255, justify="left")
        self.disc_info_label.pack(anchor="w", pady=(18, 0))

    def _build_structure_view(self):
        panes = ttk.Panedwindow(self.sa_tab, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left = ttk.Frame(panes, padding=(4, 6, 4, 4))
        right = ttk.Frame(panes, padding=(6, 6, 4, 4))
        panes.add(left, weight=5)
        panes.add(right, weight=4)
        self.tree = ttk.Treeview(left, columns=("offset",), show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="File Structure", anchor="center")
        self.tree.heading("offset", text="Offset", anchor="center")
        self.tree.column("#0", width=350, minwidth=230, stretch=True)
        self.tree.column("offset", width=112, minwidth=100, stretch=False, anchor="e")
        ybar = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        xbar = ttk.Scrollbar(left, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.tree.tag_configure("table", foreground="#245b88")
        self.tree.tag_configure("cycle", foreground="#a05a14")
        self.tree.bind("<<TreeviewOpen>>", self.on_tree_open)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        detail_tabs = ttk.Notebook(right)
        detail_tabs.pack(fill="both", expand=True)
        props = ttk.Frame(detail_tabs, padding=8)
        raw = ttk.Frame(detail_tabs, padding=8)
        detail_tabs.add(props, text="Properties")
        detail_tabs.add(raw, text="Raw Data")
        self.properties = tk.Text(props, wrap="word", borderwidth=0, padx=4, pady=4, state="disabled")
        py = ttk.Scrollbar(props, orient="vertical", command=self.properties.yview)
        self.properties.configure(yscrollcommand=py.set)
        self.properties.pack(side="left", fill="both", expand=True)
        py.pack(side="right", fill="y")
        self.raw = tk.Text(raw, wrap="none", font=("TkFixedFont", 9), borderwidth=0, state="disabled")
        ry = ttk.Scrollbar(raw, orient="vertical", command=self.raw.yview)
        rx = ttk.Scrollbar(raw, orient="horizontal", command=self.raw.xview)
        self.raw.configure(yscrollcommand=ry.set, xscrollcommand=rx.set)
        self.raw.grid(row=0, column=0, sticky="nsew")
        ry.grid(row=0, column=1, sticky="ns")
        rx.grid(row=1, column=0, sticky="ew")
        raw.rowconfigure(0, weight=1)
        raw.columnconfigure(0, weight=1)
        self.set_text(self.properties, "Open a DAT file to browse its file header, tables, and expandable HSD structures.")
        self.set_text(self.raw, "Select a structure or table to inspect its bytes.")

    @staticmethod
    def set_text(widget: tk.Text, value: str):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    # -------------------------------------------------------------- open files
    def open_iso(self):
        path = filedialog.askopenfilename(
            title="Open Melee / GameCube disc image",
            filetypes=[("GameCube images", "*.iso *.gcm"), ("All files", "*.*")],
        )
        if path:
            self.load_iso(path)

    def open_dat(self):
        path = filedialog.askopenfilename(
            title="Open standalone DAT file",
            filetypes=[("DAT / USD files", "*.dat *.usd *.0at *.1at *.2at *.3at *.4at *.5at *.6at *.7at *.8at *.9at"), ("All files", "*.*")],
        )
        if path:
            self.load_file(path)

    def reload_current(self):
        if self.iso:
            self.load_iso(str(self.iso.path))
        elif self.dat_model:
            self.load_file(str(self.dat_model.path))

    def load_iso(self, path: str):
        try:
            model = GameCubeIso(path)
        except (OSError, GameCubeFormatError, ValueError, struct.error) as exc:
            messagebox.showerror("Unable to open GameCube image", str(exc), parent=self.root)
            self.status.set("Disc open failed")
            return
        self.iso = model
        self.tabs.tab(self.disc_tab, text="Melee File Tree" if model.is_melee else "GameCube File Tree")
        self.staged.clear()
        self.disc_iids.clear()
        self.disc_loaded.clear()
        self.character_groups = {group.code: group for group in build_character_groups(model.entries)}
        self.character_root_iid = None
        self.character_group_iids.clear()
        self.character_group_code_by_iid.clear()
        self.character_file_entries.clear()
        self.character_file_iids.clear()
        self.character_tree_loaded = False
        self.character_group_loaded.clear()
        self.stage_groups = {group.key: group for group in build_stage_groups(model.entries)}
        self.stage_root_iid = None
        self.stage_categories.clear()
        self.stage_category_iids.clear()
        self.stage_category_by_iid.clear()
        self.stage_group_iids.clear()
        self.stage_group_key_by_iid.clear()
        self.stage_file_entries.clear()
        self.stage_file_iids.clear()
        self.stage_tree_loaded = False
        self.stage_category_loaded.clear()
        self.stage_group_loaded.clear()
        for group in self.stage_groups.values():
            self.stage_categories.setdefault(group.category, []).append(group)
        self.selected_disc_entry = None
        self.disc_tree.delete(*self.disc_tree.get_children(""))
        title = "Super Smash Bros. Melee" if model.is_melee else "GameCube Disc"
        root_text = "{} — {} ({})".format(model.game_id, title, model.path.name)
        root_iid = "disc-root"
        self.disc_tree.insert("", "end", iid=root_iid, text=root_text, values=("Disc", "", "0x00000000"), tags=("directory",), open=True)
        self.disc_iids[0] = root_iid
        if model.is_melee and self.character_groups:
            self.character_root_iid = "disc-characters"
            self.disc_tree.insert(
                root_iid, "end", iid=self.character_root_iid, text="Characters",
                values=("Virtual Folder", "", ""), tags=("directory",),
            )
            self.disc_tree.insert(
                self.character_root_iid, "end", iid=self.character_root_iid + "/__pending__",
                text="", values=("", "", ""),
            )
        if model.is_melee and self.stage_groups:
            self.stage_root_iid = "disc-stages"
            self.disc_tree.insert(
                root_iid, "end", iid=self.stage_root_iid, text="Stages",
                values=("Virtual stage folders", "", ""), tags=("directory",),
            )
            self.disc_tree.insert(
                self.stage_root_iid, "end", iid=self.stage_root_iid + "/__pending__",
                text="", values=("", "", ""),
            )
        self._populate_disc_directory(0)
        self.filename.set(model.path.name)
        self.disc_info_label.configure(
            text="Game ID: {}\nFiles: {:,}\nFolders: {:,}\nDisc size: {:,} bytes\nFST: 0x{:X} ({:,} bytes)".format(
                model.game_id, model.file_count, model.directory_count, model.iso_size, model.fst_offset, model.fst_size
            )
        )
        warning = (" — " + model.warnings[0]) if model.warnings else ""
        self.status.set("Opened {} — {} files, {} folders{}".format(model.game_id, model.file_count, model.directory_count, warning))
        self._show_disc_overview()
        self._update_staged_controls()
        self.tabs.select(self.disc_tab)
        self.texture_scan_report = None
        self._clear_texture_gallery()
        self.texture_scan_button.configure(state="disabled")
        self.texture_status.set("Select a DAT/USD file, then use Browse Textures or open this tab and scan.")

    def load_file(self, path: str):
        try:
            model = DatTreeModel(path)
        except (OSError, DatFormatError, ValueError, struct.error) as exc:
            messagebox.showerror("Unable to open DAT", str(exc), parent=self.root)
            self.status.set("DAT open failed")
            return
        self._set_dat_model(model)
        self.tabs.select(self.sa_tab)

    def load_dat_bytes(self, data: bytes, display_name: str, disc_path: str):
        try:
            model = DatTreeModel(Path(disc_path), data=data)
        except (DatFormatError, ValueError, struct.error) as exc:
            messagebox.showerror("Unable to read DAT", "{}\n\nDisc path: {}".format(exc, disc_path), parent=self.root)
            self.status.set("DAT could not be parsed")
            return False
        self._set_dat_model(model)
        self.status.set("Loaded {} from {}".format(display_name, disc_path))
        return True

    def _set_dat_model(self, model: DatTreeModel, modified: bool = False):
        self.dat_model = model
        self.dat_working_data = bytes(model.data)
        if not modified:
            self.dat_original_data = self.dat_working_data
            self.dat_modified = False
        else:
            self.dat_modified = self.dat_original_data is not None and self.dat_working_data != self.dat_original_data
        self.records.clear()
        self.loaded.clear()
        self.tree.delete(*self.tree.get_children(""))
        records = model.root_tree_records()
        header = records[0]
        self.insert_record("", header, offset_text="0")
        for item in records[1:]:
            self.insert_record(header.iid, item)
        self.tree.heading("#0", text=model.file_name)
        self.tree.item(header.iid, open=True)
        for item in records[1:]:
            if item.kind in {"root_table", "reference_table"}:
                self.tree.item(item.iid, open=True)
                self.populate_table(item)
        self._show_file_overview()
        self.texture_heading.configure(text="DAT Texture Tree — {}".format(model.file_name))
        self.texture_scan_report = None
        self._clear_texture_gallery()
        self.texture_scan_button.configure(state="normal")
        self.texture_status.set(
            "{} loaded. Choose Scan DAT / Refresh PNGs to enumerate embedded GX images.".format(model.file_name)
        )
        self._update_texture_edit_buttons()

    # -------------------------------------------------------------- disc tree
    def _entry_iid(self, index: int) -> str:
        return "disc-entry-{}".format(index)

    def _character_group_iid(self, code: str) -> str:
        return "disc-character-{}".format(code)

    def _stage_category_iid(self, category: str) -> str:
        return "disc-stage-category-{}".format(category.lower().replace(" ", "-"))

    def _stage_group_iid(self, key: str) -> str:
        return "disc-stage-group-{}".format(key.replace(":", "-"))

    def _populate_character_tree(self):
        """Create virtual character folders; their entries retain real FST paths."""
        if not self.iso or not self.character_root_iid or self.character_tree_loaded:
            return
        self._remove_disc_pending(self.character_root_iid)
        for group in self.character_groups.values():
            iid = self._character_group_iid(group.code)
            self.character_group_iids[group.code] = iid
            self.character_group_code_by_iid[iid] = group.code
            self.disc_tree.insert(
                self.character_root_iid, "end", iid=iid, text=group.name,
                values=("Character", "{} files".format(len(group.entries)), ""),
                tags=("directory",),
            )
            if group.entries:
                self.disc_tree.insert(iid, "end", iid=iid + "/__pending__", text="", values=("", "", ""))
        self.character_tree_loaded = True

    def _populate_stage_tree(self):
        """Create presentation-only stage categories and expandable subfolders."""
        if not self.iso or not self.stage_root_iid or self.stage_tree_loaded:
            return
        self._remove_disc_pending(self.stage_root_iid)
        preferred_order = ("Stages", "Target Tests", "1P Mode", "Other Stage Files")
        categories = sorted(
            self.stage_categories,
            key=lambda value: (preferred_order.index(value) if value in preferred_order else 99, value.casefold()),
        )
        for category in categories:
            groups = self.stage_categories[category]
            iid = self._stage_category_iid(category)
            self.stage_category_iids[category] = iid
            self.stage_category_by_iid[iid] = category
            self.disc_tree.insert(
                self.stage_root_iid, "end", iid=iid, text=category,
                values=("Stage category", "{} groups".format(len(groups)), ""),
                tags=("directory",),
            )
            if groups:
                self.disc_tree.insert(iid, "end", iid=iid + "/__pending__", text="", values=("", "", ""))
        self.stage_tree_loaded = True

    def _populate_stage_category(self, category: str):
        if not self.iso or category in self.stage_category_loaded:
            return
        parent_iid = self.stage_category_iids.get(category)
        if not parent_iid:
            return
        self._remove_disc_pending(parent_iid)
        for group in self.stage_categories.get(category, []):
            iid = self._stage_group_iid(group.key)
            self.stage_group_iids[group.key] = iid
            self.stage_group_key_by_iid[iid] = group.key
            self.disc_tree.insert(
                parent_iid, "end", iid=iid, text=group.name,
                values=("Stage group", "{} files".format(len(group.entries)), ""),
                tags=("directory",),
            )
            if group.entries:
                self.disc_tree.insert(iid, "end", iid=iid + "/__pending__", text="", values=("", "", ""))
        self.stage_category_loaded.add(category)

    def _populate_stage_group(self, key: str):
        if not self.iso or key in self.stage_group_loaded:
            return
        group = self.stage_groups.get(key)
        parent_iid = self.stage_group_iids.get(key)
        if not group or not parent_iid:
            return
        self._remove_disc_pending(parent_iid)
        for entry in group.entries:
            iid = "disc-stage-file-{}".format(entry.index)
            self.stage_file_entries[iid] = entry
            self.stage_file_iids[entry.index] = iid
            description = disc_file_description(entry.name)
            tags = ("changed",) if entry.index in self.staged else ()
            self.disc_tree.insert(
                parent_iid, "end", iid=iid, text=entry.name,
                values=(description or "Stage file", self._format_size(self._effective_size(entry)), "0x{:08X}".format(entry.offset or 0)),
                tags=tags,
            )
        self.stage_group_loaded.add(key)

    def _populate_character_group(self, code: str):
        """Add character-file aliases that resolve to their original FST entries."""
        if not self.iso or code in self.character_group_loaded:
            return
        group = self.character_groups.get(code)
        parent_iid = self.character_group_iids.get(code)
        if not group or not parent_iid:
            return
        self._remove_disc_pending(parent_iid)
        for entry in group.entries:
            iid = "disc-character-file-{}".format(entry.index)
            self.character_file_entries[iid] = entry
            self.character_file_iids[entry.index] = iid
            tags = ("changed",) if entry.index in self.staged else ()
            description = disc_file_description(entry.name)
            self.disc_tree.insert(
                parent_iid, "end", iid=iid, text=entry.name,
                values=(description or "Character file", self._format_size(self._effective_size(entry)), "0x{:08X}".format(entry.offset or 0)),
                tags=tags,
            )
        self.character_group_loaded.add(code)

    def _populate_disc_directory(self, directory_index: int):
        if not self.iso or directory_index in self.disc_loaded:
            return
        parent_iid = self.disc_iids.get(directory_index)
        if not parent_iid:
            return
        for child in self.iso.children_of(directory_index):
            iid = self._entry_iid(child.index)
            self.disc_iids[child.index] = iid
            if child.is_directory:
                self.disc_tree.insert(parent_iid, "end", iid=iid, text=child.name, values=("Folder", "", ""), tags=("directory",))
                if self.iso.children_of(child.index):
                    self.disc_tree.insert(iid, "end", iid=iid + "/__pending__", text="", values=("", "", ""))
            else:
                tags = ("changed",) if child.index in self.staged else ()
                self.disc_tree.insert(
                    parent_iid, "end", iid=iid, text=child.name,
                    values=(disc_file_description(child.name) or "File", self._format_size(self._effective_size(child)), "0x{:08X}".format(child.offset or 0)),
                    tags=tags,
                )
        self.disc_loaded.add(directory_index)

    def _format_size(self, size: int | None) -> str:
        if size is None:
            return ""
        return "{:,} B".format(size)

    def _effective_size(self, entry: FstEntry) -> int:
        staged = self.staged.get(entry.index)
        if staged:
            try:
                return Path(staged).stat().st_size
            except OSError:
                pass
        return entry.size or 0

    def on_disc_open(self, _event):
        if not self.iso:
            return
        iid = self.disc_tree.focus()
        if iid == self.character_root_iid:
            self._remove_disc_pending(iid)
            self._populate_character_tree()
            return
        if iid == self.stage_root_iid:
            self._remove_disc_pending(iid)
            self._populate_stage_tree()
            return
        stage_category = self.stage_category_by_iid.get(iid)
        if stage_category:
            self._remove_disc_pending(iid)
            self._populate_stage_category(stage_category)
            return
        stage_key = self.stage_group_key_by_iid.get(iid)
        if stage_key:
            self._remove_disc_pending(iid)
            self._populate_stage_group(stage_key)
            return
        character_code = self.character_group_code_by_iid.get(iid)
        if character_code:
            self._remove_disc_pending(iid)
            self._populate_character_group(character_code)
            return
        if iid == "disc-root":
            self._remove_disc_pending(iid)
            self._populate_disc_directory(0)
            return
        entry = self._entry_from_iid(iid)
        if entry and entry.is_directory:
            self._remove_disc_pending(iid)
            self._populate_disc_directory(entry.index)

    def _remove_disc_pending(self, iid: str):
        for child in self.disc_tree.get_children(iid):
            if child.endswith("/__pending__"):
                self.disc_tree.delete(child)

    def _entry_from_iid(self, iid: str) -> FstEntry | None:
        virtual_entry = self.character_file_entries.get(iid)
        if virtual_entry is not None:
            return virtual_entry
        stage_entry = self.stage_file_entries.get(iid)
        if stage_entry is not None:
            return stage_entry
        if not self.iso or not iid.startswith("disc-entry-"):
            return None
        try:
            return self.iso.get_entry(int(iid.rsplit("-", 1)[1]))
        except (ValueError, KeyError):
            return None

    def on_disc_select(self, _event):
        if not self.iso:
            return
        selection = self.disc_tree.selection()
        if not selection:
            self.selected_disc_entry = None
            return
        iid = selection[0]
        if iid == self.character_root_iid:
            self.selected_disc_entry = None
            file_count = sum(len(group.entries) for group in self.character_groups.values())
            self.set_text(
                self.disc_details,
                "Characters\nType: Virtual folder\nCharacter folders: {}\nCharacter files: {}\n\n"
                "Files are grouped by their Melee fighter prefix for easier browsing. "
                "These folders are only a viewing aid; each file keeps its original disc path.".format(
                    len(self.character_groups), file_count
                ),
            )
            self._set_disc_buttons(False, False, False, False)
            self.status.set("Characters: {} groups, {} files".format(len(self.character_groups), file_count))
            return
        if iid == self.stage_root_iid:
            self.selected_disc_entry = None
            count = sum(len(group.entries) for group in self.stage_groups.values())
            self.set_text(
                self.disc_details,
                "Stages\nType: Virtual folder\nStage groups: {}\nStage files: {}\n\n"
                "Stages are grouped by their known Melee stage names. These folders are only a viewing aid; "
                "each file retains its original disc path.".format(len(self.stage_groups), count),
            )
            self._set_disc_buttons(False, False, False, False)
            self.status.set("Stages: {} groups, {} files".format(len(self.stage_groups), count))
            return
        stage_category = self.stage_category_by_iid.get(iid)
        if stage_category:
            self.selected_disc_entry = None
            groups = self.stage_categories.get(stage_category, [])
            count = sum(len(group.entries) for group in groups)
            self.set_text(
                self.disc_details,
                "{}\nType: Stage category\nStage groups: {}\nFiles: {}\n\n"
                "Expand a stage folder to select individual DAT/USD files.".format(stage_category, len(groups), count),
            )
            self._set_disc_buttons(False, False, False, False)
            self.status.set("{}: {} groups, {} files".format(stage_category, len(groups), count))
            return
        stage_key = self.stage_group_key_by_iid.get(iid)
        if stage_key:
            group = self.stage_groups[stage_key]
            self.selected_disc_entry = None
            lines = [
                group.name,
                "Type: Stage group (virtual folder)",
                "Files: {}".format(len(group.entries)),
                "",
                "Individual files keep their original disc paths:",
            ]
            lines.extend("  {} — {}".format(entry.path, disc_file_description(entry.name) or "Stage file") for entry in group.entries)
            self.set_text(self.disc_details, "\n".join(lines))
            self._set_disc_buttons(False, False, False, False)
            self.status.set("{}: {} stage files".format(group.name, len(group.entries)))
            return
        character_code = self.character_group_code_by_iid.get(iid)
        if character_code:
            group = self.character_groups[character_code]
            self.selected_disc_entry = None
            lines = [
                group.name,
                "Type: Character group (virtual folder)",
                "Files: {}".format(len(group.entries)),
                "",
                "Select an individual file below to export or stage a replacement.",
                "Original disc paths are preserved:",
            ]
            lines.extend("  {}".format(entry.path) for entry in group.entries)
            self.set_text(self.disc_details, "\n".join(lines))
            self._set_disc_buttons(False, False, False, False)
            self.status.set("{}: {} character files".format(group.name, len(group.entries)))
            return
        entry = self._entry_from_iid(iid)
        self.selected_disc_entry = entry
        if entry is None:
            self._show_disc_overview()
            self._set_disc_buttons(False, False, False, False)
            return
        staged_path = self.staged.get(entry.index)
        lines = [
            entry.name,
            "Type: {}".format("Folder" if entry.is_directory else "File"),
            "Disc path: {}".format(entry.path),
        ]
        if entry.is_file:
            description = disc_file_description(entry.name)
            if description:
                lines.append("Affects / Description: {}".format(description))
        if entry.is_file:
            lines.extend([
                "Disc offset: 0x{:08X}".format(entry.offset or 0),
                "Original size: {:,} bytes".format(entry.size or 0),
            ])
            if staged_path:
                lines.extend([
                    "Replacement: {}".format(Path(staged_path).name),
                    "Staged size: {:,} bytes".format(Path(staged_path).stat().st_size),
                    "Status: replacement staged (source ISO unchanged)",
                ])
        else:
            lines.append("Children: {}".format(len(self.iso.children_of(entry.index))))
        self.set_text(self.disc_details, "\n".join(lines))
        is_file = entry.is_file
        is_dat = is_file and entry.name.casefold().endswith((".dat", ".usd", ".0at", ".1at", ".2at", ".3at", ".4at", ".5at", ".6at", ".7at", ".8at", ".9at"))
        self._set_disc_buttons(is_file, is_file, bool(is_dat), bool(is_dat))
        self.status.set("Selected {}".format(entry.path))

    def _set_disc_buttons(self, export: bool, import_file: bool, browse: bool, analyze: bool):
        self.export_button.configure(state="normal" if export else "disabled")
        self.import_button.configure(state="normal" if import_file else "disabled")
        self.browse_button.configure(state="normal" if browse else "disabled")
        self.analyze_button.configure(state="normal" if analyze else "disabled")

    def _show_disc_overview(self):
        if not self.iso:
            self.set_text(self.disc_details, "Open a Melee/GameCube ISO to browse the disc's folder and file structure.")
            return
        self.set_text(
            self.disc_details,
            "{}\n{} files and {} folders\n\nSelect a file or folder to export it. "
            "Select a DAT/USD file to import a replacement, browse its DAT data, or analyze its structure.\n\n"
            "Import changes are staged separately. The original ISO is never modified.".format(
                self.iso.game_id, self.iso.file_count, self.iso.directory_count
            )
        )

    def on_disc_double_click(self, event):
        if not self.iso:
            return
        iid = self.disc_tree.identify_row(event.y)
        if not iid:
            return
        entry = self._entry_from_iid(iid)
        if entry and entry.is_file and entry.name.casefold().endswith((".dat", ".usd")):
            self.browse_textures()

    # ------------------------------------------------------- Melee quick links
    def disc_quick_link(self, category: str):
        if not self.iso:
            messagebox.showinfo("Open a Melee ISO", "Open a GameCube ISO first.", parent=self.root)
            return
        if category == "stages":
            if not self.stage_root_iid:
                messagebox.showinfo("No stage files", "No recognized Melee stage files were found in this image.", parent=self.root)
                return
            self._populate_stage_tree()
            self.disc_tree.item(self.stage_root_iid, open=True)
            self.disc_tree.selection_set(self.stage_root_iid)
            self.disc_tree.focus(self.stage_root_iid)
            self.disc_tree.see(self.stage_root_iid)
            self.on_disc_select(None)
            self.status.set(
                "Stages shortcut: {} stage groups, {} files".format(
                    len(self.stage_groups), sum(len(group.entries) for group in self.stage_groups.values())
                )
            )
            return
        if category == "characters":
            if not self.character_root_iid:
                messagebox.showinfo("No character files", "No recognized Melee character files were found in this image.", parent=self.root)
                return
            self._populate_character_tree()
            self.disc_tree.item(self.character_root_iid, open=True)
            self.disc_tree.selection_set(self.character_root_iid)
            self.disc_tree.focus(self.character_root_iid)
            self.disc_tree.see(self.character_root_iid)
            self.on_disc_select(None)
            self.status.set(
                "Characters shortcut: {} fighter folders, {} files".format(
                    len(self.character_groups),
                    sum(len(group.entries) for group in self.character_groups.values()),
                )
            )
            return

        def matches(entry: FstEntry) -> bool:
            if not entry.is_file:
                return False
            name = entry.name.casefold()
            path = entry.path.casefold()
            if category == "system":
                return name in {"boot.bin", "bi2.bin", "apploader.img", "apploader.ldr", "start.dol", "game.toc", "iso.hdr"} or "/sys/" in path
            if category == "menus":
                return name.startswith(("mn", "sdmenu", "menu")) and name.endswith((".dat", ".usd"))
            if category == "stages":
                return name.startswith(("gr", "grp")) and name.endswith((".dat", ".usd"))
            return False
        candidates = [entry for entry in self.iso.entries if matches(entry)]
        if not candidates:
            messagebox.showinfo("No matching Melee files", "No {} files were found in this image.".format(category), parent=self.root)
            return
        self._reveal_entry(candidates[0])
        self.status.set("{} shortcut: {} matching files".format(category.title(), len(candidates)))

    def _reveal_entry(self, entry: FstEntry):
        if not self.iso:
            return
        chain = []
        parent = entry.parent_index
        while parent > 0:
            chain.append(parent)
            parent = self.iso.get_entry(parent).parent_index
        self._populate_disc_directory(0)
        parent_iid = "disc-root"
        for directory_index in reversed(chain):
            iid = self._entry_iid(directory_index)
            self.disc_tree.item(parent_iid, open=True)
            self._remove_disc_pending(parent_iid)
            self._populate_disc_directory(0 if parent_iid == "disc-root" else int(parent_iid.rsplit("-", 1)[1]))
            if not self.disc_tree.exists(iid):
                return
            self.disc_tree.item(iid, open=True)
            self._remove_disc_pending(iid)
            self._populate_disc_directory(directory_index)
            parent_iid = iid
        target_iid = self._entry_iid(entry.index)
        if self.disc_tree.exists(target_iid):
            self.disc_tree.selection_set(target_iid)
            self.disc_tree.focus(target_iid)
            self.disc_tree.see(target_iid)

    def focus_search(self):
        self.search_entry.focus_set()
        self.search_entry.select_range(0, "end")

    def search_disc_next(self):
        if not self.iso:
            return
        query = self.query.get().strip()
        if not query:
            return
        matches = self.iso.find(query)
        if not matches:
            self.status.set("No disc path matches '{}'".format(query))
            return
        self.search_hits = [entry.index for entry in matches]
        self.search_index = (self.search_index + 1) % len(self.search_hits)
        self._reveal_entry(self.iso.get_entry(self.search_hits[self.search_index]))
        self.status.set("Disc search {}/{}: {}".format(self.search_index + 1, len(matches), matches[self.search_index].path))

    # --------------------------------------------------------- import / export
    def export_selected(self):
        if not self.iso or not self.selected_disc_entry:
            return
        entry = self.selected_disc_entry
        try:
            if entry.is_file:
                destination = filedialog.asksaveasfilename(
                    title="Export selected disc file",
                    initialfile=entry.name,
                    defaultextension=Path(entry.name).suffix,
                    filetypes=[("Same file type", "*" + Path(entry.name).suffix), ("All files", "*.*")],
                )
                if not destination:
                    return
                data = self.iso.read_file(entry.index, self.staged)
                Path(destination).write_bytes(data)
                self.status.set("Exported {} ({:,} bytes)".format(entry.path, len(data)))
            else:
                directory = filedialog.askdirectory(title="Export selected disc folder")
                if not directory:
                    return
                prefix = entry.path + "/"
                exported = 0
                for child in self.iso.entries:
                    if not child.is_file or not child.path.startswith(prefix):
                        continue
                    relative = child.path[len(prefix):]
                    target = Path(directory).joinpath(*relative.split("/"))
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(self.iso.read_file(child.index, self.staged))
                    exported += 1
                self.status.set("Exported {} files from {}".format(exported, entry.path))
        except (OSError, ValueError) as exc:
            messagebox.showerror("Export failed", str(exc), parent=self.root)

    def import_replacement(self):
        if not self.iso or not self.selected_disc_entry or not self.selected_disc_entry.is_file:
            return
        entry = self.selected_disc_entry
        source = filedialog.askopenfilename(
            title="Choose a replacement for {}".format(entry.name),
            filetypes=[
                ("Matching file type", "*" + Path(entry.name).suffix),
                ("All files", "*.*"),
            ],
        )
        if not source:
            return
        try:
            staged_info = self.iso.stage_replacement_for_rebuild(entry.index, source)
        except (OSError, ReplacementError) as exc:
            messagebox.showerror("Cannot stage replacement", str(exc), parent=self.root)
            return
        self.staged[entry.index] = str(Path(source).resolve())
        row_iids = (
            self._entry_iid(entry.index),
            self.character_file_iids.get(entry.index),
            self.stage_file_iids.get(entry.index),
        )
        for iid in row_iids:
            if iid and self.disc_tree.exists(iid):
                self.disc_tree.item(iid, tags=("changed",), values=(
                    "File", self._format_size(int(staged_info["new_size"])), "0x{:08X}".format(entry.offset or 0)
                ))
        self._update_staged_controls()
        self.on_disc_select(None)
        self.status.set("Replacement staged for {} — source ISO not changed".format(entry.path))
        messagebox.showinfo(
            "Replacement staged",
            "{}\n\nOriginal size: {:,} bytes\nReplacement size: {:,} bytes\nCurrent free range: {}\n\n"
            "Use Rebuild / Save ISO As… to create a verified copy. All files will be relocated and repacked; "
            "the source ISO will remain untouched.".format(
                entry.path, int(staged_info["old_size"]), int(staged_info["new_size"]),
                (("{:,} bytes".format(int(staged_info["capacity"]))) if staged_info["capacity"] is not None else "not suitable for in-place replacement")
            ),
            parent=self.root,
        )

    def _update_staged_controls(self):
        state = "normal" if self.iso and self.staged else "disabled"
        self.save_copy_button.configure(state=state)
        self.file_menu.entryconfigure(4, state=state)
        self.staged_label.configure(
            text="{} staged replacement(s)".format(len(self.staged)) if self.staged else "No staged replacements"
        )

    def save_patched_iso(self):
        if not self.iso or not self.staged:
            return
        original = self.iso.path
        stem = original.stem
        ext = original.suffix or ".iso"
        destination = filedialog.asksaveasfilename(
            title="Rebuild GameCube ISO as a new copy",
            initialdir=str(original.parent),
            initialfile=stem + "-rebuilt" + ext,
            defaultextension=ext,
            filetypes=[("GameCube images", "*.iso *.gcm"), ("All files", "*.*")],
        )
        if not destination:
            return
        target = Path(destination).expanduser().resolve()
        overwrite = target.exists()
        if overwrite and not messagebox.askyesno(
            "Replace existing output?",
            "The output file already exists. Replace it?\n\n{}".format(target),
            parent=self.root,
        ):
            return
        try:
            result = self.iso.rebuild_patched_copy(target, self.staged, overwrite=overwrite)
        except (OSError, ReplacementError, GameCubeFormatError, ValueError) as exc:
            messagebox.showerror("Could not rebuild ISO", str(exc), parent=self.root)
            return
        messagebox.showinfo(
            "Rebuilt ISO saved and verified",
            "Created: {}\nGame ID: {}\nSize: {:,} bytes\nFST offset: 0x{:X}\nFiles replaced: {}\n\n"
            "All disc files were repacked and verified. The original ISO was not modified.".format(
                result["destination"], result["game_id"], result["size"], result["fst_offset"], len(result["replacements"])
            ),
            parent=self.root,
        )
        self.load_iso(str(target))

    # --------------------------------------------------------------- DAT loads
    def _selected_dat_bytes(self) -> tuple[bytes, str, str] | None:
        if not self.iso or not self.selected_disc_entry or not self.selected_disc_entry.is_file:
            return None
        entry = self.selected_disc_entry
        try:
            data = self.iso.read_file(entry.index, self.staged)
        except OSError as exc:
            messagebox.showerror("Unable to read disc file", str(exc), parent=self.root)
            return None
        return data, entry.name, entry.path

    def browse_textures(self):
        selected = self._selected_dat_bytes()
        if not selected:
            return
        data, name, disc_path = selected
        if not self.load_dat_bytes(data, name, disc_path):
            return
        self.scan_current_dat_textures()
        self.tabs.select(self.texture_tab)
        self.status.set("DAT loaded from disc; GX texture PNG previews are ready.")

    def analyze_structure(self):
        selected = self._selected_dat_bytes()
        if not selected:
            return
        data, name, disc_path = selected
        if not self.load_dat_bytes(data, name, disc_path):
            return
        self.tabs.select(self.sa_tab)

    # -------------------------------------------------------- structure browser
    def insert_record(self, parent: str, record: TreeRecord, offset_text: str | None = None, cycle: bool = False):
        assert self.dat_model
        if offset_text is None:
            offset_text = "" if record.offset is None else "0x{:X}".format(self.dat_model.absolute_offset(record.offset))
        tags = ("cycle",) if cycle else (("table",) if record.kind in {"root_table", "reference_table", "relocation_table", "string_table"} else ())
        self.tree.insert(parent, "end", iid=record.iid, text=record.text, values=(offset_text,), tags=tags)
        self.records[record.iid] = record
        if record.kind == "structure" and not cycle and self.dat_model.direct_children(record.offset or 0, record.type_hint):
            self.tree.insert(record.iid, "end", iid=record.iid + "/__pending__", text="", values=("",))

    def on_tree_open(self, _event):
        if not self.dat_model:
            return
        iid = self.tree.focus()
        if not iid or iid in self.loaded:
            return
        record = self.records.get(iid)
        if not record:
            return
        if record.kind in {"root_table", "reference_table"}:
            self.populate_table(record)
        elif record.kind == "structure":
            self.populate_structure(record)

    def remove_pending(self, iid: str):
        for child in self.tree.get_children(iid):
            if child.endswith("/__pending__"):
                self.tree.delete(child)

    def populate_table(self, record: TreeRecord):
        assert self.dat_model
        self.remove_pending(record.iid)
        for child in self.dat_model.table_children(record.kind):
            self.insert_record(record.iid, child)
        self.loaded.add(record.iid)

    def populate_structure(self, record: TreeRecord):
        assert self.dat_model and record.offset is not None
        self.remove_pending(record.iid)
        children = self.dat_model.children_with_siblings(record.offset, record.type_hint, record.ancestor_offsets[:-1])
        seen: set[int] = set()
        counts: dict[str, int] = {}
        for offset, type_hint, _label, is_cycle in children:
            if offset in seen:
                continue
            seen.add(offset)
            key = type_hint or "Structure"
            sibling_index = counts.get(key, 0)
            counts[key] = sibling_index + 1
            label = self.dat_model._known_root_labels.get(offset)
            title = self.dat_model.structure_title(offset, type_hint, label, sibling_index)
            iid = record.iid + "/" + str(offset)
            child = TreeRecord("structure", title, iid, offset, type_hint, label, record.ancestor_offsets + (offset,))
            self.insert_record(record.iid, child, cycle=is_cycle)
        self.loaded.add(record.iid)

    def on_tree_select(self, _event):
        if not self.dat_model:
            return
        selection = self.tree.selection()
        if not selection:
            return
        record = self.records.get(selection[0])
        if not record:
            return
        if record.kind == "file_header":
            self._show_file_overview()
        elif record.kind == "structure":
            self.show_structure(record)
        elif record.kind == "relocation_table":
            self.show_table("Relocation Table", self.dat_model.rt_start, self.dat_model.rt_count * 4,
                            "{} 32-bit pointer-location entries".format(self.dat_model.rt_count))
        elif record.kind == "root_table":
            self.show_table("Root Nodes Table", self.dat_model.rt_end, self.dat_model.root_count * 8,
                            "{} root node entries".format(self.dat_model.root_count))
        elif record.kind == "reference_table":
            self.show_table("Reference Nodes Table", self.dat_model.root_nodes_end, self.dat_model.ref_count * 8,
                            "{} reference node entries".format(self.dat_model.ref_count))
        elif record.kind == "string_table":
            size = len(self.dat_model.body) - self.dat_model.string_table_start
            self.show_table("String Table", self.dat_model.string_table_start, size,
                            "{} root/reference labels; {} bytes".format(len(self.dat_model.root_nodes) + len(self.dat_model.reference_nodes), size))

    def _show_file_overview(self):
        if not self.dat_model:
            return
        d = self.dat_model.describe()
        lines = [
            d["file"], "", d["path"], "",
            "File size: {:,} bytes".format(d["size"]),
            "SHA-256: {}".format(d["sha256"]),
            "HSD magic: {}".format(d["magic"]),
            "Relocation entries: {}".format(d["relocations"]),
            "Root nodes: {} ({} tree roots)".format(d["root_nodes"], d["root_structures"]),
            "Reference nodes: {}".format(d["reference_nodes"]),
            "Data section: {:,} bytes".format(d["data_size"]),
            "Relocation table: 0x{:X} – 0x{:X}".format(d["rt_start"], d["rt_end"]),
            "String table starts: 0x{:X}".format(d["string_table_start"]),
            "", "Read-only preview: texture decode, import/export, and rebuilding are not enabled yet."
        ]
        self.set_text(self.properties, "\n".join(lines))
        self.set_text(self.raw, "Select a structure or table to inspect its bytes.")

    def show_table(self, title: str, offset: int, length: int, description: str):
        assert self.dat_model
        text = "{}\n\nOffset in data section: 0x{:X}\nAbsolute file offset: 0x{:X}\nLength: {:,} bytes\n\n{}".format(
            title, offset, self.dat_model.absolute_offset(offset), length, description)
        self.set_text(self.properties, text)
        self.show_raw(offset, min(length, 0x300))

    def show_structure(self, record: TreeRecord):
        assert self.dat_model and record.offset is not None
        offset = record.offset
        length = self.dat_model.structure_length(offset, record.type_hint)
        pointers = self.dat_model.record_pointer_details(offset, record.type_hint)
        lines = [
            record.text,
            "Type: {}".format(record.type_hint or "Unidentified HSD structure"),
            "Data-relative offset: 0x{:X}".format(offset),
            "Absolute file offset: 0x{:X}".format(self.dat_model.absolute_offset(offset)),
            "Inferred span: 0x{:X} ({} bytes)".format(length, length),
            "Pointer fields in span: {}".format(len(pointers)),
        ]
        if record.label:
            lines.append("Root/reference label: {}".format(record.label))
        lines.extend(["", "Pointers:"])
        if pointers:
            for item in pointers:
                target = "NULL" if not item["target"] else "0x{:X} (file 0x{:X})".format(item["target"], item["target_file_offset"])
                lines.append("  +0x{:02X}  {:30s} -> {}".format(item["relative_offset"], item["field"], target))
        else:
            lines.append("  No relocation-table pointers found in this structure span.")
        lines.extend(["", "Generic pointer view only; full DTW class validation remains in progress."])
        self.set_text(self.properties, "\n".join(lines))
        self.show_raw(offset, min(max(length, 0x40), 0x180))

    def show_raw(self, offset: int, length: int):
        assert self.dat_model
        data = self.dat_model.read_bytes(offset, length)
        rows = []
        for start in range(0, len(data), 16):
            chunk = data[start:start + 16]
            hex_part = " ".join("{:02X}".format(byte) for byte in chunk)
            ascii_part = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
            rows.append("{:08X}  {:47s}  {}".format(offset + start, hex_part, ascii_part))
        self.set_text(self.raw, "\n".join(rows) if rows else "No data available.")

    def show_about(self):
        messagebox.showinfo(
            "About",
            "DAT Texture Wizard — Linux Preview\n\n"
            "Melee-oriented GameCube file browser with safe file export and staged replacement.\n"
            "DAT navigation is read-only; texture decoding and full ISO relocation are still in development.",
            parent=self.root,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DAT Texture Wizard native Linux GUI preview")
    parser.add_argument("disc_or_dat", nargs="?", help="Optional ISO/GCM/DAT file to open at startup")
    parser.add_argument(
        "--appimage-smoke-test",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)
    if args.appimage_smoke_test:
        # Used by the AppImage CI job under Xvfb to verify bundled Tcl/Tk loads.
        root = tk.Tk()
        root.withdraw()
        root.update_idletasks()
        tcl_version = root.tk.call("info", "patchlevel")
        tk_version = root.tk.call("package", "provide", "Tk")
        root.destroy()
        print("AppImage GUI smoke test passed (Tcl {}, Tk {}).".format(tcl_version, tk_version))
        return 0
    root = tk.Tk()
    DatTextureWizardPreview(root, args.disc_or_dat)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
