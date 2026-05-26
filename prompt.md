# Transportation & Logistics Web Application — Prompt

---

## Context and Role

As a Full-Stack Developer specializing in enterprise-grade logistics systems, you are responsible for designing and implementing a high-performance **Transportation & Logistics Web Application**. The platform must use **Framer Motion** to deliver immersive, scroll-based storytelling animations while maintaining responsiveness, accessibility, and production-level quality across all modules.

The application must serve the complete logistics lifecycle — shipment booking, real-time tracking, fleet and driver management, route optimization, and analytics reporting — all presented through a modern, animated interface that guides both operators and end users through complex workflows with clarity and ease.

---

## Objective

Full-stack platform that does this:

- Scroll animations using Framer Motion. Works on the public landing page and the logged-in dashboard too.
- Looks modern. Works on every screen size. Pages transition smoothly, not jarring.
- Multi-step booking flow. Shows cost as they input data. Real-time stuff.
- Different user types get different access. Admin sees everything. Dispatcher books and assigns. Driver only sees their jobs. Customer books and tracks their own orders.
- Everything gets logged in MongoDB. Complete audit trail. Who did what, when they did it.
- Sends emails when important things happen. Booking confirmation. Driver gets dispatch info. Delivery notification. Works.

---

## UI and Animation Requirements


### Scroll-Based Storytelling

Things animate as people scroll through. Use Framer Motion, but be smart. Only `transform` and `opacity` because the browser won't lag. Target 60fps. That's the goal.

Each section:

- **Hero Section** — Headline appears word by word. Background moves slower than the text. Creates that depth effect. Works really well.
- **Features Section** — Cards slide in one by one. Keeps you looking at each feature instead of seeing everything at once.
- **Statistics Section** — Numbers count up from zero as you scroll past. More interesting than static numbers.
- **Testimonials Section** — Horizontal carousel, swipe through it. Feels natural with momentum.
- **Dashboard Pages** — Going between Dashboard, Fleet, Tracking, Reports should feel like one connected space, not like different sites.

Make sure:

- Animations use only `transform` and `opacity`. Keep performance up.
- Use `useInView` from Framer Motion to trigger things exactly when they scroll into view.
- Don't slow down scrolling. Animations happen in background, non-blocking.

### Layout Requirements

Pages needed:

- **Landing Page** — Hero, features, stats, testimonials, contact form at the bottom.
- **Dashboard** — KPI cards, recent shipments, fleet overview.
- **Shipment Management** — Booking flow, list of shipments, tracking map.
- **Fleet & Driver Management** — Vehicle cards, driver list with status.
- **Route Planning** — Interactive map for route optimization.
- **Analytics** — Charts with date filtering.

These must be:

- Responsive across mobile, tablet, desktop. Use Tailwind CSS only.
- Actually accessible. Keyboard navigation works. Screen readers work. WCAG 2.1 AA.
- Fast. Dashboard loads under 2 seconds. Landing page scores 90+ on Lighthouse.

---

## Core Module Requirements

### Shipment Booking and Order Management

Three steps in the booking wizard. Animated transitions between each step.

- **Step 1 — Route Selection:** User enters origin and destination with autocomplete. Live map preview updates as they type.
- **Step 2 — Vehicle Selection:** Show motorcycle, van, truck, heavy freight options. Cost and time recalculate based on distance and vehicle.
- **Step 3 — Confirmation:** Order summary with full breakdown. Loading spinner on submit. Then success screen with order ID and pickup time.

Done.

### Real-Time Shipment Tracking

Map shows where shipments are. Has animated markers. Status timeline shows: Pending → Picked Up → In Transit → Out for Delivery → Delivered. Each step fills in as it happens.

When status changes, banner slides in from top. Updates every 10 seconds. Pauses when user switches tabs. Resumes when they come back. Saves battery, saves API calls.

### Fleet and Vehicle Management

Vehicles as cards. Shows registration, type, capacity, driver, availability badge. Hover and it lifts. Click to expand inline details.

Admins can:
- Add vehicles via slide-in form from the right.
- Edit details inline. Updates instantly.
- Soft-delete (set `is_active: false`). Nothing permanently gone.
- See counters at top: Total, Active, In Maintenance, Unassigned. Real-time updates.

### Driver Management

Driver profiles. Name, license number, expiry date, assigned vehicle, status badge. Badge color changes: Available, On Duty, Off Duty, On Leave.

Dispatchers assign drivers to shipments from a dropdown. Only shows available drivers. Keeps driver status and shipment in sync. No conflicts.

### Route Planning and Optimization

Dispatchers pick multiple pending shipments on a map. Request optimization. Backend calls OpenRouteService or Google Directions. Calculates best delivery order.

On the map:
- Route draws itself with animation.
- Drag waypoints to adjust.
- Reanimates on changes.

### Role-Based Access Control

Four roles. Strict boundaries.

- **Admin** — Everything. All modules. User management. System config.
- **Dispatcher** — Shipment management, driver assignment, route planning. No user management or settings.
- **Driver** — Own assigned shipments only. Can mark delivered.
- **Customer** — Book shipments. Track their own orders. That's it.

Enforced on frontend and backend. No workarounds.

### Analytics and Reporting Dashboard

Charts showing what's happening. Filterable by date range.

- **Line chart** — Total shipments per day.
- **Donut chart** — Shipment status breakdown.
- **Grouped bar chart** — Delivery time vs SLA target.
- **Gauge chart** — Fleet utilization percentage.

Charts animate in on scroll.

---

## Backend Requirements

FastAPI backend. Organized into modules: routes, models, database access, services, background workers.

Expose versioned REST API under `/api/v1/` — shipments, fleet, drivers, routes, analytics, contact, auth.

Use **Motor** (async MongoDB driver) so database calls don't block. Everything runs in parallel. Can handle more requests on a single process.

Secure endpoints with **JWT tokens**. Decode to know who's requesting, what role they have.

Apply **role enforcement** via dependency. Wrong role gets 403.

Hash passwords with **bcrypt**. Never return hashed passwords in responses.

Store secrets in `.env`: MongoDB URI, JWT secret, SMTP credentials, API keys. Use Pydantic BaseSettings.

Log everything:

- MongoDB collections: `shipments`, `vehicles`, `drivers`, `routes`, `users`, `notifications`, `contact_submissions`. Every doc has `created_at`, `updated_at`, and user ID.
- Application logs in JSON format. Include request ID, user ID, endpoint, method, status code, latency in milliseconds.

Send emails via `aiosmtplib` and BackgroundTasks at these events:

- **Shipment booked** — Customer gets tracking number and pickup time.
- **Shipment dispatched** — Customer and driver get route details.
- **Shipment delivered** — Customer gets delivery confirmation and feedback link.
- **Shipment delayed** — Dispatcher gets alert.

Use Gmail SMTP, SendGrid, or AWS SES. HTML email templates in `app/templates/email/` with plain text fallback. Use Jinja2.

Prevent spam:

- Rate limit unauthenticated endpoints to 20 requests per minute per IP via `slowapi`.
- CORS restricted to frontend domain only.

---

## Data Processing Requirements

Clean inputs. Prevent XSS and NoSQL injection.

Strip HTML tags and script content from string fields at Pydantic level.

Type-validate all query parameters through Pydantic before MongoDB queries. No operator injection.

Validate these strictly:

- Emails — regex check on both client and server.
- Phone numbers — numeric, correct length, country-aware.
- Required fields — return 422 with field-level errors if missing.

API responses follow standard format:

**Success:** `{ "success": true, "data": { ... }, "meta": { "page": 1, "total": 42 } }`

**Error:** `{ "success": false, "error": { "code": "...", "message": "...", "details": [...] } }`

---

## Output Requirements

Finished app should have:

- Animated scroll-driven Transportation & Logistics platform covering all modules.
- Multi-step booking wizard. Animated transitions. Real-time cost estimation.
- Live tracking map. Pulsing markers. Status timeline. 10-second polling.
- Fleet and driver dashboards. Add vehicles. Assign drivers. See availability.
- Route optimization map. Self-drawing polylines. Draggable waypoints.
- Analytics dashboard. Date-filtered charts. Animated on scroll.
- Email notifications at all four shipment events.
- Confirmation message after booking.
- Clear error states. Client validation. Server errors. No page reloads. Form state preserved.

---

## Error Handling and Documentation

Frontend errors:

- 401 → auto refresh token or redirect to login.
- 429 → toast explaining rate limit.
- 5xx → toast with request ID for support.
- Unhandled errors → Error Boundary catches, shows retry button for data load failures, form error state for submission.

Backend errors:

- Global `@app.exception_handler` catches unhandled exceptions.
- Log full traceback via `structlog`.
- Return sanitized 500 response. Never expose internal stack traces.
- All business logic exceptions inherit from `LogisticsBaseException`. Carries status code, error code, human message.
- Log with context: request ID, endpoint, user ID, traceback.

Documentation:

Write `README.md` with:

- **Folder structure** — One line per directory explaining what's in it.
- **Setup instructions** — Step-by-step for backend (Python 3.11, venv, `pip install -r requirements.txt`, `.env` setup, DB seed script) and frontend (Node 18+, `npm install`, `.env.local`, `npm run dev`).
- **Environment variables** — Full table. Every variable. Purpose. Example value. Frontend and backend.
- **Deployment steps** — Dockerfile and docker-compose.yml. Deploy to Railway or Render (FastAPI), Vercel (React). Staging vs production differences.

---

## Performance and Scalability

Optimize React bundle using Vite code splitting. Each page loads as separate lazy chunk. Heavy dependencies (map, charts) in dedicated vendor chunks. Initial bundle has landing and auth only.

Lazy-load heavy components. Map, charts, route planning only download when needed.

Tree-shake Framer Motion. Import only specific `motion` components per file, not the whole library.

All FastAPI handlers must be `async` using Motor's async API. Event loop never blocked by database I/O.

Cache analytics aggregation query results for 5 minutes using Redis or in-memory TTL cache. Prevents repeated heavy MongoDB pipeline executions.

Debounce address autocomplete, route recalculation, search inputs at 300ms minimum before requests.

Support high traffic. Semantic HTML5. Open Graph meta tags. Structured JSON-LD. Full keyboard navigation.

---

## Technology Stack

Frontend:
- React 18 with Vite, React Router v6, TanStack Query
- Framer Motion v11 for animations
- Tailwind CSS v3 with Forms and Typography plugins
- React Hook Form with Zod for validation
- Axios with interceptors

Backend:
- FastAPI with Python 3.11
- Motor for async MongoDB, Pydantic v2
- PyJWT and bcrypt for auth
- aiosmtplib with Jinja2 for emails
- slowapi for rate limiting, structlog for logging
- python-dotenv and Pydantic BaseSettings

Database:
- MongoDB Atlas (`logistics_db`) with collections: `users`, `shipments`, `vehicles`, `drivers`, `routes`, `notifications`, `contact_submissions`

Optional:
- Redis for query caching and session storage
- OpenRouteService or Google Directions API for routes
- Mapbox GL JS or Leaflet.js for maps
