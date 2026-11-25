import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import config, security
from .db import get_db
from .models import Faculty

_bearer = HTTPBearer()


def current_faculty(
    cred: HTTPAuthorizationCredentials = Depends(_bearer), db: Session = Depends(get_db)
) -> Faculty:
    try:
        fid = security.decode_token(cred.credentials)
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")
    faculty = db.get(Faculty, fid)
    if not faculty:
        raise HTTPException(401, "Unknown user")
    return faculty


def require_admin(faculty: Faculty = Depends(current_faculty)) -> Faculty:
    if faculty.email not in config.ADMIN_EMAILS:
        raise HTTPException(403, "Admin only")
    return faculty


def require_reviewer(faculty: Faculty = Depends(current_faculty)) -> Faculty:
    if faculty.email not in config.REVIEWER_EMAILS:
        raise HTTPException(403, "Reviewers only")
    return faculty


def require_reviewer_or_admin(faculty: Faculty = Depends(current_faculty)) -> Faculty:
    if faculty.email not in config.REVIEWER_EMAILS and faculty.email not in config.ADMIN_EMAILS:
        raise HTTPException(403, "Reviewers or admins only")
    return faculty
