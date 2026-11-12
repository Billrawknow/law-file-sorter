"""
Document Sorter - desktop app
-----------------------------
A simple window for office staff (no technical knowledge needed):
  1. Choose folder   - pick the downloads folder (remembered for next time)
  2. Preview         - see where every file will go, nothing is moved yet.
                       Double-click a file to open and check it. Select files and
                       use "Move to" or "Don't move" to change where they go -
                       including a new folder (e.g. a client's name) or any
                       folder on the computer.
  Rules              - "files whose name contains Caleb always go to Caleb's
                       folder". Saved in the folder being sorted, so the nightly
                       automatic run uses them too.
  3. Sort now        - move the files into Contracts / Evidence / Filings /
                       Correspondence / Other, and log every move

Run from source:   python sorter_app.py
Build the .exe:    see build_exe.bat (staff then need no Python at all)
"""

import json
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from sort_files import (CATEGORIES, LOG_NAME, OTHER, RULES_NAME, apply_moves, clean_folder_name,
                        destination_for, load_rules, plan_moves, rules_problem, save_rules, sortable_files)

APP_TITLE = "Document Sorter"
FIRM_NAME = "WAKILI KIPKIRUI KEMBOI & ASSOCIATES ADVOCATES"      # change per client
SETTINGS = Path.home() / ".document_sorter.json"
FOLDERS = list(CATEGORIES) + [OTHER]
MAX_RECENT = 8


def load_settings():
    try:
        data = json.loads(SETTINGS.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(**changes):
    data = load_settings()
    data.update(changes)
    try:
        SETTINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass                                    # remembering settings is a convenience only


def load_last_folder():
    folder = load_settings().get("folder", "")
    return folder if folder and Path(folder).is_dir() else ""


def save_last_folder(folder):
    save_settings(folder=folder)


def open_in_explorer(path):
    """Open a file or folder with the computer's default program."""
    if sys.platform.startswith("win"):
        os.startfile(path)                      # noqa: S606 - Windows only
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


class SorterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} - {FIRM_NAME}")
        icon = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "icon.ico"
        if sys.platform.startswith("win") and icon.exists():
            self.iconbitmap(str(icon))
        self.geometry("820x560")
        self.minsize(640, 420)
        self.folder = tk.StringVar(value=load_last_folder())
        self.status = tk.StringVar()
        self.moves = []
        self.overrides = {}          # filename -> folder name, or None for "don't move"
        self.row_paths = {}          # tree row id -> path to open on double-click
        self._build()
        self._refresh_buttons()
        self.status.set("Choose the folder to sort, then click Preview."
                        if not self.folder.get() else "Click Preview to see what will be sorted.")

    # ------------------------------------------------------------ layout
    def _build(self):
        style = ttk.Style(self)
        style.configure("Title.TLabel", font=("Segoe UI", 15, "bold"))
        style.configure("Sub.TLabel", foreground="#5f6670")
        style.configure("Big.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 6))
        style.configure("Treeview", rowheight=24)

        top = ttk.Frame(self, padding=(16, 14, 16, 6))
        top.pack(fill="x")
        ttk.Label(top, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(top, text=f"{FIRM_NAME}  ·  sorts downloads into "
                            + ", ".join(FOLDERS), style="Sub.TLabel").pack(anchor="w")

        row = ttk.Frame(self, padding=(16, 6))
        row.pack(fill="x")
        ttk.Label(row, text="Folder:").pack(side="left")
        ttk.Entry(row, textvariable=self.folder, state="readonly").pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row, text="Choose folder...", command=self.choose_folder).pack(side="left")

        buttons = ttk.Frame(self, padding=(16, 6))
        buttons.pack(fill="x")
        self.preview_btn = ttk.Button(buttons, text="1. Preview", style="Big.TButton", command=self.preview)
        self.preview_btn.pack(side="left")
        self.sort_btn = ttk.Button(buttons, text="2. Sort now", style="Big.TButton", command=self.sort_now)
        self.sort_btn.pack(side="left", padx=8)
        self.log_btn = ttk.Button(buttons, text="Open log", command=self.open_log)
        self.log_btn.pack(side="right")
        self.rules_btn = ttk.Button(buttons, text="Rules...", command=self.edit_rules)
        self.rules_btn.pack(side="right", padx=(0, 8))
        self.open_btn = ttk.Button(buttons, text="Open folder", command=lambda: open_in_explorer(self.folder.get()))
        self.open_btn.pack(side="right", padx=8)

        actions = ttk.Frame(self, padding=(16, 0, 16, 4))
        actions.pack(fill="x")
        ttk.Label(actions, text="Selected file(s):", style="Sub.TLabel").pack(side="left")
        self.openfile_btn = ttk.Button(actions, text="Open file", command=self.open_selected)
        self.openfile_btn.pack(side="left", padx=(8, 0))
        self.moveto_btn = ttk.Menubutton(actions, text="Move to \u25be")
        self.move_menu = tk.Menu(self.moveto_btn, tearoff=False, postcommand=self._build_move_menu)
        self.moveto_btn["menu"] = self.move_menu
        self.moveto_btn.pack(side="left", padx=8)
        self.skip_btn = ttk.Button(actions, text="Don't move", command=lambda: self.set_destination(None))
        self.skip_btn.pack(side="left")
        self.rule_btn = ttk.Button(actions, text="Always do this...", command=self.rule_from_selected)
        self.rule_btn.pack(side="left", padx=8)
        ttk.Label(actions, text="Tip: double-click a file to open it", style="Sub.TLabel").pack(side="right")

        table = ttk.Frame(self, padding=(16, 6))
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=("file", "dest", "note"), show="headings", selectmode="extended")
        for col, text, width in (("file", "File", 300), ("dest", "Goes to", 220), ("note", "Note", 260)):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor="w")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.tag_configure("failed", foreground="#b42318")
        self.tree.tag_configure("done", foreground="#1d7a43")
        self.tree.tag_configure("changed", foreground="#1f5f8b")
        self.tree.tag_configure("skip", foreground="#7a7f87")
        self.tree.tag_configure("rule", foreground="#6b3fa0")
        self.tree.bind("<Double-1>", lambda e: self.open_selected())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._refresh_buttons())

        status = ttk.Label(self, textvariable=self.status, padding=(16, 8), justify="left")
        status.pack(fill="x")
        status.bind("<Configure>", lambda e: status.configure(wraplength=e.width - 32))

    # ------------------------------------------------------------ helpers
    def _target(self):
        folder = self.folder.get()
        return Path(folder) if folder and Path(folder).is_dir() else None

    def _refresh_buttons(self):
        has_folder = self._target() is not None
        for btn in (self.preview_btn, self.open_btn, self.rules_btn):
            btn.state(["!disabled"] if has_folder else ["disabled"])
        self.sort_btn.state(["!disabled"] if self.moves else ["disabled"])
        selected = bool(self.tree.selection())
        self.openfile_btn.state(["!disabled"] if selected else ["disabled"])
        editable = selected and self.preview_mode
        for btn in (self.moveto_btn, self.skip_btn):
            btn.state(["!disabled"] if editable else ["disabled"])
        one = editable and len(self.tree.selection()) == 1
        self.rule_btn.state(["!disabled"] if one else ["disabled"])
        log_exists = has_folder and (self._target() / LOG_NAME).exists()
        self.log_btn.state(["!disabled"] if log_exists else ["disabled"])

    def _recent_destinations(self):
        target = self._target()
        recent = load_settings().get("recent", [])
        return [r for r in recent if not (target and not Path(r).is_absolute() and r in FOLDERS)][:MAX_RECENT]

    def _build_move_menu(self):
        menu = self.move_menu
        menu.delete(0, "end")
        for folder in FOLDERS:
            menu.add_command(label=folder, command=lambda f=folder: self.set_destination(f))
        recent = self._recent_destinations()
        if recent:
            menu.add_separator()
            menu.add_command(label="Recently used:", state="disabled")
            for dest in recent:
                menu.add_command(label="   " + self._label_for(dest), command=lambda d=dest: self.set_destination(d))
        menu.add_separator()
        menu.add_command(label="New folder...", command=self.new_folder)
        menu.add_command(label="Choose another folder...", command=self.choose_destination)
        menu.add_separator()
        menu.add_command(label="Automatic (by file type)", command=lambda: self.set_destination("auto"))

    def _label_for(self, dest):
        """How a destination is shown: 'Clients/Caleb' inside the folder, full path outside it."""
        return str(Path(dest)) if Path(dest).is_absolute() else dest

    def _remember(self, dest):
        recent = [r for r in load_settings().get("recent", []) if r != dest]
        save_settings(recent=[dest] + recent[:MAX_RECENT - 1])

    def new_folder(self):
        if not self.tree.selection():
            return
        name = simpledialog.askstring(APP_TITLE, "Name of the new folder\n(for example: Caleb Otieno, "
                                                 "or Clients/Jane Wanjiru)", parent=self)
        if name is None:
            return
        try:
            folder = clean_folder_name(name)
        except ValueError as err:
            messagebox.showwarning(APP_TITLE, str(err))
            return
        self._remember(folder)
        self.set_destination(folder)

    def choose_destination(self):
        if not self.tree.selection():
            return
        chosen = filedialog.askdirectory(title="Move the selected file(s) to...",
                                         initialdir=self.folder.get() or str(Path.home()), mustexist=True)
        if not chosen:
            return
        target, chosen_path = self._target(), Path(chosen).resolve()
        if target and chosen_path == target.resolve():
            self.set_destination(None)          # same folder = leave the file where it is
            return
        try:
            dest = chosen_path.relative_to(target.resolve()).as_posix()   # inside: keep it short
        except ValueError:
            dest = str(chosen_path)                                       # elsewhere on the computer
        self._remember(dest)
        self.set_destination(dest)

    def _clear_table(self):
        self.tree.delete(*self.tree.get_children())
        self.row_paths = {}

    preview_mode = False

    # ------------------------------------------------------------ actions
    def choose_folder(self):
        chosen = filedialog.askdirectory(title="Choose the folder to sort",
                                         initialdir=self.folder.get() or str(Path.home()))
        if chosen:
            self.folder.set(chosen)
            save_last_folder(chosen)
            self.moves = []
            self.overrides = {}
            self.preview_mode = False
            self._clear_table()
            self.status.set("Folder selected. Click Preview to see what will be sorted.")
            self._refresh_buttons()

    def preview(self):
        target = self._target()
        if not target:
            messagebox.showwarning(APP_TITLE, "That folder no longer exists. Please choose it again.")
            return
        self.preview_mode = True
        selected_names = {self.tree.set(i, "file") for i in self.tree.selection()}
        rules = load_rules(target)
        self.moves = plan_moves(target, self.overrides, rules)
        dest_by_name = {src.name: dest for src, dest in self.moves}
        self._clear_table()
        for path in sortable_files(target):
            dest = dest_by_name.get(path.name)
            notes, tag = [], ()
            if dest is None:
                folder_text, tag = "(stays here)", ("skip",)
                notes.append("You chose not to move this file")
            else:
                folder_text = self._display_folder(dest)
                if path.name in self.overrides:
                    tag = ("changed",)
                    normally, _ = destination_for(path, {}, rules)
                    notes.append(f"You chose this (normally {self._label_for(normally)})")
                else:
                    _, reason = destination_for(path, {}, rules)
                    if reason:
                        tag = ("rule",)
                        notes.append(reason[0].upper() + reason[1:])
                if dest.name != path.name:
                    notes.append(f"Will be saved as {dest.name} - name already used")
            row = self.tree.insert("", "end", values=(path.name, folder_text, "; ".join(notes)), tags=tag)
            self.row_paths[row] = path
            if path.name in selected_names:
                self.tree.selection_add(row)
        if self.row_paths:
            counts = {}
            for _, d in self.moves:
                label = self._display_folder(d).rstrip("/")
                label = Path(label).name if Path(label).is_absolute() else label   # short name in the summary
                counts[label] = counts.get(label, 0) + 1
            summary = ", ".join(f"{f} {n}" for f, n in counts.items())
            kept = len(self.row_paths) - len(self.moves)
            self.status.set(f"Preview: {len(self.moves)} file(s) ready to sort ({summary or 'none'})"
                            + (f", {kept} staying where they are" if kept else "")
                            + ". Nothing has been moved yet. Double-click a file to check it; "
                              "use 'Move to' to change a folder; then click 'Sort now'.")
        else:
            self.status.set("Nothing to sort - this folder is already tidy.")
        problem = rules_problem(target)
        if problem:
            self.status.set(self.status.get() + "  Warning: " + problem)
        self._refresh_buttons()

    # ------------------------------------------------------------ rules
    def edit_rules(self):
        target = self._target()
        if target:
            RulesDialog(self, target)
            if self.preview_mode:
                self.preview()

    def rule_from_selected(self):
        target, selection = self._target(), self.tree.selection()
        if not target or len(selection) != 1:
            return
        path = self.row_paths.get(selection[0])
        dest = next((d for s_, d in self.moves if s_ == path), None)
        current = None
        if dest is not None:
            try:
                current = dest.parent.relative_to(target).as_posix()
            except ValueError:
                current = str(dest.parent)
        rule = RuleEditor.ask(self, target, contains=Path(path.name).stem, folder=current)
        if rule:
            rules = load_rules(target)
            rules.insert(0, rule)                 # newest rule first, so it wins
            save_rules(target, rules)
            self.overrides.pop(path.name, None)
            self.preview()
            self.status.set(f"Rule saved: files containing '{rule['contains']}' will always go to "
                            f"{self._label_for(rule['folder'])}. " + self.status.get())

    def _display_folder(self, dest):
        target = self._target()
        try:
            return dest.parent.relative_to(target).as_posix() + "/"
        except (ValueError, TypeError):
            return str(dest.parent)

    def set_destination(self, folder):
        """folder: a folder name, None for "don't move", or "auto" to undo a change."""
        names = [self.tree.set(i, "file") for i in self.tree.selection()]
        if not names or not self.preview_mode:
            return
        for name in names:
            if folder == "auto":
                self.overrides.pop(name, None)
            else:
                self.overrides[name] = folder
        self.preview()

    def open_selected(self):
        selection = self.tree.selection()
        if not selection:
            return
        path = self.row_paths.get(selection[0])
        if not path or not path.exists():
            messagebox.showinfo(APP_TITLE, "That file isn't there any more. Click Preview to refresh the list.")
            return
        try:
            open_in_explorer(path)
        except OSError:
            messagebox.showwarning(APP_TITLE, f"There's no program on this computer to open {path.name}.")

    def sort_now(self):
        target = self._target()
        if not target or not self.moves:
            return
        if not messagebox.askyesno(APP_TITLE, f"Move {len(self.moves)} file(s) into their folders now?"):
            return
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            moved, failed, _log = apply_moves(target, self.moves)
        finally:
            self.config(cursor="")
        self._clear_table()
        self.preview_mode = False
        for src, dest in moved:
            row = self.tree.insert("", "end", values=(src.name, self._display_folder(dest), "Moved"), tags=("done",))
            self.row_paths[row] = dest
        for src, reason in failed:
            row = self.tree.insert("", "end", values=(src.name, "-", f"Not moved: {reason}"), tags=("failed",))
            self.row_paths[row] = src
        self.moves = []
        self.overrides = {}
        self._refresh_buttons()
        if failed:
            self.status.set(f"Sorted {len(moved)} file(s). {len(failed)} couldn't be moved - "
                            "close them in Word or Acrobat and sort again.")
            messagebox.showwarning(APP_TITLE, f"{len(failed)} file(s) were not moved because they are open "
                                              "in another program.\n\nClose them and click Preview again.")
        else:
            self.status.set(f"Done. {len(moved)} file(s) sorted. Every move is recorded in {LOG_NAME}.")

    def open_log(self):
        target = self._target()
        if target and (target / LOG_NAME).exists():
            open_in_explorer(target / LOG_NAME)


class RuleEditor(tk.Toplevel):
    """Small dialog: 'If the file name contains [text], move it to [folder]'."""

    def __init__(self, parent, target, contains="", folder=None):
        super().__init__(parent)
        self.title("Rule")
        self.transient(parent)
        self.resizable(False, False)
        self.target, self.result = target, None
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="If the file name contains:").grid(row=0, column=0, sticky="w")
        self.contains = tk.StringVar(value=contains)
        entry = ttk.Entry(frame, textvariable=self.contains, width=40)
        entry.grid(row=1, column=0, columnspan=2, sticky="we", pady=(2, 10))
        ttk.Label(frame, text="(capitals don't matter, e.g. caleb matches Caleb_ID.pdf)",
                  style="Sub.TLabel").grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Label(frame, text="Move it to this folder:").grid(row=3, column=0, sticky="w")
        recent = [r for r in load_settings().get("recent", []) if r not in FOLDERS]
        self.folder = tk.StringVar(value=folder or "")
        combo = ttk.Combobox(frame, textvariable=self.folder, values=FOLDERS + recent, width=38)
        combo.grid(row=4, column=0, sticky="we", pady=(2, 0))
        ttk.Button(frame, text="Browse...", command=self.browse).grid(row=4, column=1, padx=(8, 0))
        ttk.Label(frame, text="Type a new name (e.g. Clients/Caleb Otieno) or pick one",
                  style="Sub.TLabel").grid(row=5, column=0, columnspan=2, sticky="w", pady=(2, 12))
        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Save rule", command=self.save).pack(side="right", padx=8)
        self.bind("<Return>", lambda e: self.save())
        self.bind("<Escape>", lambda e: self.destroy())
        entry.focus_set()
        entry.select_range(0, "end")

    def browse(self):
        chosen = filedialog.askdirectory(parent=self, title="Choose the folder", initialdir=str(self.target))
        if chosen:
            try:
                self.folder.set(Path(chosen).resolve().relative_to(self.target.resolve()).as_posix())
            except ValueError:
                self.folder.set(str(Path(chosen).resolve()))

    def save(self):
        text, folder = self.contains.get().strip(), self.folder.get().strip()
        if len(text) < 2:
            messagebox.showwarning("Rule", "Type at least 2 letters of the file name to match.", parent=self)
            return
        if not folder:
            messagebox.showwarning("Rule", "Choose or type the folder to move matching files to.", parent=self)
            return
        if not Path(folder).is_absolute():
            try:
                folder = clean_folder_name(folder)
            except ValueError as err:
                messagebox.showwarning("Rule", str(err), parent=self)
                return
            if folder in (".", ""):
                return
        self.result = {"contains": text, "folder": folder}
        if not Path(folder).is_absolute() and folder not in FOLDERS:
            recent = [r for r in load_settings().get("recent", []) if r != folder]
            save_settings(recent=[folder] + recent[:MAX_RECENT - 1])
        self.destroy()

    @classmethod
    def ask(cls, parent, target, contains="", folder=None):
        dialog = cls(parent, target, contains, folder)
        dialog.grab_set()
        parent.wait_window(dialog)
        return dialog.result


class RulesDialog(tk.Toplevel):
    """List of saved rules with Add / Edit / Delete / Move up / Move down."""

    def __init__(self, parent, target):
        super().__init__(parent)
        self.title(f"Rules - {RULES_NAME}")
        self.transient(parent)
        self.geometry("640x340")
        self.target = target
        self.rules = load_rules(target)
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Files whose name contains the text go to the folder instead of their usual "
                              "folder. The first rule that matches wins.", wraplength=600,
                  style="Sub.TLabel").pack(anchor="w", pady=(0, 8))
        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(body, columns=("contains", "folder"), show="headings", selectmode="browse")
        self.tree.heading("contains", text="If file name contains")
        self.tree.heading("folder", text="Move to")
        self.tree.column("contains", width=180)
        self.tree.column("folder", width=300)
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.edit())
        side = ttk.Frame(body, padding=(10, 0, 0, 0))
        side.pack(side="right", fill="y")
        for text, command in (("Add...", self.add), ("Edit...", self.edit), ("Delete", self.delete),
                              ("Move up", lambda: self.move(-1)), ("Move down", lambda: self.move(1))):
            ttk.Button(side, text=text, command=command, width=12).pack(pady=2)
        ttk.Button(frame, text="Close", command=self.destroy).pack(anchor="e", pady=(10, 0))
        self.refresh()
        self.grab_set()
        parent.wait_window(self)

    def refresh(self, select=None):
        self.tree.delete(*self.tree.get_children())
        for i, rule in enumerate(self.rules):
            self.tree.insert("", "end", iid=str(i), values=(rule["contains"], rule["folder"]))
        if select is not None and 0 <= select < len(self.rules):
            self.tree.selection_set(str(select))

    def _selected(self):
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _save(self, select=None):
        save_rules(self.target, self.rules)
        self.refresh(select)

    def add(self):
        rule = RuleEditor.ask(self, self.target)
        if rule:
            self.rules.append(rule)
            self._save(len(self.rules) - 1)

    def edit(self):
        i = self._selected()
        if i is None:
            return
        rule = RuleEditor.ask(self, self.target, self.rules[i]["contains"], self.rules[i]["folder"])
        if rule:
            self.rules[i] = rule
            self._save(i)

    def delete(self):
        i = self._selected()
        if i is not None and messagebox.askyesno("Rules", f"Delete the rule for '{self.rules[i]['contains']}'?",
                                                 parent=self):
            del self.rules[i]
            self._save()

    def move(self, step):
        i = self._selected()
        j = None if i is None else i + step
        if j is not None and 0 <= j < len(self.rules):
            self.rules[i], self.rules[j] = self.rules[j], self.rules[i]
            self._save(j)


if __name__ == "__main__":
    SorterApp().mainloop()
