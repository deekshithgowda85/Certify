# CertGen Frontend

React + Vite frontend for the Bulk Certificate Generator API.

## Stack
- React 18 + Vite
- React Router v6
- Tailwind CSS
- Framer Motion (animations)
- TanStack Query (polling + caching)
- Zustand (auth state)
- React Hot Toast

## Pages
- `/login` — Sign in
- `/register` — Create account (asks for Full Name)
- `/dashboard/certificates` — Select course → generate → animated progress → download
- `/dashboard/profile` — View stats, edit name inline

## Quick Start (standalone)
```bash
cd frontend
cp .env.example .env
npm install
npm run dev
# → http://localhost:3000
```

## With Docker Compose
Add to your root docker-compose.yml:
```yaml
frontend:
  build: ./frontend
  ports:
    - "80:80"
  depends_on:
    - api
```
