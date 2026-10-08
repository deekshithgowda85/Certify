# Certify Frontend

React/Vite application for registration, login, certificate creation and downloads, account profile, and administrator metrics.

## Features

- Responsive Newsprint design system: warm paper texture, ink-black grid rules, Playfair/Lora typography, editorial-red accents, and hard-shadow card hovers.
- Shared design tokens, sharp-corner controls, keyboard focus styles, and reduced-motion support across authentication, dashboard, bulk-generation, profile, and metrics routes.
- Course templates and a manual certificate job form.
- A standalone `/bulk-certificates` page with recipient and failed-result pagination at 50 rows per page, add/remove row controls, per-row course/date fields, CSV import (`name,email,course_name,completion_date`), batch progress/results, and user-triggered merged-PDF download.
- CSV import replaces the current recipient table and accepts up to 100,000 participants. Submissions are split into queue jobs of at most 10,000 participants each; a downloadable CSV template is provided. Use ISO completion dates (`YYYY-MM-DD`) for best compatibility.
- Smaller bulk drafts are kept in the current browser session when a visitor signs in or registers before submission. Large lists stay in memory only, so keep the tab open until submission.
- A synchronous generation lock prevents multiple concurrent submissions from the page.
- Job and batch status/progress polling, certificate history, individual PDF downloads, and merged batch-PDF downloads.
- Profile editing and generated/processing job statistics.
- Metrics dashboard for API/worker health, queue activity, and sandbox pool slots.
- Bottom-center success/error toasts; shared request error formatting for validation, rate limits, network failures, and server errors.
- One transient retry for safe reads. Job submissions include an idempotency key and may be retried once; authentication writes are not automatically retried.

## Routes

- `/login`: sign in.
- `/register`: create an account and sign in.
- `/bulk-certificates`: prepare an authenticated batch of up to 100,000 participants and download successful certificates as one PDF.
- `/bulk-certificates/public`: submit and track an account-free batch; its unguessable URL is a private bearer link for progress, recipient details, and the merged PDF.
- `/dashboard/certificates`: select a course or submit a custom certificate job.
- `/dashboard/profile`: edit profile and review job history/statistics.
- `/dashboard/bulk-certificates`: authenticated bulk workspace inside the dashboard.
- Login offers both the account-owned bulk generator and the no-account public generator.
- Generated PDFs are removed from storage after 10 minutes; expired completed batches can be regenerated from their saved recipients.
- `/admin/metrics`: view service, queue, and sandbox metrics.

## Development

```powershell
cd frontend
npm install
npm run dev
```

The Vite server runs at `http://localhost:3000`. Set `VITE_API_URL` in a local `.env` only when the API is not available through the configured development proxy.

## Production build

```powershell
npm run build
npm run preview
```

Compose builds the static site and serves it through the frontend's Nginx configuration at `http://localhost:3000`. See the repository root [`README.md`](../README.md) for the complete Compose workflow.
