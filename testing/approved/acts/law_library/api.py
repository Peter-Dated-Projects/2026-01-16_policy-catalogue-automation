"""
High-level API for Canadian Laws Library
Provides user-facing interface for searching and retrieving laws
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional
from xml.etree import ElementTree as ET

from .repo_manager import LawRepoManager
from .indexer import LawIndexer

logger = logging.getLogger(__name__)


class CanadianLaws:
    """
    User-facing API for the Canadian Laws Library.

    Provides simple methods to:
    - Search for laws by title
    - Retrieve full law content
    - List regulations related to acts
    """

    def __init__(
        self, storage_path: str = "assets/justice_laws_xml", db_path: str = "laws.db"
    ):
        """
        Initialize the Canadian Laws API.

        Args:
            storage_path: Path where the git repository is stored
            db_path: Path to SQLite database
        """
        self.repo_manager = LawRepoManager(storage_path)
        self.indexer = LawIndexer(db_path)

        # Check if we need to build the index
        counts = self.indexer.get_law_count()
        if counts["total"] == 0:
            logger.info("Index is empty. Building initial index...")
            self._rebuild_index()

    def _rebuild_index(self) -> Dict[str, int]:
        """Rebuild the search index from repository files."""
        acts_path = self.repo_manager.get_acts_path()
        regulations_path = self.repo_manager.get_regulations_path()
        return self.indexer.rebuild_index(acts_path, regulations_path)

    def sync(self) -> bool:
        """
        Sync with remote repository and update index if changes detected.

        Returns:
            True if updates were pulled and indexed
        """
        logger.info("Syncing with remote repository...")
        has_updates = self.repo_manager.sync()

        if has_updates:
            logger.info("Updates detected. Rebuilding index...")
            self._rebuild_index()
            return True

        return False

    def search(self, query: str, law_type: Optional[str] = None) -> List[Dict]:
        """
        Search for laws by title using fuzzy matching.

        Args:
            query: Search term (case-insensitive)
            law_type: Optional filter - "Act" or "Regulation"

        Returns:
            List of matching laws with metadata

        Example:
            >>> laws = CanadianLaws()
            >>> results = laws.search("Privacy")
            >>> for law in results:
            ...     print(f"{law['id']}: {law['title']} ({law['type']})")
        """
        results = self.indexer.search(query, law_type)

        if not results:
            logger.info(f"No results found for '{query}'")
        else:
            logger.info(f"Found {len(results)} result(s) for '{query}'")

        return results

    def get_law(self, title: str = None, law_id: str = None) -> Optional[Dict]:
        """
        Get full details and content for a specific law.

        Args:
            title: Law title (will search for exact match)
            law_id: Law ID (e.g., "A-1")

        Returns:
            Dictionary with law metadata and XML content, or None if not found

        Example:
            >>> laws = CanadianLaws()
            >>> law = laws.get_law(law_id="A-1")
            >>> print(law['title'])
            >>> print(law['content'][:200])  # First 200 chars of XML
        """
        if law_id:
            law_data = self.indexer.get_by_id(law_id)
        elif title:
            # Search by exact title
            results = self.indexer.search(title)
            # Try to find exact match
            law_data = next(
                (r for r in results if r["title"].lower() == title.lower()),
                results[0] if results else None,
            )
        else:
            logger.error("Must provide either title or law_id")
            return None

        if not law_data:
            logger.warning(f"Law not found: {title or law_id}")
            return None

        # Read the XML content
        try:
            file_path = Path(law_data["file_path"])
            with open(file_path, "r", encoding="utf-8") as f:
                xml_content = f.read()

            law_data["content"] = xml_content
            law_data["xml_tree"] = ET.parse(file_path)

        except Exception as e:
            logger.error(f"Error reading law file: {e}")
            law_data["content"] = None
            law_data["xml_tree"] = None

        return law_data

    def list_regulations_for_act(self, act_name: str) -> List[Dict]:
        """
        Find regulations that reference a specific Act in their title.

        Args:
            act_name: Name or partial name of the Act

        Returns:
            List of related regulations

        Example:
            >>> laws = CanadianLaws()
            >>> regs = laws.list_regulations_for_act("Access to Information")
            >>> for reg in regs:
            ...     print(f"{reg['id']}: {reg['title']}")
        """
        # Search for regulations that mention the act name
        regulations = self.indexer.search(act_name, law_type="Regulation")

        logger.info(f"Found {len(regulations)} regulation(s) related to '{act_name}'")
        return regulations

    def get_statistics(self) -> Dict:
        """
        Get statistics about the law library.

        Returns:
            Dictionary with counts and repository info
        """
        counts = self.indexer.get_law_count()
        repo_info = self.repo_manager.get_repo_info()

        return {"laws": counts, "repository": repo_info}

    def print_search_results(self, results: List[Dict], max_results: int = 20) -> None:
        """
        Pretty-print search results to console.

        Args:
            results: List of law dictionaries from search()
            max_results: Maximum number of results to display
        """
        if not results:
            print("No results found.")
            return

        print(f"\nFound {len(results)} result(s):")
        print("-" * 80)

        for i, law in enumerate(results[:max_results], 1):
            print(f"{i}. [{law['type']}] {law['id']}: {law['title']}")

        if len(results) > max_results:
            print(f"\n... and {len(results) - max_results} more results")
        print("-" * 80)
