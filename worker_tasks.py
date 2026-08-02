import os
import json
from evaluator import run_evaluation_sandboxed
from database import fetch_submission_by_id, update_submission


def process_submission_task(submission_id):
    submission = fetch_submission_by_id(submission_id)
    if not submission:
        raise ValueError(f"Submission {submission_id} not found")

    submission_folder = submission['submission_folder']
    roll_number = submission['roll_number']

    if not os.path.isdir(submission_folder):
        update_submission(submission_id, 0.0, 'FAILED', 'Submission folder missing')
        return

    result = run_evaluation_sandboxed(submission_folder, roll_number)
    update_submission(
        submission_id,
        result.get('public_cost', 0.0),
        result.get('status', 'FAILED'),
        result.get('error', '')
    )
