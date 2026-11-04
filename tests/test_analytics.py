from datetime import date

import pandas as pd
import pytest

from till import analytics as a
from till import copilot, db

TODAY = date(2026, 6, 30)
BIZ = {"currency": "USD", "opening_cash": 1000, "opening_cash_date": None}


def frames(sales=(), expenses=(), products=()):
    s = pd.DataFrame(sales, columns=["id"] + db.EDITABLE["sales"])
    e = pd.DataFrame(expenses, columns=["id"] + db.EDITABLE["expenses"])
    p = pd.DataFrame(products, columns=["id"] + db.EDITABLE["products"])
    empty = lambda t: pd.DataFrame(columns=["id"] + db.EDITABLE[t])
    return a.prepare(BIZ, s, e, p, empty("customers"), empty("competitors"), empty("goals"), empty("tasks"), TODAY)


def sale(day, item="Loaf", customer=None, qty=1, price=100.0, cost=40.0):
    return (None, day, item, customer, qty, price, cost, "Counter")


def expense(day, category, amount, fixed=0):
    return (None, day, category, "x", amount, fixed)


def test_profit_arithmetic():
    d = frames([sale("2026-06-10", qty=3)], [expense("2026-06-01", "Rent", 50, 1)])
    p = a.period(d, date(2026, 6, 1), date(2026, 6, 30))
    assert (p["revenue"], p["cogs"], p["gross_profit"], p["net_profit"]) == (300, 120, 180, 130)
    assert p["gross_margin"] == pytest.approx(0.6)


def test_stock_purchases_not_double_counted_when_unit_costs_exist():
    d = frames([sale("2026-06-10")], [expense("2026-06-01", a.STOCK_CATEGORY, 500)])
    assert d.cost_basis == "unit_costs"
    assert a.period(d, date(2026, 6, 1), date(2026, 6, 30))["net_profit"] == 60


def test_purchases_used_when_unit_costs_missing():
    d = frames([sale("2026-06-10", cost=None)], [expense("2026-06-01", a.STOCK_CATEGORY, 30)])
    assert d.cost_basis == "purchases"
    assert a.period(d, date(2026, 6, 1), date(2026, 6, 30))["net_profit"] == 70


def test_missing_cost_filled_from_catalogue():
    d = frames([sale("2026-06-10", cost=None)], products=[(None, "Loaf", "Product", "Bread", 100, 25, 5, 2)])
    assert d.sales.iloc[0]["cogs"] == 25


def test_no_comparison_without_full_prior_window():
    d = frames([sale("2026-06-10")])
    assert a.window(d, 3)["prior"] is None


def test_comparison_with_full_prior_window():
    d = frames([sale("2026-01-05"), sale("2026-02-10"), sale("2026-06-10"), sale("2026-06-11")])
    w = a.window(d, 3)
    assert w["prior"]["revenue"] == 200 and w["current"]["revenue"] == 200


def test_cash_estimate_uses_opening_balance():
    d = frames([sale("2026-06-10")], [expense("2026-06-01", "Rent", 50)])
    assert a.estimated_cash(d) == 1000 + 100 - 40 - 50


def test_break_even():
    rows = [expense(f"2026-0{m}-01", "Rent", 300, 1) for m in (4, 5, 6)]
    d = frames([sale("2026-06-10")], rows)
    assert a.break_even(d) == pytest.approx(300 / 0.6)


def test_every_period_holds_the_same_number_of_monthly_bills():
    rows = [expense(f"2026-0{m}-01", "Rent", 300, 1) for m in range(1, 7)]
    d = frames([sale("2026-01-05"), sale("2026-06-10")], rows)
    for day in (date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 2)):
        d.today = day
        w = a.window(d, 3)
        assert w["current"]["operating_expenses"] == 900 and w["prior"]["operating_expenses"] == 900


def test_new_business_shows_month_to_date():
    d = frames([sale("2026-06-10")])
    d.today = date(2026, 6, 20)
    w = a.window(d, 3)
    assert w["label"] == "so far this month" and w["current"]["revenue"] == 100


def test_partial_month_flag():
    d = frames([sale("2026-06-10")])
    assert not a.monthly(d).iloc[-1]["partial"]  # 30 June is a complete month
    d.today = date(2026, 6, 15)
    assert a.monthly(d).iloc[-1]["partial"]


def test_loss_signal_and_headline():
    d = frames([sale("2026-06-10")], [expense("2026-06-01", "Rent", 500)])
    assert any(s["severity"] == "critical" and "losing" in s["title"] for s in a.signals(d))
    assert "lost" in a.headline(d, a.window(d, 3))


def test_empty_business_is_safe():
    d = frames()
    assert a.signals(d) == []
    assert a.monthly(d).empty
    assert "first sales" in a.headline(d, a.window(d, 3))
    assert a.ai_context(d)["data_available"]["sales_rows"] == 0


def test_tenant_isolation_and_grid_sync(tmp_path, monkeypatch):
    monkeypatch.setenv("TILL_DB", str(tmp_path / "t.db"))
    db.init()
    one = db.save_business(db.create_user("a@x.co", "A", "password1"), {"name": "A"})
    two = db.save_business(db.create_user("b@x.co", "B", "password1"), {"name": "B"})
    db.insert_many("customers", one, [{"name": "Kept"}, {"name": "Gone"}])
    db.insert_many("customers", two, [{"name": "Other"}])
    frame = db.fetch("customers", one)
    shown = frame["id"].tolist()
    # Business one tries to delete a row and update a row belonging to business two.
    other_id = int(db.fetch("customers", two)["id"].iloc[0])
    edited = frame[frame["name"] == "Kept"].copy()
    assert db.sync("customers", one, edited, shown + [other_id])["removed"] == 2
    assert db.fetch("customers", two)["name"].tolist() == ["Other"]
    assert db.fetch("customers", one)["name"].tolist() == ["Kept"]


def test_login(tmp_path, monkeypatch):
    monkeypatch.setenv("TILL_DB", str(tmp_path / "t.db"))
    db.init()
    assert db.create_user("A@x.co ", "A", "password1")
    assert db.create_user("a@x.co", "A", "password1") is None
    assert db.verify_user("a@x.co", "password1")
    assert db.verify_user("a@x.co", "wrong") is None


def test_review_shape_guard():
    out = copilot.normalise({"summary": "ok", "actions": [{"title": "Do", "priority": "Urgent"}], "strengths": [{"point": "p"}]})
    assert out["actions"][0]["priority"] == "Medium" and out["strengths"][0]["evidence"] == ""
    with pytest.raises(ValueError):
        copilot.normalise({"summary": " "})


def test_strict_schema_is_valid_for_groq():
    def walk(node):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
            for child in node["properties"].values():
                walk(child)
        if node.get("type") == "array":
            walk(node["items"])
    walk(copilot.REVIEW_SCHEMA)


def test_dollar_escaping():
    assert copilot.safe_md("$10 and $20") == "\\$10 and \\$20"


def test_ticking_a_task_does_not_stale_the_review():
    d = frames([sale("2026-06-10")])
    one = a.ai_context(d)
    two = dict(one, open_tasks=[{"title": "x"}], goals=[{"title": "y"}])
    assert copilot.fingerprint(one) == copilot.fingerprint(two)
    assert copilot.fingerprint(one) != copilot.fingerprint(dict(one, items=[{"item": "new"}]))


def test_csv_import_cleans_rows():
    from till import views
    raw = pd.DataFrame({"Day": ["2026-01-02", "not a date", "2026-01-03"], "Product": ["A", "B", None], "Total": ["$1,200.50", "5", "9"], "Qty": [2, 1, 1]})
    rows, rejected = views.clean_import("sales", raw, {"date": "Day", "item": "Product", "total": "Total", "qty": "Qty"})
    assert len(rows) == 1 and rejected == 2 and rows[0]["unit_price"] == pytest.approx(600.25)
    assert views.clean_import("sales", raw, {"date": "Day", "item": "Product"})[0] is None


def test_this_month_compares_same_days():
    d = frames([sale("2026-05-05"), sale("2026-05-20"), sale("2026-06-06"), sale("2026-04-02")])
    d.today = date(2026, 6, 10)
    w = a.this_month(d)
    assert w["current"]["revenue"] == 100 and w["prior"]["revenue"] == 100


def test_no_key_is_requested_from_users():
    import pathlib
    text = pathlib.Path(__file__).parent.parent.joinpath("till", "views.py").read_text()
    assert "API key" not in text and "groq_key" not in text
