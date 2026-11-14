"""Preload the reviewer login (with a persona) and demo users. Password comes from REVIEWER_PASSWORD (env, never
committed); a local default is used only in development."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from sqlalchemy import select

from apps.api import db
from apps.api.auth.security import hash_password

PERSONAS = Path(__file__).resolve().parents[1] / "data" / "personas"


def seed() -> None:
    db.init_db()
    pw = os.getenv("REVIEWER_PASSWORD", "reviewer-dev-pass")
    for uid, username, persona in [("reviewer", "reviewer", "ai_ml"), ("demo-web", "demo_web", "fullstack"),
                                   ("demo-data", "demo_data", "data_analyst")]:
        if db.one(select(db.users).where(db.users.c.id == uid)):
            continue
        rate = json.loads((PERSONAS / persona / "persona.json").read_text())["rate_floor"]
        db.q(db.users.insert().values(id=uid, username=username, password_hash=hash_password(pw), owner=persona,
                                      prefs={"rate_floor": rate, "connects_weekly_budget": 120, "saved_searches": [""],
                                             "categories": [], "min_budget": 0, "autonomy": "auto_skip_low_fit",
                                             "marketplace": "gigsim"}, created_at=time.time()))


if __name__ == "__main__":
    seed()
    print("seeded")
