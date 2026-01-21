# Canadian Law Library

A comprehensive system for syncing and searching Canadian federal laws from the official Department of Justice repository.

## Features

- **Automatic Synchronization**: Syncs with the official Government of Canada laws repository every 4 hours
- **Fast SQLite Indexing**: Instant search across thousands of Acts and Regulations
- **High-Level API**: Simple Python interface for law lookup and search
- **Background Daemon**: Non-blocking sync process that runs in the background
- **Interactive Shell**: Built-in command-line interface for exploring laws

## Installation

```bash
# Install dependencies
uv pip install gitpython lxml

# Or if using pip
pip install gitpython lxml
```

## Quick Start

### Basic Usage

```python
from law_library import CanadianLaws

# Initialize the library (automatically clones repo and builds index on first run)
laws = CanadianLaws()

# Search for laws
results = laws.search("Privacy")
for law in results:
    print(f"{law['id']}: {law['title']} ({law['type']})")

# Get full law content
law = laws.get_law(law_id="A-1")
print(law['title'])
print(law['content'][:500])  # First 500 chars of XML

# Find regulations related to an Act
regs = laws.list_regulations_for_act("Access to Information")
for reg in regs:
    print(f"{reg['id']}: {reg['title']}")
```

### Interactive Shell

Run the main program to start an interactive shell with automatic syncing:

```bash
cd testing/approved/acts
python main.py
```

Available commands:
- `search <query>` - Search for laws by title
- `acts <query>` - Search only Acts
- `regulations <query>` - Search only Regulations
- `get <id>` - Get full details for a law by ID
- `related <act_name>` - Find regulations related to an Act
- `stats` - Show library statistics
- `sync` - Manually trigger a sync with remote
- `help` - Show help message
- `quit` - Exit

## Architecture

### Components

1. **LawRepoManager** (`repo_manager.py`)
   - Manages Git operations (clone, fetch, pull)
   - Handles network errors and merge conflicts
   - Provides paths to Acts and Regulations directories

2. **LawIndexer** (`indexer.py`)
   - Parses XML files and extracts metadata
   - Builds and maintains SQLite database index
   - Provides fast fuzzy search capabilities

3. **CanadianLaws** (`api.py`)
   - High-level user-facing API
   - Coordinates repo manager and indexer
   - Handles sync-triggered re-indexing

4. **LawLibraryDaemon** (`main.py`)
   - Background thread for 4-hour sync cycles
   - Interactive command shell
   - Logging and error handling

### Data Storage

```
testing/approved/acts/
├── law_library/          # Python package
│   ├── __init__.py
│   ├── api.py
│   ├── indexer.py
│   └── repo_manager.py
├── assets/
│   └── justice_laws_xml/ # Git repository clone
│       ├── eng/
│       │   ├── acts/     # ~600 XML files
│       │   └── regulations/ # ~2000+ XML files
│       └── fra/          # French XML files
├── laws.db              # SQLite index
├── law_library.log      # Application logs
└── main.py              # Entry point
```

## Performance

- **Search**: ~0.01s (SQLite indexed)
- **Initial Clone**: ~2-5 minutes (depends on network)
- **Index Build**: ~30-60 seconds for ~2600 laws
- **Sync Check**: ~2-5 seconds
- **Sync Pull**: ~30 seconds (if updates available)

## Error Handling

The system includes robust error handling for:
- Network interruptions during Git operations
- Merge conflicts (logs error, requires manual resolution)
- Invalid XML files (logs warning, skips file)
- Database errors (logs error, continues processing)

## Logging

Logs are written to both:
- Console (INFO level)
- `law_library.log` file (INFO level)

To adjust log level:
```python
import logging
logging.getLogger('law_library').setLevel(logging.DEBUG)
```

## Requirements

- Python 3.10+
- GitPython
- lxml (for XML parsing)
- SQLite3 (built-in)

## Repository

Official source: [https://github.com/justicecanada/laws-lois-xml](https://github.com/justicecanada/laws-lois-xml)

## License

This tool is for accessing public domain Canadian federal laws. The official law repository is maintained by the Department of Justice Canada.
