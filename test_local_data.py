from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parent


def _git(*args, input_text=None):
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        input=input_text,
        text=True,
        check=True,
        capture_output=True,
    ).stdout


def test_machine_local_data_is_ignored_by_git():
    private_paths = {
        "perfumeria_lamus.db",
        "perfumeria_lamus.db-wal",
        "store.sqlite",
        "store.sqlite-shm",
        "store.sqlite3-journal",
        "local.lamusbackup",
        ".env",
        "instance/secret_key",
    }
    ignored = set(
        _git("check-ignore", "--stdin", input_text="\n".join(private_paths)).splitlines()
    )
    assert ignored == private_paths


def test_no_machine_local_data_is_tracked():
    tracked = _git("ls-files").splitlines()
    private_suffixes = (
        ".db",
        ".db-journal",
        ".db-shm",
        ".db-wal",
        ".sqlite",
        ".sqlite-journal",
        ".sqlite-shm",
        ".sqlite-wal",
        ".sqlite3",
        ".sqlite3-journal",
        ".sqlite3-shm",
        ".sqlite3-wal",
        ".lamusbackup",
    )
    assert not [
        path
        for path in tracked
        if path == ".env"
        or path.startswith("instance/")
        or path.endswith(private_suffixes)
    ]
