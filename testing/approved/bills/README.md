# Canadian Legislative Bill Tracker

A Python system for monitoring Canadian Parliament bills via the LEGISinfo API. Tracks bill status changes, maintains historical data, and provides analytics tools.

## Overview

This system consists of three main components:
- **Bill Tracker** (`main.py`): Daemon that polls the LEGISinfo API and maintains a persistent database of all bills
- **Bill Lookup** (`bill_lookup.py`): Query tool for viewing detailed information about specific bills
- **Bill Analytics** (`bill_analytics.py`): Analysis tool for aggregating statistics across bills

The tracker monitors bills from Parliament 35 (1994) onwards and stores data in a JSON database at `assets/data.json`.

## Core Functionality

### Tracking System
- Polls LEGISinfo API every 4 hours for status changes
- Maintains complete history of bill status transitions
- Classifies bills by type (Government, Private Member's, Senate)
- Tracks lifecycle stages (First Reading → Royal Assent)
- Detects Royal Assent and Coming-into-Force status
- Flags bills that died on Order Paper

### Analytics & Queries
- Look up individual bills by ID (e.g., `C-11`, `S-2`)
- View sponsor analysis and political weight
- Track activity timelines and stale bills
- Analyze Royal Assent patterns and chapter citations
- Generate summaries by stage, chamber, and status

## File Structure

```
testing/legislative/
├── main.py              # Bill tracking daemon
├── bill_lookup.py       # Query tool for individual bills
├── bill_analytics.py    # Aggregate analytics
├── utils.py             # Shared utility functions
└── assets/
    └── data.json        # Persistent bill database
```

## Usage

### Start the Tracker

```bash
# Run with automatic historical fetch (first time)
python testing/legislative/main.py

# Skip historical fetch (faster startup)
python testing/legislative/main.py --no-historical

# Force re-fetch all historical data
python testing/legislative/main.py --force-historical
```

The daemon will run continuously until interrupted (Ctrl+C).

### Query Bills

```bash
# Look up specific bills
python testing/legislative/bill_lookup.py C-11
python testing/legislative/bill_lookup.py S-2 C-234

# View analytics
python testing/legislative/bill_analytics.py
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
