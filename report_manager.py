import csv
import io
import sqlite3

import database as db


ACTION_LABELS = {
    "LOGIN": "Signed in",
    "LOGOUT": "Signed out",
    "PASSWORD_CHANGED": "Changed password",
    "PASSWORD_RESET": "Reset forgotten password",
    "RECOVERY_CODE_CREATED": "Created recovery code",
    "ADD_CUSTOMER": "Added customer",
    "EDIT_CUSTOMER": "Edited customer",
    "ARCHIVE_CUSTOMER": "Archived customer",
    "ADD_CUSTOMER_DEBT": "Recorded customer credit sale",
    "ADD_CUSTOMER_PAYMENT": "Recorded customer payment",
    "CUSTOMER_WRITEOFF": "Recorded customer write-off",
    "EDIT_CUSTOMER_ENTRY": "Edited customer ledger entry",
    "VOID_CUSTOMER_ENTRY": "Voided customer ledger entry",
    "ADD_VENDOR": "Added vendor",
    "EDIT_VENDOR": "Edited vendor",
    "ARCHIVE_VENDOR": "Archived vendor",
    "ADD_VENDOR_PURCHASE": "Recorded vendor purchase",
    "ADD_VENDOR_PAYMENT": "Recorded vendor payment",
    "VENDOR_CREDIT": "Recorded vendor credit",
    "EDIT_VENDOR_ENTRY": "Edited vendor ledger entry",
    "VOID_VENDOR_ENTRY": "Voided vendor ledger entry",
    "BANK_CHANGE": "Changed bank balance",
    "BACKUP_CREATED": "Downloaded complete backup",
    "RESTORE_COMPLETED": "Restored complete backup",
}


def get_action_events(date_from="", date_to="", action=""):
    clauses = []
    values = []
    if date_from:
        clauses.append("date(a.created_at) >= date(?)")
        values.append(date_from)
    if date_to:
        clauses.append("date(a.created_at) <= date(?)")
        values.append(date_to)
    if action:
        clauses.append("a.action = ?")
        values.append(action)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with sqlite3.connect(db.DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"""
            SELECT a.*,
              CASE WHEN u.role = 'owner' THEN 'BU SALIM'
                   ELSE COALESCE(u.full_name, u.username, 'System') END AS owner_name,
              CASE
                WHEN a.table_name = 'customers' THEN (SELECT name FROM customers WHERE id = a.record_id)
                WHEN a.table_name = 'vendors' THEN (SELECT name FROM vendors WHERE id = a.record_id)
                WHEN a.table_name = 'ledger' THEN (
                  SELECT c.name FROM ledger l JOIN customers c ON c.id = l.customer_id WHERE l.id = a.record_id
                )
                WHEN a.table_name = 'vendor_ledger' THEN (
                  SELECT v.name FROM vendor_ledger vl JOIN vendors v ON v.id = vl.vendor_id WHERE vl.id = a.record_id
                )
              END AS account_name
            FROM audit_log a
            LEFT JOIN users u ON u.id = a.user_id
            {where}
            ORDER BY a.created_at DESC, a.id DESC
            LIMIT 2000
        """, values).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["action_label"] = ACTION_LABELS.get(item["action"], item["action"].replace("_", " ").title())
        result.append(item)
    return result


def get_owner_stats(user_id):
    with sqlite3.connect(db.DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("""
            SELECT COUNT(*) AS action_count,
              SUM(CASE WHEN action = 'LOGIN' THEN 1 ELSE 0 END) AS login_count,
              MAX(CASE WHEN action = 'LOGIN' THEN created_at END) AS last_login
            FROM audit_log WHERE user_id = ?
        """, (user_id,)).fetchone()
    return dict(row)


def actions_csv(events, translate=lambda value: value, format_moment=lambda value: value):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([translate(label) for label in ["Date", "Owner", "Action", "Account", "Record type", "Record ID", "Details"]])
    for event in events:
        writer.writerow([
            format_moment(event["created_at"]),
            event["owner_name"],
            translate(event["action_label"]),
            event.get("account_name") or "",
            translate(event.get("table_name") or ""),
            event.get("record_id") or "",
            translate(event.get("new_values") or ""),
        ])
    return output.getvalue()
