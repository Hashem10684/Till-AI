"""Every screen in the app."""
from __future__ import annotations

import os
import tomllib
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from . import analytics as a
from . import copilot, db, demo, ui

CURRENCIES = ["USD", "EUR", "GBP", "AED", "SAR", "QAR", "EGP", "INR", "PKR", "NGN", "KES", "ZAR", "CAD", "AUD", "SGD"]
PERIODS = ["This month", "Last month", "3 mo", "1 year"]
TABLES = ["sales", "expenses", "products", "customers", "competitors", "goals", "tasks"]
OFFLINE = "Till's AI is offline right now. Your numbers still work."
LIMIT = f"You've used today's {copilot.DAILY_LIMIT} AI requests. They reset tomorrow."


def user_id() -> int:
    return st.session_state["user_id"]


def business() -> dict:
    return db.get_business(user_id())


def load() -> a.Data:
    b = business()
    return a.prepare(b, *[db.fetch(t, b["id"]) for t in TABLES])


def _key_from_file() -> str | None:
    """Reads .streamlit/secrets.toml beside app.py, whichever folder the app was started from."""
    folder = Path(__file__).resolve().parent.parent / ".streamlit"
    for name in ("secrets.toml", "secrets.toml.txt"):
        try:
            with open(folder / name, "rb") as file:
                return tomllib.load(file).get("GROQ_API_KEY")
        except (OSError, tomllib.TOMLDecodeError):
            continue
    return None


def server_key() -> str | None:
    """The single key the app owner sets. Users never see or supply one."""
    key = os.environ.get("GROQ_API_KEY") or _key_from_file()
    if not key:
        try:
            key = st.secrets.get("GROQ_API_KEY")
        except Exception:
            key = None
    key = (key or "").strip()
    if not key or "your_key_here" in key:
        print("Till: no GROQ_API_KEY found. Add it to .streamlit/secrets.toml beside app.py.", flush=True)
        return None
    return key


def page(name: str):
    return st.session_state["pages"][name]


def get_window(data: a.Data, choice: str) -> dict:
    if choice == "This month":
        return a.this_month(data)
    return a.window(data, {"Last month": 1, "3 mo": 3, "1 year": 12}[choice])


# Sign in and first run ---------------------------------------------------
def auth_page() -> None:
    st.markdown(ui.logo(), unsafe_allow_html=True)
    pitch, forms = st.columns([1.15, 1], gap="large")
    with pitch:
        ui.hero("Your side hustle, sorted.", "Make more. Keep more.", "Track what comes in, see what you keep, and get advice from an AI coach.")
    with forms:
        sign_up, sign_in = st.tabs(["Sign up", "Log in"])
        with sign_in, st.form("signin"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Log in", type="primary", width="stretch"):
                user = db.verify_user(email, password)
                if user:
                    st.session_state.update(user_id=user["id"], fresh_login=True)
                    st.rerun()
                st.error("That email and password don't match.")
        with sign_up, st.form("signup"):
            name = st.text_input("First name")
            email = st.text_input("Email", key="new_email")
            password = st.text_input("Password (8+ characters)", type="password", key="new_password")
            if st.form_submit_button("Create my account", type="primary", width="stretch"):
                if "@" not in email or len(password) < 8:
                    st.error("Enter a real email and a password with at least 8 characters.")
                else:
                    uid = db.create_user(email, name, password)
                    if uid:
                        st.session_state.update(user_id=uid, fresh_login=True)
                        st.rerun()
                    st.error("That email already has an account. Log in instead.")


def onboarding() -> None:
    _, middle, _ = st.columns([1, 2, 1])
    with middle:
        st.markdown(ui.logo(), unsafe_allow_html=True)
        st.title("What are you building?")
        st.write("Three quick questions and you're in.")
        with st.form("onboard"):
            name = st.text_input("What's it called?", placeholder="Maya's Cakes")
            what = st.text_input("What do you sell?", placeholder="Custom cakes for birthdays on campus")
            currency = st.selectbox("Your currency", CURRENCIES)
            if st.form_submit_button("Let's go", type="primary", width="stretch"):
                if name.strip():
                    db.save_business(user_id(), {"name": name.strip(), "description": what.strip(), "currency": currency, "stage": "Just starting"})
                    st.rerun()
                st.error("Give your business a name to continue.")
        if st.button("Just show me an example", width="stretch"):
            demo.load(db.save_business(user_id(), dict(demo.BUSINESS)))
            st.rerun()


# Quick logging -----------------------------------------------------------
@st.dialog("Money in")
def log_sale(data: a.Data) -> None:
    bid = data.business["id"]
    names = data.products["name"].tolist() if not data.products.empty else []
    with st.form("sale"):
        item = st.selectbox("What did you sell?", names, index=None, accept_new_options=True, placeholder="Pick one or type something new")
        total = st.number_input("How much did you get in total?", min_value=0.0, value=None, placeholder="0.00")
        left, right = st.columns(2)
        qty = left.number_input("How many?", min_value=1, value=1)
        when = right.date_input("When?", date.today())
        with st.expander("Add more detail"):
            cost = st.number_input("What did one cost you?", min_value=0.0, value=None, help="Skip this if you log your costs under Money out.")
            customer = st.text_input("Who bought it?")
        if st.form_submit_button("Save sale", type="primary", width="stretch"):
            if not item or not total:
                st.error("Add what you sold and how much you got.")
                return
            if item not in names:
                db.insert_many("products", bid, [{"name": item, "kind": "Product", "price": total / qty, "unit_cost": cost}])
            db.insert_many("sales", bid, [{"date": when, "item": item, "customer": customer, "qty": qty, "unit_price": total / qty, "unit_cost": cost, "channel": "Logged"}])
            st.session_state["toast"] = f"Nice! {a.money(total, data.business['currency'])} added."
            st.rerun()


@st.dialog("Money out")
def log_expense(data: a.Data) -> None:
    with st.form("expense"):
        category = st.selectbox("What was it for?", a.EXPENSE_CATEGORIES)
        amount = st.number_input("How much?", min_value=0.0, value=None, placeholder="0.00")
        when = st.date_input("When?", date.today())
        note = st.text_input("Note (optional)")
        repeat = st.checkbox("I pay this every month")
        if st.form_submit_button("Save cost", type="primary", width="stretch"):
            if not amount:
                st.error("Add how much you spent.")
                return
            db.insert_many("expenses", data.business["id"], [{"date": when, "category": category, "description": note, "amount": amount, "fixed": int(repeat)}])
            st.session_state["toast"] = "Saved."
            st.rerun()


def log_buttons(data: a.Data) -> None:
    left, right = st.columns(2)
    if left.button("Money in", icon=":material/add:", type="primary", width="stretch"):
        log_sale(data)
    if right.button("Money out", icon=":material/remove:", width="stretch"):
        log_expense(data)


# Home --------------------------------------------------------------------
def home() -> None:
    data = load()
    if "toast" in st.session_state:
        st.toast(copilot.safe_md(st.session_state.pop("toast")), icon=":material/celebration:")
    if not data.has_sales and not data.has_expenses:
        return first_run(data)
    cur = data.business["currency"]
    # Monthly bills land early in the month, so the first week would look worse than it is.
    default = "Last month" if data.today.day <= 7 and data.sales["date"].min().date() < data.today.replace(day=1) else "This month"
    choice = st.segmented_control("Period", PERIODS, default=default, key="period", label_visibility="collapsed") or default
    w = get_window(data, choice)
    c, p = w["current"], w["prior"]

    sticker, mood = None, ""
    if p:
        gap = c["net_profit"] - p["net_profit"]
        if abs(gap) >= 1:
            sticker, mood = (f"{a.money(gap, cur)} more than before", "up") if gap > 0 else (f"{a.money(-gap, cur)} less than before", "down")
    verb = "You kept" if c["net_profit"] >= 0 else "You're down"
    ui.hero(f"{verb} so far this month" if choice == "This month" else f"{verb} in {w['label']}", a.money(abs(c["net_profit"]), cur), a.story(data, w), sticker, mood)
    log_buttons(data)
    st.write("")

    best = a.product_table(data, w)
    columns = st.columns(3)
    ui.stat(columns[0], "sun", "Money in", a.money(c["revenue"], cur), f"from {c['orders']} orders")
    ui.stat(columns[1], "pink", "Money out", a.money(c["total_costs"], cur), "items, bills and everything else")
    ui.stat(columns[2], "mint", "Best seller", best.iloc[0]["item"] if not best.empty else "None yet",
            f"{a.money(best.iloc[0]['revenue'], cur)} in sales" if not best.empty else "Log a sale to see it")
    st.write("")

    left, right = st.columns([3, 2])
    with left.container(key="tile_chart"):
        st.subheader("Your months")
        months = a.monthly(data)
        if not months.empty:
            ui.show(ui.months_chart(months, a.SYMBOLS.get(cur, cur + " ")))
    found = a.signals(data, w)
    with right.container(key="tile_alerts"):
        st.subheader("Till noticed")
        if found:
            ui.signal_list(found[:3])
        else:
            st.write("Nothing to worry about right now.")
    st.write("")

    left, right = st.columns(2)
    with left.container(key="tile_move"):
        st.subheader("Your next move")
        next_move(data)
    with right.container(key="tile_todo"):
        st.subheader("To-do")
        task_rows(data, limit=3, key="home")
        st.page_link(page("plan"), label="See your full plan")
    st.write("")
    with st.expander("See the full breakdown"):
        breakdown(data, w, found)


def next_move(data: a.Data) -> None:
    saved = db.latest_insight(data.business["id"])
    if saved and saved["payload"]["actions"]:
        action = saved["payload"]["actions"][0]
        st.markdown(f"**{copilot.safe_md(action['title'])}**\n\n{copilot.safe_md(action['first_step'])}")
        st.page_link(page("plan"), label="See your game plan")
    else:
        st.write("Get the three moves that matter most for your business.")
        if st.button("Make my game plan", type="primary"):
            st.session_state["run_review"] = True
            st.switch_page(page("plan"))


def breakdown(data: a.Data, w: dict, found: list[dict]) -> None:
    cur = data.business["currency"]
    symbol = a.SYMBOLS.get(cur, cur + " ")
    money_tab, costs, items, days, more = st.tabs(["Money", "Costs", "Items", "Best days", "All alerts"])
    with money_tab:
        ui.pl_table(w, cur)
        cash = a.estimated_cash(data)
        if cash is not None:
            st.caption(copilot.safe_md(f"Estimated cash: {a.money(cash, cur)}. This doesn't include money people still owe you."))
    with costs:
        spend = a.expense_table(data, w)
        if spend.empty:
            st.write("Log some costs to see this.")
        else:
            ui.show(ui.bars(spend["category"].tolist(), spend["amount"].tolist(), symbol, [f"{s * 100:.0f}%" for s in spend["share"]]))
    with items:
        table = a.product_table(data, w).head(7)
        if not table.empty:
            labels = [f"keep {m * 100:.0f}%" if pd.notna(m) else "add a cost" for m in table["margin"]]
            ui.show(ui.bars(table["item"].tolist(), table["revenue"].tolist(), symbol, labels))
    with days:
        ui.show(ui.weekday_chart(a.weekday_table(data, w), symbol))
        st.caption("Average sales per day.")
    with more:
        if found:
            ui.signal_list(found)
        else:
            st.write("All clear.")


def first_run(data: a.Data) -> None:
    ui.hero(f"Welcome to {data.business['name']}", "Let's go.", "Log your first sale or cost and Till will start tracking what you keep.")
    log_buttons(data)
    st.write("")
    with st.container(key="tile_start"):
        st.subheader("Haven't started selling yet?")
        st.write("Ask Till to help you pick a price, find your first customers or plan your launch.")
        st.page_link(page("coach"), label="Ask Till", icon=":material/forum:")


# Ask Till ----------------------------------------------------------------
SUGGESTIONS = ["How do I make more money this month?", "Am I charging enough?", "What should I post to get more sales?", "What should I do this week?"]


def coach() -> None:
    data = load()
    bid = data.business["id"]
    key = server_key()
    head, clear = st.columns([5, 1], vertical_alignment="bottom")
    head.title("Ask Till")
    history = db.messages(bid)
    if history and clear.button("New chat", width="stretch"):
        db.clear_messages(bid)
        st.rerun()
    if not key:
        st.info(OFFLINE, icon=":material/cloud_off:")
    for message in history:
        with st.chat_message(message["role"], avatar=":material/sell:" if message["role"] == "assistant" else ":material/person:"):
            st.markdown(copilot.safe_md(message["content"]))

    typed = st.chat_input("Ask anything about your business", disabled=not key)
    question = typed or st.session_state.pop("pending_question", None)
    if not history and key and not question:
        st.write("Till knows your numbers, so ask away. It can't browse the web, so share what you know about your market.")
        columns = st.columns(2)
        for i, text in enumerate(SUGGESTIONS):
            if columns[i % 2].button(text, key=f"s{i}", width="stretch"):
                st.session_state["pending_question"] = text
                st.rerun()
    if not question:
        return
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(copilot.safe_md(question))
    if not db.take_ai_credit(bid, copilot.DAILY_LIMIT):
        st.warning(LIMIT)
        return
    db.add_message(bid, "user", question)
    parts: list[str] = []

    def stream():
        for piece in copilot.chat_stream(key, a.ai_context(data), db.messages(bid)):
            parts.append(piece)
            yield copilot.safe_md(piece)

    with st.chat_message("assistant", avatar=":material/sell:"):
        try:
            st.write_stream(stream())
        except copilot.AIError as exc:
            st.error(str(exc))
    if parts:
        db.add_message(bid, "assistant", "".join(parts))


# Plan --------------------------------------------------------------------
def goal_row(data: a.Data, goal: dict) -> None:
    achieved = a.goal_progress(data, goal)
    target = float(goal.get("target") or 0)
    ratio = max(0.0, min(achieved / target, 1.0)) if target > 0 else 0.0
    money_goal = goal.get("metric") in ("Sales", "Net profit")
    fmt = (lambda v: a.money(v, data.business["currency"])) if money_goal else (lambda v: f"{v:,.0f}")
    st.progress(ratio, text=copilot.safe_md(f"**{goal['title']}**: {fmt(achieved)} of {fmt(target)}"))


def task_rows(data: a.Data, limit: int | None = None, key: str = "plan") -> None:
    if data.tasks.empty:
        st.write("Nothing here yet.")
        return
    tasks = data.tasks[data.tasks["done"].fillna(0).astype(int) == 0]
    if tasks.empty:
        st.write("All done. Nice work.")
    for t in (tasks.head(limit) if limit else tasks).to_dict("records"):
        due = pd.to_datetime(t["due_date"], errors="coerce")
        note = "" if pd.isna(due) else f" ({due:%d %b})"
        if not pd.isna(due) and due.date() < data.today:
            note = " :red[(late)]"
        if st.checkbox(f"{copilot.safe_md(t['title'])}{note}", key=f"{key}_{t['id']}"):
            db.set_task_done(data.business["id"], int(t["id"]), True)
            st.rerun()


def run_review(data: a.Data, context: dict, fingerprint: str) -> None:
    key = server_key()
    if not key:
        st.info(OFFLINE, icon=":material/cloud_off:")
        return
    if not db.take_ai_credit(data.business["id"], copilot.DAILY_LIMIT):
        st.warning(LIMIT)
        return
    with st.spinner("Till is looking through your numbers"):
        try:
            result = copilot.review(key, context)
        except copilot.AIError as exc:
            st.error(str(exc))
            return
    db.save_insight(data.business["id"], fingerprint, result)
    st.rerun()


def game_plan(data: a.Data) -> None:
    bid = data.business["id"]
    context = a.ai_context(data)
    fingerprint = copilot.fingerprint(context)
    saved = db.latest_insight(bid)
    head, button = st.columns([3, 1], vertical_alignment="bottom")
    head.subheader("Your game plan")
    clicked = button.button("Update my plan" if saved else "Make my game plan", type="primary", width="stretch")
    if clicked or st.session_state.pop("run_review", False):
        run_review(data, context, fingerprint)
    if not saved:
        st.write("Till reads your numbers and picks the three moves that matter most.")
        return
    payload = saved["payload"]
    if saved["fingerprint"] != fingerprint:
        st.caption("Your numbers have changed since this plan was made.")
    st.write(copilot.safe_md(payload["summary"]))
    existing = set(data.tasks["title"]) if not data.tasks.empty else set()
    for i, item in enumerate(payload["actions"]):
        with st.container(key=f"tile_action{i}"):
            text, add = st.columns([4, 1], vertical_alignment="center")
            text.markdown(f"**{copilot.safe_md(item['title'])}**  \n{copilot.safe_md(item['why'])}  \nStart with: {copilot.safe_md(item['first_step'])}")
            added = item["title"] in existing
            if add.button("Added" if added else "Add to to-do", key=f"add{i}", disabled=added, width="stretch"):
                db.add_task(bid, item["title"], item["priority"], (data.today + timedelta(days=7)).isoformat(), "Till")
                st.rerun()
    with st.expander("See why"):
        for title, field in [("What's working", "strengths"), ("What's not", "weaknesses"), ("Chances to grow", "opportunities"), ("Things to watch", "threats")]:
            if payload[field]:
                st.markdown(f"**{title}**")
                for entry in payload[field]:
                    st.markdown(f"- {copilot.safe_md(entry['point'])}: {copilot.safe_md(entry['evidence'])}")
        if payload["unknowns"]:
            st.markdown("**What Till couldn't tell**")
            for unknown in payload["unknowns"]:
                st.markdown(f"- {copilot.safe_md(unknown)}")


def plan() -> None:
    data = load()
    bid = data.business["id"]
    st.title("Plan")
    game_plan(data)
    st.write("")
    left, right = st.columns(2, gap="medium")
    with left.container(key="tile_tasks"):
        st.subheader("To-do")
        task_rows(data)
        with st.form("task", clear_on_submit=True, border=False):
            title = st.text_input("Add something to do", label_visibility="collapsed", placeholder="Add something to do")
            if st.form_submit_button("Add") and title.strip():
                db.add_task(bid, title.strip())
                st.rerun()
    with right.container(key="tile_goals"):
        st.subheader("Goals")
        for g in data.goals.to_dict("records"):
            goal_row(data, g)
        with st.expander("Add a goal"):
            with st.form("goal", clear_on_submit=True, border=False):
                title = st.text_input("What's the goal?")
                kinds = {"Sales": "Money in", "New customers": "New customers", "Custom": "Something else"}
                metric = st.selectbox("Track", list(kinds), format_func=kinds.get)
                target = st.number_input("Target", min_value=0.0, step=10.0)
                due = st.date_input("Finish by", value=None)
                if st.form_submit_button("Add goal") and title.strip() and target > 0:
                    db.insert_many("goals", bid, [{"title": title.strip(), "metric": metric, "target": target, "progress": 0,
                                                   "start_date": date.today().isoformat(), "due_date": due.isoformat() if due else None}])
                    st.rerun()
        if not data.goals.empty:
            with st.expander("Edit goals"):
                editor("goals", bid, {"title": "Goal", "target": "Target", "progress": st.column_config.NumberColumn("Progress (for Something else goals)"),
                                      "due_date": st.column_config.DateColumn("Finish by")})


# Data grids and spreadsheet import -----------------------------------------
def problems(table: str, frame: pd.DataFrame) -> list[str]:
    errors = []
    for column in ("qty", "unit_price", "unit_cost", "amount", "price"):
        if column in frame and (pd.to_numeric(frame[column], errors="coerce") < 0).any():
            errors.append(f"{column.replace('_', ' ').capitalize()} can't be negative.")
    return errors


def editor(table: str, bid: int, config: dict, frame: pd.DataFrame | None = None) -> None:
    frame = db.fetch(table, bid) if frame is None else frame
    view = frame.copy()
    for column, spec in config.items():
        if isinstance(spec, dict) and spec.get("type_config", {}).get("type") == "date":
            view[column] = pd.to_datetime(view[column], errors="coerce").dt.date
        if isinstance(spec, dict) and spec.get("type_config", {}).get("type") == "checkbox":
            view[column] = view[column].fillna(0).astype(bool)
    version = st.session_state.get(f"v_{table}", 0)
    edited = st.data_editor(view, column_config=config, column_order=list(config), num_rows="dynamic", hide_index=True,
                            width="stretch", key=f"grid_{table}_{version}")
    if st.button("Save changes", key=f"save_{table}", type="primary"):
        errors = problems(table, edited)
        if errors:
            for e in errors:
                st.error(e)
            return
        result = db.sync(table, bid, edited, [int(i) for i in frame["id"]])
        st.session_state[f"v_{table}"] = version + 1
        note = f"Saved: {result['added']} added, {result['updated']} updated, {result['removed']} removed."
        if result["skipped"]:
            note += f" {result['skipped']} rows skipped because a required field is empty."
        st.toast(note)
        st.rerun()


SYNONYMS = {
    "date": ["date", "day", "sale date", "transaction date", "created"],
    "item": ["item", "product", "service", "description", "name"],
    "qty": ["qty", "quantity", "units", "count"],
    "unit_price": ["unit price", "price", "unit_price"],
    "total": ["total", "amount", "revenue", "sales", "net sales", "value"],
    "unit_cost": ["unit cost", "cost", "unit_cost"],
    "customer": ["customer", "client", "customer name", "buyer"],
    "category": ["category", "type", "account"],
    "description": ["description", "details", "memo", "note", "vendor", "supplier"],
    "amount": ["amount", "total", "value", "cost", "spent"],
}


def guess(field: str, columns: list[str]) -> int:
    lowered = [c.strip().lower() for c in columns]
    for word in SYNONYMS.get(field, []):
        if word in lowered:
            return lowered.index(word) + 1
    return 0


def importer(table: str, bid: int) -> None:
    fields = {"sales": [("date", True), ("item", True), ("qty", False), ("unit_price", False), ("total", False), ("unit_cost", False), ("customer", False)],
              "expenses": [("date", True), ("category", True), ("amount", True), ("description", False)]}[table]
    with st.expander("Import a spreadsheet"):
        file = st.file_uploader("Choose a CSV file", type="csv", key=f"csv_{table}_{st.session_state.get(f'v_{table}', 0)}")
        if not file:
            st.caption("Export from your till, bank or accounting software. Excel files can be saved as CSV.")
            return
        try:
            raw = pd.read_csv(file)
        except Exception:
            st.error("This file couldn't be read as a CSV. Save it as CSV from your spreadsheet app and try again.")
            return
        st.caption("Match your columns to Till's fields.")
        options = ["(not in my file)"] + list(raw.columns)
        columns = st.columns(len(fields))
        chosen = {}
        for column, (name, required) in zip(columns, fields):
            label = name.replace("_", " ").capitalize() + (" *" if required else "")
            chosen[name] = column.selectbox(label, options, guess(name, list(raw.columns)), key=f"map_{table}_{name}")
        st.dataframe(raw.head(5), hide_index=True, width="stretch")
        if st.button(f"Import {len(raw):,} rows", key=f"import_{table}", type="primary"):
            rows, rejected = clean_import(table, raw, {k: v for k, v in chosen.items() if v != options[0]})
            if rows is None:
                st.error(rejected)
                return
            db.insert_many(table, bid, rows)
            st.session_state[f"v_{table}"] = st.session_state.get(f"v_{table}", 0) + 1
            st.toast(f"Imported {len(rows):,} rows. {rejected} rows skipped because of a bad date or number.")
            st.rerun()


def clean_import(table: str, raw: pd.DataFrame, mapping: dict):
    need = {"sales": ["date", "item"], "expenses": ["date", "category", "amount"]}[table]
    missing = [n for n in need if n not in mapping]
    if missing:
        return None, "Match these required fields: " + ", ".join(missing) + "."
    if table == "sales" and "unit_price" not in mapping and "total" not in mapping:
        return None, "Match either Unit price or Total."

    def number(name):
        if name not in mapping:
            return pd.Series([None] * len(raw), dtype="float64")
        return pd.to_numeric(raw[mapping[name]].astype(str).str.replace(r"[^\d.\-]", "", regex=True), errors="coerce")

    dates = pd.to_datetime(raw[mapping["date"]], errors="coerce", format="mixed", dayfirst=False)
    text = lambda n: raw[mapping[n]].where(raw[mapping[n]].notna(), None) if n in mapping else [None] * len(raw)
    if table == "sales":
        qty = number("qty").fillna(1)
        price = number("unit_price")
        price = price.where(price.notna(), number("total") / qty.where(qty != 0))
        frame = pd.DataFrame({"date": dates, "item": text("item"), "customer": text("customer"), "qty": qty, "unit_price": price,
                              "unit_cost": number("unit_cost"), "channel": None})
        bad = frame["date"].isna() | frame["item"].isna() | frame["unit_price"].isna() | (frame["unit_price"] < 0)
    else:
        frame = pd.DataFrame({"date": dates, "category": text("category"), "description": text("description"),
                              "amount": number("amount").abs(), "fixed": 0})
        bad = frame["date"].isna() | frame["category"].isna() | frame["amount"].isna()
    return frame[~bad].to_dict("records"), int(bad.sum())


# My stuff ----------------------------------------------------------------
def profile_form(b: dict) -> None:
    with st.form("profile"):
        one, two = st.columns(2)
        name = one.text_input("Business name", b.get("name") or "")
        currency = two.selectbox("Currency", CURRENCIES, CURRENCIES.index(b["currency"]) if b.get("currency") in CURRENCIES else 0)
        what = st.text_area("What you sell", b.get("description") or "")
        who = st.text_area("Who buys from you", b.get("target_customers") or "")
        problem = st.text_area("Your biggest problem right now", b.get("challenge") or "")
        dream = st.text_area("Where you want to be in a year", b.get("ambition") or "")
        old_cash = float(b.get("opening_cash") or 0)
        cash = st.number_input("Cash you have in the business today (optional)", value=old_cash, step=10.0)
        if st.form_submit_button("Save", type="primary"):
            if name.strip():
                db.save_business(user_id(), {"name": name.strip(), "currency": currency, "description": what, "target_customers": who, "challenge": problem, "ambition": dream,
                                             "opening_cash": cash, "opening_cash_date": b.get("opening_cash_date") if cash == old_cash else date.today().isoformat()})
                st.toast("Saved.")
                st.rerun()
            st.error("Your business needs a name.")
    st.caption("Till's AI runs on Groq. When you use it, a summary of your numbers, including customer names, is sent there to get your answer.")
    left, right = st.columns(2)
    if left.button("Log out", width="stretch"):
        st.session_state.clear()
        st.rerun()
    with right.popover("Delete my data", width="stretch"):
        st.write("This can't be undone.")
        if st.button("Clear all my records"):
            db.clear_business_data(b["id"])
            st.rerun()
        if st.button("Delete my account"):
            db.delete_user(user_id())
            st.session_state.clear()
            st.rerun()


def stuff() -> None:
    data = load()
    b = data.business
    bid = b["id"]
    st.title("My stuff")
    tabs = st.tabs(["Sales", "Costs", "What I sell", "Customers", "Competitors", "Profile"])
    with tabs[0]:
        frame = db.fetch("sales", bid)
        if len(frame) > 200:
            st.caption(f"Your latest 200 of {len(frame):,} sales.")
        editor("sales", bid, {"date": st.column_config.DateColumn("Date", required=True), "item": st.column_config.TextColumn("Item", required=True), "customer": "Customer",
                              "qty": st.column_config.NumberColumn("How many", min_value=0), "unit_price": st.column_config.NumberColumn("Price each", min_value=0, required=True)}, frame.head(200))
        importer("sales", bid)
    with tabs[1]:
        frame = db.fetch("expenses", bid)
        if len(frame) > 200:
            st.caption(f"Your latest 200 of {len(frame):,} costs.")
        editor("expenses", bid, {"date": st.column_config.DateColumn("Date", required=True), "category": st.column_config.SelectboxColumn("For", options=a.EXPENSE_CATEGORIES, required=True),
                                 "description": "Note", "amount": st.column_config.NumberColumn("Amount", min_value=0, required=True), "fixed": st.column_config.CheckboxColumn("Monthly")}, frame.head(200))
        importer("expenses", bid)
    with tabs[2]:
        editor("products", bid, {"name": st.column_config.TextColumn("Name", required=True), "price": st.column_config.NumberColumn("Price", min_value=0),
                                 "unit_cost": st.column_config.NumberColumn("Costs me", min_value=0), "stock": st.column_config.NumberColumn("In stock"), "reorder_level": st.column_config.NumberColumn("Restock at")})
    with tabs[3]:
        editor("customers", bid, {"name": st.column_config.TextColumn("Name", required=True), "notes": "Notes"})
    with tabs[4]:
        st.caption("Till can't browse the web, so tell it who you're up against.")
        editor("competitors", bid, {"name": st.column_config.TextColumn("Name", required=True), "pricing": "Their prices", "strengths": "What they do well", "weaknesses": "Where they fall short"})
    with tabs[5]:
        profile_form(b)
