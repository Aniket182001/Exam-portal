# AIQM Exam Portal Deployment Guide

Follow these steps to deploy the AIQM Exam Portal into a production environment utilizing PostgreSQL and Gunicorn.

## 1. Clone the Repository
Clone the repository to your production server:
```bash
git clone https://github.com/Aniket182001/Exam-portal.git
cd Exam-portal
```

## 2. Create a Virtual Environment
It is highly recommended to isolate the project dependencies:
```bash
python -m venv venv
```

Activate the virtual environment:
- On Linux/macOS: `source venv/bin/activate`
- On Windows: `venv\Scripts\activate`

## 3. Install Requirements
Install the required packages, including production dependencies like `gunicorn` and `psycopg2-binary`:
```bash
pip install -r requirements.txt
```

## 4. Environment Configuration
Create a `.env` file based on the provided example. This file manages sensitive configuration and the database connection:
```bash
cp .env.example .env
```
Edit the `.env` file with your specific credentials:
```env
SECRET_KEY=your_secure_random_secret_key
DATABASE_URL=postgresql://username:password@host:5432/database_name
```
*Note: If the `DATABASE_URL` is omitted, the application will gracefully fallback to a local SQLite database (`instance/exam_portal.db`).*

## 5. Initialize the Database
Run the Flask database migrations to initialize your PostgreSQL schema. This step creates all the necessary tables:
```bash
flask db upgrade
```

## 6. Run the Application Locally (For Testing)
To verify everything is configured correctly, start the Flask development server:
```bash
flask run
```
Access the application at `http://localhost:5000` to confirm functionality. Stop the server (`Ctrl+C`) before proceeding to production mode.

## 7. Run with Gunicorn (Production)
For a robust production deployment, use Gunicorn to serve the application:
```bash
gunicorn -w 4 -b 0.0.0.0:8000 run:app
```
This binds the application to port `8000` using 4 worker processes. It is recommended to run this command under a process manager like systemd or Supervisor, and place it behind a reverse proxy like Nginx.
