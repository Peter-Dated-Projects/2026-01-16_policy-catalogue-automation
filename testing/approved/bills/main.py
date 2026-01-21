"""
Canadian Legislative Bill Tracking System
A persistent daemon that monitors bill status changes via the LEGISinfo API.
"""

import argparse
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import requests

# Configuration
POLL_INTERVAL_HOURS = 4
LEGIS_URL = "https://www.parl.ca/legisinfo/en/bills/xml"
# Current parliament to actively monitor (auto-detected from API)
# Will be set to the highest parliament number found in the bills
CURRENT_PARLIAMENT = None  # Auto-detected on first fetch
# Historical sessions to track (going back to 35th Parliament, 1994)
# Format: Parliament-Session (e.g., "44-1" = 44th Parliament, 1st Session)
HISTORICAL_PARLIAMENTS = list(range(35, 45))  # Parliaments 35 through 44
STORAGE_DIR = Path("assets")
DB_FILE = STORAGE_DIR / "data.json"

# Logging setup
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class BillStage(Enum):
    """Legislative stages for Canadian bills."""

    FIRST_READING = "First Reading"
    SECOND_READING = "Second Reading"
    COMMITTEE = "Committee"
    REPORT_STAGE = "Report Stage"
    THIRD_READING = "Third Reading"
    PASSED_HOUSE = "Passed House"
    SENATE_STAGES = "Senate Stages"
    ROYAL_ASSENT = "Royal Assent"
    DEFEATED = "Defeated"
    UNKNOWN = "Unknown"


class CIFStatus(Enum):
    """Coming into Force status for bills that received Royal Assent."""

    ACTIVE_ON_ASSENT = "Active on Royal Assent"  # Default: active immediately
    FIXED_DATE = "Fixed Date"  # Specific date mentioned in CIF section
    WAITING_FOR_ORDER = "Waiting for Order in Council"  # Needs regulation to activate
    NOT_DETERMINED = "Not Yet Determined"  # Royal Assent received but CIF not analyzed


@dataclass(frozen=True)
class BillState:
    """Immutable snapshot of a bill's status at a specific point in time."""

    status_code: str
    status_text: str
    timestamp: str  # ISO format datetime
    chamber: str
    text_url: str
    stage: Optional[str] = None  # BillStage enum value name
    text_changed: bool = False  # Whether bill text was amended

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class Bill:
    """Represents a single piece of legislation with its complete history."""

    def __init__(
        self,
        session: str,
        bill_id: str,
        title: str,
        history: Optional[List[BillState]] = None,
        bill_type: Optional[str] = None,
        sponsor: Optional[str] = None,
        sponsor_affiliation: Optional[str] = None,
        royal_assent_date: Optional[str] = None,
        last_activity_date: Optional[str] = None,
        has_royal_recommendation: bool = False,
        current_stage: Optional[str] = None,
        publication_count: int = 0,
        is_active: bool = True,
        died_on_order_paper: bool = False,
        chapter_citation: Optional[str] = None,
        cif_status: Optional[str] = None,
        cif_details: Optional[str] = None,
    ):
        self.session = session
        self.bill_id = bill_id
        self.title = title
        self.history: List[BillState] = history or []
        # Auto-classify if not provided
        self.bill_type = bill_type or self.classify_bill_type(bill_id, title)
        self.sponsor = sponsor
        self.sponsor_affiliation = sponsor_affiliation
        self.royal_assent_date = royal_assent_date
        self.last_activity_date = last_activity_date
        self.has_royal_recommendation = has_royal_recommendation
        # Stage tracking
        self.current_stage = current_stage or BillStage.FIRST_READING.name
        self.publication_count = publication_count
        # Lifecycle tracking
        self.is_active = is_active  # False if from old parliament and didn't pass
        self.died_on_order_paper = (
            died_on_order_paper  # True if bill died when session ended
        )
        # Royal Assent / Statute tracking
        self.chapter_citation = chapter_citation  # e.g., "S.C. 2023, c. 15"
        self.cif_status = (
            cif_status or CIFStatus.NOT_DETERMINED.name
        )  # Coming into Force status
        self.cif_details = cif_details  # Raw text from CIF section

    @staticmethod
    def classify_bill_type(bill_id: str, title: str) -> str:
        """
        Classify bill type based on identifier and title.

        Returns one of:
        - "Government Bill (House)" - C-bills numbered < 201
        - "Private Member's Bill" - C-bills numbered > 200
        - "Senate Bill" - S-bills
        - "Amending Bill" - Title contains "Act to amend"
        - "New Act" - Title contains "Act respecting"
        """
        # Extract bill number from identifier (e.g., "C-11" -> 11, "S-5" -> 5)
        match = re.match(r"([CS])-?(\d+)", bill_id, re.IGNORECASE)

        if not match:
            return "Unknown"

        bill_prefix = match.group(1).upper()
        bill_number = int(match.group(2))

        # Classification by identifier
        if bill_prefix == "C":
            if bill_number < 201:
                bill_category = "Government Bill (House)"
            else:
                bill_category = "Private Member's Bill"
        elif bill_prefix == "S":
            bill_category = "Senate Bill"
        else:
            bill_category = "Unknown"

        # Add amendment/new act classification
        title_lower = title.lower()
        if "act to amend" in title_lower:
            bill_category += " - Amending"
        elif "act respecting" in title_lower:
            bill_category += " - New Act"

        return bill_category

    @property
    def current_state(self) -> Optional[BillState]:
        """Returns the most recent state, or None if no history exists."""
        return self.history[-1] if self.history else None

    @property
    def unique_key(self) -> str:
        """Unique identifier for this bill."""
        return f"{self.session}-{self.bill_id}"

    @property
    def is_royal_assent_received(self) -> bool:
        """Check if bill has received royal assent."""
        return bool(self.royal_assent_date)

    @property
    def parliament_number(self) -> int:
        """Extract parliament number from session (e.g., '44-1' -> 44)."""
        try:
            return int(self.session.split("-")[0])
        except:
            return 0

    @property
    def is_from_current_parliament(self) -> bool:
        """Check if bill is from the current parliament."""
        if CURRENT_PARLIAMENT is None:
            return True  # If not yet determined, treat all as current
        return self.parliament_number == CURRENT_PARLIAMENT

    def determine_stage_transition(
        self, status_text: str, chamber: str, new_publication_count: int = 0
    ) -> Tuple[BillStage, bool]:
        """
        Determine the legislative stage and whether text has changed.

        Args:
            status_text: Current status from XML (e.g., "At second reading...")
            chamber: Current chamber ("House of Commons" or "Senate")
            new_publication_count: Number of publication entries in XML

        Returns:
            Tuple of (BillStage, text_changed_flag)
        """
        text_changed = False
        status_lower = status_text.lower()

        # Check if bill is new (empty history)
        if not self.history:
            return (BillStage.FIRST_READING, False)

        # Get previous chamber
        previous_chamber = self.current_state.chamber if self.current_state else None

        # Chamber switch detection (House -> Senate or Senate -> House)
        if previous_chamber and previous_chamber != chamber:
            if chamber == "Senate" or "senate" in chamber.lower():
                logger.info(f"📨 Bill {self.bill_id} moved to Senate")
                return (BillStage.SENATE_STAGES, False)
            elif chamber == "House of Commons" or "house" in chamber.lower():
                logger.info(f"📨 Bill {self.bill_id} moved to House")
                return (BillStage.PASSED_HOUSE, False)

        # Royal Assent (final stage)
        if "royal assent" in status_lower or self.royal_assent_date:
            return (BillStage.ROYAL_ASSENT, False)

        # Defeated/withdrawn
        if (
            "defeated" in status_lower
            or "withdrawn" in status_lower
            or "not proceeded" in status_lower
        ):
            return (BillStage.DEFEATED, False)

        # Third Reading
        if "third reading" in status_lower:
            return (BillStage.THIRD_READING, False)

        # Report Stage (critical for amendment detection)
        if "report stage" in status_lower or "report" in status_lower:
            # Check if publication count increased (indicates amendment)
            if new_publication_count > self.publication_count:
                text_changed = True
                logger.info(
                    f"📝 Amendment detected for {self.bill_id}: "
                    f"Publications {self.publication_count} → {new_publication_count}"
                )
            return (BillStage.REPORT_STAGE, text_changed)

        # Committee Stage
        if "committee" in status_lower:
            return (BillStage.COMMITTEE, False)

        # Second Reading
        if "second reading" in status_lower:
            return (BillStage.SECOND_READING, False)

        # First Reading (default for new bills or initial stages)
        if "first reading" in status_lower or "introduced" in status_lower:
            return (BillStage.FIRST_READING, False)

        # Passed originating chamber
        if "passed" in status_lower and "house" in status_lower:
            return (BillStage.PASSED_HOUSE, False)

        # If we can't determine, keep current stage
        try:
            current_stage_enum = BillStage[self.current_stage]
        except (KeyError, TypeError):
            current_stage_enum = BillStage.UNKNOWN

        return (current_stage_enum, False)

    def update(
        self,
        status_code: str,
        status_text: str,
        chamber: str,
        text_url: str,
        publication_count: int = 0,
    ) -> bool:
        """
        Compare new data against current state. If different, append new BillState.

        Returns:
            True if a change was detected and recorded, False otherwise.
        """
        # Determine stage transition
        new_stage, text_changed = self.determine_stage_transition(
            status_text, chamber, publication_count
        )

        new_state = BillState(
            status_code=status_code,
            status_text=status_text,
            timestamp=datetime.now().isoformat(),
            chamber=chamber,
            text_url=text_url,
            stage=new_stage.name,
            text_changed=text_changed,
        )

        # Check if state has changed
        if self.current_state is None:
            # First time seeing this bill
            self.current_stage = new_stage.name
            self.publication_count = publication_count
            self.history.append(new_state)
            return True

        # Compare all fields except timestamp
        state_changed = (
            self.current_state.status_code != new_state.status_code
            or self.current_state.status_text != new_state.status_text
            or self.current_state.chamber != new_state.chamber
            or self.current_state.stage != new_state.stage
            or text_changed
        )

        if state_changed:
            old_status = self.current_state.status_text
            old_stage = self.current_state.stage or "Unknown"

            # Update tracking fields
            self.current_stage = new_stage.name
            self.publication_count = publication_count

            self.history.append(new_state)

            # Enhanced logging
            if text_changed:
                logger.info(
                    f"📝 AMENDMENT: Bill {self.bill_id} text changed at {new_stage.value}"
                )

            stage_change = (
                f" [{old_stage} → {new_stage.name}]"
                if old_stage != new_stage.name
                else ""
            )
            logger.info(
                f"⚠️  ALERT: Bill {self.bill_id} moved from '{old_status}' → '{status_text}'{stage_change}"
            )

            # If bill just received Royal Assent, trigger statute processing
            if (
                new_stage == BillStage.ROYAL_ASSENT
                and old_stage != BillStage.ROYAL_ASSENT.name
            ):
                logger.info(
                    f"🎉 Bill {self.bill_id} received ROYAL ASSENT - now a Statute!"
                )
                # Note: Full text processing would happen here if we had access to bill text
                # For now, we mark it for later processing
                self.cif_status = CIFStatus.NOT_DETERMINED.name

            return True

        return False

    def to_dict(self) -> Dict:
        """Serialize bill and its full history for JSON storage."""
        return {
            "session": self.session,
            "bill_id": self.bill_id,
            "title": self.title,
            "bill_type": self.bill_type,
            "sponsor": self.sponsor,
            "sponsor_affiliation": self.sponsor_affiliation,
            "royal_assent_date": self.royal_assent_date,
            "last_activity_date": self.last_activity_date,
            "has_royal_recommendation": self.has_royal_recommendation,
            "current_stage": self.current_stage,
            "publication_count": self.publication_count,
            "is_active": self.is_active,
            "died_on_order_paper": self.died_on_order_paper,
            "chapter_citation": self.chapter_citation,
            "cif_status": self.cif_status,
            "cif_details": self.cif_details,
            "history": [state.to_dict() for state in self.history],
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Bill":
        """Deserialize bill from JSON data."""
        history = [BillState(**state_data) for state_data in data.get("history", [])]
        return cls(
            session=data["session"],
            bill_id=data["bill_id"],
            title=data["title"],
            history=history,
            bill_type=data.get("bill_type"),  # Backward compatible
            sponsor=data.get("sponsor"),
            sponsor_affiliation=data.get("sponsor_affiliation"),
            royal_assent_date=data.get("royal_assent_date"),
            last_activity_date=data.get("last_activity_date"),
            has_royal_recommendation=data.get("has_royal_recommendation", False),
            current_stage=data.get("current_stage"),
            publication_count=data.get("publication_count", 0),
            is_active=data.get(
                "is_active", True
            ),  # Backward compatible - default to True
            died_on_order_paper=data.get("died_on_order_paper", False),
            chapter_citation=data.get("chapter_citation"),
            cif_status=data.get("cif_status"),
            cif_details=data.get("cif_details"),
        )


# =============================================================================
# Royal Assent Processing Functions
# =============================================================================


def extract_chapter_citation(bill_text: str, metadata: Dict) -> Optional[str]:
    """
    Extract the chapter citation (permanent statute ID) from bill text or metadata.

    Searches for patterns like:
    - S.C. 2024, c. 15
    - Statutes of Canada 2024 Chapter 15
    - S.C. 2023, ch. 42

    Args:
        bill_text: Full text of the bill/statute
        metadata: Bill metadata dictionary

    Returns:
        Chapter citation string or None if not found
    """
    # Pattern 1: S.C. YYYY, c. NN (most common)
    pattern1 = r"S\.C\.\s*(\d{4}),\s*c(?:h)?\.?\s*(\d+)"

    # Pattern 2: Statutes of Canada YYYY Chapter NN
    pattern2 = r"Statutes\s+of\s+Canada\s+(\d{4})\s+Chapter\s+(\d+)"

    # Pattern 3: Alternative formatting variations
    pattern3 = (
        r"(?:S\.C\.|Statutes of Canada)\s*(\d{4})[,\s]+(?:c\.|ch\.|Chapter)\s*(\d+)"
    )

    # Search in metadata first (more reliable)
    metadata_text = str(metadata)
    for pattern in [pattern1, pattern2, pattern3]:
        match = re.search(pattern, metadata_text, re.IGNORECASE)
        if match:
            year = match.group(1)
            chapter = match.group(2)
            return f"S.C. {year}, c. {chapter}"

    # Search in bill text (first 5000 chars where chapter info usually appears)
    text_header = bill_text[:5000] if bill_text else ""
    for pattern in [pattern1, pattern2, pattern3]:
        match = re.search(pattern, text_header, re.IGNORECASE)
        if match:
            year = match.group(1)
            chapter = match.group(2)
            return f"S.C. {year}, c. {chapter}"

    return None


def analyze_coming_into_force(bill_text: str) -> Tuple[str, Optional[str]]:
    """
    Analyze the Coming into Force (CIF) section of a bill.

    Canadian bills have three common CIF patterns:
    1. Active on Royal Assent (immediate)
    2. Fixed date (specific year/date mentioned)
    3. Order in Council (requires future regulation)

    Args:
        bill_text: Full text of the bill/statute

    Returns:
        Tuple of (CIFStatus enum name, details text)
    """
    if not bill_text:
        return (CIFStatus.NOT_DETERMINED.name, None)

    # Scan last 2000 characters where CIF sections typically appear
    cif_section = bill_text[-2000:]

    # Look for Coming into Force header
    cif_patterns = [
        r"Coming into Force",
        r"Coming into force",
        r"Commencement",
        r"Entry into Force",
    ]

    cif_header_found = False
    cif_text_start = -1

    for pattern in cif_patterns:
        match = re.search(pattern, cif_section, re.IGNORECASE)
        if match:
            cif_header_found = True
            cif_text_start = match.start()
            break

    # If no CIF section found, default to active on assent
    if not cif_header_found:
        return (
            CIFStatus.ACTIVE_ON_ASSENT.name,
            "No Coming into Force section found - defaults to Royal Assent",
        )

    # Extract text after CIF header (next 500 chars)
    cif_details = cif_section[cif_text_start : cif_text_start + 500]

    # Check for Order in Council pattern
    order_patterns = [
        r"Order in Council",
        r"order of the Governor in Council",
        r"by order of the Governor",
        r"fixed by order",
    ]

    for pattern in order_patterns:
        if re.search(pattern, cif_details, re.IGNORECASE):
            return (CIFStatus.WAITING_FOR_ORDER.name, cif_details.strip())

    # Check for specific date/year mentions
    date_patterns = [
        r"\d{4}",  # Year
        r"(January|February|March|April|May|June|July|August|September|October|November|December)",
        r"\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)",
        r"on a day to be fixed",
    ]

    for pattern in date_patterns:
        if re.search(pattern, cif_details, re.IGNORECASE):
            # If mentions "to be fixed" it's likely Order in Council
            if re.search(r"to be fixed", cif_details, re.IGNORECASE):
                return (CIFStatus.WAITING_FOR_ORDER.name, cif_details.strip())
            return (CIFStatus.FIXED_DATE.name, cif_details.strip())

    # Check for "on assent" or "on sanction"
    assent_patterns = [
        r"on (?:the day on which|royal) assent",
        r"on sanction",
        r"(?:on|upon) (?:its )?(?:receiving|receipt of) (?:royal )?assent",
    ]

    for pattern in assent_patterns:
        if re.search(pattern, cif_details, re.IGNORECASE):
            return (CIFStatus.ACTIVE_ON_ASSENT.name, cif_details.strip())

    # Default to active on assent if section exists but unclear
    return (CIFStatus.ACTIVE_ON_ASSENT.name, cif_details.strip())


def process_passed_bill(bill: Bill, bill_text: str = "", metadata: Dict = None) -> bool:
    """
    Process a bill that has received Royal Assent.

    Extracts chapter citation and analyzes Coming into Force status.
    Only runs once when bill transitions to ROYAL_ASSENT stage.

    NOTE: This function is available for future use when bill text becomes accessible
    via API. Currently not called automatically but infrastructure is ready.

    Args:
        bill: Bill object that received Royal Assent
        bill_text: Full text of the bill/statute (if available)
        metadata: Bill metadata dictionary

    Returns:
        True if processing was performed, False if already processed
    """
    # Only process if not already done
    if bill.chapter_citation or bill.cif_status != CIFStatus.NOT_DETERMINED.name:
        return False

    metadata = metadata or {}

    # Extract chapter citation
    chapter = extract_chapter_citation(bill_text, metadata)
    if chapter:
        bill.chapter_citation = chapter
        logger.info(f"📜 Bill {bill.bill_id} chapter citation: {chapter}")
    else:
        logger.warning(f"⚠️  Could not extract chapter citation for {bill.bill_id}")

    # Analyze Coming into Force
    cif_status, cif_details = analyze_coming_into_force(bill_text)
    bill.cif_status = cif_status
    bill.cif_details = cif_details

    # Log CIF status
    status_emoji = {
        CIFStatus.ACTIVE_ON_ASSENT.name: "✅",
        CIFStatus.FIXED_DATE.name: "📅",
        CIFStatus.WAITING_FOR_ORDER.name: "⏳",
    }
    emoji = status_emoji.get(cif_status, "❓")
    logger.info(f"{emoji} Bill {bill.bill_id} CIF status: {cif_status}")

    return True


class BillTracker:
    """Tracks bills and their status changes over time."""

    def __init__(self, fetch_historical: bool = True):
        self.bills: Dict[str, Bill] = {}
        self.fetch_historical = fetch_historical
        self._ensure_storage_exists()
        self._load_database()

    def _ensure_storage_exists(self) -> None:
        """Create the legislation folder if it doesn't exist."""
        STORAGE_DIR.mkdir(exist_ok=True)
        logger.info(f"Storage directory verified: {STORAGE_DIR.absolute()}")

    def _detect_current_parliament(self, bill_data_list: List[Dict]) -> int:
        """Detect the current parliament number from bill data.

        Returns the highest parliament number found in the bills.

        Args:
            bill_data_list: List of bill data dictionaries with 'session' field

        Returns:
            Highest parliament number found
        """
        parliament_numbers = []
        for bill_data in bill_data_list:
            session = bill_data.get("session", "")
            if session and "-" in session:
                try:
                    parliament_num = int(session.split("-")[0])
                    parliament_numbers.append(parliament_num)
                except (ValueError, IndexError):
                    continue

        if parliament_numbers:
            current = max(parliament_numbers)
            return current

        # Fallback to 44 if no bills found (shouldn't happen)
        return 44

    def _update_current_parliament(self, new_parliament: int) -> None:
        """Update the global CURRENT_PARLIAMENT if a newer parliament is detected."""
        global CURRENT_PARLIAMENT

        if CURRENT_PARLIAMENT is None:
            CURRENT_PARLIAMENT = new_parliament
            logger.info(f"🏛️  Detected current parliament: {CURRENT_PARLIAMENT}")
        elif new_parliament > CURRENT_PARLIAMENT:
            old = CURRENT_PARLIAMENT
            CURRENT_PARLIAMENT = new_parliament
            logger.info(
                f"🏛️  Parliament changed: {old} → {CURRENT_PARLIAMENT} "
                f"(new parliament session detected!)"
            )

    def _load_database(self) -> None:
        """Load existing bills and their history from disk.

        First fetches current bills to detect parliament number, then loads
        historical data if needed.
        """
        # Step 1: Always fetch current bills first to detect parliament number
        logger.info("Fetching current bills to detect parliament...")
        current_bills_data = self._fetch_current_bills_xml()

        if current_bills_data:
            detected_parliament = self._detect_current_parliament(current_bills_data)
            self._update_current_parliament(detected_parliament)
        else:
            logger.warning(
                "Could not fetch current bills. Will use default parliament."
            )

        # Step 2: Load existing database
        if not DB_FILE.exists():
            logger.info("No existing database found. Starting fresh.")

            # Process the current bills we just fetched
            if current_bills_data:
                logger.info(f"Processing {len(current_bills_data)} current bills...")
                self._process_bill_data_batch(current_bills_data)

            # Then fetch historical if requested
            if self.fetch_historical:
                logger.info("Will perform initial historical bill fetch...")
                self._fetch_historical_bills()

            # Save everything
            self._save_database()
            return

        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            for bill_data in data.get("bills", []):
                bill = Bill.from_dict(bill_data)
                self.bills[bill.unique_key] = bill

            bills_loaded = len(self.bills)
            logger.info(f"Loaded {bills_loaded} bills from database.")

            # Process current bills to update any changes
            if current_bills_data:
                logger.info(f"Updating {len(current_bills_data)} current bills...")
                changes = self._process_bill_data_batch(current_bills_data)
                if changes > 0:
                    logger.info(f"Detected {changes} changes in current bills.")
                    self._save_database()

            # If database exists but is empty/very small, offer to fetch historical
            if bills_loaded < 10 and self.fetch_historical:
                logger.info(
                    f"Database has only {bills_loaded} bills. "
                    "Fetching historical bills to populate database..."
                )
                self._fetch_historical_bills()
                self._save_database()
        except Exception as e:
            logger.error(f"Failed to load database: {e}")

    def _fetch_current_bills_xml(self) -> List[Dict]:
        """Fetch and parse current bills from the main API endpoint.

        Returns:
            List of parsed bill data dictionaries
        """
        try:
            response = requests.get(LEGIS_URL, timeout=30)
            response.raise_for_status()

            root = ET.fromstring(response.content)
            ns = {"ns": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}

            bill_data_list = []
            for bill_elem in root.iter():
                if "Bill" in bill_elem.tag:
                    try:
                        bill_data = self._parse_bill_element(bill_elem, ns)
                        if bill_data:
                            bill_data_list.append(bill_data)
                    except Exception as e:
                        logger.debug(f"Failed to parse bill element: {e}")

            return bill_data_list

        except requests.RequestException as e:
            logger.error(f"Network error fetching current bills: {e}")
            return []
        except Exception as e:
            logger.error(f"Error parsing current bills XML: {e}")
            return []

    def _process_bill_data_batch(self, bill_data_list: List[Dict]) -> int:
        """Process a batch of bill data and return number of changes detected.

        Args:
            bill_data_list: List of bill data dictionaries

        Returns:
            Number of bills that had changes
        """
        changes = 0
        for bill_data in bill_data_list:
            try:
                # Only process bills from current parliament
                session = bill_data["session"]
                parliament_num = int(session.split("-")[0])

                if CURRENT_PARLIAMENT and parliament_num == CURRENT_PARLIAMENT:
                    changed = self._process_bill(bill_data, suppress_new_log=False)
                    if changed:
                        changes += 1
            except Exception as e:
                logger.warning(f"Failed to process bill: {e}")

        return changes

    def _save_database(self) -> None:
        """Save all bills and their history to disk."""
        try:
            data = {
                "last_updated": datetime.now().isoformat(),
                "bills": [bill.to_dict() for bill in self.bills.values()],
            }

            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info(f"Database saved with {len(self.bills)} bills.")
        except Exception as e:
            logger.error(f"Failed to save database: {e}")

    def _fetch_historical_bills(self) -> None:
        """Fetch all bills from historical parliamentary sessions."""
        logger.info("=" * 60)
        logger.info("HISTORICAL BILL FETCH - This may take several minutes...")
        logger.info("=" * 60)

        total_fetched = 0

        for parliament_num in HISTORICAL_PARLIAMENTS:
            # Most parliaments have 1-2 sessions, some have more
            for session_num in range(1, 5):  # Try up to 4 sessions per parliament
                session_id = f"{parliament_num}-{session_num}"

                try:
                    # Build session-specific URL
                    session_url = f"https://www.parl.ca/legisinfo/en/bills/xml?parlsession={parliament_num}-{session_num}"

                    logger.info(f"Fetching Parliament {session_id}...")
                    response = requests.get(session_url, timeout=30)

                    # If session doesn't exist, we'll get 404 or empty response
                    if response.status_code == 404:
                        break  # No more sessions for this parliament

                    response.raise_for_status()

                    # Try to parse - if empty or invalid, move on
                    try:
                        root = ET.fromstring(response.content)
                    except ET.ParseError:
                        logger.warning(f"Could not parse XML for session {session_id}")
                        break

                    ns = (
                        {"ns": root.tag.split("}")[0].strip("{")}
                        if "}" in root.tag
                        else {}
                    )

                    session_count = 0
                    for bill_elem in root.iter():
                        if "Bill" in bill_elem.tag:
                            try:
                                bill_data = self._parse_bill_element(bill_elem, ns)
                                if bill_data:
                                    self._process_bill(bill_data, suppress_new_log=True)
                                    session_count += 1
                            except Exception as e:
                                logger.debug(
                                    f"Failed to parse bill in {session_id}: {e}"
                                )

                    if session_count == 0:
                        break  # Empty session, likely end of this parliament

                    total_fetched += session_count
                    logger.info(f"  → Added {session_count} bills from {session_id}")

                    # Be respectful to the API
                    time.sleep(1)

                except requests.RequestException:
                    # Session doesn't exist or network issue
                    break
                except Exception as e:
                    logger.warning(f"Error fetching session {session_id}: {e}")
                    break

        logger.info("=" * 60)
        logger.info(f"Historical fetch complete: {total_fetched} bills added")
        logger.info("=" * 60)

        # Save the historical data
        self._save_database()

    def fetch_and_process_bills(self) -> None:
        """Fetch bills from LEGISinfo API and process changes.

        Only monitors bills from the current parliament. Historical bills are
        preserved but not actively polled.
        """
        try:
            logger.info("Fetching current bills from LEGISinfo API...")

            # Fetch and parse current bills
            all_bill_data = self._fetch_current_bills_xml()

            if not all_bill_data:
                logger.warning("No bills fetched from API.")
                return

            # Auto-detect current parliament from the bills we found
            detected_parliament = self._detect_current_parliament(all_bill_data)
            self._update_current_parliament(detected_parliament)

            # Now process bills from current parliament
            logger.info(f"Processing bills from parliament {CURRENT_PARLIAMENT}...")
            bills_processed = 0
            changes_detected = 0
            current_parliament_bills = set()

            # Process the bills
            for bill_data in all_bill_data:
                try:
                    # Only process bills from current parliament
                    session = bill_data["session"]
                    parliament_num = int(session.split("-")[0])

                    if parliament_num == CURRENT_PARLIAMENT:
                        unique_key = f"{session}-{bill_data['bill_id']}"
                        current_parliament_bills.add(unique_key)
                        changed = self._process_bill(bill_data)
                        bills_processed += 1
                        if changed:
                            changes_detected += 1
                    else:
                        logger.debug(
                            f"Skipping historical bill {bill_data['bill_id']} from parliament {parliament_num}"
                        )
                except Exception as e:
                    logger.warning(f"Failed to process bill: {e}")

            # Mark bills from previous parliaments as inactive if they didn't receive royal assent
            self._update_bill_lifecycle_status(current_parliament_bills)

            logger.info(
                f"Processed {bills_processed} active bills. "
                f"Changes detected: {changes_detected}"
            )

            # Save after processing
            self._save_database()

        except requests.RequestException as e:
            logger.error(f"Network error while fetching bills: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during fetch: {e}")

    def _update_bill_lifecycle_status(self, current_parliament_bills: set) -> None:
        """Mark bills from old parliaments as inactive if they died on the order paper.

        Canadian parliamentary rule: Bills that don't receive Royal Assent before
        a parliament/session ends die on the order paper and must be reintroduced
        as new bills in the next session.
        """
        for unique_key, bill in self.bills.items():
            # Skip if bill already marked as inactive
            if not bill.is_active:
                continue

            # If bill received royal assent, it's permanently law (never dies)
            if bill.is_royal_assent_received:
                continue

            # If bill is from an old parliament and not in current API feed
            if (
                not bill.is_from_current_parliament
                and unique_key not in current_parliament_bills
            ):
                if bill.is_active:  # Only log once when marking inactive
                    logger.info(
                        f"⚰️  Bill {bill.bill_id} ({bill.session}) died on order paper "
                        f"(parliament ended without Royal Assent)"
                    )
                    bill.is_active = False
                    bill.died_on_order_paper = True

    def _parse_bill_element(self, elem: ET.Element, ns: Dict) -> Optional[Dict]:
        """Extract bill data from XML element."""

        def safe_find(path: str) -> Optional[str]:
            """Safely find element text, handling namespaces and missing elements."""
            try:
                found = elem.find(path)
                if found is not None and found.text:
                    return found.text.strip()
            except:
                pass
            return None

        # Extract data from the actual XML structure
        bill_number = safe_find("BillNumberFormatted")  # e.g., "C-11" or "S-1"
        session_code = safe_find("ParlSessionCode")  # e.g., "44-1"

        # Also try alternative field names
        if not bill_number:
            bill_number = safe_find("BillNumber") or safe_find("Number")
        if not session_code:
            session_code = safe_find("Session") or safe_find("Parliament")

        # Get title - try long title first
        title = (
            safe_find("LongTitleEn")
            or safe_find("ShortTitleEn")
            or safe_find("Title")
            or "Unknown Title"
        )

        # Status information
        status_text = (
            safe_find("CurrentStatusEn")
            or safe_find("LatestCompletedMajorStageEn")
            or safe_find("Status")
            or "Unknown Status"
        )

        status_code = safe_find("CurrentStatusId") or "UNKNOWN"

        # Chamber information
        chamber_id = safe_find("OriginatingChamberId")
        if chamber_id == "1":
            chamber = "House of Commons"
        elif chamber_id == "2":
            chamber = "Senate"
        else:
            chamber = safe_find("Chamber") or "Unknown"

        if not bill_number or not session_code:
            return None

        text_url = f"https://www.parl.ca/legisinfo/en/bill/{session_code}/{bill_number}"

        # New tracking fields
        sponsor = safe_find("SponsorEn")
        sponsor_affiliation = safe_find("PoliticalAffiliationId")
        royal_assent_date = safe_find("ReceivedRoyalAssentDateTime")
        last_activity_date = safe_find("LatestActivityDateTime")

        # Count publications (for amendment detection)
        publication_count = 0
        try:
            # Count all Publication elements under this bill
            for pub in elem.findall(".//Publication"):
                publication_count += 1
        except:
            pass

        # Check for royal recommendation (typically indicated by MinistryId or certain bill types)
        ministry_id = safe_find("MinistryId")
        bill_type_text = safe_find("BillTypeEn") or ""
        has_royal_recommendation = (
            ministry_id and ministry_id != "0"
        ) or "Government Bill" in bill_type_text

        return {
            "bill_id": bill_number,
            "session": session_code,
            "title": title,
            "status_code": status_code,
            "status_text": status_text,
            "chamber": chamber,
            "text_url": text_url,
            "sponsor": sponsor,
            "sponsor_affiliation": sponsor_affiliation,
            "royal_assent_date": royal_assent_date,
            "last_activity_date": last_activity_date,
            "has_royal_recommendation": has_royal_recommendation,
            "publication_count": publication_count,
        }

    def _process_bill(self, bill_data: Dict, suppress_new_log: bool = False) -> bool:
        """Process a bill, updating or creating as needed."""
        session = bill_data["session"]
        bill_id = bill_data["bill_id"]
        unique_key = f"{session}-{bill_id}"

        # Get or create bill
        if unique_key not in self.bills:
            bill = Bill(
                session=session,
                bill_id=bill_id,
                title=bill_data["title"],
                sponsor=bill_data.get("sponsor"),
                sponsor_affiliation=bill_data.get("sponsor_affiliation"),
                royal_assent_date=bill_data.get("royal_assent_date"),
                last_activity_date=bill_data.get("last_activity_date"),
                has_royal_recommendation=bill_data.get(
                    "has_royal_recommendation", False
                ),
            )
            self.bills[unique_key] = bill
            if not suppress_new_log:
                sponsor_info = f" | Sponsor: {bill.sponsor}" if bill.sponsor else ""
                logger.info(
                    f"📝 New bill tracked: {bill_id} ({bill.bill_type}){sponsor_info} - {bill_data['title'][:50]}"
                )
        else:
            bill = self.bills[unique_key]
            # Update metadata that might change
            bill.sponsor = bill_data.get("sponsor") or bill.sponsor
            bill.sponsor_affiliation = (
                bill_data.get("sponsor_affiliation") or bill.sponsor_affiliation
            )
            bill.royal_assent_date = (
                bill_data.get("royal_assent_date") or bill.royal_assent_date
            )
            bill.last_activity_date = (
                bill_data.get("last_activity_date") or bill.last_activity_date
            )
            bill.has_royal_recommendation = bill_data.get(
                "has_royal_recommendation", bill.has_royal_recommendation
            )

        # Update and check for changes
        return bill.update(
            status_code=bill_data["status_code"],
            status_text=bill_data["status_text"],
            chamber=bill_data["chamber"],
            text_url=bill_data["text_url"],
            publication_count=bill_data.get("publication_count", 0),
        )

    def run_daemon(self, time_delay_seconds: float = POLL_INTERVAL_HOURS) -> None:
        """Main daemon loop - polls indefinitely."""
        logger.info("=" * 60)
        logger.info("Canadian Legislative Bill Tracker - STARTED")
        logger.info(f"Poll interval: {round(time_delay_seconds / 3600, 2)} hours")
        logger.info("=" * 60)

        while True:
            try:
                self.fetch_and_process_bills()

                sleep_seconds = time_delay_seconds
                next_poll = datetime.now().replace(microsecond=0)
                next_poll = next_poll.timestamp() + sleep_seconds
                next_poll_str = datetime.fromtimestamp(next_poll).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

                logger.info(f"Sleeping until next poll at {next_poll_str}")
                time.sleep(sleep_seconds)

            except KeyboardInterrupt:
                logger.info("\n🛑 Daemon stopped by user.")
                break
            except Exception as e:
                logger.error(f"Unexpected error in daemon loop: {e}")
                logger.info("Retrying in 5 minutes...")
                time.sleep(300)  # Wait 5 minutes before retry


def main():
    """Entry point for the bill tracking daemon."""
    parser = argparse.ArgumentParser(
        description="Canadian Legislative Bill Tracking System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run daemon with historical fetch on first run
  python main.py
  
  # Run daemon without historical fetch (faster startup)
  python main.py --no-historical
  
  # Force fetch all historical bills (even if database exists)
  python main.py --force-historical
        """,
    )
    parser.add_argument(
        "--no-historical",
        action="store_true",
        help="Skip automatic historical bill fetch on first run",
    )
    parser.add_argument(
        "--force-historical",
        action="store_true",
        help="Force fetch all historical bills, even if database exists",
    )

    args = parser.parse_args()

    # Determine if we should fetch historical bills
    fetch_historical = not args.no_historical

    tracker = BillTracker(fetch_historical=fetch_historical)

    # If force-historical is set, fetch regardless of database state
    if args.force_historical:
        logger.info("Force historical fetch requested...")
        tracker._fetch_historical_bills()

    tracker.run_daemon(time_delay_seconds=POLL_INTERVAL_HOURS * 3600)
    # tracker.run_daemon(time_delay_seconds=30)


if __name__ == "__main__":
    main()
