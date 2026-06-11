from sqlalchemy import Column, String, Integer, DateTime, Text, Boolean, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base
import uuid


def generate_uuid() -> str:
    return str(uuid.uuid4())


class RenderJobDB(Base):
    __tablename__ = "render_jobs"

    id = Column(String, primary_key=True, default=generate_uuid)
    status = Column(String, default="queued")
    inputType = Column(String, nullable=False)
    inputSize = Column(Integer, nullable=False)
    theme = Column(String, nullable=False)
    optionsJson = Column(Text, nullable=False)
    outputKey = Column(String, nullable=True)
    pageCount = Column(Integer, nullable=True)
    sizeBytes = Column(Integer, nullable=True)
    sha256 = Column(String, nullable=True)
    fileCount = Column(Integer, nullable=True)
    outputFormat = Column(String, default="pdf")
    error = Column(Text, nullable=True)
    callbackUrl = Column(String, nullable=True)
    apiKeyHash = Column(String, nullable=True)
    createdAt = Column(DateTime(timezone=True), server_default=func.now())
    finishedAt = Column(DateTime(timezone=True), nullable=True)


class APIKeyDB(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    keyHash = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=True)
    dailyLimit = Column(Integer, default=100)
    maxConcurrent = Column(Integer, default=3)
    isActive = Column(Boolean, default=True)
    createdAt = Column(DateTime(timezone=True), server_default=func.now())


class AuditLogDB(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    apiKeyHash = Column(String, nullable=True)
    endpoint = Column(String, nullable=False)
    jobId = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    success = Column(Boolean, default=True)
    error = Column(Text, nullable=True)


class DailyUsageDB(Base):
    __tablename__ = "daily_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    apiKeyHash = Column(String, nullable=False)
    date = Column(String, nullable=False)
    count = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("apiKeyHash", "date", name="uq_daily_usage_key_date"),
    )
