import requests
import xml.etree.ElementTree as ET
import feedparser
import json
import difflib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path
import time
import schedule
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ============================================================================
# DATA STRUCTURES
# ============================================================================


@dataclass
class ChangeEvent:
    """Unified data structure for all policy/legislative changes"""

    event_type: str  # NEW, AMENDMENT, STATUS_CHANGE
    source: str  # LEGISLATIVE, EXECUTIVE
    id: str
    title: str
    timestamp: str
    change_summary: Dict[str, Any]
    url: Optional[str] = None

    def to_dict(self):
        return asdict(self)


@dataclass
class BillStatus:
    """Tracks bill status for change detection"""

    bill_id: str
    session_id: str
    title: str
    status: str
    last_updated: str
    text_version: Optional[str] = None


# ============================================================================
# PIPELINE A: LEGISLATIVE TRACKER (LEGISinfo)
# ============================================================================


class LegislativeTracker:
    """Tracks bills from LEGISinfo API"""

    MASTER_LIST_URL = "https://www.parl.ca/legisinfo/en/bills/xml"
    BILL_DETAIL_URL = "https://www.parl.ca/legisinfo/en/bill/{session_id}/{bill_id}/xml"

    def __init__(self, storage_path: str = "./data/bills_state.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.previous_state: Dict[str, BillStatus] = self._load_state()

    def _load_state(self) -> Dict[str, BillStatus]:
        """Load previous bill states from disk"""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                    return {k: BillStatus(**v) for k, v in data.items()}
            except Exception as e:
                logger.error(f"Error loading state: {e}")
                return {}
        return {}

    def _save_state(self):
        """Save current bill states to disk"""
        try:
            data = {k: asdict(v) for k, v in self.previous_state.items()}
            with open(self.storage_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving state: {e}")

    def fetch_master_list(self) -> List[Dict[str, str]]:
        """Fetch all bills from master list"""
        try:
            response = requests.get(self.MASTER_LIST_URL, timeout=30)
            response.raise_for_status()

            root = ET.fromstring(response.content)
            bills = []

            # Parse XML structure (adjust based on actual LEGISinfo XML schema)
            for bill in root.findall(".//Bill"):
                bill_data = {
                    "bill_id": bill.findtext("BillId", ""),
                    "session_id": bill.findtext("SessionId", ""),
                    "title": bill.findtext("Title", ""),
                    "status": bill.findtext("Status", ""),
                    "last_updated": bill.findtext("LastUpdated", ""),
                }
                bills.append(bill_data)

            logger.info(f"Fetched {len(bills)} bills from master list")
            return bills

        except Exception as e:
            logger.error(f"Error fetching master list: {e}")
            return []

    def fetch_bill_details(self, session_id: str, bill_id: str) -> Optional[Dict]:
        """Fetch detailed information for a specific bill"""
        try:
            url = self.BILL_DETAIL_URL.format(session_id=session_id, bill_id=bill_id)
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            root = ET.fromstring(response.content)

            # Extract detailed information
            details = {
                "bill_id": bill_id,
                "session_id": session_id,
                "title": root.findtext(".//Title", ""),
                "status": root.findtext(".//Status", ""),
                "summary": root.findtext(".//Summary", ""),
                "text_url": root.findtext(".//TextURL", ""),
                "sponsor": root.findtext(".//Sponsor", ""),
                "events": [],
            }

            # Parse events/stages
            for event in root.findall(".//Event"):
                details["events"].append(
                    {
                        "date": event.findtext("Date", ""),
                        "stage": event.findtext("Stage", ""),
                        "chamber": event.findtext("Chamber", ""),
                    }
                )

            return details

        except Exception as e:
            logger.error(f"Error fetching bill details for {bill_id}: {e}")
            return None

    def fetch_bill_text(self, text_url: str) -> Optional[str]:
        """Fetch the actual text of a bill"""
        try:
            response = requests.get(text_url, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Error fetching bill text from {text_url}: {e}")
            return None

    def generate_diff(self, old_text: str, new_text: str) -> Dict[str, Any]:
        """Generate a diff between two versions of bill text"""
        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)

        # Generate unified diff
        diff = list(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile="Previous Version",
                tofile="Current Version",
                lineterm="",
            )
        )

        # Calculate statistics
        additions = sum(
            1 for line in diff if line.startswith("+") and not line.startswith("+++")
        )
        deletions = sum(
            1 for line in diff if line.startswith("-") and not line.startswith("---")
        )

        return {
            "diff_lines": diff,
            "additions": additions,
            "deletions": deletions,
            "total_changes": additions + deletions,
        }

    def detect_changes(self) -> List[ChangeEvent]:
        """Main polling function: detect changes in bills"""
        logger.info("Starting legislative change detection...")
        events = []

        current_bills = self.fetch_master_list()

        for bill_data in current_bills:
            bill_key = f"{bill_data['session_id']}-{bill_data['bill_id']}"
            current_status = BillStatus(
                bill_id=bill_data["bill_id"],
                session_id=bill_data["session_id"],
                title=bill_data["title"],
                status=bill_data["status"],
                last_updated=bill_data["last_updated"],
            )

            # Check if this is a new bill
            if bill_key not in self.previous_state:
                logger.info(f"New bill detected: {bill_key}")
                event = ChangeEvent(
                    event_type="NEW",
                    source="LEGISLATIVE",
                    id=bill_data["bill_id"],
                    title=bill_data["title"],
                    timestamp=datetime.now().isoformat(),
                    change_summary={
                        "session_id": bill_data["session_id"],
                        "initial_status": bill_data["status"],
                    },
                    url=self.BILL_DETAIL_URL.format(
                        session_id=bill_data["session_id"], bill_id=bill_data["bill_id"]
                    ),
                )
                events.append(event)

            # Check if status has changed
            elif self.previous_state[bill_key].status != current_status.status:
                logger.info(
                    f"Status change detected for {bill_key}: "
                    f"{self.previous_state[bill_key].status} → {current_status.status}"
                )

                # Fetch detailed information
                details = self.fetch_bill_details(
                    bill_data["session_id"], bill_data["bill_id"]
                )

                change_summary = {
                    "previous_status": self.previous_state[bill_key].status,
                    "new_status": current_status.status,
                    "session_id": bill_data["session_id"],
                }

                # If text URL is available, attempt to generate diff
                if details and details.get("text_url"):
                    current_text = self.fetch_bill_text(details["text_url"])
                    if current_text and self.previous_state[bill_key].text_version:
                        diff_result = self.generate_diff(
                            self.previous_state[bill_key].text_version, current_text
                        )
                        change_summary["diff_stats"] = {
                            "additions": diff_result["additions"],
                            "deletions": diff_result["deletions"],
                            "total_changes": diff_result["total_changes"],
                        }
                        # Store diff for later retrieval
                        diff_path = Path(f"./data/diffs/{bill_key}-diff.txt")
                        diff_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(diff_path, "w") as f:
                            f.writelines(diff_result["diff_lines"])
                        change_summary["diff_url"] = f"file://{diff_path.absolute()}"

                    current_status.text_version = current_text

                event = ChangeEvent(
                    event_type=(
                        "AMENDMENT"
                        if "amend" in current_status.status.lower()
                        else "STATUS_CHANGE"
                    ),
                    source="LEGISLATIVE",
                    id=bill_data["bill_id"],
                    title=bill_data["title"],
                    timestamp=datetime.now().isoformat(),
                    change_summary=change_summary,
                    url=self.BILL_DETAIL_URL.format(
                        session_id=bill_data["session_id"], bill_id=bill_data["bill_id"]
                    ),
                )
                events.append(event)

            # Update state
            self.previous_state[bill_key] = current_status

        # Save updated state
        self._save_state()
        logger.info(f"Legislative tracking complete. {len(events)} changes detected.")

        return events


# ============================================================================
# PIPELINE B: EXECUTIVE TRACKER (Canada Gazette)
# ============================================================================


class ExecutiveTracker:
    """Tracks policies from Canada Gazette RSS feeds"""

    PROPOSALS_RSS = "https://gazette.gc.ca/rss/p1-eng.xml"
    ENACTED_RSS = "https://gazette.gc.ca/rss/p2-eng.xml"

    def __init__(self, storage_path: str = "./data/policies_state.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.previous_entries: Dict[str, Dict] = self._load_state()

    def _load_state(self) -> Dict[str, Dict]:
        """Load previous policy entries from disk"""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading state: {e}")
                return {}
        return {}

    def _save_state(self):
        """Save current policy entries to disk"""
        try:
            with open(self.storage_path, "w") as f:
                json.dump(self.previous_entries, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving state: {e}")

    def parse_rss_feed(self, url: str) -> List[Dict]:
        """Parse RSS feed and extract entries"""
        try:
            feed = feedparser.parse(url)
            entries = []

            for entry in feed.entries:
                entry_data = {
                    "id": entry.get("id", entry.get("link", "")),
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "summary": entry.get("summary", ""),
                    "feed_type": "proposal" if "p1" in url else "enacted",
                }
                entries.append(entry_data)

            logger.info(f"Parsed {len(entries)} entries from {url}")
            return entries

        except Exception as e:
            logger.error(f"Error parsing RSS feed {url}: {e}")
            return []

    def classify_policy_type(self, title: str) -> str:
        """Determine if policy is new or amended based on title"""
        title_lower = title.lower()

        if "regulations amending" in title_lower or "amendment" in title_lower:
            return "AMENDMENT"
        elif "regulations respecting" in title_lower or "new regulation" in title_lower:
            return "NEW"
        else:
            return "UNKNOWN"

    def detect_changes(self) -> List[ChangeEvent]:
        """Main polling function: detect changes in policies"""
        logger.info("Starting executive change detection...")
        events = []

        # Check both RSS feeds
        for feed_url in [self.PROPOSALS_RSS, self.ENACTED_RSS]:
            entries = self.parse_rss_feed(feed_url)
            feed_type = "proposal" if "p1" in feed_url else "enacted"

            for entry in entries:
                entry_id = entry["id"]

                # Check if this is a new entry
                if entry_id not in self.previous_entries:
                    logger.info(f"New policy detected: {entry['title'][:50]}...")

                    policy_type = self.classify_policy_type(entry["title"])

                    event = ChangeEvent(
                        event_type=policy_type,
                        source="EXECUTIVE",
                        id=entry_id,
                        title=entry["title"],
                        timestamp=datetime.now().isoformat(),
                        change_summary={
                            "feed_type": feed_type,
                            "published_date": entry["published"],
                            "summary": (
                                entry["summary"][:200] + "..."
                                if len(entry["summary"]) > 200
                                else entry["summary"]
                            ),
                        },
                        url=entry["link"],
                    )
                    events.append(event)

                    # Store this entry
                    self.previous_entries[entry_id] = entry

        # Save updated state
        self._save_state()
        logger.info(f"Executive tracking complete. {len(events)} changes detected.")

        return events


# ============================================================================
# UNIFIED SYSTEM CONTROLLER
# ============================================================================


class PolicyTrackerSystem:
    """Main system that coordinates both pipelines"""

    def __init__(self):
        self.legislative_tracker = LegislativeTracker()
        self.executive_tracker = ExecutiveTracker()
        self.events_log_path = Path("./data/events_log.jsonl")
        self.events_log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_event(self, event: ChangeEvent):
        """Append event to log file"""
        try:
            with open(self.events_log_path, "a") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
        except Exception as e:
            logger.error(f"Error logging event: {e}")

    def poll_legislative(self):
        """Poll legislative pipeline (every 4 hours)"""
        logger.info("=" * 60)
        logger.info("POLLING LEGISLATIVE PIPELINE")
        logger.info("=" * 60)

        events = self.legislative_tracker.detect_changes()

        for event in events:
            self.log_event(event)
            self.process_event(event)

        return events

    def poll_executive(self):
        """Poll executive pipeline (daily)"""
        logger.info("=" * 60)
        logger.info("POLLING EXECUTIVE PIPELINE")
        logger.info("=" * 60)

        events = self.executive_tracker.detect_changes()

        for event in events:
            self.log_event(event)
            self.process_event(event)

        return events

    def process_event(self, event: ChangeEvent):
        """Process a change event (customize based on your needs)"""
        logger.info(f"\n{'='*60}")
        logger.info(f"EVENT DETECTED")
        logger.info(f"{'='*60}")
        logger.info(f"Type: {event.event_type}")
        logger.info(f"Source: {event.source}")
        logger.info(f"ID: {event.id}")
        logger.info(f"Title: {event.title}")
        logger.info(f"Timestamp: {event.timestamp}")
        logger.info(f"Summary: {json.dumps(event.change_summary, indent=2)}")
        if event.url:
            logger.info(f"URL: {event.url}")
        logger.info(f"{'='*60}\n")

    def setup_scheduler(self):
        """Setup polling schedule"""
        # Legislative: Every 4 hours
        schedule.every(4).hours.do(self.poll_legislative)

        # Executive: Daily at 10:00 AM
        schedule.every().day.at("10:00").do(self.poll_executive)

        logger.info("Scheduler configured:")
        logger.info("  - Legislative polling: Every 4 hours")
        logger.info("  - Executive polling: Daily at 10:00 AM")

    def run_once(self):
        """Run both pipelines once (for testing)"""
        logger.info("\n" + "=" * 60)
        logger.info("RUNNING SINGLE POLL CYCLE")
        logger.info("=" * 60 + "\n")

        legislative_events = self.poll_legislative()
        executive_events = self.poll_executive()

        total_events = len(legislative_events) + len(executive_events)
        logger.info(f"\nTotal events detected: {total_events}")
        logger.info(f"  - Legislative: {len(legislative_events)}")
        logger.info(f"  - Executive: {len(executive_events)}")

        return legislative_events + executive_events

    def run_forever(self):
        """Run the system continuously with scheduled polling"""
        logger.info("Starting Policy Tracker System...")
        self.setup_scheduler()

        # Run initial poll
        logger.info("Running initial poll...")
        self.run_once()

        # Start scheduled polling
        logger.info("\nEntering scheduled polling mode...")
        logger.info("Press Ctrl+C to stop.\n")

        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            logger.info("\nShutting down Policy Tracker System...")


# ============================================================================
# MAIN EXECUTION
# ============================================================================


def main():
    """Main entry point"""
    import sys

    tracker = PolicyTrackerSystem()

    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        # Run once for testing
        tracker.run_once()
    else:
        # Run continuously with scheduler
        tracker.run_forever()


if __name__ == "__main__":
    main()
