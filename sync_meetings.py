import os
import re
import json
from datetime import datetime
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build

# --------------------------------------------------
# CONFIG
# --------------------------------------------------

DOC_ID = os.environ.get("GOOGLE_DOC_ID")

BASE_OUTPUT_DIR = Path("docs/Meetings")
BASE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SCOPES = ["https://www.googleapis.com/auth/documents.readonly"]

MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}

DATE_PATTERN = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})"
)

# --------------------------------------------------
# AUTH
# --------------------------------------------------

def get_docs_service():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")

    if not creds_json:
        raise ValueError("Missing GOOGLE_CREDENTIALS environment variable")

    creds_info = json.loads(creds_json)

    creds = service_account.Credentials.from_service_account_info(
        creds_info,
        scopes=SCOPES
    )

    return build("docs", "v1", credentials=creds)

# --------------------------------------------------
# EXTRACT TEXT
# --------------------------------------------------

def extract_text(doc):
    text = ""
    body = doc.get("body", {}).get("content", [])

    for block in body:
        paragraph = block.get("paragraph")
        if not paragraph:
            continue

        for elem in paragraph.get("elements", []):
            run = elem.get("textRun")
            if run:
                text += run.get("content", "")

        text += "\n"

    return text

# --------------------------------------------------
# SPLIT MEETINGS
# --------------------------------------------------

def split_meetings(text):
    matches = list(DATE_PATTERN.finditer(text))

    meetings = []

    for i, match in enumerate(matches):
        month = match.group(1)
        day = int(match.group(2))
        year = int(match.group(3))

        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        section = text[start:end].strip()

        date_obj = datetime(year, MONTHS[month], day)

        filename = f"meeting_{date_obj.strftime('%Y-%m-%d')}.md"

        meetings.append((date_obj, filename, section))

    return meetings

# --------------------------------------------------
# FIELD HELPERS
# --------------------------------------------------

def get_field(text, label):
    match = re.search(rf"\*\*{label}:\*\*\s*(.*)", text)
    return match.group(1).strip() if match else ""

def get_list(text, section):
    pattern = rf"\*\*{section}\*\*.*?(?=\*\*|$)"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return []
    return [l.strip("- ").strip() for l in match.group(0).split("\n") if l.strip().startswith("-")]

# --------------------------------------------------
# FORMAT MEETING
# --------------------------------------------------

def format_meeting(date_str, content):

    facilitator = get_field(content, "Facilitator")
    attendees = get_field(content, "Attendees")
    note_taker = get_field(content, "Note Taking volunteer")
    next_facilitator = get_field(content, "Next month's facilitator")

    agenda = get_list(content, "Agendas") or get_list(content, "Agenda")
    open_mic = get_list(content, "Open Mic")
    events = get_list(content, "Upcoming Events and Opportunities")
    actions = get_list(content, "Meeting notes and action items")

    md = f"""# OSGeo Nepal General Meeting - {date_str}

**Facilitator**: {facilitator}  
**Attendees**: {attendees}  
**Note-taking volunteer**: {note_taker}  

## Agendas
"""

    for a in agenda:
        md += f"- [ ] {a}\n"

    md += "\n## Open Mic\n"
    for o in open_mic:
        md += f"- [ ] {o}\n"

    md += "\n## Upcoming Events and Opportunities\n"
    for e in events:
        md += f"- [ ] {e}\n"

    md += f"""

## Next month's facilitator
- {next_facilitator}

## Action items
"""

    for a in actions:
        md += f"- [ ] {a}\n"

    return md

# --------------------------------------------------
# SAVE (YEAR + SORT NEWEST FIRST)
# --------------------------------------------------

def save_meetings(meetings):
    created = []
    skipped = []

    # 🔥 SORT NEWEST FIRST
    meetings.sort(key=lambda x: x[0], reverse=True)

    for date_obj, filename, content in meetings:
        year_dir = BASE_OUTPUT_DIR / str(date_obj.year)
        year_dir.mkdir(parents=True, exist_ok=True)

        path = year_dir / filename

        if path.exists():
            skipped.append(str(path))
            continue

        date_str = date_obj.strftime("%B %d, %Y")

        formatted = format_meeting(date_str, content)

        with open(path, "w", encoding="utf-8") as f:
            f.write(formatted)

        created.append(str(path))

    return created, skipped

# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():
    if not DOC_ID:
        raise ValueError("Missing GOOGLE_DOC_ID environment variable")

    service = get_docs_service()
    doc = service.documents().get(documentId=DOC_ID).execute()

    text = extract_text(doc)

    meetings = split_meetings(text)

    created, skipped = save_meetings(meetings)

    print("\n=== SYNC RESULTS ===")

    print("\nCreated:")
    for c in created:
        print(" +", c)

    print("\nSkipped:")
    for s in skipped:
        print(" -", s)

    print(f"\nDone → Created: {len(created)}, Skipped: {len(skipped)}")


if __name__ == "__main__":
    main()