#!/usr/bin/env python3
"""
build_resume.py — Cross-platform (Windows / macOS / Linux) zero-token differential resume compiler.

Instead of asking the LLM to rewrite the full resume 5 times, the LLM writes a compact
`patches.json` containing only the job-specific deltas (headline, tailored summary,
re-ordered skills, and modified top experience bullets). This script merges each patch
with `candidate_profile.json` and compiles:
  - <Index>_<Company>_<Role>.md
  - <Index>_<Company>_<Role>.html
  - <Index>_<Company>_<Role>.pdf (via headless Chrome or Windows pre-installed Microsoft Edge)

Usage:
  macOS/Linux: python3 .agents/skills/job-hunter/scripts/build_resume.py --profile .job-hunter/candidate_profile.json --patches .job-hunter/runs/<id>/patches.json --outdir .job-hunter/runs/<id>/resumes
  Windows:     python .agents/skills/job-hunter/scripts/build_resume.py --profile .job-hunter/candidate_profile.json --patches .job-hunter/runs/<id>/patches.json --outdir .job-hunter/runs/<id>/resumes
"""

import argparse
import copy
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def get_candidate_browsers() -> list[str]:
    candidates = []
    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA", "")
        prog_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        prog_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        for base in [prog_files, prog_x86, local_app]:
            if not base:
                continue
            candidates.extend(
                [
                    os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"),
                    os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                    os.path.join(base, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
                ]
            )
        # Also check Windows Registry App Paths if available
        try:
            import winreg  # type: ignore
            for exe_name in ("chrome.exe", "msedge.exe", "brave.exe"):
                for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                    try:
                        with winreg.OpenKey(
                            hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"
                        ) as k:
                            val, _ = winreg.QueryValueEx(k, "")
                            if val:
                                candidates.append(val)
                    except OSError:
                        pass
        except Exception:
            pass
        candidates.extend(["chrome", "msedge", "brave"])
    elif sys.platform == "darwin":
        candidates.extend(
            [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                "google-chrome",
                "chromium",
            ]
        )
    else:
        candidates.extend(
            [
                "google-chrome",
                "google-chrome-stable",
                "chromium",
                "chromium-browser",
                "microsoft-edge",
                "brave-browser",
            ]
        )
    return candidates


def find_browser() -> str | None:
    for p in get_candidate_browsers():
        if Path(p).is_file():
            return str(Path(p))
        which_hit = shutil.which(p)
        if which_hit:
            return which_hit
    return None


def slugify(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", text.strip())
    return s.strip("_")[:35] or "Job"


def esc(text: str) -> str:
    return html.escape(str(text or "")).strip()


def format_bold_colon(text: str) -> str:
    """If a bullet starts with 'Label: rest of sentence', bold the label cleanly."""
    escaped = esc(text)
    m = re.match(r"^([A-Za-z0-9 &/+-]{2,28}:)(\s+.*)$", escaped)
    if m:
        return f"<strong>{m.group(1)}</strong>{m.group(2)}"
    return escaped


def apply_patch(base_profile: dict, patch: dict) -> dict:
    merged = copy.deepcopy(base_profile)

    if patch.get("target_headline"):
        merged.setdefault("basics", {})["headline"] = patch["target_headline"]

    if patch.get("tailored_summary"):
        merged["summary"] = patch["tailored_summary"]

    if patch.get("skills_override") and isinstance(patch["skills_override"], dict):
        merged["skills"] = patch["skills_override"]

    bullet_overrides = patch.get("experience_bullet_overrides") or {}
    if isinstance(bullet_overrides, dict):
        for exp in merged.get("experience", []):
            exp_id = exp.get("id") or exp.get("company")
            if exp_id in bullet_overrides:
                new_bullets = bullet_overrides[exp_id]
                if isinstance(new_bullets, list) and new_bullets:
                    orig_bullets = exp.get("bullets", [])
                    if patch.get("replace_all_bullets") or len(new_bullets) >= len(orig_bullets):
                        exp["bullets"] = new_bullets
                    else:
                        exp["bullets"] = new_bullets + orig_bullets[len(new_bullets) :]

    if patch.get("projects_override") and isinstance(patch["projects_override"], list):
        merged["projects"] = patch["projects_override"]

    return merged


def render_markdown(data: dict) -> str:
    basics = data.get("basics", {})
    name = basics.get("name", "Candidate Name")
    headline = basics.get("headline", "")
    contacts = []
    for k in ("location", "email", "phone"):
        if basics.get(k):
            contacts.append(str(basics[k]))
    for link in basics.get("links", []):
        if isinstance(link, dict):
            label = link.get("label") or link.get("url")
            url = link.get("url", "")
            contacts.append(f"[{label}]({url})" if url else str(label))
        elif isinstance(link, str):
            contacts.append(link)

    lines = [f"# {name}"]
    if headline:
        lines.append(f"**{headline}**")
    if contacts:
        lines.append(" | ".join(contacts))
    lines.append("")

    if data.get("summary"):
        lines.extend(["## Professional Summary", data["summary"].strip(), ""])

    skills = data.get("skills", {})
    if skills:
        lines.append("## Technical Skills")
        for cat, items in skills.items():
            val = ", ".join(items) if isinstance(items, list) else str(items)
            lines.append(f"- **{cat}:** {val}")
        lines.append("")

    experiences = data.get("experience", [])
    if experiences:
        lines.append("## Professional Experience")
        for exp in experiences:
            role = exp.get("role", "")
            company = exp.get("company", "")
            dates = exp.get("dates", "")
            loc = exp.get("location", "")
            lines.append(f"### {role} — {company}")
            sub = " | ".join(x for x in [dates, loc] if x)
            if sub:
                lines.append(f"*{sub}*")
            for b in exp.get("bullets", []):
                lines.append(f"- {b}")
            lines.append("")

    projects = data.get("projects", [])
    if projects:
        lines.append("## Key Projects")
        for proj in projects:
            pname = proj.get("name", "")
            tech = proj.get("tech", "")
            dates = proj.get("dates", "")
            header = f"### {pname}" + (f" ({tech})" if tech else "")
            if dates:
                header += f" — *{dates}*"
            lines.append(header)
            for b in proj.get("bullets", []):
                lines.append(f"- {b}")
            lines.append("")

    education = data.get("education", [])
    if education:
        lines.append("## Education")
        for edu in education:
            inst = edu.get("institution", "")
            deg = edu.get("degree", "")
            dates = edu.get("dates", "")
            details = edu.get("details", "")
            lines.append(f"**{inst}** — {deg}" + (f" ({dates})" if dates else ""))
            if details:
                lines.append(f"- {details}")
        lines.append("")

    certs = data.get("certifications", [])
    if certs:
        lines.append("## Certifications & Awards")
        for c in certs:
            lines.append(f"- {c}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def render_html(data: dict, template_str: str) -> str:
    basics = data.get("basics", {})
    name = esc(basics.get("name", "Candidate Name"))
    headline = esc(basics.get("headline", ""))
    headline_block = f'<div class="headline">{headline}</div>' if headline else ""

    contact_spans = []
    for k in ("location", "email", "phone"):
        val = basics.get(k)
        if val:
            if k == "email":
                contact_spans.append(f'<span><a href="mailto:{esc(val)}">{esc(val)}</a></span>')
            else:
                contact_spans.append(f"<span>{esc(val)}</span>")

    for link in basics.get("links", []):
        if isinstance(link, dict):
            label = esc(link.get("label") or link.get("url", ""))
            url = esc(link.get("url", ""))
            if url and not url.startswith(("http://", "https://")):
                url = "https://" + url
            contact_spans.append(f'<span><a href="{url}">{label}</a></span>' if url else f"<span>{label}</span>")
        elif isinstance(link, str):
            u = esc(link)
            href = u if u.startswith(("http://", "https://")) else f"https://{u}"
            contact_spans.append(f'<span><a href="{href}">{u}</a></span>')

    summary_html = ""
    if data.get("summary"):
        summary_html = (
            '<section class="section">'
            '<div class="section-title">Summary</div>'
            f'<div class="summary-text">{esc(data["summary"])}</div>'
            "</section>"
        )

    skills_html = ""
    skills = data.get("skills", {})
    if skills:
        rows = []
        for cat, items in skills.items():
            val = ", ".join(esc(i) for i in items) if isinstance(items, list) else esc(items)
            rows.append(f'<div class="skill-row"><span class="skill-cat">{esc(cat)}:</span> {val}</div>')
        skills_html = (
            '<section class="section">'
            '<div class="section-title">Technical Skills</div>'
            f'<div class="skills-list">{"".join(rows)}</div>'
            "</section>"
        )

    exp_html = ""
    experiences = data.get("experience", [])
    if experiences:
        entries = []
        for exp in experiences:
            company = esc(exp.get("company", ""))
            loc = esc(exp.get("location", ""))
            role = esc(exp.get("role", ""))
            dates = esc(exp.get("dates", ""))
            bullets = "".join(f"<li>{format_bold_colon(b)}</li>" for b in exp.get("bullets", []))
            entries.append(
                '<div class="entry">'
                f'<div class="entry-header"><span>{company}</span><span>{dates}</span></div>'
                f'<div class="entry-sub"><span>{role}</span><span>{loc}</span></div>'
                f'<ul class="bullets">{bullets}</ul>'
                "</div>"
            )
        exp_html = (
            '<section class="section">'
            '<div class="section-title">Experience</div>'
            f'{"".join(entries)}'
            "</section>"
        )

    proj_html = ""
    projects = data.get("projects", [])
    if projects:
        entries = []
        for proj in projects:
            pname = esc(proj.get("name", ""))
            tech = esc(proj.get("tech", ""))
            dates = esc(proj.get("dates", ""))
            title_left = f"{pname}" + (
                f' <span style="font-weight:normal;font-style:italic;">| {tech}</span>' if tech else ""
            )
            bullets = "".join(f"<li>{format_bold_colon(b)}</li>" for b in proj.get("bullets", []))
            entries.append(
                '<div class="entry">'
                f'<div class="entry-header"><span>{title_left}</span><span>{dates}</span></div>'
                f'<ul class="bullets">{bullets}</ul>'
                "</div>"
            )
        proj_html = (
            '<section class="section">'
            '<div class="section-title">Projects</div>'
            f'{"".join(entries)}'
            "</section>"
        )

    edu_html = ""
    education = data.get("education", [])
    if education:
        entries = []
        for edu in education:
            inst = esc(edu.get("institution", ""))
            deg = esc(edu.get("degree", ""))
            dates = esc(edu.get("dates", ""))
            loc = esc(edu.get("location", ""))
            details = esc(edu.get("details", ""))
            detail_ul = f'<ul class="bullets"><li>{details}</li></ul>' if details else ""
            entries.append(
                '<div class="entry">'
                f'<div class="entry-header"><span>{inst}</span><span>{dates}</span></div>'
                f'<div class="entry-sub"><span>{deg}</span><span>{loc}</span></div>'
                f"{detail_ul}"
                "</div>"
            )
        edu_html = (
            '<section class="section">'
            '<div class="section-title">Education</div>'
            f'{"".join(entries)}'
            "</section>"
        )

    cert_html = ""
    certs = data.get("certifications", [])
    if certs:
        items = "".join(f"<li>{esc(c)}</li>" for c in certs)
        cert_html = (
            '<section class="section">'
            '<div class="section-title">Certifications &amp; Honors</div>'
            f'<ul class="bullets">{items}</ul>'
            "</section>"
        )

    out = template_str
    replacements = {
        "{{NAME}}": name,
        "{{TARGET_HEADLINE}}": headline or "Resume",
        "{{HEADLINE_BLOCK}}": headline_block,
        "{{CONTACT_ITEMS}}": "".join(contact_spans),
        "{{SUMMARY_SECTION}}": summary_html,
        "{{SKILLS_SECTION}}": skills_html,
        "{{EXPERIENCE_SECTION}}": exp_html,
        "{{PROJECTS_SECTION}}": proj_html,
        "{{EDUCATION_SECTION}}": edu_html,
        "{{CERTIFICATIONS_SECTION}}": cert_html,
    }
    for k, v in replacements.items():
        out = out.replace(k, v)
    return out


def html_to_pdf(html_path: Path, pdf_path: Path, browser_bin: str | None) -> bool:
    if not browser_bin:
        return False
    # Use .as_uri() so Windows paths become valid file:///C:/... URIs
    file_uri = html_path.resolve().as_uri()
    pdf_out = str(pdf_path.resolve())

    for headless_flag in ("--headless=new", "--headless"):
        cmd = [
            browser_bin,
            headless_flag,
            "--disable-gpu",
            "--no-sandbox",
            "--no-pdf-header-footer",
            "--print-to-pdf-no-header",
            f"--print-to-pdf={pdf_out}",
            file_uri,
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            if res.returncode == 0 and pdf_path.exists() and pdf_path.stat().st_size > 1000:
                return True
        except Exception:
            continue
    return False


def main():
    ap = argparse.ArgumentParser(description="Compile standardized ATS resumes (MD + HTML + PDF) across Windows/macOS/Linux.")
    ap.add_argument("--profile", default=".job-hunter/candidate_profile.json", help="Base candidate_profile.json")
    ap.add_argument("--patches", help="Path to patches.json containing the 5 job patches")
    ap.add_argument("--outdir", default=".job-hunter/resumes", help="Output directory for generated resumes")
    args = ap.parse_args()

    profile_path = Path(args.profile)
    if not profile_path.exists():
        raise FileNotFoundError(f"Base profile not found: {profile_path}")

    base_profile = json.loads(profile_path.read_text(encoding="utf-8"))
    template_path = Path(__file__).resolve().parent.parent / "assets" / "resume_template.html"
    template_str = template_path.read_text(encoding="utf-8")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    browser_bin = find_browser()

    if args.patches:
        patches_data = json.loads(Path(args.patches).read_text(encoding="utf-8"))
        patches = patches_data.get("patches", patches_data) if isinstance(patches_data, dict) else patches_data
    else:
        patches = [{"job_index": 0, "company": "Master", "role_title": "Standardized_Resume"}]

    generated = []
    for idx, patch in enumerate(patches, start=1):
        job_idx = patch.get("job_index", idx)
        company = slugify(patch.get("company", f"Company_{job_idx}"))
        role = slugify(patch.get("role_title", "Role"))
        stem = f"{job_idx:02d}_{company}_{role}"

        tailored_data = apply_patch(base_profile, patch)

        md_path = outdir / f"{stem}.md"
        html_path = outdir / f"{stem}.html"
        pdf_path = outdir / f"{stem}.pdf"

        md_path.write_text(render_markdown(tailored_data), encoding="utf-8")
        html_path.write_text(render_html(tailored_data, template_str), encoding="utf-8")
        pdf_ok = html_to_pdf(html_path, pdf_path, browser_bin)

        generated.append(
            {
                "job_index": job_idx,
                "company": patch.get("company"),
                "role_title": patch.get("role_title"),
                "markdown": str(md_path.resolve().as_posix()),
                "html": str(html_path.resolve().as_posix()),
                "pdf": str(pdf_path.resolve().as_posix()) if pdf_ok else None,
                "pdf_rendered": pdf_ok,
                "browser_used": browser_bin,
            }
        )

    print(json.dumps({"status": "SUCCESS", "platform": sys.platform, "generated_resumes": generated}, indent=2))


if __name__ == "__main__":
    main()
