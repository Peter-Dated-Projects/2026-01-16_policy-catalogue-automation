# 01-16-2026_policy-catalogue-automation
automates the cataloguing of government policy in canada


## Backend

The backend will host a bunch of microservices that will handle different aspects of the policy catalogue automation:

1. Data Collection + Ingestion Workflow
2. SQL Database
3. Document Storage
4. RAG Pipeline
5. Newsletter Generation Pipeline

## Frontend

This will display all of the policies in a user-friendly manner, allowing users to search, filter, and view policy details.

We'll also include stuff for testing/generating reports and newsletter emails.

## Testing Projects

### Legislative Bill Tracker
[View Documentation](testing/approved/legislative/README.md)

A Python system that monitors Canadian Parliament bills via the LEGISinfo API. Tracks bill status changes from Parliament 35 (1994) onwards, maintains historical data with complete status transition history, and provides analytics tools for viewing bill details, sponsor analysis, and Royal Assent patterns. Polls the API every 4 hours to detect changes across all lifecycle stages.

### Federal Regulation Tracker
[View Documentation](testing/approved/regulation/README.md)

A Python system that monitors Canadian Federal Regulations from the Canada Gazette RSS feeds. Tracks both proposed regulations (Part I) and enacted regulations (Part II), extracting structured metadata including regulation IDs, sponsor departments, enabling acts, and publication dates. Polls feeds every 24 hours and maintains a persistent JSON database of all regulations.