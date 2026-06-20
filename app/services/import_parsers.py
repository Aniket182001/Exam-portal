import os
from abc import ABC, abstractmethod
import openpyxl
import docx
import pypdf

class QuestionParser(ABC):
    @abstractmethod
    def parse(self, filepath):
        """
        Parses a file and returns a list of dictionaries with question data.
        Returns: list of dicts:
        [
            {
                "question": "Text",
                "options": ["A", "B", ...],
                "correct_option_index": 0,
                "marks": 1.0
            }
        ]
        """
        pass

class ExcelParser(QuestionParser):
    def parse(self, filepath):
        parsed_questions = []
        
        # Load the workbook and select the active worksheet
        wb = openpyxl.load_workbook(filepath, data_only=True)
        sheet = wb.active
        
        # Assume the first row is headers: Question, Option A, Option B, Option C, Option D, Correct Option, Marks
        # We start iterating from row 2
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not row:
                continue
                
            # Unpack assuming at least 9 columns (pad with None if fewer)
            row_data = list(row)
            while len(row_data) < 9:
                row_data.append(None)
                
            q_text = row_data[0]
            opt_a = row_data[1]
            opt_b = row_data[2]
            opt_c = row_data[3]
            opt_d = row_data[4]
            opt_e = row_data[5]
            opt_f = row_data[6]
            correct_opt = row_data[7]
            marks = row_data[8]
            
            # Skip empty rows (missing question text)
            if not q_text or not str(q_text).strip():
                continue
                
            # Collect valid options
            raw_options = [opt_a, opt_b, opt_c, opt_d, opt_e, opt_f]
            valid_options = []
            for opt in raw_options:
                if opt is not None and str(opt).strip():
                    valid_options.append(str(opt).strip())
                    
            if len(valid_options) < 2:
                continue # Skip if not enough valid options
                
            # Determine correct option index
            correct_index = 0
            if correct_opt is not None:
                correct_str = str(correct_opt).strip().lower()
                # If correct_opt is specified as A, B, C, D, E, F
                if len(correct_str) == 1 and correct_str in 'abcdef':
                    idx = ord(correct_str) - ord('a')
                    if idx < len(valid_options):
                        correct_index = idx
                else:
                    # Or if they pasted the exact text
                    for i, opt in enumerate(valid_options):
                        if opt.lower() == correct_str:
                            correct_index = i
                            break
                            
            # Determine marks
            try:
                marks_val = float(marks) if marks is not None else 1.0
            except ValueError:
                marks_val = 1.0
                
            parsed_questions.append({
                "question": str(q_text).strip(),
                "options": valid_options,
                "correct_option_index": correct_index,
                "marks": marks_val
            })
            
        return parsed_questions

class DocxParser(QuestionParser):
    def parse(self, filepath):
        parsed_questions = []
        doc = docx.Document(filepath)
        
        current_q = None
        
        def finalize_question():
            if current_q and len(current_q["options"]) >= 2:
                correct_idx = 0
                if current_q.get("correct_raw"):
                    ans = current_q["correct_raw"].strip().lower()
                    if len(ans) == 1 and ans in "abcdef":
                        idx = ord(ans) - ord('a')
                        if idx < len(current_q["options"]):
                            correct_idx = idx
                    else:
                        for i, opt in enumerate(current_q["options"]):
                            if opt.lower() == ans:
                                correct_idx = i
                                break
                
                parsed_questions.append({
                    "question": current_q["question"].strip(),
                    "options": current_q["options"][:6],
                    "correct_option_index": correct_idx,
                    "marks": current_q["marks"]
                })

        for p in doc.paragraphs:
            line = p.text.strip()
            if not line:
                continue
                
            line_lower = line.lower()
            
            if line_lower.startswith("question"):
                finalize_question()
                q_text = line
                if ":" in line:
                    q_text = line.split(":", 1)[1].strip()
                current_q = {
                    "question": q_text,
                    "options": [],
                    "correct_raw": None,
                    "marks": 1.0
                }
            elif current_q is not None:
                if len(line) >= 2 and line[0].upper() in "ABCDEF" and line[1] in ".) ":
                    opt_text = line[2:].strip()
                    current_q["options"].append(opt_text)
                elif line_lower.startswith("answer:") or line_lower.startswith("answer :"):
                    current_q["correct_raw"] = line.split(":", 1)[1].strip()
                elif line_lower.startswith("marks:") or line_lower.startswith("marks :"):
                    marks_str = line.split(":", 1)[1].strip()
                    try:
                        current_q["marks"] = float(marks_str)
                    except ValueError:
                        pass
                else:
                    # Append to question if options haven't started yet
                    if len(current_q["options"]) == 0 and current_q["correct_raw"] is None:
                        current_q["question"] += "\n" + line
                        
        finalize_question()
        return parsed_questions

class PdfParser(QuestionParser):
    def parse(self, filepath):
        parsed_questions = []
        
        with open(filepath, 'rb') as f:
            reader = pypdf.PdfReader(f)
            text = ""
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
                    
        current_q = None
        
        def finalize_question():
            if current_q and len(current_q["options"]) >= 2:
                correct_idx = 0
                if current_q.get("correct_raw"):
                    ans = current_q["correct_raw"].strip().lower()
                    if len(ans) == 1 and ans in "abcdef":
                        idx = ord(ans) - ord('a')
                        if idx < len(current_q["options"]):
                            correct_idx = idx
                    else:
                        for i, opt in enumerate(current_q["options"]):
                            if opt.lower() == ans:
                                correct_idx = i
                                break
                
                parsed_questions.append({
                    "question": current_q["question"].strip(),
                    "options": current_q["options"][:6],
                    "correct_option_index": correct_idx,
                    "marks": current_q["marks"]
                })

        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            line_lower = line.lower()
            
            if line_lower.startswith("question"):
                finalize_question()
                q_text = line
                if ":" in line:
                    q_text = line.split(":", 1)[1].strip()
                current_q = {
                    "question": q_text,
                    "options": [],
                    "correct_raw": None,
                    "marks": 1.0
                }
            elif current_q is not None:
                if len(line) >= 2 and line[0].upper() in "ABCDEF" and line[1] in ".) ":
                    opt_text = line[2:].strip()
                    current_q["options"].append(opt_text)
                elif line_lower.startswith("answer:") or line_lower.startswith("answer :"):
                    current_q["correct_raw"] = line.split(":", 1)[1].strip()
                elif line_lower.startswith("marks:") or line_lower.startswith("marks :"):
                    marks_str = line.split(":", 1)[1].strip()
                    try:
                        current_q["marks"] = float(marks_str)
                    except ValueError:
                        pass
                else:
                    # Append to question if options haven't started yet
                    if len(current_q["options"]) == 0 and current_q["correct_raw"] is None:
                        current_q["question"] += "\n" + line
                        
        finalize_question()
        return parsed_questions

def get_parser(filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext == '.xlsx':
        return ExcelParser()
    elif ext == '.docx':
        return DocxParser()
    elif ext == '.pdf':
        return PdfParser()
    else:
        raise ValueError(f"Unsupported file format: {ext}")
