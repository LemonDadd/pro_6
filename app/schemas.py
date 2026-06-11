from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from datetime import datetime


class PageMargins(BaseModel):
    top: int = Field(default=25, description="Top margin in mm")
    right: int = Field(default=20, description="Right margin in mm")
    bottom: int = Field(default=25, description="Bottom margin in mm")
    left: int = Field(default=20, description="Left margin in mm")


class CoverOptions(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    date: Optional[str] = None


class RenderOptions(BaseModel):
    pageSize: Literal["A4", "Letter"] = Field(default="A4", description="Page size")
    margins: PageMargins = Field(default_factory=PageMargins)
    toc: bool = Field(default=False, description="Include table of contents")
    cover: Optional[CoverOptions] = None
    header: Optional[str] = Field(default=None, description="Header template, e.g. '{{page}}/{{pages}}'")
    footer: Optional[str] = Field(default=None, description="Footer template, e.g. '{{page}}/{{pages}}'")
    codeHighlight: bool = Field(default=True, description="Enable code highlighting")
    mermaid: bool = Field(default=True, description="Enable mermaid diagram rendering")

    @field_validator("header", "footer")
    @classmethod
    def validate_template(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 200:
            raise ValueError("Header/footer template too long (max 200 chars)")
        return v


class SyncRenderRequest(BaseModel):
    markdown: str = Field(..., description="Markdown content to render")
    theme: Literal["default", "github", "resume"] = Field(default="default")
    options: RenderOptions = Field(default_factory=RenderOptions)
    customCssUrl: Optional[str] = None


class AsyncRenderRequest(BaseModel):
    markdown: Optional[str] = Field(default=None, description="Markdown content")
    url: Optional[str] = Field(default=None, description="URL to fetch markdown from")
    theme: Literal["default", "github", "resume"] = Field(default="default")
    options: RenderOptions = Field(default_factory=RenderOptions)
    callbackUrl: Optional[str] = None
    customCssUrl: Optional[str] = None

    @field_validator("markdown", "url")
    @classmethod
    def check_one_source(cls, v, info):
        values = info.data
        if not values.get("markdown") and not values.get("url"):
            raise ValueError("Either 'markdown' or 'url' must be provided")
        if values.get("markdown") and values.get("url"):
            raise ValueError("Provide only one of 'markdown' or 'url'")
        return v


class JobStatus(BaseModel):
    id: str
    status: Literal["queued", "processing", "done", "failed"]
    inputType: Literal["markdown", "url"]
    inputSize: int
    theme: str
    outputKey: Optional[str] = None
    pdfUrl: Optional[str] = None
    pageCount: Optional[int] = None
    sizeBytes: Optional[int] = None
    sha256: Optional[str] = None
    error: Optional[str] = None
    createdAt: datetime
    finishedAt: Optional[datetime] = None


class ThemeInfo(BaseModel):
    name: str
    description: str


class RenderResult(BaseModel):
    jobId: str
    status: str


class AuditLogEntry(BaseModel):
    id: int
    apiKeyHash: str
    endpoint: str
    jobId: Optional[str]
    timestamp: datetime
    success: bool
    error: Optional[str] = None
