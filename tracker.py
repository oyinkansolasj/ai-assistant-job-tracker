# tracker.py - Holds the app's live state while it is running.

import json
import os
import re
from datetime import date, timedelta
from validation import (
    VALID_STATUSES,
    validate_company_name,
    validate_date_applied,
    validate_status,
)

# Follow-up reminders: how many days after the last contact to follow up,
# for each "open" status. Rejected / withdrawn applications get no reminders.
FOLLOW_UP_DAYS_BY_STATUS = {"applied": 7, "interviewing": 5, "offer": 3}
MAX_FOLLOW_UPS = 3      # after this many follow-ups with no reply, suggest moving on
UPCOMING_DAYS = 3       # also show reminders coming up in the next few days

# session_state keeps track of everything happening in the current session.

session_state = {
    # What the user is searching for
    "search_goal": {
        "target_role": "",      # e.g. "Data Analyst"
        "industry": "",         # e.g. "Fintech"
        "company_size": "",     # "small", "medium", or "large"
        "work_mode": "",        # "on-site", "hybrid", or "remote"
        "availability": "",     # e.g. "Mon-Fri, 9am-5pm"
    },

    # The date the user wants to hit their goal by ("YYYY-MM-DD")
    "deadline": None,

    # Application goals and progress
    "application_counts": {
        "daily_goal": 0,        # e.g. 10 a day
        "weekly_goal": 0,       # e.g. 20 a week
        "today": 0,             # applications sent today
        "this_week": 0,         # applications sent this week
        "total": 0,             # all applications ever sent
    },

    # Every job the user is tracking. Each one is an application made by create_application() below.
    "pipeline": [],

    # The text of the user's CV (loaded from data/cv.txt), used for job matching
    "cv_text": "",

    # The most recent thing the AI assistant did or suggested
    "last_action": {
        "type": None,           # "add", "update", or "delete"
        "details": None,        # e.g. "Moved Acme Ltd to interview"
        "approved": None,       # True if the user said yes, False if no
    },
}

# Application data model An application is a dictionary with these 
# five fields: company_name, role_title, date_applied, status, and notes.

def create_application(company_name, role_title, status="applied", date_applied=None, notes="",
                       job_description="", match=None):
    """Build a new application dictionary, checking the input first, job_description and match are optional: they hold the pasted job advert
    and the CV match result (see match_cv_to_job below).
    last_contact and follow_up_count are used for follow-up reminders."""
    applied_on = validate_date_applied(date_applied) if date_applied else date.today().isoformat()
    return {
        "company_name": validate_company_name(company_name),
        "role_title": role_title.strip(),
        "date_applied": applied_on,
        "status": validate_status(status),
        "notes": notes.strip(),
        "job_description": job_description.strip(),
        "match": match,
        "last_contact": applied_on,     # last time you or the company got in touch
        "follow_up_count": 0,           # how many times you've followed up
    }


# Helper functions

def recalculate_counts():
    """Work out today / this week / total from the applications in the pipeline."""
    counts = session_state["application_counts"]
    today = date.today()
    counts["today"] = counts["this_week"] = 0
    counts["total"] = len(session_state["pipeline"])

    for application in session_state["pipeline"]:
        applied = date.fromisoformat(application["date_applied"])
        if applied == today:
            counts["today"] += 1
        if applied.isocalendar()[:2] == today.isocalendar()[:2]:   # same year and week
            counts["this_week"] += 1


def log_application(company_name, role_title, status="applied", date_applied=None, notes="",
                    job_description="", match=None):
    """Create a new application, add it to the pipeline, and update the counts."""
    application = create_application(company_name, role_title, status, date_applied, notes,
                                     job_description, match)
    session_state["pipeline"].append(application)
    recalculate_counts()

    session_state["last_action"] = {
        "type": "add",
        "details": f"Logged {application['role_title']} at {application['company_name']}",
        "approved": True,
    }
    return application


def update_status(index, new_status):
    """Change the status of the application at position `index` in the pipeline."""
    pipeline = session_state["pipeline"]
    if index < 0 or index >= len(pipeline):
        raise ValueError(f"There is no application number {index + 1}.")

    application = pipeline[index]
    old_status = application["status"]
    apply_status_change(application, new_status)

    session_state["last_action"] = {
        "type": "update",
        "details": f"Moved {application['company_name']} from {old_status} to {application['status']}",
        "approved": True,
    }
    return application


def apply_status_change(application, new_status):
    """Change an application's status. A real change counts as contact from
    the company, so the follow-up clock restarts from today."""
    new_status = validate_status(new_status)
    if new_status != application["status"]:
        application["status"] = new_status
        application["last_contact"] = date.today().isoformat()
        application["follow_up_count"] = 0
    return application


def delete_application(index):
    """Remove the application at position `index` from the pipeline."""
    pipeline = session_state["pipeline"]
    if index < 0 or index >= len(pipeline):
        raise ValueError(f"There is no application number {index + 1}.")

    application = pipeline.pop(index)
    recalculate_counts()

    session_state["last_action"] = {
        "type": "delete",
        "details": f"Deleted {application['role_title']} at {application['company_name']}",
        "approved": True,
    }
    return application


def calculate_follow_up_date(from_date, days):
    """Return the date `days` after `from_date` (both YYYY-MM-DD)."""
    return (date.fromisoformat(from_date) + timedelta(days=days)).isoformat()


# Follow-up reminders

def is_open(application):
    """An application is open if it's still waiting on something."""
    return application["status"] in FOLLOW_UP_DAYS_BY_STATUS


def next_follow_up_date(application):
    """When to follow up next (YYYY-MM-DD), or None if the application is closed."""
    if not is_open(application):
        return None
    last_contact = application.get("last_contact") or application["date_applied"]
    return calculate_follow_up_date(last_contact, FOLLOW_UP_DAYS_BY_STATUS[application["status"]])


def get_follow_up_reminders():
    """Find open applications that need a follow-up.
    Returns {"due": [...], "upcoming": [...]}. Each item is a dictionary with
    index, application, follow_up_date, and days (overdue for due, until for upcoming)."""
    today = date.today()
    due, upcoming = [], []
    for index, application in enumerate(session_state["pipeline"]):
        follow_up = next_follow_up_date(application)
        if follow_up is None:
            continue
        days = (today - date.fromisoformat(follow_up)).days
        item = {"index": index, "application": application, "follow_up_date": follow_up}
        if days >= 0:
            due.append({**item, "days": days})                  # days overdue (0 = today)
        elif -days <= UPCOMING_DAYS:
            upcoming.append({**item, "days": -days})            # days until due

    due.sort(key=lambda item: -item["days"])            # most overdue first
    upcoming.sort(key=lambda item: item["days"])        # soonest first
    return {"due": due, "upcoming": upcoming}


def apply_follow_up(application):
    """Record that you followed up today, so the next reminder moves forward."""
    application["last_contact"] = date.today().isoformat()
    application["follow_up_count"] = application.get("follow_up_count", 0) + 1
    return application


def mark_followed_up(index):
    """Mark the application at `index` as followed up today."""
    pipeline = session_state["pipeline"]
    if index < 0 or index >= len(pipeline):
        raise ValueError(f"There is no application number {index + 1}.")
    application = apply_follow_up(pipeline[index])
    session_state["last_action"] = {
        "type": "update",
        "details": f"Followed up with {application['company_name']} "
                   f"(follow-up #{application['follow_up_count']})",
        "approved": True,
    }
    return application


def summarize_pipeline():
    """Return a summary of the pipeline: totals, counts by status, goals, and follow-ups due."""
    pipeline = session_state["pipeline"]

    by_status = {status: 0 for status in VALID_STATUSES}
    for application in pipeline:
        by_status[application["status"]] += 1

    follow_ups_due = get_follow_up_reminders()["due"]

    return {
        "total": len(pipeline),
        "by_status": by_status,
        "counts": session_state["application_counts"],
        "deadline": session_state["deadline"],
        "follow_ups_due": follow_ups_due,
    }


# AI: draft a follow-up email with the Gemini API
# Setup (one time):
#   pip install google-genai in your terminal 
#   export GEMINI_API_KEY="your-key"     (get one at https://aistudio.google.com/apikey)
# Optional: export GEMINI_MODEL="..." to try a specific Gemini model first.

# Models to try, in order. If one is busy or slow, the next one is used.
GEMINI_MODELS = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.1-flash-lite"]
if os.environ.get("GEMINI_MODEL"):
    GEMINI_MODELS.insert(0, os.environ["GEMINI_MODEL"])

GEMINI_TIMEOUT_SECONDS = 30   # give up on a model after this long

# What the email should do for each status
EMAIL_PURPOSE = {
    "applied": "politely check in on the application and restate interest",
    "interviewing": "thank them for the interview and ask about next steps",
    "offer": "thank them for the offer and ask any open questions or confirm next steps",
    "rejected": "thank them for their time and ask for brief feedback",
    "withdrawn": "politely confirm the withdrawal and keep the door open for the future",
}


def build_follow_up_prompt(application):
    """Write the instructions we send to Gemini for one application."""
    days_since = (date.today() - date.fromisoformat(application["date_applied"])).days
    goal = session_state["search_goal"]
    return f"""Draft a short, professional follow-up email for a job application.

Company: {application['company_name']}
Role: {application['role_title']}
Date applied: {application['date_applied']} ({days_since} days ago)
Current status: {application['status']}
Notes: {application['notes'] or 'none'}
Candidate's target role: {goal['target_role'] or 'not given'}

The email should {EMAIL_PURPOSE[application['status']]}.
Rules:
- Start with a "Subject:" line, then the email body.
- Under 150 words, warm but professional, no exaggeration.
- Only use the facts above. Do not invent names, dates, or achievements.
- Use [Your Name] and [Recruiter Name] as placeholders.
"""


def draft_follow_up_email(index):
    """Ask Gemini to draft a follow-up email for the application at `index`.
    Returns the draft as text. It is never sent automatically."""
    pipeline = session_state["pipeline"]
    if index < 0 or index >= len(pipeline):
        raise ValueError(f"There is no application number {index + 1}.")

    return gemini_generate(build_follow_up_prompt(pipeline[index]))


def gemini_generate(prompt, want_json=False):
    """Send a prompt to Gemini and return the reply text.
    Tries each model in GEMINI_MODELS until one answers.
    Raises RuntimeError with a friendly message if none do."""
    try:
        from google import genai    # imported here so the rest of the app works without it
        from google.genai import types
    except ImportError:
        raise RuntimeError("The Gemini library isn't installed. Run: pip install google-genai")
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        raise RuntimeError("No Gemini API key found. Run: export GEMINI_API_KEY=\"your-key\"")

    client = genai.Client(   # reads the API key from the environment
        http_options=types.HttpOptions(
            timeout=GEMINI_TIMEOUT_SECONDS * 1000,              # in milliseconds
            retry_options=types.HttpRetryOptions(attempts=1),   # we handle fallback ourselves
        )
    )
    config = types.GenerateContentConfig(response_mime_type="application/json") if want_json else None

    errors = []
    for model in GEMINI_MODELS:
        try:
            response = client.models.generate_content(model=model, contents=prompt, config=config)
        except Exception as error:
            errors.append(f"{model}: {str(error)[:80]}")
            continue          # busy, slow, or unavailable: try the next model
        if response.text:
            return response.text.strip()
        errors.append(f"{model}: empty reply")

    raise RuntimeError("Gemini isn't available right now. Please try again later.\n    "
                       + "\n    ".join(errors))



# CV profile matching
# match_cv_to_job() tries Gemini first. If Gemini is busy or not set up,
# it falls back to a simple keyword match so you always get a score.
# A match result looks like:
#   {"score": 72, "method": "gemini" or "keyword", "matched_skills": [...],
#    "missing_skills": [...], "summary": "...", "tips": [...], "scored_on": "YYYY-MM-DD"}

# Common words that say nothing about skills, ignored by the keyword match
STOPWORDS = set("""
a about above after all also an and any are as at be been being both but by can could do
does doing during each etc for from further had has have having he her here hers him his how
i if in into is it its itself just me more most must my no nor not now of off on once only or
other our ours out over own per same she should so some such than that the their theirs them
then there these they this those through to too under until up very via was we were what when
where which while who whom why will with within without would you your yours
ability able across apply applicant applicants candidate candidates closing company day days
date description duties employer employment equal excellent experience including job join
looking new offer opportunity people plus position preferred required requirements
responsibilities responsible role salary seeking skills strong successful team teams use using
well work working year years will help make get good great high key level like range role
junior senior mid lead entry graduate intern building understanding knowledge familiarity
proven solid hands-on demonstrated environment fast-paced ideally desirable essential bonus
need needs needed want wants seek ensure across
""".split())


def extract_keywords(text):
    """Return the meaningful words in some text (lowercase, no stopwords)."""
    words = re.findall(r"[a-z0-9][a-z0-9+#.\-]*", text.lower())
    words = [word.rstrip(".-") for word in words]
    return [simplify(word) for word in words
            if len(word) > 1 and word not in STOPWORDS and not word.isdigit()]


def simplify(word):
    """Treat simple plurals as the same word, e.g. 'dashboards' -> 'dashboard'."""
    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def keyword_match(cv_text, job_description, top_n=25):
    """Simple offline match: what share of the job's key words appear in the CV."""
    job_words = extract_keywords(job_description)
    if not job_words:
        raise ValueError("The job description has no keywords to match against.")
    cv_words = set(extract_keywords(cv_text))

    # The job's most frequent words are treated as its key requirements
    frequency = {}
    for word in job_words:
        frequency[word] = frequency.get(word, 0) + 1
    key_words = sorted(frequency, key=lambda word: (-frequency[word], job_words.index(word)))[:top_n]

    matched = [word for word in key_words if word in cv_words]
    missing = [word for word in key_words if word not in cv_words]
    return {
        "score": round(100 * len(matched) / len(key_words)),
        "method": "keyword",
        "matched_skills": matched,
        "missing_skills": missing,
        "summary": "Rough keyword match: the share of the job's most frequent words found in your CV.",
        "tips": [f"If you have real experience with '{word}', mention it in your CV."
                 for word in missing[:3]],
        "scored_on": date.today().isoformat(),
    }


def build_match_prompt(cv_text, application):
    return f"""You are a careful recruiter. Compare this candidate's CV with the job description.

JOB: {application['role_title']} at {application['company_name']}
JOB DESCRIPTION:
\"\"\"
{application['job_description']}
\"\"\"

CV:
\"\"\"
{cv_text}
\"\"\"

Reply with JSON only, in exactly this shape:
{{"score": <whole number 0-100: how well the CV matches the job's requirements>,
  "matched_skills": [<up to 8 requirements the CV clearly shows>],
  "missing_skills": [<up to 8 requirements the CV does not show>],
  "summary": "<one or two sentences on the overall fit>",
  "tips": [<up to 3 short, specific ways to tailor the CV for this job>]}}

Rules: be honest, not flattering. Only count a skill as matched if the CV gives evidence of it.
Do not invent experience the CV does not mention."""


def gemini_match(cv_text, application):
    """Ask Gemini to score the match. Raises RuntimeError if it can't."""
    reply = gemini_generate(build_match_prompt(cv_text, application), want_json=True)
    try:
        data = json.loads(reply)
        score = int(data["score"])
    except (ValueError, KeyError, TypeError):
        raise RuntimeError("Gemini's reply wasn't in the expected format.")
    if not 0 <= score <= 100:
        raise RuntimeError(f"Gemini gave an impossible score ({score}).")

    def as_list(value):
        return [str(item) for item in value][:8] if isinstance(value, list) else []

    return {
        "score": score,
        "method": "gemini",
        "matched_skills": as_list(data.get("matched_skills")),
        "missing_skills": as_list(data.get("missing_skills")),
        "summary": str(data.get("summary", "")).strip(),
        "tips": as_list(data.get("tips"))[:3],
        "scored_on": date.today().isoformat(),
    }


def match_cv_to_job(cv_text, application):
    """Score how well the CV matches one application's job description.
    Returns (match_result, note). note explains a fallback, or is None."""
    if not cv_text.strip():
        raise ValueError("No CV loaded yet.")
    if not application.get("job_description", "").strip():
        raise ValueError("This application has no job description to match against.")

    try:
        return gemini_match(cv_text, application), None
    except RuntimeError as error:
        note = f"Gemini couldn't score this ({str(error).splitlines()[0]}), so a keyword match was used."
        return keyword_match(cv_text, application["job_description"]), note
