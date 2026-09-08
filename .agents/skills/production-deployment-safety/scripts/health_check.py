import sys
import os
import time
import subprocess
import urllib.request
import urllib.error

# Add parent dir to path so we can import app and extensions
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))

from app import create_app
from app.extensions import db
from sqlalchemy import text

def check_service():
    """Check if the systemd service is active (skip if we are not running systemd)"""
    # If the service doesn't exist, this will fail, which might happen in local dev.
    # We will only warn if we are on a system that seems to use systemctl for it.
    try:
        # Check if service file exists or systemctl knows about it
        result = subprocess.run(['systemctl', 'is-active', 'exam-portal.service'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("systemctl: exam-portal.service is active.")
            return True
        elif 'unknown' in result.stderr or 'could not be found' in result.stderr:
            print("systemctl: exam-portal.service not found. Skipping service check.")
            return True # Not a systemd environment
        else:
            print(f"systemctl: exam-portal.service is NOT active. Status: {result.stdout.strip()}")
            return False
    except FileNotFoundError:
        print("systemctl not found. Skipping service check.")
        return True

def check_http():
    """Check if the app is serving requests via HTTP"""
    url = os.environ.get('HEALTH_CHECK_URL', 'http://127.0.0.1:8000/')
    retries = 5
    
    for i in range(retries):
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    print(f"HTTP GET {url} successful (200 OK).")
                    return True
                else:
                    print(f"HTTP GET {url} returned status {response.status}.")
        except urllib.error.URLError as e:
            print(f"HTTP GET {url} failed: {e.reason}. Retrying...")
        except Exception as e:
            print(f"HTTP GET {url} unexpected error: {e}. Retrying...")
            
        time.sleep(2)
        
    print(f"HTTP health check failed after {retries} retries.")
    return False

def check_database():
    """Perform a smoke test query on the database to ensure it's accessible and schema is correct"""
    try:
        app = create_app()
        with app.app_context():
            with db.engine.connect() as conn:
                # Basic connection test
                conn.execute(text("SELECT 1"))
                
                # Check for the existence of the student_attempts table and company_name column
                # as a smoke test that the schema is correct.
                try:
                    conn.execute(text("SELECT company_name FROM student_attempts LIMIT 1"))
                except Exception as inner_e:
                    print(f"Database smoke test query failed: {inner_e}")
                    return False
                    
        print("Database smoke tests passed.")
        return True
    except Exception as e:
        print(f"Database connection or context error: {e}")
        return False

def run_health_check():
    print("Starting health checks...")
    
    if not check_service():
        return 1
        
    if not check_http():
        return 1
        
    if not check_database():
        return 1
        
    print("All health checks passed successfully.")
    return 0

if __name__ == "__main__":
    sys.exit(run_health_check())
