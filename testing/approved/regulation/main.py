"""
Canadian Federal Regulation Lifecycle Tracker
Monitors Canada Gazette RSS feeds for proposed and enacted regulations.
"""

import feedparser
import re
import json
import logging
import time
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict
import schedule


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class Stage(Enum):
    """Regulation lifecycle stages"""

    PROPOSED = "PROPOSED"  # Part I - Consultation phase
    ENACTED = "ENACTED"  # Part II - Official law


@dataclass
class Regulation:
    """
    Normalized representation of a Canadian Federal Regulation
    """

    regulation_name: str  # Clean human-readable title
    regulation_id: Optional[str]  # SOR/YYYY-NNN or SI/YYYY-NNN
    date_published: str  # ISO 8601 format
    stage: str  # PROPOSED or ENACTED
    sponsor: Optional[str]  # Department/entity requesting it
    enabling_act: Optional[str]  # Parent Act (if extractable)
    links: str  # URL to full text
    raw_title: str  # Original full title for reference

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict) -> "Regulation":
        """Create Regulation from dictionary"""
        return Regulation(**data)


class RegulationTracker:
    """
    Main tracker for Canadian Federal Regulations
    """

    PART_I_URL = "https://gazette.gc.ca/rss/p1-eng.xml"  # Proposed regulations
    PART_II_URL = "https://gazette.gc.ca/rss/p2-eng.xml"  # Enacted regulations

    def __init__(self, data_file: str = "assets/data.json"):
        self.data_file = Path(data_file)
        self.regulations: List[Regulation] = []
        self._ensure_assets_directory()
        self._load_existing_data()

    def _ensure_assets_directory(self):
        """Create assets directory if it doesn't exist"""
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Data directory ensured: {self.data_file.parent}")

    def _load_existing_data(self):
        """Load existing regulations from JSON file"""
        if self.data_file.exists():
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.regulations = [Regulation.from_dict(item) for item in data]
                logger.info(
                    f"Loaded {len(self.regulations)} existing regulations from {self.data_file}"
                )
            except Exception as e:
                logger.error(f"Error loading existing data: {e}")
                self.regulations = []
        else:
            logger.info("No existing data file found. Starting fresh.")
            self.regulations = []

    def _save_data(self):
        """Save regulations to JSON file"""
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(
                    [reg.to_dict() for reg in self.regulations],
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
            logger.info(
                f"Saved {len(self.regulations)} regulations to {self.data_file}"
            )
        except Exception as e:
            logger.error(f"Error saving data: {e}")

    def _extract_regulation_id(self, text: str) -> Optional[str]:
        """
        Extract regulation ID (SOR/YYYY-NNN or SI/YYYY-NNN) from text
        """
        # Pattern for SOR (Statutory Orders and Regulations) or SI (Statutory Instruments)
        pattern = r"\b(SOR|SI)/\d{4}-\d+\b"
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(0).upper() if match else None

    def _extract_sponsor(self, entry) -> Optional[str]:
        """
        Extract sponsor (department/entity) from RSS entry
        Checks author field and description
        """
        # Check author field first
        if hasattr(entry, "author") and entry.author:
            return entry.author.strip()

        # Try to extract from summary/description
        if hasattr(entry, "summary") and entry.summary:
            # Common patterns: "Department of ...", "Minister of ...", etc.
            dept_pattern = (
                r"(Department of [^,.\n]+|Minister of [^,.\n]+|[A-Z][a-z]+ Canada)"
            )
            match = re.search(dept_pattern, entry.summary)
            if match:
                return match.group(1).strip()

        return None

    def _extract_enabling_act(self, text: str) -> Optional[str]:
        """
        Extract the enabling Act from text
        Looks for patterns like "under the [Act Name] Act"
        """
        # Common patterns for enabling acts
        patterns = [
            r"(?:under|pursuant to) (?:the )?([^,.\n]+Act)",
            r"(?:made under|established under) (?:the )?([^,.\n]+Act)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def _clean_regulation_name(self, title: str) -> str:
        """
        Clean regulation title by removing bureaucratic prefixes
        """
        # Remove common prefixes
        prefixes_to_remove = [
            r"^Regulations?\s+[Aa]mending\s+the\s+",
            r"^Order\s+[Aa]mending\s+the\s+",
            r"^Regulations?\s+",
            r"^Order\s+",
        ]

        cleaned = title
        for prefix in prefixes_to_remove:
            cleaned = re.sub(prefix, "", cleaned, flags=re.IGNORECASE)

        return cleaned.strip()

    def _parse_date(self, date_str: str) -> str:
        """
        Parse date from RSS feed and convert to ISO 8601 format
        """
        try:
            # feedparser provides structured time
            parsed = feedparser.parse(f"<entry><updated>{date_str}</updated></entry>")
            if parsed.entries and hasattr(parsed.entries[0], "updated_parsed"):
                dt = datetime(*parsed.entries[0].updated_parsed[:6])
                return dt.isoformat()

            # Fallback: try common date formats
            for fmt in ["%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"]:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.isoformat()
                except ValueError:
                    continue

            # If all else fails, return current timestamp
            logger.warning(f"Could not parse date: {date_str}. Using current time.")
            return datetime.now().isoformat()
        except Exception as e:
            logger.error(f"Error parsing date {date_str}: {e}")
            return datetime.now().isoformat()

    def _regulation_exists(self, reg_id: Optional[str], title: str, date: str) -> bool:
        """
        Check if a regulation already exists in our data
        Uses ID if available, otherwise title+date
        """
        for existing in self.regulations:
            # If both have IDs, compare by ID
            if reg_id and existing.regulation_id and reg_id == existing.regulation_id:
                return True

            # Otherwise, compare by title and date
            if existing.raw_title == title and existing.date_published.startswith(
                date.split("T")[0]
            ):
                return True

        return False

    def _fetch_and_parse_feed(self, url: str, stage: Stage) -> List[Regulation]:
        """
        Fetch and parse RSS feed, returning list of Regulation objects
        """
        logger.info(f"Fetching {stage.value} regulations from {url}")

        try:
            feed = feedparser.parse(url)

            if feed.bozo:
                logger.warning(f"Feed parsing warning: {feed.bozo_exception}")

            regulations = []

            for entry in feed.entries:
                try:
                    # Extract basic fields
                    raw_title = (
                        entry.title if hasattr(entry, "title") else "Unknown Title"
                    )
                    link = entry.link if hasattr(entry, "link") else ""
                    date_published = self._parse_date(
                        entry.published if hasattr(entry, "published") else ""
                    )

                    # Extract metadata
                    full_text = f"{raw_title} {entry.summary if hasattr(entry, 'summary') else ''}"
                    regulation_id = self._extract_regulation_id(full_text)
                    sponsor = self._extract_sponsor(entry)
                    enabling_act = self._extract_enabling_act(full_text)
                    regulation_name = self._clean_regulation_name(raw_title)

                    # Check if already exists
                    if self._regulation_exists(
                        regulation_id, raw_title, date_published
                    ):
                        logger.debug(f"Skipping duplicate: {regulation_name}")
                        continue

                    # Create Regulation object
                    regulation = Regulation(
                        regulation_name=regulation_name,
                        regulation_id=regulation_id,
                        date_published=date_published,
                        stage=stage.value,
                        sponsor=sponsor,
                        enabling_act=enabling_act,
                        links=link,
                        raw_title=raw_title,
                    )

                    regulations.append(regulation)
                    logger.info(
                        f"Found new regulation: {regulation_name} [{regulation_id or 'No ID'}]"
                    )

                except Exception as e:
                    logger.error(f"Error parsing entry: {e}")
                    continue

            return regulations

        except Exception as e:
            logger.error(f"Error fetching feed from {url}: {e}")
            return []

    def scan_gazette(self):
        """
        Scan both Gazette feeds for new regulations
        """
        logger.info("=" * 60)
        logger.info("Starting Gazette scan...")

        new_regulations = []

        # Fetch Part I (Proposed)
        part_i_regs = self._fetch_and_parse_feed(self.PART_I_URL, Stage.PROPOSED)
        new_regulations.extend(part_i_regs)

        # Fetch Part II (Enacted)
        part_ii_regs = self._fetch_and_parse_feed(self.PART_II_URL, Stage.ENACTED)
        new_regulations.extend(part_ii_regs)

        # Add new regulations to our list
        if new_regulations:
            self.regulations.extend(new_regulations)
            self._save_data()
            logger.info(
                f"✓ Scan complete. Found {len(new_regulations)} new regulation(s)."
            )
        else:
            logger.info("✓ Scan complete. No new regulations found.")

        logger.info(f"Total regulations tracked: {len(self.regulations)}")
        logger.info("=" * 60)

    def run_once(self):
        """Run a single scan"""
        self.scan_gazette()

    def run_scheduled(self):
        """
        Run the tracker with 24-hour polling schedule
        """
        logger.info("🚀 Starting Canadian Federal Regulation Tracker")
        logger.info(f"📁 Data file: {self.data_file.absolute()}")
        logger.info(f"⏰ Polling schedule: Every 24 hours")
        logger.info(f"📊 Currently tracking: {len(self.regulations)} regulations")
        logger.info("")

        # Run immediately on startup
        self.scan_gazette()

        # Schedule daily scans
        schedule.every(24).hours.do(self.scan_gazette)

        logger.info("⏳ Waiting for next scheduled scan...")

        # Main loop
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute for scheduled tasks
        except KeyboardInterrupt:
            logger.info("\n👋 Shutting down tracker. Goodbye!")


def main():
    """
    Main entry point
    """
    # Initialize tracker with default data file location
    tracker = RegulationTracker(data_file="assets/data.json")

    # Run with scheduled polling
    tracker.run_scheduled()

    # Alternative: Run once and exit
    # tracker.run_once()


if __name__ == "__main__":
    main()
