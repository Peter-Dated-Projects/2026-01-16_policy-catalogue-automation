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


def detect_gazette_part(soup: BeautifulSoup) -> str:
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


def extract_part_i(soup: BeautifulSoup, url: str) -> List[Dict]:
    """
    Extract data from Part I Gazette (Notices & Proposed Regulations).

    Part I uses hierarchical headers:
    - h2/h3: Category (Government Notices, Parliament, Proposed Regulations)
    - h4: Organization/Department
    - h5: Enabling Act
    - ul/li: Individual items with links

    Args:
        soup: BeautifulSoup object
        url: Base URL for resolving relative links

    Returns:
        List of dictionaries with structured data
    """
    results = []

    # Find the main content area
    main_content = soup.find("main") or soup.find("div", class_="main-content") or soup

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

        # Items with links (look for <a> tags within lists or paragraphs)
        elif element.name == "a" and element.get("href"):
            href = element.get("href")
            # Skip navigation links and anchors
            if href.startswith("#") or "index-eng" in href or "index-fra" in href:
                continue

            title = element.get_text(strip=True)
            if not title:  # Skip empty links
                continue

            # Resolve relative URLs
            full_url = urljoin(url, href)

            # Create entry
            entry = {
                "part": "Part I",
                "category": current_category,
                "organization": current_organization,
                "enabling_act": current_enabling_act,
                "title": title,
                "registration_id": None,  # Part I doesn't have registration IDs
                "url": full_url,
            }
            results.append(entry)

    return results


def extract_part_ii(soup: BeautifulSoup, url: str) -> List[Dict]:
    """
    Extract data from Part II Gazette (Official Regulations).

    Part II uses tabular structure with columns:
    - Title
    - Enabling Act
    - Registration Number (SOR/SI)
    - Date

    Args:
        soup: BeautifulSoup object
        url: Base URL for resolving relative links

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
                th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])
            ]
            if any(
                h in " ".join(potential_headers)
                for h in ["title", "act", "registration"]
            ):
                headers = potential_headers
                rows = rows[1:]  # Skip header row

        # Process data rows
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:  # Skip rows with too few columns
                continue

            # Extract data based on common patterns
            title = None
            enabling_act = None
            registration_id = None
            item_url = None

            for cell in cells:
                cell_text = cell.get_text(strip=True)

                # Look for registration ID pattern (SOR/YYYY-XXX or SI/YYYY-XXX)
                reg_match = re.search(r"(SOR|SI)/\d{4}-\d+", cell_text)
                if reg_match:
                    registration_id = reg_match.group(0)

                # Look for links (these are usually the title)
                link = cell.find("a")
                if link and link.get("href"):
                    title = link.get_text(strip=True)
                    item_url = urljoin(url, link.get("href"))

                # Heuristic: longer text without SOR/SI is likely the act name
                if len(cell_text) > 10 and not reg_match and not link:
                    if "act" in cell_text.lower() or "regulations" in cell_text.lower():
                        enabling_act = cell_text

            # Only add if we have at least a title
            if title:
                entry = {
                    "part": "Part II",
                    "category": "Official Regulations",
                    "organization": None,  # Part II doesn't typically list organizations
                    "enabling_act": enabling_act,
                    "title": title,
                    "registration_id": registration_id,
                    "url": item_url,
                }
                results.append(entry)

    return results


def scrape_gazette(url: str) -> List[Dict]:
    """
    Main function to scrape a Canada Gazette index page.

    Args:
        url: URL of the Gazette index page

    Returns:
        List of structured dictionaries containing regulation/notice data
    """
    try:
        # Make HTTP request with proper headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()  # Raise exception for HTTP errors

        # Parse HTML
        soup = BeautifulSoup(response.content, "html.parser")

        # Detect which part we're scraping
        part = detect_gazette_part(soup)
        print(f"Detected: {part}")

        # Use appropriate extraction logic
        if part == "Part I":
            results = extract_part_i(soup, url)
        else:
            results = extract_part_ii(soup, url)

        return results

    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL: {e}")
        return []
    except Exception as e:
        print(f"Error processing page: {e}")
        return []


# Main execution
if __name__ == "__main__":
    # Sample URLs for testing
    # Part I: Notices and Proposed Regulations
    url_part_i = "https://gazette.gc.ca/rp-pr/p1/2026/2026-01-24/html/index-eng.html"

    # Part II: Official Regulations (example - uncomment to test)
    # url_part_ii = "https://gazette.gc.ca/rp-pr/p2/2026/2026-01-22/html/index-eng.html"

    # Scrape the page
    print(f"Scraping: {url_part_i}")
    data = scrape_gazette(url_part_i)

    # Output results
    print(f"\nExtracted {len(data)} items:")
    print(json.dumps(data, indent=2, ensure_ascii=False))

    # Optionally save to file
    with open("gazette_data.json", "w", encoding="utf-8") as f:
        json.dump(data, indent=2, ensure_ascii=False, fp=f)
    print("\nData saved to gazette_data.json")
