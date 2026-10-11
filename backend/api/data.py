from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agents.data_reporting import DataReportResult
from api.models import CompanyContext
from services.auth import AuthUser, current_user
from services.data_runner import OutreachError, add_sheet, refresh_sheet, run_data_report, save_upload

router = APIRouter(prefix="/data", tags=["data"])


class DataRunRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    request_id: str | None = None
    company_context: CompanyContext | None = None
    time_zone: str | None = Field(default=None, max_length=64)


class UploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    # 5 MB file -> about 6.7 MB of base64.
    content_base64: str = Field(min_length=1, max_length=7_200_000)


@router.post("/run", response_model=DataReportResult)
async def run(body: DataRunRequest, user: AuthUser = Depends(current_user)) -> DataReportResult:
    try:
        return await run_data_report(
            user,
            prompt=body.prompt,
            request_id=body.request_id,
            company_context=body.company_context.model_dump() if body.company_context else {},
            time_zone=body.time_zone,
        )
    except OutreachError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.post("/datasets")
async def upload(body: UploadRequest, user: AuthUser = Depends(current_user)) -> dict[str, Any]:
    try:
        return await save_upload(user, body.filename, body.content_base64)
    except OutreachError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


class SheetRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


@router.post("/sheets")
async def link_sheet(body: SheetRequest, user: AuthUser = Depends(current_user)) -> dict[str, Any]:
    """Adds one tab of a Google Sheet as a data file."""
    try:
        return await add_sheet(user, body.url)
    except OutreachError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.post("/sheets/{dataset_id}/refresh")
async def refresh(dataset_id: str, user: AuthUser = Depends(current_user)) -> dict[str, Any]:
    try:
        return await refresh_sheet(user.id, dataset_id)
    except OutreachError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
