#!/usr/bin/env python3
"""
apply_helper.py — Cross-platform (Windows / macOS / Linux) approval-gated browser pre-filler & Application Copilot.

Safety Contract:
  - ONLY runs for job indices explicitly approved by the user (--approve 1 3 ...).
  - Opens the target job application URL in Chrome / Edge / default browser.
  - Reveals & highlights the tailored ATS PDF in Windows File Explorer (`explorer.exe /select,...`)
    or macOS Finder (`open -R ...`), and copies the native PDF path to the OS clipboard (`clip.exe` / `pbcopy`)
    so pressing Ctrl+V in the Windows File Upload dialog attaches the PDF immediately.
  - Launches the interactive `application_copilot.html` dashboard containing:
      1. Drag-to-bookmark-bar "⚡ Auto-Fill & Pause Before Submit" bookmarklets (works on Windows Chrome/Edge/Brave & macOS),
      2. 1-click copy buttons for native PDF paths, contact info, cover notes, and custom screening answers.
  - NEVER clicks the final Submit button — always pauses for the user's manual click.

Usage:
  macOS/Linux: python3 .agents/skills/job-hunter/scripts/apply_helper.py --profile .job-hunter/candidate_profile.json --patches .job-hunter/runs/<id>/patches.json --resumes-dir .job-hunter/runs/<id>/resumes --approve 1 2
  Windows:     python .agents/skills/job-hunter/scripts/apply_helper.py --profile .job-hunter/candidate_profile.json --patches .job-hunter/runs/<id>/patches.json --resumes-dir .job-hunter/runs/<id>/resumes --approve 1 2
"""

import argparse
import html
import json
import os
import subprocess
import sys
import urllib.parse
import webbrowser
from pathlib import Path


def build_autofill_js(candidate: dict, job_patch: dict, pdf_path: str) -> str:
    basics = candidate.get("basics", {})
    full_name = basics.get("name", "")
    parts = full_name.split()
    first_name = parts[0] if parts else ""
    last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
    email = basics.get("email", "")
    phone = basics.get("phone", "")
    location = basics.get("location", "")

    linkedin = ""
    github = ""
    portfolio = ""
    for link in basics.get("links", []):
        u = link.get("url", "") if isinstance(link, dict) else str(link)
        ul = u.lower()
        if "linkedin.com" in ul and not linkedin:
            linkedin = u
        elif "github.com" in ul and not github:
            github = u
        elif u and not portfolio:
            portfolio = u

    payload = {
        "fullName": full_name,
        "firstName": first_name,
        "lastName": last_name,
        "email": email,
        "phone": phone,
        "location": location,
        "linkedin": linkedin,
        "github": github,
        "portfolio": portfolio,
        "coverNote": job_patch.get("cover_note", ""),
        "customAnswers": job_patch.get("drafted_answers", {}),
        "resumePdfPath": pdf_path,
        "company": job_patch.get("company", ""),
        "role": job_patch.get("role_title", ""),
    }

    return f"""
(function() {{
  const data = {json.dumps(payload)};
  function setNativeValue(el, val) {{
    if (!el || !val) return false;
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
                || Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
    if (setter) {{
      setter.call(el, val);
    }} else {{
      el.value = val;
    }}
    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    el.style.outline = '2px solid #10b981';
    return true;
  }}

  const inputs = Array.from(document.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]), textarea'));
  let filledCount = 0;

  for (const el of inputs) {{
    if (el.type === 'file') {{
      el.style.outline = '3px dashed #f59e0b';
      continue;
    }}
    const labelEl = el.id ? document.querySelector(`label[for="${{CSS.escape(el.id)}}"]`) : el.closest('label');
    const hint = [
      el.name || '',
      el.id || '',
      el.placeholder || '',
      el.getAttribute('aria-label') || '',
      labelEl ? labelEl.innerText : ''
    ].join(' ').toLowerCase();

    if (hint.includes('first_name') || hint.includes('firstname') || hint.includes('first name')) {{
      if (setNativeValue(el, data.firstName)) filledCount++;
    }} else if (hint.includes('last_name') || hint.includes('lastname') || hint.includes('last name')) {{
      if (setNativeValue(el, data.lastName)) filledCount++;
    }} else if (hint.includes('full name') || hint === 'name' || hint.includes('your name') || hint.includes('candidate name')) {{
      if (setNativeValue(el, data.fullName)) filledCount++;
    }} else if (hint.includes('email') || el.type === 'email') {{
      if (setNativeValue(el, data.email)) filledCount++;
    }} else if (hint.includes('phone') || hint.includes('mobile') || el.type === 'tel') {{
      if (setNativeValue(el, data.phone)) filledCount++;
    }} else if (hint.includes('linkedin')) {{
      if (setNativeValue(el, data.linkedin)) filledCount++;
    }} else if (hint.includes('github')) {{
      if (setNativeValue(el, data.github)) filledCount++;
    }} else if (hint.includes('portfolio') || hint.includes('website') || hint.includes('personal url')) {{
      if (setNativeValue(el, data.portfolio || data.github || data.linkedin)) filledCount++;
    }} else if (hint.includes('location') || hint.includes('city')) {{
      if (setNativeValue(el, data.location)) filledCount++;
    }} else if (el.tagName === 'TEXTAREA' && (hint.includes('cover') || hint.includes('additional') || hint.includes('why '))) {{
      if (setNativeValue(el, data.coverNote)) filledCount++;
    }}
  }}

  const submitBtns = Array.from(document.querySelectorAll('button[type=submit], input[type=submit], button'));
  for (const btn of submitBtns) {{
    const t = (btn.innerText || btn.value || '').toLowerCase();
    if (t.includes('submit') || t.includes('apply')) {{
      btn.style.outline = '4px solid #22c55e';
      btn.style.boxShadow = '0 0 16px rgba(34,197,94,0.6)';
    }}
  }}

  const old = document.getElementById('jh-copilot-banner');
  if (old) old.remove();
  const banner = document.createElement('div');
  banner.id = 'jh-copilot-banner';
  banner.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:999999;background:#0f172a;color:#f8fafc;padding:14px 18px;border-radius:10px;box-shadow:0 10px 25px rgba(0,0,0,0.35);font-family:system-ui,sans-serif;font-size:13px;max-width:360px;border:1px solid #334155;';
  banner.innerHTML = `
    <div style="font-weight:700;color:#4ade80;margin-bottom:4px;">✓ Job Hunter Pre-Fill Active (Paused Before Submit)</div>
    <div style="color:#cbd5e1;margin-bottom:6px;">Auto-filled <b>${{filledCount}}</b> field(s) for <b>${{data.company}}</b>.</div>
    <div style="font-size:12px;color:#94a3b8;margin-bottom:6px;">Attach tailored PDF:<br/><code style="color:#fbbf24;word-break:break-all;">${{data.resumePdfPath}}</code></div>
    <div style="font-size:11px;color:#e2e8f0;">Review fields & click <b>Submit</b> manually when ready.</div>
  `;
  document.body.appendChild(banner);
  return filledCount;
}})();
""".strip()


def copy_to_os_clipboard(text: str) -> bool:
    if not text:
        return False
    try:
        if sys.platform == "win32":
            subprocess.run(["clip.exe"], input=text.encode("utf-16le"), check=False, timeout=5)
            return True
        elif sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=False, timeout=5)
            return True
        else:
            subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode("utf-8"), check=False, timeout=5)
            return True
    except Exception:
        return False


def reveal_file_in_os(filepath: str):
    if not filepath or not Path(filepath).exists():
        return
    norm_path = os.path.normpath(filepath)
    try:
        if sys.platform == "win32":
            # Opens Windows File Explorer with the exact PDF highlighted
            subprocess.Popen(["explorer.exe", f"/select,{norm_path}"])
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", norm_path], check=False)
        else:
            subprocess.Popen(["xdg-open", str(Path(norm_path).parent)])
    except Exception:
        pass


def open_url_or_file_cross_platform(target: str):
    try:
        if sys.platform == "win32":
            if target.startswith(("http://", "https://")):
                webbrowser.open(target)
            else:
                os.startfile(os.path.normpath(target))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", target], check=False)
        else:
            webbrowser.open(target)
    except Exception:
        webbrowser.open(target)


def launch_and_prefill(url: str, js_code: str) -> str:
    if sys.platform == "darwin":
        subprocess.run(["open", "-a", "Google Chrome", url], check=False)
        applescript = f"""
        delay 3.5
        tell application "Google Chrome"
            if (count of windows) > 0 then
                execute active tab of front window javascript {json.dumps(js_code)}
            end if
        end tell
        """
        try:
            res = subprocess.run(["osascript", "-e", applescript], capture_output=True, text=True, timeout=12)
            if res.returncode == 0:
                return f"MACOS_CHROME_AUTOFILLED (fields={res.stdout.strip()})"
        except Exception:
            pass
        return "OPENED_TAB_AND_COPILOT_DASHBOARD"

    # Windows & Linux: open URL in default browser (Chrome/Edge) and use Copilot Bookmarklet / Console / Clipboard
    open_url_or_file_cross_platform(url)
    return "OPENED_TAB_AND_COPILOT_DASHBOARD (use 1-click Bookmarklet or Ctrl+V path in Windows File Dialog)"


def generate_copilot_html(candidate: dict, approved_patches: list, resumes_dir: Path, out_html: Path):
    basics = candidate.get("basics", {})
    is_win = sys.platform == "win32"
    shortcut_hint = "Ctrl+V" if is_win else "Cmd+Shift+G"

    cards_html = []
    for p in approved_patches:
        idx = p.get("job_index", 1)
        company = html.escape(p.get("company", ""))
        role = html.escape(p.get("role_title", ""))
        url = html.escape(p.get("job_url", ""))
        cover = html.escape(p.get("cover_note", ""))
        pdf_files = list(resumes_dir.glob(f"{idx:02d}_*.pdf"))
        native_pdf_path = os.path.normpath(str(pdf_files[0].resolve())) if pdf_files else "See resumes folder"

        js_autofill = build_autofill_js(candidate, p, native_pdf_path)
        bookmarklet_href = "javascript:" + urllib.parse.quote(js_autofill)

        answers_rows = []
        for q, ans in (p.get("drafted_answers") or {}).items():
            answers_rows.append(
                f'<div class="qa"><strong>{html.escape(q)} (Click box to copy):</strong>'
                f'<pre onclick="navigator.clipboard.writeText(this.innerText)">{html.escape(str(ans))}</pre></div>'
            )

        cards_html.append(
            f"""
            <div class="card">
              <div class="card-head">
                <div>
                  <span class="badge">Job #{idx} Approved</span>
                  <h2>{role} — {company}</h2>
                </div>
                <div class="btn-group">
                  <a class="bookmarklet" href="{bookmarklet_href}" title="Drag me to your Bookmarks Bar, then click me on the job tab to auto-fill all fields!">⚡ Auto-Fill Job #{idx} (Drag to Bookmarks Bar)</a>
                  <a class="btn" href="{url}" target="_blank">Open Application Form ↗</a>
                </div>
              </div>
              <div class="field-row">
                <strong>Tailored ATS Resume PDF (Click path to copy — paste with {shortcut_hint} in file upload dialog):</strong>
                <pre class="path-box" onclick="navigator.clipboard.writeText(this.innerText)">{html.escape(native_pdf_path)}</pre>
              </div>
              <div class="qa">
                <strong>Tailored Cover Note / "Why {company}?" (Click box to copy):</strong>
                <pre onclick="navigator.clipboard.writeText(this.innerText)">{cover}</pre>
              </div>
              {"".join(answers_rows)}
            </div>
            """
        )

    page = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>Job Hunter — Cross-Platform Application Copilot</title>
  <style>
    body {{ font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; max-width: 940px; margin: 28px auto; padding: 0 20px; }}
    h1 {{ font-size: 22px; margin-bottom: 6px; }}
    .sub {{ color: #94a3b8; font-size: 14px; margin-bottom: 20px; line-height: 1.5; }}
    .quick-bar {{ background: #1e293b; padding: 12px 16px; border-radius: 8px; margin-bottom: 20px; display: flex; gap: 12px; flex-wrap: wrap; border: 1px solid #334155; }}
    .chip {{ background: #334155; padding: 6px 10px; border-radius: 6px; font-size: 13px; cursor: pointer; user-select: none; }}
    .chip:hover {{ background: #475569; }}
    .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 18px; margin-bottom: 16px; }}
    .card-head {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 10px; }}
    .card-head h2 {{ font-size: 18px; margin: 4px 0 0 0; }}
    .btn-group {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
    .badge {{ background: #065f46; color: #6ee7b7; font-size: 11px; padding: 3px 8px; border-radius: 99px; font-weight: 600; }}
    .btn {{ background: #2563eb; color: #fff; text-decoration: none; padding: 8px 14px; border-radius: 6px; font-weight: 600; font-size: 13px; }}
    .bookmarklet {{ background: #f59e0b; color: #0f172a; text-decoration: none; padding: 8px 12px; border-radius: 6px; font-weight: 700; font-size: 12px; cursor: grab; }}
    .field-row {{ font-size: 13px; color: #cbd5e1; margin-bottom: 10px; }}
    .path-box {{ color: #fbbf24; font-family: Consolas, monospace; font-size: 12.5px; }}
    .qa {{ margin-top: 10px; font-size: 13px; }}
    pre {{ background: #0f172a; border: 1px solid #334155; padding: 10px; border-radius: 6px; white-space: pre-wrap; word-break: break-all; cursor: pointer; color: #e2e8f0; margin-top: 4px; }}
    pre:hover {{ border-color: #38bdf8; }}
  </style>
</head>
<body>
  <h1>Job Hunter — Application Copilot (Paused Before Submit)</h1>
  <div class="sub">
    • <b>Windows &amp; Mac Instant File Upload:</b> Click the yellow PDF path box to copy it, then press <b>Ctrl+V</b> (Windows) or <b>Cmd+Shift+G</b> (Mac) inside the browser's File Upload dialog.<br/>
    • <b>Instant Form Auto-Fill:</b> Drag the orange <b>⚡ Auto-Fill</b> button to your Bookmarks Bar and click it on the open job tab to fill fields and highlight Submit without clicking it.
  </div>
  <div class="quick-bar">
    <div class="chip" onclick="navigator.clipboard.writeText('{html.escape(basics.get('name', ''))}')">Copy Name: {html.escape(basics.get('name', ''))}</div>
    <div class="chip" onclick="navigator.clipboard.writeText('{html.escape(basics.get('email', ''))}')">Copy Email: {html.escape(basics.get('email', ''))}</div>
    <div class="chip" onclick="navigator.clipboard.writeText('{html.escape(basics.get('phone', ''))}')">Copy Phone: {html.escape(basics.get('phone', ''))}</div>
  </div>
  {"".join(cards_html)}
</body>
</html>"""
    out_html.write_text(page, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Pre-fill approved job applications and pause at Submit (Windows/macOS/Linux).")
    ap.add_argument("--profile", default=".job-hunter/candidate_profile.json")
    ap.add_argument("--patches", required=True, help="Path to patches.json")
    ap.add_argument("--resumes-dir", required=True, help="Directory containing generated PDFs")
    ap.add_argument("--approve", nargs="+", type=int, required=True, help="Approved job numbers (e.g. 1 3)")
    args = ap.parse_args()

    candidate = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    patches_raw = json.loads(Path(args.patches).read_text(encoding="utf-8"))
    patches = patches_raw.get("patches", patches_raw) if isinstance(patches_raw, dict) else patches_raw
    resumes_dir = Path(args.resumes_dir)

    approved_set = set(args.approve)
    approved_patches = [p for p in patches if p.get("job_index") in approved_set]

    if not approved_patches:
        print(json.dumps({"status": "ERROR", "message": f"No matching jobs found for indices {args.approve}"}))
        return

    copilot_path = resumes_dir.parent / "application_copilot.html"
    generate_copilot_html(candidate, approved_patches, resumes_dir, copilot_path)
    open_url_or_file_cross_platform(str(copilot_path.resolve()))

    actions = []
    first_pdf_copied = False
    for p in approved_patches:
        idx = p.get("job_index")
        url = p.get("job_url", "")
        pdf_matches = list(resumes_dir.glob(f"{idx:02d}_*.pdf"))
        native_pdf_path = os.path.normpath(str(pdf_matches[0].resolve())) if pdf_matches else ""

        if native_pdf_path:
            reveal_file_in_os(native_pdf_path)
            if not first_pdf_copied:
                copy_to_os_clipboard(native_pdf_path)
                first_pdf_copied = True

        status = "NO_URL"
        if url:
            js_code = build_autofill_js(candidate, p, native_pdf_path)
            status = launch_and_prefill(url, js_code)

        actions.append(
            {
                "job_index": idx,
                "company": p.get("company"),
                "role_title": p.get("role_title"),
                "job_url": url,
                "tailored_pdf": str(Path(native_pdf_path).as_posix()) if native_pdf_path else "",
                "native_os_pdf_path": native_pdf_path,
                "autofill_status": status,
                "submit_clicked": False,
            }
        )

    print(
        json.dumps(
            {
                "status": "PREFILLED_PAUSED_BEFORE_SUBMIT",
                "platform": sys.platform,
                "copilot_sheet": str(copilot_path.resolve().as_posix()),
                "clipboard_preloaded_with_first_pdf_path": first_pdf_copied,
                "approved_jobs_processed": actions,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
