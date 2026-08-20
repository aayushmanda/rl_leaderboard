import os
import time
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename

from env import normalize_roll_number  # Utility from official env package
from database import (
    init_db,
    fetch_leaderboard,
    fetch_user_history,
    record_initial_submission,
    update_submission,
    record_deliverables
)
from evaluator import ALLOWED_TECHNIQUES, safe_extract_zip
from redis import Redis
from rq import Queue

# Environment setup
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# OAuth library loading
try:
    from authlib.integrations.flask_client import OAuth
except ImportError:
    class OAuth:
        def __init__(self, app): pass
        def register(self, **kwargs): pass
from datetime import datetime
from zoneinfo import ZoneInfo

DEADLINE = datetime(2026, 8, 31, 0, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata"))

def submissions_open():
    return datetime.now(ZoneInfo("Asia/Kolkata")) < DEADLINE

ALLOWED_DOMAINS = {'smail.iitm.ac.in', 'iitm.ac.in'}

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "")

app.config['UPLOAD_FOLDER'] = 'submissions'
app.config['DELIVERABLES_FOLDER'] = 'deliverables'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB Max Upload Limit

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['DELIVERABLES_FOLDER'], exist_ok=True)
os.makedirs('data', exist_ok=True)

REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
redis_conn = Redis.from_url(REDIS_URL)
submission_queue = Queue('submission_queue', connection=redis_conn)

# Initialize Database Schema
init_db()

# OAuth Configuration
RAW_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
RAW_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')

GOOGLE_CLIENT_ID = RAW_CLIENT_ID.strip('\'" \\\n\r')
GOOGLE_CLIENT_SECRET = RAW_CLIENT_SECRET.strip('\'" \\\n\r')

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = os.environ.get('OAUTHLIB_INSECURE_TRANSPORT', '0')

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

def extract_roll_from_email(email):
    raw_roll = email.split('@')[0]
    try:
        return normalize_roll_number(raw_roll)
    except ValueError:
        return raw_roll.upper()

# --- Authentication Routes ---

@app.route('/login')
def login():
    # Force Google to present the account selection prompt on every login attempt
    return google.authorize_redirect(
        url_for('auth_callback', _external=True),
        prompt='select_account'
    )

@app.route('/auth/callback')
def auth_callback():
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo') or google.parse_id_token(token, nonce=None)

        if not user_info or 'email' not in user_info:
            flash("Failed to retrieve user email from Google.", "error")
            return redirect(url_for('leaderboard'))

        email = user_info['email'].lower()
        domain = email.split('@')[-1]

        if domain not in ALLOWED_DOMAINS:
            flash(f"Access restricted! Please log in with an official IIT Madras email (@smail.iitm.ac.in). Received: {email}", "error")
            return redirect(url_for('leaderboard'))

        session['user'] = {
            'email': email,
            'name': user_info.get('name', ''),
            'roll_number': extract_roll_from_email(email)
        }
        flash(f"Welcome, {session['user']['name']} ({session['user']['roll_number']})!", "success")
    except Exception as exc:
        flash(f"Authentication error: {exc}", "error")

    return redirect(url_for('leaderboard'))

@app.route('/logout')
def logout():
    session.pop('user', None)
    flash("You have been logged out.", "success")
    return redirect(url_for('leaderboard'))

# --- Main Routes ---

@app.route('/')
def leaderboard():
    leaderboard_data = fetch_leaderboard()
    return render_template('index.html', 
                           leaderboard=leaderboard_data, 
                           techniques=ALLOWED_TECHNIQUES,
                           current_user=session.get('user'))

@app.route('/dashboard')
def dashboard():
    user = session.get('user')
    if not user:
        flash("Please log in to view your dashboard.", "error")
        return redirect(url_for('leaderboard'))

    history, deliverable = fetch_user_history(user['roll_number'])
    return render_template('dashboard.html', 
                           history=history, 
                           deliverable=deliverable, 
                           current_user=user)

@app.route('/submit', methods=['POST'])
def submit():
    if not submissions_open():
        flash("Submissions are closed. Deadline was 30th August, 2026.", "error")
        return redirect(url_for('leaderboard'))
    user = session.get('user')
    if not user:
        flash("You must be logged in with an IITM email to submit.", "error")
        return redirect(url_for('leaderboard'))

    technique_name = request.form.get('technique_name')
    file = request.files.get('file')

    if not file or technique_name not in ALLOWED_TECHNIQUES:
        flash("Invalid submission details or technique.", "error")
        return redirect(url_for('leaderboard'))

    roll = user['roll_number']
    timestamp = str(int(time.time()))
    sub_folder = os.path.join(app.config['UPLOAD_FOLDER'], roll, secure_filename(technique_name), timestamp)
    os.makedirs(sub_folder, exist_ok=True)

    filename = secure_filename(file.filename)
    upload_path = os.path.join(sub_folder, filename)
    file.save(upload_path)

    try:
        if filename.endswith('.zip'):
            safe_extract_zip(upload_path, sub_folder)
        elif filename.endswith('.py'):
            os.rename(upload_path, os.path.join(sub_folder, "policy.py"))
        else:
            flash("Invalid file format! Please upload a .zip or .py file.", "error")
            return redirect(url_for('dashboard'))

        submission_id = record_initial_submission(
            user['email'], roll, technique_name, sub_folder
        )
        submission_queue.enqueue(
            'worker_tasks.process_submission_task',
            submission_id,
            job_timeout=900
        )
        flash(
            "Your submission has been queued for evaluation. "
            "Results will appear on your dashboard once processing completes.",
            "info"
        )
    except Exception as exc:
        if 'submission_id' in locals():
            update_submission(submission_id, 0.0, 'FAILED', f"Queue error: {exc}")
        flash(f"Submission error: {str(exc)}", "error")

    return redirect(url_for('dashboard'))

@app.route('/submit_deliverables', methods=['POST'])
def submit_deliverables():
    if not submissions_open():
        flash("Submissions are closed. Deadline was 30th August, 2026.", "error")
        return redirect(url_for('leaderboard'))
    user = session.get('user')
    if not user:
        flash("You must be logged in to submit deliverables.", "error")
        return redirect(url_for('dashboard'))

    notebook_file = request.files.get('notebook')
    report_file = request.files.get('report')

    if not notebook_file or not report_file:
        flash("Both Notebook (.ipynb) and Report (.pdf) are required.", "error")
        return redirect(url_for('dashboard'))

    if not notebook_file.filename.endswith('.ipynb') or not report_file.filename.endswith('.pdf'):
        flash("Invalid file types! Notebook must be .ipynb and Report must be .pdf.", "error")
        return redirect(url_for('dashboard'))

    roll = user['roll_number']
    user_dir = os.path.join(app.config['DELIVERABLES_FOLDER'], roll)
    os.makedirs(user_dir, exist_ok=True)

    nb_path = os.path.join(user_dir, secure_filename(f"{roll}_notebook.ipynb"))
    rp_path = os.path.join(user_dir, secure_filename(f"{roll}_report.pdf"))

    notebook_file.save(nb_path)
    report_file.save(rp_path)

    record_deliverables(user['email'], roll, nb_path, rp_path)

    flash("Final deliverables (Notebook & Report) uploaded successfully!", "success")
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    # Local dev only; Docker/Oracle should run via gunicorn
    app.run(debug=True, host='0.0.0.0', port=5000)
