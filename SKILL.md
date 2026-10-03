---
name: job-hunter
description: Cross-platform (Windows, macOS, Linux) token-minimal job hunting, standardized ATS resume tailoring, application caution recon, and approval-gated browser pre-fill skill. Activate whenever the user provides a resume in the local folder, provides specific job titles/professions to search for (e.g., "Voice over artist", "Podcaster", "Content Manager in Hyderabad"), asks to find matching jobs, hunt for job openings, tailor their resume for top roles, analyze application risks/cautions, or apply to jobs. Always finds strictly 5 high-fit job profiles per run across LinkedIn, Direct ATS Boards (Greenhouse/Lever/Ashby), and Wellfound/YC.
---

# Job Hunter (`job-hunter`)

A cross-platform (**Windows, macOS, and Linux**), token-minimal, script-driven workflow that searches across the top 3 high-response platforms using either **local candidate resumes** or **explicit user-provided job titles/professions**, finds **strictly 5 high-fit, active job profiles**, generates **5 standardized ATS-friendly resumes (PDF + Markdown + HTML)** via differential JSON patching, produces an **Application Caution & Knockout Brief**, and pre-fills approved applications in the browser (pausing at the final **Submit** button).

---

## Supported Search Modes

1. **Explicit Title / Profession Mode (User-Specified Roles):**
   - Whenever the user gives specific job titles, professions, or query pivots (e.g. *"Voice over artist"*, *"Podcaster"*, *"Find Content Lead or Social Media Manager roles in Hyderabad"*, *"Senior DevOps Engineer"*), the skill immediately prioritizes and hunts for those exact job titles across the top 3 platforms.
   - If a candidate profile already exists or is provided, the skill automatically updates `search_targets.target_roles` and tailors the 5 ATS resumes specifically to those requested titles.
   - If no resume is provided, the skill still performs the full 3-platform discovery, headless browser DOM verification, and outputs the top 5 verified live job requisitions.
2. **Resume-Driven Mode:**
   - Reads the local candidate resume once, caches the structured profile in `.job-hunter/candidate_profile.json`, extracts target titles and YoE, and finds matching opportunities.
3. **Hybrid Re-Targeting Mode:**
   - The user can iteratively pivot target titles (e.g., *"Now find Voice Over Artist / Podcaster roles for this profile"*) without re-parsing raw files.

---

## Cross-Platform Execution Notes (Windows & macOS/Linux)

- **Python Command:**
  - **Windows (PowerShell / CMD):** Use `python` (or `py -3` if `python` is not aliased).
  - **macOS / Linux:** Use `python3`.
- **Zero-Dependency Resume Extraction (`parse_resume.py`):**
  - `.docx`: Parsed via pure-Python `zipfile` + `xml.etree.ElementTree` on all OSes.
  - `.pdf`: Uses `pypdf`/`fitz`/`pdfplumber` if installed $\rightarrow$ macOS Quartz `PDFKit` $\rightarrow$ `pdftotext` $\rightarrow$ built-in pure-Python `zlib` PDF stream parser on Windows/Linux.
  - `.rtf` / `.doc`: Uses PowerShell `System.Windows.Forms.RichTextBox` on Windows, `textutil` on macOS, or pure-Python RTF stripping.
  - Images (`.png`, `.jpg`): Extracted via vision or transcribed directly into `.job-hunter/candidate_profile.json`.
- **Zero-Dependency Headless PDF Rendering (`build_resume.py`):**
  - Automatically detects **Google Chrome**, **Microsoft Edge (`msedge.exe` — pre-installed on all Windows 10/11 PCs)**, or **Brave** via standard paths and Windows Registry (`winreg`), and converts `file:///C:/...` URIs cleanly via `.as_uri()`.
- **Approval-Gated Pre-Fill (`apply_helper.py`):**
  - **Windows:** Highlights the tailored PDF in File Explorer (`explorer.exe /select,...`), pre-loads the native Windows PDF path into the clipboard via `clip.exe` (so pressing `Ctrl+V` inside the browser's File Upload dialog attaches the resume in 1 second), opens the application tabs, and launches the local **Application Copilot** with a drag-to-bookmark-bar **⚡ Auto-Fill & Pause Before Submit** button.
  - **macOS:** Reveals the tailored PDF in Finder (`open -R`), copies path via `pbcopy`, injects auto-fill JS into Chrome via AppleScript, and launches the local **Application Copilot**.

---

## Core Guardrails (Non-Negotiable)

1. **Strictly 5 Job Profiles per Run:** Never dump 15+ vague links or stop at 2. Every run must shortlist and process **exactly 5** verified, active job profiles (skipping URLs already recorded in `.job-hunter/seen_jobs.json`).
2. **Explicit Title & Seniority Precision:** When the user supplies explicit job titles (e.g., "Voice Over Artist", "Podcaster"), match those exact titles. Filter experience (YoE) precisely to the candidate's verified background.
3. **Strict Location Enforcement:** All shortlisted roles must strictly match the candidate's target location (e.g. Hyderabad, Bengaluru, Remote, Indian companies only) and must be verified against the job description body.
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

### Stage 1: Ingestion & Target Role Formulation (~300 tokens)

- **If a local resume is provided:** Run `parse_resume.py`:
  ```bash
  python3 .agents/skills/job-hunter/scripts/parse_resume.py . --state-dir .job-hunter
  ```
- **If user provides explicit target titles/professions:** (e.g. *"Voice over artist, Podcaster"*, *"Frontend Developer in Hyderabad"*):
  Update `.job-hunter/candidate_profile.json` with the new target roles:
  ```json
  "search_targets": {
    "target_roles": ["Voice Over Artist", "Podcaster", "Audio Show Host"],
    "locations": ["Hyderabad", "Remote"],
    "seniority": "Mid-to-Senior",
    "years_of_experience": 5
  }
  ```

---

### Stage 2: 3-Platform Discovery & Top 5 Selection (~1,200 tokens)

1. Generate targeted search queries across the **3 high-response platforms** (supporting explicit `--roles`, `--locations`, and `--keywords` overrides):
   ```bash
   python3 .agents/skills/job-hunter/scripts/inspect_ats_form.py --generate-queries --roles "Voice Over Artist" "Podcaster" --locations "Hyderabad" "Remote"
   ```
2. Execute `search_web` in parallel across the 3 platforms (or run `python3 .agents/skills/job-hunter/scripts/inspect_ats_form.py --search --roles "..."`):
   - **Platform 1 — LinkedIn Jobs:** Active role listings (`linkedin.com/jobs/view/...`)
   - **Platform 2 — Direct ATS Boards (Highest Reliability):** `boards.greenhouse.io`, `job-boards.greenhouse.io`, `jobs.lever.co`, `jobs.ashbyhq.com`
   - **Platform 3 — Wellfound / YC / Direct Indian Audio & Media Portals:** `wellfound.com/jobs`, `kalakaar.kukufm.com`, `creator.pocketfm.com`
3. Collect promising direct job posting URLs matching candidate's location, titles, and experience bracket, and inspect them:
   ```bash
   python3 .agents/skills/job-hunter/scripts/inspect_ats_form.py --urls "<url1>" "<url2>" "<url3>" "<url4>" "<url5>"
   ```
4. **Mandatory Browser DOM Verification:** Verify in headless Chrome/Edge that each job link is live (HTTP 200), that the apply/interest button is physically present and clickable, and that the application flow is submittable:
   ```bash
   python3 .agents/skills/job-hunter/scripts/inspect_ats_form.py --verify-browser --urls "<url1>" "<url2>" "<url3>" "<url4>" "<url5>"
   ```
5. Select **strictly the Top 5** best-fitting, currently active jobs and record them:
   ```bash
   python3 .agents/skills/job-hunter/scripts/inspect_ats_form.py --record-seen "<url1>" "<url2>" "<url3>" "<url4>" "<url5>"
   ```

---

### Stage 3: Differential Resume Tailoring (0-Token PDF Compilation)

Create a run folder `.job-hunter/runs/<YYYY-MM-DD_HHMM>/` and write `patches.json` containing **5 compact differential patch objects** tailored to each job:

```json
[
  {
    "job_index": 1,
    "company": "Company Name",
    "role_title": "Target Job Title",
    "platform": "Direct ATS (Greenhouse) | LinkedIn | Platform Portal",
    "job_url": "https://...",
    "match_score": "98%",
    "target_headline": "Tailored Headline matching the Target Role",
    "tailored_summary": "Sharp 2-sentence summary mirroring the JD's requirements and candidate's verified strengths.",
    "skills_override": {
      "Domain & Execution": ["Skill 1", "Skill 2"],
      "Tools & Platforms": ["..."]
    },
    "experience_bullet_overrides": {
      "exp_1": [
        "Re-framed bullet emphasizing exact keywords from the role + original verified metric."
      ]
    },
    "cover_note": "Concise 3-4 sentence pitch answering 'Why this role & company?' using candidate's real metrics.",
    "drafted_answers": {
      "Custom Question": "Ready-to-paste answer"
    }
  }
]
```

Compile all 5 standardized resumes (Markdown `.md` + HTML `.html` + Single-column ATS `.pdf`):

```bash
python3 .agents/skills/job-hunter/scripts/build_resume.py --profile .job-hunter/candidate_profile.json --patches .job-hunter/runs/<run_id>/patches.json --outdir .job-hunter/runs/<run_id>/resumes
```

*(Note: `build_resume.py` automatically generates a dedicated `PDFs/` subfolder at `.job-hunter/runs/<run_id>/resumes/PDFs/` containing strictly the 5 `.pdf` files, keeping them isolated from markdown and HTML).*

---

### Stage 4: Present the 5-Job Action & Caution Brief

Present a clean, structured summary with clickable file links (`file:///...` using forward slashes):

1. **Overview Table of the 5 Selected Jobs:**
   - `#`, **Role & Company**, **Platform**, **Match %**, **Tailored Resume Links (`[PDF](file:///...)` | `[MD](file:///...)`)**, and **Application Link**.
2. **Per-Job Breakdown (1 to 5):**
   - **Why You Fit:** 1–2 sentences linking candidate's real metrics to the JD.
   - **Resume Customizations Made:** Which keywords, skills, and bullets were prioritized.
   - **What to Be Cautious About (Application Recon):**
     - **Knockout Risks:** Visa/sponsorship, strict in-office requirements, hard YoE cutoffs.
     - **Process Notes:** Platform-specific onboarding steps, portfolio links, take-home tests.
     - **Required Custom Form Fields & Pre-Drafted Answers:** Specific questions on the application with ready-to-paste answers.
3. **Direct 1-Click Copyable Job URLs:**
   Output the 5 verified live job URLs one by one in clean, copyable code blocks alongside their corresponding tailored PDF link.
4. **Approval Gate Prompt:**
   Ask the user: *"Which of these 5 jobs (#1–#5) would you like me to open and pre-fill for you?"*

---

### Stage 5: Approval-Gated Pre-Fill (Pause Before Submit)

Once the user approves specific job numbers (e.g., *"Apply to 1, 3, and 4"*), run:

```bash
python3 .agents/skills/job-hunter/scripts/apply_helper.py --profile .job-hunter/candidate_profile.json --patches .job-hunter/runs/<run_id>/patches.json --resumes-dir .job-hunter/runs/<run_id>/resumes --approve 1 3 4
```

This script:
- Opens the approved application URLs in the browser,
- Reveals the tailored ATS `.pdf` files in **Windows File Explorer (`explorer.exe /select`)** or **macOS Finder (`open -R`)**, and copies the PDF file path to the clipboard (`clip.exe` / `pbcopy`) for instant `Ctrl+V` attachment,
- Pre-fills candidate fields and highlights the **Submit** button in green **without clicking it**,
- Opens the local **Application Copilot** (`application_copilot.html`) with 1-click copy boxes and a drag-to-bookmarks-bar **⚡ Auto-Fill** button.
