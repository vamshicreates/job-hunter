#!/usr/bin/env python3
"""
parse_resume.py — Cross-platform (Windows / macOS / Linux) token-minimal local resume extractor & cache manager.

Usage:
  macOS/Linux: python3 .agents/skills/job-hunter/scripts/parse_resume.py [path_to_resume_or_dir] [--state-dir .job-hunter] [--force]
  Windows:     python .agents/skills/job-hunter/scripts/parse_resume.py [path_to_resume_or_dir] [--state-dir .job-hunter] [--force]

Behavior:
  1. Finds the resume file (.pdf, .docx, .doc, .rtf, .md, .txt) in the given path or workspace.
  2. Computes SHA-256 hash. If .job-hunter/candidate_profile.json exists with the same
     source_hash (and --force is not set), returns CACHE_HIT with a compact summary (~250 tokens).
  3. Otherwise extracts clean plain text using cross-platform extractors:
     - PDF: pypdf/fitz/pdfplumber (if installed) -> macOS Quartz PDFKit -> pdftotext CLI -> Pure-Python zlib PDF stream parser (works on Windows out-of-the-box).
     - DOCX: Pure-Python zipfile + XML parser (works on Windows, macOS, Linux with zero dependencies).
     - RTF/DOC: macOS textutil / Windows PowerShell RichTextBox / pure-Python RTF stripper.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zlib
import zipfile
from pathlib import Path

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".rtf", ".md", ".txt"}
IGNORE_DIRS = {".git", ".agents", ".job-hunter", "node_modules", "__pycache__", ".venv", "venv"}
IGNORE_FILES = {"readme.md", "skill.md", "claude.md", "site.md", "design.md", "license.md"}


def find_resume_file(target_path: Path) -> Path:
    if target_path.is_file():
        return target_path

    candidates = []
    for root, dirs, files in os.walk(target_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
        for fname in files:
            if fname.lower() in IGNORE_FILES or fname.startswith("."):
                continue
            fpath = Path(root) / fname
            if fpath.suffix.lower() in SUPPORTED_EXTENSIONS:
                name_lower = fname.lower()
                priority = 2 if ("resume" in name_lower or "cv" in name_lower) else 1
                candidates.append((priority, fpath.stat().st_mtime, fpath))

    if not candidates:
        raise FileNotFoundError(
            f"No resume file ({', '.join(sorted(SUPPORTED_EXTENSIONS))}) found in {target_path}"
        )
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


def file_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _decode_pdf_literal(s: str) -> str:
    """Decode PDF literal string escapes like \\n, \\r, \\(, \\), and octal \\ddd."""
    def replace_octal(m):
        return chr(int(m.group(1), 8))

    s = re.sub(r"\\([0-7]{1,3})", replace_octal, s)
    s = (
        s.replace(r"\n", "\n")
        .replace(r"\r", "\r")
        .replace(r"\t", " ")
        .replace(r"\(", "(")
        .replace(r"\)", ")")
        .replace(r"\\", "\\")
    )
    return s


def extract_pdf_pure_python(filepath: Path) -> str:
    """
    Pure-Python stdlib fallback PDF text extractor for Windows/Linux when no third-party
    PDF libraries or CLI tools are installed. Decompresses FlateDecode streams and extracts
    Tj / TJ text blocks.
    """
    raw_bytes = filepath.read_bytes()
    streams = []

    # Find all stream ... endstream blocks
    for m in re.finditer(rb"stream[\r\n]+(.*?)[\r\n]+endstream", raw_bytes, re.DOTALL):
        stream_data = m.group(1)
        decompressed = None
        for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
            try:
                decompressed = zlib.decompress(stream_data, wbits)
                break
            except Exception:
                continue
        if decompressed is None:
            decompressed = stream_data
        try:
            streams.append(decompressed.decode("latin-1", errors="ignore"))
        except Exception:
            pass

    extracted_lines = []
    for content in streams:
        if "BT" not in content:
            continue
        # Process each BT ... ET text object
        for bt_block in re.findall(r"BT(.*?)ET", content, re.DOTALL):
            pieces = []
            # Match either (...) Tj or [(...)] TJ
            for token_match in re.finditer(r"\[(.*?)\]\s*TJ|\((?:\\.|[^\\()])*\)\s*Tj", bt_block, re.DOTALL):
                tj_array = token_match.group(1)
                if tj_array is not None:
                    sub_strs = re.findall(r"\(((?:\\.|[^\\()])*)\)", tj_array)
                    pieces.append("".join(_decode_pdf_literal(x) for x in sub_strs))
                else:
                    single = re.search(r"\(((?:\\.|[^\\()])*)\)\s*Tj", token_match.group(0))
                    if single:
                        pieces.append(_decode_pdf_literal(single.group(1)))
            line = " ".join("".join(pieces).split())
            if line:
                extracted_lines.append(line)

    result = "\n".join(extracted_lines)
    # Remove non-printable control chars except newline/tab
    result = "".join(ch for ch in result if ch == "\n" or ch == "\t" or (32 <= ord(ch) <= 126) or ord(ch) >= 160)
    return result.strip()


def extract_pdf_text(filepath: Path) -> str:
    # Method 1: Optional Python libraries (cross-platform: Windows, macOS, Linux)
    try:
        import pypdf  # type: ignore
        reader = pypdf.PdfReader(str(filepath))
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        if text:
            return text
    except Exception:
        pass

    try:
        import fitz  # PyMuPDF # type: ignore
        doc = fitz.open(str(filepath))
        text = "\n".join(page.get_text() for page in doc).strip()
        if text:
            return text
    except Exception:
        pass

    try:
        import pdfplumber  # type: ignore
        with pdfplumber.open(str(filepath)) as pdf:
            text = "\n".join((p.extract_text() or "") for p in pdf.pages).strip()
            if text:
                return text
    except Exception:
        pass

    # Method 2: macOS native Quartz PDFKit via osascript
    if sys.platform == "darwin":
        jxa_script = f"""
        ObjC.import('Foundation');
        ObjC.import('Quartz');
        var url = $.NSURL.fileURLWithPath({json.dumps(str(filepath.resolve()))});
        var doc = $.PDFDocument.alloc.initWithURL(url);
        if (!doc || doc.isNil()) {{
            throw new Error('Could not open PDF via Quartz');
        }}
        var out = [];
        var count = doc.pageCount;
        for (var i = 0; i < count; i++) {{
            var page = doc.pageAtIndex(i);
            var s = page.string;
            if (s && !s.isNil()) {{
                out.push(ObjC.unwrap(s));
            }}
        }}
        out.join('\\n--- PAGE ---\\n');
        """
        try:
            res = subprocess.run(
                ["osascript", "-l", "JavaScript", "-e", jxa_script],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass

    # Method 3: pdftotext CLI (if installed via Poppler / Git for Windows / Scoop / Chocolatey / Linux)
    try:
        res = subprocess.run(
            ["pdftotext", str(filepath), "-"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass

    # Method 4: Pure-Python stdlib zlib stream parser (works on Windows out-of-the-box)
    text = extract_pdf_pure_python(filepath)
    if len(text) >= 40:
        return text

    raise RuntimeError(
        f"Could not extract text from PDF {filepath}. On Windows, install pypdf (`pip install pypdf`) if the PDF uses custom font encodings."
    )


def extract_docx_or_rtf_text(filepath: Path) -> str:
    ext = filepath.suffix.lower()

    # Method 1 (Primary for .docx on all OSes): Pure Python stdlib zipfile + XML parser
    if ext == ".docx":
        try:
            paragraphs = []
            with zipfile.ZipFile(filepath) as zf:
                xml_content = zf.read("word/document.xml")
                tree = ET.fromstring(xml_content)
                for elem in tree.iter():
                    if elem.tag.endswith("}p"):
                        texts = [t.text for t in elem.iter() if t.tag.endswith("}t") and t.text]
                        if texts:
                            paragraphs.append("".join(texts))
            if paragraphs:
                return "\n".join(paragraphs)
        except Exception:
            pass

    # Method 2: macOS built-in textutil for .doc / .rtf / .docx
    if sys.platform == "darwin":
        try:
            res = subprocess.run(
                ["textutil", "-convert", "txt", "-stdout", str(filepath)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass

    # Method 3: Windows PowerShell RichTextBox / Word COM fallback for .rtf / .doc
    if sys.platform == "win32" and ext == ".rtf":
        ps_cmd = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$rtb = New-Object System.Windows.Forms.RichTextBox; "
            f"$rtb.LoadFile({json.dumps(str(filepath.resolve()))}); "
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            "Write-Output $rtb.Text"
        )
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass

    # Method 4: Pure-Python basic RTF control-word stripper
    if ext == ".rtf":
        raw = filepath.read_text(encoding="utf-8", errors="ignore")
        stripped = re.sub(r"\\par[d]?", "\n", raw)
        stripped = re.sub(r"\\[a-zA-Z]+\d*\s?", "", stripped)
        stripped = stripped.replace("{", "").replace("}", "")
        if stripped.strip():
            return stripped.strip()

    raise RuntimeError(f"Could not extract text from {filepath}")


def extract_text(filepath: Path) -> str:
    ext = filepath.suffix.lower()
    if ext == ".pdf":
        raw = extract_pdf_text(filepath)
    elif ext in {".docx", ".doc", ".rtf"}:
        raw = extract_docx_or_rtf_text(filepath)
    else:
        raw = filepath.read_text(encoding="utf-8", errors="replace")

    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw.splitlines()]
    cleaned = []
    blank_streak = 0
    for line in lines:
        if not line:
            blank_streak += 1
            if blank_streak <= 1:
                cleaned.append("")
        else:
            blank_streak = 0
            cleaned.append(line)
    return "\n".join(cleaned).strip()


def extract_contact_hints(text: str) -> dict:
    emails = list(dict.fromkeys(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)))
    phones = list(
        dict.fromkeys(
            re.findall(r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}", text)
        )
    )
    urls = list(
        dict.fromkeys(
            re.findall(
                r"(?:https?://)?(?:www\.)?(?:linkedin\.com/in/[A-Za-z0-9_-]+|github\.com/[A-Za-z0-9_.-]+|[A-Za-z0-9.-]+\.(?:dev|io|me|com|org|ai)/[A-Za-z0-9_./-]*)",
                text,
                re.IGNORECASE,
            )
        )
    )
    return {
        "emails": emails[:2],
        "phones": phones[:2],
        "links": urls[:6],
    }


def main():
    parser = argparse.ArgumentParser(description="Extract and cache resume profile with minimum tokens (Windows/macOS/Linux).")
    parser.add_argument("path", nargs="?", default=".", help="Path to resume file or directory")
    parser.add_argument("--state-dir", default=".job-hunter", help="Directory to store cached profile")
    parser.add_argument("--force", action="store_true", help="Force re-extraction even if hash matches")
    args = parser.parse_args()

    state_dir = Path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    profile_path = state_dir / "candidate_profile.json"

    try:
        resume_file = find_resume_file(Path(args.path))
    except FileNotFoundError as e:
        print(json.dumps({"status": "ERROR", "message": str(e)}, indent=2))
        sys.exit(1)

    current_hash = file_sha256(resume_file)

    if profile_path.exists() and not args.force:
        try:
            cached = json.loads(profile_path.read_text(encoding="utf-8"))
            if cached.get("source_hash") == current_hash:
                summary_payload = {
                    "status": "CACHE_HIT",
                    "platform": sys.platform,
                    "profile_path": str(profile_path.as_posix()),
                    "source_file": str(resume_file.as_posix()),
                    "source_hash": current_hash,
                    "candidate_name": cached.get("basics", {}).get("name"),
                    "target_roles": cached.get("search_targets", {}).get("target_roles", []),
                    "seniority": cached.get("search_targets", {}).get("seniority"),
                    "years_of_experience": cached.get("search_targets", {}).get("years_of_experience"),
                    "locations": cached.get("search_targets", {}).get("locations", []),
                    "core_skills": cached.get("skills", {}),
                }
                print(json.dumps(summary_payload, indent=2))
                return
        except Exception:
            pass

    raw_text = extract_text(resume_file)
    hints = extract_contact_hints(raw_text)

    raw_extract_path = state_dir / "raw_resume_extract.json"
    extract_data = {
        "status": "CACHE_MISS_EXTRACTED",
        "platform": sys.platform,
        "source_file": str(resume_file.as_posix()),
        "source_hash": current_hash,
        "profile_target_path": str(profile_path.as_posix()),
        "detected_contacts": hints,
        "raw_text": raw_text,
    }
    raw_extract_path.write_text(json.dumps(extract_data, indent=2), encoding="utf-8")
    print(json.dumps(extract_data, indent=2))


if __name__ == "__main__":
    main()
