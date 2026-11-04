#!/usr/bin/env python3
"""Native, read-only Tk GUI preview for DAT Texture Wizard navigation."""
from __future__ import annotations

import argparse
import struct
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from dtw_dat_probe import DatFormatError
from dtw_dat_tree import DatTreeModel, TreeRecord


class DatTextureWizardPreview:
    def __init__(self, root: tk.Tk, initial_file: str | None = None):
        self.root = root
        self.model: DatTreeModel | None = None
        self.records: dict[str, TreeRecord] = {}
        self.loaded: set[str] = set()
        self.root.title("DAT Texture Wizard — Linux Preview")
        self.root.geometry("1200x760")
        self.root.minsize(900, 560)
        self._build_menu()
        self._build_toolbar()
        self._build_tabs()
        self.status = tk.StringVar(value="Ready — open a DAT file")
        ttk.Separator(root).pack(fill="x")
        ttk.Label(root, textvariable=self.status, anchor="w", padding=(8, 4)).pack(fill="x")
        root.bind("<Control-o>", lambda _e: self.open_file())
        root.bind("<Control-f>", lambda _e: self.search_entry.focus_set())
        root.bind("<F5>", lambda _e: self.reload_file())
        if initial_file:
            root.after(120, lambda: self.load_file(initial_file))

    def _build_menu(self):
        menu = tk.Menu(self.root)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Open DAT…", accelerator="Ctrl+O", command=self.open_file)
        file_menu.add_command(label="Reload", accelerator="F5", command=self.reload_file)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.destroy)
        menu.add_cascade(label="File", menu=file_menu)
        tools_menu = tk.Menu(menu, tearoff=False)
        tools_menu.add_command(label="Find Structure…", accelerator="Ctrl+F", command=self.focus_search)
        menu.add_cascade(label="Tools", menu=tools_menu)
        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="About", command=self.show_about)
        menu.add_cascade(label="Help", menu=help_menu)
        self.root.configure(menu=menu)

    def _build_toolbar(self):
        bar = ttk.Frame(self.root, padding=(10, 8))
        bar.pack(fill="x")
        ttk.Button(bar, text="Open DAT", command=self.open_file).pack(side="left")
        ttk.Button(bar, text="Reload", command=self.reload_file).pack(side="left", padx=(6, 14))
        ttk.Label(bar, text="Find:").pack(side="left")
        self.query = tk.StringVar()
        self.search_entry = ttk.Entry(bar, textvariable=self.query, width=28)
        self.search_entry.pack(side="left", padx=6)
        self.search_entry.bind("<Return>", lambda _e: self.search_next())
        ttk.Button(bar, text="Find next", command=self.search_next).pack(side="left")
        self.filename = tk.StringVar(value="No DAT loaded")
        ttk.Label(bar, textvariable=self.filename, anchor="e").pack(side="right", fill="x", expand=True, padx=12)

    def _build_tabs(self):
        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.sa_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.sa_tab, text="Structural Analysis")
        self._build_structure_view()
        self.texture_tab = ttk.Frame(self.tabs, padding=24)
        self.tabs.add(self.texture_tab, text="DAT Texture Tree")
        ttk.Label(self.texture_tab, text="DAT Texture Tree", font=("TkDefaultFont", 14, "bold")).pack(anchor="w")
        ttk.Label(
            self.texture_tab,
            text=("This tab is reserved for the expandable texture/model hierarchy, texture thumbnails, "
                  "and import/export actions. It will be connected after the HSD decoder and GX texture "
                  "reader are ported."),
            wraplength=760, justify="left"
        ).pack(anchor="w", pady=(8, 0))
        ttk.Label(self.texture_tab, text="Current milestone: read-only structure navigation.", foreground="#526579").pack(anchor="w", pady=(14, 0))

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

    def open_file(self):
        path = filedialog.askopenfilename(
            title="Open DAT file",
            filetypes=[("DAT / USD files", "*.dat *.usd *.0at *.1at *.2at *.3at *.4at *.5at *.6at *.7at *.8at *.9at"), ("All files", "*.*")],
        )
        if path:
            self.load_file(path)

    def reload_file(self):
        if self.model:
            self.load_file(str(self.model.path))

    def load_file(self, path: str):
        try:
            model = DatTreeModel(path)
        except (OSError, DatFormatError, ValueError, struct.error) as exc:
            messagebox.showerror("Unable to open DAT", str(exc), parent=self.root)
            self.status.set("Open failed")
            return
        self.model = model
        self.records.clear()
        self.loaded.clear()
        self.tree.delete(*self.tree.get_children(""))
        records = model.root_tree_records()
        header = records[0]
        self.insert_record("", header, offset_text="0")
        # Original navigation: DAT sections live below the expanded File Header.
        for item in records[1:]:
            self.insert_record(header.iid, item)
        self.tree.heading("#0", text=model.file_name)
        self.tree.item(header.iid, open=True)
        # The original viewer opens the root/reference node tables by default.
        for item in records[1:]:
            if item.kind in {"root_table", "reference_table"}:
                self.tree.item(item.iid, open=True)
                self.populate_table(item)
        self.filename.set(model.file_name)
        self.status.set("Loaded {} — {:,} bytes, {} relocations, {} root nodes".format(
            model.file_name, len(model.data), model.rt_count, len(model.root_nodes)))
        self.show_file_overview()

    def insert_record(self, parent: str, record: TreeRecord, offset_text: str | None = None, cycle: bool = False):
        assert self.model
        if offset_text is None:
            offset_text = "" if record.offset is None else "0x{:X}".format(self.model.absolute_offset(record.offset))
        tags = ("cycle",) if cycle else (("table",) if record.kind in {"root_table", "reference_table", "relocation_table", "string_table"} else ())
        self.tree.insert(parent, "end", iid=record.iid, text=record.text, values=(offset_text,), tags=tags)
        self.records[record.iid] = record
        if record.kind == "structure" and not cycle and self.model.direct_children(record.offset or 0, record.type_hint):
            self.tree.insert(record.iid, "end", iid=record.iid + "/__pending__", text="", values=("",))

    def on_tree_open(self, _event):
        iid = self.tree.focus()
        if not self.model or not iid or iid in self.loaded:
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
        assert self.model
        self.remove_pending(record.iid)
        for child in self.model.table_children(record.kind):
            self.insert_record(record.iid, child)
        self.loaded.add(record.iid)

    def populate_structure(self, record: TreeRecord):
        assert self.model and record.offset is not None
        self.remove_pending(record.iid)
        children = self.model.children_with_siblings(record.offset, record.type_hint, record.ancestor_offsets[:-1])
        seen: set[int] = set()
        counts: dict[str, int] = {}
        for offset, type_hint, _label, is_cycle in children:
            if offset in seen:
                continue
            seen.add(offset)
            key = type_hint or "Structure"
            sibling_index = counts.get(key, 0)
            counts[key] = sibling_index + 1
            label = self.model._known_root_labels.get(offset)
            title = self.model.structure_title(offset, type_hint, label, sibling_index)
            iid = record.iid + "/" + str(offset)
            child = TreeRecord("structure", title, iid, offset, type_hint, label, record.ancestor_offsets + (offset,))
            self.insert_record(record.iid, child, cycle=is_cycle)
        self.loaded.add(record.iid)

    def on_tree_select(self, _event):
        if not self.model:
            return
        selection = self.tree.selection()
        if not selection:
            return
        record = self.records.get(selection[0])
        if not record:
            return
        if record.kind == "file_header":
            self.show_file_overview()
        elif record.kind == "structure":
            self.show_structure(record)
        elif record.kind == "relocation_table":
            self.show_table("Relocation Table", self.model.rt_start, self.model.rt_count * 4,
                            "{} 32-bit pointer-location entries".format(self.model.rt_count))
        elif record.kind == "root_table":
            self.show_table("Root Nodes Table", self.model.rt_end, self.model.root_count * 8,
                            "{} root node entries".format(self.model.root_count))
        elif record.kind == "reference_table":
            self.show_table("Reference Nodes Table", self.model.root_nodes_end, self.model.ref_count * 8,
                            "{} reference node entries".format(self.model.ref_count))
        elif record.kind == "string_table":
            size = len(self.model.body) - self.model.string_table_start
            self.show_table("String Table", self.model.string_table_start, size,
                            "{} root/reference labels; {} bytes".format(len(self.model.root_nodes) + len(self.model.reference_nodes), size))

    def show_file_overview(self):
        if not self.model:
            return
        d = self.model.describe()
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
        assert self.model
        text = "{}\n\nOffset in data section: 0x{:X}\nAbsolute file offset: 0x{:X}\nLength: {:,} bytes\n\n{}".format(
            title, offset, self.model.absolute_offset(offset), length, description)
        self.set_text(self.properties, text)
        self.show_raw(offset, min(length, 0x300))

    def show_structure(self, record: TreeRecord):
        assert self.model and record.offset is not None
        offset = record.offset
        length = self.model.structure_length(offset, record.type_hint)
        pointers = self.model.record_pointer_details(offset, record.type_hint)
        lines = [
            record.text,
            "Type: {}".format(record.type_hint or "Unidentified HSD structure"),
            "Data-relative offset: 0x{:X}".format(offset),
            "Absolute file offset: 0x{:X}".format(self.model.absolute_offset(offset)),
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
        assert self.model
        data = self.model.read_bytes(offset, length)
        rows = []
        for start in range(0, len(data), 16):
            chunk = data[start:start + 16]
            hex_part = " ".join("{:02X}".format(byte) for byte in chunk)
            ascii_part = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
            rows.append("{:08X}  {:47s}  {}".format(offset + start, hex_part, ascii_part))
        self.set_text(self.raw, "\n".join(rows) if rows else "No data available.")

    def focus_search(self):
        self.search_entry.focus_set()
        self.search_entry.select_range(0, "end")

    def search_next(self):
        if not self.model:
            return
        query = self.query.get().strip().lower()
        if not query:
            return
        hits = []
        for iid, record in self.records.items():
            value = "{} {} 0x{:X}".format(record.text, record.label or "", record.offset or 0).lower()
            if query in value:
                hits.append(iid)
        if not hits:
            self.status.set("No visible match — expand branches to make deeper structures searchable.")
            return
        index = (getattr(self, "search_index", -1) + 1) % len(hits)
        self.search_index = index
        iid = hits[index]
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)
        self.status.set("Match {}/{}: {}".format(index + 1, len(hits), self.records[iid].text))

    def show_about(self):
        messagebox.showinfo(
            "About",
            "DAT Texture Wizard — Linux GUI Preview\n\n"
            "Native Tk prototype for the linux-port branch.\n"
            "Expandable HSD navigation is read-only in this milestone.",
            parent=self.root,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DAT Texture Wizard native Linux GUI preview")
    parser.add_argument("dat_file", nargs="?", help="Optional DAT file to open at startup")
    args = parser.parse_args(argv)
    root = tk.Tk()
    DatTextureWizardPreview(root, args.dat_file)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
