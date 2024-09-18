from pathlib import Path

import numpy as np
import pandas as pd
from stable_baselines3 import A2C

from env.SumoEnvironmentGenerator import SumoEnvironmentGenerator


class SumoTraceGenerator:
    def generate_traces(self, env_generator: SumoEnvironmentGenerator, path: Path, size: int, speed_loc: int,
                 friction_log: float,
                 speed_scale: float = 0.0, friction_scale: float = 0.0):
        rng = np.random.default_rng()
        speeds = rng.normal(speed_loc, speed_scale, size=size)
        frictions = rng.normal(friction_log, friction_scale, size=size)

        for experiment, values in enumerate(zip(speeds, frictions)):
            speed, friction_coefficient = values
            friction_coefficient = max(0, min(1, friction_coefficient))
            experiment_string = str(experiment).zfill(4)
            env = env_generator.get_generation_env(output_prefix=str(path.joinpath(experiment_string)))
            model = A2C(env=env, policy='MlpPolicy').load(Path().joinpath('env', 'training_data', 'a2c'))

            metadata = {'desiredSpeed': speed, 'friction': friction_coefficient}
            pd.DataFrame(metadata, index=['metadata']).to_xml(Path(path).joinpath(experiment_string + '_metadata.xml'))

            obs, info = env.reset()
            # Revisit Friction calculation
            vehicletype = env.sumo.vehicletype
            vehicletype.setAccel('carCustom', speed)
            vehicletype.setDecel('carCustom', vehicletype.getDecel('carCustom') * friction_coefficient)
            vehicletype.setEmergencyDecel('carCustom',
                                          vehicletype.getEmergencyDecel('carCustom') * friction_coefficient)
            for traffic_signal in env.traffic_signals.values():
                for lane in traffic_signal.lanes:
                    traffic_signal.sumo.lane.setParameter(lane, 'frictionCoefficient', friction_coefficient)

            done = False
            while not done:
                action, _state = model.predict(obs, deterministic=True)
                obs, _reward, terminated, truncated, info = env.step(action)
                done = terminated or truncated
            env.close()

        return 1
