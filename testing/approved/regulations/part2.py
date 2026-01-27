from bs4 import BeautifulSoup
import json
import requests
import re
from urllib.parse import urljoin


def parse_p2_publication(index_url: str) -> dict:
    """
    Parses Part II publication index page to extract SOR and SI entries.
    Part II lists entries with title, enabling act, registration number, and date.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36"
    }
    response = requests.get(index_url, headers=headers)
    soup = BeautifulSoup(response.content, "html.parser")

    results = {
        "SOR": [],  # Statutory Orders and Regulations
        "SI": [],  # Statutory Instruments (Other than Regulations)
    }

    # Extract publication date from the page
    wb_cont = soup.find("h1", id="wb-cont")
    publication_date = None
    if wb_cont:
        date_p = wb_cont.find_next("p")
        if date_p:
            publication_date = date_p.get_text(strip=True)

    # Find all links on the page
    all_links = soup.find_all("a")

    for a_tag in all_links:
        href = a_tag.get("href")
        if not href:
            continue

        # Check if this is a link to a regulation or SI document
        # These typically have "sor-dors" or "si-tr" in the URL
        if "sor-dors" not in href and "si-tr" not in href:
            continue

        # Extract entry data
        entry = {
            "category": "Part 2",
            "part": "2",
            "url": urljoin(index_url, href),
        }

        # Get the link text and following text
        link_text = a_tag.get_text(strip=True)

        # The parent element usually contains the full entry info
        parent = a_tag.parent
        if parent:
            full_text = parent.get_text()

            # Extract title from link text
            # Split on em dash or hyphen to separate title from enabling act
            if "—" in link_text:
                parts = link_text.split("—", 1)
                entry["title"] = parts[0].strip()
                if len(parts) > 1:
                    entry["enabling_act"] = parts[1].strip()
            else:
                entry["title"] = link_text

            # Extract registration number (SOR/YYYY-NNN or SI/YYYY-NNN)
            sor_match = re.search(r"SOR/\d{4}-\d+", full_text)
            si_match = re.search(r"SI/\d{4}-\d+", full_text)

            if sor_match:
                entry["registration_number"] = sor_match.group(0)
                entry["type"] = "SOR"

                # Extract date (typically after registration number in format DD/MM/YY)
                date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})", full_text)
                if date_match:
                    entry["date"] = date_match.group(1)

                results["SOR"].append(entry)

            elif si_match:
                entry["registration_number"] = si_match.group(0)
                entry["type"] = "SI"

                # Extract date
                date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})", full_text)
                if date_match:
                    entry["date"] = date_match.group(1)

                results["SI"].append(entry)

    return results


def parse_p2_detail(url: str, entry_type: str) -> dict:
    """
    Parses a detailed Part II regulation or statutory instrument page.
    Extracts full content and metadata.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.content, "html.parser")

    result = {
        "url": url,
        "type": entry_type,
        "category": "Part 2",
        "part": "2",
    }

    # Extract main content container
    main_content = soup.find("main") or soup.find(id="wb-cont")

    if main_content:
        # Extract title (usually h1)
        title_tag = main_content.find("h1")
        if title_tag:
            result["title"] = title_tag.get_text(strip=True)

        # Extract registration number and date (usually in a paragraph near the top)
        paragraphs = main_content.find_all("p")
        for para in paragraphs[:5]:  # Check first few paragraphs
            para_text = para.get_text(strip=True)

            # Look for registration number pattern
            if "SOR/" in para_text or "SI/" in para_text:
                result["registration_number"] = para_text

            # Look for date pattern
            date_pattern = r"([A-Z][a-z]+\s+\d{1,2},\s+\d{4})"
            match = re.search(date_pattern, para_text)
            if match:
                result["date"] = match.group(1)

        # Extract enabling act (usually mentioned early in content)
        enabling_act_tag = main_content.find(
            string=re.compile(r"(Pursuant to|under)", re.IGNORECASE)
        )
        if enabling_act_tag:
            parent = enabling_act_tag.parent
            if parent:
                result["enabling_act"] = parent.get_text(strip=True)

        # Store full HTML content
        result["content"] = str(main_content)

    return result


# Example usage
if __name__ == "__main__":
    # Parse the Part II index page
    index_url = "https://gazette.gc.ca/rp-pr/p2/2025/2025-12-31/html/index-eng.html"

    part2_data = parse_p2_publication(index_url)

    # Output summary
    print(f"Found {len(part2_data['SOR'])} SOR entries")
    print(f"Found {len(part2_data['SI'])} SI entries")

    # Save to JSON
    with open("part2_data.json", "w", encoding="utf-8") as f:
        json.dump(part2_data, f, ensure_ascii=False, indent=4)

    print("\nSample SOR entries:")
    for entry in part2_data["SOR"][:3]:
        print(
            f"  - {entry.get('registration_number', 'N/A')}: {entry.get('title', 'N/A')}"
        )

    print("\nSample SI entries:")
    for entry in part2_data["SI"][:3]:
        print(
            f"  - {entry.get('registration_number', 'N/A')}: {entry.get('title', 'N/A')}"
        )
