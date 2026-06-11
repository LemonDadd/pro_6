"""Test script for bug fixes: filename validation, batch limits, pdfVariant, timeout race"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.schemas import BatchFileItem, BatchRenderRequest, JobStatus, RenderOptions
from pydantic import ValidationError


def test_bug1_filename_security():
    print("\n=== Bug 1: Filename Security Validation ===")
    cases = [
        ("../etc/passwd.md", False, "path traversal"),
        ("sub/file.md", False, "path separator /"),
        ("dir\\file.md", False, "path separator \\"),
        ("..\\secret.md", False, "path traversal \\"),
        ("file\x00.md", False, "null byte"),
        ("file|name.md", False, "pipe character"),
        ("file;name.md", False, "semicolon"),
        ("file$(cmd).md", False, "command substitution"),
        ("ch01.md", True, "normal name"),
        ("my-file_v2.md", True, "hyphen and underscore"),
        ("Chapter 1.md", True, "space allowed"),
        ("a.md", True, "short name"),
    ]
    passed = 0
    for filename, should_pass, desc in cases:
        try:
            item = BatchFileItem(filename=filename, markdown="# Test")
            ok = should_pass
        except ValidationError as e:
            ok = not should_pass
        status = "PASS" if ok else "FAIL"
        print(f"  {status}: '{filename}' ({desc}) - expected {'valid' if should_pass else 'invalid'}")
        if ok:
            passed += 1
    print(f"  Result: {passed}/{len(cases)}")
    return passed == len(cases)


def test_bug2_batch_limits():
    print("\n=== Bug 2: Batch Limits in Config ===")
    from app.config import get_settings
    s = get_settings()
    print(f"  batch_max_files: {s.batch_max_files}")
    print(f"  batch_max_payload_kb: {s.batch_max_payload_kb}")

    has_max_files = hasattr(s, "batch_max_files") and s.batch_max_files > 0
    has_max_payload = hasattr(s, "batch_max_payload_kb") and s.batch_max_payload_kb > 0

    print(f"  Config has batch_max_files: {has_max_files}")
    print(f"  Config has batch_max_payload_kb: {has_max_payload}")

    try:
        items = [BatchFileItem(filename=f"file{i}.md", markdown="# Test") for i in range(5)]
        req = BatchRenderRequest(files=items)
        print(f"  Schema accepts 5 files (no hardcoded limit): True")
    except ValidationError as e:
        print(f"  Schema rejects 5 files (unexpected): {e}")
        return False

    return has_max_files and has_max_payload


def test_bug3_pdf_variant():
    print("\n=== Bug 3: JobStatus pdfVariant ===")
    has_field = hasattr(JobStatus, "model_fields") and "pdfVariant" in JobStatus.model_fields
    print(f"  JobStatus has pdfVariant field: {has_field}")

    from app.models import RenderJobDB
    has_db_col = hasattr(RenderJobDB, "pdfVariant")
    print(f"  RenderJobDB has pdfVariant column: {has_db_col}")

    from app.database import run_migrations
    print(f"  run_migrations exists: True")

    return has_field and has_db_col


def test_bug4_race_condition():
    print("\n=== Bug 4: Sync Timeout Race Condition ===")
    import inspect
    src = inspect.getsource(RenderJobService.execute_sync_render_workload)
    has_refresh_check = "thread_db.refresh(job)" in src and 'job.status == "failed"' in src
    print(f"  Workload has pre-commit refresh+check: {has_refresh_check}")

    mark_src = inspect.getsource(RenderJobService.mark_job_failed)
    has_status_guard = 'job.status in ("queued", "processing")' in mark_src
    print(f"  mark_job_failed guards status: {has_status_guard}")

    from app.api.v1.routes import render_sync
    route_src = inspect.getsource(render_sync)
    has_408 = "HTTP_408_REQUEST_TIMEOUT" in route_src
    print(f"  Route uses HTTP 408 for timeout: {has_408}")

    has_empty_check = "not pdf_bytes" in route_src
    print(f"  Route checks empty pdf_bytes: {has_empty_check}")

    has_error_mark_failed = "mark_job_failed" in route_src and "except Exception" in route_src
    print(f"  Route calls mark_job_failed on error: {has_error_mark_failed}")

    return has_refresh_check and has_status_guard and has_408 and has_empty_check


def main():
    results = {}
    results["bug1-filename"] = test_bug1_filename_security()
    results["bug2-batch-limits"] = test_bug2_batch_limits()
    results["bug3-pdf-variant"] = test_bug3_pdf_variant()
    results["bug4-race-condition"] = test_bug4_race_condition()

    print("\n" + "=" * 50)
    print("Summary:")
    for name, ok in results.items():
        print(f"  {name}: {'PASS' if ok else 'FAIL'}")
    all_pass = all(results.values())
    print(f"\nOverall: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
    return all_pass


if __name__ == "__main__":
    from app.services.render_job import RenderJobService
    main()
