"""
Canadian Law Library - Local mirror system for Government of Canada laws.

This package provides:
- Syncing with the official Department of Justice Git repository
- Access to local Acts and Regulations XML files
"""

from .api import CanadianLaws
from .repo_manager import LawRepoManager

__all__ = ["CanadianLaws", "LawRepoManager"]
