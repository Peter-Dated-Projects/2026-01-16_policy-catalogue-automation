"""
Canada Gazette Web Scraper
Extracts structured data from Canada Gazette Part I and Part II index pages.

Usage:
    python main.py
"""

import requests
from bs4 import BeautifulSoup, NavigableString
import json
import re
from typing import List, Dict, Optional
from urllib.parse import urljoin
from datetime import datetime
from pathlib import Path


class GazettePublication:
    """
    Represents a single Canada Gazette publication with metadata and content.

    Attributes:
        url: The URL of the publication
        date: Publication date (YYYY-MM-DD)
        part: Part I or Part II
        volume: Volume number
        number: Publication number within the volume
        extra: Extra identifier (e.g., "extra1", "x1")
        title: Publication title
        items: List of extracted items from the publication
    """

    def __init__(self, url: str):
        """
        Initialize and parse a Canada Gazette publication.

        Args:
            url: URL of the Gazette index page
        """
        self.url = url
        self.date = None
        self.part = None
        self.volume = None
        self.number = None
        self.extra = None
        self.title = None
        self.items: List[Dict] = []

        # Parse the publication
        self._parse()

    def _extract_metadata_from_url(self) -> None:
        """
        Extract date, part, volume, and extra info from the URL.

        Example URLs:
        - https://gazette.gc.ca/rp-pr/p1/2026/2026-01-24/html/index-eng.html
        - https://gazette.gc.ca/rp-pr/p2/2025/2025-12-18/html/index-eng.html
        - https://gazette.gc.ca/rp-pr/p1/2026/2026-01-19-x1/html/extra1-eng.html
        """
        # Extract part (p1 or p2)
        part_match = re.search(r"/p(\d+)/", self.url)
        if part_match:
            self.part = int(part_match.group(1))

        # Extract date (YYYY-MM-DD)
        date_match = re.search(r"/(\d{4})/(\d{4}-\d{2}-\d{2})", self.url)
        if date_match:
            self.date = date_match.group(2)

        # Extract extra identifiers (e.g., x1, x2)
        extra_match = re.search(r"/(\d{4}-\d{2}-\d{2}-x\d+)/", self.url)
        if extra_match:
            self.extra = extra_match.group(1).split("-")[-1]  # Gets "x1"
            self.date = "-".join(
                extra_match.group(1).split("-")[:3]
            )  # Gets "YYYY-MM-DD"

    def _extract_metadata_from_page(self, soup: BeautifulSoup) -> None:
        """
        Extract metadata from the page content itself.

        Args:
            soup: BeautifulSoup object of the page
        """
        # Extract title
        title_tag = soup.find("title")
        if title_tag:
            self.title = title_tag.text.strip()

        # Try to find volume and number in the page
        # Look for patterns like "Vol. 160, Number 4" or "Volume 160, No. 3"
        volume_pattern = re.compile(r"Vol(?:ume)?\.?\s*(\d+)", re.IGNORECASE)
        number_pattern = re.compile(r"(?:Number|No\.|N°)\s*(\d+)", re.IGNORECASE)

        # Check in title
        if self.title:
            vol_match = volume_pattern.search(self.title)
            if vol_match:
                self.volume = int(vol_match.group(1))
            num_match = number_pattern.search(self.title)
            if num_match:
                self.number = int(num_match.group(1))

        # Check in h1 or other headings
        if not self.volume or not self.number:
            for heading in soup.find_all(
                ["h1", "h2", "div"], class_=re.compile("header|title", re.IGNORECASE)
            ):
                text = heading.get_text()
                if not self.volume:
                    vol_match = volume_pattern.search(text)
                    if vol_match:
                        self.volume = int(vol_match.group(1))
                if not self.number:
                    num_match = number_pattern.search(text)
                    if num_match:
                        self.number = int(num_match.group(1))
                if self.volume and self.number:
                    break

        # Check meta tags
        if not self.volume or not self.number:
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                if not self.volume:
                    vol_match = volume_pattern.search(meta_desc["content"])
                    if vol_match:
                        self.volume = int(vol_match.group(1))
                if not self.number:
                    num_match = number_pattern.search(meta_desc["content"])
                    if num_match:
                        self.number = int(num_match.group(1))

    def _detect_part(self, soup: BeautifulSoup) -> str:
        """
        Detect whether this is a Part I or Part II Gazette page.

        Args:
            soup: BeautifulSoup object of the page

        Returns:
            "Part I" or "Part II"
        """
        # Check the title or heading for part information
        title = soup.find("title")
        if title and "part ii" in title.text.lower():
            return "Part II"

        # Check for h1 or other prominent headings
        h1 = soup.find("h1")
        if h1 and "part ii" in h1.text.lower():
            return "Part II"

        # Check for table structure (Part II typically has tables)
        tables = soup.find_all("table")
        if tables:
            # Check if tables contain SOR/SI registration patterns
            for table in tables:
                if table.find(string=re.compile(r"SOR/|SI/")):
                    return "Part II"

        # Default to Part I (notices and proposed regulations)
        return "Part I"

    def _parse(self) -> None:
        """
        Main parsing method. Fetches and parses the publication.
        """
        try:
            # Make HTTP request
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            response = requests.get(self.url, headers=headers, timeout=30)
            response.raise_for_status()

            # Parse HTML
            soup = BeautifulSoup(response.content, "html.parser")

            # Extract metadata from URL and page
            self._extract_metadata_from_url()
            self._extract_metadata_from_page(soup)

            # Detect part and extract items
            part_str = self._detect_part(soup)

            if part_str == "Part I":
                self.items = self._extract_part_i(soup)
            else:
                self.items = self._extract_part_ii(soup)

        except requests.exceptions.RequestException as e:
            print(f"Error fetching URL: {e}")
        except Exception as e:
            print(f"Error processing page: {e}")
            raise

    def _extract_part_i(self, soup: BeautifulSoup) -> List[Dict]:
        """
        Extract data from Part I Gazette (Notices & Proposed Regulations).

        Args:
            soup: BeautifulSoup object

        Returns:
            List of dictionaries with structured data
        """
        results = []

        # Find the main content area
        main_content = (
            soup.find("main") or soup.find("div", class_="main-content") or soup
        )

        # Current context tracking
        current_category = None
        current_organization = None
        current_enabling_act = None

        # Iterate through all elements to maintain hierarchy
        for element in main_content.descendants:
            if isinstance(element, NavigableString):
                continue

            # Stop at footer or footnotes
            if element.name in ["h2", "h3"]:
                text = element.get_text(strip=True).lower()
                if any(
                    stop in text
                    for stop in ["footnote", "about government", "about the gazette"]
                ):
                    break

            # Category level (h2 or h3)
            if element.name in ["h2", "h3"]:
                current_category = element.get_text(strip=True)
                current_organization = None
                current_enabling_act = None

            # Organization/Department level (h4)
            elif element.name == "h4":
                current_organization = element.get_text(strip=True)
                current_enabling_act = None

            # Enabling Act level (h5)
            elif element.name == "h5":
                current_enabling_act = element.get_text(strip=True)

            # Items with links
            elif element.name == "a" and element.get("href"):
                href = element.get("href")
                # Skip navigation links and anchors
                if href.startswith("#") or "index-eng" in href or "index-fra" in href:
                    continue

                title = element.get_text(strip=True)
                if not title:
                    continue

                # Resolve relative URLs
                full_url = urljoin(self.url, href)

                # Create entry
                entry = {
                    "part": "Part I",
                    "category": current_category,
                    "organization": current_organization,
                    "enabling_act": current_enabling_act,
                    "title": title,
                    "registration_id": None,
                    "url": full_url,
                }
                results.append(entry)

        return results

    def _extract_part_ii(self, soup: BeautifulSoup) -> List[Dict]:
        """
        Extract data from Part II Gazette (Official Regulations).

        Args:
            soup: BeautifulSoup object

        Returns:
            List of dictionaries with structured data
        """
        results = []

        # Find tables containing regulations
        tables = soup.find_all("table")

        for table in tables:
            rows = table.find_all("tr")

            # Try to identify header row
            headers = []
            header_row = table.find("thead")
            if header_row:
                headers = [
                    th.get_text(strip=True).lower()
                    for th in header_row.find_all(["th", "td"])
                ]
            elif rows:
                # First row might be headers
                potential_headers = [
                    th.get_text(strip=True).lower()
                    for th in rows[0].find_all(["th", "td"])
                ]
                if any(
                    h in " ".join(potential_headers)
                    for h in ["title", "act", "registration"]
                ):
                    headers = potential_headers
                    rows = rows[1:]

            # Process data rows
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) < 2:
                    continue

                # Extract data
                title = None
                enabling_act = None
                registration_id = None
                item_url = None

                for cell in cells:
                    cell_text = cell.get_text(strip=True)

                    # Look for registration ID
                    reg_match = re.search(r"(SOR|SI)/\d{4}-\d+", cell_text)
                    if reg_match:
                        registration_id = reg_match.group(0)

                    # Look for links
                    link = cell.find("a")
                    if link and link.get("href"):
                        title = link.get_text(strip=True)
                        item_url = urljoin(self.url, link.get("href"))

                    # Heuristic: longer text without SOR/SI is likely the act name
                    if len(cell_text) > 10 and not reg_match and not link:
                        if (
                            "act" in cell_text.lower()
                            or "regulations" in cell_text.lower()
                        ):
                            enabling_act = cell_text

                # Only add if we have at least a title
                if title:
                    entry = {
                        "part": "Part II",
                        "category": "Official Regulations",
                        "organization": None,
                        "enabling_act": enabling_act,
                        "title": title,
                        "registration_id": registration_id,
                        "url": item_url,
                    }
                    results.append(entry)

        return results

    def get_filename(self) -> str:
        """
        Generate standardized filename for this publication.

        Format: yyyy-mm-dd_part-[number]_volume-[number]_number-[number]_[extra].json
        Example: 2026-01-24_part-1_volume-160_number-4.json
        Example: 2026-01-19_part-1_volume-160_number-3_x1.json

        Returns:
            Standardized filename string
        """
        parts = []

        # Date (required)
        if self.date:
            parts.append(self.date)
        else:
            parts.append("unknown-date")

        # Part number
        if self.part:
            parts.append(f"part-{self.part}")

        # Volume number
        if self.volume:
            parts.append(f"volume-{self.volume}")

        # Publication number
        if self.number:
            parts.append(f"number-{self.number}")

        # Extra identifier
        if self.extra:
            parts.append(self.extra)

        return "_".join(parts) + ".json"

    def to_dict(self) -> Dict:
        """
        Convert publication data to dictionary format.

        Returns:
            Dictionary with metadata and items
        """
        return {
            "metadata": {
                "url": self.url,
                "date": self.date,
                "part": self.part,
                "volume": self.volume,
                "number": self.number,
                "extra": self.extra,
                "title": self.title,
                "total_items": len(self.items),
            },
            "items": self.items,
        }

    def save_to_file(self, output_dir: str = ".") -> str:
        """
        Save publication data to a JSON file with standardized naming.

        Args:
            output_dir: Directory to save the file in

        Returns:
            Path to the saved file
        """
        # Ensure output directory exists
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Generate filename and full path
        filename = self.get_filename()
        filepath = output_path / filename

        # Save to file
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

        return str(filepath)

    def __repr__(self) -> str:
        """String representation of the publication."""
        return f"GazettePublication(date={self.date}, part={self.part}, volume={self.volume}, number={self.number}, items={len(self.items)})"


# Main execution
if __name__ == "__main__":
    # Sample URLs for testing
    urls = [
        "https://gazette.gc.ca/rp-pr/p1/2026/2026-01-24/html/index-eng.html",
        "https://gazette.gc.ca/rp-pr/p1/2026/2026-01-17/html/index-eng.html",
        # Add more URLs as needed
        # "https://gazette.gc.ca/rp-pr/p2/2026/2026-01-22/html/index-eng.html",
        # "https://gazette.gc.ca/rp-pr/p1/2026/2026-01-19-x1/html/extra1-eng.html",
    ]

    # Process each publication
    for url in urls:
        print(f"\n{'='*80}")
        print(f"Processing: {url}")
        print("=" * 80)

        # Create publication object (automatically parses)
        publication = GazettePublication(url)

        # Display metadata
        print(f"\n{publication}")
        print(f"Date: {publication.date}")
        print(f"Part: {publication.part}")
        print(f"Volume: {publication.volume}")
        print(f"Number: {publication.number}")
        print(f"Extra: {publication.extra}")
        print(f"Title: {publication.title}")
        print(f"Items found: {len(publication.items)}")

        # Save to file
        filepath = publication.save_to_file(output_dir="output")
        print(f"\nSaved to: {filepath}")

        # Optionally print first few items
        print("\nSample items:")
        for item in publication.items[:3]:
            print(f"  - {item['title'][:60]}...")
