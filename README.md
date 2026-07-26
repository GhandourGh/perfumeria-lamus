# Perfumería Lamus — Maison Ledger

Flask + SQLite debt, payment, and customer-account system for Perfumería Lamus,
redesigned as a premium retail-finance ledger: warm porcelain paper, hairline
bronze rules, serif numerals, and a charcoal-noir navigation cabinet.

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export INITIAL_ADMIN_PASSWORD='choose-a-private-password'
.venv/bin/python app.py
```

Open `http://127.0.0.1:5001`.

On a brand-new database, the first-run environment value creates the owner
account. The password must be at least 8 characters. It is only used when there
are no users yet.

- Username defaults to `busalim`. Override it with `INITIAL_ADMIN_USERNAME`.
- Owner name defaults to `BU SALIM`. Override it with `INITIAL_ADMIN_NAME`.
- Set `SECRET_KEY` in the environment if desired. Otherwise the app creates a
  strong machine-local key under the ignored `instance/` directory.

Never commit the SQLite database, `.env` files, or the generated `instance/`
directory. They contain business data or private authentication material.

## Install on a new MacBook

Install Apple's command-line tools and clone the app:

```bash
xcode-select --install
git clone https://github.com/GhandourGh/perfumeria-lamus.git
cd perfumeria-lamus
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

For a fresh empty installation, create the owner and start Lamus:

```bash
export INITIAL_ADMIN_USERNAME='busalim'
export INITIAL_ADMIN_NAME='BU SALIM'
export INITIAL_ADMIN_PASSWORD='choose-a-private-password'
.venv/bin/python app.py
```

Open `http://127.0.0.1:5001`. Keep the Terminal window open while using Lamus.

To move the current store records instead of starting empty, close Lamus on
both computers and copy `perfumeria_lamus.db` from the old app folder into the
same folder on the new MacBook. Also copy the ignored `instance` folder if old
`.lamusbackup` files must remain restorable on the new computer. Never upload
either item to GitHub.

## Sections

- **Dashboard** — outstanding balance, overdue total, collected today, new credit today, customer finder, attention list, house accounts.
- **Overdue accounts** — customer credit sales past their due date and customer
  or vendor balances left unpaid for more than 30 days. Includes filters,
  account badges, ledger status, statements, dashboards, and reports.
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
- `ledger.due_date` is optional. A customer’s chosen due date takes priority;
  otherwise customer debts and vendor purchases use the 30-day aging window
  (`OVERDUE_AGING_DAYS` in `database.py`).
- All schema changes are additive; existing tables, columns, and records are untouched.
