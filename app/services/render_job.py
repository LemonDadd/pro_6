import json
import logging
from typing import Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
import httpx

from app.models import RenderJobDB
from app.schemas import AsyncRenderRequest, RenderOptions, SyncRenderRequest, JobStatus
from app.services.pdf_renderer import PdfRenderer
from app.services.storage import StorageService
from app.services.auth import AuthService
from app.tasks.render_tasks import render_pdf_task
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class RenderJobService:
    def __init__(self):
        self.pdf_renderer = PdfRenderer()
        self.storage = StorageService()
        self.auth = AuthService()

    @staticmethod
    def _job_to_status(db: Session, job: RenderJobDB) -> JobStatus:
        pdf_url = None
        if job.outputKey and job.status == "done":
            try:
                storage = StorageService()
                pdf_url = storage.generate_presigned_url(job.outputKey)
            except Exception:
                pass
        return JobStatus(
            id=job.id,
            status=job.status,
            inputType=job.inputType,
            inputSize=job.inputSize,
            theme=job.theme,
            outputKey=job.outputKey,
            pdfUrl=pdf_url,
            pageCount=job.pageCount,
            sizeBytes=job.sizeBytes,
            sha256=job.sha256,
            error=job.error,
            createdAt=job.createdAt,
            finishedAt=job.finishedAt,
        )

    def sync_render(
        self,
        db: Session,
        request: SyncRenderRequest,
        api_key_hash: str,
    ) -> Tuple[bytes, int]:
        size_kb = len(request.markdown.encode("utf-8")) / 1024
        if size_kb > settings.sync_max_size_kb:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_413_PAYLOAD_TOO_LARGE,
                detail=f"Markdown too large for sync render ({size_kb:.1f}KB > {settings.sync_max_size_kb}KB). Use async API.",
            )

        self.auth.check_rate_limit(db, api_key_hash)
        self.auth.increment_usage(db, api_key_hash)

        try:
            pdf_bytes, page_count = self.pdf_renderer.render_to_pdf(
                markdown_text=request.markdown,
                theme=request.theme,
                options=request.options,
                custom_css_url=request.customCssUrl,
            )
            self.auth.log_audit(db, api_key_hash, "POST /v1/render/sync", success=True)
            return pdf_bytes, page_count
        except Exception as e:
            self.auth.log_audit(db, api_key_hash, "POST /v1/render/sync", success=False, error=str(e))
            raise

    async def _fetch_url_content(self, url: str) -> str:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text

    async def create_async_job(
        self,
        db: Session,
        request: AsyncRenderRequest,
        api_key_hash: str,
    ) -> JobStatus:
        self.auth.check_rate_limit(db, api_key_hash)
        self.auth.check_concurrent_limit(db, api_key_hash)

        if request.url:
            try:
                markdown_text = await self._fetch_url_content(request.url)
                input_type = "url"
            except Exception as e:
                self.auth.log_audit(
                    db, api_key_hash, "POST /v1/render/jobs",
                    success=False, error=f"URL fetch failed: {e}",
                )
                raise
        else:
            markdown_text = request.markdown or ""
            input_type = "markdown"

        input_size = len(markdown_text.encode("utf-8"))

        job = RenderJobDB(
            status="queued",
            inputType=input_type,
            inputSize=input_size,
            theme=request.theme,
            optionsJson=request.options.model_dump_json(),
            callbackUrl=request.callbackUrl,
            apiKeyHash=api_key_hash,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        self.auth.increment_usage(db, api_key_hash)
        self.auth.log_audit(db, api_key_hash, "POST /v1/render/jobs", job_id=job.id, success=True)

        render_pdf_task.delay(
            job_id=job.id,
            markdown_text=markdown_text,
            theme=request.theme,
            options_json=request.options.model_dump_json(),
            custom_css_url=request.customCssUrl,
            callback_url=request.callbackUrl,
        )

        return self._job_to_status(db, job)

    def get_job_status(self, db: Session, job_id: str, api_key_hash: str) -> JobStatus:
        job = db.query(RenderJobDB).filter(RenderJobDB.id == job_id).first()
        if not job:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

        if job.apiKeyHash and job.apiKeyHash != api_key_hash:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        self.auth.log_audit(db, api_key_hash, f"GET /v1/render/jobs/{job_id}", job_id=job_id, success=True)
        return self._job_to_status(db, job)

    def cancel_job(self, db: Session, job_id: str, api_key_hash: str) -> JobStatus:
        job = db.query(RenderJobDB).filter(RenderJobDB.id == job_id).first()
        if not job:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

        if job.apiKeyHash and job.apiKeyHash != api_key_hash:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        if job.status != "queued":
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel job with status '{job.status}'. Only 'queued' jobs can be cancelled.",
            )

        job.status = "failed"
        job.error = "Cancelled by user"
        job.finishedAt = datetime.utcnow()
        db.commit()
        db.refresh(job)

        self.auth.log_audit(db, api_key_hash, f"DELETE /v1/render/jobs/{job_id}", job_id=job_id, success=True)
        return self._job_to_status(db, job)
