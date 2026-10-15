import argparse
import os
import sys
import time

from docx import Document
from dotenv import load_dotenv
from openai import OpenAI, APITimeoutError, InternalServerError, RateLimitError
from pypdf import PdfReader

load_dotenv()
client = OpenAI(timeout=120)
MODEL = os.environ["MODEL_NAME"]

MAX_CHARS = 3000   # biggest piece of text sent in one request

SYSTEM_PROMPT = (
    "You summarize documents clearly and accurately. "
    "Only use information from the text provided."
)

# The three summary styles. Each one is just a different instruction.
STYLES = {
    "short": "Summarize the following text in 2 to 3 sentences:",
    "bullets": (
        "Summarize the following text as 5 to 7 bullet points. "
        "Start each bullet with '- ' and keep each one to a single line:"
    ),
    "detailed": (
        "Write a detailed summary of the following text in 3 to 4 short "
        "paragraphs, covering the main points and important details:"
    ),
}


# ---------- Reading files ----------

def read_text_file(path):
    """Read a text file and return its contents as a string."""
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_pdf(path):
    """Extract text from every page of a PDF."""
    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def read_docx(path):
    """Extract text from a Word document."""
    doc = Document(path)
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())


def read_file(path):
    """Pick the right reader based on the file type."""
    extension = os.path.splitext(path)[1].lower()

    if extension == ".pdf":
        return read_pdf(path)
    if extension == ".docx":
        return read_docx(path)
    if extension in (".txt", ".md"):
        return read_text_file(path)

    raise ValueError(
        f"Unsupported file type: '{extension}'. Use .txt, .md, .pdf, or .docx"
    )


# ---------- Summarizing ----------

def split_into_chunks(text, max_chars=MAX_CHARS):
    """Split text into chunks of at most max_chars, keeping paragraphs together."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current = ""

    for para in paragraphs:
        # A single paragraph that is too big gets cut into pieces
        while len(para) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(para[:max_chars])
            para = para[max_chars:]
        if not para:
            continue

        if current and len(current) + 2 + len(para) > max_chars:
            chunks.append(current)
            current = para
        elif current:
            current += "\n\n" + para
        else:
            current = para

    if current:
        chunks.append(current)
    return chunks


def ask_model(instruction, text, retries=5, max_tokens=3000):
    """Send one request to the model. Retry with a pause if it is busy or returns nothing."""
    for attempt in range(1, retries + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"{instruction}\n\n{text}"},
                ],
                max_tokens=max_tokens,
            )
            reply = (response.choices[0].message.content or "").strip()
            if reply:
                return reply
            print(f"    (empty reply, retry {attempt}/{retries})")
        except (APITimeoutError, InternalServerError, RateLimitError):
            print(f"    (model busy, retry {attempt}/{retries})")
        time.sleep(2 * attempt)   # wait longer after each failure: 2s, 4s, 6s...
    raise RuntimeError("The model did not return a summary after several tries.")

def summarize_long(text, style="short", on_progress=print):
    """Summarize text of any length in the chosen style.

    on_progress is a function that receives status messages.
    It defaults to print, so the command-line version works as before.
    """
    # Short enough: one request, using the chosen style
    if len(text) <= MAX_CHARS:
        return ask_model(STYLES[style], text)

    # Too long: summarize each chunk, then summarize the summaries
    chunks = split_into_chunks(text)
    on_progress(f"Long text: split into {len(chunks)} parts.")

    partial_summaries = []
    for i, chunk in enumerate(chunks, start=1):
        on_progress(f"Summarizing part {i} of {len(chunks)}...")
        partial_summaries.append(
            ask_model("Summarize this part of a longer document in 2 to 3 sentences:", chunk)
        )

    on_progress("Combining the part summaries...")
    combined = "\n\n".join(partial_summaries)
    return summarize_long(combined, style, on_progress)   # the style is applied at the final step


# ---------- Command line ----------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Summarize a .txt, .md, .pdf, or .docx file with AI."
    )
    parser.add_argument("file", help="path to the file to summarize")
    parser.add_argument(
        "--style",
        choices=list(STYLES),
        default="short",
        help="short (default), bullets, or detailed",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="also save the summary to <filename>_summary.txt",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    path = args.file

    try:
        text = read_file(path)
    except FileNotFoundError:
        print(f"File not found: {path}")
        sys.exit(1)
    except ValueError as e:
        print(e)
        sys.exit(1)

    if not text.strip():
        print("No text found in the file. (A scanned PDF is an image and has no selectable text.)")
        sys.exit(1)

    print(f"Read {len(text):,} characters. Style: {args.style}. Summarizing...\n")
    try:
        summary = summarize_long(text, args.style)
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print("\n=== SUMMARY ===")
    print(summary)

    if args.save:
        save_path = os.path.splitext(path)[0] + "_summary.txt"
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(summary + "\n")
        print(f"\nSaved to {save_path}")


if __name__ == "__main__":
    main()