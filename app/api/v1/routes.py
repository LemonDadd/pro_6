from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.schemas import SyncRenderRequest, AsyncRenderRequest, JobStatus, ThemeInfo
from app.services.auth import api_key_header, AuthService, hash_api_key, get_auth_service
from app.services.render_job import RenderJobService
from app.services.pdf_renderer import PdfRenderer
from app.config import get_settings

router = APIRouter(prefix="/v1", tags=["render"])
settings = get_settings()


def _get_api_key_hash(
    db: Session = Depends(get_db),
    api_key: str = Security(api_key_header),
    auth: AuthService = Depends(get_auth_service),
) -> str:
    return auth.validate_api_key(db, api_key)


@router.post("/render/sync", response_class=Response)
def render_sync(
    request: SyncRenderRequest,
    db: Session = Depends(get_db),
    api_key_hash: str = Depends(_get_api_key_hash),
    auth: AuthService = Depends(get_auth_service),
):
    service = RenderJobService()
    try:
        pdf_bytes, page_count = service.sync_render(db, request, api_key_hash)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Render failed: {str(e)}",
        )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'inline; filename="rendered.pdf"',
            "X-Page-Count": str(page_count),
        },
    )


@router.post("/render/jobs", response_model=JobStatus, status_code=status.HTTP_202_ACCEPTED)
async def create_render_job(
    request: AsyncRenderRequest,
    db: Session = Depends(get_db),
    api_key_hash: str = Depends(_get_api_key_hash),
):
    service = RenderJobService()
    return await service.create_async_job(db, request, api_key_hash)


@router.get("/render/jobs/{job_id}", response_model=JobStatus)
def get_job_status(
    job_id: str,
    db: Session = Depends(get_db),
    api_key_hash: str = Depends(_get_api_key_hash),
):
    service = RenderJobService()
    return service.get_job_status(db, job_id, api_key_hash)


@router.delete("/render/jobs/{job_id}", response_model=JobStatus)
def cancel_job(
    job_id: str,
    db: Session = Depends(get_db),
    api_key_hash: str = Depends(_get_api_key_hash),
):
    service = RenderJobService()
    return service.cancel_job(db, job_id, api_key_hash)


@router.get("/themes", response_model=List[ThemeInfo])
def list_themes():
    renderer = PdfRenderer()
    return renderer.get_available_themes()
