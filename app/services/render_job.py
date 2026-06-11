import json
import logging
from typing import Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
import httpx

from app.database import SessionLocal
from app.models import RenderJobDB
from app.schemas import AsyncRenderRequest, RenderOptions, SyncRenderRequest, JobStatus, BatchRenderRequest
from app.services.pdf_renderer import PdfRenderer
from app.services.storage import StorageService
from app.services.auth import AuthService
from app.tasks.render_tasks import render_pdf_task, render_batch_pdf_task
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
            outputFormat=job.outputFormat or "pdf",
            pdfVariant=job.pdfVariant,
            fileCount=job.fileCount,
            outputKey=job.outputKey,
            pdfUrl=pdf_url,
            pageCount=job.pageCount,
            sizeBytes=job.sizeBytes,
            sha256=job.sha256,
            error=job.error,
            createdAt=job.createdAt,
            finishedAt=job.finishedAt,
        )

    def sync_render_preflight(
        self,
        db: Session,
        request: SyncRenderRequest,
        api_key_hash: str,
    ) -> str:
        size_kb = len(request.markdown.encode("utf-8")) / 1024
        if size_kb > settings.sync_max_size_kb:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Markdown too large for sync render ({size_kb:.1f}KB > {settings.sync_max_size_kb}KB). Use async API.",
            )

        self.auth.check_rate_limit(db, api_key_hash)
        self.auth.check_concurrent_limit(db, api_key_hash)

        job = RenderJobDB(
            status="processing",
            inputType="markdown",
            inputSize=len(request.markdown.encode("utf-8")),
            theme=request.theme,
            optionsJson=request.options.model_dump_json(),
            apiKeyHash=api_key_hash,
            pdfVariant=request.options.outputFormat if request.options.outputFormat != "pdf" else None,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        self.auth.increment_usage(db, api_key_hash)
        return job.id

    @staticmethod
    def execute_sync_render_workload(
        job_id: str,
        markdown: str,
        theme: str,
        options_dict: dict,
        custom_css_url: Optional[str],
        api_key_hash: str,
        cancel_event: Optional[object] = None,
    ) -> Tuple[bytes, int]:
        import threading
        thread_db = SessionLocal()
        pdf_renderer = PdfRenderer()
        storage = StorageService()
        auth = AuthService()
        try:
            job = thread_db.query(RenderJobDB).filter(RenderJobDB.id == job_id).first()
            if not job:
                raise RuntimeError(f"Job {job_id} not found in thread DB")

            if job.status == "failed":
                return b"", 0

            options = RenderOptions(**options_dict)
            pdf_bytes, page_count = pdf_renderer.render_to_pdf(
                markdown_text=markdown,
                theme=theme,
                options=options,
                custom_css_url=custom_css_url,
            )

            try:
                pdf_variant = None
                if options.outputFormat == "pdf-a-2b":
                    pdf_variant = "pdf-a-2b"
                object_key, sha256_hash, size_bytes = storage.upload_pdf(
                    pdf_bytes, job.id, pdf_variant=pdf_variant
                )
                job.outputKey = object_key
                job.sizeBytes = size_bytes
                job.sha256 = sha256_hash
            except Exception as e:
                logger.warning(f"Sync render S3 upload failed (non-critical): {e}")

            thread_db.refresh(job)
            if job.status == "failed":
                logger.info(f"Job {job_id} was marked failed by timeout, skipping done update")
                return b"", 0

            job.status = "done"
            job.pageCount = page_count
            job.finishedAt = datetime.utcnow()
            thread_db.commit()

            auth.log_audit(thread_db, api_key_hash, "POST /v1/render/sync", job_id=job.id, success=True)
            return pdf_bytes, page_count
        except Exception as e:
            try:
                thread_db.refresh(job)
            except Exception:
                job = thread_db.query(RenderJobDB).filter(RenderJobDB.id == job_id).first()
            if job and job.status != "failed":
                job.status = "failed"
                job.error = str(e)
                job.finishedAt = datetime.utcnow()
                thread_db.commit()
            auth.log_audit(thread_db, api_key_hash, "POST /v1/render/sync", job_id=job_id, success=False, error=str(e))
            raise
        finally:
            thread_db.close()

    @staticmethod
    def mark_job_failed(
        job_id: str,
        api_key_hash: str,
        error_msg: str,
    ):
        thread_db = SessionLocal()
        auth = AuthService()
        try:
            job = thread_db.query(RenderJobDB).filter(RenderJobDB.id == job_id).first()
            if job and job.status in ("queued", "processing"):
                job.status = "failed"
                job.error = error_msg
                job.finishedAt = datetime.utcnow()
                thread_db.commit()
            auth.log_audit(thread_db, api_key_hash, "POST /v1/render/sync", job_id=job_id, success=False, error=error_msg)
        finally:
            thread_db.close()

    def sync_render(
        self,
        db: Session,
        request: SyncRenderRequest,
        api_key_hash: str,
    ) -> Tuple[bytes, int]:
        job_id = self.sync_render_preflight(db, request, api_key_hash)
        return self.execute_sync_render_workload(
            job_id=job_id,
            markdown=request.markdown,
            theme=request.theme,
            options_dict=request.options.model_dump(),
            custom_css_url=request.customCssUrl,
            api_key_hash=api_key_hash,
        )

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
            pdfVariant=request.options.outputFormat if request.options.outputFormat != "pdf" else None,
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

    async def create_batch_job(
        self,
        db: Session,
        request: BatchRenderRequest,
        api_key_hash: str,
    ) -> JobStatus:
        file_count = len(request.files)

        if file_count > settings.batch_max_files:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Too many files in batch ({file_count} > {settings.batch_max_files}).",
            )

        total_input_size = sum(len(f.markdown.encode("utf-8")) for f in request.files)
        total_input_kb = total_input_size / 1024
        if total_input_kb > settings.batch_max_payload_kb:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Batch payload too large ({total_input_kb:.1f}KB > {settings.batch_max_payload_kb}KB).",
            )

        self.auth.check_rate_limit(db, api_key_hash, required_count=file_count)
        self.auth.check_concurrent_limit(db, api_key_hash)

        job = RenderJobDB(
            status="queued",
            inputType="batch",
            inputSize=total_input_size,
            theme=request.theme,
            optionsJson=request.options.model_dump_json(),
            callbackUrl=request.callbackUrl,
            apiKeyHash=api_key_hash,
            outputFormat="zip",
            fileCount=file_count,
            pdfVariant=request.options.outputFormat if request.options.outputFormat != "pdf" else None,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        self.auth.increment_usage_by(db, api_key_hash, file_count)
        self.auth.log_audit(db, api_key_hash, "POST /v1/render/batch/jobs", job_id=job.id, success=True)

        files_data = [{"filename": f.filename, "markdown": f.markdown} for f in request.files]

        render_batch_pdf_task.delay(
            job_id=job.id,
            files=files_data,
            theme=request.theme,
            options_json=request.options.model_dump_json(),
            custom_css_url=request.customCssUrl,
            callback_url=request.callbackUrl,
        )

        return self._job_to_status(db, job)
