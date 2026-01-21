# Canadian Federal Regulation Tracker

A robust Python system for tracking the lifecycle of Canadian Federal Regulations from the Canada Gazette RSS feeds.

## Overview

The Canada Gazette is the official newspaper of the Canadian government where regulations are published:
- **Part I**: Proposed regulations (Consultation phase)
- **Part II**: Enacted regulations (Official Laws)

This tracker monitors both feeds, extracts metadata, and maintains a persistent history of all regulations.

## Features

✅ **Automated Data Collection**
- Fetches regulations from both Part I (proposed) and Part II (enacted) RSS feeds
- Polls every 24 hours to catch new publications

✅ **Smart Metadata Extraction**
- Regulation IDs (SOR/YYYY-NNN or SI/YYYY-NNN)
- Sponsor departments/entities
- Enabling Acts
- Publication dates in ISO 8601 format
- Direct links to full text

✅ **Persistent Storage**
- Saves data to `assets/data.json`
- Merges new data with existing records
- Automatic deduplication
- Never loses history

✅ **Robust Error Handling**
- Comprehensive logging
- Graceful handling of malformed feeds
- Continues operation even if individual entries fail

## Installation

### Prerequisites
- Python 3.7+
- Virtual environment (recommended)

### Install Dependencies

```bash
# Install required packages
pip install feedparser schedule

# Or if using the workspace's virtual environment:
source /path/to/.venv/bin/activate
pip install feedparser schedule
```

## Usage

### Run Once (Single Scan)

```bash
cd /path/to/testing/regulation
python main.py
```

By default, the script runs in scheduled mode (continuous polling every 24 hours). To run a single scan and exit, modify the `main()` function:

```python
def main():
    tracker = RegulationTracker(data_file="assets/data.json")
    tracker.run_once()  # Run once and exit
```

### Run Continuously (Scheduled Mode)

```bash
python main.py
```

This will:
1. Run an initial scan immediately
2. Schedule scans every 24 hours
3. Continue running until interrupted (Ctrl+C)

### Programmatic Usage

```python
from main import RegulationTracker

# Initialize tracker
tracker = RegulationTracker(data_file="assets/data.json")

# Run a single scan
tracker.scan_gazette()

# Access regulations
for reg in tracker.regulations:
    print(f"{reg.regulation_name} - Stage: {reg.stage}")
    if reg.regulation_id:
        print(f"  ID: {reg.regulation_id}")
    if reg.sponsor:
        print(f"  Sponsor: {reg.sponsor}")
```

## Data Structure

Each regulation is stored with the following fields:

```json
{
  "regulation_name": "Clean human-readable title",
  "regulation_id": "SOR/2024-12",
  "date_published": "2024-01-15T19:00:00",
  "stage": "PROPOSED",
  "sponsor": "Department of Health",
  "enabling_act": "Food and Drugs Act",
  "links": "https://gazette.gc.ca/...",
  "raw_title": "Original full title from RSS"
}
```

### Field Descriptions

| Field | Description | Example |
|-------|-------------|---------|
| `regulation_name` | Cleaned title without bureaucratic prefixes | `"Food and Drug Regulations"` |
| `regulation_id` | Unique identifier (may be null for Part I) | `"SOR/2024-12"` or `"SI/2024-5"` |
| `date_published` | ISO 8601 timestamp | `"2024-01-15T19:00:00"` |
| `stage` | Lifecycle stage | `"PROPOSED"` or `"ENACTED"` |
| `sponsor` | Requesting department/entity | `"Department of Health"` |
| `enabling_act` | Parent legislation | `"Food and Drugs Act"` |
| `links` | URL to full text | `"https://gazette.gc.ca/..."` |
| `raw_title` | Original unprocessed title | Full title from feed |

## Polling Strategy

The system polls **every 24 hours** because:
- Part I publishes every Saturday
- Part II publishes every second Wednesday
- Daily checks ensure we catch all updates without overwhelming the server

## File Structure

```
testing/regulation/
├── main.py              # Main tracker implementation
├── README.md            # This file
└── assets/
    └── data.json        # Persistent regulation database
```

## Logging

The system logs all operations with timestamps:
```
2026-01-21 10:17:02 - INFO - Starting Gazette scan...
2026-01-21 10:17:03 - INFO - Found new regulation: Food and Drug Regulations [SOR/2024-12]
2026-01-21 10:17:04 - INFO - ✓ Scan complete. Found 2 new regulation(s).
```

## Error Handling

- **Feed parsing errors**: Logged but don't stop execution
- **Individual entry errors**: Skipped with logging
- **Date parsing failures**: Falls back to current timestamp
- **Missing metadata**: Stored as `null` for optional fields

## Testing

Initial test results:
- ✅ Successfully scanned both Part I and Part II feeds
- ✅ Found 606 historical regulations
- ✅ Created `assets/data.json` with proper structure
- ✅ Metadata extraction working (sponsor, links, dates)

## Future Enhancements

Potential improvements:
- Add email/webhook notifications for new regulations
- Export to CSV/Excel formats
- Web dashboard for visualization
- Filter by department or Act
- Track regulation amendments and changes
- Historical trend analysis

## License

This tool is for educational and research purposes.

## Data Sources

- Part I Feed: https://gazette.gc.ca/rss/p1-eng.xml
- Part II Feed: https://gazette.gc.ca/rss/p2-eng.xml

---

**Questions or Issues?**
Check the logs for detailed information about system operation and any errors encountered.
