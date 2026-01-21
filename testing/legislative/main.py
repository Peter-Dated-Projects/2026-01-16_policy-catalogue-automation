"""
Canadian Legislative Bill Tracking System
A persistent daemon that monitors bill status changes via the LEGISinfo API.
"""

import argparse
import json
import logging
import os
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
# Current parliament to actively monitor (bills in older sessions are historical only)
CURRENT_PARLIAMENT = 44  # Update this when a new parliament begins
# Historical sessions to track (going back to 35th Parliament, 1994)
# Format: Parliament-Session (e.g., "44-1" = 44th Parliament, 1st Session)
HISTORICAL_PARLIAMENTS = list(range(35, 45))  # Parliaments 35 through 44
STORAGE_DIR = Path("assets")
DB_FILE = STORAGE_DIR / "bills_db.json"

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
    def days_since_last_activity(self) -> Optional[int]:
        """Calculate days since last activity."""
        if not self.last_activity_date:
            return None
        try:
            # Parse ISO format datetime (may include timezone)
            if "T" in self.last_activity_date:
                # Remove timezone info for parsing
                date_part = self.last_activity_date.split("T")[0]
                last_date = datetime.fromisoformat(date_part)
            else:
                last_date = datetime.fromisoformat(self.last_activity_date)

            days = (datetime.now() - last_date).days
            return days
        except:
            return None

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
        )


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

    def _load_database(self) -> None:
        """Load existing bills and their history from disk."""
        if not DB_FILE.exists():
            logger.info("No existing database found. Starting fresh.")
            if self.fetch_historical:
                logger.info("Will perform initial historical bill fetch...")
                self._fetch_historical_bills()
            return

        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            for bill_data in data.get("bills", []):
                bill = Bill.from_dict(bill_data)
                self.bills[bill.unique_key] = bill

            bills_loaded = len(self.bills)
            logger.info(f"Loaded {bills_loaded} bills from database.")

            # If database exists but is empty/very small, offer to fetch historical
            if bills_loaded < 10 and self.fetch_historical:
                logger.info(
                    f"Database has only {bills_loaded} bills. "
                    "Fetching historical bills to populate database..."
                )
                self._fetch_historical_bills()
        except Exception as e:
            logger.error(f"Failed to load database: {e}")

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
            logger.info(
                f"Fetching current parliament {CURRENT_PARLIAMENT} bills from LEGISinfo API..."
            )
            response = requests.get(LEGIS_URL, timeout=30)
            response.raise_for_status()

            root = ET.fromstring(response.content)

            # Handle XML namespaces if present
            ns = {"ns": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}

            bills_processed = 0
            changes_detected = 0
            current_parliament_bills = set()

            # Parse bills from XML
            for bill_elem in root.iter():
                if "Bill" in bill_elem.tag:
                    try:
                        bill_data = self._parse_bill_element(bill_elem, ns)
                        if bill_data:
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
                        logger.warning(f"Failed to parse bill element: {e}")

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
