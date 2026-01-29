"""
Main orchestrator script for Canada Gazette scraping.
Runs on a 4-hour interval, dynamically discovers latest issue URLs,
scrapes data, and manages file storage with state tracking.
Checks all years back to 1998 and indexes data by publication date.
"""

import os
import json
import time
import requests
import threading
import concurrent.futures
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import traceback
import re

# Import the parsing functions from the scraper modules
from part1 import parse_p1_publication, parse_section
from part2 import parse_p2_publication
from part3 import parse_part3_table


# Configuration
SLEEP_INTERVAL = 4 * 60 * 60  # 4 hours in seconds
ASSETS_DIR = "assets"
START_YEAR = 1998  # Check back to this year
MAX_WORKERS = 5  # Max threads for concurrent scraping
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


def load_status():
    """
    Load the db_status.json file.

    Returns:
        Dictionary containing status info, or a new empty status structure
    """
    status_file = os.path.join(ASSETS_DIR, "db_status.json")

    if os.path.exists(status_file):
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading status file: {e}")

    # Return default structure
    return {
        "time_of_last_check": None,
        "latest_data_date": None,
        "years_checked": {
            "part1": {},  # year: "checked" or "empty"
            "part2": {},
            "part3": {},
        },
        "entry_counts": {"part1": 0, "part2": 0, "part3": 0},
    }


def save_status(status_data: dict):
    """
    Save the status data to db_status.json.

    Args:
        status_data: Dictionary containing status information
    """
    status_file = os.path.join(ASSETS_DIR, "db_status.json")

    try:
        with open(status_file, "w", encoding="utf-8") as f:
            json.dump(status_data, f, ensure_ascii=False, indent=2)
        print(f"Updated status file: {status_file}")
    except Exception as e:
        print(f"Error saving status file: {e}")
        traceback.print_exc()


def load_existing_data(part_num: int) -> dict:
    """
    Load existing data from part[n]_data.json if it exists.

    Args:
        part_num: The part number (1, 2, or 3)

    Returns:
        Dictionary containing existing data indexed by publication date
    """
    filename = os.path.join(ASSETS_DIR, f"part{part_num}_data.json")

    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading existing Part {part_num} data: {e}")

    # Return empty dict to store date-indexed data
    return {}


def check_year_exists(year: int, part: int) -> bool:
    """
    Check if a year's index page exists for the given part.

    Args:
        year: The year to check
        part: The part number (1, 2, or 3)

    Returns:
        True if the year exists, False otherwise
    """
    index_url = f"https://gazette.gc.ca/rp-pr/p{part}/{year}/index-eng.html"

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36"
        }
        response = requests.get(index_url, headers=headers, timeout=30)
        return response.status_code == 200
    except Exception:
        return False


def get_all_issue_urls(year: int, part: int) -> list:
    """
    Get all issue URLs for a given year and part by scraping the yearly index page.

    Args:
        year: The year to check
        part: The part number (1, 2, or 3)

    Returns:
        List of tuples (url, publication_date) for all issues in that year
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
            # Part 3 uses the index URL directly - just one entry per year
            return [(index_url, f"{year}")]

        # For Parts 1 and 2, find all issue links with dates
        issue_urls = []
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            # Check if href contains date pattern YYYY-MM-DD
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", href)
            if date_match and f"{year}" in href and "html" in href:
                full_url = urljoin(index_url, href)
                pub_date = date_match.group(1)
                # Avoid duplicates
                if (full_url, pub_date) not in issue_urls:
                    issue_urls.append((full_url, pub_date))

        if not issue_urls:
            print(f"Warning: No issue links found for Part {part} in {year}")

        return issue_urls

    except Exception as e:
        print(f"Error fetching index for Part {part}, Year {year}: {e}")
        traceback.print_exc()
        return []


def extract_publication_date_from_url(url: str) -> str:
    """
    Extract the publication date from a Gazette URL or webpage.

    Args:
        url: The URL to extract the date from

    Returns:
        The publication date as a string (e.g., "2026-01-24")
    """
    # Try to extract from URL pattern first (e.g., /2026/2026-01-24/)
    date_match = re.search(r"/(\d{4}-\d{2}-\d{2})/", url)
    if date_match:
        return date_match.group(1)

    # Check for year-only pattern for Part 3
    year_match = re.search(r"/p3/(\d{4})/", url)
    if year_match:
        return year_match.group(1)

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

            # Check if the URL is valid (not None or empty)
            if section_url and isinstance(section_url, str):
                try:
                    part1_data[section_name] = parse_section(
                        section_url, section_name, identifier_prefix
                    )
                except Exception as e:
                    print(f"  Warning: Failed to parse section '{section_name}': {e}")
            else:
                print(f"  Warning: No valid URL for section '{section_name}', skipping")

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


def count_all_entries(data_dict: dict, part_num: int) -> int:
    """
    Count total entries across all dates in the data structure.

    Args:
        data_dict: The full data dictionary indexed by date
        part_num: The part number (1, 2, or 3)

    Returns:
        Total count of entries
    """
    total = 0
    try:
        for date_key, data in data_dict.items():
            total += count_entries(data, part_num)
    except Exception as e:
        print(f"Error counting all entries for Part {part_num}: {e}")
    return total


def count_entries(data, part_num: int) -> int:
    """
    Count the number of entries in a single scraped data object.

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


def save_data(part_num: int, data_dict: dict):
    """
    Save scraped data to JSON file in the assets directory.
    Data is indexed by publication date.

    Args:
        part_num: The part number (1, 2, or 3)
        data_dict: Dictionary with publication dates as keys
    """
    filename = os.path.join(ASSETS_DIR, f"part{part_num}_data.json")
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data_dict, f, ensure_ascii=False, indent=2)
        print(
            f"Saved Part {part_num} data to {filename} ({len(data_dict)} publication dates)"
        )
    except Exception as e:
        print(f"Error saving Part {part_num} data: {e}")
        traceback.print_exc()


def process_year_for_part(
    year: int, part: int, status: dict, status_lock: threading.Lock = None
) -> dict:
    """
    Process a specific year for a specific part.
    Scrapes all issues from that year and returns the data indexed by publication date.

    Args:
        year: The year to process
        part: The part number (1, 2, or 3)
        status: The current status dict
        status_lock: Optional lock for thread-safe status updates

    Returns:
        Dictionary with publication dates as keys and scraped data as values
    """
    part_key = f"part{part}"

    # Helper context manager for optional locking
    class OptionalLock:
        def __init__(self, lock):
            self.lock = lock

        def __enter__(self):
            if self.lock:
                self.lock.acquire()

        def __exit__(self, exc_type, exc_val, exc_tb):
            if self.lock:
                self.lock.release()

    # Check if we've already processed this year
    with OptionalLock(status_lock):
        if str(year) in status["years_checked"][part_key]:
            year_status = status["years_checked"][part_key][str(year)]
            if year_status == "checked":
                print(f"Part {part}, Year {year}: Already checked, skipping")
                return {}
            elif year_status == "empty":
                print(f"Part {part}, Year {year}: Previously marked as empty, skipping")
                return {}

    # Check if the year exists
    if not check_year_exists(year, part):
        print(f"Part {part}, Year {year}: Does not exist, marking as empty")
        with OptionalLock(status_lock):
            status["years_checked"][part_key][str(year)] = "empty"
        return {}

    print(f"Part {part}, Year {year}: Processing...")

    # Get all issue URLs for this year
    issue_urls = get_all_issue_urls(year, part)

    if not issue_urls:
        print(f"Part {part}, Year {year}: No issues found, marking as empty")
        with OptionalLock(status_lock):
            status["years_checked"][part_key][str(year)] = "empty"
        return {}

    # Scrape each issue
    year_data = {}
    for url, pub_date in issue_urls:
        try:
            print(f"  Scraping {pub_date}: {url}")

            if part == 1:
                data = scrape_part1(url)
            elif part == 2:
                data = scrape_part2(url)
            elif part == 3:
                data = scrape_part3(url)
            else:
                continue

            # Store with publication date as key
            year_data[pub_date] = data

        except Exception as e:
            print(f"  Error scraping {url}: {e}")
            traceback.print_exc()

    # Mark year as checked
    with OptionalLock(status_lock):
        if year_data:
            status["years_checked"][part_key][str(year)] = "checked"
            print(
                f"Part {part}, Year {year}: Successfully scraped {len(year_data)} issues"
            )
        else:
            status["years_checked"][part_key][str(year)] = "empty"
            status["years_checked"][part_key][str(year)] = "empty"
        print(f"Part {part}, Year {year}: No data found, marking as empty")

    return year_data


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
    1. Load existing status and data
    2. Check all years from START_YEAR to current year
    3. Scrape unchecked years for all three parts
    4. Merge new data with existing data
    5. Save updated data and status
    """
    print("\n" + "=" * 60)
    print(f"Starting scraping cycle at {datetime.now().isoformat()}")
    print("=" * 60)

    current_year = datetime.now().year

    # Load existing status and data
    status = load_status()
    status_lock = threading.Lock()

    # Process each part
    for part in [1, 2, 3]:
        print(f"\n{'=' * 60}")
        print(f"Processing Part {part}")
        print(f"{'=' * 60}")

        # Load existing data for this part
        existing_data = load_existing_data(part)
        print(f"Loaded {len(existing_data)} existing publication dates for Part {part}")

        # Process each year from START_YEAR to current_year using ThreadPoolExecutor
        future_to_year = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for year in range(START_YEAR, current_year + 1):
                future = executor.submit(
                    process_year_for_part, year, part, status, status_lock
                )
                future_to_year[future] = year

            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_year):
                year = future_to_year[future]
                try:
                    year_data = future.result()

                    # Merge new data into existing data (thread-safe in main thread)
                    if year_data:
                        existing_data.update(year_data)

                except Exception as e:
                    print(f"Error processing Part {part}, Year {year}: {e}")
                    traceback.print_exc()

        # Save updated data for this part
        save_data(part, existing_data)

        # Update total entry count
        total_entries = count_all_entries(existing_data, part)
        status["entry_counts"][f"part{part}"] = total_entries
        print(f"Part {part}: Total entries = {total_entries}")

    # Update status metadata
    status["time_of_last_check"] = datetime.utcnow().isoformat() + "Z"

    # Find the most recent publication date across all parts
    latest_date = "Unknown"
    for part in [1, 2, 3]:
        data = load_existing_data(part)
        if data:
            # Get the most recent date key
            dates = sorted(data.keys(), reverse=True)
            if dates:
                latest_date = dates[0]
                break

    status["latest_data_date"] = latest_date

    # Save status
    save_status(status)

    print("\n" + "=" * 60)
    print(f"Scraping cycle completed at {datetime.now().isoformat()}")
    print(f"Latest publication date: {latest_date}")
    print(
        f"Entry counts: Part1={status['entry_counts']['part1']}, "
        f"Part2={status['entry_counts']['part2']}, "
        f"Part3={status['entry_counts']['part3']}"
    )
    print("=" * 60)


def main():
    """
    Main loop: Run scraping cycles continuously with 4-hour intervals.
    Each cycle checks all years from 1998 to present for all 3 parts,
    but skips years that have already been checked.
    """
    print("Canada Gazette Scraper - Starting")
    print(f"Sleep interval: {SLEEP_INTERVAL / 3600} hours")
    print(f"Checking years from {START_YEAR} to present")

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
