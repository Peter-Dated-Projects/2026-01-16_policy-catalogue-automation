# Legislative Stage State Machine

The bill tracking system now includes a comprehensive state machine that tracks bills through the Canadian legislative process.

## BillStage Enum

```python
class BillStage(Enum):
    FIRST_READING = "First Reading"
    SECOND_READING = "Second Reading"
    COMMITTEE = "Committee"
    REPORT_STAGE = "Report Stage"
    THIRD_READING = "Third Reading"
    PASSED_HOUSE = "Passed House"
    SENATE_STAGES = "Senate Stages"
    ROYAL_ASSENT = "Royal Assent"
    DEFEATED = "Defeated"
    UNKNOWN = "Unknown"
```

## Stage Transition Logic

The `determine_stage_transition()` method implements logic-first stage detection:

### 1. New Bill Detection
- **Trigger**: Empty history
- **Action**: Default to `FIRST_READING`

### 2. Chamber Switch Detection
- **Trigger**: Chamber changes from previous state
- **From House → Senate**: Transition to `SENATE_STAGES`
- **From Senate → House**: Transition to `PASSED_HOUSE`
- **Logging**: `📨 Bill {id} moved to Senate/House`

### 3. Final Stages

#### Royal Assent
- **Trigger**: Status contains "royal assent" OR `royal_assent_date` is set
- **Stage**: `ROYAL_ASSENT`
- **Note**: Bill becomes law

#### Defeated/Withdrawn
- **Trigger**: Status contains "defeated", "withdrawn", or "not proceeded"
- **Stage**: `DEFEATED`

### 4. Reading Stages

#### Third Reading
- **Trigger**: Status contains "third reading"
- **Stage**: `THIRD_READING`

#### Second Reading
- **Trigger**: Status contains "second reading"
- **Stage**: `SECOND_READING`

#### First Reading
- **Trigger**: Status contains "first reading" or "introduced"
- **Stage**: `FIRST_READING`

### 5. Critical Amendment Detection (Report Stage)

**This is the most important stage for text change detection.**

- **Trigger**: Status contains "report stage" or "report"
- **Stage**: `REPORT_STAGE`
- **Amendment Detection**:
  - Compares `new_publication_count` with stored `publication_count`
  - If count increased → `text_changed = True`
  - Logs: `📝 Amendment detected for {id}: Publications {old} → {new}`

#### Why Publication Count?

Publications in the LEGISinfo XML represent different versions of the bill text:
- **First Reading**: Initial publication
- **After Committee**: Amended publication (if changes made)
- **Report Stage**: Additional publication (if amendments)

**Tracking publication count is the reliable trigger for running expensive diff operations.**

### 6. Committee Stage
- **Trigger**: Status contains "committee"
- **Stage**: `COMMITTEE`

### 7. Fallback
- **Trigger**: None of the above match
- **Action**: Keep current stage (no false transitions)

## State Machine Features

### Enhanced Tracking

Each `BillState` now includes:

```python
@dataclass(frozen=True)
class BillState:
    status_code: str
    status_text: str
    timestamp: str
    chamber: str
    text_url: str
    stage: Optional[str] = None          # BillStage enum name
    text_changed: bool = False            # Amendment flag
```

### Bill Class Properties

```python
class Bill:
    current_stage: str                    # Current BillStage enum name
    publication_count: int                # For amendment detection
```

## State Transitions Return Values

```python
(new_stage: BillStage, text_changed: bool)
```

- **new_stage**: The determined legislative stage
- **text_changed**: `True` if bill text was amended (triggers diff engine)

## Enhanced Logging

### Stage Changes
```
⚠️  ALERT: Bill C-11 moved from 'At committee' → 'Report stage' [COMMITTEE → REPORT_STAGE]
```

### Amendment Detection
```
📝 Amendment detected for C-11: Publications 2 → 3
📝 AMENDMENT: Bill C-11 text changed at Report Stage
```

### Chamber Switches
```
📨 Bill C-11 moved to Senate
```

## Database Schema

Stage information is persisted in the database:

```json
{
  "bill_id": "C-11",
  "current_stage": "COMMITTEE",
  "publication_count": 2,
  "history": [
    {
      "status_text": "At consideration in committee",
      "stage": "COMMITTEE",
      "text_changed": false,
      "timestamp": "2026-01-19T10:00:00"
    },
    {
      "status_text": "Report stage",
      "stage": "REPORT_STAGE",
      "text_changed": true,
      "timestamp": "2026-01-19T12:00:00"
    }
  ]
}
```

## Usage Examples

### Detect Stage Transitions

```python
# In the update() method:
new_stage, text_changed = self.determine_stage_transition(
    status_text="Report stage",
    chamber="House of Commons",
    new_publication_count=3
)

if text_changed:
    # Trigger expensive diff operation
    run_text_diff_analysis()
```

### Query Bills by Stage

```python
# Find all bills in committee
committee_bills = [
    bill for bill in tracker.bills.values()
    if bill.current_stage == BillStage.COMMITTEE.name
]

# Find bills that have been amended
amended_bills = [
    bill for bill in tracker.bills.values()
    if any(state.text_changed for state in bill.history)
]
```

### Track Stage History

```python
for bill in tracker.bills.values():
    stages_visited = [state.stage for state in bill.history]
    print(f"{bill.bill_id}: {' → '.join(stages_visited)}")
```

## Benefits of the State Machine

### 1. **Accurate Stage Tracking**
- No guessing based on vague status text
- Explicit logic for each transition

### 2. **Amendment Detection**
- Publication count comparison is reliable
- Prevents false positives from status text alone

### 3. **Chamber Handling**
- Correctly identifies when bills move between chambers
- Distinguishes Senate's First Reading from new bills

### 4. **Performance Optimization**
- `text_changed` flag controls expensive diff operations
- Only analyze text when necessary

### 5. **Historical Analysis**
- Full stage history preserved
- Can analyze typical legislative timelines

## Typical Bill Flow

### House of Commons Bill
```
FIRST_READING → SECOND_READING → COMMITTEE → REPORT_STAGE* → 
THIRD_READING → PASSED_HOUSE → SENATE_STAGES → ROYAL_ASSENT
```

*Text may change at Report Stage (amendments)

### Senate Bill
```
FIRST_READING → SECOND_READING → COMMITTEE → REPORT_STAGE* → 
THIRD_READING → PASSED_HOUSE (to Commons) → ROYAL_ASSENT
```

### Private Member's Bill (often dies in Committee)
```
FIRST_READING → SECOND_READING → COMMITTEE → DEFEATED
```

## Future Enhancements

Potential additions:
- Sub-stages within Committee (hearings, clause-by-clause)
- Vote tracking (majority, opposition votes)
- Time-in-stage analytics
- Prediction model for bill success probability
- Automatic text diff triggering when `text_changed=True`
