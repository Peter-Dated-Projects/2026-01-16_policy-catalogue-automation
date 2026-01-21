"""
High-level API for Canadian Laws Library
Provides user-facing interface for syncing and accessing laws
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional
from xml.etree import ElementTree as ET

from .repo_manager import LawRepoManager

logger = logging.getLogger(__name__)


class CanadianLaws:
    """
    User-facing API for the Canadian Laws Library.

    Provides:
    - Syncing with official repository
    - Access to local XML files
    - Repository information
    """

    def __init__(self, storage_path: str = "assets/justice_laws_xml"):
        """
        Initialize the Canadian Laws API.

        Args:
            storage_path: Path where the git repository is stored
        """
        self.repo_manager = LawRepoManager(storage_path)

    def sync(self) -> bool:
        """
        Sync with remote repository.

        Returns:
            True if updates were pulled
        """
        logger.info("Syncing with remote repository...")
        return self.repo_manager.sync()

    def get_acts_path(self) -> Path:
        """
        Get the path to the Acts directory.

        Returns:
            Path to eng/acts directory
        """
        return self.repo_manager.get_acts_path()

    def get_regulations_path(self) -> Path:
        """
        Get the path to the Regulations directory.

        Returns:
            Path to eng/regulations directory
        """
        return self.repo_manager.get_regulations_path()

    def list_all_acts(self) -> List[Path]:
        """
        List all Act XML files in the repository.

        Returns:
            List of paths to Act XML files
        """
        acts_path = self.get_acts_path()
        if not acts_path.exists():
            logger.warning(f"Acts directory not found: {acts_path}")
            return []
        return sorted(acts_path.glob("*.xml"))

    def list_all_regulations(self) -> List[Path]:
        """
        List all Regulation XML files in the repository.

        Returns:
            List of paths to Regulation XML files
        """
        regs_path = self.get_regulations_path()
        if not regs_path.exists():
            logger.warning(f"Regulations directory not found: {regs_path}")
            return []
        return sorted(regs_path.glob("*.xml"))

    def get_statistics(self) -> Dict:
        """
        Get statistics about the law library.

        Returns:
            Dictionary with file counts and repository info
        """
        acts = self.list_all_acts()
        regulations = self.list_all_regulations()
        repo_info = self.repo_manager.get_repo_info()

        return {
            "files": {
                "acts": len(acts),
                "regulations": len(regulations),
                "total": len(acts) + len(regulations),
            },
            "repository": repo_info,
        }
