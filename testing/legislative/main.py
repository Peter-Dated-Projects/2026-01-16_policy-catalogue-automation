# legislative law


import requests
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class BillState:
    bill_id: str  # e.g., "C-11"
    session: str  # e.g., "44-1"
    title: str
    status_id: (
        int  # LEGISinfo uses distinct IDs for statuses (e.g., 100 = First Reading)
    )
    status_text: str  # "Second Reading"
    chamber: str  # "House of Commons" or "Senate"
    last_updated: datetime
    xml_url: str  # URL to detailed XML


class Bill:
    def __init__(self, session: str, bill_id: str, title: str):
        self.session = session  # e.g., "44-1"
        self.bill_id = bill_id  # e.g., "C-11"
        self.title = title

        # The Ledger: Stores every state transition in order
        self._history: List[BillState] = []

        # Metadata
        self.sponsor: Optional[str] = None
        self.last_scanned: datetime = datetime.now()

    @property
    def current_state(self) -> Optional[BillState]:
        """Returns the most recent state or None if new."""
        return self._history[-1] if self._history else None

    def update(
        self,
        new_status_code: str,
        new_status_text: str,
        text_url: str,
        event_date: datetime,
        chamber: str = "House",
    ):
        """
        The Core Logic: Only updates if the state has arguably changed.
        """
        self.last_scanned = datetime.now()

        # 1. Check if this is actually a new state
        if self.current_state and self.current_state.status_code == new_status_code:
            # OPTIONAL: Check if text changed even if status didn't (Silent Amendment)
            # This is where you'd compare text_hashes if you implemented that.
            return False

        # 2. Create the new Snapshot
        new_state = BillState(
            status_code=new_status_code,
            status_text=new_status_text,
            timestamp=event_date,
            chamber=chamber,
            text_url=text_url,
        )

        # 3. Append to Ledger
        self._history.append(new_state)
        print(f"[{self.bill_id}] Transitioned to: {new_status_text}")
        return True

    def get_time_in_stage(self) -> str:
        """Calculates how long the bill has been stagnating in current state."""
        if not self.current_state:
            return "N/A"
        delta = datetime.now() - self.current_state.timestamp
        return f"{delta.days} days"

    def to_dict(self):
        """Serialization for your Database/JSON file."""
        return {
            "id": f"{self.session}-{self.bill_id}",
            "title": self.title,
            "history": [asdict(state) for state in self._history],
        }


LEGIS_URL = "https://www.parl.ca/legisinfo/en/bills/xml"


def fetch_current_bills():
    """Fetches and parses the master bill list."""
    response = requests.get(LEGIS_URL)
    response.raise_for_status()

    root = ET.fromstring(response.content)
    current_state = {}

    # XML Namespace handling (LEGISinfo usually has a namespace)
    # For simplicity here, we assume direct tag access or strip namespaces
    for bill in root.findall(".//Bill"):
        bill_id = bill.find("NumberCode").text
        session = bill.find("Session").text
        unique_key = f"{session}-{bill_id}"

        current_state[unique_key] = {
            "id": bill_id,
            "session": session,
            "status_id": int(bill.find("CurrentStatus/Id").text),
            "status_text": bill.find("CurrentStatus/Name").text,
            "updated": bill.find("LastUpdated").text,
            "detail_url": f"https://www.parl.ca/legisinfo/en/bill/{session}/{bill_id}/xml",
        }

    return current_state


if __name__ == "__main__":
    print("This is the legislative law module.")
