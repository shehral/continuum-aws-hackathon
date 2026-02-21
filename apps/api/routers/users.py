"""User management routes including registration.

Users can only access their own profile data. Administrative endpoints
are restricted to authenticated users viewing their own data.
"""

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.neo4j import get_neo4j_session
from db.postgres import get_db
from models.postgres import CaptureSession, User
from routers.auth import require_auth
from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


class UserRegister(BaseModel):
    """Request body for user registration."""

    name: str
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    """Request body for user login."""

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Response body for user operations."""

    id: str
    email: str
    name: str | None


class UserProfile(BaseModel):
    """Full user profile response."""

    id: str
    email: str
    name: str | None
    decision_count: int
    session_count: int


@router.post("/register", response_model=UserResponse)
async def register_user(
    user_data: UserRegister,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user.

    Creates a new user with the provided email and password.
    Password is hashed using bcrypt before storage.
    """
    # Check if user already exists
    result = await db.execute(select(User).where(User.email == user_data.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="A user with this email already exists",
        )

    # Hash the password
    password_hash = bcrypt.hashpw(
        user_data.password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")

    # Create new user
    new_user = User(
        email=user_data.email,
        password_hash=password_hash,
        name=user_data.name,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    logger.info(f"New user registered: {user_data.email}")

    return UserResponse(
        id=new_user.id,
        email=new_user.email,
        name=new_user.name,
    )


@router.post("/login", response_model=UserResponse)
async def login_user(
    user_data: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate a user.

    Validates email and password against the database.
    Returns user data if credentials are valid.
    """
    # Find user by email
    result = await db.execute(select(User).where(User.email == user_data.email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    # Verify password
    if not bcrypt.checkpw(
        user_data.password.encode("utf-8"),
        user.password_hash.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    logger.info(f"User logged in: {user_data.email}")

    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
    )


@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(
    user_id: str = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's profile with statistics.

    Requires authentication. Returns the user's profile data
    along with counts of their decisions and capture sessions.
    """
    # Get user from PostgreSQL
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get capture session count from PostgreSQL
    result = await db.execute(
        select(CaptureSession).where(CaptureSession.user_id == user_id)
    )
    sessions = result.scalars().all()
    session_count = len(sessions)

    # Get decision count from Neo4j
    neo4j_session = await get_neo4j_session()
    async with neo4j_session:
        result = await neo4j_session.run(
            """
            MATCH (d:DecisionTrace)
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            RETURN count(d) AS count
            """,
            user_id=user_id,
        )
        record = await result.single()
        decision_count = record["count"] if record else 0

    return UserProfile(
        id=user.id,
        email=user.email,
        name=user.name,
        decision_count=decision_count,
        session_count=session_count,
    )


@router.delete("/me")
async def delete_current_user(
    confirm: bool = False,
    user_id: str = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Delete the current user's account and all their data.

    WARNING: This permanently deletes:
    - User account
    - All capture sessions
    - All decisions in Neo4j
    - All related entities (if orphaned)

    Pass confirm=true to execute.
    """
    if not confirm:
        return {
            "status": "aborted",
            "message": "Pass confirm=true to delete your account and all data",
        }

    # Verify user exists
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Delete user's data from Neo4j
    neo4j_session = await get_neo4j_session()
    async with neo4j_session:
        # Delete user's decisions
        await neo4j_session.run(
            """
            MATCH (d:DecisionTrace)
            WHERE d.user_id = $user_id
            DETACH DELETE d
            """,
            user_id=user_id,
        )

        # Clean up orphaned entities
        await neo4j_session.run(
            """
            MATCH (e:Entity)
            WHERE NOT (e)<-[:INVOLVES]-(:DecisionTrace)
            DETACH DELETE e
            """
        )

    # Delete capture sessions from PostgreSQL
    await db.execute(delete(CaptureSession).where(CaptureSession.user_id == user_id))

    # Delete user from PostgreSQL
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()

    logger.info(f"User account deleted: {user.email}")

    return {
        "status": "deleted",
        "message": "Your account and all associated data have been permanently deleted",
    }
