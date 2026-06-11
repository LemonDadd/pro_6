import os
import logging
from typing import Optional, Tuple
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML, CSS
import httpx

from app.config import get_settings
from app.schemas import RenderOptions
from app.services.markdown_renderer import MarkdownRenderer

logger = logging.getLogger(__name__)
settings = get_settings()

BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
THEMES_DIR = BASE_DIR / "themes"
FONTS_DIR = BASE_DIR / "fonts"


class PdfRenderer:
    def __init__(self):
        self.md_renderer = MarkdownRenderer()
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
        )
        self._ensure_dirs()

    @staticmethod
    def _ensure_dirs():
        for d in [TEMPLATES_DIR, THEMES_DIR, FONTS_DIR]:
            d.mkdir(parents=True, exist_ok=True)

    def _load_theme_css(self, theme: str, custom_css_url: Optional[str] = None) -> str:
        css_parts = []
        theme_file = THEMES_DIR / f"{theme}.css"
        if theme_file.exists():
            css_parts.append(theme_file.read_text(encoding="utf-8"))

        from pygments.formatters import HtmlFormatter
        css_parts.append(HtmlFormatter(style="default").get_style_defs(".codehilite"))

        if custom_css_url and self._is_allowed_css_domain(custom_css_url):
            try:
                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(custom_css_url)
                    if resp.status_code == 200:
                        css_parts.append(resp.text)
            except Exception as e:
                logger.warning(f"Failed to load custom CSS from {custom_css_url}: {e}")

        return "\n\n".join(css_parts)

    @staticmethod
    def _is_allowed_css_domain(url: str) -> bool:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.hostname or ""
            allowed = settings.allowed_css_domain_list
            return any(domain == d or domain.endswith("." + d) for d in allowed)
        except Exception:
            return False

    def _build_page_css(self, options: RenderOptions) -> str:
        page_size = options.pageSize
        margins = options.margins
        page_css = f"""
        @page {{
            size: {page_size};
            margin: {margins.top}mm {margins.right}mm {margins.bottom}mm {margins.left}mm;
        }}
        """

        if options.header:
            header_template = self._process_header_footer_template(options.header)
            page_css += f"""
            @page {{
                @top-center {{
                    content: "{header_template}";
                    font-size: 9pt;
                    color: #666;
                }}
            }}
            """

        if options.footer:
            footer_template = self._process_header_footer_template(options.footer)
            page_css += f"""
            @page {{
                @bottom-center {{
                    content: "{footer_template}";
                    font-size: 9pt;
                    color: #666;
                }}
            }}
            """

        return page_css

    @staticmethod
    def _process_header_footer_template(template: str) -> str:
        import re
        template = re.sub(r"\{\{page\}\}", '" counter(page) "', template)
        template = re.sub(r"\{\{pages\}\}", '" counter(pages) "', template)
        template = template.replace('""', '')
        return template

    def _build_html_document(
        self,
        body_html: str,
        theme_css: str,
        page_css: str,
        options: RenderOptions,
        title: Optional[str] = None,
    ) -> str:
        template = self.jinja_env.get_template("document.html.j2")
        toc_html = None
        if options.toc:
            toc_html = self.md_renderer.generate_toc_html(body_html)

        cover_data = None
        if options.cover:
            cover_data = {
                "title": options.cover.title or title or "Document",
                "author": options.cover.author or "",
                "date": options.cover.date or "",
            }

        return template.render(
            body_html=body_html,
            theme_css=theme_css,
            page_css=page_css,
            toc_html=toc_html,
            cover=cover_data,
            title=title or "Document",
        )

    def render_to_pdf(
        self,
        markdown_text: str,
        theme: str = "default",
        options: Optional[RenderOptions] = None,
        custom_css_url: Optional[str] = None,
    ) -> Tuple[bytes, int]:
        options = options or RenderOptions()

        body_html = self.md_renderer.render(
            markdown_text,
            enable_code_highlight=options.codeHighlight,
            enable_mermaid=options.mermaid,
        )

        title = self.md_renderer.extract_title(markdown_text)
        theme_css = self._load_theme_css(theme, custom_css_url)
        page_css = self._build_page_css(options)
        full_html = self._build_html_document(body_html, theme_css, page_css, options, title)

        css_objs = [CSS(string=page_css)]
        html_doc = HTML(string=full_html, base_url=str(BASE_DIR))
        document = html_doc.render(stylesheets=css_objs)

        pdf_bytes = document.write_pdf()
        page_count = len(document.pages)

        return pdf_bytes, page_count

    def get_available_themes(self) -> list:
        themes = []
        for f in THEMES_DIR.glob("*.css"):
            name = f.stem
            desc_map = {
                "default": "Default clean theme",
                "github": "GitHub-style markdown theme",
                "resume": "Professional resume/CV theme",
            }
            themes.append({"name": name, "description": desc_map.get(name, name.capitalize() + " theme")})
        return themes
