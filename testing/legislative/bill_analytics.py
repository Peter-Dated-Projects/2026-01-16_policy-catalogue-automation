"""
Enhanced Bill Analytics - View detailed tracking information.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List
from collections import Counter


def load_bills() -> list:
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
        if 'T' in date_str:
            date_part = date_str.split('T')[0]
            last_date = datetime.fromisoformat(date_part)
        else:
            last_date = datetime.fromisoformat(date_str)
        
        days = (datetime.now() - last_date).days
        return days
    except:
        return None


def show_royal_assent_summary(bills: list):
    """Show bills with royal assent status."""
    print("\n" + "=" * 80)
    print("ROYAL ASSENT STATUS")
    print("=" * 80)
    
    received_assent = [b for b in bills if b.get("royal_assent_date")]
    pending_assent = [b for b in bills if not b.get("royal_assent_date")]
    
    print(f"Bills with Royal Assent: {len(received_assent)}")
    print(f"Bills without Royal Assent: {len(pending_assent)}")
    
    if received_assent:
        print("\nBills that received Royal Assent:")
        print("-" * 80)
        for bill in received_assent[:10]:  # Show first 10
            days = calculate_days_since(bill["royal_assent_date"])
            print(f"  {bill['bill_id']:8} | {bill['title'][:50]:50} | {days} days ago")


def show_activity_summary(bills: list):
    """Show bills by days since last activity."""
    print("\n" + "=" * 80)
    print("ACTIVITY TIMELINE")
    print("=" * 80)
    
    bills_with_activity = []
    for bill in bills:
        days = calculate_days_since(bill.get("last_activity_date"))
        if days is not None:
            bills_with_activity.append((bill, days))
    
    # Sort by most recent activity
    bills_with_activity.sort(key=lambda x: x[1])
    
    print(f"\nMost Recently Active Bills:")
    print("-" * 80)
    for bill, days in bills_with_activity[:10]:
        print(f"  {bill['bill_id']:8} | {days:3} days ago | {bill['title'][:50]}")
    
    print(f"\nLeast Recently Active Bills:")
    print("-" * 80)
    for bill, days in bills_with_activity[-10:]:
        print(f"  {bill['bill_id']:8} | {days:3} days ago | {bill['title'][:50]}")
    
    # Activity distribution
    print("\nActivity Distribution:")
    print("-" * 80)
    recent = sum(1 for _, days in bills_with_activity if days <= 30)
    moderate = sum(1 for _, days in bills_with_activity if 30 < days <= 90)
    stale = sum(1 for _, days in bills_with_activity if 90 < days <= 180)
    very_stale = sum(1 for _, days in bills_with_activity if days > 180)
    
    print(f"  Active (≤ 30 days):      {recent:3} bills")
    print(f"  Moderate (31-90 days):   {moderate:3} bills")
    print(f"  Stale (91-180 days):     {stale:3} bills")
    print(f"  Very Stale (> 180 days): {very_stale:3} bills")


def show_sponsor_analysis(bills: list):
    """Analyze bills by sponsor."""
    print("\n" + "=" * 80)
    print("SPONSOR ANALYSIS (Political Weight)")
    print("=" * 80)
    
    # Count bills by sponsor
    sponsor_counts = Counter()
    for bill in bills:
        sponsor = bill.get("sponsor")
        if sponsor:
            sponsor_counts[sponsor] += 1
    
    print(f"\nTotal Sponsors: {len(sponsor_counts)}")
    print(f"\nTop 15 Most Active Sponsors:")
    print("-" * 80)
    
    for sponsor, count in sponsor_counts.most_common(15):
        # Calculate percentage
        percentage = (count / len(bills)) * 100
        bar = "█" * min(count, 40)  # Visual bar
        print(f"{sponsor:40} {count:3} bills ({percentage:4.1f}%) {bar}")


def show_royal_recommendation_analysis(bills: list):
    """Analyze bills by royal recommendation status."""
    print("\n" + "=" * 80)
    print("ROYAL RECOMMENDATION ANALYSIS")
    print("=" * 80)
    
    with_recommendation = [b for b in bills if b.get("has_royal_recommendation")]
    without_recommendation = [b for b in bills if not b.get("has_royal_recommendation")]
    
    print(f"Bills with Royal Recommendation: {len(with_recommendation)}")
    print(f"Bills without Royal Recommendation: {len(without_recommendation)}")
    
    if with_recommendation:
        print("\nSample Bills with Royal Recommendation:")
        print("-" * 80)
        for bill in with_recommendation[:5]:
            sponsor = bill.get("sponsor", "Unknown")
            print(f"  {bill['bill_id']:8} | {sponsor:30} | {bill['title'][:40]}")


def show_detailed_bill_info(bills: list, bill_id: str = None):
    """Show detailed information for a specific bill."""
    if not bill_id:
        return
    
    bill = next((b for b in bills if b["bill_id"] == bill_id), None)
    if not bill:
        print(f"\nBill {bill_id} not found.")
        return
    
    print("\n" + "=" * 80)
    print(f"DETAILED BILL INFORMATION: {bill_id}")
    print("=" * 80)
    
    print(f"Title:                {bill['title']}")
    print(f"Type:                 {bill.get('bill_type', 'Unknown')}")
    print(f"Session:              {bill['session']}")
    print(f"Sponsor:              {bill.get('sponsor', 'Unknown')}")
    print(f"Royal Recommendation: {'Yes' if bill.get('has_royal_recommendation') else 'No'}")
    
    # Royal assent
    if bill.get("royal_assent_date"):
        days_since_assent = calculate_days_since(bill["royal_assent_date"])
        print(f"Royal Assent:         Received ({days_since_assent} days ago)")
    else:
        print(f"Royal Assent:         Not yet received")
    
    # Last activity
    if bill.get("last_activity_date"):
        days_since_activity = calculate_days_since(bill["last_activity_date"])
        print(f"Days Since Activity:  {days_since_activity}")
    
    # History
    print(f"\nStatus History ({len(bill.get('history', []))} events):")
    print("-" * 80)
    for i, event in enumerate(bill.get("history", []), 1):
        timestamp = event["timestamp"][:10] if event.get("timestamp") else "Unknown"
        print(f"{i}. [{timestamp}] {event.get('status_text', 'Unknown')} ({event.get('chamber', 'Unknown')})")


def main():
    """Generate comprehensive bill analytics."""
    bills = load_bills()
    
    if not bills:
        return
    
    print("\n" + "=" * 80)
    print("CANADIAN LEGISLATIVE BILL ANALYTICS")
    print("=" * 80)
    print(f"Total Bills Tracked: {len(bills)}")
    print(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Show different analyses
    show_activity_summary(bills)
    show_sponsor_analysis(bills)
    show_royal_recommendation_analysis(bills)
    show_royal_assent_summary(bills)
    
    # Show detailed info for a sample bill if desired
    # Uncomment to see details for specific bills:
    # show_detailed_bill_info(bills, "C-11")
    # show_detailed_bill_info(bills, "S-2")
    
    print("\n" + "=" * 80)
    print("To view details for a specific bill, edit the script and uncomment")
    print("the show_detailed_bill_info() calls at the bottom.")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
