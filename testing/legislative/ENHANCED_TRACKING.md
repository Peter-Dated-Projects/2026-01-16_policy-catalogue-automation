# Enhanced Bill Tracking Features

The legislative tracking system now includes comprehensive tracking of bill metadata and timeline information.

## New Tracking Features

### 1. Days Since Last Activity

Each bill tracks its most recent activity date and automatically calculates days elapsed.

**Fields:**
- `last_activity_date`: ISO datetime of the last activity
- Calculated property: `days_since_last_activity`

**Use Cases:**
- Identify stalled bills
- Monitor active vs. inactive legislation
- Track legislative momentum

**Example:**
```python
bill = Bill(...)
print(f"Days since last activity: {bill.days_since_last_activity}")
```

### 2. Sponsor Information (Political Weight)

Track who sponsored each bill to analyze political influence and activity.

**Fields:**
- `sponsor`: Name of the bill sponsor (e.g., "Hon. Sean Fraser", "Sen. Kim Pate")
- `sponsor_affiliation`: Political affiliation ID

**Analysis:**
- Count bills per sponsor
- Track government vs. opposition sponsorship
- Identify most active legislators

**Top Sponsors (Current Data):**
- Gord Johns: 7 bills
- Sen. Kim Pate: 4 bills
- Jenny Kwan: 4 bills

### 3. Royal Recommendation

Indicates whether a bill has received a Royal Recommendation (required for bills affecting public funds).

**Field:**
- `has_royal_recommendation`: Boolean indicator

**Detection Logic:**
- Government bills automatically flagged
- Presence of Ministry ID in XML
- Bill type indicates government sponsorship

**Statistics:**
- 21 bills with Royal Recommendation (16.8%)
- 104 bills without (83.2%)

### 4. Royal Assent Status

Track when bills receive Royal Assent (become law).

**Fields:**
- `royal_assent_date`: ISO datetime when Royal Assent received
- Calculated property: `is_royal_assent_received`

**Current Status:**
- 7 bills have received Royal Assent
- 118 bills pending

**Recent Royal Assents:**
- C-17: 39 days ago
- C-3, S-1001: 60 days ago
- C-5, C-6, C-7, C-202: 207 days ago

### 5. Coming Into Force (CIF)

While not directly tracked in a separate field, this information can be inferred from:
- Royal Assent date (many bills come into force immediately upon Royal Assent)
- Status text may indicate "In force" status
- History timeline shows when bill became active law

## Database Schema

All new fields are stored in the JSON database:

```json
{
  "session": "45-1",
  "bill_id": "C-11",
  "title": "An Act to amend...",
  "bill_type": "Government Bill (House) - Amending",
  "sponsor": "Hon. David J. McGuinty",
  "sponsor_affiliation": "0",
  "royal_assent_date": null,
  "last_activity_date": "2025-12-10T10:25:29.053-05:00",
  "has_royal_recommendation": true,
  "history": [...]
}
```

## Analytics Tools

### Bill Analytics Script

Run comprehensive analytics:

```bash
uv run bill_analytics.py
```

**Features:**
- Activity timeline analysis
- Sponsor activity rankings
- Royal Recommendation breakdown
- Royal Assent status summary
- Detailed bill information

**Activity Categories:**
- **Active** (≤ 30 days): Bills with recent movement
- **Moderate** (31-90 days): Normal legislative pace
- **Stale** (91-180 days): Potentially delayed
- **Very Stale** (> 180 days): Long-dormant bills

### Bill Type Statistics

View bill type distribution:

```bash
uv run bill_type_stats.py
```

## API Fields Mapped

From LEGISinfo XML to our database:

| XML Field | Our Field | Description |
|-----------|-----------|-------------|
| `SponsorEn` | `sponsor` | Bill sponsor name |
| `PoliticalAffiliationId` | `sponsor_affiliation` | Political party ID |
| `ReceivedRoyalAssentDateTime` | `royal_assent_date` | Date of Royal Assent |
| `LatestActivityDateTime` | `last_activity_date` | Most recent activity |
| `MinistryId` + `BillTypeEn` | `has_royal_recommendation` | Royal Recommendation indicator |

## Use Cases

### 1. Monitor Bill Progress
Track which bills are actively moving through Parliament vs. stalled.

### 2. Political Analysis
Identify most active sponsors and their legislative priorities.

### 3. Timeline Analysis
Calculate average time from introduction to Royal Assent.

### 4. Alert System
Get notified when:
- Bills receive Royal Assent
- Stalled bills resume activity
- Specific sponsors introduce new legislation

### 5. Research
Historical analysis of legislative patterns and trends.

## Backward Compatibility

All new fields are optional and backward compatible:
- Existing databases automatically upgraded
- Missing fields default to `None` or `False`
- No data loss when loading older databases

## Future Enhancements

Potential additions:
- Committee assignments
- Vote counts and results
- Amendment tracking
- Full text change detection
- Email/webhook alerts for status changes
