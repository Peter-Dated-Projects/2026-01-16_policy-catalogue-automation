from bs4 import BeautifulSoup
import json
import requests
import re
from urllib.parse import urljoin


# this is specifically for part 1
# use index urls to find specific urls
# like commission
URLS = [
    "https://gazette.gc.ca/rp-pr/p1/2026/2026-01-24/html/commis-eng.html",  # commisions
    "https://gazette.gc.ca/rp-pr/p1/2026/2026-01-24/html/notice-avis-eng.html",  # gov notices
    "https://gazette.gc.ca/rp-pr/p1/2026/2026-01-24/html/misc-divers-eng.html",  # misc notices,
    "https://gazette.gc.ca/rp-pr/p1/2026/2026-01-24/html/parliament-parlement-eng.html",  # parliament,
]


parsable_sections = [
    "Commissions",
    "Government Notices",
    "Miscellaneous Notices",
    "Parliament",
]
valid_types = [
    "Commissions",
    "Government Notices",
    "Miscellaneous Notices",
    "Parliament",
    "Proposed Regulations",
]

publication_item_identifier_prefix = ["cs", "ne", "ml", "pe"]


def parse_p1_publication(index_url: str) -> dict:
    # parses the part 1 publication index page to get all relevant urls
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36"
    }
    response = requests.get(index_url, headers=headers)
    soup = BeautifulSoup(response.content, "html.parser")

    # Find all h2 elements
    all_h2 = soup.find_all("h2")

    # Create lowercase stripped version of valid types for comparison
    valid_types_lower = [vt.lower().strip() for vt in valid_types]

    results = {}

    for h2 in all_h2:
        h2_text = h2.get_text(strip=True).lower()

        # Check if this h2 matches any valid type
        if h2_text in valid_types_lower:
            section_type = valid_types[valid_types_lower.index(h2_text)]

            # Handle Proposed Regulations specially
            if section_type == "Proposed Regulations":
                proposed_regs = []

                # Collect all siblings until we hit another valid type or footnote
                for sibling in h2.find_next_siblings():
                    # Stop if we hit another h2 with valid type or footnote
                    if sibling.name == "h2":
                        sibling_text = sibling.get_text(strip=True).lower()
                        if (
                            sibling_text in valid_types_lower
                            or sibling.get("id") == "fn"
                        ):
                            break

                    # Look for h3 (category)
                    if sibling.name == "h3":
                        category = sibling.get_text(strip=True)

                        # Find next h4 (department name)
                        h4 = sibling.find_next_sibling("h4")
                        if h4:
                            dept_name = h4.get_text(strip=True)

                            # Find next ul (contains URLs)
                            ul = h4.find_next_sibling("ul")
                            urls = []
                            if ul:
                                # Extract all URLs from li > a elements
                                for li in ul.find_all("li"):
                                    a_tag = li.find("a")
                                    if a_tag and a_tag.get("href"):
                                        # Convert relative URL to absolute URL
                                        relative_url = a_tag.get("href")
                                        absolute_url = urljoin(index_url, relative_url)
                                        urls.append(absolute_url)

                            proposed_regs.append(
                                {
                                    "category": category,
                                    "department": dept_name,
                                    "urls": urls,
                                }
                            )

                results[section_type] = proposed_regs
            else:
                # For other sections, find and store the URL
                section_url = None

                # Check if h2 contains a link
                a_tag = h2.find("a")
                if a_tag and a_tag.get("href"):
                    relative_url = a_tag.get("href")
                    section_url = urljoin(index_url, relative_url)
                else:
                    # Look for link in next sibling
                    next_elem = h2.find_next_sibling()
                    if next_elem:
                        a_tag = next_elem.find("a")
                        if a_tag and a_tag.get("href"):
                            relative_url = a_tag.get("href")
                            section_url = urljoin(index_url, relative_url)

                results[section_type] = section_url

    return results


def parse_section(url: str, section_name: str, identifier_prefix: str) -> dict:

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.content, "html.parser")

    # extract publication date from the page
    # find h1 with id="wb-cont" and get the first <p> tag after it
    wb_cont = soup.find("h1", id="wb-cont")
    publication_date = None

    # find the first <p> tag after the h1
    date_p = wb_cont.find_next("p")
    if date_p:
        # extract date text and parse it
        date_text = date_p.get_text(strip=True)
        publication_date = date_text

    # grab all h2 with id starting with cs
    h2_tags = soup.find_all("h2", id=lambda x: x and x.startswith(identifier_prefix))

    # find all intermediate html objects between h2 tags
    # store as raw html objects (not text)
    results = {}
    for h2 in h2_tags:
        section_id = h2["id"]
        section_title = h2.get_text(strip=True)
        content = []
        for sibling in h2.find_next_siblings():
            if sibling.name == "h2":
                break
            content.append(str(sibling))
        results[section_id] = {
            "title": section_title,
            "content": "\n".join(content),
            "subsection": section_name,
        }

    # for each publication item in part1_data, update object data
    # include: title, category (part 1), enabling_act, governing_authority, publication_date, content (raw html of all content objects)
    # signature, date, location, if applicable

    for section_id, data in results.items():
        # parse content to extract metadata
        content_soup = BeautifulSoup(data["content"], "html.parser")

        # Extract enabling act (look for h3 tags - typically the act name)
        h3_tag = content_soup.find("h3")
        data["enabling_act"] = h3_tag.get_text(strip=True) if h3_tag else None

        # Extract governing authority (from the section title or first h2)
        # The title itself often contains the authority
        data["governing_authority"] = data["title"]

        # Set category
        data["category"] = "Part 1"

        # set part
        data["part"] = "1"

        # Extract document-specific date from content (usually at the end)
        # Format: "location, month day, year" (e.g., "Ottawa, January 15, 2026")
        document_date = None
        location = None

        paragraphs = content_soup.find_all("p")
        if paragraphs:
            # Check last few paragraphs for date pattern
            for para in reversed(paragraphs[-3:]):  # Check last 3 paragraphs
                para_text = para.get_text(strip=True)
                # Pattern: City/Location, Month Day, Year
                date_pattern = r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?),\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})"
                match = re.search(date_pattern, para_text)
                if match:
                    location = match.group(1)
                    document_date = match.group(2)
                    break

        # Use document-specific date if found, otherwise use publication date
        data["publication_date"] = document_date if document_date else publication_date
        data["location"] = location

        # Extract signature information (name, title, location, date)
        # Signatures typically appear at the end, often without specific HTML structure
        # Look for patterns like names followed by titles and locations

        # Try to find signature patterns (text at the end with name, title, location)
        # This is a heuristic - signatures often have specific patterns
        if paragraphs:
            # Check paragraph before the date (usually signature)
            for para in reversed(paragraphs):
                para_text = para.get_text(strip=True)
                # Skip if this is the date paragraph
                if document_date and document_date in para_text:
                    continue
                # Check if it looks like a signature (contains a name pattern)
                if any(
                    word in para_text.lower()
                    for word in ["director", "secretary", "minister", "commissioner"]
                ):
                    data["signature"] = para_text
                    break
            else:
                data["signature"] = None
        else:
            data["signature"] = None

    return results


parsed_sections = parse_p1_publication(
    "https://gazette.gc.ca/rp-pr/p1/2024/2024-12-28/html/index-eng.html"
)

part1_data = {
    section_name: parse_section(
        parsed_sections[url_key], section_name, identifier_prefix
    )
    for url_key, section_name, identifier_prefix in zip(
        parsed_sections, valid_types, publication_item_identifier_prefix
    )
    if url_key in parsable_sections
}

if "Proposed Regulations" in parsed_sections:
    part1_data["Proposed Regulations"] = parsed_sections["Proposed Regulations"]


# output to json
with open("part1_data.json", "w", encoding="utf-8") as f:
    json.dump(part1_data, f, ensure_ascii=False, indent=4)
