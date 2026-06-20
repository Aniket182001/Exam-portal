import os
from abc import ABC, abstractmethod
import openpyxl

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

def get_parser(filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext == '.xlsx':
        return ExcelParser()
    # elif ext == '.docx': return WordParser()
    # elif ext == '.pdf': return PDFParser()
    else:
        raise ValueError(f"Unsupported file format: {ext}")
