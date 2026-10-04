---
name: exam-question-importer
description: Extract multiple-choice or True/False exam questions from a source .docx file (where the correct answer is marked by highlight, font color, or a "Correct answer" label) and fill them into the AIQM exam_upload_template.xlsx (Question, Option A-G, Correct Option, Marks). Use this whenever the user uploads a Word document of exam questions (CKLM, CLP, MBB, LSS, ISO, or similar certification exams) alongside the exam_upload_template.xlsx and asks to convert, migrate, or prepare it for LMS upload.
---

# Exam Question Importer

Converts a source Word-document question bank into the AIQM LMS exam upload
spreadsheet format. This encodes the workflow used across the CKLM, CLP,
MBB, and ISO exam migrations: detect the correct answer from formatting
cues in the docx (never from re-deriving the "logically correct" answer),
and preserve exact question/option text.

## Core rules (do not deviate)

1. **Never infer or "correct" an answer based on subject-matter judgment.**
   If the source docx marks option B as correct, use B — even if option C
   seems like the better answer. Flag anything ambiguous for the user
   instead of guessing.
2. **Preserve text exactly.** No paraphrasing, no fixing typos, no
   normalizing punctuation in questions or options.
3. **Correct Option column takes the OPTION LETTER (A, B, C...)**, never
   the answer text itself.
4. **Always spot-check.** After generating output, list a few sample
   rows back to the user and flag any question where no correct answer
   was detected, or where formatting looked inconsistent with the rest
   of the file.

## Workflow

1. Open the source .docx and inspect how the correct answer is marked.
   Past AIQM files have used (in order of how common they are):
   - **Yellow highlight** on the correct option's text run.
   - **A distinct font color** on the question paragraph to mark it as a
     question (varies by file: green `1E8E3E`, red `D93025`/`FF0000`).
     Use this to segment questions from options, not to mark answers.
   - **A "Correct answer" label** followed by the answer text (Google
     Forms response exports) — this appears only when the original
     respondent picked the WRONG option; the initially-selected wrong
     option is shown in a dark/selected color (`202124`) vs. an
     unselected grey (`70757A`) for the other option.
   - **Fill-in-the-blank answers** (e.g., "enter the clause number") do
     not fit the MCQ template. Do not force these into it silently —
     tell the user and ask whether to (a) generate plausible wrong-option
     distractors to make it MCQ-compatible, or (b) leave them out.

2. Run `scripts/extract_exam.py` as a starting point — it implements the
   highlight/color heuristics above. It will likely need small tweaks per
   file (a new question-color, a new selected-color) since every source
   file has been slightly different so far. Treat it as scaffolding, not
   a black box: inspect a few raw paragraphs' run colors first
   (`python-docx`, `r.font.color.rgb`, `r.font.highlight_color`) to
   confirm which pattern this particular file uses before trusting the
   automated pass.

3. Fill `exam_upload_template.xlsx`:
   - Column A: Question
   - Columns B-H: Option A through G (as many as the question has)
   - Column I ("Correct Option"): the letter of the correct option
   - Column J ("Marks"): default to 1 unless told otherwise

4. Recalculate/validate the workbook, then report back:
   - Total question count
   - Any questions with no detected correct answer (list them)
   - Any duplicate questions found in the source (list them — these are
     often genuine duplicates in the source file, not extraction bugs)
   - Any fill-in-the-blank or non-MCQ sections that were excluded

## Known source-file quirks seen so far

- Some files split questions across a page break and lose highlight
  formatting on the correct option while keeping the distinct font color
  — cross-check with color, not just highlight, when a question comes up
  with zero or multiple flagged "correct" options.
- Some source files contain literal duplicate questions (typos in the
  original) — report them, don't silently dedupe.
- A trailing "WOULD YOU LIKE TO SUBMIT THE EXAM?" or similar UI paragraph
  sometimes gets extracted as a fake final question from Google Forms
  exports — exclude it.
