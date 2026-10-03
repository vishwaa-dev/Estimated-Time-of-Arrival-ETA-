"""Utility scripts.

Train the optional ML model:
    python scripts/manage.py train-model

Seed the database from the train JSON snapshots in /data (happens
automatically on backend startup as well):
    python scripts/manage.py seed
"""
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))


def train_model() -> None:
    from app.ml.train import train

    meta = train()
    print(json.dumps(meta, indent=2))


def seed_database() -> None:
    from app.database import SessionLocal, init_db
    from app.services.seed_service import seed_all

    init_db()
    db = SessionLocal()
    try:
        seeded = seed_all(db)
        print("Seeded:", seeded or "nothing new (already present)")
    finally:
        db.close()


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action == "train-model":
        train_model()
    elif action == "seed":
        seed_database()
    else:
        print(__doc__)
