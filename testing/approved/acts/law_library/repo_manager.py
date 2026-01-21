"""
Git Repository Manager for Canadian Laws XML Repository
Handles cloning and syncing with https://github.com/justicecanada/laws-lois-xml
"""

import os
import logging
from pathlib import Path
from git import Repo, GitCommandError, InvalidGitRepositoryError
from typing import Optional

logger = logging.getLogger(__name__)


class LawRepoManager:
    """
    Manages the local mirror of the Justice Canada laws repository.

    Handles:
    - Initial cloning if repository doesn't exist
    - Checking for updates
    - Pulling latest changes
    """

    REPO_URL = "https://github.com/justicecanada/laws-lois-xml.git"

    def __init__(self, storage_path: str = "assets/justice_laws_xml"):
        """
        Initialize the repository manager.

        Args:
            storage_path: Local path where the repository will be stored
        """
        self.storage_path = Path(storage_path)
        self.repo: Optional[Repo] = None
        self._initialize_repo()

    def _initialize_repo(self) -> None:
        """Initialize or connect to existing repository."""
        if not self.storage_path.exists():
            logger.info(f"Repository not found at {self.storage_path}. Cloning...")
            self._clone_repo()
        else:
            try:
                self.repo = Repo(self.storage_path)
                logger.info(f"Connected to existing repository at {self.storage_path}")
            except InvalidGitRepositoryError:
                logger.warning(
                    f"Invalid git repository at {self.storage_path}. Re-cloning..."
                )
                self._clone_repo()

    def _clone_repo(self) -> None:
        """Clone the repository from GitHub."""
        try:
            # Create parent directory if it doesn't exist
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)

            logger.info(f"Cloning {self.REPO_URL} to {self.storage_path}...")
            self.repo = Repo.clone_from(
                self.REPO_URL,
                self.storage_path,
                progress=None,  # Set to a progress handler if needed
            )
            logger.info("Repository cloned successfully!")
        except GitCommandError as e:
            logger.error(f"Failed to clone repository: {e}")
            raise

    def check_for_updates(self) -> bool:
        """
        Check if remote has new commits.

        Returns:
            True if updates are available, False otherwise
        """
        if not self.repo:
            logger.error("Repository not initialized")
            return False

        try:
            # Fetch remote changes without merging
            logger.info("Fetching remote changes...")
            origin = self.repo.remotes.origin
            origin.fetch()

            # Compare local and remote commits
            local_commit = self.repo.head.commit
            remote_commit = (
                origin.refs.main.commit
            )  # or 'master' depending on default branch

            if local_commit.hexsha != remote_commit.hexsha:
                logger.info("Updates available!")
                return True
            else:
                logger.info("Repository is up to date")
                return False

        except GitCommandError as e:
            logger.error(f"Error checking for updates: {e}")
            return False
        except AttributeError:
            # If 'main' doesn't exist, try 'master'
            try:
                remote_commit = origin.refs.master.commit
                local_commit = self.repo.head.commit
                return local_commit.hexsha != remote_commit.hexsha
            except Exception as e:
                logger.error(f"Error determining default branch: {e}")
                return False

    def sync(self) -> bool:
        """
        Sync with remote repository (fetch + pull if updates available).

        Returns:
            True if changes were pulled, False otherwise
        """
        if not self.repo:
            logger.error("Repository not initialized")
            return False

        try:
            has_updates = self.check_for_updates()

            if has_updates:
                logger.info("Pulling latest changes...")
                origin = self.repo.remotes.origin
                origin.pull()
                logger.info("Repository synced successfully!")
                return True
            else:
                logger.info("No updates to pull")
                return False

        except GitCommandError as e:
            logger.error(f"Failed to sync repository: {e}")

            # Handle common issues
            if "merge conflict" in str(e).lower():
                logger.error("Merge conflict detected. Manual intervention required.")
            elif "network" in str(e).lower() or "connection" in str(e).lower():
                logger.error("Network issue. Will retry on next sync cycle.")

            return False
        except Exception as e:
            logger.error(f"Unexpected error during sync: {e}")
            return False

    def get_acts_path(self) -> Path:
        """Get path to Acts directory."""
        return self.storage_path / "eng" / "acts"

    def get_regulations_path(self) -> Path:
        """Get path to Regulations directory."""
        return self.storage_path / "eng" / "regulations"

    def is_initialized(self) -> bool:
        """Check if repository is properly initialized."""
        return self.repo is not None and self.storage_path.exists()

    def get_repo_info(self) -> dict:
        """
        Get information about the repository.

        Returns:
            Dictionary with repo metadata
        """
        if not self.repo:
            return {"initialized": False}

        try:
            return {
                "initialized": True,
                "path": str(self.storage_path),
                "current_commit": self.repo.head.commit.hexsha[:8],
                "last_commit_date": self.repo.head.commit.committed_datetime.isoformat(),
                "branch": self.repo.active_branch.name,
                "remotes": [remote.name for remote in self.repo.remotes],
            }
        except Exception as e:
            logger.error(f"Error getting repo info: {e}")
            return {"initialized": True, "error": str(e)}
