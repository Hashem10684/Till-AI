"""A fictional student side hustle with deliberate problems for Till to find."""
from __future__ import annotations

import random
from datetime import date, timedelta

from . import analytics, db

BUSINESS = {
    "name": "Second Round Thrift (sample)", "type": "Student thrift reselling", "location": "College town", "currency": "USD",
    "description": "I find vintage clothes at thrift stores, clean them up and resell on Depop, Instagram and at campus pop-ups. I also make custom totes.",
    "target_customers": "College students who want cheap, unique clothes.", "stage": "Growing fast", "staff": 1,
    "challenge": "I'm selling more than ever but I don't feel like I'm making more.",
    "ambition": "Make enough to cover my rent by graduation.",
}
ITEMS = [  # name, kind, category, price, cost at start, weight, stock, reorder, price rises with sourcing
    ("Vintage tee", "Product", "Clothes", 22, 7.0, 30, 34, 10, True),
    ("Y2K hoodie", "Product", "Clothes", 38, 15.0, 16, 9, 12, True),
    ("Denim jacket", "Product", "Clothes", 58, 24.0, 10, 11, 4, True),
    ("Custom tote", "Product", "Made by me", 16, 13.5, 14, 22, 8, False),
    ("Sticker pack", "Product", "Made by me", 6, 1.2, 20, 140, 30, False),
    ("Clothing alterations", "Service", "Services", 20, 3.0, 6, None, None, False),
]
CUSTOMERS = ["Maya", "Jordan", "Aisha", "Leo", "Zoe", "Omar", "Priya", "Ethan", "Nina", "Tariq", "Sofia", "Ben"]
QUIET = {"Aisha", "Ethan", "Sofia"}
CAMPUS_STORE = "Campus Store"
COMPETITORS = [
    {"name": "Big Depop sellers", "pricing": "About the same", "strengths": "Lots of followers, fast shipping", "weaknesses": "Nothing local, no pop-ups"},
    {"name": "Student union clothes swap", "pricing": "Free", "strengths": "Popular every term", "weaknesses": "Only twice a year, random stock"},
]


def load(business_id: int, today: date | None = None) -> None:
    today = today or date.today()
    rng = random.Random(11)
    db.clear_business_data(business_id)
    start = today - timedelta(days=430)
    db.save_business_cash(business_id, 400, start.isoformat())

    db.insert_many("products", business_id, [
        {"name": n, "kind": k, "category": c, "price": p, "unit_cost": round(co * 1.45, 2) if rises else co,
         "stock": s, "reorder_level": r} for n, k, c, p, co, _, s, r, rises in ITEMS])
    db.insert_many("customers", business_id, [{"name": c, "segment": "Regular"} for c in CUSTOMERS] +
                   [{"name": CAMPUS_STORE, "segment": "Bulk buyer", "notes": "Buys hoodies in bulk every Monday."}])
    db.insert_many("competitors", business_id, COMPETITORS)

    sales, expenses = [], []
    weights = [i[5] for i in ITEMS]
    for offset in range((today - start).days + 1):
        day = start + timedelta(days=offset)
        progress = offset / 430
        term = 0.65 if day.month in (6, 7, 8) else 1.2 if day.month in (9, 10, 11) else 1.0
        weekend = 1.5 if day.weekday() in (5, 6) else 1.0
        for _ in range(max(int(rng.gauss(1.3 + 1.5 * progress, 0.9) * term * weekend), 0)):
            name, _, _, price, cost, _, _, _, rises = rng.choices(ITEMS, weights=weights)[0]
            # Thrift prices climb 45% across the period while the seller's prices stay flat.
            uplift = 1 + 0.45 * progress ** 2 if rises else 1
            person = rng.choice(CUSTOMERS) if rng.random() < 0.45 else None
            if person in QUIET and day > today - timedelta(days=75):
                person = None
            sales.append({"date": day.isoformat(), "item": name, "customer": person, "qty": rng.choice([1, 1, 1, 2]),
                          "unit_price": price, "unit_cost": round(cost * uplift, 2),
                          "channel": rng.choice(["Depop", "Depop", "Instagram", "Campus pop-up"])})
        if day.weekday() == 0 and offset > 150:
            sales.append({"date": day.isoformat(), "item": "Y2K hoodie", "customer": CAMPUS_STORE, "qty": 4, "unit_price": 30,
                          "unit_cost": round(15 * (1 + 0.45 * progress ** 2), 2), "channel": "Bulk order"})
        if day.day == 1:
            for category, text, amount, fixed in [
                ("Rent or storage", "Storage locker", 140 if progress > 0.78 else 60, 1),
                ("App and platform fees", "Depop and card fees", rng.randint(70, 120) + int(70 * progress), 0),
                ("Shipping and packaging", "Mailers and postage", rng.randint(60, 90) + int(90 * progress), 0),
                ("Ads and promo", "Instagram ads", 120 if progress > 0.7 else 30, 0),
                ("Tools and supplies", "Canva and editing app", 15, 1)]:
                expenses.append({"date": day.isoformat(), "category": category, "description": text, "amount": amount, "fixed": fixed})
    db.insert_many("sales", business_id, sales)
    db.insert_many("expenses", business_id, expenses)

    db.insert_many("goals", business_id, [
        {"title": "Make $3,500 this month", "metric": "Sales", "target": 3500, "start_date": today.replace(day=1).isoformat(),
         "due_date": (today.replace(day=28) + timedelta(days=4)).replace(day=1).isoformat()},
        {"title": "Get 5 new customers", "metric": "New customers", "target": 5, "start_date": (today - timedelta(days=30)).isoformat(),
         "due_date": (today + timedelta(days=60)).isoformat()},
        {"title": "Save $1,000 for a sewing machine", "metric": "Custom", "target": 1000, "progress": 430,
         "start_date": (today - timedelta(days=120)).isoformat(), "due_date": (today + timedelta(days=150)).isoformat()},
    ])
    db.insert_many("tasks", business_id, [
        {"title": "Book a table at the campus market", "priority": "High", "due_date": (today + timedelta(days=3)).isoformat(), "done": 0, "source": "You"},
        {"title": "Reply to Campus Store about next term", "priority": "Medium", "due_date": (today - timedelta(days=2)).isoformat(), "done": 0, "source": "You"},
        {"title": "Film a try-on reel for the new jackets", "priority": "Low", "due_date": (today + timedelta(days=8)).isoformat(), "done": 0, "source": "You"},
    ])


__all__ = ["analytics"]
