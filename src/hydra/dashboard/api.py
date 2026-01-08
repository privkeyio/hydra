"""FastAPI REST API for Hydra dashboard."""

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import jwt
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from hydra.dashboard.database import (
    AuditLog,
    Execution,
    Project,
    Ticket,
    User,
    get_db,
)
from hydra.dashboard.database import (
    Session as DBSession,
)
from hydra.token_tracker import TokenUsage, get_token_tracker

# Configuration
SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY", "hydra-dashboard-secret-key-change-in-production"
)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Security
security = HTTPBearer()


# Pydantic models for API
class UserCreate(BaseModel):
    """User creation schema."""

    username: str = Field(..., min_length=3, max_length=100)
    email: Optional[str] = None
    password: str = Field(..., min_length=8)
    is_admin: bool = False


class UserResponse(BaseModel):
    """User response schema."""

    id: int
    username: str
    email: Optional[str]
    is_active: bool
    is_admin: bool
    created_at: datetime
    last_login: Optional[datetime]

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    """Login request schema."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """Token response schema."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ProjectCreate(BaseModel):
    """Project creation schema."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    repository_url: Optional[str] = None
    settings: Dict[str, Any] = Field(default_factory=dict)


class ProjectResponse(BaseModel):
    """Project response schema."""

    id: int
    name: str
    description: Optional[str]
    repository_url: Optional[str]
    created_at: datetime
    updated_at: datetime
    is_active: bool
    settings: Dict[str, Any]
    ticket_count: int = 0
    session_count: int = 0

    class Config:
        from_attributes = True


class TicketCreate(BaseModel):
    """Ticket creation schema."""

    ticket_number: str
    title: str
    description: Optional[str] = None
    status: str = "TODO"
    priority: int = Field(default=5, ge=1, le=10)
    complexity: Optional[str] = None
    model: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)


class TicketUpdate(BaseModel):
    """Ticket update schema."""

    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = Field(None, ge=1, le=10)
    complexity: Optional[str] = None
    model: Optional[str] = None
    dependencies: Optional[List[str]] = None
    acceptance_criteria: Optional[List[str]] = None
    artifacts: Optional[List[Dict[str, Any]]] = None


class TicketResponse(BaseModel):
    """Ticket response schema."""

    id: int
    project_id: int
    ticket_number: str
    title: str
    description: Optional[str]
    status: str
    priority: int
    complexity: Optional[str]
    model: Optional[str]
    dependencies: List[str]
    acceptance_criteria: List[str]
    artifacts: List[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    execution_count: int = 0

    class Config:
        from_attributes = True


class ExecutionResponse(BaseModel):
    """Execution response schema."""

    id: int
    ticket_id: int
    session_id: Optional[int]
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    duration_seconds: Optional[int]
    tokens_used: Optional[int]
    cost_estimate: Optional[str]
    output: Optional[str]
    error: Optional[str]
    commands_executed: List[str]
    files_modified: List[str]

    class Config:
        from_attributes = True


class DashboardStats(BaseModel):
    """Dashboard statistics schema."""

    total_projects: int
    total_tickets: int
    tickets_by_status: Dict[str, int]
    total_executions: int
    total_sessions: int
    active_sessions: int
    total_tokens_used: int
    estimated_cost: str


class TokenUsageResponse(BaseModel):
    """Token usage response schema."""

    id: int
    timestamp: datetime
    provider: str
    model: str
    ticket_id: Optional[int]
    session_id: Optional[int]
    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_cost: float
    output_cost: float
    total_cost: float

    class Config:
        from_attributes = True


class TokenUsageReport(BaseModel):
    """Token usage report schema."""

    period: Dict[str, str]
    summary: Dict[str, Any]
    by_provider: Dict[str, Dict[str, Any]]
    by_model: Dict[str, Dict[str, Any]]
    by_ticket: Dict[str, Dict[str, Any]]
    hourly_usage: List[Dict[str, Any]]
    top_expensive_requests: List[Dict[str, Any]]


class TokenBudgetStatus(BaseModel):
    """Token budget status schema."""

    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_cost: float
    request_count: int
    budget_limit: float
    budget_remaining: float
    budget_percentage: float
    by_model: Dict[str, Dict[str, Any]]
    by_provider: Dict[str, Dict[str, Any]]


# Helper functions
def create_access_token(data: dict) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Verify JWT token."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
        )
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )


def get_current_user(
    token_data: dict = Depends(verify_token), db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user."""
    username = token_data.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )

    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Require admin privileges."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )
    return user


# Create FastAPI app
app = FastAPI(
    title="Hydra Dashboard API",
    description="REST API for Hydra agent orchestration dashboard",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create API routers
auth_router = APIRouter(prefix="/api/auth", tags=["Authentication"])
projects_router = APIRouter(prefix="/api/projects", tags=["Projects"])
tickets_router = APIRouter(prefix="/api/tickets", tags=["Tickets"])
executions_router = APIRouter(prefix="/api/executions", tags=["Executions"])
stats_router = APIRouter(prefix="/api/stats", tags=["Statistics"])
tokens_router = APIRouter(prefix="/api/tokens", tags=["Token Usage"])


# Authentication endpoints
@auth_router.post("/register", response_model=UserResponse)
def register_user(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user."""
    # Check if username exists
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists"
        )

    # Hash password (simplified - use bcrypt in production)
    import hashlib

    hashed_password = hashlib.sha256(user_data.password.encode()).hexdigest()

    # Create user
    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_password,
        is_admin=user_data.is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@auth_router.post("/login", response_model=TokenResponse)
def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    """Login and get access token."""
    # Verify credentials
    import hashlib

    hashed_password = hashlib.sha256(login_data.password.encode()).hexdigest()

    user = (
        db.query(User)
        .filter(
            User.username == login_data.username,
            User.hashed_password == hashed_password,
        )
        .first()
    )

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    # Update last login
    user.last_login = datetime.utcnow()
    db.commit()

    # Create token
    access_token = create_access_token({"sub": user.username})

    return TokenResponse(
        access_token=access_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# Project endpoints
@projects_router.get("/", response_model=List[ProjectResponse])
def list_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all projects."""
    projects = db.query(Project).offset(skip).limit(limit).all()

    # Add counts
    for project in projects:
        project.ticket_count = len(project.tickets)
        project.session_count = len(project.sessions)

    return projects


@projects_router.post("/", response_model=ProjectResponse)
def create_project(
    project_data: ProjectCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new project."""
    # Check if project name exists
    existing = db.query(Project).filter(Project.name == project_data.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project name already exists",
        )

    project = Project(**project_data.dict())
    db.add(project)
    db.commit()
    db.refresh(project)

    # Log action
    audit_log = AuditLog(
        user_id=user.id,
        action="create_project",
        resource_type="project",
        resource_id=project.id,
        details={"project_name": project.name},
    )
    db.add(audit_log)
    db.commit()

    return project


@projects_router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get project details."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    project.ticket_count = len(project.tickets)
    project.session_count = len(project.sessions)

    return project


# Ticket endpoints
@tickets_router.get("/", response_model=List[TicketResponse])
def list_tickets(
    project_id: Optional[int] = None,
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List tickets with optional filters."""
    query = db.query(Ticket)

    if project_id:
        query = query.filter(Ticket.project_id == project_id)
    if status:
        query = query.filter(Ticket.status == status)

    tickets = query.offset(skip).limit(limit).all()

    # Add execution counts
    for ticket in tickets:
        ticket.execution_count = len(ticket.executions)

    return tickets


@tickets_router.post("/", response_model=TicketResponse)
def create_ticket(
    project_id: int,
    ticket_data: TicketCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new ticket."""
    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    ticket = Ticket(project_id=project_id, **ticket_data.dict())
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    return ticket


@tickets_router.patch("/{ticket_id}", response_model=TicketResponse)
def update_ticket(
    ticket_id: int,
    ticket_update: TicketUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update ticket details."""
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found"
        )

    # Update fields
    update_data = ticket_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(ticket, field, value)

    # Update timestamps
    ticket.updated_at = datetime.utcnow()
    if ticket.status == "IN_PROGRESS" and not ticket.started_at:
        ticket.started_at = datetime.utcnow()
    elif ticket.status in ["DONE", "COMPLETED"] and not ticket.completed_at:
        ticket.completed_at = datetime.utcnow()

    db.commit()
    db.refresh(ticket)

    return ticket


# Execution endpoints
@executions_router.get("/", response_model=List[ExecutionResponse])
def list_executions(
    ticket_id: Optional[int] = None,
    session_id: Optional[int] = None,
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List executions with optional filters."""
    query = db.query(Execution)

    if ticket_id:
        query = query.filter(Execution.ticket_id == ticket_id)
    if session_id:
        query = query.filter(Execution.session_id == session_id)
    if status:
        query = query.filter(Execution.status == status)

    return query.offset(skip).limit(limit).all()


# Statistics endpoints
@stats_router.get("/dashboard", response_model=DashboardStats)
def get_dashboard_stats(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get dashboard statistics."""
    stats = DashboardStats(
        total_projects=db.query(Project).count(),
        total_tickets=db.query(Ticket).count(),
        tickets_by_status={},
        total_executions=db.query(Execution).count(),
        total_sessions=db.query(DBSession).count(),
        active_sessions=db.query(DBSession)
        .filter(DBSession.status == "active")
        .count(),
        total_tokens_used=0,
        estimated_cost="$0.00",
    )

    # Get tickets by status
    status_counts = (
        db.query(Ticket.status, db.func.count(Ticket.id)).group_by(Ticket.status).all()
    )
    stats.tickets_by_status = {status: count for status, count in status_counts}

    # Calculate total tokens and cost
    total_tokens = db.query(db.func.sum(Execution.tokens_used)).scalar() or 0
    stats.total_tokens_used = total_tokens
    stats.estimated_cost = f"${total_tokens * 0.000002:.2f}"  # Rough estimate

    return stats


# Token usage endpoints
@tokens_router.get("/usage", response_model=List[TokenUsageResponse])
def list_token_usage(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    ticket_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List token usage records with optional filters."""
    query = db.query(TokenUsage)

    if provider:
        query = query.filter(TokenUsage.provider == provider)
    if model:
        query = query.filter(TokenUsage.model == model)
    if ticket_id:
        query = query.filter(TokenUsage.ticket_id == ticket_id)
    if start_date:
        query = query.filter(TokenUsage.timestamp >= start_date)
    if end_date:
        query = query.filter(TokenUsage.timestamp <= end_date)

    return query.order_by(TokenUsage.timestamp.desc()).offset(skip).limit(limit).all()


@tokens_router.get("/report", response_model=TokenUsageReport)
def get_token_usage_report(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    user: User = Depends(get_current_user),
):
    """Generate token usage report for specified period."""
    tracker = get_token_tracker()

    if not start_date:
        start_date = datetime.utcnow() - timedelta(days=7)
    if not end_date:
        end_date = datetime.utcnow()

    report = tracker.get_usage_report(start_date, end_date)
    return TokenUsageReport(**report)


@tokens_router.get("/budget", response_model=TokenBudgetStatus)
def get_token_budget_status(
    user: User = Depends(get_current_user),
):
    """Get current token budget status."""
    tracker = get_token_tracker()
    status = tracker.get_current_usage()
    return TokenBudgetStatus(**status)


@tokens_router.post("/budget/reset")
def reset_token_budget(
    admin_user: User = Depends(require_admin),
):
    """Reset token budget (admin only)."""
    tracker = get_token_tracker()
    tracker.reset_budget()
    return {"message": "Token budget reset successfully"}


@tokens_router.get("/export/csv")
def export_token_usage_csv(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    user: User = Depends(get_current_user),
):
    """Export token usage data as CSV."""
    import tempfile

    from fastapi.responses import FileResponse

    tracker = get_token_tracker()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as tmp:
        tracker.export_usage_csv(tmp.name, start_date, end_date)
        return FileResponse(
            path=tmp.name,
            filename=f"token_usage_{datetime.utcnow().strftime('%Y%m%d')}.csv",
            media_type="text/csv",
        )


# Include routers
app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(tickets_router)
app.include_router(executions_router)
app.include_router(stats_router)
app.include_router(tokens_router)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow()}


# Public endpoints for dashboard (no auth required)
@app.get("/stats/dashboard")
def get_dashboard_stats_public(db: Session = Depends(get_db)):
    """Get dashboard statistics without authentication."""
    from sqlalchemy import func

    total_projects = db.query(func.count(Project.id)).scalar() or 0
    active_tickets = (
        db.query(func.count(Ticket.id))
        .filter(Ticket.status.in_(["IN_PROGRESS", "TODO"]))
        .scalar()
        or 0
    )
    completed_today = (
        db.query(func.count(Ticket.id))
        .filter(
            Ticket.status == "DONE",
            func.date(Ticket.updated_at) == func.date(func.now()),
        )
        .scalar()
        or 0
    )

    total_tickets = db.query(func.count(Ticket.id)).scalar() or 0
    successful_tickets = (
        db.query(func.count(Ticket.id)).filter(Ticket.status == "DONE").scalar() or 0
    )

    success_rate = 0
    if total_tickets > 0:
        success_rate = int((successful_tickets / total_tickets) * 100)

    return {
        "total_projects": total_projects,
        "active_tickets": active_tickets,
        "completed_today": completed_today,
        "success_rate": success_rate,
    }


@app.get("/tickets")
def get_tickets_public(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Get recent tickets without authentication."""
    tickets = (
        db.query(Ticket)
        .order_by(Ticket.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    return [
        {
            "id": t.id,
            "ticket_number": t.ticket_number,
            "title": t.title,
            "status": t.status,
            "priority": t.priority,
            "model": t.model,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }
        for t in tickets
    ]
