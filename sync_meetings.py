import os
import re
from datetime import datetime
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build

# ---------------- CONFIG ----------------

DOC_ID = os.environ.get("GOOGLE_DOC_ID")
OUTPUT_DIR = Path("docs/Meetings")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SCOPES = ["https://www.googleapis.com/auth/documents.readonly"]

MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}

DATE_PATTERN = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})"
)

# ---------------- AUTH ----------------

def get_service():
    creds = service_account.Credentials.from_service_account_info(
        eval(os.environ["GOOGLE_CREDENTIALS"]),
        scopes=SCOPES
    )
    return build("docs", "v1", credentials=creds)

# ---------------- EXTRACT RAW TEXT ----------------

def extract_text(doc):
    text = ""
    for block in doc.get("body", {}).get("content", []):
        para = block.get("paragraph")
        if not para:
            continue

        line = ""
        for el in para.get("elements", []):
            run = el.get("textRun")
            if run:
                line += run.get("content", "")

        text += line + "\n"

    return text

# ---------------- SPLIT BY H3 DATES ----------------

def split_meetings(text):
    matches = list(DATE_PATTERN.finditer(text))
    meetings = []

    for i, m in enumerate(matches):
        month, day, year = m.group(1), int(m.group(2)), int(m.group(3))

        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        block = text[start:end].strip()

        date_obj = datetime(year, MONTHS[month], day)

        filename = f"meeting_{date_obj.strftime('%Y-%m-%d')}.md"

        meetings.append((date_obj, filename, block))

    return meetings

# ---------------- WRITE FILES (NO FORMAT CHANGE) ----------------

def save(meetings):
    created = []
    skipped = []

    meetings.sort(key=lambda x: x[0])  # optional chronological order

    for date_obj, filename, block in meetings:

        year_dir = OUTPUT_DIR / str(date_obj.year)
        year_dir.mkdir(parents=True, exist_ok=True)

        path = year_dir / filename

        if path.exists():
            skipped.append(str(path))
            continue

        title = f"# OSGeo Nepal General Meeting - {date_obj.strftime('%B %d, %Y')}\n\n"

        content = title + block.strip() + "\n"

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        created.append(str(path))

    return created, skipped

# ---------------- MAIN ----------------

def main():
    service = get_service()
    doc = service.documents().get(documentId=DOC_ID).execute()

    text = extract_text(doc)

    meetings = split_meetings(text)

    created, skipped = save(meetings)

    print("Created:", len(created))
    print("Skipped:", len(skipped))

if __name__ == "__main__":
    main()