"""
Canadian Law Library - Storage System
Runs background sync and maintains local law repository
"""

import logging
import threading
import time
import sys
from datetime import datetime
from law_library import CanadianLaws

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("law_library.log"),
    ],
)

logger = logging.getLogger(__name__)

# Sync interval (4 hours in seconds)
SYNC_INTERVAL = 4 * 60 * 60


class LawLibraryDaemon:
    """
    Background daemon that syncs the law repository every 4 hours.
    """

    def __init__(self, laws: CanadianLaws):
        self.laws = laws
        self.running = False
        self.thread = None
        self.last_sync = None

    def _sync_loop(self):
        """Main sync loop that runs in background thread."""
        logger.info("Starting background sync daemon...")

        while self.running:
            try:
                logger.info("Running scheduled sync...")
                self.laws.sync()
                self.last_sync = datetime.now()
                logger.info(f"Sync completed at {self.last_sync}")

                # Wait for next sync interval
                time.sleep(SYNC_INTERVAL)

            except Exception as e:
                logger.error(f"Error in sync loop: {e}")
                # Wait a bit before retrying on error
                time.sleep(60)

    def start(self):
        """Start the background sync daemon."""
        if self.running:
            logger.warning("Daemon already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._sync_loop, daemon=True)
        self.thread.start()
        logger.info("Background sync daemon started (syncs every 4 hours)")

    def stop(self):
        """Stop the background sync daemon."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Background sync daemon stopped")


def main():
    """Main entry point - Initialize storage system and keep it running."""
    logger.info("Starting Canadian Law Library Storage System...")

    try:
        # Initialize the law library
        laws = CanadianLaws()

        # Show initial statistics
        stats = laws.get_statistics()
        logger.info(f"Library initialized with {stats['laws']['total']} laws")
        logger.info(f"  Acts: {stats['laws']['acts']}")
        logger.info(f"  Regulations: {stats['laws']['regulations']}")

        # Start background sync daemon
        daemon = LawLibraryDaemon(laws)
        daemon.start()

        logger.info("Storage system is running. Press Ctrl+C to stop.")

        # test search
        print(laws.search("Access to Information"))

        # Keep the main thread alive while daemon runs
        while True:
            time.sleep(60)

    except KeyboardInterrupt:
        logger.info("Shutting down storage system...")
        if "daemon" in locals():
            daemon.stop()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
