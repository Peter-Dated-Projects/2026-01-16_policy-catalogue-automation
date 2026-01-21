"""
SQLite Indexer for Canadian Laws XML files
Parses XML files and creates a searchable database index
"""

import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Optional
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)


class LawIndexer:
    """
    Manages the SQLite database index for quick law searches.

    Scans XML files from the repository and extracts metadata:
    - Law ID (e.g., "A-1")
    - Title (English)
    - Type (Act or Regulation)
    - File path
    """

    def __init__(self, db_path: str = "laws.db"):
        """
        Initialize the indexer with a database path.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._init_database()

    def _init_database(self) -> None:
        """Create the database schema if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS laws (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    title_fr TEXT,
                    type TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Create index for faster searches
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_title 
                ON laws(title)
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_type 
                ON laws(type)
            """
            )

            conn.commit()
        logger.info(f"Database initialized at {self.db_path}")

    def _parse_xml_file(self, xml_path: Path) -> Optional[Dict[str, str]]:
        """
        Parse an XML file and extract law metadata.

        Args:
            xml_path: Path to XML file

        Returns:
            Dictionary with law metadata or None if parsing fails
        """
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()

            # Extract law ID from filename (e.g., "A-1.xml" -> "A-1")
            law_id = xml_path.stem

            # Try to find the title - XML structure may vary
            # Common paths: Title, LongTitle, ShortTitle
            title_en = None
            title_fr = None

            # Try different XML namespaces and tag names
            for title_tag in ["Title", "LongTitle", "ShortTitle", "Label"]:
                elements = root.findall(f".//{title_tag}")
                for elem in elements:
                    if elem.text and not title_en:
                        title_en = elem.text.strip()
                        break

            # If still no title, try to get from filename
            if not title_en:
                title_en = law_id.replace("-", " ")

            return {
                "id": law_id,
                "title": title_en,
                "title_fr": title_fr,
                "file_path": str(xml_path),
            }

        except ET.ParseError as e:
            logger.warning(f"Failed to parse {xml_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error processing {xml_path}: {e}")
            return None

    def index_directory(self, directory: Path, law_type: str) -> int:
        """
        Index all XML files in a directory.

        Args:
            directory: Path to directory containing XML files
            law_type: Type of law ("Act" or "Regulation")

        Returns:
            Number of files indexed
        """
        if not directory.exists():
            logger.warning(f"Directory does not exist: {directory}")
            return 0

        xml_files = list(directory.glob("*.xml"))
        logger.info(f"Found {len(xml_files)} XML files in {directory}")

        indexed_count = 0

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            for xml_file in xml_files:
                law_data = self._parse_xml_file(xml_file)

                if law_data:
                    try:
                        cursor.execute(
                            """
                            INSERT OR REPLACE INTO laws (id, title, title_fr, type, file_path, last_updated)
                            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """,
                            (
                                law_data["id"],
                                law_data["title"],
                                law_data["title_fr"],
                                law_type,
                                law_data["file_path"],
                            ),
                        )
                        indexed_count += 1
                    except sqlite3.Error as e:
                        logger.error(f"Database error for {xml_file}: {e}")

            conn.commit()

        logger.info(f"Indexed {indexed_count} {law_type}s")
        return indexed_count

    def rebuild_index(self, acts_path: Path, regulations_path: Path) -> Dict[str, int]:
        """
        Rebuild the entire index from scratch.

        Args:
            acts_path: Path to Acts directory
            regulations_path: Path to Regulations directory

        Returns:
            Dictionary with counts of indexed Acts and Regulations
        """
        logger.info("Rebuilding law index...")

        # Clear existing data
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM laws")
            conn.commit()

        acts_count = self.index_directory(acts_path, "Act")
        regulations_count = self.index_directory(regulations_path, "Regulation")

        logger.info(
            f"Index rebuilt: {acts_count} Acts, {regulations_count} Regulations"
        )

        return {
            "acts": acts_count,
            "regulations": regulations_count,
            "total": acts_count + regulations_count,
        }

    def get_law_count(self) -> Dict[str, int]:
        """
        Get counts of indexed laws by type.

        Returns:
            Dictionary with counts
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM laws WHERE type = 'Act'")
            acts_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM laws WHERE type = 'Regulation'")
            regulations_count = cursor.fetchone()[0]

            return {
                "acts": acts_count,
                "regulations": regulations_count,
                "total": acts_count + regulations_count,
            }

    def search(self, query: str, law_type: Optional[str] = None) -> List[Dict]:
        """
        Search for laws by title.

        Args:
            query: Search query
            law_type: Optional filter by type ("Act" or "Regulation")

        Returns:
            List of matching laws
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if law_type:
                cursor.execute(
                    """
                    SELECT * FROM laws 
                    WHERE title LIKE ? AND type = ?
                    ORDER BY title
                """,
                    (f"%{query}%", law_type),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM laws 
                    WHERE title LIKE ?
                    ORDER BY type, title
                """,
                    (f"%{query}%",),
                )

            return [dict(row) for row in cursor.fetchall()]

    def get_by_id(self, law_id: str) -> Optional[Dict]:
        """
        Get a law by its ID.

        Args:
            law_id: Law identifier

        Returns:
            Law data or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM laws WHERE id = ?", (law_id,))
            row = cursor.fetchone()

            return dict(row) if row else None
