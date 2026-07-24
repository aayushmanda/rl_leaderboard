import sqlite3

DB_NAME = 'leaderboard.db'

def get_db_connection():
    """Establishes connection to SQLite database with Row factory."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Automatically initializes required tables on application startup."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_email TEXT NOT NULL,
            roll_number TEXT NOT NULL,
            technique_name TEXT NOT NULL,
            submission_folder TEXT,
            public_avg_cost REAL DEFAULT 0.0,
            private_avg_cost REAL DEFAULT 0.0,
            status TEXT NOT NULL,
            error_message TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS deliverables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_email TEXT NOT NULL,
            roll_number TEXT UNIQUE NOT NULL,
            notebook_filename TEXT NOT NULL,
            report_filename TEXT NOT NULL,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def fetch_leaderboard():
    """Retrieves best score per technique per student and computes top 5 average."""
    conn = get_db_connection()
    query = """
        SELECT roll_number, technique_name, MIN(public_avg_cost) as best_cost
        FROM submissions
        WHERE status = 'SUCCESS'
        GROUP BY roll_number, technique_name
    """
    rows = conn.execute(query).fetchall()
    conn.close()

    student_scores = {}
    for row in rows:
        student_scores.setdefault(row['roll_number'], []).append(row['best_cost'])

    leaderboard_data = []
    for roll, costs in student_scores.items():
        sorted_costs = sorted(costs)[:5]
        avg_cost = sum(sorted_costs) / len(sorted_costs)
        leaderboard_data.append({
            'roll_number': roll,
            'technique_count': len(sorted_costs),
            'avg_cost': round(avg_cost, 2)
        })

    leaderboard_data.sort(key=lambda x: x['avg_cost'])
    return leaderboard_data

def fetch_user_history(roll_number):
    """Fetches user submission history and deliverable upload status."""
    conn = get_db_connection()
    history = conn.execute("""
        SELECT technique_name, public_avg_cost, status, error_message, submitted_at
        FROM submissions
        WHERE roll_number = ?
        ORDER BY submitted_at DESC
    """, (roll_number,)).fetchall()

    deliverable = conn.execute("""
        SELECT notebook_filename, report_filename, submitted_at
        FROM deliverables
        WHERE roll_number = ?
    """, (roll_number,)).fetchone()
    conn.close()

    return history, deliverable

def record_submission(email, roll, technique, folder, cost, status, error):
    """Saves model evaluation results into the submissions table."""
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO submissions (student_email, roll_number, technique_name, submission_folder, public_avg_cost, status, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (email, roll, technique, folder, cost, status, error))
    conn.commit()
    conn.close()

def record_deliverables(email, roll, nb_path, rp_path):
    """Upserts student notebook and PDF report deliverables."""
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO deliverables (student_email, roll_number, notebook_filename, report_filename)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(roll_number) DO UPDATE SET
            notebook_filename=excluded.notebook_filename,
            report_filename=excluded.report_filename,
            submitted_at=CURRENT_TIMESTAMP
    """, (email, roll, nb_path, rp_path))
    conn.commit()
    conn.close()