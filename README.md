# Perfumería Lamus — Maison Ledger

Flask + SQLite debt, payment, and customer-account system for Perfumería Lamus,
redesigned as a premium retail-finance ledger: warm porcelain paper, hairline
bronze rules, serif numerals, and a charcoal-noir navigation cabinet.

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export INITIAL_ADMIN_PASSWORD='choose-a-private-password'
export INITIAL_ADMIN_SECURITY_ANSWER='choose-a-private-recovery-answer'
.venv/bin/python app.py
```

Open `http://127.0.0.1:5001`.

On a brand-new database, the first-run environment values create the owner
account. Both private values must be at least 12 and 8 characters respectively.
They are only used when there are no users yet.

- Username defaults to `admin`. Override it with `INITIAL_ADMIN_USERNAME`.
- Owner name defaults to `Store Owner`. Override it with `INITIAL_ADMIN_NAME`.
- The recovery question can be overridden with `INITIAL_ADMIN_SECURITY_QUESTION`.
- Set `SECRET_KEY` in the environment if desired. Otherwise the app creates a
  strong machine-local key under the ignored `instance/` directory.

Never commit the SQLite database, `.env` files, or the generated `instance/`
directory. They contain business data or private authentication material.

## Sections

- **Dashboard** — outstanding balance, overdue total, collected today, new credit today, customer finder, attention list, house accounts.
- **Overdue accounts** — credit sales past their due date, or unpaid for 30+ days when no due date was set.
- **Customers / Vendors** — searchable, filterable registries with lifetime totals and quick actions.
- **Customer / vendor accounts** — full ledger, live balance previews when recording credit sales and payments, overpayment prevention, FIFO partial payments.
- **Bank** — Bancolombia balance movements with notes.
- **Reports** — printable business overview plus per-account A4 statements with letterhead, totals, and signature lines.

## Terminology

One vocabulary everywhere: **Credit sale** (customer buys on credit), **Payment**
(money received/sent), **Balance due** (customer owes), **Payable** (store owes a
vendor), **Overdue** (past due date, or older than 30 days without one).

## Data notes

- Currency is COP, formatted `$1.234.567`.
- `ledger.due_date` is optional; when empty, overdue uses the 30-day aging window
  (`OVERDUE_AGING_DAYS` in `database.py`).
- All schema changes are additive; existing tables, columns, and records are untouched.
