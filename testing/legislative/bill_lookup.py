#!/usr/bin/env python3
"""
Bill Lookup Tool - Query detailed information about specific bills.
Usage: python bill_lookup.py C-11
       python bill_lookup.py S-2 C-11 C-234
"""

import sys
import json
from pathlib import Path
from datetime import datetime


def load_bills() -> dict:
    """Load bills from the database."""
    db_file = Path("legislation/bills_db.json")
    
    if not db_file.exists():
        print("❌ No database found. Run main.py first to fetch bills.")
        return {}
    
    with open(db_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Create a lookup dictionary by bill_id
    bills_dict = {}
    for bill in data.get("bills", []):
        bills_dict[bill["bill_id"]] = bill
    
    return bills_dict


def calculate_days_since(date_str: str) -> int:
    """Calculate days since a given date."""
    if not date_str:
        return None
    try:
        if 'T' in date_str:
            date_part = date_str.split('T')[0]
            last_date = datetime.fromisoformat(date_part)
        else:
            last_date = datetime.fromisoformat(date_str)
        
        days = (datetime.now() - last_date).days
        return days
    except:
        return None


def display_bill(bill: dict):
    """Display detailed information about a bill."""
    bill_id = bill["bill_id"]
    
    print("\n" + "═" * 80)
    print(f"  {bill_id}: {bill['title']}")
    print("═" * 80)
    
    # Basic info
    print(f"\n📋 Basic Information:")
    print(f"   Session:       {bill['session']}")
    print(f"   Type:          {bill.get('bill_type', 'Unknown')}")
    
    # Sponsor info
    if bill.get("sponsor"):
        print(f"\n👤 Sponsorship:")
        print(f"   Sponsor:       {bill['sponsor']}")
        if bill.get("has_royal_recommendation"):
            print(f"   Royal Rec:     ✓ Yes (affects public funds)")
        else:
            print(f"   Royal Rec:     ✗ No")
    
    # Timeline info
    print(f"\n⏱️  Timeline:")
    
    # Last activity
    if bill.get("last_activity_date"):
        days = calculate_days_since(bill["last_activity_date"])
        if days is not None:
            status = "🟢" if days <= 30 else "🟡" if days <= 90 else "🔴"
            print(f"   Last Activity: {status} {days} days ago")
        else:
            print(f"   Last Activity: {bill['last_activity_date']}")
    
    # Royal assent
    if bill.get("royal_assent_date"):
        days = calculate_days_since(bill["royal_assent_date"])
        print(f"   Royal Assent:  ✓ Received ({days} days ago)")
        print(f"   Status:        🎉 BECAME LAW")
    else:
        print(f"   Royal Assent:  ⏳ Pending")
    
    # History
    history = bill.get("history", [])
    if history:
        print(f"\n📜 Status History ({len(history)} events):")
        for i, event in enumerate(history, 1):
            timestamp = event["timestamp"][:16].replace("T", " ") if event.get("timestamp") else "Unknown"
            status = event.get("status_text", "Unknown")
            chamber = event.get("chamber", "Unknown")
            print(f"   {i}. [{timestamp}] {status}")
            print(f"      Chamber: {chamber}")
    
    # Current status
    if history:
        current = history[-1]
        print(f"\n📍 Current Status:")
        print(f"   {current.get('status_text', 'Unknown')}")
        print(f"   Chamber: {current.get('chamber', 'Unknown')}")
    
    # Link
    if history:
        print(f"\n🔗 More Info:")
        print(f"   {history[0].get('text_url', 'N/A')}")
    
    print("─" * 80)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python bill_lookup.py <bill_id> [bill_id2] ...")
        print("\nExamples:")
        print("  python bill_lookup.py C-11")
        print("  python bill_lookup.py S-2 C-11 C-234")
        print("\nTo see all bills, use: python bill_analytics.py")
        return
    
    bills_dict = load_bills()
    if not bills_dict:
        return
    
    bill_ids = sys.argv[1:]
    
    for bill_id in bill_ids:
        bill_id = bill_id.upper()  # Normalize to uppercase
        
        if bill_id in bills_dict:
            display_bill(bills_dict[bill_id])
        else:
            print(f"\n❌ Bill {bill_id} not found in database.")
            print(f"   Available bills: {', '.join(sorted(bills_dict.keys())[:10])}...")


if __name__ == "__main__":
    main()
