from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .db import Base, engine
from .routers import auth, exams, pipeline, review, submissions


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)  # swap for Alembic migrations later
    yield


app = FastAPI(title="SafeExam – Collection & Pre-processing API", lifespan=lifespan)


@app.get("/health")
def health():
    return {"ok": True}


app.include_router(auth.router)
app.include_router(submissions.router)
app.include_router(pipeline.router)
app.include_router(review.router)
app.include_router(review.moderation)
app.include_router(exams.router)


# React portal (compiled bundle checked into app/static; source lives in /frontend)
_STATIC = Path(__file__).parent / "static"
if _STATIC.is_dir():
    app.mount("/app", StaticFiles(directory=_STATIC, html=True), name="portal")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/app/" if _STATIC.is_dir() else "/docs")
