from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from agent_review.models import ReviewRun

router = APIRouter(tags=["ui"])

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
)


@router.get("/ui/scans", response_class=HTMLResponse)
async def scan_list(request: Request) -> HTMLResponse:
    session_factory = request.app.state.session_factory

    async with session_factory() as db:
        stmt = select(ReviewRun).order_by(ReviewRun.created_at.desc()).limit(100)
        result = await db.execute(stmt)
        runs = result.scalars().all()

    template = _jinja_env.get_template("scan_list.html")
    html = template.render(runs=runs, request=request)
    return HTMLResponse(content=html)


@router.get("/ui/scans/{run_id}", response_class=HTMLResponse)
async def scan_detail(run_id: str, request: Request) -> HTMLResponse:
    session_factory = request.app.state.session_factory

    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid run_id format") from exc

    async with session_factory() as db:
        stmt = (
            select(ReviewRun)
            .options(selectinload(ReviewRun.findings))
            .where(ReviewRun.id == run_uuid)
        )
        result = await db.execute(stmt)
        run = result.scalar_one_or_none()
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        findings = list(run.findings)

    template = _jinja_env.get_template("scan_detail.html")
    html = template.render(run=run, findings=findings, request=request)
    return HTMLResponse(content=html)
