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
        raise ValueError("Missing GOOGLE_CREDENTIALS")

    creds = service_account.Credentials.from_service_account_info(
        json.loads(creds_json),
        scopes=SCOPES
    )

    return build("docs", "v1", credentials=creds)

# --------------------------------------------------
# EXTRACT TEXT
# --------------------------------------------------

def extract_text(doc):
    text = ""
    for block in doc.get("body", {}).get("content", []):
        para = block.get("paragraph")
        if not para:
            continue

        for el in para.get("elements", []):
            run = el.get("textRun")
            if run:
                text += run.get("content", "")

        text += "\n"

    return text

# --------------------------------------------------
# SPLIT BY DATE HEADINGS
# --------------------------------------------------

def split_meetings(text):
    matches = list(DATE_PATTERN.finditer(text))
    meetings = []

    for i, m in enumerate(matches):
        month, day, year = m.group(1), int(m.group(2)), int(m.group(3))

        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        section = text[start:end].strip()

        date_obj = datetime(year, MONTHS[month], day)
        filename = f"meeting_{date_obj.strftime('%Y-%m-%d')}.md"

        meetings.append((date_obj, filename, section))

    return meetings

# --------------------------------------------------
# STRUCTURE-AWARE PARSER (IMPORTANT FIX)
# --------------------------------------------------

def parse(content):
    lines = [l.strip() for l in content.split("\n")]

    data = {
        "facilitator": "",
        "attendees": "",
        "note_taker": "",
        "agenda": [],
        "open_mic": [],
        "events": [],
        "next_facilitator": "",
        "actions": []
    }

    current = None

    def clean(x):
        return x.lower().replace("**", "").replace(":", "").strip()

    def is_heading(line):
        return line.startswith("###") or line.startswith("####")

    def next_value(i):
        """
        Returns next non-empty NON-heading line
        """
        j = i + 1
        while j < len(lines):
            l = lines[j].strip()
            if not l:
                j += 1
                continue
            if is_heading(l):
                return ""
            return l
        return ""

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        n = clean(line)

        # ---------------- STRICT FIELD MATCHING ----------------
        if n == "facilitator":
            data["facilitator"] = next_value(i)

        elif n == "attendees":
            data["attendees"] = next_value(i)

        elif n == "note taking volunteer":
            data["note_taker"] = next_value(i)

        elif n == "next facilitator":
            data["next_facilitator"] = next_value(i)

        # ---------------- SECTION SWITCHING ONLY ----------------
        elif "agenda" in n:
            current = "agenda"

        elif "open mic" in n:
            current = "open_mic"

        elif "upcoming events and opportunities" in n:
            current = "events"

        elif "action items" in n:
            current = "actions"

        # ---------------- LIST ITEMS ----------------
        elif line.startswith("-"):
            item = line.replace("-", "").strip()

            if current == "agenda":
                data["agenda"].append(item)
            elif current == "open_mic":
                data["open_mic"].append(item)
            elif current == "events":
                data["events"].append(item)
            elif current == "actions":
                data["actions"].append(item)

        i += 1

    return data

# --------------------------------------------------
# FORMAT MARKDOWN
# --------------------------------------------------

def format_meeting(date_str, content):

    d = parse(content)

    md = f"""# OSGeo Nepal General Meeting - {date_str}

**Facilitator**: {d['facilitator']}  
**Attendees**: {d['attendees']}  
**Note-taking volunteer**: {d['note_taker']}  

## Agendas
"""

    for a in d["agenda"]:
        md += f"- [ ] {a}\n"

    md += "\n## Open Mic\n"
    for o in d["open_mic"]:
        md += f"- [ ] {o}\n"

    md += "\n## Upcoming Events and Opportunities\n"
    for e in d["events"]:
        md += f"- [ ] {e}\n"

    md += f"""
## Next month's facilitator
- {d['next_facilitator']}

## Action items
"""

    for a in d["actions"]:
        md += f"- [ ] {a}\n"

    return md

# --------------------------------------------------
# SAVE (YEAR + SORT NEWEST FIRST)
# --------------------------------------------------

def save_meetings(meetings):
    created, skipped = [], []

    meetings.sort(key=lambda x: x[0], reverse=True)

    for date_obj, filename, content in meetings:
        year_dir = BASE_OUTPUT_DIR / str(date_obj.year)
        year_dir.mkdir(parents=True, exist_ok=True)

        path = year_dir / filename

        if path.exists():
            skipped.append(str(path))
            continue

        md = format_meeting(date_obj.strftime("%B %d, %Y"), content)

        with open(path, "w", encoding="utf-8") as f:
            f.write(md)

        created.append(str(path))

    return created, skipped

# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():
    service = get_docs_service()
    doc = service.documents().get(documentId=DOC_ID).execute()

    text = extract_text(doc)

    meetings = split_meetings(text)

    created, skipped = save_meetings(meetings)

    print("\nCreated:")
    for c in created:
        print("+", c)

    print("\nSkipped:")
    for s in skipped:
        print("-", s)

    print(f"\nDone → {len(created)} created, {len(skipped)} skipped")


if __name__ == "__main__":
    main()