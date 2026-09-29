#!/usr/bin/env python3
"""
doctor.py — One-command setup & readiness verifier for installing `job-hunter` on a new laptop (Windows / macOS / Linux).

Usage:
  Windows:     python .agents/skills/job-hunter/scripts/doctor.py
  macOS/Linux: python3 .agents/skills/job-hunter/scripts/doctor.py
"""

import json
import sys
from pathlib import Path

# Import local sibling helpers
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from build_resume import find_browser  # noqa: E402
from parse_resume import ensure_local_pypdf  # noqa: E402


def main():
    state_dir = Path(".job-hunter")
    resumes_dir = Path("resumes")
    state_dir.mkdir(parents=True, exist_ok=True)
    resumes_dir.mkdir(parents=True, exist_ok=True)

    py_ok = sys.version_info >= (3, 9)
    browser_bin = find_browser()

    # Check PDF extraction capability
    if sys.platform == "darwin":
        pdf_engine = "macOS native Quartz PDFKit (ready)"
        pdf_ok = True
    else:
        pypdf_ready = ensure_local_pypdf(state_dir)
        pdf_engine = (
            "pypdf auto-bootstrapped in .job-hunter/.deps (ready)"
            if pypdf_ready
            else "pure-Python zlib fallback (ready; run `pip install pypdf` if using Canva/LaTeX PDFs)"
        )
        pdf_ok = True

    template_path = SCRIPT_DIR.parent / "assets" / "resume_template.html"
    template_ok = template_path.exists()

    report = {
        "status": "READY" if (py_ok and browser_bin and pdf_ok and template_ok) else "ACTION_NEEDED",
        "os_platform": sys.platform,
        "python_version": sys.version.split()[0],
        "python_ok": py_ok,
        "headless_pdf_browser": browser_bin or "NOT_FOUND (Install Google Chrome or Microsoft Edge)",
        "pdf_text_extractor": pdf_engine,
        "ats_template_present": template_ok,
        "resumes_drop_folder": str(resumes_dir.resolve().as_posix()),
        "next_step": "Drop a resume (.pdf, .docx, or .md) into the `resumes/` folder and tell the agent: 'Run job-hunter on my resume'",
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
