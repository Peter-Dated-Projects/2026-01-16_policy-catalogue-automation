# 🏛️ Canadian Legislative Bill Tracker

A production-ready Python daemon that continuously monitors Canadian Parliament bills via the LEGISinfo API, detecting and logging all status changes with complete historical tracking.

## ✨ Features

- **Persistent Daemon**: Runs continuously, polling every 4 hours
- **Historical Tracking**: Automatically fetches all bills from Parliaments 35-44 (1994-present) on first run
- **Change Detection**: Only alerts when bill status actually changes
- **Complete History**: Maintains immutable audit trail of all status transitions
- **Crash Recovery**: Loads previous state on restart—no duplicate alerts
- **Error Resilient**: Handles network failures gracefully, retries automatically
- **Type-Safe**: Fully type-hinted with modern Python best practices
- **Flexible Configuration**: Command-line options to control historical fetching

## 🏗️ Architecture

### Core Classes

#### `BillState` (Frozen Dataclass)
Immutable snapshot of a bill at a specific moment:
```python
@dataclass(frozen=True)
class BillState:
    status_code: str
    status_text: str
    timestamp: str
    chamber: str
    text_url: str
```

#### `Bill` (Class)
Represents a single piece of legislation:
```python
class Bill:
    session: str          # e.g., "44-1"
    bill_id: str          # e.g., "C-11"
    title: str
    history: List[BillState]
    
    def update(...) -> bool:  # Returns True if changed
    def to_dict() -> Dict:    # JSON serialization
```

#### `BillTracker` (Daemon Manager)
Orchestrates polling, persistence, and change detection:
- Loads/saves from `legislation/bills_db.json`
- Fetches XML from LEGISinfo API
- Detects changes and logs alerts

## 📁 File Structure

```
testing/legislative/
├── main.py              # Complete tracking system
├── README.md            # This file
└── ../../legislation/   # Storage directory (auto-created)
    └── bills_db.json    # Persistent state database
```

## 🚀 Usage

### Running the Daemon

```bash
# Start tracking (runs forever until Ctrl+C)
# On first run, automatically fetches all historical bills (1-2 minutes)
python testing/legislative/main.py

# Or with UV
uv run testing/legislative/main.py

# Skip historical fetch (faster startup, current bills only)
python testing/legislative/main.py --no-historical

# Force re-fetch all historical bills (even if database exists)
python testing/legislative/main.py --force-historical
```

### Expected Output

**First Run (with historical fetch):**
```
2026-01-19 00:29:56 - INFO - No existing database found. Starting fresh.
2026-01-19 00:29:56 - INFO - Will perform initial historical bill fetch...
2026-01-19 00:29:56 - INFO - ============================================================
2026-01-19 00:29:56 - INFO - HISTORICAL BILL FETCH - This may take several minutes...
2026-01-19 00:29:56 - INFO - ============================================================
2026-01-19 00:29:56 - INFO - Fetching Parliament 35-1...
2026-01-19 00:29:57 - INFO -   → Added 300 bills from 35-1
2026-01-19 00:29:58 - INFO - Fetching Parliament 35-2...
2026-01-19 00:29:59 - INFO -   → Added 358 bills from 35-2
...
2026-01-19 00:31:20 - INFO - Historical fetch complete: 6,234 bills added
2026-01-19 00:31:20 - INFO - ============================================================
```

**Subsequent Runs (daemon mode):**
```
2026-01-18 19:52:19 - INFO - Loaded 6,234 bills from database.
2026-01-18 19:52:19 - INFO - ============================================================
2026-01-18 19:52:19 - INFO - Canadian Legislative Bill Tracker - STARTED
2026-01-18 19:52:19 - INFO - Poll interval: 4 hours
2026-01-18 19:52:19 - INFO - ============================================================
2026-01-18 19:52:19 - INFO - Fetching current bills from LEGISinfo API...
2026-01-18 19:52:20 - INFO - 📝 New bill tracked: C-42 - Budget Implementation Act, 2026
2026-01-18 19:52:20 - INFO - Processed 127 bills. Changes detected: 0
2026-01-18 19:52:20 - INFO - Database saved with 6,361 bills.
2026-01-18 19:52:20 - INFO - Sleeping until next poll at 2026-01-18 23:52:20

# When changes occur:
2026-01-18 23:52:30 - INFO - ⚠️  ALERT: Bill C-11 moved from 'First Reading' -> 'Second Reading'
```

## 🔧 Configuration

Edit constants in [main.py](main.py):

```python
POLL_INTERVAL_HOURS = 4  # Polling frequency
HISTORICAL_PARLIAMENTS = list(range(35, 45))  # Parliaments 35-44 (1994-present)
STORAGE_DIR = Path("legislation")  # Where to save data
LEGIS_URL = "https://www.parl.ca/legisinfo/en/bills/xml"  # Data source
```

### Historical Parliament Coverage

The system tracks bills from:
- **Parliament 35** (1994-1997): ~658 bills
- **Parliament 36** (1997-2000): ~828 bills  
- **Parliament 37** (2000-2004): ~1,060 bills
- **Parliament 38** (2004-2006): ~395 bills
- **Parliament 39** (2006-2008): ~827 bills
- **Parliament 40** (2008-2011): ~1,027 bills
- **Parliament 41** (2011-2015): ~1,022 bills
- **Parliament 42** (2015-2019): ~441 bills
- **Parliament 43** (2019-2021): ~86 bills
- **Parliament 44** (2021-2025): Current session

**Total: ~6,000+ bills** tracked across 30+ years of Canadian legislative history.

## 📊 Data Persistence

### Database Schema (`bills_db.json`)

```json
{
  "last_updated": "2026-01-18T19:52:20.176369",
  "bills": [
    {
      "session": "44-1",
      "bill_id": "C-11",
      "title": "An Act to amend the Broadcasting Act",
      "history": [
        {
          "status_code": "FIRST_READING",
          "status_text": "First Reading",
          "timestamp": "2026-01-15T10:30:00",
          "chamber": "House of Commons",
          "text_url": "https://www.parl.ca/legisinfo/en/bill/44-1/C-11"
        },
        {
          "status_code": "SECOND_READING",
          "status_text": "Second Reading",
          "timestamp": "2026-01-18T14:20:00",
          "chamber": "House of Commons",
          "text_url": "https://www.parl.ca/legisinfo/en/bill/44-1/C-11"
        }
      ]
    }
  ]
}
```

### Key Benefits

- **Restart Safe**: Daemon loads previous state, avoiding false "new bill" alerts
- **Complete Audit Trail**: Every status change is preserved forever
- **Human Readable**: JSON format allows manual inspection/analysis

## 🛡️ Error Handling

The system handles:

1. **Network Failures**: Logs error, waits 5 minutes, retries
2. **Malformed XML**: Skips problematic bills, continues processing
3. **Missing Fields**: Uses safe defaults ("Unknown Status", etc.)
4. **Keyboard Interrupt**: Clean shutdown with final database save

## 📦 Dependencies

```python
# Standard library (built-in)
import json
import logging
import os
import time
import xml.etree.ElementTree
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

# External (requires installation)
import requests  # pip install requests
```

### Installation

```bash
pip install requests
# or
uv add requests
```

## 🧪 Testing the System

### Quick Test
```bash
# Run the test suite
python testing/legislative/test_historical.py
```

### 1. First Run (Fresh Start)
```bash
python testing/legislative/main.py
```
- Creates `legislation/` folder
- Fetches ~6,000+ historical bills (takes 1-2 minutes)
- Fetches all current bills
- Saves to `bills_db.json`
- Enters daemon mode (polls every 4 hours)

### 2. Second Run (Persistence Test)
Stop (Ctrl+C) and restart:
```bash
python testing/legislative/main.py
```
- Loads all 6,000+ bills from database instantly
- Should NOT alert about bills as "new"
- Only alerts if statuses changed since last poll

### 3. Fast Start (Skip Historical)
```bash
python testing/legislative/main.py --no-historical
```
- Starts immediately without historical fetch
- Only tracks current parliament bills

### 4. Force Refresh Historical Data
```bash
python testing/legislative/main.py --force-historical
```
- Re-fetches all historical bills
- Useful if LEGISinfo updates past bill information

## 🔍 Advanced Usage

### Query Bill History Programmatically

```python
import json

with open('legislation/bills_db.json') as f:
    data = json.load(f)

# Find a specific bill
for bill in data['bills']:
    if bill['bill_id'] == 'C-11':
        print(f"Bill: {bill['title']}")
        print(f"Status changes: {len(bill['history'])}")
        for state in bill['history']:
            print(f"  {state['timestamp']}: {state['status_text']}")
```

### Running as a System Service (Linux/macOS)

Create `legislative-tracker.service`:
```ini
[Unit]
Description=Canadian Legislative Bill Tracker
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/project
ExecStart=/usr/bin/python3 testing/legislative/main.py
Restart=on-failure
RestartSec=300

[Install]
WantedBy=multi-user.target
```

## 📝 Design Decisions

### Why Frozen Dataclasses for BillState?
Immutability ensures history cannot be accidentally modified, providing audit trail integrity.

### Why Load Before Poll?
Prevents the system from treating existing bills as "new" after every restart.

### Why 4-Hour Polling?
Balance between responsiveness and API courtesy. Canadian Parliament doesn't update bills every minute.

### Why JSON Storage?
- Human-readable for debugging
- No external database dependency
- Sufficient for typical legislative tracking scale
- Easy backup/version control

## 🚨 Known Limitations

1. **XML Schema Dependence**: If LEGISinfo changes their XML structure, parsing may fail
2. **Single Process**: Doesn't support distributed tracking (intentional simplicity)
3. **No Authentication**: API is currently public; may need auth if Parliament restricts access
4. **File-Based Storage**: For very large datasets (10,000+ bills with long histories), consider SQLite

## 📚 Resources

- **LEGISinfo XML Feed**: https://www.parl.ca/legisinfo/en/bills/xml
- **Parliament of Canada**: https://www.parl.ca/
- **Bill Status Workflow**: https://www.parl.ca/about/parliament/education/ourcountryourparliament/html_booklet/process-passing-bill-e.html

## 🤝 Contributing

To extend this system:

1. **Add More Data Points**: Extend `BillState` with sponsors, votes, committee assignments
2. **Notifications**: Integrate email/Slack alerts in `Bill.update()`
3. **Web Dashboard**: Build Flask/FastAPI frontend reading `bills_db.json`
4. **Analytics**: Add matplotlib graphs of bill progression timelines

## 📄 License

This is a reference implementation for educational/governmental use.
