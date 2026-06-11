import re
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, Literal, List
from datetime import datetime

_SAFE_FILENAME_RE = re.compile(r'^[a-zA-Z0-9_\-\.\s]+\.md$')


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
    outputFormat: Literal["pdf", "pdf-a-2b"] = Field(default="pdf", description="PDF output format")
    watermark: Optional[str] = Field(default=None, description="Watermark text. If empty, no watermark is applied.")
    watermarkOpacity: float = Field(default=0.15, ge=0.05, le=0.5, description="Watermark opacity (0.05 to 0.5)")
    watermarkAngle: int = Field(default=-45, ge=-90, le=90, description="Watermark rotation angle in degrees")

    @field_validator("header", "footer")
    @classmethod
    def validate_template(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 200:
            raise ValueError("Header/footer template too long (max 200 chars)")
        return v

    @field_validator("watermark")
    @classmethod
    def validate_watermark(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 100:
            raise ValueError("Watermark text too long (max 100 chars)")
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

    @model_validator(mode="after")
    def check_one_source(self):
        has_md = self.markdown is not None and self.markdown != ""
        has_url = self.url is not None and self.url != ""
        if not has_md and not has_url:
            raise ValueError("Either 'markdown' or 'url' must be provided")
        if has_md and has_url:
            raise ValueError("Provide only one of 'markdown' or 'url'")
        return self


class BatchFileItem(BaseModel):
    filename: str = Field(..., description="Markdown file name, e.g. 'ch01.md'")
    markdown: str = Field(..., description="Markdown content")

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        if not v:
            raise ValueError("Filename must not be empty")
        if len(v) > 255:
            raise ValueError("Filename too long (max 255 chars)")
        if "\x00" in v:
            raise ValueError("Filename contains null byte")
        if "/" in v or "\\" in v:
            raise ValueError(f"Filename must not contain path separators: {v}")
        if ".." in v:
            raise ValueError(f"Filename must not contain path traversal: {v}")
        if not v.endswith(".md"):
            raise ValueError(f"Filename must end with .md: {v}")
        if not _SAFE_FILENAME_RE.match(v):
            raise ValueError(
                f"Filename contains unsafe characters: {v}. "
                f"Only alphanumeric, underscore, hyphen, dot, and space are allowed."
            )
        return v


class BatchRenderRequest(BaseModel):
    """异步批量渲染多个 Markdown 文件，返回 ZIP 压缩包的 Job"""
    files: List[BatchFileItem] = Field(..., description="List of markdown files to render")
    theme: Literal["default", "github", "resume"] = Field(default="default")
    options: RenderOptions = Field(default_factory=RenderOptions)
    callbackUrl: Optional[str] = None
    customCssUrl: Optional[str] = None

    @field_validator("files")
    @classmethod
    def validate_files(cls, v: List[BatchFileItem]) -> List[BatchFileItem]:
        if not v:
            raise ValueError("At least one file is required")
        seen = set()
        for f in v:
            if f.filename in seen:
                raise ValueError(f"Duplicate filename: {f.filename}")
            seen.add(f.filename)
        return v


class JobStatus(BaseModel):
    id: str
    status: Literal["queued", "processing", "done", "failed"]
    inputType: Literal["markdown", "url", "batch"]
    inputSize: int
    theme: str
    outputFormat: Literal["pdf", "zip"] = Field(default="pdf", description="Output file format")
    pdfVariant: Optional[str] = Field(default=None, description="PDF variant, e.g. 'pdf-a-2b'")
    fileCount: Optional[int] = Field(default=None, description="Number of output files (batch jobs)")
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
