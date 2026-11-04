"""All business maths lives here. The AI receives these results and never calculates them itself."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

STOCK_CATEGORY = "Stuff I bought to sell"
EXPENSE_CATEGORIES = [STOCK_CATEGORY, "Shipping and packaging", "Ads and promo", "App and platform fees",
                      "Tools and supplies", "Rent or storage", "Pay for helpers", "Other"]
MIN_COST_COVERAGE = 0.5


@dataclass
class Data:
    business: dict
    sales: pd.DataFrame
    expenses: pd.DataFrame
    products: pd.DataFrame
    customers: pd.DataFrame
    competitors: pd.DataFrame
    goals: pd.DataFrame
    tasks: pd.DataFrame
    today: date = field(default_factory=date.today)
    cost_basis: str = "unit_costs"
    cost_coverage: float = 0.0

    @property
    def has_sales(self) -> bool:
        return not self.sales.empty

    @property
    def has_expenses(self) -> bool:
        return not self.expenses.empty


def prepare(business, sales, expenses, products, customers, competitors, goals, tasks, today=None) -> Data:
    today = today or date.today()
    sales = sales.copy()
    for col in ("qty", "unit_price", "unit_cost"):
        sales[col] = pd.to_numeric(sales[col], errors="coerce")
    sales["qty"] = sales["qty"].fillna(1)
    sales["date"] = pd.to_datetime(sales["date"], errors="coerce")
    sales = sales.dropna(subset=["date", "unit_price"])
    if not products.empty and not sales.empty:
        known = dict(zip(products["name"], pd.to_numeric(products["unit_cost"], errors="coerce")))
        sales["unit_cost"] = sales["unit_cost"].where(sales["unit_cost"].notna(), sales["item"].map(known))
    sales["revenue"] = sales["qty"] * sales["unit_price"]
    sales["has_cost"] = sales["unit_cost"].notna()
    sales["cogs"] = (sales["qty"] * sales["unit_cost"]).fillna(0.0)

    expenses = expenses.copy()
    expenses["amount"] = pd.to_numeric(expenses["amount"], errors="coerce")
    expenses["date"] = pd.to_datetime(expenses["date"], errors="coerce")
    expenses = expenses.dropna(subset=["date", "amount"])
    expenses["fixed"] = pd.to_numeric(expenses["fixed"], errors="coerce").fillna(0).astype(bool)

    total = sales["revenue"].sum()
    coverage = float(sales.loc[sales["has_cost"], "revenue"].sum() / total) if total > 0 else 0.0
    # Counting unit costs and stock purchases together would charge the same goods twice.
    basis = "unit_costs" if coverage >= MIN_COST_COVERAGE else "purchases"
    return Data(business, sales, expenses, products, customers, competitors, goals, tasks, today, basis, coverage)


def _between(frame: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    return frame[(frame["date"] >= pd.Timestamp(start)) & (frame["date"] <= pd.Timestamp(end))]


def period(data: Data, start: date, end: date) -> dict:
    s, e = _between(data.sales, start, end), _between(data.expenses, start, end)
    revenue = float(s["revenue"].sum())
    stock = float(e.loc[e["category"] == STOCK_CATEGORY, "amount"].sum())
    operating = float(e.loc[e["category"] != STOCK_CATEGORY, "amount"].sum())
    cogs = float(s["cogs"].sum()) if data.cost_basis == "unit_costs" else stock
    gross = revenue - cogs
    net = gross - operating
    orders = _orders(s)
    return {
        "revenue": revenue, "cogs": cogs, "gross_profit": gross,
        "gross_margin": gross / revenue if revenue else None,
        "operating_expenses": operating, "total_costs": cogs + operating,
        "net_profit": net, "net_margin": net / revenue if revenue else None,
        "orders": orders, "avg_order": revenue / orders if orders else None,
        "customers": int(s["customer"].dropna().nunique()),
    }


def _orders(sales: pd.DataFrame) -> int:
    if sales.empty:
        return 0
    return int(sales.assign(c=sales["customer"].fillna("")).groupby(["date", "c", "channel"], dropna=False).ngroups)


def _full_month_end(today: date) -> date:
    """The last day of the most recent complete month."""
    month_end = pd.Timestamp(today).to_period("M").end_time.date()
    return today if today == month_end else today.replace(day=1) - timedelta(days=1)


def window(data: Data, months: int = 3) -> dict:
    """Whole calendar months, so each period holds the same number of rent and wage bills."""
    end = _full_month_end(data.today)
    last = pd.Timestamp(end).to_period("M")
    start = (last - (months - 1)).start_time.date()
    first_record = min([f["date"].min() for f in (data.sales, data.expenses) if not f.empty], default=None)
    if first_record is not None and first_record.date() > end:
        # A business younger than one complete month is shown month to date.
        start = data.today.replace(day=1)
        return {"months": 1, "start": start, "end": data.today, "label": "so far this month",
                "current": period(data, start, data.today), "prior": None}
    prior_end = start - timedelta(days=1)
    prior_start = (pd.Timestamp(prior_end).to_period("M") - (months - 1)).start_time.date()
    # A comparison is only fair when the earlier period is covered by records (a week's grace).
    comparable = data.has_sales and data.sales["date"].min() <= pd.Timestamp(prior_start + timedelta(days=7))
    label = f"{start:%B %Y}" if months == 1 else f"{start:%b %Y} to {end:%b %Y}"
    return {"months": months, "start": start, "end": end, "label": label, "current": period(data, start, end),
            "prior": period(data, prior_start, prior_end) if comparable else None}


def this_month(data: Data) -> dict:
    """Month to date, compared with the same number of days last month."""
    start = data.today.replace(day=1)
    prior_end = start - timedelta(days=1)
    prior_start = prior_end.replace(day=1)
    same_day = prior_start.replace(day=min(data.today.day, prior_end.day))
    comparable = data.has_sales and data.sales["date"].min() <= pd.Timestamp(prior_start + timedelta(days=7))
    return {"months": 1, "start": start, "end": data.today, "label": f"{start:%B} so far",
            "current": period(data, start, data.today),
            "prior": period(data, prior_start, same_day) if comparable else None}


def change(current: float | None, prior: float | None) -> float | None:
    if current is None or prior is None or prior <= 0:
        return None
    return (current - prior) / prior


def monthly(data: Data, months: int = 14) -> pd.DataFrame:
    this_month = pd.Timestamp(data.today).to_period("M")
    rows = []
    for offset in range(months - 1, -1, -1):
        month = this_month - offset
        start, end = month.start_time.date(), month.end_time.date()
        if data.today < end:
            end = data.today
        rows.append({"month": month.to_timestamp(), "label": month.strftime("%b %y"),
                     "partial": month == this_month and data.today != month.end_time.date(),
                     **period(data, start, end)})
    frame = pd.DataFrame(rows)
    active = frame[(frame["revenue"] > 0) | (frame["total_costs"] > 0)]
    return frame.loc[active.index.min():].reset_index(drop=True) if not active.empty else frame.iloc[0:0]


def product_table(data: Data, w: dict) -> pd.DataFrame:
    s = _between(data.sales, w["start"], w["end"])
    if s.empty:
        return pd.DataFrame(columns=["item", "revenue", "qty", "gross_profit", "margin", "share", "has_cost"])
    g = s.groupby("item").agg(revenue=("revenue", "sum"), qty=("qty", "sum"), cogs=("cogs", "sum"),
                              has_cost=("has_cost", "all")).reset_index()
    g["gross_profit"] = g["revenue"] - g["cogs"]
    g["margin"] = (g["gross_profit"] / g["revenue"]).where(g["has_cost"] & (g["revenue"] > 0))
    g["share"] = g["revenue"] / g["revenue"].sum()
    return g.sort_values("revenue", ascending=False).reset_index(drop=True)


def customer_table(data: Data) -> pd.DataFrame:
    s = data.sales[data.sales["customer"].notna()]
    if s.empty:
        return pd.DataFrame(columns=["customer", "revenue", "visits", "first", "last", "days_since"])
    cutoff = pd.Timestamp(data.today - timedelta(days=364))
    g = s.groupby("customer").agg(first=("date", "min"), last=("date", "max"), visits=("date", "nunique")).reset_index()
    recent = s[s["date"] >= cutoff].groupby("customer")["revenue"].sum()
    g["revenue"] = g["customer"].map(recent).fillna(0.0)
    g["days_since"] = (pd.Timestamp(data.today) - g["last"]).dt.days
    return g.sort_values("revenue", ascending=False).reset_index(drop=True)


def customer_summary(data: Data, w: dict) -> dict:
    table = customer_table(data)
    start = pd.Timestamp(w["start"])
    s = _between(data.sales, w["start"], w["end"])
    named = s[s["customer"].notna()]
    named_share = float(named["revenue"].sum() / s["revenue"].sum()) if s["revenue"].sum() else 0.0
    if table.empty:
        return {"named_share": named_share, "known": 0, "active": 0, "new": 0, "repeat_rate": None,
                "top_name": None, "top_share": None, "dormant": []}
    by_customer = named.groupby("customer")["revenue"].sum().sort_values(ascending=False)
    total_named = by_customer.sum()
    visits = named.groupby("customer")["date"].nunique()
    dormant = table[(table["visits"] >= 3) & (table["days_since"] >= 60)]
    return {
        "named_share": named_share, "known": len(table), "active": int(len(by_customer)),
        "new": int((table["first"] >= start).sum()),
        "repeat_rate": float((visits >= 2).mean()) if len(visits) else None,
        "top_name": by_customer.index[0] if len(by_customer) else None,
        "top_share": float(by_customer.iloc[0] / s["revenue"].sum()) if len(by_customer) else None,
        "dormant": dormant[["customer", "days_since", "revenue"]].to_dict("records"),
    }


def expense_table(data: Data, w: dict) -> pd.DataFrame:
    e = _between(data.expenses, w["start"], w["end"])
    if data.cost_basis == "unit_costs":
        e = e[e["category"] != STOCK_CATEGORY]
    if e.empty:
        return pd.DataFrame(columns=["category", "amount", "share"])
    g = e.groupby("category")["amount"].sum().sort_values(ascending=False).reset_index()
    g["share"] = g["amount"] / g["amount"].sum()
    return g


def weekday_table(data: Data, w: dict) -> pd.DataFrame:
    s = _between(data.sales, w["start"], w["end"])
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    daily = s.groupby("date")["revenue"].sum()
    if daily.empty:
        return pd.DataFrame({"day": names, "average": [0.0] * 7})
    index = pd.date_range(max(daily.index.min(), pd.Timestamp(w["start"])), pd.Timestamp(w["end"]))
    daily = daily.reindex(index, fill_value=0.0)
    average = daily.groupby(daily.index.dayofweek).mean().reindex(range(7), fill_value=0.0)
    return pd.DataFrame({"day": names, "average": average.values})


def estimated_cash(data: Data) -> float | None:
    """Opening cash plus money in, less money out. Ignores credit terms, so it is an estimate."""
    opening = data.business.get("opening_cash")
    if not opening or (not data.has_sales and not data.has_expenses):
        return None
    since = pd.Timestamp(data.business.get("opening_cash_date") or "1900-01-01")
    s = data.sales[(data.sales["date"] >= since) & (data.sales["date"] <= pd.Timestamp(data.today))]
    e = data.expenses[(data.expenses["date"] >= since) & (data.expenses["date"] <= pd.Timestamp(data.today))]
    purchases = float(e.loc[e["category"] == STOCK_CATEGORY, "amount"].sum())
    other = float(e.loc[e["category"] != STOCK_CATEGORY, "amount"].sum())
    goods = purchases if purchases > 0 else float(s["cogs"].sum())
    return float(opening) + float(s["revenue"].sum()) - goods - other


def monthly_fixed_costs(data: Data) -> float | None:
    w = window(data, 3)
    e = _between(data.expenses, w["start"], w["end"])
    e = e[e["fixed"] & (e["category"] != STOCK_CATEGORY)]
    if e.empty:
        return None
    return float(e["amount"].sum()) / max(e["date"].dt.to_period("M").nunique(), 1)


def break_even(data: Data) -> float | None:
    """Monthly sales needed to cover fixed costs at the recent gross margin."""
    fixed = monthly_fixed_costs(data)
    margin = window(data, 3)["current"]["gross_margin"]
    if not fixed or margin is None or margin <= 0:
        return None
    return fixed / margin


def runway_months(data: Data) -> float | None:
    cash = estimated_cash(data)
    w = window(data, 3)
    net = w["current"]["net_profit"]
    if cash is None or net >= 0 or cash <= 0:
        return None
    return cash / (-net / w["months"])


def goal_progress(data: Data, goal: dict) -> float:
    metric = goal.get("metric") or "Custom"
    if metric == "Custom":
        return float(goal.get("progress") or 0)
    start = pd.to_datetime(goal.get("start_date"), errors="coerce")
    start = data.today.replace(day=1) if pd.isna(start) else start.date()
    due = pd.to_datetime(goal.get("due_date"), errors="coerce")
    end = data.today if pd.isna(due) else min(due.date(), data.today)
    p = period(data, start, end)
    if metric == "Sales":
        return p["revenue"]
    if metric == "Net profit":
        return p["net_profit"]
    if metric == "New customers":
        table = customer_table(data)
        if table.empty:
            return 0.0
        return float(((table["first"] >= pd.Timestamp(start)) & (table["first"] <= pd.Timestamp(end))).sum())
    return float(goal.get("progress") or 0)


SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹", "CAD": "CA$", "AUD": "A$"}


def money(value: float | None, currency: str) -> str:
    if value is None:
        return "n/a"
    sign = "-" if value < 0 else ""
    symbol = SYMBOLS.get(currency)
    return f"{sign}{symbol}{abs(value):,.0f}" if symbol else f"{sign}{currency} {abs(value):,.0f}"


def pct(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value * 100:.{digits}f}%"


def headline(data: Data, w: dict) -> str:
    """The plain-English sentence at the top of the dashboard."""
    cur = data.business.get("currency", "USD")
    c, p = w["current"], w["prior"]
    if not data.has_sales:
        return "Add your first sales and costs, and this page will show how the business is doing."
    if c["revenue"] == 0:
        return "No sales are recorded for this period."
    if not data.has_expenses:
        return f"You sold {money(c['revenue'], cur)}. Add your costs to see what you kept."
    verb = "kept" if c["net_profit"] >= 0 else "lost"
    first = f"You sold {money(c['revenue'], cur)} and {verb} {money(abs(c['net_profit']), cur)}."
    growth = change(c["revenue"], p["revenue"]) if p else None
    if growth is None:
        return first
    sales_part = f"Sales are {'up' if growth >= 0 else 'down'} {abs(growth) * 100:.0f}%"
    if c["net_margin"] is None or p["net_margin"] is None or c["net_margin"] < 0 or p["net_margin"] < 0:
        return f"{first} {sales_part}."
    gap = c["net_margin"] - p["net_margin"]
    if abs(gap) < 0.005:
        return f"{first} {sales_part}, and you keep about the same share of each sale."
    worse = gap < 0
    joiner = "but" if (growth >= 0) == worse else "and"
    return f"{first} {sales_part}, {joiner} you keep {'less' if worse else 'more'} of each sale: {c['net_margin'] * 100:.0f}% now, {p['net_margin'] * 100:.0f}% before."


def story(data: Data, w: dict) -> str:
    """One short line under the big number on Home."""
    c, p = w["current"], w["prior"]
    if c["revenue"] == 0:
        return "No sales logged for this period yet."
    if not data.has_expenses and data.cost_basis == "purchases":
        return "Log what you spent to see what you really kept."
    keep = f"You keep {c['net_margin'] * 100:.0f}% of what you make." if c["net_margin"] and c["net_margin"] > 0 else "Right now, more is going out than coming in."
    growth = change(c["revenue"], p["revenue"]) if p else None
    if growth is None or c["net_margin"] is None or p["net_margin"] is None:
        return keep
    trend = f"Money in is {'up' if growth >= 0 else 'down'} {abs(growth) * 100:.0f}%"
    if p["net_margin"] > 0 and c["net_margin"] > 0:
        gap = c["net_margin"] - p["net_margin"]
        if abs(gap) >= 0.005:
            word = "but" if (growth >= 0) == (gap < 0) else "and"
            return f"{trend}, {word} you're keeping {'less' if gap < 0 else 'more'} of it: {c['net_margin'] * 100:.0f}% now, {p['net_margin'] * 100:.0f}% before."
    return f"{trend}. {keep}"


def signals(data: Data, w: dict | None = None) -> list[dict]:
    """Rule-based checks. Severity is one of critical, warning, good, info."""
    cur = data.business.get("currency", "USD")
    out: list[dict] = []

    def add(severity, title, detail):
        out.append({"severity": severity, "title": title, "detail": detail})

    w = w or window(data, 3)
    if data.has_sales:
        c, p = w["current"], w["prior"]
        gap = (pd.Timestamp(data.today) - data.sales["date"].max()).days
        if gap >= 14:
            add("warning", f"No sales recorded for {gap} days", "If you made sales, log them so your numbers stay true.")
        if data.has_expenses and c["revenue"] > 0 and c["net_profit"] < 0:
            add("critical", "You are losing money", f"You spent {money(-c['net_profit'], cur)} more than you made in {w['label']}.")
        if p:
            growth = change(c["revenue"], p["revenue"])
            if growth is not None and growth <= -0.10:
                add("critical" if growth <= -0.25 else "warning", f"Sales dropped {-growth * 100:.0f}%", f"{money(c['revenue'], cur)} against {money(p['revenue'], cur)} in the period before.")
            elif growth is not None and growth >= 0.10:
                add("good", f"Sales grew {growth * 100:.0f}%", f"{money(c['revenue'], cur)} against {money(p['revenue'], cur)} in the period before.")
            if c["gross_margin"] is not None and p["gross_margin"] is not None:
                drop = p["gross_margin"] - c["gross_margin"]
                if drop >= 0.03:
                    add("warning", "Your items are earning you less", f"After item costs you keep {pct(c['gross_margin'], 0)} of each sale, down from {pct(p['gross_margin'], 0)}. Your costs may have gone up, or it might be time to raise prices.")
            opex_growth = change(c["operating_expenses"], p["operating_expenses"])
            if opex_growth is not None and growth is not None and opex_growth > growth + 0.05 and opex_growth >= 0.05:
                add("warning", "Bills are growing faster than sales", f"Bills moved {opex_growth * 100:+.0f}% while sales moved {growth * 100:+.0f}%.")

        items = product_table(data, w)
        if len(items) >= 2 and items.iloc[0]["share"] >= 0.40:
            add("warning", f"{items.iloc[0]['item']} is {items.iloc[0]['share'] * 100:.0f}% of sales", "Most of your money comes from one item. A backup would be safer.")
        low = items[(items["margin"].notna()) & (items["margin"] < 0.20) & (items["share"] >= 0.03)]
        for row in low.head(3).to_dict("records"):
            add("warning", f"{row['item']} barely pays", f"It brought in {money(row['revenue'], cur)}, but only {money(row['gross_profit'], cur)} was left after what it cost you.")

        cs = customer_summary(data, w)
        if cs["top_share"] is not None and cs["top_share"] >= 0.20:
            add("warning", f"{cs['top_name']} is {cs['top_share'] * 100:.0f}% of sales", "Losing this one customer would really hurt. Start building a backup.")
        if cs["dormant"]:
            lost = sum(d["revenue"] for d in cs["dormant"])
            add("warning", f"{len(cs['dormant'])} regulars have gone quiet", f"No orders in 60+ days. They spent {money(lost, cur)} with you last year. A quick message could bring them back.")

        be = break_even(data)
        if be:
            run_rate = window(data, 3)["current"]["revenue"] / window(data, 3)["months"]
            add("good" if run_rate >= be * 1.2 else "warning", f"You need about {money(be, cur)} a month to cover your regular bills",
                f"You are averaging {money(run_rate, cur)} a month, {'a comfortable' if run_rate >= be * 1.2 else 'a thin'} cushion." if run_rate >= be else f"You are averaging {money(run_rate, cur)} a month, below break-even.")
        if data.cost_basis == "unit_costs" and data.cost_coverage < 0.95:
            add("info", "Some items have no cost yet", "Add what each item costs you so your profit is accurate.")
        no_stock = not (data.expenses["category"] == STOCK_CATEGORY).any() if data.has_expenses else True
        if data.cost_basis == "purchases" and no_stock:
            add("info", "Your profit may look too high", "Log what you paid for the things you sell.")

    if not data.products.empty:
        stock = pd.to_numeric(data.products["stock"], errors="coerce")
        reorder = pd.to_numeric(data.products["reorder_level"], errors="coerce")
        low_stock = data.products[stock.notna() & reorder.notna() & (stock <= reorder)]
        if not low_stock.empty:
            add("warning", f"{len(low_stock)} {'item needs' if len(low_stock) == 1 else 'items need'} reordering", ", ".join(low_stock["name"].head(5)))

    cash = estimated_cash(data)
    if cash is not None and cash < 0:
        add("critical", "Estimated cash is negative", "Your records show more going out than coming in. Check for sales you forgot to log.")
    runway = runway_months(data)
    if runway is not None and runway < 6:
        add("critical" if runway < 3 else "warning", f"About {runway:.1f} months of cash left", "At the recent rate of loss.")

    if data.has_sales and not data.has_expenses:
        add("info", "No expenses recorded yet", "Log what you spend so Till can work out what you actually keep.")
    if not data.tasks.empty:
        open_tasks = data.tasks[data.tasks["done"].fillna(0).astype(int) == 0]
        due = pd.to_datetime(open_tasks["due_date"], errors="coerce")
        overdue = int((due < pd.Timestamp(data.today)).sum())
        if overdue:
            add("info", f"{overdue} {'task is' if overdue == 1 else 'tasks are'} overdue", "Check your to-do list on the Plan page.")

    rank = {"critical": 0, "warning": 1, "good": 2, "info": 3}
    return sorted(out, key=lambda s: rank[s["severity"]])


def _r(value, digits=2):
    return None if value is None or pd.isna(value) else round(float(value), digits)


def ai_context(data: Data, months: int = 3) -> dict:
    """The complete fact sheet handed to the model."""
    b = data.business
    w = window(data, months)
    clean = lambda p: {k: _r(v, 3 if "margin" in k else 2) for k, v in p.items()} if p else None
    open_tasks, goals = [], []
    if not data.tasks.empty:
        t = data.tasks[data.tasks["done"].fillna(0).astype(int) == 0]
        open_tasks = t[["title", "priority", "due_date"]].where(t[["title", "priority", "due_date"]].notna(), None).head(15).to_dict("records")
    if not data.goals.empty:
        goals = [{"title": g["title"], "metric": g["metric"], "target": _r(g["target"]),
                  "achieved_so_far": _r(goal_progress(data, g)), "due_date": g["due_date"]}
                 for g in data.goals.to_dict("records")]
    months = monthly(data, 13)
    return {
        "today": data.today.isoformat(),
        "business": {k: b.get(k) for k in ("name", "type", "location", "currency", "description", "target_customers", "stage", "staff", "challenge", "ambition")},
        "data_available": {"sales_rows": len(data.sales), "expense_rows": len(data.expenses), "products": len(data.products),
                           "customers": len(data.customers), "competitors": len(data.competitors),
                           "share_of_sales_with_unit_cost": _r(data.cost_coverage),
                           "cost_method": "unit costs on sales" if data.cost_basis == "unit_costs" else "stock purchases"},
        "last_period": {"period": w["label"], "current": clean(w["current"]), "previous_same_length": clean(w["prior"])},
        "monthly": [{"month": r["label"], "partial_month": bool(r["partial"]), "sales": _r(r["revenue"], 0),
                     "gross_margin": _r(r["gross_margin"], 3), "running_costs": _r(r["operating_expenses"], 0),
                     "net_profit": _r(r["net_profit"], 0)} for r in months.to_dict("records")],
        "items": [{"item": r["item"], "sales": _r(r["revenue"], 0), "units_sold": _r(r["qty"], 0), "margin": _r(r["margin"], 3),
                   "share_of_sales": _r(r["share"], 3)} for r in product_table(data, w).head(20).to_dict("records")],
        "catalogue": data.products[["name", "kind", "price", "unit_cost", "stock", "reorder_level"]].astype(object).where(data.products[["name", "kind", "price", "unit_cost", "stock", "reorder_level"]].notna(), None).head(40).to_dict("records") if not data.products.empty else [],
        "customers": customer_summary(data, w) | {"top_customers": [
            {"name": r["customer"], "sales_last_12_months": _r(r["revenue"], 0), "visits": int(r["visits"]), "days_since_last": int(r["days_since"])}
            for r in customer_table(data).head(10).to_dict("records")]},
        "expenses_by_category": [{"category": r["category"], "amount": _r(r["amount"], 0), "share": _r(r["share"], 3)} for r in expense_table(data, w).to_dict("records")],
        "average_sales_by_weekday": {r["day"]: _r(r["average"], 0) for r in weekday_table(data, w).to_dict("records")} if data.has_sales else {},
        "cash": {"estimated_cash": _r(estimated_cash(data), 0), "months_of_runway_if_losing_money": _r(runway_months(data), 1),
                 "monthly_fixed_costs": _r(monthly_fixed_costs(data), 0), "break_even_monthly_sales": _r(break_even(data), 0)},
        "competitors_entered_by_owner": data.competitors.drop(columns=["id"]).astype(object).where(data.competitors.drop(columns=["id"]).notna(), None).to_dict("records") if not data.competitors.empty else [],
        "goals": goals, "open_tasks": open_tasks,
        "automatic_checks": signals(data, w),
    }
