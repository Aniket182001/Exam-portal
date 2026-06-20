import openpyxl

wb = openpyxl.Workbook()
sheet = wb.active
sheet.title = "Questions"

# Headers
headers = ["Question", "Option A", "Option B", "Option C", "Option D", "Correct Option", "Marks"]
sheet.append(headers)

# Data
questions = [
    ["What is the capital of France?", "Berlin", "Madrid", "Paris", "Rome", "C", 1],
    ["Which planet is known as the Red Planet?", "Earth", "Mars", "Jupiter", "Saturn", "B", 1.5],
    ["What is the largest mammal?", "Elephant", "Blue Whale", "Giraffe", "Shark", "B", 2],
    ["Who wrote Hamlet?", "Charles Dickens", "William Shakespeare", "Mark Twain", "Jane Austen", "B", 1],
    ["Empty Row Test", None, None, None, None, None, None], # Should be skipped because options < 2
    [None, "A", "B", "C", "D", "A", 1], # Should be skipped because no question text
    ["Water boils at what temperature (Celsius)?", "90", "100", "110", "120", "100", 1], # Correct option specified by exact text
]

for q in questions:
    sheet.append(q)

wb.save("demo_import.xlsx")
print("demo_import.xlsx created successfully!")
