# Certify Frontend

React/Vite application for registration, login, certificate creation and downloads, account profile, and administrator metrics.

## Features

- Responsive black-and-white application theme and animated dashboard components.
- Course templates and a manual certificate job form.
- A synchronous generation lock prevents multiple concurrent submissions from the page.
- Job status/progress polling, certificate history, PDF downloads, and bulk ZIP downloads.
- Profile editing and generated/processing job statistics.
- Metrics dashboard for API/worker health, queue activity, and sandbox pool slots.
- Bottom-center success/error toasts; shared request error formatting for validation, rate limits, network failures, and server errors.
- One transient retry for safe reads. Job submissions include an idempotency key and may be retried once; authentication writes are not automatically retried.

## Routes

- `/login`: sign in.
- `/register`: create an account and sign in.
- `/dashboard/certificates`: select a course or submit a custom certificate job.
- `/dashboard/profile`: edit profile and review job history/statistics.
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
