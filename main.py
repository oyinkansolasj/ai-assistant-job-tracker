# main.py - The command line interface (CLI). Run with: python3 main.py

import copy

from storage import (
    load_applications,
    load_cv,
    load_search_goal,
    read_cv_document,
    save_applications,
    save_cv,
    save_search_goal,
    to_json,
)
from tracker import (
    session_state,
    create_application,
    recalculate_counts,
    log_application,
    update_status,
    delete_application,
    MAX_FOLLOW_UPS,
    apply_follow_up,
    apply_status_change,
    get_follow_up_reminders,
    mark_followed_up,
    next_follow_up_date,
    summarize_pipeline,
    draft_follow_up_email,
    match_cv_to_job,
)
from validation import (
    VALID_STATUSES,
    validate_company_name,
    validate_date_applied,
    validate_deadline,
    validate_goal,
    validate_status,
)

# Small input helpers

def ask(prompt, validator=None, optional=False):
    """Ask a question. If a validator is given, keep asking until the answer is valid."""
    while True:
        answer = input(prompt).strip()
        if optional and answer == "":
            return None
        if validator is None:
            return answer
        try:
            return validator(answer)
        except ValueError as error:
            print(f"  ✗ {error}")


def ask_multiline(prompt):
    """Let the user paste several lines. They finish by typing END on its own line."""
    print(prompt)
    print("  (Paste the text, then type END on a new line and press Enter.)")
    lines = []
    while True:
        line = input()
        if line.strip().upper() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def confirm(prompt):
    """Ask for a clear yes or no. Anything vague (like "maybe") is rejected
    and the question is asked again. Returns True for yes, False for no."""
    while True:
        answer = input(f"{prompt} (yes/no): ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        if answer == "":
            print("  Please type yes or no.")
        else:
            print(f"  '{answer}' isn't a clear decision. Please type yes or no.")


SAVE_PATH_LABEL = "data/applications.json"
GOAL_PATH_LABEL = "data/search_goal.json"
CV_PATH_LABEL = "data/cv.txt"


def preview_and_write(file_label, heading, record, footer, write, data, success_message):
    """Show exactly what will be written, ask for a clear yes/no, then write it.
    Returns True only if the file was written successfully."""
    print(f"\n  About to save to {file_label}:")
    print(f"  {heading}")
    body = record if isinstance(record, str) else to_json(record)
    for line in body.splitlines():
        print(f"    {line}")
    if footer:
        print(f"  {footer}")

    if not confirm("Save this to the file?"):
        return False
    try:
        write(data)
    except OSError as error:
        print(f"  ✗ Could not write {file_label}: {error}")
        return False
    print(f"  ✓ {success_message}")
    return True


def preview_and_save(new_pipeline, heading, record, footer=None):
    """Preview and save the applications file."""
    if footer is None:
        others = len(new_pipeline) - 1
        footer = (f"The file will hold {len(new_pipeline)} application(s) in total "
                  f"({others} other(s) unchanged).")
    return preview_and_write(
        SAVE_PATH_LABEL, heading, record, footer, save_applications, new_pipeline,
        f"Saved {len(new_pipeline)} application(s) to {SAVE_PATH_LABEL}.",
    )


def preview_and_save_goal(goal_record, heading):
    """Preview and save the search goal file."""
    return preview_and_write(
        GOAL_PATH_LABEL, heading, goal_record, None, save_search_goal, goal_record,
        f"Saved your search goal to {GOAL_PATH_LABEL}.",
    )


def record_declined(action_type, details):
    """Remember that the user said no to an action."""
    session_state["last_action"] = {"type": action_type, "details": details, "approved": False}
    print("  Cancelled. Nothing was changed.")

# Menu actions

def apply_goal_record(goal_record):
    """Put a saved search goal into session_state."""
    session_state["search_goal"].update(goal_record["search_goal"])
    session_state["deadline"] = goal_record["deadline"]
    session_state["application_counts"]["daily_goal"] = goal_record["daily_goal"]
    session_state["application_counts"]["weekly_goal"] = goal_record["weekly_goal"]


def print_goal(goal_record):
    goal = goal_record["search_goal"]
    print(f"    Target role  : {goal['target_role'] or '-'}")
    print(f"    Industry     : {goal['industry'] or '-'}")
    print(f"    Company size : {goal['company_size'] or '-'}")
    print(f"    Work mode    : {goal['work_mode'] or '-'}")
    print(f"    Availability : {goal['availability'] or '-'}")
    print(f"    Deadline     : {goal_record['deadline'] or 'none set'}")
    print(f"    Goals        : {goal_record['daily_goal']} a day, {goal_record['weekly_goal']} a week")


def collect_search_goal():
    """Ask for a new search goal, then offer to save it."""
    print("\n=== Set up your job search ===")
    goal_record = {
        "search_goal": {
            "target_role": ask("Target role (e.g. Data Analyst): "),
            "industry": ask("Industry (e.g. Fintech): "),
            "company_size": ask("Company size (small / medium / large / any): "),
            "work_mode": ask("Work mode (on-site / hybrid / remote): "),
            "availability": ask("Availability (e.g. Mon-Fri, 9am-5pm): "),
        },
        "deadline": ask("Deadline to reach your goal (YYYY-MM-DD, blank to skip): ",
                        validate_deadline, optional=True),
        "daily_goal": ask("Daily application goal (e.g. 10): ", validate_goal),
        "weekly_goal": ask("Weekly application goal (e.g. 20): ", validate_goal),
    }
    apply_goal_record(goal_record)
    if not preview_and_save_goal(goal_record, "SEARCH GOAL:"):
        print("  Not saved. Using this search goal for this session only.")


def load_or_collect_search_goal():
    """Use the saved search goal if there is one (and the user wants to keep it),
    otherwise ask for a new one. Returns False if the saved file is broken."""
    try:
        goal_record = load_search_goal()
    except RuntimeError as error:
        print(f"  ✗ {error}")
        return False

    if goal_record is None:
        collect_search_goal()
        return True

    print(f"  ✓ Loaded your search goal from {GOAL_PATH_LABEL}:")
    print_goal(goal_record)
    if not confirm("Keep this search goal?"):
        collect_search_goal()
        return True

    apply_goal_record(goal_record)

    # A saved deadline may have passed since last time
    if goal_record["deadline"]:
        try:
            validate_deadline(goal_record["deadline"])
        except ValueError:
            print(f"  ! Your deadline {goal_record['deadline']} has passed.")
            goal_record["deadline"] = ask("New deadline (YYYY-MM-DD, blank for none): ",
                                          validate_deadline, optional=True)
            apply_goal_record(goal_record)
            if not preview_and_save_goal(goal_record, "UPDATED search goal (new deadline):"):
                print("  Not saved. Using the new deadline for this session only.")
    return True


def log_new_application():
    print("\n=== Log a new application ===")
    company = ask("Company name: ", validate_company_name)
    role = ask("Role title: ")
    date_applied = ask("Date applied (YYYY-MM-DD, blank for today): ", validate_date_applied, optional=True)
    status = ask(f"Status ({' / '.join(VALID_STATUSES)}, blank for applied): ", validate_status, optional=True) or "applied"
    notes = ask("Notes (optional): ")

    job_description, match = "", None
    if confirm("Add the job description (for CV matching)?"):
        job_description = ask_multiline("Paste the job description:")
        if job_description and session_state["cv_text"]:
            match = run_match(company, role, job_description)
        elif job_description:
            print("  No CV loaded yet, so no match score. Use option 7, then option 6 to score it.")

    # Build the record first (not added yet), so we can show exactly what will be saved
    new_record = create_application(company, role, status, date_applied, notes, job_description, match)
    new_pipeline = session_state["pipeline"] + [new_record]
    if not preview_and_save(new_pipeline, "NEW application:", new_record):
        record_declined("add", f"Add {role} at {company}")
        return
    application = log_application(company, role, status, date_applied, notes, job_description, match)
    follow_up = next_follow_up_date(application)
    if follow_up:
        print(f"  ✓ Logged. You'll be reminded to follow up on {follow_up}.")
    else:
        print("  ✓ Logged.")


def print_pipeline():
    """Show every application with a number, so the user can pick one."""
    for number, app in enumerate(session_state["pipeline"], start=1):
        print(f"  {number}. {app['company_name']} - {app['role_title']} "
              f"[{app['status']}] applied {app['date_applied']}{match_label(app)}")


def match_label(app):
    """Short text like '  · match 72%' (or '' if not scored yet)."""
    return f"  · match {app['match']['score']}%" if app.get("match") else ""


def update_application_status():
    print("\n=== Update an application status ===")
    index = pick_application()
    if index is None:
        return
    new_status = ask(f"New status ({' / '.join(VALID_STATUSES)}): ", validate_status)

    app = session_state["pipeline"][index]
    new_pipeline = copy.deepcopy(session_state["pipeline"])
    apply_status_change(new_pipeline[index], new_status)
    heading = f"UPDATED application {index + 1} (status: {app['status']} → {new_status}):"
    if not preview_and_save(new_pipeline, heading, new_pipeline[index]):
        record_declined("update", f"Change {app['company_name']} to {new_status}")
        return
    update_status(index, new_status)
    print("  ✓ Status updated.")


def delete_an_application():
    print("\n=== Delete an application ===")
    index = pick_application()
    if index is None:
        return

    app = session_state["pipeline"][index]
    new_pipeline = session_state["pipeline"][:index] + session_state["pipeline"][index + 1:]
    heading = f"DELETE application {index + 1} (this cannot be undone):"
    footer = (f"The file will hold {len(new_pipeline)} application(s) in total "
              f"(the others stay unchanged).")
    if not preview_and_save(new_pipeline, heading, app, footer):
        record_declined("delete", f"Delete {app['role_title']} at {app['company_name']}")
        return
    delete_application(index)
    print("  ✓ Application deleted.")


def set_up_cv():
    print("\n=== Set up your CV ===")
    if session_state["cv_text"]:
        print(f"  You already have a CV saved ({len(session_state['cv_text'].split())} words). "
              "A new one will replace it.")
    print("  Tip: you can drag the file into this window to paste its path.")
    cv_text = ask("Path to your CV (.pdf or .docx): ", read_cv_document)

    footer = f"{len(cv_text.split())} words. Check the text above looks right before saving."
    saved = preview_and_write(CV_PATH_LABEL, "CV TEXT:", cv_text, footer, save_cv, cv_text,
                              f"Saved your CV to {CV_PATH_LABEL}.")
    if not saved:
        record_declined("add", "Save CV")
        return
    session_state["cv_text"] = cv_text
    session_state["last_action"] = {"type": "add", "details": "Saved CV", "approved": True}


def run_match(company, role, job_description):
    """Score the CV against a job description and print the result."""
    print("  Matching your CV... (this sends your CV and the job description to Google Gemini)")
    application = {"company_name": company, "role_title": role, "job_description": job_description}
    try:
        match, note = match_cv_to_job(session_state["cv_text"], application)
    except ValueError as error:
        print(f"  ✗ Couldn't score this: {error}")
        return None
    if note:
        print(f"  ! {note}")
    print_match(match)
    return match


def print_match(match):
    method = "Gemini" if match["method"] == "gemini" else "keyword match (rough)"
    print(f"\n  CV MATCH: {match['score']}%   (by {method})")
    if match["summary"]:
        print(f"  {match['summary']}")
    if match["matched_skills"]:
        print(f"  ✓ You have : {', '.join(match['matched_skills'])}")
    if match["missing_skills"]:
        print(f"  ✗ Missing  : {', '.join(match['missing_skills'])}")
    for tip in match["tips"]:
        print(f"  → {tip}")


def match_an_application():
    print("\n=== Match your CV to an application ===")
    if not session_state["cv_text"]:
        print("  No CV loaded yet. Choose option 7 to set up your CV first.")
        return
    index = pick_application()
    if index is None:
        return

    app = session_state["pipeline"][index]
    job_description = app.get("job_description", "")
    if not job_description or not confirm("Use the job description already saved for this application?"):
        job_description = ask_multiline("Paste the job description:")
        if not job_description:
            print("  ✗ No job description given, so nothing to match.")
            return

    match = run_match(app["company_name"], app["role_title"], job_description)
    if match is None:
        return

    new_pipeline = copy.deepcopy(session_state["pipeline"])
    new_pipeline[index]["job_description"] = job_description
    new_pipeline[index]["match"] = match
    heading = f"UPDATED application {index + 1} (CV match: {match['score']}%):"
    if not preview_and_save(new_pipeline, heading, new_pipeline[index]):
        record_declined("update", f"Save CV match for {app['company_name']}")
        return
    session_state["pipeline"][index] = new_pipeline[index]
    session_state["last_action"] = {
        "type": "update",
        "details": f"Saved {match['score']}% CV match for {app['company_name']}",
        "approved": True,
    }


def pick_application():
    """List the applications and ask the user to choose one.
    Returns its position in the pipeline, or None if there is nothing to pick."""
    pipeline = session_state["pipeline"]
    if not pipeline:
        print("  You have no applications yet.")
        return None

    print_pipeline()
    number = ask("Which number? ", validate_goal)
    if number < 1 or number > len(pipeline):
        print(f"  ✗ Pick a number from 1 to {len(pipeline)}.")
        return None
    return number - 1


def draft_follow_up():
    print("\n=== Draft a follow-up email (Gemini) ===")
    index = pick_application()
    if index is None:
        return

    print_draft(index)


def print_draft(index):
    """Draft a follow-up email with Gemini and print it. Returns True if a draft was shown."""
    print("  Drafting with Gemini...")
    try:
        draft = draft_follow_up_email(index)
    except RuntimeError as error:
        print(f"  ✗ {error}")
        return False

    print("\n" + "-" * WIDTH)
    print(draft)
    print("-" * WIDTH)
    print("  This is a draft only. Review it and send it yourself.")
    return True


def reminder_line(item):
    """One line describing a reminder, e.g. 'Acme - Analyst [applied] overdue by 3 days'."""
    app = item["application"]
    if "overdue" in item:
        days = item["days"]
        when = "due today" if days == 0 else f"overdue by {days} day{'s' if days != 1 else ''}"
    else:
        days = item["days"]
        when = f"due in {days} day{'s' if days != 1 else ''} ({item['follow_up_date']})"
    count = app.get("follow_up_count", 0)
    done = f", followed up {count}x" if count else ""
    return f"{app['company_name']} - {app['role_title']} [{app['status']}] {when}{done}"


def follow_up_reminders():
    print("\n=== Follow-up reminders ===")
    reminders = get_follow_up_reminders()
    due = [{**item, "overdue": True} for item in reminders["due"]]
    upcoming = reminders["upcoming"]
    if not due and not upcoming:
        print("  Nothing to follow up on right now. 🎉")
        return

    choices = due + upcoming
    if due:
        print("  DUE NOW")
        for number, item in enumerate(due, start=1):
            print(f"    {number}. {reminder_line(item)}")
            if item["application"].get("follow_up_count", 0) >= MAX_FOLLOW_UPS:
                print(f"       ! You've followed up {MAX_FOLLOW_UPS}+ times with no reply. "
                      "Consider moving on (status: withdrawn).")
    if upcoming:
        print("  COMING UP")
        for number, item in enumerate(upcoming, start=len(due) + 1):
            print(f"    {number}. {reminder_line(item)}")

    number = ask("Pick a number to act on (blank to go back): ", validate_goal, optional=True)
    if number is None:
        return
    if number < 1 or number > len(choices):
        print(f"  ✗ Pick a number from 1 to {len(choices)}.")
        return
    index = choices[number - 1]["index"]
    app = session_state["pipeline"][index]

    print(f"\n  {app['company_name']} - {app['role_title']}")
    print("    1. Mark as followed up today")
    print("    2. Draft a follow-up email first (AI)")
    action = ask("  Choose 1-2 (blank to go back): ", optional=True)
    if action == "2":
        if not print_draft(index) or not confirm("Did you send it? Mark as followed up today?"):
            return
    elif action != "1":
        return
    save_follow_up(index)


def save_follow_up(index):
    """Preview, confirm, and save a follow-up for one application."""
    app = session_state["pipeline"][index]
    new_pipeline = copy.deepcopy(session_state["pipeline"])
    apply_follow_up(new_pipeline[index])
    heading = (f"UPDATED application {index + 1} (followed up today, "
               f"next reminder {next_follow_up_date(new_pipeline[index])}):")
    if not preview_and_save(new_pipeline, heading, new_pipeline[index]):
        record_declined("update", f"Mark follow-up for {app['company_name']}")
        return
    mark_followed_up(index)
    print(f"  ✓ Marked as followed up. Next reminder: {next_follow_up_date(app)}.")


WIDTH = 56   # how wide the summary box is


def show_summary():
    """Print a formatted pipeline summary, with applications grouped by status."""
    summary = summarize_pipeline()
    counts = summary["counts"]
    goal = session_state["search_goal"]

    print("\n" + "=" * WIDTH)
    print(" PIPELINE SUMMARY".center(WIDTH))
    print("=" * WIDTH)
    print(f" Searching for : {goal['target_role'] or '-'} | {goal['industry'] or '-'} | "
          f"{goal['company_size'] or '-'} | {goal['work_mode'] or '-'}")
    print(f" Deadline      : {summary['deadline'] or 'none set'}")
    print(f" Progress      : Today {counts['today']}/{counts['daily_goal']}  ·  "
          f"Week {counts['this_week']}/{counts['weekly_goal']}  ·  "
          f"Total {summary['total']}")
    print("-" * WIDTH)

    # Applications grouped by status
    for status, count in summary["by_status"].items():
        print(f" {status.upper():<14}({count})")
        for app in session_state["pipeline"]:
            if app["status"] == status:
                print(f"    • {app['company_name']} - {app['role_title']}  "
                      f"(applied {app['date_applied']}){match_label(app)}")

    if summary["follow_ups_due"]:
        print("-" * WIDTH)
        print(f" FOLLOW-UPS DUE ({len(summary['follow_ups_due'])})  - choose option 8 to act on them")
        for item in summary["follow_ups_due"]:
            print(f"    ! {reminder_line({**item, 'overdue': True})}")

    last = session_state["last_action"]
    if last["type"]:
        result = "approved" if last["approved"] else "declined"
        print("-" * WIDTH)
        print(f" Last action   : {last['details']} ({result})")
    print("=" * WIDTH)


# Main loop

def main():
    print("Welcome to your Job Application Tracker!")
    try:
        session_state["pipeline"] = load_applications()
    except RuntimeError as error:
        print(f"  ✗ {error}")
        return
    recalculate_counts()
    if session_state["pipeline"]:
        print(f"  ✓ Loaded {len(session_state['pipeline'])} application(s) from {SAVE_PATH_LABEL}.")
    else:
        print(f"  ✓ Checked {SAVE_PATH_LABEL}: no saved applications yet.")
    session_state["cv_text"] = load_cv()
    if session_state["cv_text"]:
        print(f"  ✓ Loaded your CV from {CV_PATH_LABEL} ({len(session_state['cv_text'].split())} words).")
    else:
        print(f"  ✓ No CV saved yet. Choose option 7 to add one for job matching.")
    if not load_or_collect_search_goal():
        return

    due = get_follow_up_reminders()["due"]
    if due:
        print(f"\n  🔔 You have {len(due)} follow-up(s) due. Choose option 8 to act on them.")
    show_summary()

    while True:
        print("\nWhat would you like to do?")
        print("  1. Log a new application")
        print("  2. Update an application status")
        print("  3. Delete an application")
        print("  4. View pipeline summary")
        print("  5. Draft a follow-up email (AI)")
        print("  6. Match your CV to an application (AI)")
        print("  7. Set up / replace your CV")
        print("  8. Follow-up reminders")
        print("  9. Quit")
        choice = input("Choose 1-9: ").strip()

        if choice == "1":
            log_new_application()
        elif choice == "2":
            update_application_status()
        elif choice == "3":
            delete_an_application()
        elif choice == "4":
            pass   # the summary is shown below
        elif choice == "5":
            draft_follow_up()
        elif choice == "6":
            match_an_application()
        elif choice == "7":
            set_up_cv()
        elif choice == "8":
            follow_up_reminders()
        elif choice == "9":
            print("Goodbye, and good luck with your applications!")
            break
        else:
            print("  Please choose a number from 1 to 9.")
            continue

        # Always show the current state after an action
        show_summary()


if __name__ == "__main__":
    main()
