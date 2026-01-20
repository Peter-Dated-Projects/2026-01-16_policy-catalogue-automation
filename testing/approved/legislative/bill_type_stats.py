"""
Bill Type Statistics - Analyze bills by type from the database.
"""

import json
from pathlib import Path
from collections import Counter
from typing import Dict


def load_bills() -> list:
    """Load bills from the database."""
    db_file = Path("legislation/bills_db.json")

    if not db_file.exists():
        print("No database found. Run main.py first to fetch bills.")
        return []

    with open(db_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("bills", [])


def analyze_bill_types(bills: list) -> Dict[str, int]:
    """Count bills by type."""
    bill_types = [bill.get("bill_type", "Unknown") for bill in bills]
    return Counter(bill_types)


def main():
    """Generate bill type statistics report."""
    bills = load_bills()

    if not bills:
        return

    print("\n" + "=" * 70)
    print("CANADIAN LEGISLATIVE BILL TYPE STATISTICS")
    print("=" * 70)
    print(f"Total Bills: {len(bills)}\n")

    # Count by type
    type_counts = analyze_bill_types(bills)

    print("Bill Type Distribution:")
    print("-" * 70)

    # Sort by count (descending) then by name
    sorted_types = sorted(type_counts.items(), key=lambda x: (-x[1], x[0]))

    for bill_type, count in sorted_types:
        percentage = (count / len(bills)) * 100
        bar = "█" * int(percentage / 2)  # Scale bar to fit
        print(f"{bill_type:45} {count:4} ({percentage:5.1f}%) {bar}")

    print("-" * 70)

    # Show examples for each type
    print("\nExamples by Type:")
    print("-" * 70)

    examples_by_type = {}
    for bill in bills:
        bill_type = bill.get("bill_type", "Unknown")
        if bill_type not in examples_by_type:
            examples_by_type[bill_type] = []
        if len(examples_by_type[bill_type]) < 2:  # Keep max 2 examples per type
            examples_by_type[bill_type].append(bill)

    for bill_type in sorted(examples_by_type.keys()):
        print(f"\n{bill_type}:")
        for bill in examples_by_type[bill_type]:
            bill_id = bill["bill_id"]
            title = bill["title"][:60]
            print(f"  • {bill_id}: {title}{'...' if len(bill['title']) > 60 else ''}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
