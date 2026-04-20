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

OUTPUT_DIR = Path("docs/Meetings")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SCOPES = ["https://www.googleapis.com/auth/documents.readonly"]

MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}

# Matches:
# ### April 04, 2026
# April 04, 2026
DATE_PATTERN = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})"
)

# --------------------------------------------------
# AUTH (GitHub Secret based)
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
# EXTRACT TEXT FROM GOOGLE DOC
# --------------------------------------------------

def extract_text(doc):
    text = ""

    body = doc.get("body", {}).get("content", [])

    for element in body:
        paragraph = element.get("paragraph")
        if not paragraph:
            continue

        for elem in paragraph.get("elements", []):
            run = elem.get("textRun")
            if run:
                text += run.get("content", "")

    return text

# --------------------------------------------------
# SPLIT BY H3 DATE HEADINGS
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

        meetings.append((filename, section))

    return meetings

# --------------------------------------------------
# SAVE FILES (NO OVERWRITE)
# --------------------------------------------------

def save_meetings(meetings):
    created = []
    skipped = []

    for filename, content in meetings:
        path = OUTPUT_DIR / filename

        if path.exists():
            skipped.append(filename)
            continue

        # ensure markdown format
        if not content.startswith("###"):
            content = "### " + content

        with open(path, "w", encoding="utf-8") as f:
            f.write(content + "\n")

        created.append(filename)

    return created, skipped

# --------------------------------------------------
# MAIN EXECUTION
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

    print("\nCreated files:")
    for c in created:
        print(" +", c)

    print("\nSkipped files:")
    for s in skipped:
        print(" -", s)

    print(f"\nDone → Created: {len(created)}, Skipped: {len(skipped)}")


if __name__ == "__main__":
    main()