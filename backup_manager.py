import io
import json
import os
import sqlite3
import tempfile
import threading
import zipfile
from datetime import date, datetime
from pathlib import Path

import database as db


APP_VERSION = 1
DEFAULT_BACKUP_DIR = Path.home() / "Documents" / "Perfumeria Lamus Backups"
STATE_PATH = Path(__file__).resolve().parent / "instance" / "backup_state.json"
REQUIRED_TABLES = {"users", "customers", "ledger", "vendors", "vendor_ledger", "bank_accounts", "bank_balance_log", "audit_log"}
_scheduler_started = False


def _database_snapshot():
    fd, snapshot_name = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    snapshot = Path(snapshot_name)
    source = sqlite3.connect(db.DATABASE)
    destination = sqlite3.connect(snapshot)
    try:
        source.backup(destination)
        if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("The database safety check failed.")
    finally:
        destination.close()
        source.close()
    return snapshot


def create_backup(folder=None, automatic=False):
    """Create a complete, portable archive of all Lamus data."""
    target_dir = Path(folder) if folder else configured_folder()
    target_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    output = target_dir / f"Perfumeria-Lamus-{stamp}.lamusbackup"
    snapshot = _database_snapshot()
    try:
        manifest = {
            "format": "perfumeria-lamus-backup",
            "version": APP_VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "contains": [
                "users and login access",
                "customers and complete ledgers",
                "vendors and complete ledgers",
                "payments, purchases, and balances",
                "bank history",
                "audit history",
            ],
        }
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
            archive.write(snapshot, "lamus-data.db")
        output.chmod(0o600)
    finally:
        snapshot.unlink(missing_ok=True)
    _write_state(output, automatic=automatic)
    _prune(target_dir)
    return output


def _write_state(path, automatic=False):
    state = _read_state()
    updates = {
        "last_backup_date": date.today().isoformat(),
        "last_backup_at": datetime.now().isoformat(timespec="minutes"),
        "last_backup_path": str(path),
        "last_error": "",
    }
    if automatic:
        updates.update({
            "last_auto_backup_date": date.today().isoformat(),
            "last_auto_backup_at": datetime.now().isoformat(timespec="minutes"),
            "last_auto_backup_path": str(path),
        })
    state.update(updates)
    STATE_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    STATE_PATH.chmod(0o600)


def _read_state():
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _location_path(location, custom_folder=""):
    choices = {
        "documents": Path.home() / "Documents" / "Perfumeria Lamus Backups",
        "desktop": Path.home() / "Desktop" / "Perfumeria Lamus Backups",
        "downloads": Path.home() / "Downloads" / "Perfumeria Lamus Backups",
    }
    if location in choices:
        return choices[location]
    if location == "custom":
        raw = (custom_folder or "").strip()
        if not raw:
            raise ValueError("Enter the custom backup folder.")
        path = Path(raw).expanduser()
        if not path.is_absolute():
            raise ValueError("The custom folder must be a complete path.")
        return path
    raise ValueError("Choose a valid backup location.")


def save_schedule(enabled, backup_time, location, custom_folder=""):
    try:
        datetime.strptime(backup_time, "%H:%M")
    except ValueError:
        raise ValueError("Choose a valid backup time.")
    folder = _location_path(location, custom_folder)
    try:
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        probe = folder / ".lamus-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        raise ValueError("Lamus cannot write to that folder. Choose another location.")
    state = _read_state()
    state.update({
        "enabled": bool(enabled),
        "backup_time": backup_time,
        "location": location,
        "custom_folder": str(folder) if location == "custom" else "",
        "last_error": "",
    })
    STATE_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    STATE_PATH.chmod(0o600)


def configured_folder():
    state = _read_state()
    try:
        return _location_path(state.get("location", "documents"), state.get("custom_folder", ""))
    except ValueError:
        return DEFAULT_BACKUP_DIR


def _prune(folder, keep=30):
    for old in sorted(Path(folder).glob("*.lamusbackup"), reverse=True)[keep:]:
        old.unlink(missing_ok=True)


def status():
    state = _read_state()
    state.setdefault("enabled", True)
    state.setdefault("backup_time", "20:00")
    state.setdefault("location", "documents")
    state.setdefault("custom_folder", "")
    folder = configured_folder()
    state["folder"] = str(folder)
    state["backup_count"] = len(list(folder.glob("*.lamusbackup"))) if folder.exists() else 0
    return state


def run_due_backup(now_value=None):
    now_value = now_value or datetime.now()
    state = _read_state()
    enabled = state.get("enabled", True)
    due = now_value.strftime("%H:%M") >= state.get("backup_time", "20:00")
    already_done = state.get("last_auto_backup_date") == now_value.date().isoformat()
    if enabled and due and not already_done:
        return create_backup(automatic=True)
    return None


def _extract_database(upload):
    raw = upload.read()
    try:
        with zipfile.ZipFile(io.BytesIO(raw), "r") as archive:
            names = set(archive.namelist())
            if not {"manifest.json", "lamus-data.db"} <= names:
                raise ValueError("This is not a complete Lamus backup.")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format") != "perfumeria-lamus-backup":
                raise ValueError("This backup belongs to a different application.")
            return archive.read("lamus-data.db")
    except (zipfile.BadZipFile, json.JSONDecodeError):
        raise ValueError("The selected file is not a valid Lamus backup.")


def restore_backup(upload):
    if not upload or not upload.filename:
        raise ValueError("Choose a Lamus backup file first.")
    restored_bytes = _extract_database(upload)
    fd, candidate_name = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    candidate = Path(candidate_name)
    try:
        candidate.write_bytes(restored_bytes)
        check = sqlite3.connect(candidate)
        try:
            if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("The backup is damaged and cannot be restored.")
            tables = {row[0] for row in check.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            if not REQUIRED_TABLES <= tables:
                raise ValueError("The backup is incomplete and cannot be restored.")
        finally:
            check.close()

        # Always preserve the current state before replacing anything.
        create_backup()
        database_path = Path(db.DATABASE).resolve()
        replacement = database_path.with_suffix(database_path.suffix + ".restoring")
        replacement.write_bytes(candidate.read_bytes())
        os.replace(replacement, database_path)
    finally:
        candidate.unlink(missing_ok=True)


def _daily_worker(app):
    with app.app_context():
        while True:
            state = _read_state()
            try:
                run_due_backup()
            except Exception as exc:
                state["last_error"] = str(exc)
                STATE_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
            threading.Event().wait(60)


def start_scheduler(app):
    global _scheduler_started
    if _scheduler_started or app.config.get("TESTING"):
        return
    _scheduler_started = True
    threading.Thread(target=_daily_worker, args=(app,), daemon=True, name="lamus-backups").start()
