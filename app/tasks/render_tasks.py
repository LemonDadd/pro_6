import logging
import json
from datetime import datetime
from typing import Optional

import httpx
from celery import Task

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import RenderJobDB
from app.schemas import RenderOptions
from app.services.pdf_renderer import PdfRenderer
from app.services.storage import StorageService

logger = logging.getLogger(__name__)


class DatabaseTask(Task):
    _db = None
    _pdf_renderer = None
    _storage = None

    @property
    def db(self):
        if self._db is None:
            self._db = SessionLocal()
        return self._db

    @property
    def pdf_renderer(self):
        if self._pdf_renderer is None:
            self._pdf_renderer = PdfRenderer()
        return self._pdf_renderer

    @property
    def storage(self):
        if self._storage is None:
            self._storage = StorageService()
        return self._storage

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        if self._db is not None:
            self._db.close()
            self._db = None


@celery_app.task(base=DatabaseTask, bind=True, name="app.tasks.render_pdf_task")
def render_pdf_task(self, job_id: str, markdown_text: str, theme: str, options_json: str,
                    custom_css_url: Optional[str] = None, callback_url: Optional[str] = None):
    db = self.db
    job = db.query(RenderJobDB).filter(RenderJobDB.id == job_id).first()
    if not job:
        logger.error(f"Job {job_id} not found")
        return

    try:
        job.status = "processing"
        db.commit()

        options = RenderOptions(**json.loads(options_json))
        pdf_bytes, page_count = self.pdf_renderer.render_to_pdf(
            markdown_text=markdown_text,
            theme=theme,
            options=options,
            custom_css_url=custom_css_url,
        )

        object_key, sha256_hash, size_bytes = self.storage.upload_pdf(pdf_bytes, job_id)

        job.status = "done"
        job.outputKey = object_key
        job.pageCount = page_count
        job.sizeBytes = size_bytes
        job.sha256 = sha256_hash
        job.finishedAt = datetime.utcnow()
        db.commit()

        if callback_url:
            _trigger_callback(db, job, callback_url)

        return {
            "jobId": job_id,
            "status": "done",
            "pageCount": page_count,
            "sizeBytes": size_bytes,
            "sha256": sha256_hash,
        }

    except Exception as e:
        logger.exception(f"Render job {job_id} failed")
        job.status = "failed"
        job.error = str(e)
        job.finishedAt = datetime.utcnow()
        db.commit()

        if callback_url:
            _trigger_callback(db, job, callback_url)
        raise


def _trigger_callback(db, job: RenderJobDB, callback_url: str):
    try:
        from app.services.storage import StorageService
        storage = StorageService()
        pdf_url = None
        if job.outputKey:
            pdf_url = storage.generate_presigned_url(job.outputKey)

        payload = {
            "jobId": job.id,
            "status": job.status,
            "pdfUrl": pdf_url,
            "pageCount": job.pageCount,
            "sizeBytes": job.sizeBytes,
            "sha256": job.sha256,
            "error": job.error,
            "finishedAt": job.finishedAt.isoformat() if job.finishedAt else None,
        }

        with httpx.Client(timeout=10.0) as client:
            client.post(callback_url, json=payload)
        logger.info(f"Callback triggered for job {job.id}")
    except Exception as e:
        logger.warning(f"Callback failed for job {job.id}: {e}")


@celery_app.task(name="app.tasks.cleanup_expired_pdfs")
def cleanup_expired_pdfs():
    storage = StorageService()
    storage.cleanup_expired()
    logger.info("Expired PDF cleanup completed")
