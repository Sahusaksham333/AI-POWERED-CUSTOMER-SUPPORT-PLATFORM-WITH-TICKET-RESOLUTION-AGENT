import re
from pathlib import Path
import pymupdf  # Modern API replacing deprecated 'import fitz'
import pandas as pd

def find_pdf_file(filename: str) -> Path:
    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir / filename,
        Path.cwd() / filename,
        Path.home() / "Downloads" / filename,
    ]
    for path in candidates:
        if path.exists():
            return path
            
    # Fallback: search for any matching PDF in current dir or Downloads
    for folder in [script_dir, Path.home() / "Downloads"]:
        matches = list(folder.glob("*IT_Hardware_Software_Troubleshooting*.pdf"))
        if matches:
            return matches[0]
            
    raise FileNotFoundError(
        f"Could not find '{filename}' in:\n  - {script_dir}\n  - {Path.home() / 'Downloads'}"
    )

def extract_faq_to_excel(pdf_filename: str, output_excel: str):
    pdf_path = find_pdf_file(pdf_filename)
    print(f"Reading PDF from: {pdf_path}")
    
    doc = pymupdf.open(pdf_path)
    full_text = "\n".join(page.get_text("text") for page in doc)

    # Strip page headers
    full_text = re.sub(r"IT Hardware & Software Troubleshooting FAQ\s+Page \d+", "", full_text)

    records = []
    current_part = "PART A — HARDWARE TROUBLESHOOTING"
    current_category = "Uncategorized"

    pattern = re.compile(
        r"(PART [AB]\s+—\s+[A-Z\s]+(?:\(\d+\s+FAQs\))?)|"
        r"(?:^|\n)([A-Z][a-zA-Z\s,/&-]+)\n(?=\d{3}\.\s)|"
        r"(\d{3})\.\s+(.*?)\s+Suggested answer:\s+(.*?)(?=\n(?:PART [AB]|[A-Z][a-zA-Z\s,/&-]+\n\d{3}\.|\d{3}\.\s)|\Z)",
        re.DOTALL
    )

    for match in pattern.finditer(full_text):
        part_hdr, cat_hdr, q_id, question, answer = match.groups()
        if part_hdr:
            current_part = part_hdr.strip()
        elif cat_hdr:
            current_category = cat_hdr.strip()
        elif q_id:
            records.append({
                "ID": q_id.strip(),
                "Part": current_part,
                "Category": current_category,
                "Question": " ".join(question.split()),
                "Suggested Answer": " ".join(answer.split())
            })

    output_path = Path(__file__).resolve().parent / output_excel
    df = pd.DataFrame(records)
    df.to_excel(output_path, index=False)
    print(f"Successfully extracted {len(df)} records to: {output_path}")

if __name__ == "__main__":
    extract_faq_to_excel(
        "IT_Hardware_Software_Troubleshooting_FAQ_300_QA.pdf",
        "IT_Troubleshooting_FAQ_300.xlsx"
    )