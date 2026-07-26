import json
import os
import smtplib
import sqlite3
import tempfile
import threading
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

import keyring
from cryptography.fernet import Fernet, InvalidToken

import database as db


INSTANCE_DIR = Path(__file__).resolve().parent / "instance"
BACKUP_DIR = INSTANCE_DIR / "backups"
CONFIG_PATH = INSTANCE_DIR / "backup_settings.json"
KEY_PATH = INSTANCE_DIR / "backup_recovery.key"
KEYRING_SERVICE = "Perfumeria Lamus Backups"
_scheduler_started = False


def _prepare_dirs():
    INSTANCE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)


def get_settings():
    defaults = {
        "enabled": False,
        "sender_email": "",
        "recipient_email": "",
        "last_backup": "",
        "last_email": "",
        "last_error": "",
    }
    if CONFIG_PATH.exists():
        try:
            defaults.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            defaults["last_error"] = "Backup settings could not be read."
    return defaults


def save_settings(sender_email, recipient_email, enabled, app_password=None):
    _prepare_dirs()
    settings = get_settings()
    old_sender = settings.get("sender_email")
    settings.update({
        "sender_email": sender_email.strip(),
        "recipient_email": recipient_email.strip(),
        "enabled": bool(enabled),
    })
    CONFIG_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    CONFIG_PATH.chmod(0o600)
    if old_sender and old_sender != settings["sender_email"]:
        try:
            keyring.delete_password(KEYRING_SERVICE, old_sender)
        except keyring.errors.PasswordDeleteError:
            pass
    if app_password:
        keyring.set_password(KEYRING_SERVICE, settings["sender_email"], app_password.replace(" ", ""))


def _save_status(**updates):
    settings = get_settings()
    settings.update(updates)
    _prepare_dirs()
    CONFIG_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    CONFIG_PATH.chmod(0o600)


def get_or_create_recovery_key():
    _prepare_dirs()
    if not KEY_PATH.exists():
        KEY_PATH.write_bytes(Fernet.generate_key())
        KEY_PATH.chmod(0o600)
    return KEY_PATH.read_bytes().strip()


def _plain_database_copy(target):
    source = sqlite3.connect(db.DATABASE)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
        result = destination.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"Database check failed: {result}")
    finally:
        destination.close()
        source.close()


def create_backup(send_email=False):
    _prepare_dirs()
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output = BACKUP_DIR / f"lamus_{stamp}.lamusbackup"
    fd, plain_name = tempfile.mkstemp(suffix=".db", dir=INSTANCE_DIR)
    os.close(fd)
    try:
        _plain_database_copy(plain_name)
        output.write_bytes(Fernet(get_or_create_recovery_key()).encrypt(Path(plain_name).read_bytes()))
        output.chmod(0o600)
    finally:
        Path(plain_name).unlink(missing_ok=True)

    _prune_backups()
    _save_status(last_backup=datetime.now().isoformat(timespec="minutes"), last_error="")
    if send_email:
        email_backup(output)
    return output


def _prune_backups(keep=30):
    backups = sorted(BACKUP_DIR.glob("*.lamusbackup"), reverse=True)
    for old in backups[keep:]:
        old.unlink(missing_ok=True)


def email_backup(path):
    settings = get_settings()
    sender = settings.get("sender_email", "").strip()
    recipient = settings.get("recipient_email", "").strip()
    password = keyring.get_password(KEYRING_SERVICE, sender) if sender else None
    if not sender or not recipient or not password:
        raise ValueError("Save the Gmail address, receiving email, and Gmail app password first.")

    message = EmailMessage()
    message["Subject"] = f"Perfumería Lamus backup · {datetime.now():%d %b %Y}"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        "Your encrypted Perfumería Lamus backup is attached.\n\n"
        "Keep your separate recovery key safe. This attachment cannot be restored without it."
    )
    message.add_attachment(
        path.read_bytes(),
        maintype="application",
        subtype="octet-stream",
        filename=path.name,
    )
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(sender, password)
        smtp.send_message(message)
    _save_status(last_email=datetime.now().isoformat(timespec="minutes"), last_error="")


def test_email():
    return create_backup(send_email=True)


def restore_backup(upload, recovery_key):
    if not upload:
        raise ValueError("Choose a Lamus backup file.")
    supplied_key = (recovery_key or "").strip().encode()
    try:
        encrypted = upload.read()
        plain = Fernet(supplied_key).decrypt(encrypted)
    except (ValueError, InvalidToken):
        raise ValueError("The backup or recovery key is not valid.")

    _prepare_dirs()
    fd, candidate_name = tempfile.mkstemp(suffix=".db", dir=INSTANCE_DIR)
    os.close(fd)
    candidate = Path(candidate_name)
    try:
        candidate.write_bytes(plain)
        check = sqlite3.connect(candidate)
        try:
            result = check.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            check.close()
        if result != "ok":
            raise ValueError("This backup failed its safety check.")

        create_backup(send_email=False)
        database_path = Path(db.DATABASE).resolve()
        replacement = database_path.with_suffix(database_path.suffix + ".restoring")
        replacement.write_bytes(candidate.read_bytes())
        os.replace(replacement, database_path)
    finally:
        candidate.unlink(missing_ok=True)


def backup_status():
    settings = get_settings()
    _prepare_dirs()
    files = sorted(BACKUP_DIR.glob("*.lamusbackup"), reverse=True)
    settings["backup_count"] = len(files)
    settings["latest_file"] = files[0].name if files else ""
    settings["recovery_key"] = get_or_create_recovery_key().decode()
    settings["password_saved"] = bool(
        settings.get("sender_email")
        and keyring.get_password(KEYRING_SERVICE, settings["sender_email"])
    )
    return settings


def _daily_worker(app):
    with app.app_context():
        while True:
            settings = get_settings()
            if settings.get("enabled"):
                last = settings.get("last_backup")
                try:
                    due = not last or datetime.fromisoformat(last) <= datetime.now() - timedelta(hours=24)
                except ValueError:
                    due = True
                if due:
                    try:
                        create_backup(send_email=True)
                    except Exception as exc:
                        _save_status(last_error=str(exc))
            threading.Event().wait(3600)


def start_scheduler(app):
    global _scheduler_started
    if _scheduler_started or app.config.get("TESTING"):
        return
    _scheduler_started = True
    threading.Thread(target=_daily_worker, args=(app,), daemon=True, name="lamus-backups").start()
