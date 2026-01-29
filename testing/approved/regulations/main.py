"""
Main orchestrator script for Canada Gazette scraping.
Runs on a 4-hour interval, dynamically discovers latest issue URLs,
scrapes data, and manages file storage with state tracking.
"""

import os
import json
import time
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import traceback

# Import the parsing functions from the scraper modules
from part1 import parse_p1_publication, parse_section
from part2 import parse_p2_publication
from part3 import parse_part3_table


# Configuration
SLEEP_INTERVAL = 4 * 60 * 60  # 4 hours in seconds
ASSETS_DIR = "assets"
VALID_TYPES = [
    "Commissions",
    "Government Notices",
    "Miscellaneous Notices",
    "Parliament",
]
PUBLICATION_ITEM_IDENTIFIER_PREFIX = ["cs", "ne", "ml", "pe"]
PARSABLE_SECTIONS = [
    "Commissions",
    "Government Notices",
    "Miscellaneous Notices",
    "Parliament",
]


def ensure_assets_directory():
    """Create the assets directory if it doesn't exist."""
    if not os.path.exists(ASSETS_DIR):
        os.makedirs(ASSETS_DIR)
        print(f"Created directory: {ASSETS_DIR}")


def get_latest_issue_url(year: int, part: int) -> str:
    """
    Discover the latest issue URL for a given part by scraping the yearly index page.

    Args:
        year: The year to check
        part: The part number (1, 2, or 3)

    Returns:
        The URL of the most recent issue, or None if not found
    """
    index_url = f"https://gazette.gc.ca/rp-pr/p{part}/{year}/index-eng.html"

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36"
        }
        response = requests.get(index_url, headers=headers, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        if part == 3:
            # Part 3 uses the index URL directly
            return index_url

        # For Parts 1 and 2, find the most recent issue link
        # Look for links that contain the pattern YYYY-MM-DD
        issue_links = []
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            # Check if href contains date pattern YYYY-MM-DD or similar
            if f"{year}" in href and ("html" in href or "index" in href):
                full_url = urljoin(index_url, href)
                issue_links.append(full_url)

        if issue_links:
            # Return the first link (usually the most recent)
            # You could enhance this to actually parse dates and find the latest
            return issue_links[0]

        print(f"Warning: No issue links found for Part {part} in {year}")
        return None

    except Exception as e:
        print(f"Error fetching index for Part {part}: {e}")
        traceback.print_exc()
        return None


def extract_publication_date_from_url(url: str) -> str:
    """
    Extract the publication date from a Gazette URL or webpage.

    Args:
        url: The URL to extract the date from

    Returns:
        The publication date as a string (e.g., "2026-01-24")
    """
    # Try to extract from URL pattern first (e.g., /2026/2026-01-24/)
    import re

    date_match = re.search(r"/(\d{4}-\d{2}-\d{2})/", url)
    if date_match:
        return date_match.group(1)

    # Otherwise try to fetch and parse the page
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=30)
        soup = BeautifulSoup(response.content, "html.parser")

        # Look for h1 with id="wb-cont" and get the next <p> tag
        wb_cont = soup.find("h1", id="wb-cont")
        if wb_cont:
            date_p = wb_cont.find_next("p")
            if date_p:
                return date_p.get_text(strip=True)

        return "Unknown"
    except Exception as e:
        print(f"Error extracting date from {url}: {e}")
        return "Unknown"


def scrape_part1(url: str) -> dict:
    """
    Scrape Part 1 data from the given URL.

    Args:
        url: The Part 1 index URL to scrape

    Returns:
        Dictionary containing all Part 1 data
    """
    print(f"Scraping Part 1 from: {url}")

    # Parse the P1 publication to get section URLs
    parsed_sections = parse_p1_publication(url)

    # Parse each section
    part1_data = {}
    for url_key, section_name, identifier_prefix in zip(
        parsed_sections.keys(), VALID_TYPES, PUBLICATION_ITEM_IDENTIFIER_PREFIX
    ):
        if url_key in PARSABLE_SECTIONS and url_key in parsed_sections:
            section_url = parsed_sections[url_key]
            part1_data[section_name] = parse_section(
                section_url, section_name, identifier_prefix
            )

    # Add Proposed Regulations if present
    if "Proposed Regulations" in parsed_sections:
        part1_data["Proposed Regulations"] = parsed_sections["Proposed Regulations"]

    return part1_data


def scrape_part2(url: str) -> dict:
    """
    Scrape Part 2 data from the given URL.

    Args:
        url: The Part 2 index URL to scrape

    Returns:
        Dictionary containing all Part 2 data
    """
    print(f"Scraping Part 2 from: {url}")
    return parse_p2_publication(url)


def scrape_part3(url: str) -> list:
    """
    Scrape Part 3 data from the given URL.

    Args:
        url: The Part 3 index URL to scrape

    Returns:
        List containing all Part 3 data
    """
    print(f"Scraping Part 3 from: {url}")
    return parse_part3_table(url)


def count_entries(data, part_num: int) -> int:
    """
    Count the number of entries in the scraped data.

    Args:
        data: The data structure (dict or list)
        part_num: The part number (1, 2, or 3)

    Returns:
        Total count of entries
    """
    try:
        if part_num == 1:
            # Part 1 is nested dict structure
            total = 0
            for section_name, section_data in data.items():
                if isinstance(section_data, dict):
                    total += len(section_data)
                elif isinstance(section_data, list):
                    total += len(section_data)
            return total
        elif part_num == 2:
            # Part 2 has SOR and SI keys
            return len(data.get("SOR", [])) + len(data.get("SI", []))
        elif part_num == 3:
            # Part 3 is a list
            return len(data) if isinstance(data, list) else 0
    except Exception as e:
        print(f"Error counting entries for Part {part_num}: {e}")
        return 0


def save_data(part_num: int, data):
    """
    Save scraped data to JSON file in the assets directory.

    Args:
        part_num: The part number (1, 2, or 3)
        data: The data to save
    """
    filename = os.path.join(ASSETS_DIR, f"part{part_num}_data.json")
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Saved Part {part_num} data to {filename}")
    except Exception as e:
        print(f"Error saving Part {part_num} data: {e}")
        traceback.print_exc()


def update_status_file(publication_date: str, entry_counts: dict):
    """
    Update the db_status.json file with metadata about the last run.

    Args:
        publication_date: The publication date of the latest scraped issue
        entry_counts: Dictionary containing entry counts for each part
    """
    status_file = os.path.join(ASSETS_DIR, "db_status.json")

    status_data = {
        "time_of_last_check": datetime.utcnow().isoformat() + "Z",
        "latest_data_date": publication_date,
        "entry_counts": entry_counts,
    }

    try:
        with open(status_file, "w", encoding="utf-8") as f:
            json.dump(status_data, f, ensure_ascii=False, indent=2)
        print(f"Updated status file: {status_file}")
    except Exception as e:
        print(f"Error updating status file: {e}")
        traceback.print_exc()


def run_scraping_cycle():
    """
    Execute one complete scraping cycle:
    1. Discover latest URLs
    2. Scrape all three parts
    3. Save data
    4. Update status file
    """
    print("\n" + "=" * 60)
    print(f"Starting scraping cycle at {datetime.now().isoformat()}")
    print("=" * 60)

    current_year = datetime.now().year

    # Initialize tracking variables
    part1_data = None
    part2_data = None
    part3_data = None
    latest_date = "Unknown"

    # Discover and scrape Part 1
    try:
        part1_url = get_latest_issue_url(current_year, 1)
        if part1_url:
            latest_date = extract_publication_date_from_url(part1_url)
            part1_data = scrape_part1(part1_url)
            save_data(1, part1_data)
        else:
            print("Warning: Could not find Part 1 URL")
    except Exception as e:
        print(f"Error processing Part 1: {e}")
        traceback.print_exc()

    # Discover and scrape Part 2
    try:
        part2_url = get_latest_issue_url(current_year, 2)
        if part2_url:
            part2_data = scrape_part2(part2_url)
            save_data(2, part2_data)
        else:
            print("Warning: Could not find Part 2 URL")
    except Exception as e:
        print(f"Error processing Part 2: {e}")
        traceback.print_exc()

    # Discover and scrape Part 3
    try:
        part3_url = get_latest_issue_url(current_year, 3)
        if part3_url:
            part3_data = scrape_part3(part3_url)
            save_data(3, part3_data)
        else:
            print("Warning: Could not find Part 3 URL")
    except Exception as e:
        print(f"Error processing Part 3: {e}")
        traceback.print_exc()

    # Count entries and update status
    entry_counts = {
        "part1": count_entries(part1_data, 1) if part1_data else 0,
        "part2": count_entries(part2_data, 2) if part2_data else 0,
        "part3": count_entries(part3_data, 3) if part3_data else 0,
    }

    update_status_file(latest_date, entry_counts)

    print("\n" + "=" * 60)
    print(f"Scraping cycle completed at {datetime.now().isoformat()}")
    print(f"Publication date: {latest_date}")
    print(
        f"Entry counts: Part1={entry_counts['part1']}, Part2={entry_counts['part2']}, Part3={entry_counts['part3']}"
    )
    print("=" * 60)


def main():
    """
    Main loop: Run scraping cycles continuously with 4-hour intervals.
    """
    print("Canada Gazette Scraper - Starting")
    print(f"Sleep interval: {SLEEP_INTERVAL / 3600} hours")

    # Ensure assets directory exists
    ensure_assets_directory()

    # Run forever
    while True:
        try:
            run_scraping_cycle()
        except Exception as e:
            print(f"Unexpected error in scraping cycle: {e}")
            traceback.print_exc()

        print(f"\nSleeping for {SLEEP_INTERVAL / 3600} hours...")
        print(
            f"Next run at: {datetime.fromtimestamp(time.time() + SLEEP_INTERVAL).isoformat()}\n"
        )

        time.sleep(SLEEP_INTERVAL)


if __name__ == "__main__":
    main()
