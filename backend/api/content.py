from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agents.content_copy import ContentResult
from api.models import CompanyContext
from integrations.social.providers import SocialError
from services.auth import AuthUser, current_user
from services.content_runner import OutreachError, publish_variant, run_content, save_variant

router = APIRouter(prefix="/content", tags=["content"])


class ContentRunRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    request_id: str | None = None
    company_context: CompanyContext | None = None


class PublishRequest(BaseModel):
    piece_id: str = Field(min_length=1, max_length=40)
    variant_id: str = Field(min_length=1, max_length=40)
    provider: str = Field(pattern="^(linkedin|x|notion|medium)$")
    # The user's edits, if they changed the draft before posting.
    text: str | None = Field(default=None, max_length=10_000)
    parts: list[str] | None = Field(default=None, max_length=25)


class VariantEdits(BaseModel):
    """The user's changes to a draft; fields left out stay as they are."""

    piece_id: str = Field(min_length=1, max_length=40)
    title: str | None = Field(default=None, max_length=300)
    subtitle: str | None = Field(default=None, max_length=600)
    text: str | None = Field(default=None, max_length=60_000)
    parts: list[Annotated[str, Field(max_length=2000)]] | None = Field(default=None, max_length=25)
    headlines: list[Annotated[str, Field(max_length=200)]] | None = Field(default=None, max_length=5)
    descriptions: list[Annotated[str, Field(max_length=400)]] | None = Field(default=None, max_length=4)
    tags: list[Annotated[str, Field(max_length=60)]] | None = Field(default=None, max_length=8)


@router.post("/run", response_model=ContentResult)
async def run(body: ContentRunRequest, user: AuthUser = Depends(current_user)) -> ContentResult:
    try:
        return await run_content(
            user,
            prompt=body.prompt,
            request_id=body.request_id,
            company_context=body.company_context.model_dump() if body.company_context else {},
        )
    except OutreachError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.post("/requests/{request_id}/publish")
async def publish(request_id: str, body: PublishRequest, user: AuthUser = Depends(current_user)) -> dict[str, Any]:
    try:
        return await publish_variant(
            user, request_id, piece_id=body.piece_id, variant_id=body.variant_id,
            provider=body.provider, text=body.text, parts=body.parts,
        )
    except SocialError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.patch("/requests/{request_id}/variants/{variant_id}")
async def save(request_id: str, variant_id: str, body: VariantEdits, user: AuthUser = Depends(current_user)) -> dict[str, Any]:
    try:
        return await save_variant(
            user, request_id, piece_id=body.piece_id, variant_id=variant_id,
            edits=body.model_dump(exclude={"piece_id"}, exclude_none=True),
        )
    except OutreachError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
