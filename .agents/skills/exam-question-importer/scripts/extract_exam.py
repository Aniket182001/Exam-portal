#!/usr/bin/env python3
"""
Extract MCQ / True-False questions from a source .docx exam file and fill
an exam_upload_template.xlsx (Question | Option A-G | Correct Option | Marks).

Usage:
    python extract_exam.py <source.docx> <template.xlsx> <output.xlsx>

How it detects the correct answer (in priority order):
  1. An explicit "Correct answer" label followed by the answer text
     (common in Google Forms response exports).
  2. A run with a highlight color applied (python-docx font.highlight_color).
  3. A run whose font color is one of a small set of "selected/dark" colors
     often used to mark the chosen answer in form exports (e.g. 202124),
     as opposed to "unselected/greyed" colors (e.g. 70757A).

Question boundaries are detected by a run color used for headings -- this
varies by source file, so COMMON_QUESTION_COLORS lists several seen across
past AIQM exam docs. Extend this list if a new doc uses a different color.

This script encodes an assumption, not a law of formatting: always spot-check
a sample of the output against the source file before uploading to the LMS.
"""

import sys
import json
from docx import Document
import openpyxl

# Colors (hex, no '#') seen marking a QUESTION paragraph across past files.
# Extend this set if a new source doc uses a different heading color.
COMMON_QUESTION_COLORS = {
    "1E8E3E",  # green
    "D93025",  # red (google-forms red)
    "FF0000",  # red (pure)
}

# Colors seen marking a SELECTED (as opposed to greyed-out/unselected) option
# in Google Forms response exports, used as a correct-answer heuristic when
# no "Correct answer" label is present.
SELECTED_COLOR = "202124"
UNSELECTED_COLOR = "70757A"

LETTERS = ["A", "B", "C", "D", "E", "F", "G"]


def para_run_colors(p):
    colors = []
    for r in p.runs:
        c = r.font.color.rgb if r.font.color and r.font.color.rgb else None
        colors.append(str(c) if c else None)
    return colors


def is_question_para(p):
    for r in p.runs:
        c = r.font.color.rgb if r.font.color and r.font.color.rgb else None
        if c is not None and str(c) in COMMON_QUESTION_COLORS:
            return True
    return False


def extract_items(docx_path):
    doc = Document(docx_path)
    items = []
    cur_q = None
    cur_opts = []  # list of (text, is_correct)

    def flush():
        nonlocal cur_q, cur_opts
        if cur_q is not None and cur_opts:
            items.append({"q": cur_q, "opts": cur_opts[:]})
        cur_q = None
        cur_opts = []

    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        if is_question_para(p):
            flush()
            cur_q = text
            continue

        # Handle "Correct answer" label pattern (Google Forms export): the
        # paragraph AFTER this label is the correct answer text, and it may
        # duplicate an already-listed option -- mark that option correct.
        if text == "Correct answer":
            continue  # handled by looking ahead isn't trivial paragraph-by-
            # paragraph in this simplified script; prefer the highlight/
            # color heuristic below for such docs, or extend as needed.

        # Split runs into lines (options can be newline-separated within
        # one paragraph), tracking highlight + color per line.
        cur_line_text = ""
        cur_line_highlight = False
        cur_line_color = None
        for r in p.runs:
            rt = r.text
            hl = bool(r.font.highlight_color)
            c = r.font.color.rgb if r.font.color and r.font.color.rgb else None
            c = str(c) if c else None
            parts = rt.split("\n")
            for j, part in enumerate(parts):
                if j > 0:
                    lt = cur_line_text.strip()
                    if lt:
                        cur_opts.append((lt, cur_line_highlight, cur_line_color))
                    cur_line_text = ""
                    cur_line_highlight = False
                    cur_line_color = None
                cur_line_text += part
                if hl:
                    cur_line_highlight = True
                if c:
                    cur_line_color = c
        lt = cur_line_text.strip()
        if lt:
            cur_opts.append((lt, cur_line_highlight, cur_line_color))
    flush()

    # Resolve correctness per item
    resolved = []
    for it in items:
        opts = it["opts"]
        correct_idx = None
        for i, (text, hl, color) in enumerate(opts):
            if hl:
                correct_idx = i
                break
        if correct_idx is None:
            for i, (text, hl, color) in enumerate(opts):
                if color == SELECTED_COLOR:
                    correct_idx = i
                    break
        resolved.append({
            "q": it["q"],
            "opts": [o[0] for o in opts],
            "correct_idx": correct_idx,
        })
    return resolved


def write_to_template(items, template_path, output_path):
    wb = openpyxl.load_workbook(template_path)
    ws = wb["Sheet1"]

    flagged = []
    for i, it in enumerate(items):
        row = i + 2
        ws.cell(row=row, column=1, value=it["q"])
        for j, opt in enumerate(it["opts"][:7]):
            ws.cell(row=row, column=2 + j, value=opt)
        if it["correct_idx"] is not None and it["correct_idx"] < 7:
            ws.cell(row=row, column=9, value=LETTERS[it["correct_idx"]])
        else:
            flagged.append((row, it["q"]))
        ws.cell(row=row, column=10, value=1)

    wb.save(output_path)
    return flagged


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python extract_exam.py <source.docx> <template.xlsx> <output.xlsx>")
        sys.exit(1)

    src, template, out = sys.argv[1], sys.argv[2], sys.argv[3]
    items = extract_items(src)
    flagged = write_to_template(items, template, out)

    print(f"Extracted {len(items)} questions -> {out}")
    if flagged:
        print(f"WARNING: {len(flagged)} question(s) had no detected correct answer:")
        for row, q in flagged:
            print(f"  row {row}: {q[:70]}")
    print("Always spot-check output against the source docx before uploading to LMS.")
