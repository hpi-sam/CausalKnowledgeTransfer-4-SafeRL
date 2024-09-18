from pathlib import Path

import numpy as np
import pandas as pd
from stable_baselines3 import A2C

from env.SumoEnvironmentGenerator import SumoEnvironmentGenerator


class SumoTraceGenerator:
    def generate_traces(self, env_generator: SumoEnvironmentGenerator, path: Path, size: int, speed_loc: float,
                 friction_log: float,
                 speed_scale: float = 0.0, friction_scale: float = 0.0):
        rng = np.random.default_rng()
        speeds = rng.normal(speed_loc, speed_scale, size=size)
        frictions = rng.normal(friction_log, friction_scale, size=size)

        for experiment, values in enumerate(zip(speeds, frictions)):
            speed, friction_coefficient = values
            friction_coefficient = max(0.01, min(1, friction_coefficient))
            experiment_string = str(experiment).zfill(4)
            env = env_generator.get_generation_env(output_prefix=str(path.joinpath(experiment_string)))
            model = A2C(env=env, policy='MlpPolicy').load(Path().joinpath('env', 'training_data', 'a2c'))

            metadata = {'desiredSpeed': speed, 'friction': friction_coefficient}
            pd.DataFrame(metadata, index=['metadata']).to_xml(Path(path).joinpath(experiment_string + '_metadata.xml'))

            obs, info = env.reset()
            # Revisit Friction calculation
            vehicletype = env.sumo.vehicletype
            vehicletype.setMaxSpeed('carCustom', speed)
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

def main():
    from env.SumoEnvironmentGenerator import SumoEnvironmentGenerator
    from pathlib import Path
    from tqdm import tqdm
    import itertools

    environments = SumoEnvironmentGenerator(
        net_file=str(Path().joinpath('nets', 'simple_unprotected_right', 'simple_unprotected_right.net.xml')),
        route_file=str(Path().joinpath('nets', 'simple_unprotected_right', 'simple_unprotected_right.rou.xml')),
        sumocfg_file=str(Path().joinpath('nets', 'simple_unprotected_right', 'simple_unprotected_right.sumocfg')),
        duration=3600,
        learning_data_csv_name=str(Path().joinpath('env', 'training_data', 'output.csv')),
    )

    speeds = [30, 50, 80, 100, 130]
    frictions = [1.0, 0.75, 0.5, 0.25]

    experiments = list(itertools.product(speeds, frictions))

    for speed, friction in tqdm(experiments):
        simulation_output_path = Path().joinpath('data', f'a2c_{int(speed)}_f{friction}')
        Path.mkdir(simulation_output_path, parents=True, exist_ok=True)

        trace_generator = SumoTraceGenerator()
        trace_generator.generate_traces(
            env_generator=environments,
            path=simulation_output_path,
            size=100,
            speed_loc=float(speed) / 3.6,
            friction_log=friction,
            friction_scale=0.1
        )
if __name__ == '__main__':
    main()