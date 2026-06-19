import os
import webbrowser
from threading import Timer
from dotenv import load_dotenv

# Load environment variables from .env file (required for Gunicorn)
load_dotenv()

from app import create_app

app = create_app()

def open_browser():
    webbrowser.open("http://127.0.0.1:5000")

if __name__ == "__main__":
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        Timer(1, open_browser).start()
    app.run(debug=True)