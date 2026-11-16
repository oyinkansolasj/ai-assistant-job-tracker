# storage.py - Saves and loads your data in the data/ folder:
#   data/applications.json  - every application you have logged
#   data/search_goal.json   - your search goal, deadline, and application goals
#   data/cv.txt             - the text of your CV, used for job matching

import json
import os
from pathlib import Path

# The file lives in the data/ folder next to this script, so it works no matter which folder you run the app from.
DATA_FILE = Path(__file__).parent / "data" / "applications.json"
GOAL_FILE = Path(__file__).parent / "data" / "search_goal.json"
CV_FILE = Path(__file__).parent / "data" / "cv.txt"

REQUIRED_FIELDS = ["company_name", "role_title", "date_applied", "status", "notes"]
# Fields added later. Older saved applications get these defaults when loaded.
OPTIONAL_FIELDS = {"job_description": "", "match": None, "last_contact": None, "follow_up_count": 0}
GOAL_FIELDS = ["search_goal", "deadline", "daily_goal", "weekly_goal"]


def to_json(data):
    """Turn data into the exact text that gets written to the file."""
    return json.dumps(data, indent=2, ensure_ascii=False)


def load_applications(path=None):
    """Read saved applications. Returns an empty list if there is no file yet."""
    path = path or DATA_FILE
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"{path} is not valid JSON ({error}). "
            "Fix it or move it somewhere else, then start the app again."
        )

    if not isinstance(data, list):
        raise RuntimeError(f"{path} should contain a list of applications.")
    for number, application in enumerate(data, start=1):
        missing = [field for field in REQUIRED_FIELDS if field not in application]
        if missing:
            raise RuntimeError(f"Application {number} in {path} is missing: {', '.join(missing)}.")
        for field, default in OPTIONAL_FIELDS.items():
            application.setdefault(field, default)
    return data


def save_applications(applications, path=None):
    """Write all applications to their file."""
    write_json(applications, path or DATA_FILE)


def load_search_goal(path=None):
    """Read the saved search goal. Returns None if there is no file yet."""
    path = path or GOAL_FILE
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"{path} is not valid JSON ({error}). "
            "Fix it or move it somewhere else, then start the app again."
        )

    missing = [field for field in GOAL_FIELDS if not isinstance(data, dict) or field not in data]
    if missing:
        raise RuntimeError(f"{path} is missing: {', '.join(missing)}.")
    return data


def save_search_goal(goal, path=None):
    """Write the search goal to its file."""
    write_json(goal, path or GOAL_FILE)


def write_json(data, path):
    """Safely write data to a JSON file.
    It writes to a temporary file first, then swaps it in, so a crash
    halfway through can never leave you with a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(to_json(data) + "\n", encoding="utf-8")
    os.replace(temp_path, path)


# CV

def read_cv_document(file_path):
    """Pull the text out of a CV saved as a PDF or Word (.docx) file."""
    path = Path(str(file_path).strip().strip("'\"")).expanduser()   # allow drag-and-dropped paths
    if not path.exists():
        raise ValueError(f"Can't find a file at {path}.")

    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            from pypdf import PdfReader
            text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
        elif suffix == ".docx":
            from docx import Document
            text = "\n".join(paragraph.text for paragraph in Document(path).paragraphs)
        else:
            raise ValueError("Please use a .pdf or .docx file.")
    except ImportError as error:
        raise ValueError(f"A library is missing ({error.name}). Run: pip install pypdf python-docx")
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(f"Couldn't read {path.name}: {error}")

    # Tidy up: drop empty lines and extra spaces
    lines = [" ".join(line.split()) for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    if len(text) < 50:
        raise ValueError(f"Found almost no text in {path.name}. If it's a scanned image, "
                         "export it as a text-based PDF or Word file instead.")
    return text


def load_cv(path=None):
    """Read the saved CV text. Returns "" if there is no saved CV yet."""
    path = path or CV_FILE
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def save_cv(cv_text, path=None):
    """Write the CV text to data/cv.txt (same safe write as the JSON files)."""
    path = path or CV_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".txt.tmp")
    temp_path.write_text(cv_text + "\n", encoding="utf-8")
    os.replace(temp_path, path)
