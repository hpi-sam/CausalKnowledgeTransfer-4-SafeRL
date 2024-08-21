from stable_baselines3 import DQN
from sumo_rl import SumoEnvironment


def get_model(env: SumoEnvironment,_name: str="") -> DQN:
    model = DQN(
        env=env,
        policy='MlpPolicy',
        learning_rate=0.001,
        learning_starts=0,
        train_freq=1,
        target_update_interval=500,
        exploration_fraction=0.05,
        exploration_final_eps=0.01,
        verbose=1
    )

    return model
