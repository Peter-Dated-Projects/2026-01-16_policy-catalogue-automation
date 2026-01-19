"""
Test script to verify bill type classification logic.
"""

from main import Bill


def test_bill_classification():
    """Test various bill types to ensure correct classification."""

    test_cases = [
        # (bill_id, title, expected_type)
        (
            "C-11",
            "An Act to amend the Broadcasting Act",
            "Government Bill (House) - Amending",
        ),
        (
            "C-11",
            "An Act respecting online streaming",
            "Government Bill (House) - New Act",
        ),
        ("C-11", "Some other kind of bill", "Government Bill (House)"),
        ("C-234", "An Act respecting farm heating", "Private Member's Bill - New Act"),
        (
            "C-234",
            "An Act to amend the Income Tax Act",
            "Private Member's Bill - Amending",
        ),
        ("C-234", "Some other private member bill", "Private Member's Bill"),
        ("S-5", "An Act respecting environmental protection", "Senate Bill - New Act"),
        (
            "S-5",
            "An Act to amend the Environmental Protection Act",
            "Senate Bill - Amending",
        ),
        ("S-5", "Some senate bill", "Senate Bill"),
        (
            "C-201",
            "An Act to amend the Canada Health Act",
            "Private Member's Bill - Amending",
        ),
        ("C-200", "An Act respecting something", "Government Bill (House) - New Act"),
        ("S-201", "An Act respecting a framework", "Senate Bill - New Act"),
    ]

    print("Testing Bill Type Classification")
    print("=" * 70)

    all_passed = True
    for bill_id, title, expected_type in test_cases:
        actual_type = Bill.classify_bill_type(bill_id, title)
        passed = actual_type == expected_type
        all_passed = all_passed and passed

        status = "✓" if passed else "✗"
        print(f"{status} {bill_id:8} | {actual_type:40} | {title[:30]}...")

        if not passed:
            print(f"  Expected: {expected_type}")
            print(f"  Got:      {actual_type}")

    print("=" * 70)
    if all_passed:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed")

    return all_passed


if __name__ == "__main__":
    success = test_bill_classification()
    exit(0 if success else 1)
