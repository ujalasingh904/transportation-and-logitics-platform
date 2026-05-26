# Transportation & Logistics Web Application — Prompt

---

## Context and Role

As a Full-Stack Developer specializing in enterprise-grade logistics systems, you are responsible for designing and implementing a high-performance **Transportation & Logistics Web Application**. The platform must use **Framer Motion** to deliver immersive, scroll-based storytelling animations while maintaining responsiveness, accessibility, and production-level quality across all modules.

The application must serve the complete logistics lifecycle — shipment booking, real-time tracking, fleet and driver management, route optimization, and analytics reporting — all presented through a modern, animated interface that guides both operators and end users through complex workflows with clarity and ease.

---

## Objective

Develop a complete full-stack Transportation & Logistics platform that:

- Implements scroll-based storytelling animations using Framer Motion across all public and authenticated pages.
- Delivers a modern, fully responsive UI with smooth page transitions and interactive data dashboards.
- Provides a multi-step animated shipment booking flow with real-time cost estimation and order confirmation.
- Includes role-based access for Admin, Dispatcher, Driver, and Customer — each with a tailored interface and strict permission boundaries.
- Logs all shipment, driver, and fleet activity securely in MongoDB with structured audit trails.
- Triggers email notifications to relevant users at every key shipment lifecycle event.

---

## UI and Animation Requirements

### Scroll-Based Storytelling

Implement scroll-triggered animations using Framer Motion across both the public landing pages and the authenticated application shell. All animations must use only `transform` and `opacity` — GPU-friendly properties that avoid layout recalculation and maintain 60fps across devices.

Animate sections sequentially to create a narrative flow, including smooth transitions between:

- **Hero Section** — Full-viewport animated headline using a word-by-word staggered text reveal, paired with a parallax background where logistics imagery scrolls slower than the foreground to create layered depth.
- **Features Section** — Cards animate in one by one with staggered delays so the visitor's attention follows each platform capability in sequence.
- **Statistics Section** — Animated number counters count up from zero as each metric enters the viewport, reinforcing the platform's operational scale.
- **Testimonials Section** — Horizontal drag carousel with momentum-based swiping using Framer Motion's drag constraints for natural, touch-friendly browsing.
- **Dashboard Pages** — Shared layout transitions between Dashboard, Fleet, Tracking, and Reports so navigation feels spatially continuous rather than like hard page reloads.

Ensure animations:

- Are performant and avoid layout thrashing by using only `transform` and `opacity`.
- Use Framer Motion's `useInView` hook to trigger section animations precisely as they enter the viewport.
- Do not block scroll performance — all animation callbacks must be passive and non-blocking.

### Layout Requirements

The application must include the following pages and sections:

- **Landing Page** — Hero, Features, Statistics, Testimonials, and a "Get in Touch" call-to-action section.
- **Dashboard** — KPI summary cards, recent shipments table, and fleet status overview.
- **Shipment Management** — Multi-step booking wizard, shipment list with filters, and a live tracking map view.
- **Fleet & Driver Management** — Vehicle card grid and driver profile list with status badges and assignment controls.
- **Route Planning** — Interactive map with optimized polyline rendering and draggable waypoints.
- **Analytics** — Chart-driven KPI reporting page with date range filtering.

The layout must be:

- Fully responsive across mobile (320px+), tablet (768px), and desktop (1280px+) using Tailwind CSS utility classes exclusively.
- Accessible — all interactive elements must carry ARIA labels, `role` attributes, and full keyboard navigation support meeting **WCAG 2.1 AA** standards.
- Optimized for performance — the authenticated dashboard shell must load in under 2 seconds; the public landing page must score **90+ on Lighthouse Performance**.

---

## Core Module Requirements

### Shipment Booking and Order Management

The booking flow must be implemented as a 3-step animated form wizard using Framer Motion's `AnimatePresence` with horizontal slide transitions between steps, giving users a clear sense of forward progression.

- **Step 1 — Route Selection:** Origin and destination address autocomplete backed by a geocoding API, with the map preview updating live as the user types.
- **Step 2 — Vehicle Selection:** Animated selection cards for motorcycle, van, truck, and heavy freight; cost and transit time recalculate dynamically based on distance and vehicle class on each selection.
- **Step 3 — Confirmation:** Animated order summary with a full charge breakdown; a loading spinner runs on submit, followed by a confirmation modal with an animated checkmark, order ID, and estimated pickup time.

### Real-Time Shipment Tracking

The tracking view must render a full-width interactive map using Leaflet.js or Mapbox GL JS with animated pulsing markers for each active shipment. A vertical status timeline — Pending → Picked Up → In Transit → Out for Delivery → Delivered — must fill in each completed step with a smooth Framer Motion layout animation.

- Status change banners must slide in from the top of the map when the shipment state updates.
- The frontend must poll the status endpoint every 10 seconds using a debounced interval that pauses automatically when the browser tab is hidden and resumes on focus.

### Fleet and Vehicle Management

The fleet view must display a grid of vehicle cards showing registration number, type, capacity, assigned driver, and a color-coded availability badge. Hovering lifts and shadows the card; clicking expands an inline detail panel without navigating away from the page.

- Admins can add vehicles via a slide-in drawer form from the right edge of the screen and edit details inline with optimistic UI updates.
- Deactivating a vehicle performs a soft-delete by setting `is_active: false` — no documents are permanently removed.
- A summary row at the top displays animated counters for total, active, in-maintenance, and unassigned vehicles.

### Driver Management

Driver profiles must display full name, license number, license expiry date, assigned vehicle, and a color-coded status badge — **Available, On Duty, Off Duty, On Leave** — that transitions color smoothly when the status changes.

- Dispatchers assign a driver to a shipment via a searchable dropdown populated only with currently Available drivers.
- The assignment must update both the shipment document and the driver's status in a single MongoDB transaction to prevent race conditions.

### Route Planning and Optimization

Dispatchers must be able to select multiple pending shipments on the map and trigger a route optimization request. The backend calls OpenRouteService or Google Directions API with the driver's start location, delivery addresses, and time window constraints to calculate the most efficient delivery sequence.

- The optimized route renders as an animated polyline that draws itself progressively using Framer Motion's `pathLength` SVG animation.
- Dispatchers can drag waypoints to adjust the route, and the polyline reanimates to reflect each change in real time.

### Role-Based Access Control

Four roles must be enforced with strict permission boundaries across all frontend routes and backend endpoints:

- **Admin** — full access to all modules, user management, and system configuration.
- **Dispatcher** — shipment management, driver assignment, and route planning; no access to user management or system settings.
- **Driver** — view own assigned shipments, update delivery status, and submit location updates only.
- **Customer** — create shipment bookings and track own shipments only.

### Analytics and Reporting Dashboard

The analytics page must surface operational KPIs through interactive Recharts charts, each animated into view by Framer Motion on scroll and filterable by a configurable date range picker.

- **Line chart** — total shipments per day over the selected date range.
- **Donut chart** — animated shipment status distribution breakdown.
- **Grouped bar chart** — average delivery time versus SLA target.
- **Gauge chart** — fleet utilization rate as a percentage.

---

## Backend Requirements

Implement a FastAPI backend organized into clearly separated modules for routes, models, database repositories, services, and background workers.

- Expose versioned REST API endpoints under `/api/v1/` for every module — shipments, fleet, drivers, routes, analytics, contact, and auth.
- Use **Motor** (async MongoDB driver) for all database operations so the event loop is never blocked by I/O, enabling high concurrency on a single process.
- Secure all authenticated endpoints using **JWT tokens** decoded via a `get_current_user` FastAPI dependency, which attaches the user's role to every request context.
- Apply **role enforcement** via a `require_role` dependency on each route that raises HTTP 403 if the authenticated user's role does not match the required permission level.
- Hash all passwords with **bcrypt** before storage; never return the hashed password in any API response.
- Store all environment-sensitive configuration — MongoDB URI, JWT secret, SMTP credentials, routing API keys — in a `.env` file loaded via Pydantic's `BaseSettings`.

Securely log all activity in:

- **MongoDB collections** — `shipments`, `vehicles`, `drivers`, `routes`, `users`, `notifications`, `contact_submissions` — with complete audit fields including `created_at`, `updated_at`, and actor user ID on every document.
- **Structured application logs** — using `structlog` in JSON format; every request log line must include request ID, user ID, endpoint path, HTTP method, response status code, and latency in milliseconds.

Trigger email notifications to relevant users using `aiosmtplib` via FastAPI's `BackgroundTasks` at the following events:

- **Shipment booked** — confirmation to the customer with the tracking number and estimated pickup time.
- **Shipment dispatched** — route details to both the customer and the assigned driver.
- **Shipment delivered** — delivery confirmation to the customer with an optional feedback link.
- **Shipment delayed** — delay alert to the assigned dispatcher.

Use a secure email service (Gmail SMTP, SendGrid, or AWS SES) configured via environment variables. All email templates must be Jinja2 HTML files stored in `app/templates/email/` with a plaintext fallback for clients that do not render HTML.

Prevent spam and abuse using:

- **Rate limiting** via `slowapi` — unauthenticated endpoints capped at 20 requests per minute per IP address.
- **CORS** restricted to the frontend's deployed domain only.

---

## Data Processing Requirements

Sanitize all inputs to prevent:

- **XSS attacks** — HTML tags and script content stripped from all string fields at the Pydantic model level before reaching business logic or the database.
- **NoSQL injection** — all query parameters type-validated through Pydantic before being passed to Motor query builders so operator injection cannot reach MongoDB.

Validate the following fields with strict server-side rules:

- Email addresses — regex format validation enforced on both client and server independently.
- Phone numbers — numeric format and length validation with country code awareness.
- All required fields — missing required fields return a structured **422 Unprocessable Entity** response with a field-level error array.

Ensure all API responses conform to a standard JSON envelope:

- **Success** — `{ "success": true, "data": { ... }, "meta": { "page": 1, "total": 42 } }`
- **Error** — `{ "success": false, "error": { "code": "...", "message": "...", "details": [...] } }`

---

## Output Requirements

- A fully animated, scroll-driven Transportation & Logistics web application covering all modules described above.
- A functional multi-step shipment booking wizard with animated transitions and real-time cost estimation.
- Live shipment tracking map with pulsing markers, status timeline, and 10-second polling.
- Fleet and driver management dashboards with animated card grids, drawer forms, and optimistic updates.
- Route optimization map view with self-drawing animated polylines and draggable waypoints.
- Analytics dashboard with date-filtered Recharts visualizations animated into view on scroll.
- Email notifications successfully triggered at all four shipment lifecycle events.
- Confirmation message displayed to the user inside the booking wizard after successful submission.
- Graceful inline error states shown for both client-side validation failures and server-returned errors, without full-page reloads or loss of form state.

---

## Error Handling and Documentation

Handle frontend errors gracefully:

- Axios interceptors must centrally catch **401** (auto token refresh or redirect to login), **429** (toast notification explaining the rate limit), and **5xx** (generic error toast with a request ID for support tracing).
- React Error Boundaries must catch page-level failures and render appropriate fallback UIs — a retry button for data load failures and a form error state for submission failures — rather than crashing the application.

Handle backend validation and runtime errors:

- A global `@app.exception_handler` must catch all unhandled exceptions, log the full traceback via `structlog`, and return a sanitized 500 response that never exposes internal stack traces to the client.
- All business logic exceptions must inherit from a `LogisticsBaseException` carrying a status code, error code, and human-readable message, serialized into the standard error envelope format.
- Log backend failures with sufficient context — request ID, endpoint, user ID, and traceback — for effective production debugging.

Document the following in a root-level `README.md`:

- **Folder structure** — every top-level directory described in one line for both the frontend and backend.
- **Setup instructions** — step-by-step local development guide for the FastAPI backend (Python 3.11, venv creation, `pip install -r requirements.txt`, `.env` setup, DB seed script) and the React frontend (Node 18+, `npm install`, `.env.local` setup, `npm run dev`).
- **Environment variable configuration** — complete table of every required variable with its purpose and an example value, covering both frontend and backend.
- **Deployment steps** — Dockerization via `Dockerfile` and `docker-compose.yml`; recommended targets are Railway or Render for FastAPI and Vercel for React; staging versus production configuration differences documented clearly.

---

## Performance and Scalability

- Optimize the React bundle using Vite code splitting — each page loads as a separate lazy chunk, and heavy dependencies like the map and chart libraries are split into dedicated vendor chunks so the initial bundle contains only landing and auth code.
- Lazy-load all heavy components — map views, chart pages, and route planning — so they are only downloaded when the user navigates to that page.
- Ensure animations do not degrade performance — all Framer Motion imports must be tree-shaken, importing only the specific `motion` components needed per file rather than the full library.
- Support high traffic without API bottlenecks — all FastAPI route handlers must be `async` using Motor's async API; the event loop must never be blocked by database I/O.
- Cache analytics aggregation query results for 5 minutes using Redis or an in-memory TTL cache to prevent repeated heavy MongoDB pipeline executions on every dashboard refresh.
- Use proper debouncing for all user interactions that trigger API calls — address autocomplete, route recalculation, and search inputs must debounce at 300ms minimum before sending requests.
- Ensure accessibility and SEO optimization — semantic HTML5 elements, Open Graph meta tags on the landing page, structured JSON-LD for the organization, and full keyboard navigability across all interactive components.

---

## Technology Stack

Use the following:

**Frontend:**
- React 18 with Vite as the build tool, React Router v6 for client-side routing, TanStack Query for all server state management.
- Framer Motion v11 for all animations across landing pages and the authenticated application shell.
- Tailwind CSS v3 with the official Forms and Typography plugins for the complete styling system.
- React Hook Form with Zod for client-side form management and schema-based validation.
- Axios with interceptor-based error handling for all HTTP client requests.

**Backend:**
- FastAPI with Python 3.11 as the asynchronous API framework.
- Motor as the async MongoDB driver for all database operations; Pydantic v2 for request/response data modeling and validation.
- PyJWT and bcrypt for JWT authentication and password hashing.
- aiosmtplib with Jinja2 HTML templates for the transactional email delivery system.
- slowapi for request rate limiting; structlog for structured JSON application logging.
- python-dotenv and Pydantic BaseSettings for environment variable management.

**Database:**
- MongoDB Atlas (`logistics_db`) as the primary database with the following collections: `users`, `shipments`, `vehicles`, `drivers`, `routes`, `notifications`, `contact_submissions`.

**Optional:**
- Redis for analytics query caching and session storage in high-traffic deployments.
- OpenRouteService or Google Directions API for route optimization calculations.
- Mapbox GL JS or Leaflet.js for interactive map rendering.
