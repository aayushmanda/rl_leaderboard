import os
import zipfile
import json
import subprocess

ALLOWED_TECHNIQUES = [
    "Tabular Q-Learning",
    "Tabular SARSA",
    "TD(lambda) with Eligibility Traces",
    "Neural Network based Q-Learning",
    "Neural Network based SARSA",
    "REINFORCE with or without a baseline",
    "A2C",
    "A3C",
    "Proximal Policy Optimization (PPO)",
    "DQN",
    "Double DQN"
]

def safe_extract_zip(zip_filepath, extract_target):
    """Safely extracts zip files preventing Zip-Slip path traversal attacks."""
    with zipfile.ZipFile(zip_filepath, 'r') as zip_ref:
        for member in zip_ref.infolist():
            target_path = os.path.realpath(os.path.join(extract_target, member.filename))
            if not target_path.startswith(os.path.realpath(extract_target)):
                raise Exception("Security Error: Zip file contains malicious path traversal components.")
        zip_ref.extractall(extract_target)

def run_evaluation_sandboxed(submission_folder, roll_number):
    """Runs evaluation_runner.py in an isolated subprocess with a 60s hard timeout."""
    try:
        cmd = ["python3", "evaluation_runner.py", submission_folder, roll_number]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            err_msg = result.stderr.strip() or result.stdout.strip() or 'Runtime Execution Error'
            return {'public_cost': 0.0, 'status': 'FAILED', 'error': err_msg}

        raw_output = result.stdout.strip()
        if not raw_output:
            err_msg = result.stderr.strip() or 'Evaluation runner returned empty output.'
            return {'public_cost': 0.0, 'status': 'FAILED', 'error': err_msg}

        # Parse JSON output from the last formatted line of stdout
        for line in reversed(raw_output.splitlines()):
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue

        return {'public_cost': 0.0, 'status': 'FAILED', 'error': f"Invalid JSON output: {raw_output[:150]}"}

    except subprocess.TimeoutExpired:
        return {'public_cost': 0.0, 'status': 'FAILED', 'error': 'Execution Timed Out (Exceeded 60s limit).'}
    except Exception as exc:
        return {'public_cost': 0.0, 'status': 'FAILED', 'error': str(exc)}