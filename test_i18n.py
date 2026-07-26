import re

from bs4 import BeautifulSoup

import app
import database as db
import i18n


ENGLISH_UI_WORDS = re.compile(
    r"\b(?:account|archive|backup|balance|bank|cancel|close|confirm|credit|"
    r"customer|date|edit|entry|file|generated|history|issued|movement|new|"
    r"note|open|owner|password|payable|payment|phone|prepared|purchase|"
    r"report|restore|save|security|settled|signature|statement|vendor)\b",
    re.IGNORECASE,
)


def authenticated_client(locale="es_CO"):
    client = app.app.test_client()
    with client.session_transaction() as session:
        session.update(
            user_id=1,
            username="admin",
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


def test_all_primary_spanish_pages_have_no_known_english_ui_labels():
    client = authenticated_client()
    urls = [
        "/", "/customers", "/customers/add", "/vendors/overview", "/vendors",
        "/vendors/add", "/bank", "/reports", "/backups", "/security",
    ]
    customers = db.get_customers_overview()
    vendors = db.get_vendors_overview()
    if customers:
        customer_id = customers[0]["id"]
        urls.extend([
            f"/customers/{customer_id}",
            f"/customers/{customer_id}/edit",
            f"/customers/{customer_id}/report",
        ])
    if vendors:
        vendor_id = vendors[0]["id"]
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
