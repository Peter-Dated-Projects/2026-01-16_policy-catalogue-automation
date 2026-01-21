# Canadian Federal Regulation Tracker

A Python system for monitoring Canadian Federal Regulations from the Canada Gazette RSS feeds. Tracks both proposed and enacted regulations with automated polling.

## Overview

The Canada Gazette publishes regulations in two parts:
- **Part I**: Proposed regulations (consultation phase)
- **Part II**: Enacted regulations (official law)

This tracker monitors both RSS feeds, extracts structured metadata, and maintains a persistent database of regulations.

## Core Functionality

### Data Collection
- Fetches from Part I and Part II RSS feeds
- Polls every 24 hours for new publications
- Extracts regulation IDs (SOR/YYYY-NNN, SI/YYYY-NNN)
- Identifies sponsor departments
- Parses enabling acts
- Normalizes publication dates to ISO 8601 format

### Data Management
- Stores data in JSON format at `assets/data.json`
- Merges new data with existing records
- Automatic deduplication by regulation ID
- Preserves historical entries

## File Structure

```
testing/regulation/
├── main.py           # Regulation tracking daemon
└── assets/
    └── data.json     # Persistent regulation database
```

## Usage

### Run the Tracker

```bash
# Run continuously (polls every 24 hours)
python testing/regulation/main.py
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
