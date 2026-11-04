"""Runs every screen headlessly, for both a brand-new and a populated business."""
import pytest
from streamlit.testing.v1 import AppTest

from till import db, demo


def boot(tmp_path, monkeypatch, sample):
    monkeypatch.setenv("TILL_DB", str(tmp_path / "a.db"))
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    db.init()
    uid = db.create_user("o@x.co", "O", "password1")
    bid = db.save_business(uid, dict(demo.BUSINESS) if sample else {"name": "New shop", "currency": "USD"})
    if sample:
        demo.load(bid)
    return uid


@pytest.mark.parametrize("sample", [False, True])
@pytest.mark.parametrize("page", ["home", "coach", "plan", "stuff"])
def test_every_page_renders(tmp_path, monkeypatch, sample, page):
    uid = boot(tmp_path, monkeypatch, sample)
    source = f"""
import streamlit as st
from till import views, ui
class P: pass
st.session_state["user_id"] = {uid}
st.session_state["pages"] = dict.fromkeys(["home", "coach", "plan", "stuff"], "x")
import unittest.mock as m
from streamlit.delta_generator import DeltaGenerator
with m.patch.object(DeltaGenerator, "page_link"), m.patch("streamlit.page_link"):
    views.{page}()
"""
    at = AppTest.from_string(source, default_timeout=60).run()
    assert not at.exception, at.exception


def test_sign_up_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("TILL_DB", str(tmp_path / "b.db"))
    at = AppTest.from_file("../app.py", default_timeout=60).run()
    assert not at.exception
    at.text_input[3].set_value("nobody@x.co")
    at.text_input[4].set_value("wrongpass1")
    at.button[1].click().run()
    assert any("don't match" in e.value for e in at.error)


def test_grid_edit_saves_dates_and_ticks(tmp_path, monkeypatch):
    uid = boot(tmp_path, monkeypatch, False)
    bid = db.get_business(uid)["id"]
    db.insert_many("expenses", bid, [{"date": "2026-01-01", "category": "Rent", "amount": 100, "fixed": 1}])
    source = f"""
import streamlit as st
from till import views
st.session_state["user_id"] = {uid}
import datetime, pandas as pd
captured = {{}}
real = st.data_editor
def fake(view, **kw):
    captured["types"] = (type(view["date"].iloc[0]).__name__, str(view["fixed"].dtype))
    out = real(view, **kw)
    out = out.copy(); out.loc[out.index[0], "amount"] = 250.0; out.loc[out.index[0], "date"] = datetime.date(2026, 2, 2)
    return out
st.data_editor = fake
views.editor("expenses", {bid}, {{"date": st.column_config.DateColumn("Date"), "category": "Category", "description": "Description", "amount": "Amount", "fixed": st.column_config.CheckboxColumn("Same")}})
st.session_state["types"] = captured["types"]
"""
    at = AppTest.from_string(source, default_timeout=60).run()
    assert not at.exception, at.exception
    assert at.session_state["types"] == ("date", "bool")
    at.button[0].click().run()
    row = db.fetch("expenses", bid).iloc[0]
    assert row["amount"] == 250 and row["date"] == "2026-02-02" and row["fixed"] == 1


def test_daily_ai_limit(tmp_path, monkeypatch):
    uid = boot(tmp_path, monkeypatch, False)
    bid = db.get_business(uid)["id"]
    assert [db.take_ai_credit(bid, 2) for _ in range(3)] == [True, True, False]


def test_key_is_found_from_any_folder(tmp_path, monkeypatch):
    from pathlib import Path
    from till import views
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    fake = tmp_path / "app" / ".streamlit"
    fake.mkdir(parents=True)
    (fake / "secrets.toml").write_text('GROQ_API_KEY = " gsk_test "')
    monkeypatch.setattr(views, "__file__", str(tmp_path / "app" / "till" / "views.py"))
    monkeypatch.chdir(tmp_path)
    assert views.server_key() == "gsk_test"
    (fake / "secrets.toml").write_text('GROQ_API_KEY = "gsk_your_key_here"')
    assert views.server_key() is None
