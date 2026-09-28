#!/usr/bin/env python3
"""
inspect_ats_form.py — Token-minimal 3-platform search query generator & ATS form/caution inspector.

Modes:
  1. Generate targeted 3-platform search queries from candidate_profile.json:
     python3 inspect_ats_form.py --generate-queries --profile .job-hunter/candidate_profile.json

  2. Inspect candidate job URLs (strips 95% HTML bloat, extracts JD requirements, form inputs,
     and automated caution/knockout warnings):
     python3 inspect_ats_form.py --urls <url1> <url2> ... [--state-dir .job-hunter]
"""

import argparse
import concurrent.futures
import html
import json
import re
import ssl
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


class JobPageExtractor(HTMLParser):
    """Lightweight stdlib HTML parser that strips scripts/styles and captures text + form fields."""

    SKIP_TAGS = {"script", "style", "svg", "noscript", "path", "head", "footer", "nav"}

    def __init__(self):
        super().__init__()
        self.skip_depth = 0
        self.title = ""
        self.in_title = False
        self.text_chunks = []
        self.form_fields = []
        self.current_label = []
        self.in_label = False
        self.meta_info = {}

    def handle_starttag(self, tag, attrs):
        tag_l = tag.lower()
        attr_dict = {k.lower(): (v or "") for k, v in attrs}

        if tag_l in self.SKIP_TAGS:
            self.skip_depth += 1
            return

        if tag_l == "title":
            self.in_title = True
        elif tag_l == "meta":
            name = attr_dict.get("name", attr_dict.get("property", "")).lower()
            content = attr_dict.get("content", "")
            if name in {"description", "og:title", "og:description", "twitter:title"} and content:
                self.meta_info[name] = content

        if self.skip_depth > 0:
            return

        if tag_l == "label":
            self.in_label = True
            self.current_label = []
        elif tag_l in {"input", "textarea", "select"}:
            input_type = attr_dict.get("type", "text").lower()
            if input_type in {"hidden", "submit", "button", "image", "reset"}:
                return
            name = attr_dict.get("name") or attr_dict.get("id") or ""
            placeholder = attr_dict.get("placeholder") or attr_dict.get("aria-label") or ""
            required = "required" in attr_dict or attr_dict.get("aria-required") == "true"
            self.form_fields.append(
                {
                    "tag": tag_l,
                    "type": input_type,
                    "name": name[:80],
                    "placeholder": placeholder[:100],
                    "required": required,
                    "nearest_label": "",
                }
            )

    def handle_endtag(self, tag):
        tag_l = tag.lower()
        if tag_l in self.SKIP_TAGS and self.skip_depth > 0:
            self.skip_depth -= 1
            return
        if tag_l == "title":
            self.in_title = False
        elif tag_l == "label":
            self.in_label = False
            label_txt = " ".join("".join(self.current_label).split()).strip()
            if label_txt and self.form_fields and not self.form_fields[-1]["nearest_label"]:
                self.form_fields[-1]["nearest_label"] = label_txt[:140]
            elif label_txt:
                self.form_fields.append(
                    {
                        "tag": "label_question",
                        "type": "question",
                        "name": "",
                        "placeholder": "",
                        "required": "*" in label_txt,
                        "nearest_label": label_txt[:140],
                    }
                )

    def handle_data(self, data):
        if self.in_title:
            self.title += data
            return
        if self.skip_depth > 0:
            return
        if self.in_label:
            self.current_label.append(data)
        cleaned = " ".join(data.split())
        if cleaned:
            self.text_chunks.append(cleaned)


def detect_platform(url: str) -> str:
    u = url.lower()
    if "linkedin.com" in u:
        return "LinkedIn"
    if "greenhouse.io" in u:
        return "Direct ATS (Greenhouse)"
    if "lever.co" in u:
        return "Direct ATS (Lever)"
    if "ashbyhq.com" in u:
        return "Direct ATS (Ashby)"
    if "wellfound.com" in u or "angel.co" in u:
        return "Wellfound (AngelList)"
    if "workatastartup.com" in u or "ycombinator.com" in u:
        return "YC Work at a Startup"
    return "Web Job Board"


def analyze_cautions(full_text: str, form_fields: list, url: str) -> dict:
    text_l = full_text.lower()
    cautions = []
    knockout_risks = []
    required_items = []

    # 1. Visa / Work Authorization Knockouts
    if any(
        kw in text_l
        for kw in [
            "without sponsorship",
            "unable to sponsor",
            "not offer visa sponsorship",
            "no visa sponsorship",
            "must be authorized to work",
            "us citizen",
            "u.s. citizen",
            "security clearance",
            "active clearance",
        ]
    ):
        knockout_risks.append(
            "Work Authorization / Sponsorship Restriction: Listing explicitly mentions sponsorship limits, citizenship, or clearance requirements."
        )

    # 2. Strict On-Site / Location Mandates
    if any(
        kw in text_l
        for kw in [
            "5 days a week in office",
            "5 days in-office",
            "fully on-site",
            "in-person only",
            "must reside within",
            "no remote",
        ]
    ):
        knockout_risks.append(
            "Strict On-Site Mandate: Job requires in-office attendance or strict geographic residency."
        )

    # 3. Ghost Job / Talent Pool / Stale Signals
    if any(
        kw in text_l
        for kw in [
            "general interest",
            "future openings",
            "talent community",
            "talent pool",
            "evergreen requisition",
            "30+ days ago",
        ]
    ):
        cautions.append(
            "Possible Evergreen / Ghost Listing: Contains talent-pool or old-posting indicators; verify recent hiring activity on LinkedIn before investing heavy time."
        )

    # 4. Staffing / Recruiting Agency Check
    if any(
        kw in text_l
        for kw in [
            "our client is looking",
            "on behalf of our client",
            "staffing agency",
            "recruiting firm",
            "premier client",
        ]
    ):
        cautions.append(
            "Third-Party Staffing Agency: Listing appears to be posted by an external recruiter rather than the direct hiring company."
        )

    # 5. Extra Application Friction (Video, Take-Home, Cover Letter, Links)
    if any(kw in text_l for kw in ["loom video", "video introduction", "short video", "record a video"]):
        cautions.append("High Friction: Application requests a recorded video / Loom introduction.")
    if any(kw in text_l for kw in ["take-home assignment", "take home project", "coding challenge"]):
        cautions.append("Process Note: Hiring pipeline mentions a take-home assignment or coding test.")

    # Inspect extracted form inputs for required fields
    seen_labels = set()
    for f in form_fields:
        label = (f.get("nearest_label") or f.get("placeholder") or f.get("name") or "").strip()
        if not label or label.lower() in seen_labels:
            continue
        seen_labels.add(label.lower())
        label_l = label.lower()
        if any(
            k in label_l
            for k in [
                "cover letter",
                "linkedin",
                "github",
                "portfolio",
                "website",
                "salary",
                "compensation",
                "sponsorship",
                "authorized",
                "why ",
                "tell us",
            ]
        ):
            required_items.append(label)

    if "linkedin.com" in url.lower():
        cautions.append(
            "LinkedIn Auth Gate: Requires active LinkedIn login session for Easy Apply, or click through to the company's external ATS link."
        )

    return {
        "knockout_risks": knockout_risks,
        "cautions": cautions,
        "custom_questions_detected": required_items[:10],
    }


def inspect_single_url(url: str) -> dict:
    platform = detect_platform(url)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            raw_bytes = resp.read(350_000)  # Cap at 350KB to stay fast & light
            html_str = raw_bytes.decode("utf-8", errors="replace")
            final_url = resp.geturl()
    except Exception as e:
        return {
            "url": url,
            "platform": platform,
            "fetch_status": f"FETCH_LIMITED ({type(e).__name__})",
            "note": "Page blocked direct script fetch or requires browser/search snippet fallback.",
            "caution_analysis": analyze_cautions("", [], url),
        }

    parser = JobPageExtractor()
    try:
        parser.feed(html_str)
    except Exception:
        pass

    full_text = " ".join(parser.text_chunks)
    caution_report = analyze_cautions(full_text, parser.form_fields, final_url)

    # Deduplicate form fields for compact output
    compact_fields = []
    seen = set()
    for f in parser.form_fields:
        key = (f["nearest_label"] or f["placeholder"] or f["name"]).strip()
        if key and key not in seen:
            seen.add(key)
            compact_fields.append(
                {
                    "label": key,
                    "type": f["type"],
                    "required": f["required"],
                }
            )

    return {
        "url": final_url,
        "platform": platform,
        "fetch_status": "OK",
        "page_title": html.unescape(parser.title.strip())[:160],
        "meta_description": html.unescape(parser.meta_info.get("og:description") or parser.meta_info.get("description") or "")[:300],
        "compact_jd_excerpt": full_text[:2200],
        "form_fields_count": len(compact_fields),
        "form_fields_preview": compact_fields[:15],
        "caution_analysis": caution_report,
    }


def generate_queries(profile_path: Path, state_dir: Path) -> dict:
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile not found at {profile_path}. Run parse_resume.py first.")

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    targets = profile.get("search_targets", {})
    roles = targets.get("target_roles", [])[:3] or ["Software Engineer"]
    locs = targets.get("locations", [])[:2] or ["Remote"]
    skills = []
    for cat_skills in (profile.get("skills") or {}).values():
        if isinstance(cat_skills, list):
            skills.extend(cat_skills[:2])
    top_skills = " ".join(skills[:3])

    primary_role = f'"{roles[0]}"'
    role_or_group = " OR ".join(f'"{r}"' for r in roles[:2])
    loc_str = " OR ".join(f'"{l}"' for l in locs)

    seen_path = state_dir / "seen_jobs.json"
    seen_urls = []
    if seen_path.exists():
        try:
            seen_urls = json.loads(seen_path.read_text(encoding="utf-8")).get("seen_urls", [])
        except Exception:
            pass

    return {
        "candidate_roles": roles,
        "locations": locs,
        "previously_seen_count": len(seen_urls),
        "previously_seen_urls_to_skip": seen_urls[-25:],
        "recommended_search_queries": {
            "platform_1_linkedin": f"site:linkedin.com/jobs/view ({role_or_group}) ({loc_str}) {top_skills}".strip(),
            "platform_2_direct_ats": (
                f"(site:boards.greenhouse.io OR site:job-boards.greenhouse.io OR site:jobs.lever.co OR site:jobs.ashbyhq.com) "
                f"({role_or_group}) ({loc_str}) {top_skills}"
            ).strip(),
            "platform_3_wellfound_yc": (
                f"(site:wellfound.com/jobs OR site:workatastartup.com/jobs) "
                f"({ primary_role }) ({loc_str})"
            ).strip(),
        },
    }


def main():
    ap = argparse.ArgumentParser(description="Generate 3-platform queries or inspect ATS job URLs.")
    ap.add_argument("--generate-queries", action="store_true", help="Generate search queries from profile")
    ap.add_argument("--profile", default=".job-hunter/candidate_profile.json", help="Path to candidate_profile.json")
    ap.add_argument("--urls", nargs="+", help="List of job URLs to inspect in parallel")
    ap.add_argument("--state-dir", default=".job-hunter", help="Path to state directory")
    ap.add_argument("--record-seen", nargs="+", help="Record selected 5 job URLs in seen_jobs.json")
    args = ap.parse_args()

    state_dir = Path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)

    if args.record_seen:
        seen_path = state_dir / "seen_jobs.json"
        existing = []
        if seen_path.exists():
            try:
                existing = json.loads(seen_path.read_text(encoding="utf-8")).get("seen_urls", [])
            except Exception:
                pass
        merged = list(dict.fromkeys(existing + args.record_seen))
        seen_path.write_text(json.dumps({"seen_urls": merged}, indent=2), encoding="utf-8")
        print(json.dumps({"status": "RECORDED", "total_seen": len(merged)}, indent=2))
        return

    if args.generate_queries:
        out = generate_queries(Path(args.profile), state_dir)
        print(json.dumps(out, indent=2))
        return

    if args.urls:
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            future_to_url = {pool.submit(inspect_single_url, u): u for u in args.urls}
            for fut in concurrent.futures.as_completed(future_to_url):
                results.append(fut.result())
        # Preserve input URL order
        url_order = {u: i for i, u in enumerate(args.urls)}
        results.sort(key=lambda r: url_order.get(r.get("url"), 999))
        print(json.dumps({"inspected_jobs": results}, indent=2))
        return

    ap.print_help()


if __name__ == "__main__":
    main()
