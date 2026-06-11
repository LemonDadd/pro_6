# 功能需求迭代提示词

> 复制下方 **「Agent 提示词」** 整段到 Cursor Agent。
> 来源：第 3 轮 `/不满意原因` 审查（batch / PDF/A-2b / watermark 收尾）。
> 每轮迭代后更新「变更记录」。

---

## 变更记录

| 轮次 | 日期 | 范围 | 状态 |
|------|------|------|------|
| 1 | 2026-06-11 | 页眉页脚页码、同步 30s 超时、sync/async 配额一致 | 已完成 |
| 2 | 2026-06-11 | batch zip 多 md、PDF/A-2b、文本水印 | 已完成（核心链路） |
| 3 | 2026-06-11 | batch 校验补齐、PDF/A 状态可见、验收脚本 | 待开发 |

---

## Agent 提示词（复制从这里开始）

**项目路径**：`/Users/ext.feixuan3/Desktop/solo/pro_6`
**栈**：FastAPI + SQLAlchemy + Celery + Redis + WeasyPrint + MinIO(S3) + Python 3.14

### 核心需求（不变）

在现有 Markdown → PDF 渲染 API 上新增三项能力：

1. **Batch ZIP 多 MD**：一次请求提交多份 Markdown，批量渲染为 PDF 并打包成 ZIP 返回或供下载。
2. **PDF/A-2b 输出**：渲染选项支持输出符合 PDF/A-2b 的长期归档格式（非默认 PDF 1.x）。
3. **Watermark 文本水印**：渲染选项支持在每页叠加可配置的文本水印（如「CONFIDENTIAL」「DRAFT」）。

### 已完成（勿重复改，除非回归）

- `POST /v1/render/batch/jobs`（JSON 请求体）、`inputType: batch`、`outputFormat: zip`、`fileCount`、按文件数扣日配额、整批占 1 并发槽、失败整批 `failed` 并带文件名、审计 `POST /v1/render/batch/jobs`
- `RenderOptions.outputFormat: pdf | pdf-a-2b`，`PdfRenderer` 调用 `write_pdf(pdf_variant="pdf/a-2b")`，失败抛明确错误不降级；S3 Metadata `pdf-variant`
- `RenderOptions.watermark` / `watermarkOpacity` / `watermarkAngle`，CSS `position: fixed` 全页水印，与页眉页脚、PDF/A 可组合
- 页眉页脚 `{{page}}` / `{{pages}}`、同步 30s 超时、sync/async 配额与审计
- SQLite 启动迁移 `fileCount`、`outputFormat` 列；`AsyncRenderRequest` model_validator 修复

### P0 — 必须修复

#### 1. Batch 文件名校验与安全上限

**问题**：`BatchRenderRequest` 只校验 `.md` 后缀和去重，未禁止 `foo/bar.md`、`../x.md` 等路径型文件名；文件数硬编码上限 100，无总 payload 大小限制，与需求文档不一致。

**要求**：

- `filename` 必须是安全 basename：禁止 `/`、`\`、`..`、绝对路径；校验失败返回 422
- 在 `app/config.py` + `.env.example` 增加 `batch_max_files`（建议默认 20）、`batch_max_total_kb`；替换 schemas 中硬编码 100
- 预检阶段校验总 markdown 字节数 ≤ `batch_max_total_kb`

#### 2. 任务状态暴露 PDF/A 输出格式

**问题**：用户提交 `options.outputFormat: "pdf-a-2b"` 后，`GET /v1/render/jobs/{id}` 返回的 `outputFormat` 仍是 `"pdf"`（该字段目前只表示 pdf/zip 容器），无法从状态接口确认将得到归档 PDF。

**要求**：

- 在 `JobStatus` 增加字段（如 `pdfVariant: Optional[Literal["pdf", "pdf-a-2b"]]`），从 `optionsJson` 解析并在创建/查询时返回
- 批量 job 保持 `outputFormat: "zip"`，`pdfVariant` 反映 ZIP 内 PDF 的渲染选项
- 更新 OpenAPI 描述，避免与容器 `outputFormat` 混淆

### P1 — 体验与验收补齐

- 将根目录临时脚本（`test_pdfa.py`、`test_renderer_direct.py`、`test_multipage_watermark.py`、`test_new_features.py`）合并进 `run_tests.py` 或 `tests/`，删除重复文件
- `test_pdfa` 须用 pypdf 读取 `/OutputIntents` 或 XMP `pdfaid` 命名空间，确认 PDF/A 标识（不要仅因 `write_pdf` 无异常即 PASS）
- 水印验收：多页 PDF（含 cover + toc）逐页 `extract_text` 确认 `CONFIDENTIAL` 存在
- README 或 OpenAPI 补充 batch / pdf-a-2b / watermark 各一条 curl 示例

### 验收清单

| 项 | 命令 / 动作 | 期望 |
|----|-------------|------|
| Batch 安全校验 | POST batch，`filename: "../evil.md"` | 422 |
| Batch 上限 | 提交超过 `batch_max_files` 个文件 | 422 |
| Batch 端到端 | 启动 worker + MinIO，`POST .../batch/jobs` 含 2 个 md，轮询至 `done` | `pdfUrl` 下载 ZIP 含 2 个 PDF |
| PDF/A 状态 | POST jobs `options.outputFormat: "pdf-a-2b"`，GET job | `pdfVariant: "pdf-a-2b"` |
| PDF/A 内容 | `.venv/bin/python run_tests.py` 或合并后的 pdf-a 用例 | pypdf 读到 `/OutputIntents` 或 XMP pdfaid |
| 水印多页 | 带 cover+toc+3 页正文的 sync 渲染 | 每页 extract_text 含水印文字 |
| 组合回归 | batch + pdf-a-2b + watermark | ZIP 内 PDF 满足上述两项 |
| 回归 | `python run_tests.py` | 页眉页脚、配额、超时不退化 |

### 工作方式

1. 先读 `app/schemas.py`、`app/services/render_job.py`、`app/config.py`，再改校验与 JobStatus 字段。
2. **最小 diff**：不复制渲染逻辑；验收脚本合并而非再建根目录临时文件。
3. 总结分：**已实现 / 未实现**；附 batch 安全校验、pdf-a-2b 状态查询、水印多页各一条验证命令。

## Agent 提示词（复制到这里结束）
