# Whiskey District Cashout Automation System

## Overview

The current end-of-day cashout process at Whiskey District is heavily manual. At the end of each shift, staff must reconcile information by hand across multiple sources, including:

- Paper cashout sheets
- Debit and credit machine reports
- Customer and discount receipts
- TouchBistro shift reports

This workflow introduces several recurring problems:

- Significant time spent on repetitive data entry
- Frequent human error during transcription and reconciliation
- Difficulty tracking discrepancies between sources
- Delayed investigation of inaccuracies, often days after the shift occurred

The goal of this system is to streamline end-of-day cashout processing by using OCR to extract data from physical documents and centralizing all shift information in a structured digital format. This reduces manual entry, improves accuracy, and shortens the feedback loop on discrepancies.

The long-term vision is for this tool to serve as the foundation of a broader internal operations platform for Whiskey District, expanding beyond cashouts into adjacent workflows over time.

## Current Workflow Summary

The existing cashout process generally follows these steps:

1. The server closes their shift in TouchBistro.
2. The server prints debit and credit machine reports.
3. The server prints the TouchBistro shift report.
4. The server compares slips, receipts, and report totals.
5. Discrepancies are investigated manually before leaving.
6. Tip-outs are calculated by hand.
7. The cashout bag is prepared and submitted.
8. Management later transcribes the contents of each cashout into spreadsheets.
9. Any discrepancies identified after the fact are investigated manually.

Cashout data ultimately flows into master spreadsheets and bookkeeping summaries used for ongoing financial tracking.

## Users & Roles

### Cashiers / Servers

Servers and cashiers interact with the system on a per-shift basis. They can:

- Start a shift
- End a shift
- Upload cashout documents (photos or scans)
- Review the data extracted by OCR
- Verify and correct extracted values before submitting

### Admin / Management

Admins and managers oversee historical data and reconciliation. They can:

- View shift history across servers and dates
- View original uploaded images
- Review OCR-processed data
- Edit submitted data when corrections are needed
- Filter records by date range
- Export reports for accounting and bookkeeping
- Investigate discrepancies across shifts

## OCR & Document Processing

The system will process several types of documents commonly produced during a shift:

- Printed cashout sheets
- Printed payment terminal reports (debit/credit)
- Handwritten discount and comp receipts

OCR will be handled through **Google Cloud Vision**, using its document text detection capabilities. Extracted values will be mapped into structured fields tied to the submitting shift.

All uploaded images will remain stored alongside their extracted data, both for auditing and to allow future review or re-processing if the OCR pipeline improves.

## Upload Workflow

The upload interface should be flexible enough to fit the realities of a restaurant environment. Supported upload methods include:

- Direct upload from a mobile phone camera
- Drag-and-drop
- Copy/paste (clipboard)
- Traditional file picker

The application must work across:

- Phones
- Tablets
- Desktop browsers

## Data Verification Workflow

Once OCR has processed an uploaded document, the user is presented with an editable review step:

- Extracted fields are shown in a structured table
- Users can correct any incorrect or missing values
- Users can reupload an image if the original was unclear or poorly scanned
- Submission is only finalized after the user verifies the data

This keeps a human in the loop while still removing the bulk of manual entry.

## Reporting & Spreadsheet Integration

All structured data is stored in **PostgreSQL**, which acts as the source of truth.

Excel will connect to PostgreSQL through **Power Query**, and is expected to remain the primary reporting interface for management and bookkeeping. This keeps the existing spreadsheet-based reporting habits intact while replacing the manual data entry behind them.

Exports should support:

- Excel
- CSV
- PDF
- Google Sheets

Spreadsheet-side functionality is expected to include:

- Formulas
- Macros
- Tip-out calculations
- Variance tracking between sources
- Summary views by shift, server, and date range

## Authentication & Permissions

Authentication is handled via:

- Cookie-based sessions
- Server-side session storage

Permission rules:

- Only admins can access historical data and cross-shift views
- Cashiers can only access their active submission flow and current shift

## Technical Stack

- **Backend:** FastAPI
- **Frontend:** Vue 3 + TypeScript
- **Database:** PostgreSQL
- **OCR:** Google Cloud Vision
- **Deployment:** Render
- **Architecture:** Backend-served SPA

## MVP Scope (Phase 1)

The first prototype is intentionally narrow. Its purpose is to validate the core OCR workflow and the data pipeline from upload to spreadsheet, before investing in workflow polish.

The first version only needs:

- Authentication
- Image upload
- OCR processing
- Database storage
- Spreadsheet preview / integration

The initial prototype does **not** require:

- Shift management
- Admin dashboards
- A full OCR verification workflow
- Advanced reporting

Estimated timeline for the first prototype: **approximately 2 weeks**.

## Future Expansion

Once the core pipeline is proven, future iterations may include:

- Full shift tracking
- Automated discrepancy detection across sources
- Advanced reporting dashboards
- Broader internal operations tooling for other parts of the restaurant

## User Stories

### Cashier / Server

- As a cashier, I want to start my shift in the system so my cashout is associated with the correct server and time.
- As a cashier, I want to take a photo of my cashout sheet from my phone so I don't have to type the data in by hand.
- As a cashier, I want to upload my debit/credit machine report so the totals are captured automatically.
- As a cashier, I want to review the values OCR extracted before submitting, so I can fix anything that was misread.
- As a cashier, I want to reupload a document if the photo was unclear, without losing the rest of my submission.
- As a cashier, I want to end my shift once everything is submitted, so I know the cashout is officially closed.

### Admin / Manager

- As a manager, I want to see a list of all submitted cashouts so I can review the day's activity.
- As a manager, I want to filter shifts by date range and server so I can focus on a specific period.
- As a manager, I want to view the original uploaded image alongside the extracted data, so I can verify what was submitted.
- As a manager, I want to edit submitted data when I find an error, so the records stay accurate.
- As a manager, I want to investigate discrepancies between reports without digging through paper, so issues are resolved sooner.

### OCR Review

- As a cashier, I want OCR to pre-fill the cashout form so I only need to confirm or correct values.
- As a manager, I want to see which fields were edited after OCR extraction, so I can spot recurring extraction issues.

### Export & Reporting

- As a manager, I want to export cashout data to Excel so I can continue using existing reporting spreadsheets.
- As a manager, I want Excel to pull live data from the database via Power Query, so reports stay current without re-exporting.
- As a manager, I want to export filtered records to CSV or PDF, so I can share specific reports with bookkeeping.

## Known Unknowns / Open Questions

The following items are intentionally left open at this stage and will be resolved as the project progresses:

- Production domain name
- Final spreadsheet structure used by management and bookkeeping
- Finalized data models for shifts, cashouts, and supporting documents
- Additional reporting requirements beyond the current spreadsheet workflow
- Scope of future operational tooling beyond cashouts

## Contributors

- Remi Lemire

## Client

Developed for [Placeholder].

## License

This project is proprietary and intended for internal use only. See [LICENSE](LICENSE) for details.
