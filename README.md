# SAAKSHYA

Build a functional hackathon prototype named “SAAKSHYA” for SIH problem statement SIH26261: AI-Powered Document Authentication & Compliance Platform.

PROJECT PURPOSE:
Create an AICTE-style application validation and decision-support dashboard. This is a demonstration prototype using synthetic data. It is NOT an official AICTE application, and it must not claim to connect to the real AICTE portal or real issuing authorities.

DESIGN:

* Professional government-tech dashboard.
* Clean white background with navy blue and teal accents.
* Simple sidebar navigation.
* Responsive layout for laptop screens.
* Clear status badges, cards, tables, and readable reports.
* Make the application easy to demonstrate to judges.

PAGES:

1. Dashboard:
    Show total applications, pending reviews, applications with discrepancies, and completed reviews. Use realistic but clearly synthetic sample data.
2. Applications:
    Display a table with application ID, institution name, application type, submission date, and validation status.
    Allow the user to open an application and inspect its details.
3. New Application:
    Create a form with institution ID, institution name, application category, application reference number, and submitted documents.
4. Document Upload:
    Allow PDF uploads and display uploaded filenames, document categories, and processing status. Validate file types and handle upload errors clearly.
5. Validation Engine:
    Implement working rule-based validation for:

* Missing mandatory fields.
* Missing required documents according to a configurable checklist.
* Expired documents when a valid expiry date is available.
* Institution ID mismatches.
* Conflicting values between application details and synthetic institutional records.
* Potential duplicate documents based on available file hashes or comparable metadata.

Every finding must include the rule triggered, the relevant field or document, the compared values where applicable, and a recommended next action.

Do not label a document forged solely because a mismatch or metadata anomaly exists.

6. Verification Status:
    Support these statuses: Verified, Mismatch Detected, Expired, Verification Pending, Source Unavailable, and Manual Review Required.
    For the demo, issuer verification responses must be simulated and clearly labelled as mock responses.
7. Results and Review:
    Generate an application validation report with findings, severity, evidence, and recommended actions.
    Allow a reviewer to mark findings as Open, Under Review, Resolved, or Escalated.
    Store review actions in an audit history.
8. Synthetic Data:
    Include at least five sample applications with different scenarios:

* Complete application with no detected discrepancies.
* Missing mandatory document.
* Expired certificate.
* Institution ID mismatch.
* Conflicting faculty counts between the application and synthetic institutional records.

TECHNICAL REQUIREMENTS:

* Implement functional navigation and working buttons.
* Persist applications and review decisions using the platform’s available database or persistent storage.
* Keep validation rules separate from the UI so that they can be modified later.
* Include loading states, empty states, and error messages.
* Do not make buttons that merely look functional; implement their actions.
* Do not invent real AICTE APIs or claim official integration.
* Use deterministic rule-based validation for the initial prototype. Do not pretend to have an advanced AI model if one is not implemented.
* If actual PDF text extraction is not supported, clearly indicate that extraction is unavailable and allow the demo to use manually entered or synthetic extracted fields. Do not pretend that uploaded documents have been fully analyzed.

FIRST PRIORITY:
Build the complete working dashboard, sample applications, validation rules, and results page before adding advanced AI features.

This project was built with [Lovable](https://lovable.dev).

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/020a3279-7687-4b43-a44f-fb258855a820).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```

## Local FastAPI integration

The login, Applications list/create/detail, private PDF upload/list, and per-application validation run/findings views use the FastAPI backend. Other prototype tools can still use the browser's synthetic demo store; the sidebar identifies those as prototype data. Backend pages do not fall back to local demo records when the API is unavailable. The integration does not verify issuers or connect to AICTE.

Set the browser-visible backend origin in the root `.env` (copy `.env.example` to `.env`):

```sh
cp .env.example .env
# edit VITE_API_BASE_URL if your backend uses a different origin
```

Create and activate the backend virtual environment, install `backend/requirements.txt`, configure `backend/.env`, and provision a user as described in [backend/README.md](backend/README.md). Start the backend from `backend/` with `uvicorn app.main:app --reload`, then start the frontend from the repository root with `npm run dev`. Backend access tokens stay in browser memory and are cleared on refresh/sign-out. Backend CORS allows the local Vite origins by default; set `CORS_ORIGINS` to a comma-separated list of exact trusted origins when using a different frontend origin.

The application API uses the backend's snake_case schema: `institution_id`, `institution_name`, `category`, `reference_number`, `submitted_at`, and `declared_faculty_count`. Document upload sends multipart `category` and `file` fields. Backend ownership and role checks remain authoritative; the UI only hides actions the current role cannot use.
