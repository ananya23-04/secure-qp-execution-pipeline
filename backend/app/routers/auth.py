from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config, security
from ..db import get_db
from ..deps import current_faculty
from ..models import Faculty, _id

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)
    institution: str = Field(min_length=2)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


@router.post("/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(Faculty).where(Faculty.email == body.email.lower())):
        raise HTTPException(409, "Email already registered")
    fid = _id()
    faculty = Faculty(
        id=fid,
        email=body.email.lower(),
        password_hash=security.hash_password(body.password),
        institution=body.institution,
        pseudonym=security.pseudonym_for(fid),
    )
    db.add(faculty)
    db.commit()
    return {"pseudonym": faculty.pseudonym}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    f = db.scalar(select(Faculty).where(Faculty.email == body.email.lower()))
    if not f or not security.verify_password(body.password, f.password_hash):
        raise HTTPException(401, "Invalid credentials")
    return {"access_token": security.create_token(f.id), "token_type": "bearer"}


@router.get("/me")
def me(faculty: Faculty = Depends(current_faculty)):
    """Who am I and what may I do? The portal uses this to decide which screens to show."""
    roles = ["faculty"]
    if faculty.email in config.REVIEWER_EMAILS:
        roles.append("reviewer")
    if faculty.email in config.ADMIN_EMAILS:
        roles.append("admin")
    return {"email": faculty.email, "pseudonym": faculty.pseudonym,
            "institution": faculty.institution, "roles": roles}
