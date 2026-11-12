"""
Law Firm File Sorter
--------------------
Sorts a messy downloads folder into subfolders by document type, and logs
every move to sort_log.txt with a timestamp, the original path and the
destination path.

    Contracts/       .docx .doc
    Evidence/        .jpg .jpeg .png
    Filings/         .pdf
    Correspondence/  .txt .eml
    Other/           everything else

Saved rules (optional): sorter_rules.json in the folder being sorted, e.g.
    [{"contains": "caleb", "folder": "Clients/Caleb Otieno"},
     {"contains": "ID_",   "folder": "D:/Client IDs"}]
A file whose name contains the text (capitals ignored) goes to that folder instead of
its file-type folder. The first matching rule wins. The desktop app edits this file.

Safe by default: it only PREVIEWS what it would do. Add --apply to move files.
Nothing is ever overwritten: if a file with the same name already exists in the
destination, the new one is saved as "name (2).ext", "name (3).ext", ...

Usage:
    python sort_files.py "C:/Users/Reception/Downloads/Client Docs"           # preview
    python sort_files.py "C:/Users/Reception/Downloads/Client Docs" --apply   # sort
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

CATEGORIES = {
    "Contracts": {".docx", ".doc"},
    "Evidence": {".jpg", ".jpeg", ".png"},
    "Filings": {".pdf"},
    "Correspondence": {".txt", ".eml"},
}
OTHER = "Other"
LOG_NAME = "sort_log.txt"
RULES_NAME = "sorter_rules.json"
SKIP_NAMES = {LOG_NAME, RULES_NAME, "desktop.ini", "thumbs.db", ".ds_store"}


INVALID_CHARS = set('<>:"\\|?*')
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def clean_folder_name(name):
    """Validate a folder name typed by a user, e.g. "Caleb" or "Clients/Jane Wanjiru".
    Returns the cleaned name, or raises ValueError with a plain-English reason."""
    parts = [part.strip() for part in name.replace("\\", "/").split("/") if part.strip()]
    if not parts:
        raise ValueError("Please type a folder name.")
    for part in parts:
        if part in (".", ".."):
            raise ValueError("Folder names can't be '.' or '..'.")
        if any(ch in INVALID_CHARS for ch in part):
            raise ValueError('Folder names can\'t contain any of these: < > : " \\ | ? *')
        if part.rstrip(". ").lower() in RESERVED or part.endswith((".", " ")):
            raise ValueError(f"'{part}' can't be used as a folder name on Windows.")
    return "/".join(parts)


def load_rules(target):
    """Read saved rules from the folder. A missing or broken file means no rules."""
    try:
        data = json.loads((target / RULES_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [r for r in data if isinstance(r, dict) and str(r.get("contains", "")).strip() and r.get("folder")]


def rules_problem(target):
    """Plain-English warning if the rules file exists but can't be read, else None."""
    path = target / RULES_NAME
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError
    except (OSError, ValueError):
        return f"{RULES_NAME} couldn't be read, so no saved rules were used. Re-create the rules in the app."
    return None


def save_rules(target, rules):
    (target / RULES_NAME).write_text(json.dumps(rules, indent=2, ensure_ascii=False), encoding="utf-8")


def matching_rule(path, rules):
    name = path.name.lower()
    return next((r for r in rules if str(r["contains"]).strip().lower() in name), None)


def category_for(path):
    ext = path.suffix.lower()
    for folder, extensions in CATEGORIES.items():
        if ext in extensions:
            return folder
    return OTHER


def free_name(dest_folder, filename, taken):
    """Return a destination path that doesn't overwrite anything."""
    candidate = dest_folder / filename
    stem, suffix = Path(filename).stem, Path(filename).suffix
    n = 2
    while candidate.exists() or candidate in taken:
        candidate = dest_folder / f"{stem} ({n}){suffix}"
        n += 1
    return candidate


def sortable_files(target):
    """Files in the top level of the folder that should be considered for sorting."""
    return [
        path for path in sorted(target.iterdir(), key=lambda p: p.name.lower())
        if path.is_file()                                         # leave subfolders alone
        and path.name.lower() not in SKIP_NAMES                   # log and system files
        and not path.name.startswith(("~$", "."))                 # Office lock files, hidden files
    ]


def destination_for(path, overrides, rules):
    """Decide where a file goes. Returns (folder or None, reason).
    Priority: the user's choice in the preview > saved rules > file type."""
    if path.name in overrides:
        return overrides[path.name], "chosen"
    rule = matching_rule(path, rules)
    if rule:
        return rule["folder"], f"rule: name contains '{rule['contains']}'"
    return category_for(path), ""


def plan_moves(target, overrides=None, rules=None):
    """Work out every move first, so the preview shows exactly what --apply will do.

    overrides: optional {filename: destination} chosen by the user, where destination is
      - a folder name inside the target, e.g. "Contracts" or "Clients/Caleb Otieno"
      - an absolute path anywhere on the computer, e.g. "D:/Clients/Jane Wanjiru"
      - None, meaning "don't move this file"
    """
    overrides = overrides or {}
    rules = load_rules(target) if rules is None else rules
    moves, taken = [], set()
    for path in sortable_files(target):
        folder, _reason = destination_for(path, overrides, rules)
        if folder is None:
            continue
        dest_folder = Path(folder) if Path(folder).is_absolute() else target / folder
        dest = free_name(dest_folder, path.name, taken)
        taken.add(dest)
        moves.append((path, dest))
    return moves


def write_log(log_path, lines):
    with open(log_path, "a", encoding="utf-8") as log:
        log.write("\n".join(lines) + "\n")


def apply_moves(target, moves):
    """Move the planned files and log each one.
    Returns (moved, failed, log_path): moved is a list of (src, dest),
    failed is a list of (src, reason)."""
    moved, failed, lines = [], [], []
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for src, dest in moves:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
        except OSError as err:
            reason = err.strerror or str(err)
            failed.append((src, reason))
            lines.append(f"{datetime.now():%Y-%m-%d %H:%M:%S} | FAILED | {src} | {reason}")
            continue
        moved.append((src, dest))
        lines.append(f"{datetime.now():%Y-%m-%d %H:%M:%S} | MOVED  | {src} -> {dest}")
    log_path = target / LOG_NAME
    write_log(log_path, [f"--- Run started {started}: {len(moved)} moved, {len(failed)} failed ---", *lines])
    return moved, failed, log_path


def main():
    parser = argparse.ArgumentParser(description="Sort a folder of legal documents into subfolders by type.")
    parser.add_argument("folder", help="the folder to sort")
    parser.add_argument("--apply", action="store_true", help="actually move the files (default is a preview)")
    args = parser.parse_args()

    target = Path(args.folder).expanduser().resolve()
    if not target.is_dir():
        sys.exit(f"Folder not found: {target}")

    rules = load_rules(target)
    moves = plan_moves(target, rules=rules)
    problem = rules_problem(target)
    if problem:
        print(f"Warning: {problem}")
    if rules:
        print(f"Using {len(rules)} saved rule(s) from {RULES_NAME}")
    if not moves:
        print(f"Nothing to sort in {target}.")
        return

    mode = "SORTING" if args.apply else "PREVIEW (nothing will be moved)"
    print(f"{mode}: {len(moves)} file(s) in {target}\n")

    def show(rows):
        counts = {}
        for src, dest in rows:
            notes = []
            rule = matching_rule(src, rules)
            if rule:
                notes.append(f"rule: '{rule['contains']}'")
            if dest.name != src.name:
                notes.append("renamed: a file with that name already exists")
            try:
                shown = dest.relative_to(target)
            except ValueError:
                shown = dest
            print(f"  {src.name:<40} -> {shown}" + (f"  ({'; '.join(notes)})" if notes else ""))
            counts[dest.parent.name] = counts.get(dest.parent.name, 0) + 1
        print("\nSummary: " + ", ".join(f"{folder} {n}" for folder, n in sorted(counts.items())))

    if not args.apply:
        show(moves)
        print("\nThis was a preview. Run again with --apply to move the files.")
        return

    moved, failed, log_path = apply_moves(target, moves)
    show(moved)
    for src, reason in failed:
        print(f"  FAILED  {src.name}: {reason}  (is it open in another program?)")
    print(f"Logged to {log_path}")
    if failed:
        print(f"{len(failed)} file(s) couldn't be moved. Close them in Word/Acrobat and run again.")


if __name__ == "__main__":
    main()
