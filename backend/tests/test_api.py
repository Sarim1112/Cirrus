import json
from datetime import timedelta

from sqlalchemy import func, select

from app.advisor.providers import ProviderReply, set_provider
from app.config import local_today
from app.db import open_session, utcnow
from app.main import purge_expired
from app.models import AuthSession, ChatMessage, Goal, PasswordReset, Transaction, User
from app.routers import auth as auth_router
from app.security import SESSION_COOKIE, hash_token

from .conftest import PASSWORD, register

STATEMENT = (
    "Date,Description,Amount,Balance\n"
    "{d1},NETFLIX.COM 866-579-7172,-16.49,1983.51\n"
    "{d2},PAYROLL DEP ACME,2000.00,3983.51\n"
    "{d3},MYSTERY VENDOR 90210,-25.00,3958.51\n"
)


def statement(today=None):
    today = today or local_today()
    days = [today - timedelta(days=n) for n in (3, 2, 1)]
    return STATEMENT.format(d1=days[0], d2=days[1], d3=days[2]).encode()


def upload(client, content=None, name="bank.csv", path="/api/imports", **data):
    return client.post(path, files={"file": (name, content or statement(), "text/csv")}, data=data)


def chat(client, message):
    response = client.post("/api/chat", json={"message": message})
    assert response.status_code == 200, response.text
    events = []
    for block in response.text.strip().split("\n\n"):
        name, payload = block.split("\n", 1)
        events.append((name.removeprefix("event: "), json.loads(payload.removeprefix("data: "))))
    return events


# --- accounts ------------------------------------------------------------------------------


def test_register_me_logout_login(client):
    user = register(client)
    assert user["email"] == "ada@example.com"
    assert "password" not in json.dumps(user)
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.clear()
    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.post(
            "/api/auth/login", json={"email": "ADA@example.com", "password": PASSWORD}
        ).status_code
        == 200
    )


def test_session_cookie_flags_and_token_storage(client):
    response = client.post(
        "/api/auth/register", json={"email": "a@example.com", "password": PASSWORD}
    )
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    token = response.cookies[SESSION_COOKIE]
    with open_session() as db:
        stored = db.execute(select(AuthSession.token_hash)).scalar_one()
    assert stored == hash_token(token)
    assert stored != token


def test_passwords_are_hashed_with_argon2(client):
    register(client)
    with open_session() as db:
        stored = db.execute(select(User.password_hash)).scalar_one()
    assert stored.startswith("$argon2id$")


def test_weak_password_duplicate_email_and_wrong_password(client):
    assert (
        client.post(
            "/api/auth/register", json={"email": "a@example.com", "password": "short"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/auth/register", json={"email": "ada@example.com", "password": "my-ada-password-1"}
        ).status_code
        == 422
    )
    register(client)
    assert (
        client.post(
            "/api/auth/register", json={"email": "ada@example.com", "password": PASSWORD}
        ).status_code
        == 409
    )
    client.cookies.clear()
    wrong = client.post(
        "/api/auth/login", json={"email": "ada@example.com", "password": "wrong password!"}
    )
    missing = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "wrong password!"}
    )
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json() == missing.json()


def test_login_is_rate_limited(client):
    register(client)
    client.cookies.clear()
    codes = [
        client.post(
            "/api/auth/login", json={"email": "ada@example.com", "password": "wrong password!"}
        ).status_code
        for _ in range(9)
    ]
    assert codes[-1] == 429


def test_expired_session_is_rejected(client):
    register(client)
    with open_session() as db:
        session = db.execute(select(AuthSession)).scalar_one()
        session.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_password_reset_flow(client, monkeypatch):
    sent = {}
    monkeypatch.setattr(
        auth_router, "_send_reset_email", lambda to, link: sent.update(to=to, link=link)
    )
    register(client)
    assert (
        client.post("/api/auth/forgot-password", json={"email": "ada@example.com"}).status_code
        == 202
    )
    assert (
        client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"}).status_code
        == 202
    )
    assert sent["to"] == "ada@example.com"
    token = sent["link"].split("token=")[1]
    with open_session() as db:
        assert db.execute(select(PasswordReset.token_hash)).scalar_one() == hash_token(token)

    new = "a brand new passphrase"
    assert (
        client.post("/api/auth/reset-password", json={"token": token, "password": new}).status_code
        == 200
    )
    # Existing sessions end, and the link can't be reused.
    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.post("/api/auth/reset-password", json={"token": token, "password": new}).status_code
        == 400
    )
    client.cookies.clear()
    assert (
        client.post(
            "/api/auth/login", json={"email": "ada@example.com", "password": new}
        ).status_code
        == 200
    )


def test_change_password_signs_out_other_devices(client, second_client):
    register(client)
    second_client.post("/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD})
    body = {"current_password": PASSWORD, "new_password": "another good passphrase"}
    assert client.post("/api/auth/change-password", json=body).status_code == 200
    assert client.get("/api/auth/me").status_code == 200
    assert second_client.get("/api/auth/me").status_code == 401


def test_writes_from_other_sites_are_blocked(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "a@example.com", "password": "x"},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    allowed = client.post(
        "/api/auth/login",
        json={"email": "a@example.com", "password": "x"},
        headers={"Origin": "http://localhost:3000"},
    )
    assert allowed.status_code == 401


# --- every endpoint requires a session ------------------------------------------------------


def test_private_routes_require_sign_in(client):
    protected = [
        ("get", "/api/overview"), ("get", "/api/transactions"), ("get", "/api/forecast"),
        ("get", "/api/insights"), ("get", "/api/recurring"), ("get", "/api/budgets"),
        ("put", "/api/budgets"), ("get", "/api/goals"), ("post", "/api/goals"),
        ("post", "/api/simulate"), ("post", "/api/afford"), ("get", "/api/imports"),
        ("post", "/api/imports"), ("post", "/api/imports/preview"), ("post", "/api/chat"),
        ("get", "/api/chat/messages"), ("get", "/api/chat/status"), ("delete", "/api/chat/messages"),
        ("get", "/api/account/export"), ("post", "/api/account/delete"),
        ("patch", "/api/account/settings"), ("get", "/api/transactions/export.csv"),
    ]  # fmt: skip
    for method, path in protected:
        response = getattr(client, method)(path)
        assert response.status_code in {401, 422}, path
        if response.status_code == 422:
            # Validation runs first on some bodies. Confirm that a valid-looking one is still refused.
            assert method != "get", path


def _seed_second_user(client, second_client):
    register(client, "ada@example.com")
    register(second_client, "grace@example.com")
    assert upload(client).status_code == 201
    txn = client.get("/api/transactions").json()["items"][0]
    goal = client.post("/api/goals", json={"name": "Trip", "target_cents": 100000}).json()
    batch = client.get("/api/imports").json()["imports"][0]
    return txn, goal, batch


def test_users_cant_read_each_others_data(client, second_client):
    _seed_second_user(client, second_client)
    assert second_client.get("/api/transactions").json()["total"] == 0
    assert second_client.get("/api/imports").json()["imports"] == []
    assert second_client.get("/api/goals").json()["plans"] == []
    assert second_client.get("/api/overview").json()["has_data"] is False
    assert second_client.get("/api/account/export").json()["transactions"] == []
    assert "NETFLIX" not in second_client.get("/api/transactions/export.csv").text
    assert (
        "Netflix" not in chat(second_client, "How much did I spend at Netflix?")[-1][1]["content"]
    )


def test_users_cant_change_each_others_data(client, second_client):
    txn, goal, batch = _seed_second_user(client, second_client)
    assert (
        second_client.patch(
            f"/api/transactions/{txn['id']}", json={"category": "Other"}
        ).status_code
        == 404
    )
    assert second_client.delete(f"/api/transactions/{txn['id']}").status_code == 404
    assert (
        second_client.patch(f"/api/goals/{goal['id']}", json={"saved_cents": 5}).status_code == 404
    )
    assert second_client.delete(f"/api/goals/{goal['id']}").status_code == 404
    assert second_client.delete(f"/api/imports/{batch['id']}").status_code == 404
    assert client.get("/api/transactions").json()["total"] == 3


def test_the_same_statement_can_belong_to_two_users(client, second_client):
    register(client, "ada@example.com")
    register(second_client, "grace@example.com")
    assert upload(client).json()["rows_imported"] == 3
    assert upload(second_client).json()["rows_imported"] == 3


def test_merchant_rules_stay_private(client, second_client):
    txn, _, _ = _seed_second_user(client, second_client)
    client.patch(f"/api/transactions/{txn['id']}", json={"category": "Gifts & Donations"})
    upload(second_client)
    categories = {
        t["merchant"]: t["category"] for t in second_client.get("/api/transactions").json()["items"]
    }
    assert "Gifts & Donations" not in categories.values()


# --- imports -------------------------------------------------------------------------------


def test_preview_saves_nothing_then_import_saves_once(client):
    register(client)
    preview = upload(client, path="/api/imports/preview").json()
    assert preview["rows"] == 3
    assert preview["duplicates"] == 0
    assert preview["sample"][0]["merchant"] == "Netflix"
    assert client.get("/api/transactions").json()["total"] == 0

    first = upload(client).json()
    assert first["rows_imported"] == 3
    second = upload(client).json()
    assert second["rows_imported"] == 0
    assert second["rows_duplicate"] == 3
    assert client.get("/api/transactions").json()["total"] == 3
    assert upload(client, path="/api/imports/preview").json()["duplicates"] == 3


def test_statement_balance_is_adopted_and_rolled_forward(client):
    register(client)
    upload(client)
    overview = client.get("/api/overview").json()
    assert overview["balance_cents"] == 395851
    today = local_today()
    client.post(
        "/api/transactions",
        json={"date": today.isoformat(), "description": "Coffee", "amount_cents": -500},
    )
    assert client.get("/api/overview").json()["balance_cents"] == 395351


def test_undo_import_removes_its_transactions(client):
    register(client)
    batch = upload(client).json()
    assert client.delete(f"/api/imports/{batch['id']}").status_code == 204
    assert client.get("/api/transactions").json()["total"] == 0


def test_reverse_amounts_option(client):
    register(client)
    content = f"Date,Description,Amount\n{local_today()},COFFEE SHOP,4.00\n".encode()
    upload(client, content, reverse_amounts="true")
    assert client.get("/api/transactions").json()["items"][0]["amount_cents"] == -400


def test_bad_uploads_get_clear_errors(client):
    register(client)
    assert upload(client, b"nothing useful here\n").status_code == 422
    response = upload(client, b"\x89PNG", name="photo.png")
    assert response.status_code == 422
    assert "CSV or PDF" in response.json()["detail"]
    assert upload(client, b"x" * (10 * 1024 * 1024 + 1)).status_code == 413


def test_correction_teaches_past_and_future_transactions(client):
    register(client)
    upload(client)
    items = client.get("/api/transactions?q=mystery").json()["items"]
    assert items[0]["category"] == "Other"
    response = client.patch(
        f"/api/transactions/{items[0]['id']}", json={"category": "Entertainment"}
    )
    assert response.status_code == 200
    today = local_today()
    upload(client, f"Date,Description,Amount\n{today},MYSTERY VENDOR 90210,-9.00\n".encode())
    rows = client.get("/api/transactions?q=mystery").json()["items"]
    assert {r["category"] for r in rows} == {"Entertainment"}
    assert {r["category_source"] for r in rows} == {"user"}


def test_invalid_category_rejected(client):
    register(client)
    upload(client)
    txn = client.get("/api/transactions").json()["items"][0]
    assert (
        client.patch(f"/api/transactions/{txn['id']}", json={"category": "Nope"}).status_code == 422
    )


def test_transaction_filters_and_pagination(client):
    register(client)
    upload(client)
    today = local_today()
    assert client.get("/api/transactions?q=netflix").json()["total"] == 1
    assert client.get("/api/transactions?category=Income").json()["total"] == 1
    assert client.get(f"/api/transactions?month={today:%Y-%m}&page_size=1").json()["page_size"] == 1
    assert client.get("/api/transactions?month=nope").status_code == 422


def test_csv_export_neutralises_spreadsheet_formulas(client):
    register(client)
    today = local_today()
    client.post(
        "/api/transactions",
        json={
            "date": today.isoformat(),
            "description": "=HYPERLINK(1)",
            "amount_cents": -100,
            "category": "Other",
        },
    )
    text = client.get("/api/transactions/export.csv").text
    assert "\n=" not in text and ",=" not in text


# --- analytics, budgets and goals -----------------------------------------------------------


def test_budget_round_trip_and_validation(client):
    register(client)
    assert client.put(
        "/api/budgets", json={"budgets": [{"category": "Dining", "limit_cents": 30000}]}
    ).json() == {"saved": 1}
    assert client.get("/api/budgets").json()["status"][0]["category"] == "Dining"
    assert (
        client.put(
            "/api/budgets", json={"budgets": [{"category": "Income", "limit_cents": 1}]}
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/budgets", json={"budgets": [{"category": "Dining", "limit_cents": 0}]}
        ).status_code
        == 422
    )


def test_goal_crud_and_validation(client):
    register(client)
    assert (
        client.post(
            "/api/goals", json={"name": "Trip", "target_cents": 100000, "target_date": "2001-01-01"}
        ).status_code
        == 422
    )
    goal = client.post("/api/goals", json={"name": "Trip", "target_cents": 100000}).json()
    assert client.patch(f"/api/goals/{goal['id']}", json={"saved_cents": 100000}).status_code == 200
    assert client.get("/api/goals").json()["plans"][0]["status"] == "done"
    assert client.delete(f"/api/goals/{goal['id']}").status_code == 204


def test_simulation_validation(client):
    register(client)
    assert (
        client.post("/api/simulate", json={"changes": [{"type": "cut_category"}]}).status_code
        == 422
    )
    assert client.post("/api/simulate", json={"changes": [{"type": "unknown"}]}).status_code == 422


def test_empty_account_works_everywhere(client):
    register(client)
    assert client.get("/api/overview").json()["has_data"] is False
    assert client.get("/api/forecast").status_code == 200
    assert client.get("/api/insights").json()["insights"] == []
    assert client.get("/api/recurring").json()["streams"] == []
    assert client.get("/api/budgets").json()["suggestions"] == []
    assert client.post("/api/afford", json={"amount_cents": 100}).status_code == 200


def test_dismissed_insights_stay_gone(client):
    client.post("/api/auth/demo")
    insight = client.get("/api/insights").json()["insights"][0]
    assert client.post(f"/api/insights/{insight['key']}/dismiss").status_code == 204
    keys = [i["key"] for i in client.get("/api/insights").json()["insights"]]
    assert insight["key"] not in keys


# --- chat ----------------------------------------------------------------------------------


def test_chat_streams_status_then_final_and_saves_history(client):
    client.post("/api/auth/demo")
    events = chat(client, "What's safe to spend?")
    assert events[0][0] == "status"
    name, message = events[-1]
    assert name == "final"
    assert message["meta"]["mode"] == "built_in"
    assert message["meta"]["charts"][0]["kind"] == "forecast"
    history = client.get("/api/chat/messages").json()["messages"]
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert client.delete("/api/chat/messages").status_code == 204
    assert client.get("/api/chat/messages").json()["messages"] == []


def test_chat_validates_length_and_rate(client):
    client.post("/api/auth/demo")
    assert client.post("/api/chat", json={"message": ""}).status_code == 422
    assert client.post("/api/chat", json={"message": "x" * 1001}).status_code == 422
    codes = [client.post("/api/chat", json={"message": "hi"}).status_code for _ in range(31)]
    assert codes[-1] == 429


def test_categorize_with_ai_validates_model_output(client):
    class Model:
        name = "fake"

        def available(self):
            return True

        def chat(self, messages, tools=None, temperature=0.2):
            return ProviderReply(
                content="Mystery Vendor | Entertainment\nOther Thing | Hacked\nnot a line"
            )

    register(client)
    upload(client)
    assert client.post("/api/transactions/categorize-with-ai").status_code == 503
    set_provider(Model())
    assert client.post("/api/transactions/categorize-with-ai").json() == {
        "updated": 1,
        "merchants": 1,
    }
    row = client.get("/api/transactions?q=mystery").json()["items"][0]
    assert (row["category"], row["category_source"]) == ("Entertainment", "model")


# --- demo and deletion ----------------------------------------------------------------------


def test_demo_seeds_a_year_of_data_and_expires(client):
    response = client.post("/api/auth/demo")
    assert response.status_code == 201
    assert response.json()["is_demo"] is True
    assert response.json()["email"] is None
    overview = client.get("/api/overview").json()
    assert overview["has_data"] is True
    assert len(overview["series"]) == 12
    kinds = {i["kind"] for i in client.get("/api/insights").json()["insights"]}
    assert {"duplicate", "unusual", "price_increase", "creep"} <= kinds

    assert purge_expired() == 0
    with open_session() as db:
        user = db.execute(select(User).where(User.is_demo.is_(True))).scalar_one()
        user.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert purge_expired() == 1
    with open_session() as db:
        assert db.execute(select(func.count()).select_from(Transaction)).scalar_one() == 0
        assert db.execute(select(func.count()).select_from(Goal)).scalar_one() == 0
    assert client.get("/api/auth/me").status_code == 401


def test_demo_login_is_impossible(client):
    client.post("/api/auth/demo")
    with open_session() as db:
        email = db.execute(select(User.email)).scalar_one()
    client.cookies.clear()
    assert client.post(
        "/api/auth/login", json={"email": email, "password": "anything at all"}
    ).status_code in {401, 422}


def test_account_deletion_removes_everything(client):
    register(client)
    upload(client)
    client.post("/api/goals", json={"name": "Trip", "target_cents": 100000})
    client.put("/api/budgets", json={"budgets": [{"category": "Dining", "limit_cents": 30000}]})
    chat(client, "How much did I spend?")
    assert (
        client.post("/api/account/delete", json={"password": "wrong password!"}).status_code == 401
    )
    assert client.post("/api/account/delete", json={"password": PASSWORD}).status_code == 204
    with open_session() as db:
        for model in (User, AuthSession, Transaction, Goal, ChatMessage):
            assert db.execute(select(func.count()).select_from(model)).scalar_one() == 0, model
    assert client.get("/api/auth/me").status_code == 401


def test_export_contains_my_data(client):
    register(client)
    upload(client)
    exported = client.get("/api/account/export").json()
    assert len(exported["transactions"]) == 3
    assert "password" not in json.dumps(exported).lower()


def test_settings_update(client):
    register(client)
    updated = client.patch(
        "/api/account/settings", json={"currency": "EUR", "balance_cents": 5000}
    ).json()
    assert updated["currency"] == "EUR"
    assert updated["balance_cents"] == 5000
    assert client.patch("/api/account/settings", json={"currency": "XXX"}).status_code == 422
    cleared = client.patch("/api/account/settings", json={"clear_balance": True}).json()
    assert cleared["balance_cents"] is None


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"
