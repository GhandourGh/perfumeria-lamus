import html
import re
import sqlite3
from pathlib import Path

from bs4 import BeautifulSoup

import app
import database as db
import i18n


ENGLISH_UI_WORDS = re.compile(
    r"\b(?:account|archive|backup|balance|bank|cancel|close|confirm|credit|"
    r"customer|date|edit|entry|file|generated|history|issued|movement|new|"
    r"note|open|owner|password|payable|payment|phone|prepared|purchase|"
    r"report|restore|save|security|settled|signature|statement|vendor|take|"
    r"money|suppliers|heads|actions|sign-ins|first|latest|largest|printable)\b",
    re.IGNORECASE,
)


def authenticated_client(locale="es_CO"):
    client = app.app.test_client()
    with client.session_transaction() as session:
        session.update(
            user_id=1,
            username="busalim",
            locale=locale,
            last_seen=9_999_999_999,
            csrf_token="test-token",
        )
    return client


def visible_ui_strings(response):
    soup = BeautifulSoup(response.data, "html.parser")
    for element in soup(["script", "style"]):
        element.decompose()
    values = list(soup.stripped_strings)
    for element in soup.find_all(True):
        values.extend(
            element[attribute]
            for attribute in ("placeholder", "aria-label", "title")
            if element.get(attribute)
        )
    return values


def test_spanish_is_the_default_locale():
    response = app.app.test_client().get("/login")
    assert response.status_code == 200
    assert b'lang="es-CO"' in response.data
    assert "Bienvenido de nuevo" in response.get_data(as_text=True)
    assert "Welcome back" not in response.get_data(as_text=True)


def test_every_static_template_phrase_has_spanish_coverage():
    allowed = {
        "B",
        "BU SALIM",
        "Perfumería Lamus",
        "XXXX-XXXX-XXXX-XXXX",
    }
    missing = set()
    for path in Path("templates").glob("*.html"):
        source = path.read_text(encoding="utf-8")
        for raw in re.findall(r">([^<>]+)<", source):
            if "{%" in raw or "{{" in raw or "{#" in raw:
                continue
            phrase = html.unescape(re.sub(r"\s+", " ", raw).strip())
            if (
                phrase
                and re.search(r"[A-Za-z]", phrase)
                and phrase not in allowed
                and i18n.translate_text(phrase, "es_CO") == phrase
            ):
                missing.add(f"{path.name}: {phrase}")
        for raw in re.findall(r'(?:placeholder|aria-label|title)="([^"{]+)"', source):
            phrase = html.unescape(raw.strip())
            if (
                re.search(r"[A-Za-z]", phrase)
                and phrase not in allowed
                and i18n.translate_text(phrase, "es_CO") == phrase
            ):
                missing.add(f"{path.name}: {phrase}")
    assert not missing


def test_english_can_be_selected_globally():
    client = authenticated_client()
    response = client.post(
        "/language/en",
        data={"_csrf_token": "test-token"},
        headers={"Referer": "http://localhost/customers"},
    )
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert session["locale"] == "en"
    page = client.get("/customers")
    assert b'lang="en"' in page.data
    assert "Customers" in page.get_data(as_text=True)


def test_colombian_currency_and_dates():
    assert i18n.format_cop(1_860_000, "es_CO") == "$1.860.000"
    assert i18n.format_day("2026-07-26", "es_CO") == "26 jul 2026"


def test_bank_withdrawal_allows_an_empty_note(tmp_path, monkeypatch):
    test_database = tmp_path / "bank-note-test.db"
    source = sqlite3.connect(db.DATABASE)
    destination = sqlite3.connect(test_database)
    source.backup(destination)
    source.close()
    destination.close()
    monkeypatch.setattr(db, "DATABASE", str(test_database))

    starting_balance = db.get_current_bank_balance()
    entry_id = db.change_bank_balance(1_000, "REMOVE", "", user_id=1)

    assert db.get_current_bank_balance() == starting_balance - 1_000
    with sqlite3.connect(test_database) as connection:
        note = connection.execute(
            "SELECT note FROM bank_balance_log WHERE id = ?", (entry_id,)
        ).fetchone()[0]
    assert note == ""


def test_navbar_has_one_click_backup_download():
    response = authenticated_client().get("/")
    soup = BeautifulSoup(response.data, "html.parser")
    form = soup.select_one('form.nav-quick-backup[action="/backups/download"]')
    assert form is not None
    assert form.get("method") == "post"
    assert form.select_one('button[aria-label="Descargar copia"]') is not None
    assert form.select_one("button span").get_text(strip=True) == "Copia"
    nav = soup.select_one("#topnav-menu")
    children = [child for child in nav.children if getattr(child, "name", None)]
    backup_index = children.index(form)
    more_index = next(index for index, child in enumerate(children) if "nav-more" in child.get("class", []))
    account_index = next(index for index, child in enumerate(children) if "nav-account" in child.get("class", []))
    assert backup_index < more_index < account_index


def test_all_primary_spanish_pages_have_no_known_english_ui_labels():
    client = authenticated_client()
    urls = [
        "/", "/customers", "/customers/add", "/vendors/overview", "/vendors",
        "/vendors/add", "/bank", "/reports", "/backups", "/security",
    ]
    customers = db.get_customers_overview()
    vendors = db.get_vendors_overview()
    for customer in customers:
        customer_id = customer["id"]
        urls.extend([
            f"/customers/{customer_id}",
            f"/customers/{customer_id}/edit",
            f"/customers/{customer_id}/report",
        ])
    for vendor in vendors:
        vendor_id = vendor["id"]
        urls.extend([
            f"/vendors/{vendor_id}",
            f"/vendors/{vendor_id}/edit",
            f"/vendors/{vendor_id}/report",
        ])

    user_data = {
        str(value).strip()
        for row in [*customers, *vendors]
        for value in row.values()
        if value not in (None, "")
    }
    # Stored names and notes are the owner's own content and are never translated.
    stored_content_markers = ("test", "auto:", "supplier purchase", "family account", "prefers cash")
    failures = {}
    for url in urls:
        response = client.get(url)
        assert response.status_code == 200
        untranslated = [
            value for value in visible_ui_strings(response)
            if value not in user_data
            and not any(marker in value.casefold() for marker in stored_content_markers)
            and ENGLISH_UI_WORDS.search(value)
        ]
        if untranslated:
            failures[url] = sorted(set(untranslated))

    assert not failures
