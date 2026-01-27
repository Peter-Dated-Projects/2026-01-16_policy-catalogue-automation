import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
import json


def extract_pdf_link(toc_url: str) -> str:
    """
    Given a table of contents URL, extract the PDF link from that page.
    Returns the PDF URL if found, otherwise returns the original TOC URL.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(toc_url, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        # Look for any <a> tag where the href ends with .pdf
        pdf_link = soup.find(
            "a", href=lambda href: href and href.lower().endswith(".pdf")
        )

        if pdf_link:
            # Combine relative URL with base domain to get the full URL
            full_url = urljoin(toc_url, pdf_link["href"])
            return full_url
        else:
            # If no PDF found, return the original URL
            return toc_url

    except Exception as e:
        print(f"Error extracting PDF from {toc_url}: {e}")
        return toc_url


def parse_part3_table(index_url: str):
    """
    Parses the Part III Index Table structure correctly.
    Target URL: https://gazette.gc.ca/rp-pr/p3/2024/index-eng.html
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    print(f"Fetching: {index_url}")
    response = requests.get(index_url, headers=headers)

    if response.status_code != 200:
        print(f"Failed to fetch page: {response.status_code}")
        return []

    soup = BeautifulSoup(response.content, "html.parser")
    results = []

    # 1. Find the main table (Part III uses a standard DataTable)
    # It usually has classes like 'table' or 'dataTable'
    table = soup.find("table")

    if not table:
        print("No table found on the page. The layout might have changed.")
        return []

    # 2. Iterate through table rows (skip the header)
    rows = table.find_all("tr")

    for row in rows:
        cells = row.find_all("td")
        if not cells or len(cells) < 2:
            continue  # Skip header or malformed rows

        # Column 1: The Date (Applies to all acts in this row)
        date_text = cells[0].get_text(strip=True)

        # Column 2: The Content (Contains multiple <a> tags, one for each Act)
        content_cell = cells[1]
        links = content_cell.find_all("a")

        for link in links:
            title = link.get_text(strip=True)
            href = link.get("href")

            # SKIP LOGIC: Only skip functional/irrelevant links
            if not href or href.startswith("#") or "javascript:" in href:
                continue

            # 3. Extract Citation (S.C. YYYY, c. ##)
            # Regex looks for "S.C. 2024, c. 12" pattern in the title
            citation_match = re.search(r"S\.C\.\s*(\d{4}),\s*c\.\s*(\d+)", title)

            citation = None
            chapter = None
            year = None

            if citation_match:
                year = citation_match.group(1)
                chapter = citation_match.group(2)
                citation = f"S.C. {year}, c. {chapter}"

            # Get the TOC URL
            toc_url = urljoin(index_url, href)

            # Extract PDF URL from the TOC page
            pdf_url = extract_pdf_link(toc_url)

            # 4. Build the entry
            entry = {
                "publication_date": date_text,
                "title": title,
                "citation": citation,
                "chapter": chapter,
                "year": year,
                "toc_url": toc_url,
                "pdf_url": pdf_url,
                "type": "Public Act" if citation else "Proclamation/Other",
            }

            results.append(entry)

    return results


# --- Execution ---
if __name__ == "__main__":
    url = "https://gazette.gc.ca/rp-pr/p3/2024/index-eng.html"
    data = parse_part3_table(url)

    print(f"Found {len(data)} items.")

    # Print sample to verify
    for item in data[:5]:
        print(
            f"[{item['publication_date']}] {item['citation']} -> {item['title'][:50]}..."
        )

    # Optional: Save to file
    with open("part3_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
