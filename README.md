# Job Application Tracker - AI Assistant

A command-line job search assistant written in Python. It keeps track of every application you send, scores how well your CV matches each job using Google Gemini, reminds you when to follow up, and drafts follow-up emails. Nothing gets saved, changed or deleted until you approve it.

## Features

- **Application tracking.** Log, update and delete applications, each with a status: `applied`, `interviewing`, `offer`, `rejected` or `withdrawn`.
- **CV profile matching.** Load your CV from a PDF or Word file and paste in a job description. Gemini returns a 0–100 match score, the skills you have, the gaps, and tips for tailoring your CV. If Gemini isn't available, an offline keyword match is used instead.
- **Follow-up reminders.** Open applications get a reminder 7 days after you apply, 5 days after an interview update and 3 days after an offer. The clock restarts when you follow up or the status changes. After 3 follow-ups with no reply, the app suggests moving on.
- **AI follow-up emails.** Gemini drafts a short follow-up email that fits the application's status. The app never sends it; you review it and send it yourself.
- **Search goal and targets.** Set your target role, industry, company size, work mode (on-site, hybrid or remote), availability, a deadline, and daily and weekly application goals.
- **Pipeline summary.** After every action you see your progress towards your goals, your applications grouped by status, and any follow-ups that are due.
- **Approval before every change.** Before writing to a file, the app shows exactly what will be saved and waits for a clear `yes` or `no`. Vague answers such as "maybe" are rejected.
- **Input validation.** The app rejects empty company names, invalid statuses, badly formatted dates, past deadlines and future application dates.


## Requirements

- Python 3.9 or newer
- A free [Gemini API key](https://aistudio.google.com/apikey). This is optional: without it, CV matching falls back to the keyword match and email drafting is turned off.

## Setup

```bash
# 1. Get the code
git clone https://github.com/<your-username>/ai-job-application-tracker.git
cd ai-job-application-tracker

# 2. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install the libraries
pip install -r requirements.txt

# 4. (Optional) add your Gemini API key
export GEMINI_API_KEY="your-key"
#    To keep it for every new terminal on macOS:
#    echo 'export GEMINI_API_KEY="your-key"' >> ~/.zshrc
```


## Usage

```bash
python3 main.py
```

| # | Option | What it does |
|---|---|---|
| 1 | Log a new application | Add a company, role, date, status, notes and, optionally, the job description |
| 2 | Update an application status | Move an application to a new status |
| 3 | Delete an application | Remove an application (you'll be asked to confirm first) |
| 4 | View pipeline summary | Show your progress, applications by status and follow-ups due |
| 5 | Draft a follow-up email (AI) | Gemini writes a follow-up email for you to review |
| 6 | Match your CV to an application (AI) | Score your CV against the job description |
| 7 | Set up / replace your CV | Load your CV from a `.pdf` or `.docx` file |
| 8 | Follow-up reminders | See which follow-ups are due or coming up, and mark them done |
| 9 | Quit | Exit the app |

## Your data and privacy

Everything is stored locally in the `data/` folder:

| File | Contents |
|---|---|
| `data/applications.json` | Your applications |
| `data/search_goal.json` | Your search goal, deadline and application goals |
| `data/cv.txt` | The text taken from your CV |


## Project structure

```
├── main.py           # Command-line interface: menus, prompts, approvals, summary display
├── tracker.py        # Core logic: session state, data model, reminders, CV matching, Gemini
├── storage.py        # Loading and saving the data/ files, reading PDF/Word CVs
├── validation.py     # Input validation rules
├── requirements.txt
└── data/             # Your personal data 
```
## Roadmap

- AI job search: find roles that fit your CV and search goal
- "Not applied yet" status and job closing-date reminders
- Filter target companies by industry and size
