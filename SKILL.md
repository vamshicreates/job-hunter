---
name: job-hunter
description: Cross-platform (Windows, macOS, Linux) token-minimal job hunting, standardized ATS resume tailoring, application caution recon, and approval-gated browser pre-fill skill. Activate whenever the user provides a resume in the local folder or asks to find matching jobs, hunt for job openings, tailor their resume for top roles, analyze job application risks/cautions, or apply to jobs. Always finds strictly 5 high-fit job profiles per run across LinkedIn, Direct ATS Boards (Greenhouse/Lever/Ashby), and Wellfound/YC.
---

# Job Hunter (`job-hunter`)

A cross-platform (**Windows, macOS, and Linux**), token-minimal, script-driven workflow that reads a user's local resume once, finds **strictly 5 high-fit, active job profiles** across the top 3 high-response platforms, generates **5 standardized ATS-friendly resumes (PDF + Markdown + HTML)** via differential JSON patching, produces an **Application Caution & Knockout Brief**, and pre-fills approved applications in the browser (pausing at the final **Submit** button).

---

## Cross-Platform Execution Notes (Windows & macOS/Linux)

- **Python Command:**
  - **Windows (PowerShell / CMD):** Use `python` (or `py -3` if `python` is not aliased).
  - **macOS / Linux:** Use `python3`.
- **Zero-Dependency Resume Extraction (`parse_resume.py`):**
  - `.docx`: Parsed via pure-Python `zipfile` + `xml.etree.ElementTree` on all OSes.
  - `.pdf`: Uses `pypdf`/`fitz`/`pdfplumber` if installed $\rightarrow$ macOS Quartz `PDFKit` $\rightarrow$ `pdftotext` $\rightarrow$ built-in pure-Python `zlib` PDF stream parser on Windows/Linux.
  - `.rtf` / `.doc`: Uses PowerShell `System.Windows.Forms.RichTextBox` on Windows, `textutil` on macOS, or pure-Python RTF stripping.
- **Zero-Dependency Headless PDF Rendering (`build_resume.py`):**
  - Automatically detects **Google Chrome**, **Microsoft Edge (`msedge.exe` — pre-installed on all Windows 10/11 PCs)**, or **Brave** via standard paths and Windows Registry (`winreg`), and converts `file:///C:/...` URIs cleanly via `.as_uri()`.
- **Approval-Gated Pre-Fill (`apply_helper.py`):**
  - **Windows:** Highlights the tailored PDF in File Explorer (`explorer.exe /select,...`), pre-loads the native Windows PDF path into the clipboard via `clip.exe` (so pressing `Ctrl+V` inside the browser's File Upload dialog attaches the resume in 1 second), opens the application tabs, and launches the local **Application Copilot** with a drag-to-bookmark-bar **⚡ Auto-Fill & Pause Before Submit** button.
  - **macOS:** Reveals the tailored PDF in Finder (`open -R`), copies path via `pbcopy`, injects auto-fill JS into Chrome via AppleScript, and launches the local **Application Copilot**.

---

## Core Guardrails (Non-Negotiable)

1. **Strictly 5 Job Profiles per Run:** Never dump 15+ vague links or stop at 2. Every run must shortlist and process **exactly 5** verified, active job profiles (skipping URLs already recorded in `.job-hunter/seen_jobs.json`).
2. **Experience (YoE) Cutoff & Seniority Precision:** Filter and match job roles precisely to the candidate's verified Years of Experience (YoE). If the candidate has 4 years, shortlist roles requiring 3–5, 3–6, 4–7, or 4+ years; strictly reject over-senior positions (8–12+ or 10+ year lead/architect listings) unless requested.
3. **Strict Location Enforcement:** All shortlisted roles must strictly match the candidate's target location (e.g. Hyderabad, Bengaluru, Remote) and must be verified against the job description body.
4. **Mandatory Browser DOM Verification:** Every candidate job URL must be verified via `inspect_ats_form.py --verify-browser --urls <urls>` in a headless browser (Google Chrome or Microsoft Edge) to verify that the requisition is active (HTTP 200), that the apply/interest button is physically present in the DOM (`id="topbar-apply"`, `class="apply-button"`, `class="js-oneclick"`), and that the submission flow is open and submittable.
5. **Clean PDF Isolation:** Resumes must always have their ATS `.pdf` files automatically saved into a dedicated `PDFs/` subfolder (e.g., `<outdir>/PDFs/`), keeping them cleanly isolated from markdown and HTML for instant 1-click attachment.
6. **Direct 1-Click Copyable Links in Chat:** Always present verified live job links one by one in clean, copyable code blocks in chat alongside clickable paths to the corresponding tailored PDF.
7. **Minimum Tokens, Maximum Output:**
   - **Never** re-read a raw PDF/DOCX if `.job-hunter/candidate_profile.json` returns `CACHE_HIT`.
   - **Never** open 10 full browser tabs or dump raw HTML into LLM context—always use `inspect_ats_form.py` to strip HTML and extract only JD requirements, `<form>` inputs, and knockout flags.
   - **Never** write out 5 full resumes in chat or rewrite unchanged sections—write only a compact `patches.json` containing the job-specific deltas and run `build_resume.py` to render all 5 PDFs/MDs in zero tokens.
8. **Truthfulness in Resume Tailoring:** Re-order skills, sharpen summaries, and align bullet terminology with the target job's ATS keywords, but **never fabricate** companies, degrees, or metrics the candidate does not have.
9. **Explicit Approval Gate Before Applying:** Never run `apply_helper.py` or interact with an application form until the user explicitly approves specific job numbers (`#1`–`#5`). Even after approval, **pause at the final Submit button** for the user's manual click.

---

## The 5-Stage Workflow

### Stage 1: Resume Ingestion & Profile Cache (~300 tokens)

Run `parse_resume.py` on the local folder or user-specified resume path (use `python` on Windows, `python3` on macOS/Linux):

```bash
python3 .agents/skills/job-hunter/scripts/parse_resume.py . --state-dir .job-hunter
```

- **If `status == "CACHE_HIT"`**: Do **not** read the raw resume file again. Proceed immediately to Stage 2 using `.job-hunter/candidate_profile.json`.
- **If `status == "CACHE_MISS_EXTRACTED"`**: Read the extracted text from the script output and write `.job-hunter/candidate_profile.json` using this exact schema:

```json
{
  "source_file": "path/to/resume.pdf",
  "source_hash": "<sha256_from_parse_resume>",
  "search_targets": {
    "target_roles": ["Primary Role Title", "Secondary Role Title", "Adjacent Role Title"],
    "seniority": "Junior | Mid-Level | Senior | Staff | Lead",
    "years_of_experience": 4,
    "locations": ["Remote", "City/Country"],
    "core_keywords": ["Skill1", "Skill2", "Skill3", "Skill4"]
  },
  "basics": {
    "name": "Full Name",
    "headline": "Default Role Headline",
    "email": "email@example.com",
    "phone": "+1-555-000-0000",
    "location": "City, Country",
    "links": [
      {"label": "LinkedIn", "url": "https://linkedin.com/in/..."},
      {"label": "GitHub", "url": "https://github.com/..."},
      {"label": "Portfolio", "url": "https://..."}
    ]
  },
  "summary": "2-3 sentence baseline executive summary.",
  "skills": {
    "Languages & Core": ["..."],
    "Frameworks & Libraries": ["..."],
    "Cloud, Data & Tools": ["..."]
  },
  "experience": [
    {
      "id": "exp_1",
      "company": "Company Name",
      "role": "Job Title",
      "location": "Location",
      "dates": "MMM YYYY – Present",
      "bullets": [
        "Action verb + quantified impact + specific tools/methods..."
      ]
    }
  ],
  "projects": [
    {
      "name": "Project Name",
      "tech": "Tech Stack",
      "dates": "YYYY",
      "bullets": ["Impact-focused description..."]
    }
  ],
  "education": [
    {
      "institution": "University Name",
      "degree": "Degree & Major",
      "dates": "YYYY – YYYY",
      "location": "Location",
      "details": "GPA / Honors / Relevant Coursework"
    }
  ],
  "certifications": []
}
```

---

### Stage 2: 3-Platform Discovery & Top 5 Selection (~1,200 tokens)

1. Generate the targeted search queries across the **3 high-response platforms**:
   ```bash
   python3 .agents/skills/job-hunter/scripts/inspect_ats_form.py --generate-queries --profile .job-hunter/candidate_profile.json
   ```
2. Execute `search_web` in parallel across the 3 platforms (or if running in an agent environment without a built-in `search_web` tool, run `python3 .agents/skills/job-hunter/scripts/inspect_ats_form.py --search --profile .job-hunter/candidate_profile.json`):
   - **Platform 1 — LinkedIn Jobs:** Active role listings (`linkedin.com/jobs/view/...`)
   - **Platform 2 — Direct ATS Boards (Highest Reliability):** `boards.greenhouse.io`, `job-boards.greenhouse.io`, `jobs.lever.co`, `jobs.ashbyhq.com`
   - **Platform 3 — Wellfound / YC Work at a Startup (Highest Startup Response):** `wellfound.com/jobs`, `workatastartup.com/jobs`
3. Collect 7–10 promising direct job posting URLs matching candidate's location and experience (YoE) bracket, and inspect them:
   ```bash
   python3 .agents/skills/job-hunter/scripts/inspect_ats_form.py --urls "<url1>" "<url2>" "<url3>" "<url4>" "<url5>"
   ```
4. **Mandatory Browser DOM Verification:** Verify in headless Chrome/Edge that each job link is live (HTTP 200), that the apply/interest button is physically present and clickable, and that the application flow is submittable:
   ```bash
   python3 .agents/skills/job-hunter/scripts/inspect_ats_form.py --verify-browser --urls "<url1>" "<url2>" "<url3>" "<url4>" "<url5>"
   ```
5. Select **strictly the Top 5** best-fitting, currently active jobs and record them so future runs never repeat them:
   ```bash
   python3 .agents/skills/job-hunter/scripts/inspect_ats_form.py --record-seen "<url1>" "<url2>" "<url3>" "<url4>" "<url5>"
   ```

---

### Stage 3: Differential Resume Tailoring (0-Token PDF Compilation)

Create a run folder `.job-hunter/runs/<YYYY-MM-DD_HHMM>/` and write `patches.json` containing **5 compact differential patch objects** (one for each of the 5 jobs):

```json
[
  {
    "job_index": 1,
    "company": "Company Name",
    "role_title": "Exact Target Job Title",
    "platform": "Direct ATS (Greenhouse) | LinkedIn | Wellfound",
    "job_url": "https://...",
    "match_score": "95%",
    "target_headline": "Tailored Role Headline matching the JD",
    "tailored_summary": "Sharp 2-sentence summary mirroring the job's core stack, domain, and outcomes.",
    "skills_override": {
      "Core Stack (Matched to JD)": ["Top JD Skill 1", "Top JD Skill 2", "..."],
      "Systems & Tools": ["..."],
      "Domain & Practices": ["..."]
    },
    "experience_bullet_overrides": {
      "exp_1": [
        "Re-framed top bullet 1 highlighting exact ATS keywords from the JD + original verified metric.",
        "Re-framed top bullet 2 emphasizing relevant architecture/domain experience."
      ]
    },
    "cover_note": "Concise 3-4 sentence high-signal note answering 'Why this role & company?' using candidate's real metrics.",
    "drafted_answers": {
      "Custom Form Question 1 (if any)": "Ready-to-paste answer"
    }
  }
]
```

Compile all 5 standardized resumes (Markdown `.md` + HTML `.html` + Harvard/Jake's single-column ATS `.pdf`):

```bash
python3 .agents/skills/job-hunter/scripts/build_resume.py --profile .job-hunter/candidate_profile.json --patches .job-hunter/runs/<run_id>/patches.json --outdir .job-hunter/runs/<run_id>/resumes
```

*(Note: `build_resume.py` automatically generates a dedicated `PDFs/` subfolder at `.job-hunter/runs/<run_id>/resumes/PDFs/` containing strictly the 5 `.pdf` files, keeping them isolated from markdown and HTML).*

---

### Stage 4: Present the 5-Job Action & Caution Brief

Present a clean, structured summary to the user with clickable file links (`file:///...` using forward slashes on both Windows and macOS) to all 5 generated PDF/MD resumes:

1. **Overview Table of the 5 Selected Jobs:**
   - `#`, **Role & Company**, **Platform**, **Match %**, **Tailored Resume Links (`[PDF](file:///...)` | `[MD](file:///...)`)**, and **Job Link**.
2. **Per-Job Breakdown (1 to 5):**
   - **Why You Fit:** 1–2 sentences linking candidate's real metrics to the JD.
   - **Resume Customizations Made:** Which keywords, skills, and bullets were prioritized.
   - **What to Be Cautious About (Application Recon):**
     - **Knockout Risks:** Visa/sponsorship restrictions, strict in-office/residency mandates, security clearance, or hard YoE filters.
     - **Red Flags / Process Notes:** Repost/stale listing warnings, staffing agency intermediaries, required video/Loom intros, or take-home test warnings.
     - **Required Custom Form Fields & Pre-Drafted Answers:** Any specific screening questions found on the form along with the ready-to-paste answers.
3. **Direct 1-Click Copyable Job URLs:**
   Output the 5 verified live job URLs one by one in clean, copyable code blocks (e.g., ````text\nhttps://...\n````) alongside their corresponding tailored PDF link, so the user can easily copy and paste them into their browser with a single click.
4. **Approval Gate Prompt:**
   Ask the user: *"Which of these 5 jobs (#1–#5) would you like me to open and pre-fill for you?"*

---

### Stage 5: Approval-Gated Pre-Fill (Pause Before Submit)

Once the user replies approving specific job numbers (e.g., *"Apply to 1, 3, and 4"*), run:

```bash
python3 .agents/skills/job-hunter/scripts/apply_helper.py --profile .job-hunter/candidate_profile.json --patches .job-hunter/runs/<run_id>/patches.json --resumes-dir .job-hunter/runs/<run_id>/resumes --approve 1 3 4
```

This script:
- Opens the approved application URLs in the browser,
- Reveals the tailored ATS `.pdf` files in **Windows File Explorer (`explorer.exe /select`)** or **macOS Finder (`open -R`)**, and copies the PDF file path to the clipboard (`clip.exe` / `pbcopy`) for instant `Ctrl+V` attachment,
- Pre-fills candidate fields and highlights the **Submit** button in green **without clicking it**,
- Opens the local **Application Copilot** (`application_copilot.html`) with 1-click copy boxes and a drag-to-bookmarks-bar **⚡ Auto-Fill** button.
