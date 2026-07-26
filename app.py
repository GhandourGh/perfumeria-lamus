import os
import secrets
import time
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, Response, abort, flash, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import check_password_hash

import backup_manager
import database as db
import i18n
import report_manager
import security_manager


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
app.config.update(
    MAX_CONTENT_LENGTH=25 * 1024 * 1024,
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
    SESSION_COOKIE_NAME="lamus_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
)
db.init_db()
security_manager.init_security()
_login_attempts = {}


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


app.jinja_env.globals["csrf_token"] = csrf_token


def current_locale():
    return session.get("locale", i18n.DEFAULT_LOCALE)


def tr(value):
    return i18n.translate_text(value, current_locale())


app.jinja_env.globals["tr"] = tr


@app.before_request
def security_checks():
    if request.method == "POST":
        supplied = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token")
        if not supplied or not secrets.compare_digest(supplied, session.get("csrf_token", "")):
            abort(400, "Security check failed. Refresh the page and try again.")
    if session.get("user_id"):
        now = int(time.time())
        last_seen = session.get("last_seen", now)
        if now - last_seen > 30 * 60:
            session.clear()
            flash("You were signed out after 30 minutes of inactivity.", "error")
            return redirect(url_for("login"))
        session["last_seen"] = now


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    )
    if session.get("user_id"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.after_request
def localize_response(response):
    if response.mimetype == "text/html":
        response.set_data(i18n.localize_html(response.get_data(as_text=True), current_locale()))
    return response


@app.errorhandler(413)
def upload_too_large(_error):
    flash("That file is too large. Choose a Lamus backup under 25 MB.", "error")
    return redirect(url_for("backups"))


def safe_next_url(value):
    if not value:
        return None
    target = urlsplit(value)
    return value if not target.scheme and not target.netloc and value.startswith("/") else None


@app.route("/language/<locale>", methods=["POST"])
def set_language(locale):
    if locale not in i18n.SUPPORTED_LOCALES:
        abort(404)
    session["locale"] = locale
    target = urlsplit(request.referrer or "")
    return redirect(target.path if target.path.startswith("/") else url_for("dashboard"))


def format_cop(amount):
    return i18n.format_cop(amount, current_locale())


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
    return i18n.format_day(value, current_locale())


def format_datetime(value):
    return i18n.format_moment(value, current_locale())


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
OFFICE_ENDPOINTS = {"bank", "reports", "backups", "security"}


def resolve_workspace(endpoint):
    return "vendors" if endpoint in VENDOR_ENDPOINTS else "customers"


@app.context_processor
def inject_globals():
    user = db.get_user(current_user_id()) if current_user_id() else None
    endpoint = request.endpoint
    return {
        "current_user": user,
        "today_display": i18n.format_day(datetime.now(), current_locale()),
        "now_display": i18n.format_moment(datetime.now(), current_locale()),
        "current_locale": current_locale(),
        "supported_locales": i18n.SUPPORTED_LOCALES,
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
        username = request.form.get("username", "").strip()
        key = f"{request.remote_addr}:{username.casefold()}"
        now = time.time()
        attempts = [stamp for stamp in _login_attempts.get(key, []) if now - stamp < 15 * 60]
        if len(attempts) >= 5:
            flash("Too many attempts. Wait 15 minutes, then try again.", "error")
            return render_template("login.html"), 429
        user = db.authenticate_user(username, request.form.get("password", ""))
        if user:
            _login_attempts.pop(key, None)
            db.log_audit(user["id"], "LOGIN", "users", user["id"])
            selected_locale = current_locale()
            session.clear()
            session["locale"] = selected_locale
            session.permanent = True
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["last_seen"] = int(now)
            csrf_token()
            return redirect(safe_next_url(request.args.get("next")) or url_for("dashboard"))
        attempts.append(now)
        _login_attempts[key] = attempts
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    user_id = current_user_id()
    if user_id:
        db.log_audit(user_id, "LOGOUT", "users", user_id)
    selected_locale = current_locale()
    session.clear()
    session["locale"] = selected_locale
    return redirect(url_for("login"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        user = security_manager.use_recovery_code(
            request.form.get("username", ""),
            request.form.get("recovery_code", ""),
        )
        if user:
            session["pw_reset_allowed_for"] = user["id"]
            session["pw_reset_expires"] = int(time.time()) + 10 * 60
            return redirect(url_for("reset_password"))
        flash("The username or recovery code is not valid.", "error")
    return render_template("forgot_password.html")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    user_id = session.get("pw_reset_allowed_for")
    if not user_id or session.get("pw_reset_expires", 0) < int(time.time()):
        session.pop("pw_reset_allowed_for", None)
        session.pop("pw_reset_expires", None)
        return redirect(url_for("forgot_password"))
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        else:
            db.change_password(user_id, password)
            db.log_audit(user_id, "PASSWORD_RESET", "users", user_id)
            session.pop("pw_reset_allowed_for", None)
            session.pop("pw_reset_expires", None)
            flash("Password updated. Please log in.", "success")
            return redirect(url_for("login"))
    return render_template("reset_password.html")


@app.route("/security", methods=["GET", "POST"])
@login_required
def security():
    user = db.get_user(current_user_id())
    recovery_code = None
    if request.method == "POST":
        action = request.form.get("action")
        current_password = request.form.get("current_password", "")
        if not check_password_hash(user["password_hash"], current_password):
            flash("Your current password is incorrect.", "error")
        elif action == "password":
            new_password = request.form.get("new_password", "")
            if len(new_password) < 8:
                flash("New password must be at least 8 characters.", "error")
            elif new_password != request.form.get("confirm_password", ""):
                flash("New passwords do not match.", "error")
            else:
                db.change_password(user["id"], new_password)
                db.log_audit(user["id"], "PASSWORD_CHANGED", "users", user["id"])
                flash("Password changed successfully.", "success")
        elif action == "recovery":
            recovery_code = security_manager.create_recovery_code(user["id"])
            db.log_audit(user["id"], "RECOVERY_CODE_CREATED", "users", user["id"])
            flash("New recovery code created. Save it now; it will not be shown again.", "success")
    return render_template(
        "security.html",
        has_recovery_code=security_manager.has_recovery_code(user["id"]),
        recovery_code=recovery_code,
    )


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
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    action_filter = request.args.get("action", "")
    action_events = report_manager.get_action_events(date_from, date_to, action_filter)
    return render_template(
        "reports.html",
        stats=db.get_dashboard_stats(),
        customers=db.get_customers_overview(),
        vendors=db.get_vendors_overview(),
        bank_balance=db.get_current_bank_balance(),
        bank_history=db.get_bank_balance_history(limit=200),
        recent_activity=db.get_recent_activity(limit=100),
        action_events=action_events,
        action_labels=report_manager.ACTION_LABELS,
        action_filter=action_filter,
        date_from=date_from,
        date_to=date_to,
        owner_stats=report_manager.get_owner_stats(current_user_id()),
    )


@app.route("/reports/actions.csv")
@login_required
def report_actions_csv():
    events = report_manager.get_action_events(
        request.args.get("date_from", ""),
        request.args.get("date_to", ""),
        request.args.get("action", ""),
    )
    return Response(
        report_manager.actions_csv(
            events,
            lambda value: i18n.translate_text(value, current_locale()),
            lambda value: i18n.format_moment(value, current_locale()),
        ),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=lamus-owner-actions.csv"},
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
        db.log_audit(current_user_id(), "ADD_CUSTOMER", "customers", new_id)
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
        db.log_audit(current_user_id(), "EDIT_CUSTOMER", "customers", customer_id)
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


@app.route("/customers/<int:customer_id>/ledger/<int:entry_id>/edit", methods=["POST"])
@login_required
def edit_customer_ledger(customer_id, entry_id):
    try:
        db.edit_customer_entry(
            entry_id,
            customer_id,
            request.form.get("amount") or 0,
            description=request.form.get("description"),
            notes=request.form.get("notes"),
            payment_method=request.form.get("payment_method"),
            due_date=request.form.get("due_date"),
            user_id=current_user_id(),
        )
        flash("Ledger entry updated and balances recalculated.", "success")
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
    vendors = sorted(
        db.get_vendors_overview(),
        key=lambda vendor: vendor["balance"],
        reverse=True,
    )
    payable = [v for v in vendors if v["balance"] > 0]
    overdue = [v for v in payable if v["is_overdue"]]
    stats = {
        "total_payable": sum(v["balance"] for v in payable),
        "vendor_count": len(vendors),
        "vendors_with_balance": len(payable),
        "overdue_vendor_count": len(overdue),
        "total_overdue": sum(v["balance"] for v in overdue),
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
    vendor_list = sorted(
        db.get_vendors_overview(),
        key=lambda vendor: vendor["balance"],
        reverse=True,
    )
    return render_template("vendors.html", vendors=vendor_list)


@app.route("/vendors/add", methods=["GET", "POST"])
@login_required
def add_vendor():
    if request.method == "POST":
        new_id = db.add_vendor(**person_form(customer=False))
        db.log_audit(current_user_id(), "ADD_VENDOR", "vendors", new_id)
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
        db.log_audit(current_user_id(), "EDIT_VENDOR", "vendors", vendor_id)
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


@app.route("/vendors/<int:vendor_id>/ledger/<int:entry_id>/edit", methods=["POST"])
@login_required
def edit_vendor_ledger(vendor_id, entry_id):
    try:
        db.edit_vendor_entry(
            entry_id,
            vendor_id,
            request.form.get("amount") or 0,
            description=request.form.get("description"),
            notes=request.form.get("notes"),
            payment_method=request.form.get("payment_method"),
            user_id=current_user_id(),
        )
        flash("Ledger entry updated and balances recalculated.", "success")
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
            db.log_audit(current_user_id(), "BANK_CHANGE", "bank_accounts", 1, request.form.get("note"))
            flash("Bank movement recorded.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("bank"))
    return render_template("bank.html", balance=db.get_current_bank_balance(), history=db.get_bank_balance_history())


@app.route("/backups", methods=["GET", "POST"])
@login_required
def backups():
    if request.method == "POST":
        try:
            action = request.form.get("action")
            if action == "restore":
                accepted = {"RESTORE", "RESTAURAR"} if current_locale() == "es_CO" else {"RESTORE"}
                if (request.form.get("confirmation") or "").strip().upper() not in accepted:
                    raise ValueError("Type RESTORE exactly to confirm.")
                backup_manager.restore_backup(request.files.get("backup_file"))
                db.log_audit(current_user_id(), "RESTORE_COMPLETED", "database", None)
                session.clear()
                flash("Backup restored. Please sign in again.", "success")
                return redirect(url_for("login"))
        except Exception as exc:
            flash(str(exc), "error")
        return redirect(url_for("backups"))
    return render_template("backups.html", backup=backup_manager.status())


@app.route("/backups/download", methods=["POST"])
@login_required
def download_backup():
    path = backup_manager.create_backup()
    db.log_audit(current_user_id(), "BACKUP_CREATED", "database", None, path.name)
    return send_file(path, as_attachment=True, download_name=path.name)


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
    if os.environ.get("FLASK_DEBUG") == "1":
        app.run(debug=True, host="127.0.0.1", port=5001)
    else:
        from waitress import serve
        serve(app, host="127.0.0.1", port=5001, threads=4)
