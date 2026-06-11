"""Test script for new features: PDF/A-2b, Watermark, Batch ZIP"""
import json
import io
import zipfile
from pypdf import PdfReader
import httpx

API_BASE = "http://localhost:8000"
API_KEY = "test-key-123"
HEADERS = {"X-API-Key": API_KEY}


def test_watermark_sync():
    print("\n=== Test 1: Watermark (sync) ===")
    payload = {
        "markdown": "# Hello World\n\nThis is a test document with a watermark.\n\n## Section 1\n\nSome content here.\n\n## Section 2\n\nMore content here.",
        "theme": "default",
        "options": {
            "watermark": "CONFIDENTIAL",
            "watermarkOpacity": 0.2,
            "watermarkAngle": -45,
            "footer": "Page {{page}} of {{pages}}"
        }
    }
    with httpx.Client() as client:
        r = client.post(f"{API_BASE}/v1/render/sync", json=payload, headers=HEADERS, timeout=30)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        print(f"Content-Type: {r.headers.get('content-type')}")
        print(f"Size: {len(r.content)} bytes")
        reader = PdfReader(io.BytesIO(r.content))
        print(f"Pages: {len(reader.pages)}")
        text = reader.pages[0].extract_text() or ""
        has_watermark_text = "CONFIDENTIAL" in text
        print(f"Page 1 has watermark text (visible in text layer): {has_watermark_text}")
        with open("test_watermark.pdf", "wb") as f:
            f.write(r.content)
        print("Saved to test_watermark.pdf")
    else:
        print(f"Error: {r.text}")
    return r.status_code == 200


def test_pdfa_sync():
    print("\n=== Test 2: PDF/A-2b (sync) ===")
    payload = {
        "markdown": "# PDF/A Test\n\nThis document should be PDF/A-2b compliant.",
        "theme": "default",
        "options": {
            "outputFormat": "pdf-a-2b"
        }
    }
    with httpx.Client() as client:
        r = client.post(f"{API_BASE}/v1/render/sync", json=payload, headers=HEADERS, timeout=30)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        print(f"Size: {len(r.content)} bytes")
        reader = PdfReader(io.BytesIO(r.content))
        metadata = reader.metadata
        print(f"PDF Metadata: {dict(metadata) if metadata else 'None'}")
        pdfa_header = r.content[:8]
        print(f"First 8 bytes: {pdfa_header}")
        with open("test_pdfa.pdf", "wb") as f:
            f.write(r.content)
        print("Saved to test_pdfa.pdf")
    else:
        print(f"Error: {r.text}")
    return r.status_code == 200


def test_batch_job():
    print("\n=== Test 3: Batch ZIP (async) ===")
    payload = {
        "files": [
            {"filename": "intro.md", "markdown": "# Introduction\n\nThis is the intro document."},
            {"filename": "chapter1.md", "markdown": "# Chapter 1\n\nContent of chapter 1.\n\n## Section A\n\nDetails."},
            {"filename": "chapter2.md", "markdown": "# Chapter 2\n\nContent of chapter 2."},
        ],
        "theme": "github",
        "options": {
            "watermark": "DRAFT",
            "footer": "{{page}}/{{pages}}"
        }
    }
    with httpx.Client() as client:
        r = client.post(f"{API_BASE}/v1/render/batch/jobs", json=payload, headers=HEADERS, timeout=10)
    print(f"Status: {r.status_code}")
    if r.status_code == 202:
        job = r.json()
        print(f"Job ID: {job['id']}")
        print(f"Status: {job['status']}")
        print(f"inputType: {job['inputType']}")
        print(f"outputFormat: {job['outputFormat']}")
        print(f"fileCount: {job['fileCount']}")
        return True, job['id']
    else:
        print(f"Error: {r.text}")
        return False, None


def main():
    results = {}
    results["watermark"] = test_watermark_sync()
    results["pdfa"] = test_pdfa_sync()
    ok, job_id = test_batch_job()
    results["batch"] = ok

    print("\n=== Summary ===")
    for name, ok in results.items():
        print(f"  {name}: {'PASS' if ok else 'FAIL'}")

    if job_id:
        print(f"\nBatch job ID: {job_id}")
        print(f"Check status: GET /v1/render/jobs/{job_id}")


if __name__ == "__main__":
    main()
