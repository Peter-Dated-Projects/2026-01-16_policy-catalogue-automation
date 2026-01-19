# Bill Type Classification

The legislative tracking system now automatically classifies bills into different types based on their identifier and title.

## Classification Rules

### By Identifier (Bill Number)

| Type | Identifier Logic | Example |
|------|------------------|---------|
| **Government Bill (House)** | Starts with `C-` and number < 201 | C-11, C-18, C-200 |
| **Private Member's Bill** | Starts with `C-` and number > 200 | C-234, C-250, C-201 |
| **Senate Bill** | Starts with `S-` | S-5, S-201, S-1001 |

### By Title (Bill Purpose)

Bills are further classified by examining their title:

| Type | Title Pattern | Example |
|------|--------------|---------|
| **Amending Bill** | Contains "Act to amend..." | "An Act to amend the Criminal Code" |
| **New Act** | Contains "Act respecting..." | "An Act respecting cyber security" |

## Combined Classification

The system combines both identifier and title classifications, for example:
- `Government Bill (House) - Amending`: C-11 - "An Act to amend the Broadcasting Act"
- `Private Member's Bill - New Act`: C-234 - "An Act respecting farm heating"
- `Senate Bill - Amending`: S-5 - "An Act to amend the Environmental Protection Act"

## Usage

### Automatic Classification

When bills are fetched and tracked, they are automatically classified:

```python
bill = Bill(session="45-1", bill_id="C-11", title="An Act to amend...")
print(bill.bill_type)  # "Government Bill (House) - Amending"
```

### View Statistics

Run the statistics script to see the distribution of bill types:

```bash
uv run bill_type_stats.py
```

This will show:
- Total count by bill type
- Percentage distribution
- Example bills for each category

### Testing

To verify classification logic works correctly:

```bash
uv run test_bill_types.py
```

## Database Storage

Bill types are stored in the JSON database (`legislation/bills_db.json`):

```json
{
  "session": "45-1",
  "bill_id": "C-11",
  "title": "An Act to amend the Broadcasting Act",
  "bill_type": "Government Bill (House) - Amending",
  "history": [...]
}
```

## Implementation Details

The classification is performed by the static method `Bill.classify_bill_type()` in [main.py](main.py):

1. Extracts the bill prefix (C or S) and number using regex
2. Determines base category from identifier
3. Checks title for "Act to amend" or "Act respecting" patterns
4. Combines classifications with " - " separator if applicable

The classification is backward compatible - existing databases without `bill_type` will have it automatically added when loaded.
