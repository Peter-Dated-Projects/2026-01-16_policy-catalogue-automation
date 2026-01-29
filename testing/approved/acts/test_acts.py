"""
Pytest test suite for the Canadian Law Library (Acts) system.

Tests cover:
- Repository management (cloning, syncing, checking for updates)
- API functionality (getting paths, listing acts/regulations, statistics)
- Database indexing (parsing XML, storing metadata, searching)
- Daemon functionality (background sync)
"""

import json
import logging
import os
import shutil
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from xml.etree import ElementTree as ET

import pytest
from git import Repo

from law_library import CanadianLaws
from law_library.api import CanadianLaws as CanadianLawsAPI
from law_library.indexer import LawIndexer
from law_library.repo_manager import LawRepoManager
from main import LawLibraryDaemon


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
def mock_git_repo(temp_dir):
    """Create a mock git repository structure."""
    repo_path = temp_dir / "test_repo"
    repo_path.mkdir()

    # Create directory structure
    eng_path = repo_path / "eng"
    eng_path.mkdir()
    (eng_path / "acts").mkdir()
    (eng_path / "regulations").mkdir()

    # Create sample XML files
    create_sample_xml(eng_path / "acts" / "A-1.xml", "Test Act 1", "Act")
    create_sample_xml(eng_path / "acts" / "A-2.xml", "Test Act 2", "Act")
    create_sample_xml(
        eng_path / "regulations" / "SOR-123.xml", "Test Regulation", "Regulation"
    )

    return repo_path


@pytest.fixture
def sample_xml_content():
    """Generate sample XML content for testing."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<Statute>
    <Title>Test Statute Title</Title>
    <LongTitle>Long Title for Test Statute</LongTitle>
    <Section>
        <Label>1</Label>
        <Text>Sample section text</Text>
    </Section>
</Statute>"""


def create_sample_xml(path: Path, title: str, doc_type: str):
    """Helper function to create sample XML files."""
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<Statute>
    <Title>{title}</Title>
    <LongTitle>Long {title}</LongTitle>
    <Type>{doc_type}</Type>
</Statute>"""
    path.write_text(xml_content, encoding="utf-8")


# ============================================================================
# Repository Manager Tests
# ============================================================================


class TestLawRepoManager:
    """Test suite for LawRepoManager class."""

    def test_init_with_nonexistent_repo(self, temp_dir):
        """Test initialization when repository doesn't exist."""
        storage_path = temp_dir / "nonexistent_repo"

        with patch.object(Repo, "clone_from") as mock_clone:
            mock_repo = MagicMock()
            mock_clone.return_value = mock_repo

            manager = LawRepoManager(str(storage_path))

            # Should attempt to clone
            mock_clone.assert_called_once()
            assert manager.storage_path == storage_path

    def test_init_with_existing_repo(self, temp_dir, mock_git_repo):
        """Test initialization when repository already exists."""
        # Initialize a real git repo in mock_git_repo
        Repo.init(str(mock_git_repo))

        manager = LawRepoManager(str(mock_git_repo))

        assert manager.repo is not None
        assert manager.storage_path == mock_git_repo
        assert manager.is_initialized()

    def test_get_acts_path(self, temp_dir, mock_git_repo):
        """Test getting the acts directory path."""
        with patch.object(LawRepoManager, "_initialize_repo"):
            manager = LawRepoManager(str(mock_git_repo))
            manager.storage_path = mock_git_repo

            acts_path = manager.get_acts_path()
            assert acts_path == mock_git_repo / "eng" / "acts"

    def test_get_regulations_path(self, temp_dir, mock_git_repo):
        """Test getting the regulations directory path."""
        with patch.object(LawRepoManager, "_initialize_repo"):
            manager = LawRepoManager(str(mock_git_repo))
            manager.storage_path = mock_git_repo

            regs_path = manager.get_regulations_path()
            assert regs_path == mock_git_repo / "eng" / "regulations"

    def test_check_for_updates_no_repo(self, temp_dir):
        """Test checking for updates when repo is not initialized."""
        with patch.object(LawRepoManager, "_initialize_repo"):
            manager = LawRepoManager(str(temp_dir / "test"))
            manager.repo = None

            result = manager.check_for_updates()
            assert result is False

    def test_check_for_updates_with_changes(self, temp_dir, mock_git_repo):
        """Test checking for updates when remote has changes."""
        Repo.init(str(mock_git_repo))

        with patch.object(LawRepoManager, "_initialize_repo"):
            manager = LawRepoManager(str(mock_git_repo))
            manager.repo = Repo(str(mock_git_repo))

            # Mock the remote
            mock_origin = MagicMock()
            mock_origin.fetch = MagicMock()

            # Mock different commits
            local_commit = MagicMock()
            local_commit.hexsha = "abc123"
            remote_commit = MagicMock()
            remote_commit.hexsha = "def456"

            manager.repo.remotes.origin = mock_origin
            manager.repo.head.commit = local_commit
            mock_origin.refs.main.commit = remote_commit

            result = manager.check_for_updates()
            assert result is True

    def test_sync_with_updates(self, temp_dir, mock_git_repo):
        """Test syncing when updates are available."""
        Repo.init(str(mock_git_repo))

        with patch.object(LawRepoManager, "_initialize_repo"):
            manager = LawRepoManager(str(mock_git_repo))
            manager.repo = Repo(str(mock_git_repo))

            # Mock check_for_updates to return True
            with patch.object(manager, "check_for_updates", return_value=True):
                mock_origin = MagicMock()
                manager.repo.remotes.origin = mock_origin

                result = manager.sync()

                # Should pull changes
                mock_origin.pull.assert_called_once()
                assert result is True

    def test_sync_no_updates(self, temp_dir, mock_git_repo):
        """Test syncing when no updates are available."""
        Repo.init(str(mock_git_repo))

        with patch.object(LawRepoManager, "_initialize_repo"):
            manager = LawRepoManager(str(mock_git_repo))
            manager.repo = Repo(str(mock_git_repo))

            # Mock check_for_updates to return False
            with patch.object(manager, "check_for_updates", return_value=False):
                result = manager.sync()
                assert result is False

    def test_get_repo_info(self, temp_dir, mock_git_repo):
        """Test getting repository information."""
        repo = Repo.init(str(mock_git_repo))

        with patch.object(LawRepoManager, "_initialize_repo"):
            manager = LawRepoManager(str(mock_git_repo))
            manager.repo = repo

            info = manager.get_repo_info()

            assert info["initialized"] is True
            assert "path" in info
            assert "branch" in info


# ============================================================================
# Indexer Tests
# ============================================================================


class TestLawIndexer:
    """Test suite for LawIndexer class."""

    def test_init_creates_database(self, temp_dir):
        """Test that initialization creates the database schema."""
        db_path = temp_dir / "test_laws.db"
        indexer = LawIndexer(str(db_path))

        assert db_path.exists()

        # Verify schema
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='laws'"
            )
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == "laws"

    def test_parse_xml_file_valid(self, temp_dir, sample_xml_content):
        """Test parsing a valid XML file."""
        xml_path = temp_dir / "test.xml"
        xml_path.write_text(sample_xml_content, encoding="utf-8")

        db_path = temp_dir / "test_laws.db"
        indexer = LawIndexer(str(db_path))

        result = indexer._parse_xml_file(xml_path)

        assert result is not None
        assert result["id"] == "test"
        assert "Test Statute Title" in result["title"]
        assert result["file_path"] == str(xml_path)

    def test_parse_xml_file_invalid(self, temp_dir):
        """Test parsing an invalid XML file."""
        xml_path = temp_dir / "invalid.xml"
        xml_path.write_text("This is not valid XML", encoding="utf-8")

        db_path = temp_dir / "test_laws.db"
        indexer = LawIndexer(str(db_path))

        result = indexer._parse_xml_file(xml_path)
        assert result is None

    def test_index_directory(self, temp_dir, mock_git_repo):
        """Test indexing a directory of XML files."""
        db_path = temp_dir / "test_laws.db"
        indexer = LawIndexer(str(db_path))

        acts_path = mock_git_repo / "eng" / "acts"
        count = indexer.index_directory(acts_path, "Act")

        assert count == 2  # We created 2 act files

        # Verify database contents
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM laws WHERE type='Act'")
            results = cursor.fetchall()
            assert len(results) == 2

    def test_rebuild_index(self, temp_dir, mock_git_repo):
        """Test rebuilding the entire index."""
        db_path = temp_dir / "test_laws.db"
        indexer = LawIndexer(str(db_path))

        acts_path = mock_git_repo / "eng" / "acts"
        regs_path = mock_git_repo / "eng" / "regulations"

        result = indexer.rebuild_index(acts_path, regs_path)

        assert result["acts"] == 2
        assert result["regulations"] == 1
        assert result["total"] == 3

    def test_get_law_count(self, temp_dir, mock_git_repo):
        """Test getting law counts."""
        db_path = temp_dir / "test_laws.db"
        indexer = LawIndexer(str(db_path))

        acts_path = mock_git_repo / "eng" / "acts"
        regs_path = mock_git_repo / "eng" / "regulations"
        indexer.rebuild_index(acts_path, regs_path)

        counts = indexer.get_law_count()

        assert counts["acts"] == 2
        assert counts["regulations"] == 1
        assert counts["total"] == 3

    def test_search(self, temp_dir, mock_git_repo):
        """Test searching for laws."""
        db_path = temp_dir / "test_laws.db"
        indexer = LawIndexer(str(db_path))

        acts_path = mock_git_repo / "eng" / "acts"
        regs_path = mock_git_repo / "eng" / "regulations"
        indexer.rebuild_index(acts_path, regs_path)

        # Search for acts
        results = indexer.search("Test Act", law_type="Act")
        assert len(results) == 2

        # Search all
        results = indexer.search("Test")
        assert len(results) == 3

    def test_get_by_id(self, temp_dir, mock_git_repo):
        """Test getting a law by ID."""
        db_path = temp_dir / "test_laws.db"
        indexer = LawIndexer(str(db_path))

        acts_path = mock_git_repo / "eng" / "acts"
        regs_path = mock_git_repo / "eng" / "regulations"
        indexer.rebuild_index(acts_path, regs_path)

        law = indexer.get_by_id("A-1")
        assert law is not None
        assert law["id"] == "A-1"
        assert law["type"] == "Act"

        # Test non-existent ID
        law = indexer.get_by_id("NONEXISTENT")
        assert law is None


# ============================================================================
# API Tests
# ============================================================================


class TestCanadianLawsAPI:
    """Test suite for CanadianLaws API class."""

    def test_init(self, temp_dir):
        """Test API initialization."""
        with patch.object(LawRepoManager, "_initialize_repo"):
            api = CanadianLawsAPI(str(temp_dir / "test_storage"))
            assert api.repo_manager is not None

    def test_sync(self, temp_dir):
        """Test syncing through API."""
        with patch.object(LawRepoManager, "_initialize_repo"):
            with patch.object(LawRepoManager, "sync", return_value=True) as mock_sync:
                api = CanadianLawsAPI(str(temp_dir / "test_storage"))
                result = api.sync()

                mock_sync.assert_called_once()
                assert result is True

    def test_get_acts_path(self, temp_dir, mock_git_repo):
        """Test getting acts path through API."""
        with patch.object(LawRepoManager, "_initialize_repo"):
            api = CanadianLawsAPI(str(mock_git_repo))
            api.repo_manager.storage_path = mock_git_repo

            acts_path = api.get_acts_path()
            assert acts_path == mock_git_repo / "eng" / "acts"

    def test_get_regulations_path(self, temp_dir, mock_git_repo):
        """Test getting regulations path through API."""
        with patch.object(LawRepoManager, "_initialize_repo"):
            api = CanadianLawsAPI(str(mock_git_repo))
            api.repo_manager.storage_path = mock_git_repo

            regs_path = api.get_regulations_path()
            assert regs_path == mock_git_repo / "eng" / "regulations"

    def test_list_all_acts(self, temp_dir, mock_git_repo):
        """Test listing all acts."""
        with patch.object(LawRepoManager, "_initialize_repo"):
            api = CanadianLawsAPI(str(mock_git_repo))
            api.repo_manager.storage_path = mock_git_repo

            acts = api.list_all_acts()
            assert len(acts) == 2
            assert all(act.suffix == ".xml" for act in acts)

    def test_list_all_regulations(self, temp_dir, mock_git_repo):
        """Test listing all regulations."""
        with patch.object(LawRepoManager, "_initialize_repo"):
            api = CanadianLawsAPI(str(mock_git_repo))
            api.repo_manager.storage_path = mock_git_repo

            regs = api.list_all_regulations()
            assert len(regs) == 1
            assert all(reg.suffix == ".xml" for reg in regs)

    def test_get_statistics(self, temp_dir, mock_git_repo):
        """Test getting statistics."""
        Repo.init(str(mock_git_repo))

        with patch.object(LawRepoManager, "_initialize_repo"):
            api = CanadianLawsAPI(str(mock_git_repo))
            api.repo_manager.storage_path = mock_git_repo
            api.repo_manager.repo = Repo(str(mock_git_repo))

            stats = api.get_statistics()

            assert "files" in stats
            assert stats["files"]["acts"] == 2
            assert stats["files"]["regulations"] == 1
            assert stats["files"]["total"] == 3
            assert "repository" in stats

    def test_list_acts_nonexistent_directory(self, temp_dir):
        """Test listing acts when directory doesn't exist."""
        with patch.object(LawRepoManager, "_initialize_repo"):
            api = CanadianLawsAPI(str(temp_dir / "nonexistent"))
            api.repo_manager.storage_path = temp_dir / "nonexistent"

            acts = api.list_all_acts()
            assert acts == []


# ============================================================================
# Daemon Tests
# ============================================================================


class TestLawLibraryDaemon:
    """Test suite for LawLibraryDaemon class."""

    def test_daemon_init(self):
        """Test daemon initialization."""
        mock_laws = MagicMock()
        daemon = LawLibraryDaemon(mock_laws)

        assert daemon.laws == mock_laws
        assert daemon.running is False
        assert daemon.thread is None
        assert daemon.last_sync is None

    def test_daemon_start(self):
        """Test starting the daemon."""
        mock_laws = MagicMock()
        daemon = LawLibraryDaemon(mock_laws)

        daemon.start()

        assert daemon.running is True
        assert daemon.thread is not None
        assert daemon.thread.is_alive()

        # Cleanup
        daemon.stop()

    def test_daemon_stop(self):
        """Test stopping the daemon."""
        mock_laws = MagicMock()
        daemon = LawLibraryDaemon(mock_laws)

        daemon.start()
        time.sleep(0.1)  # Let it start
        daemon.stop()

        assert daemon.running is False
        # Thread should terminate
        time.sleep(0.2)
        assert not daemon.thread.is_alive()

    def test_daemon_sync_called(self):
        """Test that daemon calls sync method."""
        mock_laws = MagicMock()
        mock_laws.sync = MagicMock(return_value=True)

        daemon = LawLibraryDaemon(mock_laws)

        # Mock the sleep to exit quickly
        with patch("time.sleep") as mock_sleep:
            # First sleep (after sync) -> continue, second sleep -> stop daemon
            mock_sleep.side_effect = [None, Exception("Stop daemon")]

            daemon.start()

            try:
                time.sleep(0.5)  # Give daemon time to run
            except:
                pass

            daemon.stop()

            # Verify sync was called
            assert mock_laws.sync.called

    def test_daemon_double_start(self):
        """Test that starting an already running daemon does nothing."""
        mock_laws = MagicMock()
        daemon = LawLibraryDaemon(mock_laws)

        daemon.start()
        first_thread = daemon.thread

        daemon.start()  # Should do nothing
        second_thread = daemon.thread

        assert first_thread == second_thread  # Same thread

        daemon.stop()


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for the complete system."""

    def test_full_workflow(self, temp_dir, mock_git_repo):
        """Test the complete workflow: init -> sync -> index -> search."""
        # Initialize git repo
        Repo.init(str(mock_git_repo))

        with patch.object(Repo, "clone_from") as mock_clone:
            mock_clone.return_value = Repo(str(mock_git_repo))

            # 1. Initialize API
            api = CanadianLaws(str(mock_git_repo))

            # 2. Get paths
            acts_path = api.get_acts_path()
            regs_path = api.get_regulations_path()

            assert acts_path.exists()
            assert regs_path.exists()

            # 3. List laws
            acts = api.list_all_acts()
            regulations = api.list_all_regulations()

            assert len(acts) == 2
            assert len(regulations) == 1

            # 4. Get statistics
            stats = api.get_statistics()
            assert stats["files"]["total"] == 3

    def test_error_handling_invalid_xml(self, temp_dir):
        """Test that system handles invalid XML gracefully."""
        db_path = temp_dir / "test_laws.db"
        indexer = LawIndexer(str(db_path))

        # Create invalid XML
        invalid_dir = temp_dir / "invalid_xml"
        invalid_dir.mkdir()
        (invalid_dir / "bad.xml").write_text("Not valid XML at all!")

        # Should not crash
        count = indexer.index_directory(invalid_dir, "Act")
        assert count == 0  # No valid files indexed

    def test_concurrent_database_access(self, temp_dir, mock_git_repo):
        """Test that multiple threads can access the database safely."""
        db_path = temp_dir / "test_laws.db"
        indexer = LawIndexer(str(db_path))

        acts_path = mock_git_repo / "eng" / "acts"
        regs_path = mock_git_repo / "eng" / "regulations"
        indexer.rebuild_index(acts_path, regs_path)

        results = []

        def search_thread():
            """Search in a separate thread."""
            result = indexer.search("Test")
            results.append(len(result))

        # Run multiple searches concurrently
        threads = [threading.Thread(target=search_thread) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should get same results
        assert all(r == 3 for r in results)


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_directory(self, temp_dir):
        """Test indexing an empty directory."""
        db_path = temp_dir / "test_laws.db"
        indexer = LawIndexer(str(db_path))

        empty_dir = temp_dir / "empty"
        empty_dir.mkdir()

        count = indexer.index_directory(empty_dir, "Act")
        assert count == 0

    def test_xml_without_title(self, temp_dir):
        """Test parsing XML without a title element."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Statute>
    <Section>
        <Text>No title in this document</Text>
    </Section>
</Statute>"""
        xml_path = temp_dir / "notitle.xml"
        xml_path.write_text(xml_content, encoding="utf-8")

        db_path = temp_dir / "test_laws.db"
        indexer = LawIndexer(str(db_path))

        result = indexer._parse_xml_file(xml_path)
        # Should still parse, using filename as title
        assert result is not None
        assert result["id"] == "notitle"

    def test_special_characters_in_title(self, temp_dir):
        """Test handling special characters in titles."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Statute>
    <Title>Test & Title with "quotes" and 'apostrophes'</Title>
</Statute>"""
        xml_path = temp_dir / "special.xml"
        xml_path.write_text(xml_content, encoding="utf-8")

        db_path = temp_dir / "test_laws.db"
        indexer = LawIndexer(str(db_path))

        result = indexer._parse_xml_file(xml_path)
        assert result is not None
        assert "&" in result["title"]

    def test_large_number_of_files(self, temp_dir):
        """Test indexing a large number of files."""
        db_path = temp_dir / "test_laws.db"
        indexer = LawIndexer(str(db_path))

        large_dir = temp_dir / "large"
        large_dir.mkdir()

        # Create 100 XML files
        for i in range(100):
            create_sample_xml(large_dir / f"law-{i}.xml", f"Law {i}", "Act")

        count = indexer.index_directory(large_dir, "Act")
        assert count == 100

        # Verify all are in database
        counts = indexer.get_law_count()
        assert counts["total"] == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
