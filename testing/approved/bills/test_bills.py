"""
Pytest test suite for the Canadian Legislative Bill Tracking System.

Tests cover:
- Bill classification and lifecycle management
- Status change detection and tracking
- Database operations (save, load, updates)
- XML parsing and data extraction
- Royal Assent processing
- Coming into Force (CIF) analysis
- Analytics and lookup utilities
- Historical bill fetching
"""

import json
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from xml.etree import ElementTree as ET

import pytest
import requests

from bill_analytics import (
    show_activity_summary,
    show_royal_assent_summary,
    show_sponsor_analysis,
)
from bill_lookup import display_bill
from main import (
    Bill,
    BillStage,
    BillState,
    BillTracker,
    CIFStatus,
    analyze_coming_into_force,
    extract_chapter_citation,
    process_passed_bill,
)
from utils import calculate_days_since, load_bills


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    temp_path = tempfile.mkdtemp()
    yield Path(temp_path)
    # Cleanup
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def mock_db_file(temp_dir, monkeypatch):
    """Mock the database file path."""
    db_path = temp_dir / "test_bills_db.json"
    storage_dir = temp_dir / "assets"
    storage_dir.mkdir(exist_ok=True)

    # Patch the module-level constants
    import main

    monkeypatch.setattr(main, "STORAGE_DIR", storage_dir)
    monkeypatch.setattr(main, "DB_FILE", db_path)
    monkeypatch.setattr(main, "CURRENT_PARLIAMENT", 44)

    return db_path


@pytest.fixture
def sample_bill_data():
    """Generate sample bill data for testing."""
    return {
        "session": "44-1",
        "bill_id": "C-11",
        "title": "An Act to amend the Broadcasting Act",
        "bill_type": "Government Bill (House) - Amending",
        "sponsor": "Hon. John Doe",
        "sponsor_affiliation": "Liberal",
        "royal_assent_date": None,
        "last_activity_date": "2024-01-15T10:00:00",
        "has_royal_recommendation": True,
        "current_stage": "SECOND_READING",
        "publication_count": 1,
        "is_active": True,
        "died_on_order_paper": False,
        "chapter_citation": None,
        "cif_status": "NOT_DETERMINED",
        "cif_details": None,
        "history": [
            {
                "status_code": "100",
                "status_text": "First reading",
                "timestamp": "2024-01-10T10:00:00",
                "chamber": "House of Commons",
                "text_url": "https://example.com/bill.pdf",
                "stage": "FIRST_READING",
                "text_changed": False,
            },
            {
                "status_code": "200",
                "status_text": "Second reading",
                "timestamp": "2024-01-15T10:00:00",
                "chamber": "House of Commons",
                "text_url": "https://example.com/bill.pdf",
                "stage": "SECOND_READING",
                "text_changed": False,
            },
        ],
    }


@pytest.fixture
def sample_xml_response():
    """Generate sample XML response from API."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<Bills>
    <Bill>
        <BillNumberFormatted>C-11</BillNumberFormatted>
        <ParlSessionCode>44-1</ParlSessionCode>
        <LongTitleEn>An Act to amend the Broadcasting Act</LongTitleEn>
        <StatusName>Second Reading</StatusName>
        <StatusCode>200</StatusCode>
        <Chamber>House of Commons</Chamber>
        <LatestBillTextUrl>https://example.com/bill.pdf</LatestBillTextUrl>
        <SponsorPersonName>Hon. John Doe</SponsorPersonName>
        <SponsorAffiliation>Liberal</SponsorAffiliation>
        <HasRoyalRecommendation>true</HasRoyalRecommendation>
        <PublicationCount>1</PublicationCount>
    </Bill>
</Bills>"""


# ============================================================================
# Bill Model Tests
# ============================================================================


class TestBillState:
    """Test suite for BillState dataclass."""

    def test_bill_state_creation(self):
        """Test creating a BillState instance."""
        state = BillState(
            status_code="100",
            status_text="First reading",
            timestamp="2024-01-10T10:00:00",
            chamber="House of Commons",
            text_url="https://example.com/bill.pdf",
            stage="FIRST_READING",
            text_changed=False,
        )

        assert state.status_code == "100"
        assert state.status_text == "First reading"
        assert state.chamber == "House of Commons"
        assert state.stage == "FIRST_READING"
        assert state.text_changed is False

    def test_bill_state_to_dict(self):
        """Test converting BillState to dictionary."""
        state = BillState(
            status_code="100",
            status_text="First reading",
            timestamp="2024-01-10T10:00:00",
            chamber="House of Commons",
            text_url="https://example.com/bill.pdf",
        )

        state_dict = state.to_dict()

        assert isinstance(state_dict, dict)
        assert state_dict["status_code"] == "100"
        assert state_dict["chamber"] == "House of Commons"

    def test_bill_state_immutable(self):
        """Test that BillState is immutable (frozen)."""
        state = BillState(
            status_code="100",
            status_text="First reading",
            timestamp="2024-01-10T10:00:00",
            chamber="House of Commons",
            text_url="https://example.com/bill.pdf",
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            state.status_code = "200"


class TestBill:
    """Test suite for Bill class."""

    def test_bill_creation(self, sample_bill_data):
        """Test creating a Bill instance."""
        bill = Bill(
            session="44-1",
            bill_id="C-11",
            title="An Act to amend the Broadcasting Act",
        )

        assert bill.session == "44-1"
        assert bill.bill_id == "C-11"
        assert bill.title == "An Act to amend the Broadcasting Act"
        assert bill.history == []
        assert bill.is_active is True

    def test_classify_bill_type_government(self):
        """Test classifying government bills."""
        # Government bill (C-1 to C-200)
        bill_type = Bill.classify_bill_type("C-11", "An Act to amend the Test Act")
        assert "Government Bill" in bill_type
        assert "Amending" in bill_type

    def test_classify_bill_type_private_member(self):
        """Test classifying private member's bills."""
        # Private member's bill (C-201+)
        bill_type = Bill.classify_bill_type("C-234", "An Act respecting something new")
        assert "Private Member's Bill" in bill_type
        assert "New Act" in bill_type

    def test_classify_bill_type_senate(self):
        """Test classifying senate bills."""
        bill_type = Bill.classify_bill_type("S-5", "An Act to amend the Senate Act")
        assert "Senate Bill" in bill_type
        assert "Amending" in bill_type

    def test_bill_unique_key(self):
        """Test unique key generation."""
        bill = Bill(session="44-1", bill_id="C-11", title="Test Bill")
        assert bill.unique_key == "44-1-C-11"

    def test_bill_parliament_number(self):
        """Test parliament number extraction."""
        bill = Bill(session="44-1", bill_id="C-11", title="Test Bill")
        assert bill.parliament_number == 44

        bill2 = Bill(session="43-2", bill_id="C-5", title="Test Bill 2")
        assert bill2.parliament_number == 43

    def test_is_royal_assent_received(self):
        """Test royal assent status check."""
        bill = Bill(
            session="44-1",
            bill_id="C-11",
            title="Test Bill",
            royal_assent_date="2024-01-20",
        )
        assert bill.is_royal_assent_received is True

        bill2 = Bill(session="44-1", bill_id="C-12", title="Test Bill 2")
        assert bill2.is_royal_assent_received is False

    def test_update_bill_status_first_time(self):
        """Test updating a bill's status for the first time."""
        bill = Bill(session="44-1", bill_id="C-11", title="Test Bill")

        changed = bill.update(
            status_code="100",
            status_text="First reading",
            chamber="House of Commons",
            text_url="https://example.com/bill.pdf",
            publication_count=1,
        )

        assert changed is True
        assert len(bill.history) == 1
        assert bill.current_stage == "FIRST_READING"

    def test_update_bill_no_change(self):
        """Test updating a bill when status hasn't changed."""
        bill = Bill(session="44-1", bill_id="C-11", title="Test Bill")

        # First update
        bill.update(
            status_code="100",
            status_text="First reading",
            chamber="House of Commons",
            text_url="https://example.com/bill.pdf",
        )

        # Same update
        changed = bill.update(
            status_code="100",
            status_text="First reading",
            chamber="House of Commons",
            text_url="https://example.com/bill.pdf",
        )

        assert changed is False
        assert len(bill.history) == 1

    def test_update_bill_status_change(self):
        """Test updating a bill when status changes."""
        bill = Bill(session="44-1", bill_id="C-11", title="Test Bill")

        bill.update(
            status_code="100",
            status_text="First reading",
            chamber="House of Commons",
            text_url="https://example.com/bill.pdf",
        )

        changed = bill.update(
            status_code="200",
            status_text="Second reading",
            chamber="House of Commons",
            text_url="https://example.com/bill.pdf",
        )

        assert changed is True
        assert len(bill.history) == 2
        assert bill.current_stage == "SECOND_READING"

    def test_determine_stage_transition_chamber_switch(self):
        """Test stage determination when bill moves to Senate."""
        bill = Bill(session="44-1", bill_id="C-11", title="Test Bill")

        # Start in House
        bill.update(
            status_code="100",
            status_text="First reading",
            chamber="House of Commons",
            text_url="https://example.com/bill.pdf",
        )

        # Move to Senate
        stage, text_changed = bill.determine_stage_transition(
            "First reading in Senate", "Senate", 1
        )

        assert stage == BillStage.SENATE_STAGES
        assert text_changed is False

    def test_determine_stage_amendment_detection(self):
        """Test amendment detection via publication count increase."""
        bill = Bill(
            session="44-1", bill_id="C-11", title="Test Bill", publication_count=1
        )

        bill.update(
            status_code="100",
            status_text="First reading",
            chamber="House of Commons",
            text_url="https://example.com/bill.pdf",
            publication_count=1,
        )

        # Report stage with increased publication count
        stage, text_changed = bill.determine_stage_transition(
            "Report stage", "House of Commons", 2
        )

        assert stage == BillStage.REPORT_STAGE
        assert text_changed is True

    def test_bill_to_dict(self, sample_bill_data):
        """Test converting Bill to dictionary."""
        bill = Bill.from_dict(sample_bill_data)
        bill_dict = bill.to_dict()

        assert bill_dict["session"] == "44-1"
        assert bill_dict["bill_id"] == "C-11"
        assert len(bill_dict["history"]) == 2

    def test_bill_from_dict(self, sample_bill_data):
        """Test creating Bill from dictionary."""
        bill = Bill.from_dict(sample_bill_data)

        assert bill.session == "44-1"
        assert bill.bill_id == "C-11"
        assert bill.title == "An Act to amend the Broadcasting Act"
        assert len(bill.history) == 2
        assert bill.is_active is True


# ============================================================================
# Royal Assent Processing Tests
# ============================================================================


class TestRoyalAssentProcessing:
    """Test suite for royal assent and CIF processing."""

    def test_extract_chapter_citation_standard(self):
        """Test extracting standard chapter citation."""
        bill_text = """
        Some preamble text...
        S.C. 2024, c. 15
        More content...
        """
        metadata = {}

        citation = extract_chapter_citation(bill_text, metadata)
        assert citation == "S.C. 2024, c. 15"

    def test_extract_chapter_citation_alternative_format(self):
        """Test extracting chapter citation in alternative format."""
        bill_text = """
        Statutes of Canada 2024 Chapter 42
        """
        metadata = {}

        citation = extract_chapter_citation(bill_text, metadata)
        assert citation == "S.C. 2024, c. 42"

    def test_extract_chapter_citation_not_found(self):
        """Test when chapter citation is not found."""
        bill_text = "No chapter citation in this text"
        metadata = {}

        citation = extract_chapter_citation(bill_text, metadata)
        assert citation is None

    def test_analyze_coming_into_force_on_assent(self):
        """Test CIF analysis for bills active on royal assent."""
        bill_text = """
        Coming into Force
        This Act comes into force on the day on which it receives royal assent.
        """

        status, details = analyze_coming_into_force(bill_text)
        assert status == CIFStatus.ACTIVE_ON_ASSENT.name
        assert "royal assent" in details.lower()

    def test_analyze_coming_into_force_order_in_council(self):
        """Test CIF analysis for Order in Council."""
        bill_text = """
        Coming into Force
        This Act comes into force on a day to be fixed by Order in Council.
        """

        status, details = analyze_coming_into_force(bill_text)
        assert status == CIFStatus.WAITING_FOR_ORDER.name
        assert "order" in details.lower()

    def test_analyze_coming_into_force_fixed_date(self):
        """Test CIF analysis for fixed date."""
        bill_text = """
        Coming into Force
        This Act comes into force on January 1, 2025.
        """

        status, details = analyze_coming_into_force(bill_text)
        assert status == CIFStatus.FIXED_DATE.name
        assert "January" in details or "2025" in details

    def test_analyze_coming_into_force_no_section(self):
        """Test CIF analysis when no CIF section found."""
        bill_text = "Just some regular bill text without CIF section."

        status, details = analyze_coming_into_force(bill_text)
        assert status == CIFStatus.ACTIVE_ON_ASSENT.name
        assert "No Coming into Force section" in details

    def test_process_passed_bill(self):
        """Test processing a bill that received royal assent."""
        bill = Bill(
            session="44-1",
            bill_id="C-11",
            title="Test Act",
            royal_assent_date="2024-01-20",
        )

        bill_text = """
        S.C. 2024, c. 15
        Coming into Force
        This Act comes into force on the day on which it receives royal assent.
        """

        result = process_passed_bill(bill, bill_text, {})

        assert result is True
        assert bill.chapter_citation == "S.C. 2024, c. 15"
        assert bill.cif_status == CIFStatus.ACTIVE_ON_ASSENT.name

    def test_process_passed_bill_already_processed(self):
        """Test that processing is skipped if already done."""
        bill = Bill(
            session="44-1",
            bill_id="C-11",
            title="Test Act",
            royal_assent_date="2024-01-20",
            chapter_citation="S.C. 2024, c. 15",
            cif_status=CIFStatus.ACTIVE_ON_ASSENT.name,
        )

        result = process_passed_bill(bill, "", {})
        assert result is False  # Already processed


# ============================================================================
# BillTracker Tests
# ============================================================================


class TestBillTracker:
    """Test suite for BillTracker class."""

    def test_tracker_initialization(self, mock_db_file):
        """Test tracker initialization."""
        with patch.object(BillTracker, "_fetch_current_bills_xml", return_value=[]):
            tracker = BillTracker(fetch_historical=False)

            assert tracker.bills == {}
            assert tracker.fetch_historical is False

    def test_save_and_load_database(self, mock_db_file, sample_bill_data):
        """Test saving and loading the database."""
        with patch.object(BillTracker, "_fetch_current_bills_xml", return_value=[]):
            tracker = BillTracker(fetch_historical=False)

            # Add a bill
            bill = Bill.from_dict(sample_bill_data)
            tracker.bills[bill.unique_key] = bill

            # Save
            tracker._save_database()

            assert mock_db_file.exists()

            # Load in new tracker
            with patch.object(BillTracker, "_fetch_current_bills_xml", return_value=[]):
                tracker2 = BillTracker(fetch_historical=False)
                # Force reload from saved file
                with open(mock_db_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                assert len(data["bills"]) == 1
                assert data["bills"][0]["bill_id"] == "C-11"

    def test_detect_current_parliament(self, mock_db_file):
        """Test detecting current parliament number from bills."""
        with patch.object(BillTracker, "_fetch_current_bills_xml", return_value=[]):
            tracker = BillTracker(fetch_historical=False)

            bill_data = [
                {"session": "42-1", "bill_id": "C-1"},
                {"session": "43-1", "bill_id": "C-2"},
                {"session": "44-1", "bill_id": "C-3"},
                {"session": "44-2", "bill_id": "C-4"},
            ]

            parliament = tracker._detect_current_parliament(bill_data)
            assert parliament == 44

    def test_update_bill_lifecycle_status(self, mock_db_file, sample_bill_data):
        """Test marking old bills as died on order paper."""
        with patch.object(BillTracker, "_fetch_current_bills_xml", return_value=[]):
            tracker = BillTracker(fetch_historical=False)

            # Add bill from old parliament
            old_bill_data = sample_bill_data.copy()
            old_bill_data["session"] = "43-1"  # Old parliament
            old_bill_data["bill_id"] = "C-5"
            old_bill = Bill.from_dict(old_bill_data)
            tracker.bills[old_bill.unique_key] = old_bill

            # Add current bill
            current_bill = Bill.from_dict(sample_bill_data)
            tracker.bills[current_bill.unique_key] = current_bill

            # Mark old bills as inactive
            current_parliament_bills = {current_bill.unique_key}
            tracker._update_bill_lifecycle_status(current_parliament_bills)

            # Old bill should be marked as died
            assert old_bill.is_active is False
            assert old_bill.died_on_order_paper is True

            # Current bill should still be active
            assert current_bill.is_active is True

    def test_process_bill_new(self, mock_db_file):
        """Test processing a new bill."""
        with patch.object(BillTracker, "_fetch_current_bills_xml", return_value=[]):
            tracker = BillTracker(fetch_historical=False)

            bill_data = {
                "session": "44-1",
                "bill_id": "C-99",
                "title": "New Test Bill",
                "status_code": "100",
                "status_text": "First reading",
                "chamber": "House of Commons",
                "text_url": "https://example.com/bill.pdf",
            }

            changed = tracker._process_bill(bill_data, suppress_new_log=False)

            assert changed is True
            assert "44-1-C-99" in tracker.bills

    def test_fetch_and_process_bills_with_changes(
        self, mock_db_file, sample_xml_response
    ):
        """Test fetching bills and detecting changes."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = sample_xml_response.encode()
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            with patch.object(BillTracker, "_load_database"):
                tracker = BillTracker(fetch_historical=False)
                tracker.bills = {}

                tracker.fetch_and_process_bills()

                # Should have processed the bill
                assert len(tracker.bills) > 0


# ============================================================================
# Database Change Detection Tests
# ============================================================================


class TestDatabaseChangeDetection:
    """Test suite for change detection in database operations."""

    def test_change_detection_new_bill(self, mock_db_file):
        """Test that new bills are detected as changes."""
        with patch.object(BillTracker, "_fetch_current_bills_xml", return_value=[]):
            tracker = BillTracker(fetch_historical=False)

            bill_data = {
                "session": "44-1",
                "bill_id": "C-100",
                "title": "Brand New Bill",
                "status_code": "100",
                "status_text": "First reading",
                "chamber": "House of Commons",
                "text_url": "https://example.com/bill.pdf",
            }

            initial_count = len(tracker.bills)
            changed = tracker._process_bill(bill_data)

            assert changed is True
            assert len(tracker.bills) == initial_count + 1

    def test_change_detection_status_update(self, mock_db_file, sample_bill_data):
        """Test that status updates are detected as changes."""
        with patch.object(BillTracker, "_fetch_current_bills_xml", return_value=[]):
            tracker = BillTracker(fetch_historical=False)

            # Add existing bill
            bill = Bill.from_dict(sample_bill_data)
            tracker.bills[bill.unique_key] = bill

            # Update with new status
            updated_data = {
                "session": "44-1",
                "bill_id": "C-11",
                "title": "An Act to amend the Broadcasting Act",
                "status_code": "300",
                "status_text": "Third reading",
                "chamber": "House of Commons",
                "text_url": "https://example.com/bill.pdf",
            }

            changed = tracker._process_bill(updated_data)

            assert changed is True
            assert bill.current_stage == "THIRD_READING"
            assert len(bill.history) == 3  # Original 2 + new update

    def test_change_detection_no_change(self, mock_db_file, sample_bill_data):
        """Test that no change is detected when status is same."""
        with patch.object(BillTracker, "_fetch_current_bills_xml", return_value=[]):
            tracker = BillTracker(fetch_historical=False)

            # Add existing bill
            bill = Bill.from_dict(sample_bill_data)
            tracker.bills[bill.unique_key] = bill

            # Same status
            same_data = {
                "session": "44-1",
                "bill_id": "C-11",
                "title": "An Act to amend the Broadcasting Act",
                "status_code": "200",
                "status_text": "Second reading",
                "chamber": "House of Commons",
                "text_url": "https://example.com/bill.pdf",
            }

            changed = tracker._process_bill(same_data)

            assert changed is False
            assert len(bill.history) == 2  # No new history entry

    def test_database_update_on_change(self, mock_db_file, sample_bill_data):
        """Test that database is updated when changes are detected."""
        with patch.object(BillTracker, "_fetch_current_bills_xml", return_value=[]):
            tracker = BillTracker(fetch_historical=False)

            # Add and save initial bill
            bill = Bill.from_dict(sample_bill_data)
            tracker.bills[bill.unique_key] = bill
            tracker._save_database()

            initial_mtime = mock_db_file.stat().st_mtime
            time.sleep(0.1)  # Ensure time difference

            # Make a change
            bill.update(
                status_code="300",
                status_text="Third reading",
                chamber="House of Commons",
                text_url="https://example.com/bill.pdf",
            )

            # Save again
            tracker._save_database()

            new_mtime = mock_db_file.stat().st_mtime
            assert new_mtime > initial_mtime


# ============================================================================
# Utility Function Tests
# ============================================================================


class TestUtilityFunctions:
    """Test suite for utility functions."""

    def test_calculate_days_since_valid_date(self):
        """Test calculating days since a valid date."""
        # Use a date from a few days ago
        test_date = datetime.now()
        test_date = test_date.replace(day=test_date.day - 5)
        date_str = test_date.strftime("%Y-%m-%d")

        days = calculate_days_since(date_str)
        assert days >= 5
        assert days <= 6  # Account for time differences

    def test_calculate_days_since_with_time(self):
        """Test calculating days with timestamp."""
        date_str = "2024-01-15T10:30:00"
        days = calculate_days_since(date_str)
        assert isinstance(days, int)
        assert days >= 0

    def test_calculate_days_since_invalid_date(self):
        """Test calculating days with invalid date."""
        days = calculate_days_since("not-a-date")
        assert days is None

    def test_calculate_days_since_empty_string(self):
        """Test calculating days with empty string."""
        days = calculate_days_since("")
        assert days is None

    def test_load_bills_no_database(self, temp_dir, monkeypatch):
        """Test loading bills when database doesn't exist."""
        # Mock the path
        fake_path = temp_dir / "legislation" / "bills_db.json"
        monkeypatch.setattr("utils.Path", lambda x: fake_path)

        bills = load_bills()
        assert bills == []


# ============================================================================
# Analytics Tests
# ============================================================================


class TestBillAnalytics:
    """Test suite for bill analytics functions."""

    def test_show_royal_assent_summary(self, capsys, sample_bill_data):
        """Test royal assent summary display."""
        # Create bill with royal assent
        bill_with_assent = sample_bill_data.copy()
        bill_with_assent["royal_assent_date"] = "2024-01-20T10:00:00"
        bill_with_assent["chapter_citation"] = "S.C. 2024, c. 15"
        bill_with_assent["cif_status"] = "ACTIVE_ON_ASSENT"

        bills = [bill_with_assent, sample_bill_data]

        show_royal_assent_summary(bills)

        captured = capsys.readouterr()
        assert "ROYAL ASSENT STATUS" in captured.out
        assert "Bills with Royal Assent: 1" in captured.out

    def test_show_activity_summary(self, capsys, sample_bill_data):
        """Test activity summary display."""
        bills = [sample_bill_data]

        show_activity_summary(bills)

        captured = capsys.readouterr()
        assert "ACTIVITY TIMELINE" in captured.out
        assert "Most Recently Active Bills" in captured.out

    def test_show_sponsor_analysis(self, capsys, sample_bill_data):
        """Test sponsor analysis display."""
        bills = [sample_bill_data]

        show_sponsor_analysis(bills)

        captured = capsys.readouterr()
        assert "SPONSOR ANALYSIS" in captured.out
        assert "Hon. John Doe" in captured.out


# ============================================================================
# Bill Lookup Tests
# ============================================================================


class TestBillLookup:
    """Test suite for bill lookup functionality."""

    def test_display_bill(self, capsys, sample_bill_data):
        """Test displaying bill information."""
        display_bill(sample_bill_data)

        captured = capsys.readouterr()
        assert "C-11" in captured.out
        assert "Broadcasting Act" in captured.out
        assert "44-1" in captured.out


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_bill_with_no_history(self):
        """Test bill with empty history."""
        bill = Bill(session="44-1", bill_id="C-1", title="Test")
        assert bill.current_state is None

    def test_bill_with_invalid_session(self):
        """Test bill with malformed session string."""
        bill = Bill(session="invalid", bill_id="C-1", title="Test")
        assert bill.parliament_number == 0

    def test_xml_parsing_with_missing_fields(self, mock_db_file):
        """Test XML parsing when required fields are missing."""
        incomplete_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Bills>
    <Bill>
        <BillNumberFormatted>C-99</BillNumberFormatted>
    </Bill>
</Bills>"""

        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = incomplete_xml.encode()
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            with patch.object(BillTracker, "_load_database"):
                tracker = BillTracker(fetch_historical=False)
                tracker.bills = {}

                # Should handle gracefully without crashing
                try:
                    tracker.fetch_and_process_bills()
                except Exception as e:
                    pytest.fail(f"Should handle incomplete XML gracefully: {e}")

    def test_concurrent_database_operations(self, mock_db_file):
        """Test that concurrent operations don't corrupt database."""
        import threading

        with patch.object(BillTracker, "_fetch_current_bills_xml", return_value=[]):
            tracker = BillTracker(fetch_historical=False)

            # Add some bills
            for i in range(10):
                bill = Bill(session="44-1", bill_id=f"C-{i}", title=f"Bill {i}")
                tracker.bills[bill.unique_key] = bill

            def save_db():
                tracker._save_database()

            # Run multiple save operations concurrently
            threads = [threading.Thread(target=save_db) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # Database should still be valid JSON
            with open(mock_db_file, "r") as f:
                data = json.load(f)  # Should not raise
                assert len(data["bills"]) == 10


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for the complete bill tracking system."""

    def test_full_bill_lifecycle(self, mock_db_file):
        """Test a bill through its complete lifecycle."""
        with patch.object(BillTracker, "_fetch_current_bills_xml", return_value=[]):
            tracker = BillTracker(fetch_historical=False)

            # Create a new bill
            bill = Bill(session="44-1", bill_id="C-TEST", title="Test Lifecycle Bill")
            tracker.bills[bill.unique_key] = bill

            # Stage 1: First Reading
            bill.update(
                status_code="100",
                status_text="First reading",
                chamber="House of Commons",
                text_url="https://example.com/bill.pdf",
            )
            assert bill.current_stage == "FIRST_READING"

            # Stage 2: Second Reading
            bill.update(
                status_code="200",
                status_text="Second reading",
                chamber="House of Commons",
                text_url="https://example.com/bill.pdf",
            )
            assert bill.current_stage == "SECOND_READING"

            # Stage 3: Committee
            bill.update(
                status_code="250",
                status_text="Committee study",
                chamber="House of Commons",
                text_url="https://example.com/bill.pdf",
            )
            assert bill.current_stage == "COMMITTEE"

            # Stage 4: Report Stage (with amendment)
            bill.update(
                status_code="275",
                status_text="Report stage",
                chamber="House of Commons",
                text_url="https://example.com/bill.pdf",
                publication_count=2,
            )
            assert bill.current_stage == "REPORT_STAGE"

            # Stage 5: Third Reading
            bill.update(
                status_code="300",
                status_text="Third reading",
                chamber="House of Commons",
                text_url="https://example.com/bill.pdf",
                publication_count=2,
            )
            assert bill.current_stage == "THIRD_READING"

            # Stage 6: Move to Senate
            bill.update(
                status_code="350",
                status_text="First reading in Senate",
                chamber="Senate",
                text_url="https://example.com/bill.pdf",
                publication_count=2,
            )
            assert bill.current_stage == "SENATE_STAGES"

            # Stage 7: Royal Assent
            bill.royal_assent_date = "2024-06-01T10:00:00"
            bill.update(
                status_code="400",
                status_text="Royal Assent",
                chamber="Senate",
                text_url="https://example.com/bill.pdf",
                publication_count=2,
            )
            assert bill.current_stage == "ROYAL_ASSENT"
            assert bill.is_royal_assent_received is True

            # Verify complete history
            assert len(bill.history) == 7

            # Save and reload
            tracker._save_database()

            # Verify persistence
            with open(mock_db_file, "r") as f:
                data = json.load(f)
                saved_bill = data["bills"][0]
                assert len(saved_bill["history"]) == 7
                assert saved_bill["current_stage"] == "ROYAL_ASSENT"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
