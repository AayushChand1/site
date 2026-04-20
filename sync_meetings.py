import os
import re
from datetime import datetime
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build

# --------------------------------------------------
# CONFIG
# --------------------------------------------------

DOC_ID = os.environ.get("GOOGLE_DOC_ID")

BASE_DIR = Path("docs/Meetings")
BASE_DIR.mkdir(parents=True, exist_ok=True)

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

def get_service():
    creds = service_account.Credentials.from_service_account_info(
        eval(os.environ["GOOGLE_CREDENTIALS"]),
        scopes=SCOPES
    )
    return build("docs", "v1", credentials=creds)

# --------------------------------------------------
# PRESERVE MARKDOWN FORMAT (BOLD + BULLETS + STRUCTURE)
# --------------------------------------------------

def extract_markdown(doc):
    md = ""

    for block in doc.get("body", {}).get("content", []):
        para = block.get("paragraph")
        if not para:
            continue

        line = ""
        is_bullet = para.get("bullet") is not None

        for el in para.get("elements", []):
            run = el.get("textRun")
            if not run:
                continue

            text = run.get("content", "")
            style = run.get("textStyle", {})

            # preserve bold
            if style.get("bold"):
                text = f"**{text.strip()}** "

            line += text

        line = line.rstrip()

        if not line.strip():
            md += "\n"
            continue

        if is_bullet:
            md += f"- {line.strip()}\n"
        else:
            md += f"{line.strip()}\n"

    return md

# --------------------------------------------------
# SPLIT BY H3 DATES
# --------------------------------------------------

def split_meetings(doc):
    body = doc.get("body", {}).get("content", [])

    meetings = []
    current_date = None
    current_lines = []

    for block in body:
        para = block.get("paragraph")
        if not para:
            continue

        text = ""

        # rebuild full paragraph text
        for el in para.get("elements", []):
            run = el.get("textRun")
            if run:
                text += run.get("content", "")

        text = text.strip()

        if not text:
            continue

        # ONLY detect REAL heading blocks (H3 in Google Docs)
        p_style = para.get("paragraphStyle", {})
        named_style = p_style.get("namedStyleType", "")

        is_h3 = named_style == "HEADING_3"

        match = DATE_PATTERN.search(text)

        # START OF NEW MEETING
        if is_h3 and match:
            # save previous meeting
            if current_date and current_lines:
                meetings.append((current_date, "\n".join(current_lines)))

            month, day, year = match.group(1), int(match.group(2)), int(match.group(3))
            current_date = datetime(year, MONTHS[month], day)
            current_lines = [text]

        else:
            if current_date:
                current_lines.append(text)

    # last block
    if current_date and current_lines:
        meetings.append((current_date, "\n".join(current_lines)))

    # convert to filenames
    output = []
    for date_obj, block in meetings:
        filename = f"meeting_{date_obj.strftime('%Y-%m-%d')}.md"
        output.append((date_obj, filename, block))

    return output

# --------------------------------------------------
# SAVE FILES
# --------------------------------------------------

def save(meetings):
    created = []
    skipped = []

    meetings.sort(key=lambda x: x[0])  # chronological order

    for date_obj, filename, block in meetings:

        year_dir = BASE_DIR / str(date_obj.year)
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

# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():
    if not DOC_ID:
        raise ValueError("Missing GOOGLE_DOC_ID")

    service = get_service()
    doc = service.documents().get(documentId=DOC_ID).execute()

    text = extract_markdown(doc)

    meetings = split_meetings(doc)

    created, skipped = save(meetings)

    print("\n=== SYNC COMPLETE ===")
    print("Created:", len(created))
    print("Skipped:", len(skipped))


if __name__ == "__main__":
    main()