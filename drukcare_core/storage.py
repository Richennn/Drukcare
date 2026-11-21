"""Safe local CSV storage shared by Tkinter, Gradio and Streamlit.

Safety features (from the project proposal):
  * atomic writes   - data is written to a temp file, then swapped in
  * thread lock     - two threads in one app never write at the same time
  * file lock       - two apps (e.g. Tkinter + Streamlit) never write at the same time
  * daily backups   - data/backups/YYYY-MM-DD/ (last 14 days kept)
  * auto restore    - a corrupted CSV is restored from the latest backup
"""
import csv
import os
import shutil
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from . import config

# Eight ERD entities (incl. CARE_LINK) + three extension tables (profile, weight, messages).
SCHEMAS = {
    "user_account": ["User_ID", "Full_Name", "CID", "Role", "Date_of_Birth", "Phone",
                     "Created_On", "Username", "Password_Hash", "Salt"],
    # a caregiver or provider who entered the patient's username + CID (read-only access)
    "care_link": ["Link_ID", "Caregiver_ID", "Patient_ID", "Linked_On"],
    "prescription": ["Rx_ID", "Provider_ID", "Patient_ID", "Rx_Date", "Diagnosis_Note"],
    "prescription_item": ["Item_ID", "Rx_ID", "Med_Name", "Dosage", "Frequency", "Duration_Days"],
    "medication": ["Med_ID", "User_ID", "Item_ID", "Med_Name", "Dosage", "Dosage_Time",
                   "Frequency", "Priority_Level", "Start_Date", "End_Date", "Is_Active"],
    "compliance_log": ["Log_ID", "Med_ID", "Log_Date", "Scheduled_Time", "Action_Time",
                       "Compliance_Status", "Snooze_Until"],
    "exercise_goal": ["Goal_ID", "User_ID", "Goal_Type", "Exercise_Target", "Start_Date",
                      "Target_Date", "Is_Active"],
    "exercise_log": ["Exercise_ID", "Goal_ID", "Log_Date", "Progress_Value", "Progress_Percent",
                     "Activity_ID", "Activity_Type"],
    # extension tables (not in the ERD, needed for the profile page and weight chart)
    "health_profile": ["User_ID", "Email", "Gender", "Height_Cm", "Weight_Kg", "Blood_Type",
                       "Allergies", "Conditions", "Emergency_Name", "Emergency_Relation",
                       "Emergency_Phone", "Notify_Reminders", "Notify_Weekly", "Snooze_Min",
                       "Sound_On"],
    "weight_log": ["Weight_ID", "User_ID", "Log_Date", "Weight_Kg"],
    # messages a caregiver / provider sends to a linked patient (shown under the bell and as a pop-up)
    "message": ["Msg_ID", "Patient_ID", "Sender_ID", "Sent_At", "Title", "Body", "Is_Read"],
}

BACKUPS_TO_KEEP = 14


class StorageError(Exception):
    """Raised when a CSV file cannot be read or written."""


# ------------------------------------------------------------------ locking
_thread_lock = threading.RLock()
_depth = 0  # how many times the current holder has entered locked()


class _FileLock:
    """Very small cross-process lock using an exclusively created lock file."""

    def __init__(self, path: Path, timeout: float = 8.0, stale_after: float = 20.0):
        self.path, self.timeout, self.stale_after = path, timeout, stale_after

    def acquire(self):
        start = time.time()
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return
            except FileExistsError:
                try:  # break a lock left behind by a crashed program
                    if time.time() - self.path.stat().st_mtime > self.stale_after:
                        self.path.unlink()
                        continue
                except OSError:
                    pass
                if time.time() - start > self.timeout:
                    raise StorageError("Data files are busy. Please try again in a moment.")
                time.sleep(0.03)

    def release(self):
        try:
            self.path.unlink()
        except OSError:
            pass


_file_lock = _FileLock(config.DATA_DIR / ".drukcare.lock")


@contextmanager
def locked():
    """Hold the thread lock and the cross-process lock (re-entrant)."""
    global _depth
    with _thread_lock:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        if _depth == 0:
            _file_lock.acquire()
        _depth += 1
        try:
            yield
        finally:
            _depth -= 1
            if _depth == 0:
                _file_lock.release()


# ------------------------------------------------------------------ helpers
def new_id() -> str:
    """8-character unique id (matches VARCHAR(8) in the ERD)."""
    return uuid.uuid4().hex[:8]


def next_ids(name: str, column: str, prefix: str, count: int = 1, width: int = 3) -> list:
    """Readable running ids such as RX001, RX002 ... or MED001 (see the proposal presentation).
    Call it while holding locked(), so two saves never get the same number."""
    biggest = 0
    for row in read_table(name):
        value = str(row.get(column, ""))
        if value.startswith(prefix) and value[len(prefix):].isdigit():
            biggest = max(biggest, int(value[len(prefix):]))
    return [f"{prefix}{n:0{width}d}" for n in range(biggest + 1, biggest + 1 + count)]


def today_str() -> str:
    return date.today().isoformat()


def table_path(name: str) -> Path:
    return config.DATA_DIR / f"{name}.csv"


def _write_atomic(path: Path, fields, rows):
    tmp = path.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})
        f.flush()
        os.fsync(f.fileno())
    for attempt in range(10):  # Windows can briefly lock a file that is being read
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05)
    raise StorageError(f"Could not save {path.name}. Is it open in another program?")


# ------------------------------------------------------------------ backups
_last_backup_check = ""


def backup_if_needed():
    """Copy every CSV into data/backups/<today>/ once per day."""
    global _last_backup_check
    today = today_str()
    if _last_backup_check == today:
        return
    folder = config.BACKUP_DIR / today
    if not folder.exists():
        try:
            folder.mkdir(parents=True, exist_ok=True)
            for name in SCHEMAS:
                src = table_path(name)
                if src.exists():
                    shutil.copy2(src, folder / src.name)
            days = sorted(p for p in config.BACKUP_DIR.iterdir() if p.is_dir())
            for old in days[:-BACKUPS_TO_KEEP]:
                shutil.rmtree(old, ignore_errors=True)
        except OSError:
            pass
    _last_backup_check = today


def restore_from_backup(name: str) -> bool:
    """Restore one table from the newest backup. Returns True when restored."""
    if not config.BACKUP_DIR.exists():
        return False
    for folder in sorted((p for p in config.BACKUP_DIR.iterdir() if p.is_dir()), reverse=True):
        candidate = folder / f"{name}.csv"
        if candidate.exists():
            shutil.copy2(candidate, table_path(name))
            return True
    return False


def init_storage():
    """Create the data folder and any missing CSV files (safe to call often)."""
    with locked():
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        config.PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        for name, fields in SCHEMAS.items():
            if not table_path(name).exists():
                _write_atomic(table_path(name), fields, [])
        backup_if_needed()


# --------------------------------------------------------------- read/write
def read_table(name: str) -> list:
    """Return a table as a list of dicts (all values are strings)."""
    fields = SCHEMAS[name]
    with locked():
        path = table_path(name)
        if not path.exists():
            _write_atomic(path, fields, [])
            return []
        for attempt in (1, 2):
            try:
                with open(path, newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    header = reader.fieldnames or []
                    if header and not set(header) & set(fields):
                        raise csv.Error("unexpected header")
                    return [{k: (row.get(k) or "") for k in fields} for row in reader]
            except (csv.Error, UnicodeDecodeError, OSError):
                if attempt == 1 and restore_from_backup(name):
                    continue  # try again with the restored file
                raise StorageError(f"{path.name} is damaged and no backup was found.")
    return []


def write_table(name: str, rows: list):
    fields = SCHEMAS[name]
    with locked():
        backup_if_needed()
        _write_atomic(table_path(name), fields, rows)


def insert(name: str, row: dict) -> dict:
    with locked():
        rows = read_table(name)
        rows.append(row)
        write_table(name, rows)
    return row


def insert_many(name: str, new_rows: list):
    with locked():
        rows = read_table(name)
        rows.extend(new_rows)
        write_table(name, rows)


def update_where(name: str, predicate, changes: dict) -> int:
    count = 0
    with locked():
        rows = read_table(name)
        for row in rows:
            if predicate(row):
                row.update({k: str(v) for k, v in changes.items()})
                count += 1
        if count:
            write_table(name, rows)
    return count


def delete_where(name: str, predicate) -> int:
    with locked():
        rows = read_table(name)
        kept = [r for r in rows if not predicate(r)]
        removed = len(rows) - len(kept)
        if removed:
            write_table(name, kept)
    return removed


def to_bool(value) -> bool:
    return str(value).strip().lower() in ("true", "1", "yes")


def parse_date(text) -> date:
    return datetime.strptime(str(text)[:10], "%Y-%m-%d").date()
