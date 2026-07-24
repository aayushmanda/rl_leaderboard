import numpy as np
from env import make_env, IndustrialInventoryEnv  # Imports directly from the env package


def run_public_evaluation_episodes(run_policy_fn, roll_number: str, num_episodes: int = 20) -> float:
    """
    Evaluates a student policy function across 20 standard public test episodes
    using their specific roll-number variant from the env package.
    
    Args:
        run_policy_fn (callable): Student function `run_policy(obs)` returning 3 actions.
        roll_number (str): Official student roll number.
        num_episodes (int): Number of evaluation episodes (Default: 20).
        
    Returns:
        float: Average cumulative total operational cost across all public episodes.
    """
    total_cost_all_episodes = 0.0
    BASE_PUBLIC_SEED = 1000  # Standard public evaluation baseline seed

    for ep in range(num_episodes):
        seed = BASE_PUBLIC_SEED + ep
        
        # Instantiate environment variant for this student via env.make_env
        env = make_env(roll_number, scenario_mode="random", domain_randomization=True)
        obs, _ = env.reset(seed=seed)
        
        episode_cost = 0.0
        done = False
        
        while not done:
            raw_action = run_policy_fn(obs)
            action_arr = np.asarray(raw_action, dtype=np.int64)

            # Convert order quantities (0..100) to internal action indices (0..10) if necessary
            if np.any(action_arr > 10):
                action_indices = IndustrialInventoryEnv.quantities_to_action_indices(action_arr)
            else:
                action_indices = action_arr

            obs, reward, terminated, truncated, info = env.step(action_indices)
            
            # Sum up daily operational costs
            episode_cost += info["costs"]["daily_total"]
            done = terminated or truncated

        total_cost_all_episodes += episode_cost

    avg_public_cost = total_cost_all_episodes / num_episodes
    return float(avg_public_cost)


if __name__ == "__main__":
    # Test script with a sample baseline policy
    def sample_heuristic_policy(obs):
        inv = obs["inventory"]
        return [3 if inv[0] < 50 else 0, 2 if inv[1] < 40 else 0, 4 if inv[2] < 60 else 0]

    test_roll = "DA24S016"
    print(f"Running self-test evaluation for roll number: {test_roll}...")
    test_cost = run_public_evaluation_episodes(sample_heuristic_policy, roll_number=test_roll, num_episodes=5)
    print(f"Self-Test Complete. Average Episode Cost: {test_cost:.2f}")