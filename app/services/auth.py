import hashlib
import logging
from typing import Optional
from datetime import date
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import APIKeyDB, DailyUsageDB, AuditLogDB

logger = logging.getLogger(__name__)
settings = get_settings()

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(self):
        pass

    def _get_today_str(self) -> str:
        return date.today().isoformat()

    def validate_api_key(self, db: Session, api_key: Optional[str]) -> str:
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API Key is required in X-API-Key header",
            )

        key_hash = hash_api_key(api_key)

        if settings.api_key_list and api_key in settings.api_key_list:
            return key_hash

        db_key = db.query(APIKeyDB).filter(APIKeyDB.keyHash == key_hash, APIKeyDB.isActive == True).first()
        if not db_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or inactive API Key",
            )
        return key_hash

    def _get_daily_limit(self, db: Session, key_hash: str) -> int:
        db_key = db.query(APIKeyDB).filter(APIKeyDB.keyHash == key_hash).first()
        return db_key.dailyLimit if db_key else settings.daily_rate_limit

    def check_rate_limit(self, db: Session, key_hash: str, required_count: int = 1) -> bool:
        today = self._get_today_str()
        usage = db.query(DailyUsageDB).filter(
            DailyUsageDB.apiKeyHash == key_hash,
            DailyUsageDB.date == today,
        ).first()

        daily_limit = self._get_daily_limit(db, key_hash)
        current_count = usage.count if usage else 0

        if current_count + required_count > daily_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Daily rate limit exceeded ({daily_limit} requests/day). Need {required_count} more, {current_count} used.",
            )
        return True

    def increment_usage(self, db: Session, key_hash: str):
        self.increment_usage_by(db, key_hash, 1)

    def increment_usage_by(self, db: Session, key_hash: str, count: int):
        if count <= 0:
            return
        today = self._get_today_str()
        usage = db.query(DailyUsageDB).filter(
            DailyUsageDB.apiKeyHash == key_hash,
            DailyUsageDB.date == today,
        ).first()
        if usage:
            usage.count += count
        else:
            usage = DailyUsageDB(apiKeyHash=key_hash, date=today, count=count)
            db.add(usage)
        db.commit()

    def check_concurrent_limit(self, db: Session, key_hash: str) -> bool:
        from app.models import RenderJobDB
        db_key = db.query(APIKeyDB).filter(APIKeyDB.keyHash == key_hash).first()
        max_concurrent = db_key.maxConcurrent if db_key else settings.max_concurrent_jobs

        active_count = db.query(RenderJobDB).filter(
            RenderJobDB.apiKeyHash == key_hash,
            RenderJobDB.status.in_(["queued", "processing"]),
        ).count()

        if active_count >= max_concurrent:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many concurrent jobs ({active_count}/{max_concurrent}). Try again later.",
            )
        return True

    def log_audit(
        self,
        db: Session,
        key_hash: str,
        endpoint: str,
        job_id: Optional[str] = None,
        success: bool = True,
        error: Optional[str] = None,
    ):
        log = AuditLogDB(
            apiKeyHash=key_hash,
            endpoint=endpoint,
            jobId=job_id,
            success=success,
            error=error,
        )
        db.add(log)
        db.commit()


def get_auth_service() -> AuthService:
    return AuthService()
