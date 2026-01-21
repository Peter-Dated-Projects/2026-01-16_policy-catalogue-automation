"""
Canadian Law Library - Local mirror and search system for Government of Canada laws.

This package provides a complete system for:
- Syncing with the official Department of Justice Git repository
- Indexing Acts and Regulations in a SQLite database
- High-level search and retrieval API
"""

from .api import CanadianLaws
from .repo_manager import LawRepoManager
from .indexer import LawIndexer

__all__ = ["CanadianLaws", "LawRepoManager", "LawIndexer"]
