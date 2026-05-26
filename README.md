# Transportation & Logistics Web Application

A full-stack, enterprise-grade logistics platform built with React 18 + FastAPI, featuring scroll-driven Framer Motion animations, real-time shipment tracking, role-based access control, and automated email notifications across the full shipment lifecycle.

---

## Project Overview

This platform covers everything a logistics operation needs in one place — shipment booking, live tracking, fleet and driver management, route optimization, and analytics reporting. It's designed to serve four distinct user roles (Admin, Dispatcher, Driver, Customer), each with their own tailored interface and strict permission boundaries.

The frontend is built for performance and feel — Framer Motion powers scroll-based storytelling animations throughout, Vite handles code splitting and lazy loading, and TanStack Query manages all server state. The backend is a fully async FastAPI application using Motor for non-blocking MongoDB access, structured JSON logging via structlog, and transactional email delivery through aiosmtplib.

**Key capabilities:**
- Multi-step animated shipment booking wizard with live cost estimation
- Real-time tracking map with pulsing markers and 10-second polling
- Atomic driver assignment via MongoDB transactions
- Role-enforced API endpoints with JWT authentication
- Redis-cached analytics aggregations (5-minute TTL)
- Email notifications at four shipment lifecycle events
- Full audit trail on every MongoDB document

---

## Repository Structure

```
transport-logistics-platform/
│
├── frontend/                        # React 18 + Vite frontend application
│   ├── public/                      # Static assets
│   ├── src/
│   │   ├── api/                     # Axios instance and API call functions
│   │   ├── components/
│   │   │   ├── animations/          # Reusable Framer Motion wrapper components
│   │   │   ├── booking/             # BookingWizard, StepRoute, StepVehicle, StepConfirmation
│   │   │   ├── charts/              # Recharts wrappers for analytics page
│   │   │   ├── dashboard/           # KPI cards, shipment table, fleet overview
│   │   │   ├── fleet/               # VehicleCard, FleetDrawer, VehicleSummaryBar
│   │   │   ├── forms/               # Shared form field components
│   │   │   ├── layout/              # Sidebar, Topbar, AppShell
│   │   │   ├── maps/                # MapView, PulsingMarker, PolylineOverlay
│   │   │   ├── shared/              # Button, Badge, Modal, Toast, ErrorBoundary
│   │   │   └── tracking/            # StatusTimeline, StatusBanner
│   │   ├── features/
│   │   │   ├── analytics/           # Analytics page logic and hooks
│   │   │   ├── auth/                # Login, Register, auth context
│   │   │   ├── booking/             # Booking wizard state and submission logic
│   │   │   ├── drivers/             # Driver list, profile, assignment logic
│   │   │   ├── fleet/               # Fleet management state and actions
│   │   │   ├── routes/              # Route optimization UI and map interactions
│   │   │   ├── tracking/            # Live tracking polling hook and map integration
│   │   │   └── users/               # User management (Admin only)
│   │   ├── hooks/                   # Shared custom hooks (useDebounce, usePolling, etc.)
│   │   ├── layouts/                 # LandingLayout, DashboardLayout
│   │   ├── lib/                     # Axios setup, TanStack Query client config
│   │   ├── pages/                   # Route-level page components (lazy loaded)
│   │   ├── providers/               # QueryClientProvider, AuthProvider, ToastProvider
│   │   ├── routes/                  # React Router v6 route definitions and guards
│   │   ├── schemas/                 # Zod validation schemas
│   │   ├── store/                   # Global client state (Zustand or Context)
│   │   ├── styles/                  # Global CSS, Tailwind base overrides
│   │   ├── types/                   # TypeScript interfaces and enums
│   │   ├── utils/                   # Formatting, date helpers, cost calculators
│   │   └── main.tsx                 # Application entry point
│   ├── .env.local                   # Frontend environment variables (not committed)
│   ├── vite.config.ts               # Vite build config with manual chunk splitting
│   ├── tailwind.config.js           # Tailwind CSS configuration
│   └── package.json                 # Frontend dependencies and scripts
│
├── backend/                         # FastAPI backend application
│   ├── app/
│   │   ├── api/
│   │   │   └── v1/                  # Versioned route handlers
│   │   │       ├── auth.py          # Register, login, token refresh
│   │   │       ├── shipments.py     # Booking, status updates, assignment
│   │   │       ├── vehicles.py      # Fleet CRUD, soft-delete, status
│   │   │       ├── drivers.py       # Driver profiles, availability, assignment
│   │   │       ├── routes.py        # Route optimization and waypoint management
│   │   │       ├── analytics.py     # Aggregation queries with Redis caching
│   │   │       ├── notifications.py # Notification log retrieval
│   │   │       └── contact.py       # Public contact form (rate limited)
│   │   ├── core/
│   │   │   ├── config.py            # Pydantic BaseSettings, environment loading
│   │   │   ├── database.py          # Motor client, index setup, connection lifecycle
│   │   │   ├── logging.py           # structlog JSON configuration
│   │   │   ├── security.py          # JWT creation/decoding, bcrypt, RoleChecker
│   │   │   ├── rate_limit.py        # slowapi limiter instance
│   │   │   └── exceptions.py        # LogisticsBaseException and error envelope builder
│   │   ├── middleware/
│   │   │   ├── request_id.py        # Injects unique request ID into every request
│   │   │   └── audit.py             # Logs actor, endpoint, and latency per request
│   │   ├── models/
│   │   │   ├── shipment.py          # Shipment Pydantic schemas (create, update, response)
│   │   │   ├── vehicle.py           # Vehicle schemas
│   │   │   ├── driver.py            # Driver schemas
│   │   │   ├── route.py             # Route and waypoint schemas
│   │   │   ├── user.py              # User registration and response schemas
│   │   │   └── notification.py      # Notification log schema
│   │   ├── repositories/            # Database query functions per collection
│   │   ├── services/                # Business logic (cost estimation, route calls, email)
│   │   ├── templates/
│   │   │   └── email/               # Jinja2 HTML email templates + plaintext fallbacks
│   │   │       ├── booked.html
│   │   │       ├── booked.txt
│   │   │       ├── dispatched.html
│   │   │       ├── dispatched.txt
│   │   │       ├── delivered.html
│   │   │       ├── delivered.txt
│   │   │       ├── delayed.html
│   │   │       └── delayed.txt
│   │   ├── workers/                 # Background task helpers
│   │   ├── utils/                   # Shared utility functions
│   │   └── main.py                  # App factory, middleware registration, router mounts
│   ├── seed.py                      # Database seed script for local development
│   ├── requirements.txt             # Python dependencies
│   ├── Dockerfile                   # Multi-stage production Docker build
│   └── .env                         # Backend environment variables (not committed)
│
├── docker-compose.yml               # Full stack orchestration (API + frontend + MongoDB + Redis)
├── README.md                        # This file
└── .gitignore                       # Ignores .env files, node_modules, __pycache__, etc.
```

---

## Running the Application

### Prerequisites

- Python 3.11+
- Node.js 18+
- MongoDB Atlas account (or local MongoDB 6+)
- Redis (optional, for analytics caching)
- A SendGrid, Gmail SMTP, or AWS SES account for email

---

### Backend Setup

**1. Navigate to the backend directory**
```bash
cd backend
```

**2. Create and activate a virtual environment**
```bash
python -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Create your `.env` file**

Copy the example below into `backend/.env` and fill in your values:

```env
MONGODB_URI=mongodb+srv://<user>:<password>@cluster.mongodb.net/logistics_db
DATABASE_NAME=logistics_db
JWT_SECRET=your_super_secret_key_here
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=SG.your_sendgrid_api_key
EMAILS_FROM_EMAIL=dispatch@yourdomain.com

REDIS_URL=redis://localhost:6379
OPENROUTE_API_KEY=your_openrouteservice_key
CORS_ORIGINS=["http://localhost:5173","https://yourdomain.com"]
```

**5. Seed the database with sample data**
```bash
python seed.py
```

This creates sample users for each role (Admin, Dispatcher, Driver, Customer), a handful of vehicles, drivers, and shipments so the dashboard has something to show on first load.

**6. Start the development server**
```bash
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

---

### Frontend Setup

**1. Navigate to the frontend directory**
```bash
cd frontend
```

**2. Install dependencies**
```bash
npm install
```

**3. Create your `.env.local` file**
```env
VITE_API_URL=http://localhost:8000/api/v1
VITE_MAPBOX_TOKEN=your_mapbox_public_token
```

**4. Start the development server**
```bash
npm run dev
```

The frontend will be available at `http://localhost:5173`.

---

### Running with Docker

To spin up the entire stack (API, frontend, MongoDB, Redis) in one command:

```bash
docker-compose up --build
```

Services will be available at:
- Frontend: `http://localhost:5173`
- API: `http://localhost:8000`
- API Docs: `http://localhost:8000/docs`

To stop everything:
```bash
docker-compose down
```

---

### Running Tests

**Backend tests**
```bash
cd backend
pytest --cov=app --cov-report=term-missing
```

**Frontend tests**
```bash
cd frontend
npm run test
```

**Frontend type checking**
```bash
npm run typecheck
```

**Frontend lint**
```bash
npm run lint
```

---

## Environment Variable Reference

### Backend (`backend/.env`)

| Variable | Purpose | Example |
|---|---|---|
| `MONGODB_URI` | MongoDB Atlas connection string | `mongodb+srv://user:pass@cluster.mongodb.net/` |
| `DATABASE_NAME` | Name of the MongoDB database | `logistics_db` |
| `JWT_SECRET` | Secret key used to sign JWT tokens | `a9f3c2e1d8b7...` (64-char hex) |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token expiry duration in minutes | `10080` (7 days) |
| `SMTP_HOST` | SMTP server hostname | `smtp.sendgrid.net` |
| `SMTP_PORT` | SMTP server port | `587` |
| `SMTP_USER` | SMTP authentication username | `apikey` |
| `SMTP_PASSWORD` | SMTP authentication password / API key | `SG.xxxxx` |
| `EMAILS_FROM_EMAIL` | Sender address for outbound emails | `dispatch@yourdomain.com` |
| `REDIS_URL` | Redis connection URL for analytics caching | `redis://localhost:6379` |
| `OPENROUTE_API_KEY` | API key for OpenRouteService route optimization | `5b3a...` |
| `CORS_ORIGINS` | Allowed frontend origins for CORS | `["http://localhost:5173"]` |

### Frontend (`frontend/.env.local`)

| Variable | Purpose | Example |
|---|---|---|
| `VITE_API_URL` | Base URL for all API requests | `http://localhost:8000/api/v1` |
| `VITE_MAPBOX_TOKEN` | Mapbox public token for map rendering | `pk.eyJ1...` |

---

## Evaluation Methodology

The platform was evaluated against the original specification across five dimensions:

### 1. Functional Completeness
Each required module was checked against the spec — booking wizard, real-time tracking, fleet management, driver assignment, route optimization, analytics, and RBAC. Every feature was verified to work end-to-end: from the frontend interaction through the API call to the database operation and back.

### 2. Animation and UI Quality
Framer Motion implementations were reviewed to confirm all animations use only `transform` and `opacity` (GPU-friendly properties), that `useInView` correctly gates scroll-triggered animations, and that `AnimatePresence` produces proper directional slide transitions in the booking wizard. The parallax hero, staggered feature cards, counting statistics, and drag carousel were each tested manually across device sizes.

### 3. Backend Architecture and Security
The FastAPI backend was evaluated for proper async patterns throughout (no synchronous database calls), correct JWT role enforcement on every protected route, bcrypt password hashing, input sanitization at the Pydantic model level, and structured JSON logging with request context on every entry. MongoDB transactions were tested specifically on the driver assignment flow to confirm atomic behavior.

### 4. Performance
Frontend bundle analysis (via `npm run build -- --report`) confirmed correct code splitting — map and chart libraries land in separate vendor chunks, and the initial bundle contains only landing and auth code. Lighthouse was run against the production build of the landing page targeting the 90+ performance score. API response times were measured under simulated concurrent load to verify Motor's non-blocking behavior.

### 5. Code Quality and Documentation
The codebase was reviewed for consistent file organization, meaningful naming, separation of concerns between routes/services/repositories, and absence of business logic inside route handlers. Environment variable coverage was verified against the reference table above. Docker builds were tested from scratch on a clean environment to confirm the setup instructions are accurate and complete.

---

## Deployment

### Frontend → Vercel
```bash
cd frontend
npm run build
# Deploy the dist/ folder to Vercel via CLI or GitHub integration
```

### Backend → Railway or Render
Push the `backend/` directory. Both platforms detect the `Dockerfile` automatically. Set all environment variables from the reference table above in the platform's environment settings panel.

### Staging vs Production
- In staging, `CORS_ORIGINS` should include your staging frontend URL alongside localhost.
- In production, `JWT_SECRET` must be a cryptographically random 64-character string — never reuse a development value.
- Redis is optional in development but strongly recommended in production to avoid repeated heavy aggregation queries on every analytics page load.
- Set `EMAILS_FROM_EMAIL` to a domain-verified address in production to avoid deliverability issues.
