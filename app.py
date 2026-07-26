import os
import secrets
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, session, url_for

import database as db


app = Flask(__name__)


def load_secret_key():
    configured = os.environ.get("SECRET_KEY")
    if configured:
        return configured

    secret_path = Path(app.instance_path) / "secret_key"
    secret_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if secret_path.exists():
        return secret_path.read_text(encoding="utf-8").strip()

    generated = secrets.token_urlsafe(48)
    secret_path.write_text(generated, encoding="utf-8")
    secret_path.chmod(0o600)
    return generated


app.secret_key = load_secret_key()
db.init_db()


def format_cop(amount):
    value = int(round(float(amount or 0)))
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,}".replace(",", ".")


def _parse_stored_dt(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value)[:19], fmt)
        except ValueError:
            continue
    return None


def format_date(value):
    dt = _parse_stored_dt(value)
    return dt.strftime("%d %b %Y") if dt else (value or "—")


def format_datetime(value):
    dt = _parse_stored_dt(value)
    return dt.strftime("%d %b %Y · %H:%M") if dt else (value or "—")


def format_time(value):
    dt = _parse_stored_dt(value)
    return dt.strftime("%H:%M") if dt else ""


app.jinja_env.filters["cop"] = format_cop
app.jinja_env.filters["day"] = format_date
app.jinja_env.filters["moment"] = format_datetime
app.jinja_env.filters["clock"] = format_time


def current_user_id():
    return session.get("user_id")


# The app is split into two workspaces so the customer and vendor books never
# blur together. Every endpoint belongs to one of them, or to the shared
# "office" area (Bank, Reports) reachable from either workspace.
VENDOR_ENDPOINTS = {
    "vendor_overview", "vendors", "vendor_detail", "add_vendor", "edit_vendor",
    "vendor_report", "add_purchase", "add_vendor_payment",
}
OFFICE_ENDPOINTS = {"bank", "reports"}


def resolve_workspace(endpoint):
    return "vendors" if endpoint in VENDOR_ENDPOINTS else "customers"


@app.context_processor
def inject_globals():
    user = db.get_user(current_user_id()) if current_user_id() else None
    endpoint = request.endpoint
    return {
        "current_user": user,
        "today_display": datetime.now().strftime("%d %b %Y"),
        "now_display": datetime.now().strftime("%d %b %Y · %H:%M"),
        "workspace": resolve_workspace(endpoint),
        "nav_office": endpoint in OFFICE_ENDPOINTS,
    }


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = db.authenticate_user(request.form.get("username", ""), request.form.get("password", ""))
        if user:
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    user = None
    username = request.form.get("username") or request.args.get("username")
    if username:
        user = db.get_user_by_username(username)
    if request.method == "POST" and request.form.get("step") == "answer":
        user = db.get_user_by_username(request.form.get("username", ""))
        if user and db.verify_security_answer(user["id"], request.form.get("security_answer", "")):
            session["pw_reset_allowed_for"] = user["id"]
            return redirect(url_for("reset_password"))
        flash("That answer did not match.", "error")
    elif request.method == "POST" and not user:
        flash("No active account found for that username.", "error")
    return render_template("forgot_password.html", user=user, username=username)


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    user_id = session.get("pw_reset_allowed_for")
    if not user_id:
        return redirect(url_for("forgot_password"))
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        else:
            db.change_password(user_id, password)
            session.pop("pw_reset_allowed_for", None)
            flash("Password updated. Please log in.", "success")
            return redirect(url_for("login"))
    return render_template("reset_password.html")


@app.route("/")
@login_required
def dashboard():
    customers = sorted(
        db.get_customers_overview(),
        key=lambda customer: customer["balance"],
        reverse=True,
    )
    return render_template(
        "dashboard.html",
        stats=db.get_dashboard_stats(),
        recent_activity=db.get_recent_activity(limit=10),
        customers=customers,
    )


@app.route("/reports")
@login_required
def reports():
    return render_template(
        "reports.html",
        stats=db.get_dashboard_stats(),
        customers=db.get_customers_overview(),
        vendors=db.get_vendors_overview(),
        bank_balance=db.get_current_bank_balance(),
        bank_history=db.get_bank_balance_history(limit=200),
        recent_activity=db.get_recent_activity(limit=100),
    )


@app.route("/customers/<int:customer_id>/report")
@login_required
def customer_report(customer_id):
    customer = db.get_customer_summary(customer_id)
    return render_template(
        "statement_report.html",
        kind="Customer",
        person=customer,
        balance=db.get_customer_balance(customer_id),
        ledger=db.get_customer_ledger(customer_id),
    )


@app.route("/vendors/<int:vendor_id>/report")
@login_required
def vendor_report(vendor_id):
    vendors = {v["id"]: v for v in db.get_vendors_overview()}
    vendor = vendors.get(vendor_id) or db.get_vendor(vendor_id)
    return render_template(
        "statement_report.html",
        kind="Vendor",
        person=vendor,
        balance=db.get_vendor_balance(vendor_id),
        ledger=db.get_vendor_ledger(vendor_id),
    )


@app.route("/customers")
@login_required
def customers():
    customer_list = sorted(
        db.get_customers_overview(),
        key=lambda customer: customer["balance"],
        reverse=True,
    )
    return render_template("customers.html", customers=customer_list)


@app.route("/customers/add", methods=["GET", "POST"])
@login_required
def add_customer():
    if request.method == "POST":
        new_id = db.add_customer(**person_form(customer=True))
        flash("Customer added.", "success")
        _record_opening_balance("customer", new_id)
        return redirect(url_for("customer_detail", customer_id=new_id))
    return render_template("person_form.html", mode="Add", kind="Customer", action=url_for("add_customer"), person={})


@app.route("/customers/<int:customer_id>/edit", methods=["GET", "POST"])
@login_required
def edit_customer(customer_id):
    customer = db.get_customer(customer_id)
    if request.method == "POST":
        db.update_customer(customer_id, **person_form(customer=True))
        flash("Customer updated.", "success")
        return redirect(url_for("customer_detail", customer_id=customer_id))
    return render_template("person_form.html", mode="Edit", kind="Customer", action=url_for("edit_customer", customer_id=customer_id), person=customer)


@app.route("/customers/<int:customer_id>")
@login_required
def customer_detail(customer_id):
    summary = db.get_customer_summary(customer_id)
    return render_template("customer_detail.html", customer=summary, balance=db.get_customer_balance(customer_id), ledger=db.get_customer_ledger(customer_id))


@app.route("/customers/<int:customer_id>/add-debt", methods=["POST"])
@login_required
def add_debt(customer_id):
    description = (request.form.get("description") or "").strip() or None
    due_date = (request.form.get("due_date") or "").strip() or None
    try:
        db.add_debt(customer_id, parse_money_item(description or "Credit sale"), description, request.form.get("notes"), current_user_id(), due_date=due_date)
        flash("Credit sale recorded.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("customer_detail", customer_id=customer_id))


@app.route("/customers/<int:customer_id>/add-payment", methods=["POST"])
@login_required
def add_payment(customer_id):
    try:
        db.add_payment(customer_id, float(request.form.get("amount") or 0), request.form.get("payment_method") or "CASH", request.form.get("notes"), current_user_id())
        flash("Payment recorded.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("customer_detail", customer_id=customer_id))


@app.route("/customers/<int:customer_id>/ledger/<int:entry_id>/void", methods=["POST"])
@login_required
def void_customer_ledger(customer_id, entry_id):
    try:
        db.void_customer_entry(entry_id, expected_customer_id=customer_id, user_id=current_user_id(),
                               reason=(request.form.get("reason") or "").strip() or None)
        flash("Entry voided. The balance has been recalculated.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("customer_detail", customer_id=customer_id))


@app.route("/customers/<int:customer_id>/archive", methods=["POST"])
@login_required
def archive_customer(customer_id):
    db.archive_customer(customer_id, current_user_id())
    flash("Customer archived.", "success")
    return redirect(url_for("customers"))


@app.route("/vendors/overview")
@login_required
def vendor_overview():
    vendors = db.get_vendors_overview()
    payable = [v for v in vendors if v["balance"] > 0]
    stats = {
        "total_payable": sum(v["balance"] for v in payable),
        "vendor_count": len(vendors),
        "vendors_with_balance": len(payable),
        "total_purchased": sum(v["total_purchased"] for v in vendors),
        "total_paid": sum(v["total_paid"] for v in vendors),
        "bank_balance": db.get_current_bank_balance(),
        "largest_payables": sorted(payable, key=lambda v: v["balance"], reverse=True)[:5],
    }
    return render_template(
        "vendor_overview.html",
        stats=stats,
        vendors=vendors,
        recent_activity=db.get_recent_activity(limit=10, kind="vendor"),
    )


@app.route("/vendors")
@login_required
def vendors():
    return render_template("vendors.html", vendors=db.get_vendors_overview())


@app.route("/vendors/add", methods=["GET", "POST"])
@login_required
def add_vendor():
    if request.method == "POST":
        new_id = db.add_vendor(**person_form(customer=False))
        flash("Vendor added.", "success")
        _record_opening_balance("vendor", new_id)
        return redirect(url_for("vendor_detail", vendor_id=new_id))
    return render_template("person_form.html", mode="Add", kind="Vendor", action=url_for("add_vendor"), person={})


@app.route("/vendors/<int:vendor_id>/edit", methods=["GET", "POST"])
@login_required
def edit_vendor(vendor_id):
    vendor = db.get_vendor(vendor_id)
    if request.method == "POST":
        db.update_vendor(vendor_id, **person_form(customer=False))
        flash("Vendor updated.", "success")
        return redirect(url_for("vendor_detail", vendor_id=vendor_id))
    return render_template("person_form.html", mode="Edit", kind="Vendor", action=url_for("edit_vendor", vendor_id=vendor_id), person=vendor)


@app.route("/vendors/<int:vendor_id>")
@login_required
def vendor_detail(vendor_id):
    vendors_by_id = {v["id"]: v for v in db.get_vendors_overview()}
    vendor = vendors_by_id.get(vendor_id) or db.get_vendor(vendor_id)
    return render_template("vendor_detail.html", vendor=vendor, balance=db.get_vendor_balance(vendor_id), ledger=db.get_vendor_ledger(vendor_id))


@app.route("/vendors/<int:vendor_id>/add-purchase", methods=["POST"])
@login_required
def add_purchase(vendor_id):
    description = (request.form.get("description") or "").strip() or None
    try:
        db.add_purchase(vendor_id, parse_money_item(description or "Stock purchase"), description, request.form.get("notes"), current_user_id())
        flash("Stock purchase recorded.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("vendor_detail", vendor_id=vendor_id))


@app.route("/vendors/<int:vendor_id>/add-payment", methods=["POST"])
@login_required
def add_vendor_payment(vendor_id):
    try:
        db.add_vendor_payment(vendor_id, float(request.form.get("amount") or 0), request.form.get("payment_method") or "CASH", request.form.get("notes"), current_user_id())
        flash("Vendor payment recorded.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("vendor_detail", vendor_id=vendor_id))


@app.route("/vendors/<int:vendor_id>/ledger/<int:entry_id>/void", methods=["POST"])
@login_required
def void_vendor_ledger(vendor_id, entry_id):
    try:
        db.void_vendor_entry(entry_id, expected_vendor_id=vendor_id, user_id=current_user_id(),
                             reason=(request.form.get("reason") or "").strip() or None)
        flash("Entry voided. The balance has been recalculated.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("vendor_detail", vendor_id=vendor_id))


@app.route("/vendors/<int:vendor_id>/archive", methods=["POST"])
@login_required
def archive_vendor(vendor_id):
    db.archive_vendor(vendor_id, current_user_id())
    flash("Vendor archived.", "success")
    return redirect(url_for("vendors"))


@app.route("/bank", methods=["GET", "POST"])
@login_required
def bank():
    if request.method == "POST":
        try:
            db.change_bank_balance(float(request.form.get("amount") or 0), request.form.get("change_type") or "ADD", request.form.get("note"), current_user_id())
            flash("Bank movement recorded.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("bank"))
    return render_template("bank.html", balance=db.get_current_bank_balance(), history=db.get_bank_balance_history())


def person_form(customer=False):
    return {
        "name": request.form.get("name", "").strip(),
        "phone": request.form.get("phone"),
        "notes": request.form.get("notes"),
    }


def parse_money_item(default_name):
    amount = float(request.form.get("amount") or 0)
    return [{"product_name": default_name, "price": amount, "quantity": 1}]


def _record_opening_balance(kind, person_id):
    """Record the account's first entry from the add-form's optional opening
    amount. Silent when blank; flashes (but keeps the account) on a bad amount."""
    raw = (request.form.get("opening_amount") or "").strip()
    if not raw:
        return
    desc = (request.form.get("opening_description") or "").strip() or None
    try:
        amount = float(raw)
    except ValueError:
        flash("Opening balance was not a valid number — account created without it.", "error")
        return
    default_name = desc or ("Opening balance" if kind == "customer" else "Opening purchase")
    items = [{"product_name": default_name, "price": amount, "quantity": 1}]
    try:
        if kind == "customer":
            db.add_debt(person_id, items, desc, None, current_user_id())
        else:
            db.add_purchase(person_id, items, desc, None, current_user_id())
    except ValueError as exc:
        flash(f"Opening balance skipped: {exc}", "error")


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="127.0.0.1", port=5001)
