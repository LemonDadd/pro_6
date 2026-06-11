import re
import base64
import logging
from typing import Optional, Tuple
from markdown_it import MarkdownIt
from mdit_py_plugins import front_matter, anchors, tasklists, tables, deflist
from pygments import highlight
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.formatters import HtmlFormatter
from pygments.util import ClassNotFound
import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class MarkdownRenderer:
    def __init__(self):
        self.md = MarkdownIt("gfm-like", {
            "html": True,
            "linkify": True,
            "typographer": True,
            "breaks": False,
        })
        self.md.use(front_matter.front_matter_plugin)
        self.md.use(anchors.anchors_plugin)
        self.md.use(tasklists.tasklists_plugin)
        self.md.use(tables.tables_plugin)
        self.md.use(deflist.deflist_plugin)

    def _highlight_code(self, code: str, lang: Optional[str] = None) -> str:
        try:
            if lang:
                lexer = get_lexer_by_name(lang, stripall=False)
            else:
                lexer = guess_lexer(code)
            formatter = HtmlFormatter(nowrap=True, cssclass="codehilite")
            return highlight(code, lexer, formatter)
        except ClassNotFound:
            return f"<pre><code>{self._escape_html(code)}</code></pre>"
        except Exception as e:
            logger.warning(f"Code highlighting failed: {e}")
            return f"<pre><code>{self._escape_html(code)}</code></pre>"

    @staticmethod
    def _escape_html(text: str) -> str:
        return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))

    def _extract_mermaid_blocks(self, markdown_text: str) -> Tuple[str, list]:
        mermaid_blocks = []
        pattern = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)

        def replace_func(match):
            idx = len(mermaid_blocks)
            mermaid_blocks.append(match.group(1).strip())
            return f"__MERMAID_BLOCK_{idx}__"

        processed = pattern.sub(replace_func, markdown_text)
        return processed, mermaid_blocks

    def _render_mermaid_to_png(self, diagram_code: str) -> Optional[str]:
        if settings.mermaid_renderer == "kroki":
            return self._render_via_kroki(diagram_code)
        return None

    def _render_via_kroki(self, diagram_code: str) -> Optional[str]:
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{settings.kroki_url}/mermaid/png",
                    content=diagram_code.encode("utf-8"),
                    headers={"Content-Type": "text/plain"},
                )
                if response.status_code == 200:
                    png_data = base64.b64encode(response.content).decode("ascii")
                    return f"data:image/png;base64,{png_data}"
        except Exception as e:
            logger.warning(f"Mermaid rendering via Kroki failed: {e}")
        return None

    def _insert_mermaid_images(self, html_content: str, mermaid_blocks: list, enable_mermaid: bool) -> str:
        for idx, diagram in enumerate(mermaid_blocks):
            placeholder = f"__MERMAID_BLOCK_{idx}__"
            if enable_mermaid:
                img_data = self._render_mermaid_to_png(diagram)
                if img_data:
                    replacement = f'<div class="mermaid-diagram"><img src="{img_data}" alt="Mermaid diagram" /></div>'
                else:
                    replacement = f'<pre class="mermaid-placeholder"><code>{self._escape_html(diagram)}</code></pre>'
            else:
                replacement = f'<pre><code class="language-mermaid">{self._escape_html(diagram)}</code></pre>'
            html_content = html_content.replace(placeholder, replacement)
        return html_content

    def _apply_code_highlighting(self, md: MarkdownIt, enable: bool) -> MarkdownIt:
        if not enable:
            return md

        original_render = md.renderer.rules.get("fence") or md.renderer.rules.get("code_block")

        def fence_rule(tokens, idx, options, env, slf):
            token = tokens[idx]
            info = token.info.strip() if token.info else ""
            lang = info.split()[0] if info else None
            code = token.content
            highlighted = self._highlight_code(code, lang)
            return f'<div class="code-block"><pre class="codehilite"><code>{highlighted}</code></pre></div>\n'

        md.renderer.rules["fence"] = fence_rule
        md.renderer.rules["code_block"] = fence_rule
        return md

    def render(self, markdown_text: str, enable_code_highlight: bool = True, enable_mermaid: bool = True) -> str:
        processed_md, mermaid_blocks = self._extract_mermaid_blocks(markdown_text)

        md_instance = self._apply_code_highlighting(self.md, enable_code_highlight)
        html_content = md_instance.render(processed_md)

        html_content = self._insert_mermaid_images(html_content, mermaid_blocks, enable_mermaid)
        return html_content

    def extract_title(self, markdown_text: str) -> Optional[str]:
        for line in markdown_text.split("\n"):
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
            if line.startswith("## "):
                return line[3:].strip()
        return None

    def generate_toc_html(self, html_content: str) -> Optional[str]:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, "html.parser")
        headers = soup.find_all(["h1", "h2", "h3", "h4"])
        if not headers:
            return None

        toc_items = []
        for h in headers:
            level = int(h.name[1])
            text = h.get_text()
            anchor = h.get("id", "")
            toc_items.append((level, text, anchor))

        if not toc_items:
            return None

        html_parts = ['<nav class="table-of-contents"><h2>Table of Contents</h2><ul>']
        current_level = toc_items[0][0]

        for level, text, anchor in toc_items:
            while level > current_level:
                html_parts.append("<ul>")
                current_level += 1
            while level < current_level:
                html_parts.append("</ul>")
                current_level -= 1
            if anchor:
                html_parts.append(f'<li><a href="#{anchor}">{text}</a></li>')
            else:
                html_parts.append(f"<li>{text}</li>")

        while current_level > toc_items[0][0]:
            html_parts.append("</ul>")
            current_level -= 1

        html_parts.append("</ul></nav>")
        return "\n".join(html_parts)
