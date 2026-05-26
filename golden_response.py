"""
golden_response.py
==================
Transportation & Logistics Web Application — Production Reference Implementation
FastAPI backend covering all modules described in the prompt:
  - Authentication & Role-Based Access Control (JWT + bcrypt)
  - Shipment Booking & Order Management
  - Real-Time Shipment Tracking (location updates + polling endpoint)
  - Fleet & Vehicle Management (soft-delete, CRUD)
  - Driver Management (atomic assignment transactions)
  - Route Planning & Optimization (external routing API integration)
  - Analytics & Reporting (MongoDB aggregation pipeline + TTL cache)
  - In-App Notification System
  - Contact / Support Form Submission
  - Transactional Email (aiosmtplib, Jinja2 templates, BackgroundTasks)
  - Rate Limiting (slowapi), CORS, Input Sanitization, Structured Logging

Run:
    pip install fastapi uvicorn motor pydantic[email] pyjwt bcrypt aiosmtplib
                jinja2 slowapi httpx structlog python-dotenv email-validator
    uvicorn golden_response:app --reload
"""

# ---------------------------------------------------------------------------
# Standard Library
# ---------------------------------------------------------------------------
import asyncio
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Third-Party
# ---------------------------------------------------------------------------
import bcrypt
import httpx
import jwt
import structlog
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# ---------------------------------------------------------------------------
# Configuration — loaded from .env via Pydantic BaseSettings
# ---------------------------------------------------------------------------

class Settings(BaseSettings):
    """
    All sensitive configuration is read from environment variables / .env file.
    Never hard-code secrets in source code.
    """
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "logistics_db"

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 8  # 8 hours

    # Email (SMTP)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = "noreply@logistics.example.com"
    owner_email: str = "owner@logistics.example.com"

    # External routing API (OpenRouteService)
    routing_api_key: str = ""
    routing_api_url: str = "https://api.openrouteservice.org/v2/directions/driving-car"

    # CORS — comma-separated list of allowed origins
    allowed_origins: str = "http://localhost:5173,http://localhost:3000"

    # Analytics cache TTL in seconds
    analytics_cache_ttl: int = 300  # 5 minutes


settings = Settings()

# ---------------------------------------------------------------------------
# Structured Logging — JSON output for log aggregation services
# ---------------------------------------------------------------------------

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# In-Memory Analytics Cache — TTL-based; replace with Redis in production
# ---------------------------------------------------------------------------

class TTLCache:
    """
    Simple dictionary-backed TTL cache.
    In production, replace with redis-py or aiocache backed by Redis.
    """

    def __init__(self, ttl_seconds: int = 300):
        self._store: dict[str, tuple[Any, float]] = {}
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (value, time.monotonic() + self._ttl)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)


analytics_cache = TTLCache(ttl_seconds=settings.analytics_cache_ttl)

# ---------------------------------------------------------------------------
# MongoDB Client — initialized during application lifespan
# ---------------------------------------------------------------------------

class Database:
    client: Optional[AsyncIOMotorClient] = None

    @classmethod
    def get_db(cls):
        return cls.client[settings.mongodb_db]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage Motor client lifecycle — connect on startup, close on shutdown."""
    logger.info("Connecting to MongoDB", uri=settings.mongodb_uri)
    Database.client = AsyncIOMotorClient(settings.mongodb_uri)
    # Verify connection
    await Database.client.admin.command("ping")
    logger.info("MongoDB connected successfully")

    # Ensure indexes on startup
    await ensure_indexes()

    yield  # Application runs here

    logger.info("Closing MongoDB connection")
    Database.client.close()


async def ensure_indexes():
    """
    Create all required indexes.
    Called once at startup — idempotent (Motor skips existing indexes).
    """
    db = Database.get_db()
    await db.users.create_index("email", unique=True)
    await db.shipments.create_index("tracking_id", unique=True)
    await db.shipments.create_index([("status", 1), ("created_at", -1)])
    await db.vehicles.create_index("registration_number", unique=True)
    # 2dsphere index for geospatial shipment location queries
    await db.shipments.create_index([("current_location", "2dsphere")])
    logger.info("Database indexes verified")


def get_db():
    """FastAPI dependency — yields the database handle."""
    return Database.get_db()

# ---------------------------------------------------------------------------
# Custom Exceptions — structured error responses
# ---------------------------------------------------------------------------

class LogisticsBaseException(HTTPException):
    """
    Base class for all domain exceptions.
    Carries a machine-readable error_code alongside the HTTP status and message.
    """

    def __init__(self, status_code: int, error_code: str, message: str):
        self.error_code = error_code
        self.message = message
        super().__init__(status_code=status_code, detail=message)


class NotFoundError(LogisticsBaseException):
    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="NOT_FOUND",
            message=f"{resource} with id '{resource_id}' was not found.",
        )


class ForbiddenError(LogisticsBaseException):
    def __init__(self, message: str = "You do not have permission to perform this action."):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="FORBIDDEN",
            message=message,
        )


class ConflictError(LogisticsBaseException):
    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            error_code="CONFLICT",
            message=message,
        )


class ValidationError(LogisticsBaseException):
    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="VALIDATION_ERROR",
            message=message,
        )

# ---------------------------------------------------------------------------
# Standard API Response Envelope
# ---------------------------------------------------------------------------

def success_response(data: Any, meta: Optional[dict] = None) -> dict:
    """Wrap successful payloads in the standard envelope."""
    response = {"success": True, "data": data}
    if meta:
        response["meta"] = meta
    return response


def error_response(code: str, message: str, details: Optional[list] = None) -> dict:
    """Wrap error payloads in the standard envelope."""
    err = {"code": code, "message": message}
    if details:
        err["details"] = details
    return {"success": False, "error": err}

# ---------------------------------------------------------------------------
# Input Sanitization — strips HTML / script tags to prevent XSS
# ---------------------------------------------------------------------------

_SCRIPT_BLOCK_RE = re.compile(
    r"<(script|style)[^>]*>.*?</(script|style)>", re.IGNORECASE | re.DOTALL
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_JAVASCRIPT_URI_RE = re.compile(r"javascript\s*:", re.IGNORECASE)


def sanitize_string(value: str) -> str:
    """
    Remove script/style blocks (including their content), remaining HTML tags,
    and javascript: URI schemes from user-supplied strings.
    Applied via Pydantic field_validator on every string field to prevent XSS.
    """
    # First pass: strip entire script/style blocks with their content
    cleaned = _SCRIPT_BLOCK_RE.sub("", value)
    # Second pass: strip any remaining HTML tags
    cleaned = _HTML_TAG_RE.sub("", cleaned)
    # Third pass: strip javascript: URI schemes
    cleaned = _JAVASCRIPT_URI_RE.sub("", cleaned)
    return cleaned.strip()

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class UserRole(str, Enum):
    ADMIN = "admin"
    DISPATCHER = "dispatcher"
    DRIVER = "driver"
    CUSTOMER = "customer"


class ShipmentStatus(str, Enum):
    PENDING = "pending"
    PICKED_UP = "picked_up"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    DELAYED = "delayed"


class VehicleType(str, Enum):
    MOTORCYCLE = "motorcycle"
    VAN = "van"
    TRUCK = "truck"
    HEAVY_FREIGHT = "heavy_freight"


class VehicleStatus(str, Enum):
    AVAILABLE = "available"
    IN_USE = "in_use"
    MAINTENANCE = "maintenance"
    DECOMMISSIONED = "decommissioned"


class DriverStatus(str, Enum):
    AVAILABLE = "available"
    ON_DUTY = "on_duty"
    OFF_DUTY = "off_duty"
    ON_LEAVE = "on_leave"


class NotificationType(str, Enum):
    SHIPMENT_UPDATE = "shipment_update"
    ASSIGNMENT = "assignment"
    ALERT = "alert"
    SYSTEM = "system"

# ---------------------------------------------------------------------------
# Cost Estimation — per vehicle type, per km
# ---------------------------------------------------------------------------

VEHICLE_RATE_PER_KM: dict[VehicleType, float] = {
    VehicleType.MOTORCYCLE: 0.5,
    VehicleType.VAN: 1.2,
    VehicleType.TRUCK: 2.0,
    VehicleType.HEAVY_FREIGHT: 3.5,
}

VEHICLE_BASE_FARE: dict[VehicleType, float] = {
    VehicleType.MOTORCYCLE: 5.0,
    VehicleType.VAN: 15.0,
    VehicleType.TRUCK: 30.0,
    VehicleType.HEAVY_FREIGHT: 60.0,
}


def estimate_cost(distance_km: float, vehicle_type: VehicleType) -> dict:
    """
    Calculate shipment cost breakdown.
    Returns base_fare, distance_charge, total, and estimated_hours.
    """
    base = VEHICLE_BASE_FARE[vehicle_type]
    distance_charge = round(distance_km * VEHICLE_RATE_PER_KM[vehicle_type], 2)
    total = round(base + distance_charge, 2)
    # Rough transit estimate: average 60 km/h
    estimated_hours = round(distance_km / 60, 1)
    return {
        "base_fare": base,
        "distance_charge": distance_charge,
        "total": total,
        "currency": "USD",
        "estimated_hours": estimated_hours,
    }

# ---------------------------------------------------------------------------
# Pydantic Models — Request / Response Schemas
# ---------------------------------------------------------------------------

# ── User / Auth ──────────────────────────────────────────────────────────────

class UserRegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    role: UserRole = UserRole.CUSTOMER

    @field_validator("full_name")
    @classmethod
    def sanitize_name(cls, v):
        return sanitize_string(v)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v):
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit.")
        return v


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


# ── Shipment ──────────────────────────────────────────────────────────────────

class GeoPoint(BaseModel):
    """GeoJSON Point — used for location storage and 2dsphere indexing."""
    type: str = "Point"
    coordinates: list[float] = Field(
        ..., description="[longitude, latitude]", min_length=2, max_length=2
    )


class AddressInput(BaseModel):
    address: str = Field(..., min_length=5, max_length=300)
    coordinates: GeoPoint  # longitude, latitude from geocoding API

    @field_validator("address")
    @classmethod
    def sanitize_address(cls, v):
        return sanitize_string(v)


class ShipmentCreateRequest(BaseModel):
    origin: AddressInput
    destination: AddressInput
    vehicle_type: VehicleType
    distance_km: float = Field(..., gt=0, le=10_000)
    # Optional customer notes
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator("notes")
    @classmethod
    def sanitize_notes(cls, v):
        return sanitize_string(v) if v else v


class LocationUpdateRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ShipmentStatusUpdateRequest(BaseModel):
    status: ShipmentStatus


# ── Vehicle ───────────────────────────────────────────────────────────────────

class VehicleCreateRequest(BaseModel):
    registration_number: str = Field(..., min_length=3, max_length=20)
    vehicle_type: VehicleType
    capacity_kg: float = Field(..., gt=0, le=50_000)

    @field_validator("registration_number")
    @classmethod
    def sanitize_registration(cls, v):
        return sanitize_string(v).upper()


class VehicleUpdateRequest(BaseModel):
    vehicle_type: Optional[VehicleType] = None
    capacity_kg: Optional[float] = Field(None, gt=0, le=50_000)
    status: Optional[VehicleStatus] = None


# ── Driver ────────────────────────────────────────────────────────────────────

class DriverCreateRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    phone: str = Field(..., min_length=7, max_length=20)
    license_number: str = Field(..., min_length=5, max_length=30)
    license_expiry: datetime

    @field_validator("full_name", "license_number")
    @classmethod
    def sanitize_fields(cls, v):
        return sanitize_string(v)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        # Allow optional leading + for country code, then digits only
        cleaned = v.replace(" ", "").replace("-", "")
        if not re.match(r"^\+?\d{7,15}$", cleaned):
            raise ValueError("Phone must be 7–15 digits, optionally prefixed with +.")
        return cleaned


class DriverAssignRequest(BaseModel):
    driver_id: str
    shipment_id: str


# ── Route ─────────────────────────────────────────────────────────────────────

class RouteOptimizeRequest(BaseModel):
    driver_id: str
    shipment_ids: list[str] = Field(..., min_length=1, max_length=20)


# ── Contact ───────────────────────────────────────────────────────────────────

class ContactSubmissionRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    company_name: Optional[str] = Field(None, max_length=100)
    inquiry_type: str = Field(..., pattern="^(Sales|Support|Partnership|Press)$")
    message: str = Field(..., min_length=10, max_length=500)

    @field_validator("full_name", "company_name", "message")
    @classmethod
    def sanitize_text(cls, v):
        return sanitize_string(v) if v else v


# ── Analytics ─────────────────────────────────────────────────────────────────

class AnalyticsSummaryResponse(BaseModel):
    total_shipments: int
    total_delivered: int
    on_time_delivery_pct: float
    avg_transit_hours: float
    total_revenue_usd: float
    period_start: datetime
    period_end: datetime

# ---------------------------------------------------------------------------
# JWT Authentication
# ---------------------------------------------------------------------------

def create_access_token(user_id: str, email: str, role: str) -> str:
    """Sign a JWT containing user identity and role."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),  # unique token ID — enables revocation lists
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Decode and verify a JWT; raises HTTPException on any failure."""
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(request: Request, db=Depends(get_db)) -> dict:
    """
    FastAPI dependency — extracts JWT from Authorization header,
    validates it, and fetches the user document from MongoDB.
    Attaches the full user dict (including role) to the request context.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing or malformed.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth_header[len("Bearer "):]
    payload = decode_access_token(token)
    user_id = payload.get("sub")

    user = await db.users.find_one({"_id": user_id, "is_active": True})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or has been deactivated.",
        )

    # Bind request-scoped logging context for all downstream log lines
    structlog.contextvars.bind_contextvars(
        user_id=user_id,
        role=user["role"],
    )
    return user


def require_roles(*allowed_roles: UserRole):
    """
    FastAPI dependency factory — returns a dependency that enforces
    that the authenticated user's role is in `allowed_roles`.
    Usage: Depends(require_roles(UserRole.ADMIN, UserRole.DISPATCHER))
    """
    async def _check(current_user: dict = Depends(get_current_user)):
        if current_user["role"] not in [r.value for r in allowed_roles]:
            raise ForbiddenError(
                f"This action requires one of the following roles: "
                f"{[r.value for r in allowed_roles]}."
            )
        return current_user
    return _check

# ---------------------------------------------------------------------------
# Password Utilities
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Email Service — async, non-blocking via BackgroundTasks
# ---------------------------------------------------------------------------

async def send_email(to: str, subject: str, html_body: str, text_body: str = "") -> bool:
    """
    Send an HTML email via SMTP using aiosmtplib.
    Falls back to plain text if HTML rendering is unavailable on the client.
    Returns True on success, False on failure — caller logs accordingly.
    """
    try:
        import aiosmtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        message = MIMEMultipart("alternative")
        message["From"] = settings.email_from
        message["To"] = to
        message["Subject"] = subject

        # Plain text fallback must be attached first per RFC 2046
        if text_body:
            message.attach(MIMEText(text_body, "plain"))
        message.attach(MIMEText(html_body, "html"))

        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True,
        )
        logger.info("Email sent", to=to, subject=subject)
        return True
    except Exception as exc:
        # Log failure without raising — email errors must never crash API responses
        logger.error("Email delivery failed", to=to, subject=subject, error=str(exc))
        return False


def _shipment_booked_email(customer_email: str, tracking_id: str, pickup_time: str) -> None:
    """Background task: notify customer on successful booking."""
    asyncio.run(
        send_email(
            to=customer_email,
            subject="Your Shipment Has Been Booked",
            html_body=(
                f"<h2>Shipment Confirmed</h2>"
                f"<p>Your tracking number is: <strong>{tracking_id}</strong></p>"
                f"<p>Estimated pickup: {pickup_time}</p>"
            ),
            text_body=f"Tracking: {tracking_id}. Estimated pickup: {pickup_time}.",
        )
    )


def _shipment_dispatched_email(
    customer_email: str, driver_email: str, tracking_id: str
) -> None:
    """Background task: notify customer and driver on dispatch."""
    for recipient in [customer_email, driver_email]:
        asyncio.run(
            send_email(
                to=recipient,
                subject=f"Shipment {tracking_id} Dispatched",
                html_body=(
                    f"<h2>Your shipment is on its way!</h2>"
                    f"<p>Tracking ID: <strong>{tracking_id}</strong></p>"
                ),
                text_body=f"Shipment {tracking_id} has been dispatched.",
            )
        )


def _shipment_delivered_email(customer_email: str, tracking_id: str) -> None:
    """Background task: delivery confirmation to customer."""
    asyncio.run(
        send_email(
            to=customer_email,
            subject=f"Shipment {tracking_id} Delivered",
            html_body=(
                f"<h2>Delivery Complete</h2>"
                f"<p>Tracking ID <strong>{tracking_id}</strong> has been delivered.</p>"
                f"<p><a href='https://logistics.example.com/feedback'>Leave feedback</a></p>"
            ),
            text_body=f"Shipment {tracking_id} delivered. Feedback: https://logistics.example.com/feedback",
        )
    )


def _shipment_delayed_email(dispatcher_email: str, tracking_id: str) -> None:
    """Background task: delay alert to dispatcher."""
    asyncio.run(
        send_email(
            to=dispatcher_email,
            subject=f"⚠️ Shipment {tracking_id} Delayed",
            html_body=(
                f"<h2>Delay Alert</h2>"
                f"<p>Shipment <strong>{tracking_id}</strong> has exceeded its estimated delivery window.</p>"
            ),
            text_body=f"Shipment {tracking_id} is delayed.",
        )
    )


def _contact_notification_email(owner_email: str, submission: dict) -> None:
    """Background task: notify platform owner of a new contact form submission."""
    asyncio.run(
        send_email(
            to=owner_email,
            subject=f"New Contact Form: {submission['inquiry_type']} from {submission['full_name']}",
            html_body=(
                f"<h2>New Contact Submission</h2>"
                f"<p><strong>Name:</strong> {submission['full_name']}</p>"
                f"<p><strong>Email:</strong> {submission['email']}</p>"
                f"<p><strong>Company:</strong> {submission.get('company_name', 'N/A')}</p>"
                f"<p><strong>Inquiry:</strong> {submission['inquiry_type']}</p>"
                f"<p><strong>Message:</strong> {submission['message']}</p>"
                f"<p><strong>Submitted:</strong> {submission['created_at']}</p>"
            ),
            text_body=str(submission),
        )
    )

# ---------------------------------------------------------------------------
# Notification Helper — creates in-app notification documents
# ---------------------------------------------------------------------------

async def create_notification(
    db,
    user_id: str,
    notification_type: NotificationType,
    message: str,
) -> None:
    """Insert a notification document for the target user."""
    doc = {
        "_id": str(uuid.uuid4()),
        "user_id": user_id,
        "type": notification_type.value,
        "message": message,
        "is_read": False,
        "created_at": datetime.now(timezone.utc),
    }
    await db.notifications.insert_one(doc)

# ---------------------------------------------------------------------------
# Rate Limiter Setup
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)

# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Transportation & Logistics API",
    description="Production-grade logistics platform — FastAPI + MongoDB",
    version="1.0.0",
    lifespan=lifespan,
)

# Rate limit error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — only allow configured frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request / Response Logging Middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """
    Log every request with request ID, method, path, status code, and latency.
    The request ID is propagated in the response header for client-side tracing.
    """
    request_id = str(uuid.uuid4())
    start = time.perf_counter()

    # Bind request-scoped context so all log lines in this request carry these fields
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
    )

    response = await call_next(request)
    latency_ms = round((time.perf_counter() - start) * 1000, 2)

    logger.info(
        "Request completed",
        status_code=response.status_code,
        latency_ms=latency_ms,
    )
    response.headers["X-Request-ID"] = request_id
    return response

# ---------------------------------------------------------------------------
# Global Exception Handler — never expose internal tracebacks to clients
# ---------------------------------------------------------------------------

@app.exception_handler(LogisticsBaseException)
async def logistics_exception_handler(request: Request, exc: LogisticsBaseException):
    logger.warning(
        "Domain exception",
        error_code=exc.error_code,
        message=exc.message,
        status_code=exc.status_code,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(exc.error_code, exc.message),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response(
            "INTERNAL_SERVER_ERROR",
            "An unexpected error occurred. Please try again later.",
        ),
    )

# ===========================================================================
# ROUTE DEFINITIONS
# ===========================================================================

# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
async def health_check():
    """Simple liveness probe — used by load balancers and container orchestrators."""
    return success_response({"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()})

# ---------------------------------------------------------------------------
# Auth Routes — rate-limited to prevent brute-force
# ---------------------------------------------------------------------------

@app.post("/api/v1/auth/register", tags=["Auth"])
@limiter.limit("20/minute")
async def register(
    request: Request,
    body: UserRegisterRequest,
    db=Depends(get_db),
):
    """
    Register a new user account.
    Passwords are bcrypt-hashed before storage and never returned.
    """
    # Check for duplicate email
    existing = await db.users.find_one({"email": body.email})
    if existing:
        raise ConflictError(f"An account with email '{body.email}' already exists.")

    user_id = str(uuid.uuid4())
    doc = {
        "_id": user_id,
        "full_name": body.full_name,
        "email": body.email,
        "hashed_password": hash_password(body.password),
        "role": body.role.value,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await db.users.insert_one(doc)
    logger.info("User registered", user_id=user_id, role=body.role.value)

    token = create_access_token(user_id, body.email, body.role.value)
    return success_response(
        TokenResponse(
            access_token=token,
            expires_in=settings.jwt_expire_minutes * 60,
        ).model_dump()
    )


@app.post("/api/v1/auth/login", tags=["Auth"])
@limiter.limit("20/minute")
async def login(
    request: Request,
    body: UserLoginRequest,
    db=Depends(get_db),
):
    """Authenticate a user and return a signed JWT."""
    user = await db.users.find_one({"email": body.email, "is_active": True})
    if not user or not verify_password(body.password, user["hashed_password"]):
        # Use generic message to prevent email enumeration attacks
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    token = create_access_token(user["_id"], user["email"], user["role"])
    logger.info("User logged in", user_id=user["_id"])
    return success_response(
        TokenResponse(
            access_token=token,
            expires_in=settings.jwt_expire_minutes * 60,
        ).model_dump()
    )

# ---------------------------------------------------------------------------
# Shipment Routes
# ---------------------------------------------------------------------------

@app.post("/api/v1/shipments", tags=["Shipments"])
@limiter.limit("20/minute")
async def create_shipment(
    request: Request,
    body: ShipmentCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_roles(UserRole.CUSTOMER, UserRole.ADMIN)),
    db=Depends(get_db),
):
    """
    Book a new shipment.
    Generates a UUID tracking ID, calculates cost, stores with status 'pending',
    and triggers a confirmation email to the customer via BackgroundTasks.
    """
    tracking_id = f"TRK-{uuid.uuid4().hex[:10].upper()}"
    cost = estimate_cost(body.distance_km, body.vehicle_type)
    now = datetime.now(timezone.utc)
    estimated_pickup = (now + timedelta(hours=1)).isoformat()

    doc = {
        "_id": str(uuid.uuid4()),
        "tracking_id": tracking_id,
        "customer_id": current_user["_id"],
        "origin": body.origin.model_dump(),
        "destination": body.destination.model_dump(),
        "vehicle_type": body.vehicle_type.value,
        "distance_km": body.distance_km,
        "status": ShipmentStatus.PENDING.value,
        "assigned_driver_id": None,
        "current_location": body.origin.coordinates.model_dump(),
        "location_history": [
            {"coordinates": body.origin.coordinates.coordinates, "timestamp": now}
        ],
        "cost": cost,
        "notes": body.notes,
        "created_at": now,
        "updated_at": now,
    }
    await db.shipments.insert_one(doc)

    # Non-blocking email — does not delay the API response
    background_tasks.add_task(
        _shipment_booked_email,
        current_user["email"],
        tracking_id,
        estimated_pickup,
    )

    # In-app notification for the customer
    await create_notification(
        db,
        current_user["_id"],
        NotificationType.SHIPMENT_UPDATE,
        f"Your shipment {tracking_id} has been booked successfully.",
    )

    logger.info("Shipment created", tracking_id=tracking_id)
    return success_response({
        "order_id": doc["_id"],
        "tracking_id": tracking_id,
        "cost": cost,
        "estimated_pickup": estimated_pickup,
        "status": ShipmentStatus.PENDING.value,
    })


@app.get("/api/v1/shipments", tags=["Shipments"])
async def list_shipments(
    request: Request,
    status_filter: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(require_roles(
        UserRole.ADMIN, UserRole.DISPATCHER, UserRole.CUSTOMER
    )),
    db=Depends(get_db),
):
    """
    List shipments.
    - Admins and Dispatchers see all shipments.
    - Customers see only their own shipments.
    Supports status filtering and pagination.
    """
    query: dict = {}

    # Customers are restricted to their own shipments
    if current_user["role"] == UserRole.CUSTOMER.value:
        query["customer_id"] = current_user["_id"]

    # Optional status filter — validate against enum to prevent injection
    if status_filter:
        try:
            ShipmentStatus(status_filter)
            query["status"] = status_filter
        except ValueError:
            raise ValidationError(
                f"Invalid status '{status_filter}'. Valid values: "
                f"{[s.value for s in ShipmentStatus]}"
            )

    skip = (page - 1) * page_size
    total = await db.shipments.count_documents(query)
    cursor = db.shipments.find(query, {"location_history": 0}).skip(skip).limit(page_size)
    shipments = await cursor.to_list(length=page_size)

    # Convert ObjectId / datetime to serializable types
    for s in shipments:
        s["created_at"] = s["created_at"].isoformat()
        s["updated_at"] = s["updated_at"].isoformat()

    return success_response(
        shipments,
        meta={"page": page, "page_size": page_size, "total": total},
    )


@app.get("/api/v1/shipments/{tracking_id}/status", tags=["Shipments"])
async def get_shipment_status(
    tracking_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Polling endpoint for the real-time tracking view.
    Returns current status, last known coordinates, driver info, and ETA.
    Frontend polls this every 10 seconds with tab-visibility debouncing.
    """
    shipment = await db.shipments.find_one(
        {"tracking_id": tracking_id},
        {"_id": 1, "tracking_id": 1, "status": 1, "current_location": 1,
         "assigned_driver_id": 1, "cost": 1, "updated_at": 1},
    )
    if not shipment:
        raise NotFoundError("Shipment", tracking_id)

    # Customers may only query their own shipments
    if current_user["role"] == UserRole.CUSTOMER.value:
        owner_check = await db.shipments.find_one(
            {"tracking_id": tracking_id, "customer_id": current_user["_id"]}
        )
        if not owner_check:
            raise ForbiddenError()

    # Fetch driver info if assigned
    driver_info = None
    if shipment.get("assigned_driver_id"):
        driver = await db.drivers.find_one(
            {"_id": shipment["assigned_driver_id"]},
            {"full_name": 1, "phone": 1},
        )
        if driver:
            driver_info = {"name": driver["full_name"], "phone": driver["phone"]}

    # Simple ETA: fixed placeholder — replace with routing API call in production
    eta = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

    return success_response({
        "tracking_id": tracking_id,
        "status": shipment["status"],
        "current_location": shipment.get("current_location"),
        "driver": driver_info,
        "eta": eta,
        "last_updated": shipment["updated_at"].isoformat(),
    })


@app.patch("/api/v1/shipments/{tracking_id}/location", tags=["Shipments"])
async def update_shipment_location(
    tracking_id: str,
    body: LocationUpdateRequest,
    current_user: dict = Depends(require_roles(UserRole.DRIVER, UserRole.ADMIN)),
    db=Depends(get_db),
):
    """
    Accept GPS location push from the driver's mobile device.
    Appends to location_history for full replay capability.
    Only the assigned driver or an admin may call this endpoint.
    """
    shipment = await db.shipments.find_one({"tracking_id": tracking_id})
    if not shipment:
        raise NotFoundError("Shipment", tracking_id)

    # Drivers may only update shipments assigned to them
    if (
        current_user["role"] == UserRole.DRIVER.value
        and shipment.get("assigned_driver_id") != current_user["_id"]
    ):
        raise ForbiddenError("You are not assigned to this shipment.")

    # Reject location updates on terminal statuses
    if shipment["status"] in [ShipmentStatus.DELIVERED.value, ShipmentStatus.CANCELLED.value]:
        raise ValidationError(
            f"Cannot update location for a shipment with status '{shipment['status']}'."
        )

    new_point = {"type": "Point", "coordinates": [body.longitude, body.latitude]}
    history_entry = {
        "coordinates": [body.longitude, body.latitude],
        "timestamp": body.timestamp,
    }

    await db.shipments.update_one(
        {"tracking_id": tracking_id},
        {
            "$set": {
                "current_location": new_point,
                "updated_at": datetime.now(timezone.utc),
            },
            "$push": {"location_history": history_entry},
        },
    )
    return success_response({"tracking_id": tracking_id, "location_updated": True})


@app.patch("/api/v1/shipments/{tracking_id}/status", tags=["Shipments"])
async def update_shipment_status(
    tracking_id: str,
    body: ShipmentStatusUpdateRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_roles(
        UserRole.ADMIN, UserRole.DISPATCHER, UserRole.DRIVER
    )),
    db=Depends(get_db),
):
    """
    Update shipment status and trigger appropriate email notifications.
    Enforces valid status transitions to prevent data integrity issues.
    """
    shipment = await db.shipments.find_one({"tracking_id": tracking_id})
    if not shipment:
        raise NotFoundError("Shipment", tracking_id)

    # Define allowed forward transitions
    valid_transitions: dict[str, list[str]] = {
        ShipmentStatus.PENDING.value: [ShipmentStatus.PICKED_UP.value, ShipmentStatus.CANCELLED.value],
        ShipmentStatus.PICKED_UP.value: [ShipmentStatus.IN_TRANSIT.value],
        ShipmentStatus.IN_TRANSIT.value: [ShipmentStatus.OUT_FOR_DELIVERY.value, ShipmentStatus.DELAYED.value],
        ShipmentStatus.OUT_FOR_DELIVERY.value: [ShipmentStatus.DELIVERED.value, ShipmentStatus.DELAYED.value],
        ShipmentStatus.DELAYED.value: [ShipmentStatus.IN_TRANSIT.value, ShipmentStatus.OUT_FOR_DELIVERY.value],
        ShipmentStatus.DELIVERED.value: [],  # Terminal state
        ShipmentStatus.CANCELLED.value: [],  # Terminal state
    }

    current_status = shipment["status"]
    allowed = valid_transitions.get(current_status, [])
    if body.status.value not in allowed:
        raise ValidationError(
            f"Cannot transition from '{current_status}' to '{body.status.value}'. "
            f"Allowed transitions: {allowed}"
        )

    await db.shipments.update_one(
        {"tracking_id": tracking_id},
        {"$set": {"status": body.status.value, "updated_at": datetime.now(timezone.utc)}},
    )

    # Fetch customer email for notifications
    customer = await db.users.find_one({"_id": shipment["customer_id"]}, {"email": 1})
    customer_email = customer["email"] if customer else None

    # Trigger lifecycle emails via BackgroundTasks — never blocks the response
    if body.status == ShipmentStatus.DELIVERED and customer_email:
        background_tasks.add_task(_shipment_delivered_email, customer_email, tracking_id)

    elif body.status == ShipmentStatus.DELAYED:
        # Alert the dispatcher — find any dispatcher user
        dispatcher = await db.users.find_one({"role": UserRole.DISPATCHER.value}, {"email": 1})
        if dispatcher:
            background_tasks.add_task(
                _shipment_delayed_email, dispatcher["email"], tracking_id
            )

    # In-app notification for the customer
    if customer_email:
        await create_notification(
            db,
            shipment["customer_id"],
            NotificationType.SHIPMENT_UPDATE,
            f"Shipment {tracking_id} status updated to {body.status.value.replace('_', ' ').title()}.",
        )

    logger.info("Shipment status updated", tracking_id=tracking_id, new_status=body.status.value)
    return success_response({"tracking_id": tracking_id, "status": body.status.value})

# ---------------------------------------------------------------------------
# Fleet / Vehicle Routes
# ---------------------------------------------------------------------------

@app.post("/api/v1/fleet/vehicles", tags=["Fleet"])
async def add_vehicle(
    body: VehicleCreateRequest,
    current_user: dict = Depends(require_roles(UserRole.ADMIN)),
    db=Depends(get_db),
):
    """Register a new vehicle. Registration number must be unique."""
    existing = await db.vehicles.find_one(
        {"registration_number": body.registration_number}
    )
    if existing:
        raise ConflictError(
            f"Vehicle with registration '{body.registration_number}' already exists."
        )

    vehicle_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc = {
        "_id": vehicle_id,
        "registration_number": body.registration_number,
        "vehicle_type": body.vehicle_type.value,
        "capacity_kg": body.capacity_kg,
        "status": VehicleStatus.AVAILABLE.value,
        "assigned_driver_id": None,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    await db.vehicles.insert_one(doc)
    logger.info("Vehicle registered", vehicle_id=vehicle_id)
    return success_response({"vehicle_id": vehicle_id, "registration_number": body.registration_number})


@app.get("/api/v1/fleet/vehicles", tags=["Fleet"])
async def list_vehicles(
    status_filter: Optional[str] = None,
    vehicle_type: Optional[str] = None,
    current_user: dict = Depends(require_roles(UserRole.ADMIN, UserRole.DISPATCHER)),
    db=Depends(get_db),
):
    """
    List all active vehicles with optional status and type filters.
    Also returns summary counters for the dashboard animated counter widgets.
    """
    base_query = {"is_active": True}

    if status_filter:
        try:
            VehicleStatus(status_filter)
            base_query["status"] = status_filter
        except ValueError:
            raise ValidationError(f"Invalid vehicle status: {status_filter}")

    if vehicle_type:
        try:
            VehicleType(vehicle_type)
            base_query["vehicle_type"] = vehicle_type
        except ValueError:
            raise ValidationError(f"Invalid vehicle type: {vehicle_type}")

    vehicles = await db.vehicles.find(base_query).to_list(length=500)

    # Compute summary counters in a single aggregation to avoid N+1 queries
    summary_pipeline = [
        {"$match": {"is_active": True}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    summary_raw = await db.vehicles.aggregate(summary_pipeline).to_list(length=10)
    summary = {item["_id"]: item["count"] for item in summary_raw}

    for v in vehicles:
        v["created_at"] = v["created_at"].isoformat()
        v["updated_at"] = v["updated_at"].isoformat()

    return success_response(
        vehicles,
        meta={
            "total": sum(summary.values()),
            "available": summary.get(VehicleStatus.AVAILABLE.value, 0),
            "in_use": summary.get(VehicleStatus.IN_USE.value, 0),
            "maintenance": summary.get(VehicleStatus.MAINTENANCE.value, 0),
        },
    )


@app.put("/api/v1/fleet/vehicles/{vehicle_id}", tags=["Fleet"])
async def update_vehicle(
    vehicle_id: str,
    body: VehicleUpdateRequest,
    current_user: dict = Depends(require_roles(UserRole.ADMIN)),
    db=Depends(get_db),
):
    """Update vehicle details. Only provided fields are changed (partial update)."""
    vehicle = await db.vehicles.find_one({"_id": vehicle_id, "is_active": True})
    if not vehicle:
        raise NotFoundError("Vehicle", vehicle_id)

    update_fields: dict = {"updated_at": datetime.now(timezone.utc)}
    if body.vehicle_type is not None:
        update_fields["vehicle_type"] = body.vehicle_type.value
    if body.capacity_kg is not None:
        update_fields["capacity_kg"] = body.capacity_kg
    if body.status is not None:
        update_fields["status"] = body.status.value

    await db.vehicles.update_one({"_id": vehicle_id}, {"$set": update_fields})
    return success_response({"vehicle_id": vehicle_id, "updated_fields": list(update_fields.keys())})


@app.delete("/api/v1/fleet/vehicles/{vehicle_id}", tags=["Fleet"])
async def deactivate_vehicle(
    vehicle_id: str,
    current_user: dict = Depends(require_roles(UserRole.ADMIN)),
    db=Depends(get_db),
):
    """
    Soft-delete a vehicle by setting is_active=False.
    Documents are never permanently removed to preserve audit history.
    """
    vehicle = await db.vehicles.find_one({"_id": vehicle_id, "is_active": True})
    if not vehicle:
        raise NotFoundError("Vehicle", vehicle_id)

    # Prevent deactivating a vehicle that has an active driver assigned
    if vehicle.get("assigned_driver_id"):
        raise ConflictError(
            "Cannot deactivate a vehicle with an assigned driver. "
            "Unassign the driver first."
        )

    await db.vehicles.update_one(
        {"_id": vehicle_id},
        {"$set": {"is_active": False, "status": VehicleStatus.DECOMMISSIONED.value,
                  "updated_at": datetime.now(timezone.utc)}},
    )
    logger.info("Vehicle deactivated (soft-delete)", vehicle_id=vehicle_id)
    return success_response({"vehicle_id": vehicle_id, "deactivated": True})

# ---------------------------------------------------------------------------
# Driver Routes
# ---------------------------------------------------------------------------

@app.post("/api/v1/drivers", tags=["Drivers"])
async def register_driver(
    body: DriverCreateRequest,
    current_user: dict = Depends(require_roles(UserRole.ADMIN)),
    db=Depends(get_db),
):
    """Register a new driver profile. Email must be unique within the drivers collection."""
    existing = await db.drivers.find_one({"email": body.email})
    if existing:
        raise ConflictError(f"A driver with email '{body.email}' already exists.")

    driver_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc = {
        "_id": driver_id,
        "full_name": body.full_name,
        "email": body.email,
        "phone": body.phone,
        "license_number": body.license_number,
        "license_expiry": body.license_expiry,
        "status": DriverStatus.AVAILABLE.value,
        "assigned_vehicle_id": None,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    await db.drivers.insert_one(doc)
    logger.info("Driver registered", driver_id=driver_id)
    return success_response({"driver_id": driver_id})


@app.get("/api/v1/drivers/available", tags=["Drivers"])
async def list_available_drivers(
    current_user: dict = Depends(require_roles(UserRole.ADMIN, UserRole.DISPATCHER)),
    db=Depends(get_db),
):
    """
    Return only drivers with 'available' status who have a valid vehicle assigned.
    Used to populate the dispatcher's driver assignment dropdown.
    """
    drivers = await db.drivers.find(
        {
            "status": DriverStatus.AVAILABLE.value,
            "assigned_vehicle_id": {"$ne": None},
            "is_active": True,
        },
        {"full_name": 1, "phone": 1, "assigned_vehicle_id": 1},
    ).to_list(length=100)

    return success_response(drivers)


@app.post("/api/v1/drivers/assign", tags=["Drivers"])
async def assign_driver_to_shipment(
    body: DriverAssignRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_roles(UserRole.ADMIN, UserRole.DISPATCHER)),
    db=Depends(get_db),
):
    """
    Assign an available driver to a pending shipment.
    Uses a MongoDB session + transaction to atomically update both the shipment
    and the driver's status — preventing race conditions under concurrent requests.
    """
    # Validate driver exists and is available
    driver = await db.drivers.find_one(
        {"_id": body.driver_id, "status": DriverStatus.AVAILABLE.value, "is_active": True}
    )
    if not driver:
        raise NotFoundError("Available driver", body.driver_id)

    # Validate shipment exists and is pending
    shipment = await db.shipments.find_one(
        {"_id": body.shipment_id, "status": ShipmentStatus.PENDING.value}
    )
    if not shipment:
        raise NotFoundError("Pending shipment", body.shipment_id)

    now = datetime.now(timezone.utc)

    # Atomic transaction — both writes succeed or both are rolled back
    async with await Database.client.start_session() as session:
        async with session.start_transaction():
            await db.shipments.update_one(
                {"_id": body.shipment_id},
                {
                    "$set": {
                        "assigned_driver_id": body.driver_id,
                        "status": ShipmentStatus.PICKED_UP.value,
                        "updated_at": now,
                    }
                },
                session=session,
            )
            await db.drivers.update_one(
                {"_id": body.driver_id},
                {"$set": {"status": DriverStatus.ON_DUTY.value, "updated_at": now}},
                session=session,
            )

    # Notify customer and driver of dispatch
    customer = await db.users.find_one({"_id": shipment["customer_id"]}, {"email": 1})
    if customer:
        background_tasks.add_task(
            _shipment_dispatched_email,
            customer["email"],
            driver["email"],
            shipment["tracking_id"],
        )

    await create_notification(
        db,
        body.driver_id,
        NotificationType.ASSIGNMENT,
        f"You have been assigned to shipment {shipment['tracking_id']}.",
    )

    logger.info(
        "Driver assigned to shipment",
        driver_id=body.driver_id,
        shipment_id=body.shipment_id,
    )
    return success_response({
        "shipment_id": body.shipment_id,
        "driver_id": body.driver_id,
        "status": ShipmentStatus.PICKED_UP.value,
    })

# ---------------------------------------------------------------------------
# Route Planning & Optimization
# ---------------------------------------------------------------------------

@app.post("/api/v1/routes/optimize", tags=["Routes"])
async def optimize_route(
    body: RouteOptimizeRequest,
    current_user: dict = Depends(require_roles(UserRole.ADMIN, UserRole.DISPATCHER)),
    db=Depends(get_db),
):
    """
    Calculate the optimal delivery sequence for a set of shipments and a driver.
    Calls the OpenRouteService Directions API with all waypoint coordinates.
    Stores the resulting route plan in the 'routes' collection.
    """
    driver = await db.drivers.find_one({"_id": body.driver_id, "is_active": True})
    if not driver:
        raise NotFoundError("Driver", body.driver_id)

    # Fetch all requested shipments and extract coordinates
    shipments = await db.shipments.find(
        {"_id": {"$in": body.shipment_ids}},
        {"tracking_id": 1, "destination": 1, "origin": 1},
    ).to_list(length=20)

    if len(shipments) != len(body.shipment_ids):
        raise ValidationError(
            "One or more shipment IDs not found. Verify all IDs before requesting optimization."
        )

    # Build waypoints: driver start → all destinations in submitted order
    # In production, apply TSP / VRPTW algorithm before calling the routing API
    waypoints = []
    if shipments:
        # Use the first shipment's origin as the starting point
        origin_coords = shipments[0]["origin"]["coordinates"]["coordinates"]
        waypoints.append(origin_coords)  # [lng, lat]

    for s in shipments:
        dest_coords = s["destination"]["coordinates"]["coordinates"]
        waypoints.append(dest_coords)

    # Call external routing API
    route_geometry = None
    total_distance_m = 0
    estimated_duration_s = 0

    if settings.routing_api_key and len(waypoints) >= 2:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    settings.routing_api_url,
                    headers={"Authorization": settings.routing_api_key},
                    json={"coordinates": waypoints},
                )
                response.raise_for_status()
                route_data = response.json()
                route = route_data["routes"][0]
                total_distance_m = route["summary"]["distance"]
                estimated_duration_s = route["summary"]["duration"]
                route_geometry = route.get("geometry")  # Encoded polyline or GeoJSON
        except (httpx.HTTPError, KeyError, IndexError) as exc:
            # Routing API failure is non-fatal — store route without geometry
            logger.warning("Routing API call failed", error=str(exc))

    route_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    route_doc = {
        "_id": route_id,
        "assigned_driver_id": body.driver_id,
        "shipment_sequence": [s["_id"] for s in shipments],
        "waypoints": waypoints,
        "total_distance_m": total_distance_m,
        "estimated_duration_s": estimated_duration_s,
        "route_geometry": route_geometry,
        "status": "planned",
        "created_by": current_user["_id"],
        "created_at": now,
        "updated_at": now,
    }
    await db.routes.insert_one(route_doc)

    logger.info("Route optimized", route_id=route_id, shipment_count=len(shipments))
    return success_response({
        "route_id": route_id,
        "driver_id": body.driver_id,
        "total_distance_m": total_distance_m,
        "estimated_duration_s": estimated_duration_s,
        "shipment_sequence": route_doc["shipment_sequence"],
        "waypoints": waypoints,
        "route_geometry": route_geometry,
    })

# ---------------------------------------------------------------------------
# Analytics & Reporting
# ---------------------------------------------------------------------------

@app.get("/api/v1/analytics/summary", tags=["Analytics"])
async def get_analytics_summary(
    start_date: str,
    end_date: str,
    current_user: dict = Depends(require_roles(UserRole.ADMIN, UserRole.DISPATCHER)),
    db=Depends(get_db),
):
    """
    Return aggregated KPIs for the analytics dashboard.
    Results are cached for 5 minutes (settings.analytics_cache_ttl) to prevent
    repeated heavy aggregation pipeline runs on every dashboard refresh.
    """
    # Validate date range format
    try:
        start = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValidationError("Invalid date format. Use ISO 8601 (e.g. 2024-01-01).")

    if start >= end:
        raise ValidationError("start_date must be before end_date.")

    cache_key = f"analytics:{start_date}:{end_date}"
    cached = analytics_cache.get(cache_key)
    if cached:
        logger.info("Analytics served from cache", cache_key=cache_key)
        return success_response(cached)

    # Aggregation pipeline — runs once per unique date range per cache TTL window
    pipeline = [
        {"$match": {"created_at": {"$gte": start, "$lte": end}}},
        {
            "$group": {
                "_id": None,
                "total_shipments": {"$sum": 1},
                "total_delivered": {
                    "$sum": {
                        "$cond": [{"$eq": ["$status", ShipmentStatus.DELIVERED.value]}, 1, 0]
                    }
                },
                "total_revenue": {"$sum": "$cost.total"},
                # Compute transit time as hours between created_at and last updated_at
                "avg_transit_seconds": {
                    "$avg": {
                        "$cond": [
                            {"$eq": ["$status", ShipmentStatus.DELIVERED.value]},
                            {
                                "$divide": [
                                    {"$subtract": ["$updated_at", "$created_at"]},
                                    1000,  # milliseconds → seconds
                                ]
                            },
                            None,
                        ]
                    }
                },
            }
        },
    ]

    results = await db.shipments.aggregate(pipeline).to_list(length=1)

    if results:
        r = results[0]
        total = r.get("total_shipments", 0)
        delivered = r.get("total_delivered", 0)
        on_time_pct = round((delivered / total * 100) if total > 0 else 0, 1)
        avg_transit_hours = round(
            (r.get("avg_transit_seconds") or 0) / 3600, 2
        )
        summary = {
            "total_shipments": total,
            "total_delivered": delivered,
            "on_time_delivery_pct": on_time_pct,
            "avg_transit_hours": avg_transit_hours,
            "total_revenue_usd": round(r.get("total_revenue") or 0, 2),
            "period_start": start_date,
            "period_end": end_date,
        }
    else:
        summary = {
            "total_shipments": 0,
            "total_delivered": 0,
            "on_time_delivery_pct": 0.0,
            "avg_transit_hours": 0.0,
            "total_revenue_usd": 0.0,
            "period_start": start_date,
            "period_end": end_date,
        }

    analytics_cache.set(cache_key, summary)
    return success_response(summary)


@app.get("/api/v1/analytics/shipments-per-day", tags=["Analytics"])
async def get_shipments_per_day(
    start_date: str,
    end_date: str,
    current_user: dict = Depends(require_roles(UserRole.ADMIN, UserRole.DISPATCHER)),
    db=Depends(get_db),
):
    """
    Daily shipment count series for the line chart on the analytics dashboard.
    Cached independently from the summary endpoint.
    """
    try:
        start = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValidationError("Invalid date format. Use ISO 8601.")

    cache_key = f"analytics:per-day:{start_date}:{end_date}"
    cached = analytics_cache.get(cache_key)
    if cached:
        return success_response(cached)

    pipeline = [
        {"$match": {"created_at": {"$gte": start, "$lte": end}}},
        {
            "$group": {
                "_id": {
                    "year": {"$year": "$created_at"},
                    "month": {"$month": "$created_at"},
                    "day": {"$dayOfMonth": "$created_at"},
                },
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id.year": 1, "_id.month": 1, "_id.day": 1}},
    ]
    raw = await db.shipments.aggregate(pipeline).to_list(length=366)
    series = [
        {
            "date": f"{r['_id']['year']}-{r['_id']['month']:02d}-{r['_id']['day']:02d}",
            "count": r["count"],
        }
        for r in raw
    ]

    analytics_cache.set(cache_key, series)
    return success_response(series)

# ---------------------------------------------------------------------------
# Notification Routes
# ---------------------------------------------------------------------------

@app.get("/api/v1/notifications", tags=["Notifications"])
async def list_notifications(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Return all notifications for the authenticated user, newest first."""
    notifications = await db.notifications.find(
        {"user_id": current_user["_id"]},
        sort=[("created_at", -1)],
    ).limit(50).to_list(length=50)

    unread_count = sum(1 for n in notifications if not n["is_read"])
    for n in notifications:
        n["created_at"] = n["created_at"].isoformat()

    return success_response(
        notifications,
        meta={"unread_count": unread_count},
    )


@app.patch("/api/v1/notifications/mark-all-read", tags=["Notifications"])
async def mark_all_notifications_read(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Mark all unread notifications as read for the authenticated user.
    Frontend applies an optimistic update before this call completes.
    """
    result = await db.notifications.update_many(
        {"user_id": current_user["_id"], "is_read": False},
        {"$set": {"is_read": True}},
    )
    return success_response({"marked_read": result.modified_count})

# ---------------------------------------------------------------------------
# Contact / Support Form
# ---------------------------------------------------------------------------

@app.post("/api/v1/contact", tags=["Contact"])
@limiter.limit("20/minute")
async def submit_contact_form(
    request: Request,
    body: ContactSubmissionRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
):
    """
    Handle public contact form submissions.
    Stores the submission in MongoDB and notifies the platform owner via email.
    No authentication required — rate-limited to prevent spam.
    """
    submission_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc = {
        "_id": submission_id,
        "full_name": body.full_name,
        "email": body.email,
        "company_name": body.company_name,
        "inquiry_type": body.inquiry_type,
        "message": body.message,
        "created_at": now,
    }
    await db.contact_submissions.insert_one(doc)

    # Notify owner asynchronously — does not delay the API response
    background_tasks.add_task(_contact_notification_email, settings.owner_email, {
        **doc,
        "created_at": now.isoformat(),
    })

    logger.info(
        "Contact form submitted",
        submission_id=submission_id,
        inquiry_type=body.inquiry_type,
    )
    return success_response({
        "submission_id": submission_id,
        "message": "Thank you for reaching out. We will get back to you within 1–2 business days.",
    })

# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "golden_response:app",
        host="0.0.0.0",
        port=8000,
        reload=True,      # Enable hot-reload in development
        log_level="info",
    )
