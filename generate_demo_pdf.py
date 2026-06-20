from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

def create_pdf(filename):
    c = canvas.Canvas(filename, pagesize=letter)
    width, height = letter
    y = height - 50
    
    questions = [
        "Question 1: What is Python?",
        "A. Programming language",
        "B. Database",
        "C. Browser",
        "D. Operating system",
        "Answer: A",
        "Marks: 1",
        "",
        "Question 2: Which keyword defines a function?",
        "A) class",
        "B) while",
        "C) def",
        "D) import",
        "Answer: C",
        "Marks: 2",
        "",
        "Question 3: What is the largest planet?",
        "A. Earth",
        "B. Mars",
        "C. Jupiter",
        "Answer: Jupiter",
        "Marks: 1.5",
        "",
        "Question 4: Water boils at what temperature (Celsius)?",
        "A. 90",
        "B. 100",
        "C. 110",
        "D. 120",
        "Answer: B",
        "",
        "Question 5: Empty line test",
        "A. Opt A",
        "B. Opt B",
        "Answer: B",
        "Marks: 2"
    ]
    
    for line in questions:
        if y < 50:
            c.showPage()
            y = height - 50
        c.drawString(50, y, line)
        y -= 15
        
    c.save()

create_pdf("demo_import.pdf")
print("demo_import.pdf created successfully!")
