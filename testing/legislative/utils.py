"""
Shared utility functions for legislative bill analysis tools.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List


def load_bills() -> List[dict]:
    """Load bills from the database."""
    db_file = Path("legislation/bills_db.json")

    if not db_file.exists():
        print("No database found. Run main.py first to fetch bills.")
        return []

    with open(db_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("bills", [])


def calculate_days_since(date_str: str) -> int:
    """Calculate days since a given date."""
    if not date_str:
        return None
    try:
        # Parse ISO format datetime (may include timezone)
        if "T" in date_str:
            date_part = date_str.split("T")[0]
            last_date = datetime.fromisoformat(date_part)
        else:
            last_date = datetime.fromisoformat(date_str)

        days = (datetime.now() - last_date).days
        return days
    except:
        return None
