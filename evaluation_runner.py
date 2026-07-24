import sys
import os
import json
import importlib.util
import io
import numpy as np


def evaluate(submission_folder: str, roll_number: str) -> dict:
    policy_file = os.path.join(submission_folder, "policy.py")
    if not os.path.exists(policy_file):
        return {"status": "FAILED", "error": "policy.py not found in root of submitted package."}

    # Redirect standard stdout to prevent student print statements from corrupting stdout JSON
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()

    try:
        sys.path.insert(0, submission_folder)
        spec = importlib.util.spec_from_file_location("student_policy", policy_file)
        student_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(student_module)

        if not hasattr(student_module, 'run_policy'):
            sys.stdout = old_stdout
            return {"status": "FAILED", "error": "run_policy(observation) function missing in policy.py."}

        run_policy = student_module.run_policy

        # Dry-run test using observation space structure from IndustrialInventoryEnv
        mock_obs = {
            "inventory": np.array([100, 100, 100], dtype=np.int32),
            "arrival_pipeline": np.zeros((3, 4), dtype=np.int32),
            "demand_history": np.zeros((7, 3), dtype=np.int32),
            "day": np.array([1], dtype=np.int32),
            "capacity_utilisation": np.array([0.65], dtype=np.float32)
        }
        
        test_action = run_policy(mock_obs)
        if not isinstance(test_action, (list, tuple, np.ndarray)) or len(test_action) != 3:
            sys.stdout = old_stdout
            return {"status": "FAILED", "error": "run_policy must return a sequence of 3 order actions [q1, q2, q3]."}

    except Exception as exc:
        sys.stdout = old_stdout
        return {"status": "FAILED", "error": f"Import/Execution Error: {str(exc)}"}

    # Restore standard stdout before outputting JSON results
    sys.stdout = old_stdout

    # Run public evaluation episodes via evaluation.py
    try:
        from evaluation import run_public_evaluation_episodes
        public_cost = run_public_evaluation_episodes(run_policy, roll_number=roll_number, num_episodes=20)
        return {"status": "SUCCESS", "public_cost": float(public_cost), "error": ""}
    except Exception as exc:
        return {"status": "FAILED", "error": f"Runtime Evaluation Error: {str(exc)}"}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"status": "FAILED", "error": "Submission path or roll number argument missing."}))
        sys.exit(1)

    sub_folder = sys.argv[1]
    student_roll = sys.argv[2]
    
    result = evaluate(sub_folder, student_roll)
    print(json.dumps(result))