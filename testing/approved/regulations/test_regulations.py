"""
Pytest test suite for the Canada Gazette Regulations scraping system.

Tests cover:
- Part 1: Commissions, Government Notices, Miscellaneous Notices, Parliament, Proposed Regulations
- Part 2: Statutory Orders and Regulations (SOR), Statutory Instruments (SI)
- Part 3: Public Acts and Proclamations
- HTML parsing and data extraction
- URL resolution and PDF link extraction
- Data validation and error handling
"""

import json
import re
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from urllib.parse import urljoin

import pytest
import requests
from bs4 import BeautifulSoup

from part1 import parse_p1_publication, parse_section
from part2 import parse_p2_detail, parse_p2_publication
from part3 import extract_pdf_link, parse_part3_table


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    temp_path = tempfile.mkdtemp()
    yield Path(temp_path)
    # Cleanup
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def mock_part1_index_html():
    """Mock HTML for Part 1 index page."""
    return """
<!DOCTYPE html>
<html>
<head><title>Part I Index</title></head>
<body>
    <h1 id="wb-cont">Canada Gazette Part I</h1>
    <p>Vol. 160, No. 4 — January 24, 2026</p>
    
    <h2><a href="commis-eng.html">Commissions</a></h2>
    
    <h2><a href="notice-avis-eng.html">Government Notices</a></h2>
    
    <h2><a href="misc-divers-eng.html">Miscellaneous Notices</a></h2>
    
    <h2><a href="parliament-parlement-eng.html">Parliament</a></h2>
    
    <h2>Proposed Regulations</h2>
    <h3>Agriculture and Agri-Food</h3>
    <h4>Canadian Food Inspection Agency</h4>
    <ul>
        <li><a href="proposed-reg-1.html">Proposed Regulation 1</a></li>
        <li><a href="proposed-reg-2.html">Proposed Regulation 2</a></li>
    </ul>
</body>
</html>
"""


@pytest.fixture
def mock_part1_section_html():
    """Mock HTML for a Part 1 section page (e.g., Commissions)."""
    return """
<!DOCTYPE html>
<html>
<head><title>Commissions</title></head>
<body>
    <h1 id="wb-cont">Commissions</h1>
    <p>January 24, 2026</p>
    
    <h2 id="cs1">Commission of Inquiry</h2>
    <h3>Inquiries Act</h3>
    <p>This is the content of the commission notice.</p>
    <p>Governing Authority Name</p>
    <p>Ottawa, January 15, 2026</p>
    <p>Commissioner John Doe</p>
    
    <h2 id="cs2">Another Commission</h2>
    <h3>Another Act</h3>
    <p>More commission details here.</p>
    <p>Toronto, January 20, 2026</p>
</body>
</html>
"""


@pytest.fixture
def mock_part2_index_html():
    """Mock HTML for Part 2 index page."""
    return """
<!DOCTYPE html>
<html>
<head><title>Part II Index</title></head>
<body>
    <h1 id="wb-cont">Canada Gazette Part II</h1>
    <p>Vol. 159, No. 26 — December 31, 2025</p>
    
    <ul>
        <li>
            <a href="sor-dors123-eng.html">Test Regulation — Act to Amend</a>
            SOR/2025-123 12/15/25
        </li>
        <li>
            <a href="si-tr456-eng.html">Test Instrument — Another Act</a>
            SI/2025-456 12/20/25
        </li>
    </ul>
</body>
</html>
"""


@pytest.fixture
def mock_part2_detail_html():
    """Mock HTML for a Part 2 detail page."""
    return """
<!DOCTYPE html>
<html>
<head><title>SOR/2025-123</title></head>
<body>
    <main id="wb-cont">
        <h1>Test Regulation</h1>
        <p>SOR/2025-123</p>
        <p>Registered December 15, 2025</p>
        <p>Pursuant to the Test Act</p>
        
        <h2>Amendments</h2>
        <p>Section 1 is amended as follows...</p>
        
        <h2>Coming into Force</h2>
        <p>These regulations come into force on January 1, 2026.</p>
    </main>
</body>
</html>
"""


@pytest.fixture
def mock_part3_index_html():
    """Mock HTML for Part 3 index page."""
    return """
<!DOCTYPE html>
<html>
<head><title>Part III Index</title></head>
<body>
    <h1 id="wb-cont">Canada Gazette Part III</h1>
    
    <table class="table">
        <thead>
            <tr>
                <th>Date</th>
                <th>Acts</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>2024-12-15</td>
                <td><a href="act-toc-1.html">Test Act S.C. 2024, c. 12</a></td>
            </tr>
            <tr>
                <td>2024-12-15</td>
                <td><a href="act-toc-2.html">Another Act S.C. 2024, c. 13</a></td>
            </tr>
            <tr>
                <td>2024-12-20</td>
                <td><a href="act-toc-3.html">Third Act S.C. 2024, c. 14</a></td>
            </tr>
        </tbody>
    </table>
</body>
</html>
"""


@pytest.fixture
def mock_part3_toc_html():
    """Mock HTML for a Part 3 table of contents page."""
    return """
<!DOCTYPE html>
<html>
<head><title>Act TOC</title></head>
<body>
    <h1>Test Act</h1>
    <ul>
        <li><a href="test-act.pdf">Download PDF</a></li>
        <li><a href="section1.html">Section 1</a></li>
    </ul>
</body>
</html>
"""


# ============================================================================
# Part 1 Tests
# ============================================================================


class TestPart1Parsing:
    """Test suite for Part 1 gazette parsing."""

    def test_parse_p1_publication_basic_structure(self, mock_part1_index_html):
        """Test parsing Part 1 index page structure."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_part1_index_html.encode()
            mock_get.return_value = mock_response

            result = parse_p1_publication("https://example.com/index.html")

            assert "Commissions" in result
            assert "Government Notices" in result
            assert "Miscellaneous Notices" in result
            assert "Parliament" in result
            assert "Proposed Regulations" in result

    def test_parse_p1_publication_proposed_regulations(self, mock_part1_index_html):
        """Test parsing proposed regulations section."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_part1_index_html.encode()
            mock_get.return_value = mock_response

            result = parse_p1_publication("https://example.com/index.html")

            proposed_regs = result.get("Proposed Regulations", [])
            assert len(proposed_regs) > 0
            assert proposed_regs[0]["category"] == "Agriculture and Agri-Food"
            assert proposed_regs[0]["department"] == "Canadian Food Inspection Agency"
            assert len(proposed_regs[0]["urls"]) == 2

    def test_parse_section_basic_parsing(self, mock_part1_section_html):
        """Test parsing a Part 1 section page."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_part1_section_html.encode()
            mock_get.return_value = mock_response

            result = parse_section(
                "https://example.com/commis-eng.html", "Commissions", "cs"
            )

            assert "cs1" in result
            assert "cs2" in result
            assert result["cs1"]["title"] == "Commission of Inquiry"
            assert result["cs1"]["subsection"] == "Commissions"
            assert result["cs1"]["category"] == "Part 1"

    def test_parse_section_enabling_act_extraction(self, mock_part1_section_html):
        """Test extraction of enabling act."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_part1_section_html.encode()
            mock_get.return_value = mock_response

            result = parse_section(
                "https://example.com/commis-eng.html", "Commissions", "cs"
            )

            assert result["cs1"]["enabling_act"] == "Inquiries Act"

    def test_parse_section_date_extraction(self, mock_part1_section_html):
        """Test extraction of publication dates."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_part1_section_html.encode()
            mock_get.return_value = mock_response

            result = parse_section(
                "https://example.com/commis-eng.html", "Commissions", "cs"
            )

            # Should extract document-specific date from location pattern
            assert result["cs1"]["location"] == "Ottawa"
            assert "January" in result["cs1"]["publication_date"]

    def test_parse_section_signature_extraction(self, mock_part1_section_html):
        """Test extraction of signature information."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_part1_section_html.encode()
            mock_get.return_value = mock_response

            result = parse_section(
                "https://example.com/commis-eng.html", "Commissions", "cs"
            )

            # Should extract signature containing title
            assert result["cs1"]["signature"] is not None
            assert "Commissioner" in result["cs1"]["signature"]

    def test_parse_section_empty_page(self):
        """Test parsing an empty or invalid page."""
        empty_html = """<html><body>
            <h1 id="wb-cont">Empty Page</h1>
            <p>No Date</p>
        </body></html>"""

        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = empty_html.encode()
            mock_get.return_value = mock_response

            result = parse_section(
                "https://example.com/empty.html", "Commissions", "cs"
            )

            assert result == {}

    def test_parse_section_with_special_characters(self):
        """Test parsing content with special characters."""
        html_with_special = """
<!DOCTYPE html>
<html>
<body>
    <h1 id="wb-cont">Special Characters Page</h1>
    <p>January 24, 2026</p>
    <h2 id="cs1">Commission with "Quotes" & Ampersands</h2>
    <h3>Act with Special Characters © ®</h3>
    <p>Content with ñ and other unicode characters</p>
</body>
</html>
"""

        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = html_with_special.encode("utf-8")
            mock_get.return_value = mock_response

            result = parse_section(
                "https://example.com/special.html", "Commissions", "cs"
            )

            assert "cs1" in result
            # Should handle special characters without error


# ============================================================================
# Part 2 Tests
# ============================================================================


class TestPart2Parsing:
    """Test suite for Part 2 gazette parsing."""

    def test_parse_p2_publication_sor_entries(self, mock_part2_index_html):
        """Test parsing SOR (Statutory Orders and Regulations) entries."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_part2_index_html.encode()
            mock_get.return_value = mock_response

            result = parse_p2_publication("https://example.com/p2-index.html")

            assert "SOR" in result
            assert "SI" in result
            assert len(result["SOR"]) > 0

            sor_entry = result["SOR"][0]
            assert sor_entry["type"] == "SOR"
            assert sor_entry["registration_number"] == "SOR/2025-123"
            assert sor_entry["category"] == "Part 2"

    def test_parse_p2_publication_si_entries(self, mock_part2_index_html):
        """Test parsing SI (Statutory Instruments) entries."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_part2_index_html.encode()
            mock_get.return_value = mock_response

            result = parse_p2_publication("https://example.com/p2-index.html")

            assert len(result["SI"]) > 0

            si_entry = result["SI"][0]
            assert si_entry["type"] == "SI"
            assert si_entry["registration_number"] == "SI/2025-456"

    def test_parse_p2_publication_date_extraction(self, mock_part2_index_html):
        """Test extraction of dates from Part 2 entries."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_part2_index_html.encode()
            mock_get.return_value = mock_response

            result = parse_p2_publication("https://example.com/p2-index.html")

            sor_entry = result["SOR"][0]
            assert "date" in sor_entry
            assert sor_entry["date"] == "12/15/25"

    def test_parse_p2_detail_basic_info(self, mock_part2_detail_html):
        """Test parsing detailed Part 2 regulation page."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_part2_detail_html.encode()
            mock_get.return_value = mock_response

            result = parse_p2_detail("https://example.com/sor-123.html", "SOR")

            assert result["type"] == "SOR"
            assert result["category"] == "Part 2"
            assert "title" in result
            assert result["title"] == "Test Regulation"

    def test_parse_p2_detail_registration_number(self, mock_part2_detail_html):
        """Test extraction of registration number from detail page."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_part2_detail_html.encode()
            mock_get.return_value = mock_response

            result = parse_p2_detail("https://example.com/sor-123.html", "SOR")

            assert result["registration_number"] == "SOR/2025-123"

    def test_parse_p2_detail_enabling_act(self, mock_part2_detail_html):
        """Test extraction of enabling act from detail page."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_part2_detail_html.encode()
            mock_get.return_value = mock_response

            result = parse_p2_detail("https://example.com/sor-123.html", "SOR")

            assert "enabling_act" in result
            assert "Test Act" in result["enabling_act"]

    def test_parse_p2_detail_content_storage(self, mock_part2_detail_html):
        """Test that full HTML content is stored."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_part2_detail_html.encode()
            mock_get.return_value = mock_response

            result = parse_p2_detail("https://example.com/sor-123.html", "SOR")

            assert "content" in result
            assert len(result["content"]) > 0
            assert "<main" in result["content"] or "wb-cont" in result["content"]

    def test_parse_p2_publication_url_resolution(self, mock_part2_index_html):
        """Test that relative URLs are converted to absolute."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_part2_index_html.encode()
            mock_get.return_value = mock_response

            result = parse_p2_publication("https://example.com/p2/index.html")

            # URLs should be absolute
            sor_entry = result["SOR"][0]
            assert sor_entry["url"].startswith("https://")


# ============================================================================
# Part 3 Tests
# ============================================================================


class TestPart3Parsing:
    """Test suite for Part 3 gazette parsing."""

    def test_parse_part3_table_basic_structure(self, mock_part3_index_html):
        """Test parsing Part 3 index table structure."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_part3_index_html.encode()
            mock_get.return_value = mock_response

            result = parse_part3_table("https://example.com/p3/index.html")

            assert len(result) >= 3
            assert all("title" in entry for entry in result)
            assert all("citation" in entry for entry in result)

    def test_parse_part3_table_citation_extraction(self, mock_part3_index_html):
        """Test extraction of statute citations."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_part3_index_html.encode()
            mock_get.return_value = mock_response

            result = parse_part3_table("https://example.com/p3/index.html")

            # Find entry with citation
            entry_with_citation = [e for e in result if e.get("citation")][0]

            assert entry_with_citation["citation"] == "S.C. 2024, c. 12"
            assert entry_with_citation["year"] == "2024"
            assert entry_with_citation["chapter"] == "12"

    def test_parse_part3_table_date_extraction(self, mock_part3_index_html):
        """Test extraction of publication dates."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_part3_index_html.encode()
            mock_get.return_value = mock_response

            result = parse_part3_table("https://example.com/p3/index.html")

            assert all("publication_date" in entry for entry in result)
            # Dates should be extracted from table cells
            assert any("2024-12-15" in entry["publication_date"] for entry in result)

    def test_extract_pdf_link_success(self, mock_part3_toc_html):
        """Test extracting PDF link from TOC page."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_part3_toc_html.encode()
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            pdf_url = extract_pdf_link("https://example.com/toc.html")

            assert pdf_url.endswith(".pdf")
            assert "test-act.pdf" in pdf_url

    def test_extract_pdf_link_no_pdf_found(self):
        """Test when no PDF link is found on TOC page."""
        html_no_pdf = "<html><body><a href='section1.html'>Section</a></body></html>"

        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = html_no_pdf.encode()
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            pdf_url = extract_pdf_link("https://example.com/toc.html")

            # Should return original URL if no PDF found
            assert pdf_url == "https://example.com/toc.html"

    def test_extract_pdf_link_url_resolution(self, mock_part3_toc_html):
        """Test that PDF URLs are properly resolved to absolute URLs."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_part3_toc_html.encode()
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            pdf_url = extract_pdf_link("https://example.com/acts/toc.html")

            assert pdf_url.startswith("https://")

    def test_parse_part3_table_empty_table(self):
        """Test parsing empty Part 3 table."""
        empty_html = """
<html>
<body>
    <table class="table">
        <thead><tr><th>Date</th><th>Acts</th></tr></thead>
        <tbody></tbody>
    </table>
</body>
</html>
"""

        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = empty_html.encode()
            mock_get.return_value = mock_response

            result = parse_part3_table("https://example.com/p3/empty.html")

            assert result == []

    def test_parse_part3_table_skips_invalid_links(self):
        """Test that invalid links are skipped."""
        html_with_invalid = """
<html>
<body>
    <table>
        <tr>
            <td>2024-12-15</td>
            <td>
                <a href="#">Invalid link</a>
                <a href="javascript:void(0)">Another invalid</a>
                <a href="valid-act.html">Valid Act S.C. 2024, c. 15</a>
            </td>
        </tr>
    </table>
</body>
</html>
"""

        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = html_with_invalid.encode()
            mock_get.return_value = mock_response

            result = parse_part3_table("https://example.com/p3/index.html")

            # Should only have 1 valid entry
            assert len(result) == 1
            assert "Valid Act" in result[0]["title"]


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Test error handling across all parts."""

    def test_network_error_handling_part1(self):
        """Test handling of network errors in Part 1."""
        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("Network error")

            # Should not crash
            with pytest.raises(requests.RequestException):
                parse_p1_publication("https://example.com/index.html")

    def test_network_error_handling_part2(self):
        """Test handling of network errors in Part 2."""
        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("Network error")

            with pytest.raises(requests.RequestException):
                parse_p2_publication("https://example.com/index.html")

    def test_invalid_html_parsing_part1(self):
        """Test parsing invalid HTML in Part 1."""
        invalid_html = "This is not valid HTML at all <unclosed tag"

        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = invalid_html.encode()
            mock_get.return_value = mock_response

            # BeautifulSoup is forgiving, should still parse
            result = parse_p1_publication("https://example.com/index.html")
            assert isinstance(result, dict)

    def test_missing_required_fields(self):
        """Test handling of missing required fields."""
        minimal_html = """
<html>
<body>
    <h1 id="wb-cont">Minimal Page</h1>
    <p>No Date Info</p>
    <h2 id="cs1">Title Only</h2>
</body>
</html>
"""

        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = minimal_html.encode()
            mock_get.return_value = mock_response

            result = parse_section(
                "https://example.com/minimal.html", "Commissions", "cs"
            )

            # Should handle missing fields gracefully
            assert "cs1" in result
            assert result["cs1"]["title"] == "Title Only"

    def test_malformed_dates(self):
        """Test handling of malformed date strings."""
        html_bad_date = """
<html>
<body>
    <h1 id="wb-cont">Bad Date Page</h1>
    <p>Invalid Date Format: 99/99/9999</p>
    <h2 id="cs1">Test Entry</h2>
    <p>Invalid Date Format: 99/99/9999</p>
</body>
</html>
"""

        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = html_bad_date.encode()
            mock_get.return_value = mock_response

            # Should not crash on malformed dates
            result = parse_section(
                "https://example.com/baddate.html", "Commissions", "cs"
            )
            assert "cs1" in result


# ============================================================================
# Data Validation Tests
# ============================================================================


class TestDataValidation:
    """Test data validation and structure."""

    def test_part1_data_structure(self, mock_part1_section_html):
        """Test that Part 1 data has expected structure."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_part1_section_html.encode()
            mock_get.return_value = mock_response

            result = parse_section(
                "https://example.com/section.html", "Commissions", "cs"
            )

            for entry_id, entry in result.items():
                assert "title" in entry
                assert "category" in entry
                assert entry["category"] == "Part 1"
                assert "part" in entry
                assert entry["part"] == "1"
                assert "subsection" in entry
                assert "content" in entry

    def test_part2_data_structure(self, mock_part2_index_html):
        """Test that Part 2 data has expected structure."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_part2_index_html.encode()
            mock_get.return_value = mock_response

            result = parse_p2_publication("https://example.com/index.html")

            for entry in result["SOR"]:
                assert "category" in entry
                assert entry["category"] == "Part 2"
                assert "part" in entry
                assert entry["part"] == "2"
                assert "type" in entry
                assert entry["type"] == "SOR"
                assert "url" in entry

    def test_part3_data_structure(self, mock_part3_index_html):
        """Test that Part 3 data has expected structure."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_part3_index_html.encode()
            mock_get.return_value = mock_response

            result = parse_part3_table("https://example.com/index.html")

            for entry in result:
                assert "title" in entry
                assert "publication_date" in entry
                assert "toc_url" in entry
                assert "pdf_url" in entry
                assert "type" in entry

    def test_url_format_validation(self, mock_part2_index_html):
        """Test that URLs are properly formatted."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_part2_index_html.encode()
            mock_get.return_value = mock_response

            result = parse_p2_publication("https://example.com/p2/index.html")

            for entry in result["SOR"]:
                url = entry.get("url", "")
                # Should be absolute URL
                assert url.startswith("http://") or url.startswith("https://")


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for complete workflows."""

    def test_part1_full_workflow(self, mock_part1_index_html, mock_part1_section_html):
        """Test complete Part 1 parsing workflow."""
        with patch("requests.get") as mock_get:

            def side_effect(url, *args, **kwargs):
                mock_response = MagicMock()
                if "index" in url:
                    mock_response.content = mock_part1_index_html.encode()
                else:
                    mock_response.content = mock_part1_section_html.encode()
                return mock_response

            mock_get.side_effect = side_effect

            # Step 1: Parse index
            index_result = parse_p1_publication("https://example.com/index.html")

            assert "Commissions" in index_result

            # Step 2: Parse section
            section_result = parse_section(
                index_result["Commissions"], "Commissions", "cs"
            )

            assert len(section_result) > 0

    def test_part2_full_workflow(self, mock_part2_index_html, mock_part2_detail_html):
        """Test complete Part 2 parsing workflow."""
        with patch("requests.get") as mock_get:

            def side_effect(url, *args, **kwargs):
                mock_response = MagicMock()
                if "index" in url:
                    mock_response.content = mock_part2_index_html.encode()
                else:
                    mock_response.content = mock_part2_detail_html.encode()
                return mock_response

            mock_get.side_effect = side_effect

            # Step 1: Parse index
            index_result = parse_p2_publication("https://example.com/index.html")

            assert len(index_result["SOR"]) > 0

            # Step 2: Parse detail
            detail_url = index_result["SOR"][0]["url"]
            detail_result = parse_p2_detail(detail_url, "SOR")

            assert detail_result["type"] == "SOR"
            assert "content" in detail_result

    def test_part3_full_workflow(self, mock_part3_index_html, mock_part3_toc_html):
        """Test complete Part 3 parsing workflow."""
        with patch("requests.get") as mock_get:

            def side_effect(url, *args, **kwargs):
                mock_response = MagicMock()
                mock_response.raise_for_status = MagicMock()
                if "index" in url:
                    mock_response.content = mock_part3_index_html.encode()
                else:
                    mock_response.content = mock_part3_toc_html.encode()
                return mock_response

            mock_get.side_effect = side_effect

            # Step 1: Parse index table
            result = parse_part3_table("https://example.com/index.html")

            assert len(result) > 0

            # Step 2: Extract PDF link
            toc_url = result[0]["toc_url"]
            pdf_url = extract_pdf_link(toc_url)

            assert pdf_url.endswith(".pdf")


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and unusual scenarios."""

    def test_unicode_characters_in_content(self):
        """Test handling of unicode characters."""
        unicode_html = """
<html>
<body>
    <h1 id="wb-cont">Unicode Page</h1>
    <p>January 24, 2026</p>
    <h2 id="cs1">Règlement français avec caractères spéciaux</h2>
    <p>日本語テキスト</p>
    <p>Текст на русском</p>
</body>
</html>
"""

        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = unicode_html.encode("utf-8")
            mock_get.return_value = mock_response

            result = parse_section(
                "https://example.com/unicode.html", "Commissions", "cs"
            )

            assert "cs1" in result
            # Should handle unicode without error

    def test_very_long_content(self):
        """Test handling of very long content."""
        long_content = "<p>" + "A" * 100000 + "</p>"
        html = f"""
<html>
<body>
    <h1 id="wb-cont">Long Content Page</h1>
    <p>January 24, 2026</p>
    <h2 id="cs1">Entry with very long content</h2>
    {long_content}
</body>
</html>
"""

        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = html.encode()
            mock_get.return_value = mock_response

            result = parse_section("https://example.com/long.html", "Commissions", "cs")

            assert "cs1" in result
            assert len(result["cs1"]["content"]) > 50000

    def test_multiple_dates_in_content(self):
        """Test when multiple dates appear in content."""
        html = """
<html>
<body>
    <h1 id="wb-cont">Multiple Dates Page</h1>
    <p>January 24, 2026</p>
    <h2 id="cs1">Test Entry</h2>
    <p>First date: Ottawa, January 15, 2026</p>
    <p>Second date: Toronto, February 20, 2026</p>
</body>
</html>
"""

        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = html.encode()
            mock_get.return_value = mock_response

            result = parse_section(
                "https://example.com/multidates.html", "Commissions", "cs"
            )

            # Should extract the first valid date pattern
            assert "cs1" in result
            assert result["cs1"]["location"] in ["Ottawa", "Toronto"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
