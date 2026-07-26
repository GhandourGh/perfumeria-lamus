import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash


DATABASE = os.environ.get("PERFUMERIA_DB", "perfumeria_lamus.db")


@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_security_answer(answer):
    return (answer or "").strip().casefold()


def init_db():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'owner',
                is_active INTEGER DEFAULT 1,
                security_question TEXT,
                security_answer_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                is_active INTEGER DEFAULT 1,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL REFERENCES customers(id),
                entry_type TEXT NOT NULL CHECK(entry_type IN ('NEW_DEBT','PAYMENT','ADJUSTMENT','REFUND','WRITE_OFF','VOID')),
                amount REAL NOT NULL,
                balance_after REAL,
                description TEXT,
                notes TEXT,
                payment_method TEXT CHECK(payment_method IN ('CASH','CARD','CHECK','BANK_TRANSFER','SPLIT','CREDIT') OR payment_method IS NULL),
                reference_id INTEGER REFERENCES ledger(id),
                remaining_amount REAL,
                payment_status TEXT DEFAULT 'OPEN' CHECK(payment_status IN ('OPEN','PARTIAL','PAID')),
                created_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_voided INTEGER DEFAULT 0,
                voided_by INTEGER REFERENCES users(id),
                voided_at TIMESTAMP,
                void_reason TEXT,
                is_deleted INTEGER DEFAULT 0,
                deleted_at TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS ledger_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ledger_id INTEGER NOT NULL REFERENCES ledger(id),
                product_name TEXT NOT NULL,
                price REAL NOT NULL,
                quantity INTEGER DEFAULT 1
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS vendors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                is_active INTEGER DEFAULT 1,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS vendor_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vendor_id INTEGER NOT NULL REFERENCES vendors(id),
                entry_type TEXT NOT NULL CHECK(entry_type IN ('NEW_PURCHASE','PAYMENT_MADE','ADJUSTMENT','REFUND','VOID')),
                amount REAL NOT NULL,
                balance_after REAL,
                description TEXT,
                notes TEXT,
                payment_method TEXT CHECK(payment_method IN ('CASH','CARD','CHECK','BANK_TRANSFER','SPLIT') OR payment_method IS NULL),
                reference_id INTEGER REFERENCES vendor_ledger(id),
                remaining_amount REAL,
                payment_status TEXT DEFAULT 'OPEN' CHECK(payment_status IN ('OPEN','PARTIAL','PAID')),
                created_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_voided INTEGER DEFAULT 0,
                voided_by INTEGER REFERENCES users(id),
                voided_at TIMESTAMP,
                void_reason TEXT,
                is_deleted INTEGER DEFAULT 0,
                deleted_at TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS vendor_ledger_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vendor_ledger_id INTEGER NOT NULL REFERENCES vendor_ledger(id),
                product_name TEXT NOT NULL,
                price REAL NOT NULL,
                quantity INTEGER DEFAULT 1
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS bank_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bank_name TEXT NOT NULL DEFAULT 'Bancolombia',
                account_label TEXT,
                currency TEXT DEFAULT 'COP',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS bank_balance_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bank_account_id INTEGER NOT NULL REFERENCES bank_accounts(id),
                balance REAL NOT NULL,
                change_amount REAL DEFAULT 0,
                change_type TEXT DEFAULT 'SET' CHECK(change_type IN ('SET','ADD','REMOVE')),
                note TEXT,
                recorded_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        _ensure_column(c, "bank_balance_log", "change_amount", "REAL DEFAULT 0")
        _ensure_column(c, "bank_balance_log", "change_type", "TEXT DEFAULT 'SET'")
        _ensure_column(c, "ledger", "due_date", "TIMESTAMP")
        c.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                table_name TEXT,
                record_id INTEGER,
                new_values TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("INSERT OR IGNORE INTO bank_accounts (id, bank_name, account_label, currency) VALUES (1, 'Bancolombia', 'Main account', 'COP')")
        c.execute("SELECT COUNT(*) FROM users")
        if c.fetchone()[0] == 0:
            initial_password = os.environ.get("INITIAL_ADMIN_PASSWORD", "")
            recovery_answer = os.environ.get("INITIAL_ADMIN_SECURITY_ANSWER", "")
            if len(initial_password) < 12:
                raise RuntimeError(
                    "First run requires INITIAL_ADMIN_PASSWORD with at least 12 characters."
                )
            if len(recovery_answer.strip()) < 8:
                raise RuntimeError(
                    "First run requires INITIAL_ADMIN_SECURITY_ANSWER with at least 8 characters."
                )
            c.execute("""
                INSERT INTO users (username, password_hash, full_name, role, security_question, security_answer_hash)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                os.environ.get("INITIAL_ADMIN_USERNAME", "admin").strip() or "admin",
                generate_password_hash(initial_password),
                os.environ.get("INITIAL_ADMIN_NAME", "Store Owner").strip() or "Store Owner",
                "owner",
                os.environ.get("INITIAL_ADMIN_SECURITY_QUESTION", "What is your private recovery phrase?"),
                generate_password_hash(normalize_security_answer(recovery_answer)),
            ))
        conn.commit()


def _ensure_column(cursor, table, column, definition):
    existing = [row["name"] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def authenticate_user(username, password):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            return dict(row)
        return None


def get_user(user_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_user_by_username(username):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)).fetchone()
        return dict(row) if row else None


def verify_security_answer(user_id, answer):
    user = get_user(user_id)
    if not user or not user.get("security_answer_hash"):
        return False
    return check_password_hash(user["security_answer_hash"], normalize_security_answer(answer))


def change_password(user_id, new_password):
    with get_db() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new_password), user_id))
        conn.commit()


def list_people(table, balance_func):
    with get_db() as conn:
        rows = [dict(r) for r in conn.execute(f"SELECT * FROM {table} WHERE is_active = 1 ORDER BY name").fetchall()]
    for row in rows:
        row["balance"] = balance_func(row["id"])
    return rows


def add_customer(name, phone=None, notes=None):
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO customers (name, phone, notes)
            VALUES (?, ?, ?)
        """, (name, phone, notes))
        conn.commit()
        return cur.lastrowid


def get_customer(customer_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        return dict(row) if row else None


def update_customer(customer_id, name, phone=None, notes=None):
    with get_db() as conn:
        conn.execute("""
            UPDATE customers SET name = ?, phone = ?, notes = ?
            WHERE id = ?
        """, (name, phone, notes, customer_id))
        conn.commit()


def archive_customer(customer_id, user_id=None):
    """Soft-hide a customer — drops out of every list/overview (they filter
    is_active = 1) while the ledger history is preserved."""
    with get_db() as conn:
        conn.execute("UPDATE customers SET is_active = 0 WHERE id = ?", (customer_id,))
        log_audit(user_id, "ARCHIVE_CUSTOMER", "customers", customer_id, None, conn)
        conn.commit()


def get_customers_with_debt():
    return list_people("customers", get_customer_balance)


def add_vendor(name, phone=None, notes=None):
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO vendors (name, phone, notes)
            VALUES (?, ?, ?)
        """, (name, phone, notes))
        conn.commit()
        return cur.lastrowid


def get_vendor(vendor_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
        return dict(row) if row else None


def update_vendor(vendor_id, name, phone=None, notes=None):
    with get_db() as conn:
        conn.execute("""
            UPDATE vendors SET name = ?, phone = ?, notes = ?
            WHERE id = ?
        """, (name, phone, notes, vendor_id))
        conn.commit()


def archive_vendor(vendor_id, user_id=None):
    """Soft-hide a vendor while preserving their ledger history."""
    with get_db() as conn:
        conn.execute("UPDATE vendors SET is_active = 0 WHERE id = ?", (vendor_id,))
        log_audit(user_id, "ARCHIVE_VENDOR", "vendors", vendor_id, None, conn)
        conn.commit()


def get_vendors_with_balance():
    return list_people("vendors", get_vendor_balance)


def get_customer_balance(customer_id):
    with get_db() as conn:
        row = conn.execute("""
            SELECT COALESCE(SUM(CASE
                WHEN entry_type IN ('NEW_DEBT','ADJUSTMENT') THEN amount
                WHEN entry_type IN ('PAYMENT','WRITE_OFF','REFUND') THEN -amount
                ELSE 0 END), 0) AS balance
            FROM ledger
            WHERE customer_id = ? AND is_voided = 0 AND is_deleted = 0
        """, (customer_id,)).fetchone()
        return float(row["balance"] or 0)


def _apply_fifo_for_payment(cur, customer_id, payment_amount):
    remaining = float(payment_amount)
    debts = cur.execute("""
        SELECT id, remaining_amount FROM ledger
        WHERE customer_id = ? AND entry_type = 'NEW_DEBT'
          AND payment_status IN ('OPEN','PARTIAL') AND remaining_amount > 0
          AND is_voided = 0 AND is_deleted = 0
        ORDER BY created_at ASC, id ASC
    """, (customer_id,)).fetchall()
    for debt in debts:
        if remaining <= 0:
            break
        applied = min(remaining, float(debt["remaining_amount"]))
        new_remaining = round(float(debt["remaining_amount"]) - applied, 2)
        status = "PAID" if new_remaining <= 0 else "PARTIAL"
        cur.execute("UPDATE ledger SET remaining_amount = ?, payment_status = ? WHERE id = ?", (max(new_remaining, 0), status, debt["id"]))
        remaining = round(remaining - applied, 2)


def add_debt(customer_id, items, description=None, notes=None, user_id=None, due_date=None):
    total = _items_total(items)
    with get_db() as conn:
        cur = conn.cursor()
        balance = get_customer_balance(customer_id) + total
        cur.execute("""
            INSERT INTO ledger (customer_id, entry_type, amount, balance_after, description, notes, created_by, created_at, remaining_amount, payment_status, due_date)
            VALUES (?, 'NEW_DEBT', ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)
        """, (customer_id, total, balance, description, notes, user_id, now(), total, due_date))
        ledger_id = cur.lastrowid
        for item in items:
            cur.execute("""
                INSERT INTO ledger_items (ledger_id, product_name, price, quantity) VALUES (?, ?, ?, ?)
            """, (ledger_id, item["product_name"], float(item["price"]), int(item.get("quantity", 1))))
        log_audit(user_id, "ADD_CUSTOMER_DEBT", "ledger", ledger_id, f"Amount: {total}", conn)
        conn.commit()
        return ledger_id


def add_payment(customer_id, amount, payment_method="CASH", notes=None, user_id=None):
    amount = float(amount)
    current = get_customer_balance(customer_id)
    if amount <= 0:
        raise ValueError("Payment must be positive")
    if current <= 0:
        raise ValueError("Customer has no outstanding balance")
    if amount > current:
        raise ValueError("Payment exceeds customer balance")
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ledger (customer_id, entry_type, amount, balance_after, payment_method, notes, created_by, created_at)
            VALUES (?, 'PAYMENT', ?, ?, ?, ?, ?, ?)
        """, (customer_id, amount, current - amount, payment_method, notes, user_id, now()))
        ledger_id = cur.lastrowid
        _apply_fifo_for_payment(cur, customer_id, amount)
        log_audit(user_id, "ADD_CUSTOMER_PAYMENT", "ledger", ledger_id, f"Amount: {amount}", conn)
        conn.commit()
        return ledger_id


def get_customer_ledger(customer_id):
    with get_db() as conn:
        rows = [dict(r) for r in conn.execute("""
            SELECT * FROM ledger
            WHERE customer_id = ? AND is_deleted = 0
            ORDER BY created_at DESC, id DESC
        """, (customer_id,)).fetchall()]
        for row in rows:
            row["items"] = [dict(i) for i in conn.execute("SELECT * FROM ledger_items WHERE ledger_id = ?", (row["id"],)).fetchall()]
        return rows


# Signs used to fold an entry into a running balance — matches the balance math
# in get_customer_balance / get_vendor_balance.
_BALANCE_SIGN = {
    "NEW_DEBT": 1, "NEW_PURCHASE": 1, "ADJUSTMENT": 1,
    "PAYMENT": -1, "PAYMENT_MADE": -1, "WRITE_OFF": -1, "REFUND": -1,
}


def _rebuild_balance_after(cur, table, owner_col, owner_id):
    """Recompute the per-row balance_after for the surviving (non-voided) rows."""
    rows = cur.execute(f"""
        SELECT id, entry_type, amount FROM {table}
        WHERE {owner_col} = ? AND is_voided = 0 AND is_deleted = 0
        ORDER BY created_at ASC, id ASC
    """, (owner_id,)).fetchall()
    running = 0.0
    for r in rows:
        running = round(running + _BALANCE_SIGN.get(r["entry_type"], 0) * float(r["amount"]), 2)
        cur.execute(f"UPDATE {table} SET balance_after = ? WHERE id = ?", (running, r["id"]))


def _recompute_customer_ledger(cur, customer_id):
    """After a void, rebuild FIFO payment allocations and the running balance from
    the entries that survive, so the ledger stays internally consistent."""
    cur.execute("""
        UPDATE ledger SET remaining_amount = amount, payment_status = 'OPEN'
        WHERE customer_id = ? AND entry_type = 'NEW_DEBT'
          AND is_voided = 0 AND is_deleted = 0
    """, (customer_id,))
    payments = cur.execute("""
        SELECT amount FROM ledger
        WHERE customer_id = ? AND entry_type = 'PAYMENT'
          AND is_voided = 0 AND is_deleted = 0
        ORDER BY created_at ASC, id ASC
    """, (customer_id,)).fetchall()
    for p in payments:
        _apply_fifo_for_payment(cur, customer_id, p["amount"])
    _rebuild_balance_after(cur, "ledger", "customer_id", customer_id)


def void_customer_entry(entry_id, expected_customer_id=None, user_id=None, reason=None):
    with get_db() as conn:
        cur = conn.cursor()
        row = cur.execute("SELECT * FROM ledger WHERE id = ? AND is_deleted = 0", (entry_id,)).fetchone()
        if row is None or (expected_customer_id is not None and row["customer_id"] != expected_customer_id):
            raise ValueError("Entry not found")
        if row["is_voided"]:
            raise ValueError("This entry is already voided")
        cur.execute("""
            UPDATE ledger SET is_voided = 1, voided_by = ?, voided_at = ?, void_reason = ?
            WHERE id = ?
        """, (user_id, now(), (reason or None), entry_id))
        _recompute_customer_ledger(cur, row["customer_id"])
        log_audit(user_id, "VOID_CUSTOMER_ENTRY", "ledger", entry_id, reason, conn)
        conn.commit()
        return row["customer_id"]


def get_vendor_balance(vendor_id):
    with get_db() as conn:
        row = conn.execute("""
            SELECT COALESCE(SUM(CASE
                WHEN entry_type IN ('NEW_PURCHASE','ADJUSTMENT') THEN amount
                WHEN entry_type IN ('PAYMENT_MADE','REFUND') THEN -amount
                ELSE 0 END), 0) AS balance
            FROM vendor_ledger
            WHERE vendor_id = ? AND is_voided = 0 AND is_deleted = 0
        """, (vendor_id,)).fetchone()
        return float(row["balance"] or 0)


def _apply_fifo_for_vendor_payment(cur, vendor_id, payment_amount):
    remaining = float(payment_amount)
    purchases = cur.execute("""
        SELECT id, remaining_amount FROM vendor_ledger
        WHERE vendor_id = ? AND entry_type = 'NEW_PURCHASE'
          AND payment_status IN ('OPEN','PARTIAL') AND remaining_amount > 0
          AND is_voided = 0 AND is_deleted = 0
        ORDER BY created_at ASC, id ASC
    """, (vendor_id,)).fetchall()
    for purchase in purchases:
        if remaining <= 0:
            break
        applied = min(remaining, float(purchase["remaining_amount"]))
        new_remaining = round(float(purchase["remaining_amount"]) - applied, 2)
        status = "PAID" if new_remaining <= 0 else "PARTIAL"
        cur.execute("UPDATE vendor_ledger SET remaining_amount = ?, payment_status = ? WHERE id = ?", (max(new_remaining, 0), status, purchase["id"]))
        remaining = round(remaining - applied, 2)


def add_purchase(vendor_id, items, description=None, notes=None, user_id=None):
    total = _items_total(items)
    with get_db() as conn:
        cur = conn.cursor()
        balance = get_vendor_balance(vendor_id) + total
        cur.execute("""
            INSERT INTO vendor_ledger (vendor_id, entry_type, amount, balance_after, description, notes, created_by, created_at, remaining_amount, payment_status)
            VALUES (?, 'NEW_PURCHASE', ?, ?, ?, ?, ?, ?, ?, 'OPEN')
        """, (vendor_id, total, balance, description, notes, user_id, now(), total))
        ledger_id = cur.lastrowid
        for item in items:
            cur.execute("""
                INSERT INTO vendor_ledger_items (vendor_ledger_id, product_name, price, quantity) VALUES (?, ?, ?, ?)
            """, (ledger_id, item["product_name"], float(item["price"]), int(item.get("quantity", 1))))
        log_audit(user_id, "ADD_VENDOR_PURCHASE", "vendor_ledger", ledger_id, f"Amount: {total}", conn)
        conn.commit()
        return ledger_id


def add_vendor_payment(vendor_id, amount, payment_method="CASH", notes=None, user_id=None):
    amount = float(amount)
    current = get_vendor_balance(vendor_id)
    if amount <= 0:
        raise ValueError("Payment must be positive")
    if current <= 0:
        raise ValueError("Vendor has no outstanding payable")
    if amount > current:
        raise ValueError("Payment exceeds vendor balance")
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO vendor_ledger (vendor_id, entry_type, amount, balance_after, payment_method, notes, created_by, created_at)
            VALUES (?, 'PAYMENT_MADE', ?, ?, ?, ?, ?, ?)
        """, (vendor_id, amount, current - amount, payment_method, notes, user_id, now()))
        ledger_id = cur.lastrowid
        _apply_fifo_for_vendor_payment(cur, vendor_id, amount)
        if payment_method == "BANK_TRANSFER":
            cur.execute("""
                INSERT INTO bank_balance_log (bank_account_id, balance, change_amount, change_type, note, recorded_by, created_at)
                VALUES (1, ?, ?, 'REMOVE', ?, ?, ?)
            """, (_get_current_bank_balance(cur) - amount, amount, f"Auto: vendor payment #{ledger_id}", user_id, now()))
        log_audit(user_id, "ADD_VENDOR_PAYMENT", "vendor_ledger", ledger_id, f"Amount: {amount}", conn)
        conn.commit()
        return ledger_id


def get_vendor_ledger(vendor_id):
    with get_db() as conn:
        rows = [dict(r) for r in conn.execute("""
            SELECT * FROM vendor_ledger
            WHERE vendor_id = ? AND is_deleted = 0
            ORDER BY created_at DESC, id DESC
        """, (vendor_id,)).fetchall()]
        for row in rows:
            row["items"] = [dict(i) for i in conn.execute("SELECT * FROM vendor_ledger_items WHERE vendor_ledger_id = ?", (row["id"],)).fetchall()]
        return rows


def _recompute_vendor_ledger(cur, vendor_id):
    """Vendor-side twin of _recompute_customer_ledger."""
    cur.execute("""
        UPDATE vendor_ledger SET remaining_amount = amount, payment_status = 'OPEN'
        WHERE vendor_id = ? AND entry_type = 'NEW_PURCHASE'
          AND is_voided = 0 AND is_deleted = 0
    """, (vendor_id,))
    payments = cur.execute("""
        SELECT amount FROM vendor_ledger
        WHERE vendor_id = ? AND entry_type = 'PAYMENT_MADE'
          AND is_voided = 0 AND is_deleted = 0
        ORDER BY created_at ASC, id ASC
    """, (vendor_id,)).fetchall()
    for p in payments:
        _apply_fifo_for_vendor_payment(cur, vendor_id, p["amount"])
    _rebuild_balance_after(cur, "vendor_ledger", "vendor_id", vendor_id)


def void_vendor_entry(entry_id, expected_vendor_id=None, user_id=None, reason=None):
    with get_db() as conn:
        cur = conn.cursor()
        row = cur.execute("SELECT * FROM vendor_ledger WHERE id = ? AND is_deleted = 0", (entry_id,)).fetchone()
        if row is None or (expected_vendor_id is not None and row["vendor_id"] != expected_vendor_id):
            raise ValueError("Entry not found")
        if row["is_voided"]:
            raise ValueError("This entry is already voided")
        cur.execute("""
            UPDATE vendor_ledger SET is_voided = 1, voided_by = ?, voided_at = ?, void_reason = ?
            WHERE id = ?
        """, (user_id, now(), (reason or None), entry_id))
        # A bank-transfer vendor payment deducted from the bank; reverse that.
        if row["entry_type"] == "PAYMENT_MADE" and row["payment_method"] == "BANK_TRANSFER":
            amount = float(row["amount"])
            cur.execute("""
                INSERT INTO bank_balance_log (bank_account_id, balance, change_amount, change_type, note, recorded_by, created_at)
                VALUES (1, ?, ?, 'ADD', ?, ?, ?)
            """, (_get_current_bank_balance(cur) + amount, amount,
                  f"Reversal: voided vendor payment #{entry_id}", user_id, now()))
        _recompute_vendor_ledger(cur, row["vendor_id"])
        log_audit(user_id, "VOID_VENDOR_ENTRY", "vendor_ledger", entry_id, reason, conn)
        conn.commit()
        return row["vendor_id"]


def _items_total(items):
    if not items:
        raise ValueError("At least one line item is required")
    total = 0.0
    for item in items:
        price = float(item.get("price") or 0)
        qty = int(item.get("quantity") or 1)
        name = (item.get("product_name") or "").strip()
        if not name:
            raise ValueError("Each item needs a name")
        if price <= 0 or qty <= 0:
            raise ValueError("Item price and quantity must be positive")
        total += price * qty
    return round(total, 2)


def _get_current_bank_balance(cur):
    row = cur.execute("""
        SELECT balance FROM bank_balance_log
        WHERE bank_account_id = 1
        ORDER BY created_at DESC, id DESC
        LIMIT 1
    """).fetchone()
    return float(row["balance"] or 0) if row else 0.0


def get_current_bank_balance(bank_account_id=1):
    with get_db() as conn:
        return _get_current_bank_balance(conn.cursor())


def add_bank_balance_entry(balance, note=None, user_id=None, bank_account_id=1):
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO bank_balance_log (bank_account_id, balance, change_amount, change_type, note, recorded_by, created_at)
            VALUES (?, ?, 0, 'SET', ?, ?, ?)
        """, (bank_account_id, float(balance), note, user_id, now()))
        conn.commit()
        return cur.lastrowid


def change_bank_balance(amount, change_type, note=None, user_id=None, bank_account_id=1):
    amount = float(amount)
    if amount <= 0:
        raise ValueError("Amount must be positive")
    if change_type not in {"ADD", "REMOVE"}:
        raise ValueError("Invalid bank action")
    if change_type == "REMOVE" and not (note or "").strip():
        raise ValueError("A note is required when removing money")
    with get_db() as conn:
        cur = conn.cursor()
        current = _get_current_bank_balance(cur)
        new_balance = current + amount if change_type == "ADD" else current - amount
        cur.execute("""
            INSERT INTO bank_balance_log (bank_account_id, balance, change_amount, change_type, note, recorded_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (bank_account_id, new_balance, amount, change_type, note, user_id, now()))
        conn.commit()
        return cur.lastrowid


def get_bank_balance_history(bank_account_id=1, limit=50):
    with get_db() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT b.*, u.full_name AS recorded_by_name
            FROM bank_balance_log b
            LEFT JOIN users u ON u.id = b.recorded_by
            WHERE b.bank_account_id = ?
            ORDER BY b.created_at DESC, b.id DESC
            LIMIT ?
        """, (bank_account_id, limit)).fetchall()]


def get_recent_activity(limit=12, kind=None):
    """Newest ledger entries across both books. Pass kind='customer' or
    kind='vendor' to restrict to a single workspace; None returns both."""
    customer_select = """
        SELECT l.created_at AS created_at, c.name AS name, l.entry_type AS entry_type,
               l.amount AS amount, 'customer' AS kind, c.id AS person_id
        FROM ledger l JOIN customers c ON c.id = l.customer_id
        WHERE l.is_voided = 0 AND l.is_deleted = 0
    """
    vendor_select = """
        SELECT vl.created_at AS created_at, v.name AS name, vl.entry_type AS entry_type,
               vl.amount AS amount, 'vendor' AS kind, v.id AS person_id
        FROM vendor_ledger vl JOIN vendors v ON v.id = vl.vendor_id
        WHERE vl.is_voided = 0 AND vl.is_deleted = 0
    """
    if kind == "customer":
        inner = customer_select
    elif kind == "vendor":
        inner = vendor_select
    else:
        inner = customer_select + "\n            UNION ALL\n" + vendor_select
    with get_db() as conn:
        rows = [dict(r) for r in conn.execute(f"""
            SELECT * FROM (
{inner}
            )
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()]
        return rows


def get_dashboard_totals():
    customers = get_customers_with_debt()
    vendors = get_vendors_with_balance()
    return {
        "total_receivable": sum(max(c["balance"], 0) for c in customers),
        "total_payable": sum(max(v["balance"], 0) for v in vendors),
        "bank_balance": get_current_bank_balance(),
        "customer_count": len(customers),
        "vendor_count": len(vendors),
    }


# --- Read-only overview queries (used by the redesigned interface). ---
# These derive everything from the existing ledger rules and never write data.

def get_customers_overview():
    """All active customers with lifetime totals, balance, and last activity."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT c.*,
              COALESCE(SUM(CASE WHEN l.is_voided = 0 AND l.is_deleted = 0
                    AND l.entry_type IN ('NEW_DEBT','ADJUSTMENT') THEN l.amount END), 0) AS total_debt,
              COALESCE(SUM(CASE WHEN l.is_voided = 0 AND l.is_deleted = 0
                    AND l.entry_type IN ('PAYMENT','WRITE_OFF','REFUND') THEN l.amount END), 0) AS total_paid,
              MAX(CASE WHEN l.entry_type = 'PAYMENT' AND l.is_voided = 0 AND l.is_deleted = 0
                    THEN l.created_at END) AS last_payment_at,
              MAX(CASE WHEN l.entry_type = 'NEW_DEBT' AND l.is_voided = 0 AND l.is_deleted = 0
                    THEN l.created_at END) AS last_debt_at,
              MAX(CASE WHEN l.is_voided = 0 AND l.is_deleted = 0 THEN l.created_at END) AS last_activity_at
            FROM customers c
            LEFT JOIN ledger l ON l.customer_id = c.id
            WHERE c.is_active = 1
            GROUP BY c.id
            ORDER BY c.name COLLATE NOCASE
        """).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["balance"] = round(float(item["total_debt"]) - float(item["total_paid"]), 2)
        result.append(item)
    return result


def get_customer_summary(customer_id):
    """Account header numbers for one customer, consistent with get_customer_balance."""
    for row in get_customers_overview():
        if row["id"] == customer_id:
            return row
    customer = get_customer(customer_id)
    if customer:
        customer.update({"total_debt": 0, "total_paid": 0,
                         "balance": 0, "last_payment_at": None, "last_debt_at": None,
                         "last_activity_at": None})
    return customer


def get_vendors_overview():
    """All active vendors with lifetime totals, balance, and last activity."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT v.*,
              COALESCE(SUM(CASE WHEN vl.is_voided = 0 AND vl.is_deleted = 0
                    AND vl.entry_type IN ('NEW_PURCHASE','ADJUSTMENT') THEN vl.amount END), 0) AS total_purchased,
              COALESCE(SUM(CASE WHEN vl.is_voided = 0 AND vl.is_deleted = 0
                    AND vl.entry_type IN ('PAYMENT_MADE','REFUND') THEN vl.amount END), 0) AS total_paid,
              MAX(CASE WHEN vl.entry_type = 'PAYMENT_MADE' AND vl.is_voided = 0 AND vl.is_deleted = 0
                    THEN vl.created_at END) AS last_payment_at,
              MAX(CASE WHEN vl.is_voided = 0 AND vl.is_deleted = 0 THEN vl.created_at END) AS last_activity_at
            FROM vendors v
            LEFT JOIN vendor_ledger vl ON vl.vendor_id = v.id
            WHERE v.is_active = 1
            GROUP BY v.id
            ORDER BY v.name COLLATE NOCASE
        """).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["balance"] = round(float(item["total_purchased"]) - float(item["total_paid"]), 2)
        result.append(item)
    return result


def get_dashboard_stats():
    """Everything the dashboard shows, derived from live ledger data."""
    customers = get_customers_overview()
    vendors = get_vendors_overview()
    today = datetime.now().strftime("%Y-%m-%d")
    with get_db() as conn:
        today_row = conn.execute("""
            SELECT
              COALESCE(SUM(CASE WHEN entry_type = 'PAYMENT' THEN amount END), 0) AS collected_today,
              COALESCE(SUM(CASE WHEN entry_type = 'PAYMENT' THEN 1 ELSE 0 END), 0) AS payments_today,
              COALESCE(SUM(CASE WHEN entry_type = 'NEW_DEBT' THEN amount END), 0) AS debt_added_today,
              COALESCE(SUM(CASE WHEN entry_type = 'NEW_DEBT' THEN 1 ELSE 0 END), 0) AS debts_today
            FROM ledger
            WHERE is_voided = 0 AND is_deleted = 0 AND date(created_at) = ?
        """, (today,)).fetchone()
    with_balance = [c for c in customers if c["balance"] > 0]
    return {
        "total_outstanding": sum(c["balance"] for c in with_balance),
        "total_payable": sum(max(v["balance"], 0) for v in vendors),
        "bank_balance": get_current_bank_balance(),
        "customer_count": len(customers),
        "vendor_count": len(vendors),
        "customers_with_balance": len(with_balance),
        "collected_today": float(today_row["collected_today"]),
        "payments_today": int(today_row["payments_today"]),
        "debt_added_today": float(today_row["debt_added_today"]),
        "debts_today": int(today_row["debts_today"]),
        "largest_balances": sorted(with_balance, key=lambda c: c["balance"], reverse=True)[:5],
    }


def log_audit(user_id, action, table_name, record_id, new_values=None, conn=None):
    target = conn or sqlite3.connect(DATABASE)
    target.execute("""
        INSERT INTO audit_log (user_id, action, table_name, record_id, new_values)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, action, table_name, record_id, new_values))
    if conn is None:
        target.commit()
        target.close()


def seed_demo_data():
    customers = [
        ("Maria Gomez", "300 111 2233", "Pays every Friday"),
        ("Carlos Rivera", "301 555 0198", "Prefers cash"),
        ("Ana Torres", None, "Family account"),
        ("Julian Perez", "310 882 4412", None),
        ("Sofia Martinez", "320 444 7811", "Regular fragrance buyer"),
    ]
    vendors = [
        ("Aroma Imports", "601 222 1000", "Main supplier"),
        ("Belleza Mayorista", "601 333 1400", "Monthly invoices"),
        ("Fragancias Andinas", None, "Call before large orders"),
        ("Luxe Distribution", "601 777 9090", None),
    ]
    with get_db() as conn:
        if conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0:
            for name, phone, notes in customers:
                conn.execute("INSERT INTO customers (name, phone, notes) VALUES (?, ?, ?)", (name, phone, notes))
        if conn.execute("SELECT COUNT(*) FROM vendors").fetchone()[0] == 0:
            for name, phone, notes in vendors:
                conn.execute("INSERT INTO vendors (name, phone, notes) VALUES (?, ?, ?)", (name, phone, notes))
        if conn.execute("SELECT COUNT(*) FROM bank_balance_log").fetchone()[0] == 0:
            conn.execute("""
                INSERT INTO bank_balance_log (bank_account_id, balance, change_amount, change_type, note, created_at)
                VALUES (1, 2500000, 0, 'SET', 'Opening test balance', ?)
            """, (now(),))
        conn.commit()

    customer_rows = get_customers_with_debt()
    vendor_rows = get_vendors_with_balance()
    if customer_rows and all(row["balance"] == 0 for row in customer_rows):
        add_debt(customer_rows[0]["id"], [{"product_name": "Sale", "price": 180000, "quantity": 1}], notes="Test customer debt")
        add_debt(customer_rows[1]["id"], [{"product_name": "Sale", "price": 95000, "quantity": 1}], notes="Test customer debt")
        add_payment(customer_rows[0]["id"], 50000, "CASH", notes="Partial test payment")
    if vendor_rows and all(row["balance"] == 0 for row in vendor_rows):
        add_purchase(vendor_rows[0]["id"], [{"product_name": "Supplier purchase", "price": 640000, "quantity": 1}], notes="Test vendor purchase")
        add_purchase(vendor_rows[1]["id"], [{"product_name": "Supplier purchase", "price": 380000, "quantity": 1}], notes="Test vendor purchase")
        add_vendor_payment(vendor_rows[0]["id"], 140000, "BANK_TRANSFER", notes="Partial test payment")
