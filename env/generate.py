import numpy as np
import pandas as pd

print("Begin training configuration")
from pathlib import Path
import xml.etree.ElementTree as ET
import os
import subprocess

# Ensure SUMO_HOME is set
sumo_home = os.environ.get('SUMO_HOME')
if not sumo_home:
    raise EnvironmentError(
        "SUMO_HOME environment variable is not set. Please set it to your SUMO installation directory.")

# Generation Parameters
agents_path = Path().joinpath('env', 'training_data_2lane')
generation_combinations = [
    {'agent': agents_path.joinpath('a2c_s30_f1_new.zip'), 'speed': 8.33, 'friction': 1.0},
    {'agent': agents_path.joinpath('a2c_s80_f1.zip'), 'speed': 22.22, 'friction': 1.0},
]
RANDOM_FRICTION = True
RANDOM_SPEED = True
rng = np.random.default_rng()

for combination in generation_combinations:
    current_agent, current_speed, current_friction = combination.values()
    # Constants / Parameters
    SPEED = current_speed
    FRICTION = current_friction
    INSERT_PROBABILITY = 0.1
    DURATION = 3600
    REPEAT_PERIOD = 10
    DEFAULT_DECEL = 4.5
    DEFAULT_EMERGENCY_DECEL = 9.0

    # File Paths
    config_directory = Path('nets', '2lane_unprotected_right')
    config_files = {
        'netccfg_edges': config_directory.joinpath('netconfig', 'edges.edg.xml'),
        'netccfg': config_directory.joinpath('2lane_unprotected_right.netccfg'),
        'duarcfg': config_directory.joinpath('2lane_unprotected_right.duarcfg'),
        'net.xml': config_directory.joinpath('2lane_unprotected_right.net.xml'),
        'rou.xml': config_directory.joinpath('2lane_unprotected_right.rou.xml'),
        'routes.rou.xml': config_directory.joinpath('routes.rou.xml'),
        'config.rou.xml': config_directory.joinpath('config.rou.xml'),
        'experimental.rou.xml': config_directory.joinpath('experimental.rou.xml'),
    }
    findAllRoutes = Path(sumo_home, 'tools', 'findAllRoutes.py')
    vehicle2flow = Path(sumo_home, 'tools', 'route', 'vehicle2flow.py')


    # Update Friction Coefficients in Edge Configuration
    def update_friction_coefficients(file_path, friction):
        tree = ET.parse(file_path)
        root = tree.getroot()
        for param in root.findall(".//lane/param[@key='frictionCoefficient']"):
            param.set('value', str(friction))
        tree.write(file_path)


    update_friction_coefficients(config_files['netccfg_edges'], FRICTION)


    # Execute SUMO Tools using subprocess
    def run_command(command):
        result = subprocess.run(command, shell=True, text=True, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"Command failed: {command}\n{result.stderr}")
        print(result.stdout)


    run_command(f"netconvert --configuration-file {config_files['netccfg']}")
    run_command(f"python {findAllRoutes} -n {config_files['net.xml']} -o {config_files['routes.rou.xml']} "
                f"-s southJunction,westJunction -t junctionEast,junctionNorth")
    run_command(f"duarouter --configuration-file {config_files['duarcfg']}")
    run_command(f"python {vehicle2flow} {config_files['config.rou.xml']} -o {config_files['rou.xml']} "
                f"-e {DURATION} -r {REPEAT_PERIOD}")


    # Update Vehicle Configuration for Friction Adjusted Braking Distance
    def update_vehicle_type_parameters(file_path, speed, default_decel, default_emergency_decel, friction):
        tree = ET.parse(file_path)
        root = tree.getroot()
        for vType in root.findall('vType'):
            vClass = vType.attrib.get('vClass')
            if vClass and vClass != 'passenger':
                raise NotImplementedError("Check for non-passenger vehicle classes not implemented")
            vType.attrib.update({
                'maxSpeed': str(speed),
                'decel': str(default_decel * friction),
                'emergencyDecel': str(default_emergency_decel * friction),
            })
        tree.write(file_path, xml_declaration=True, encoding='UTF-8')


    update_vehicle_type_parameters(config_files['rou.xml'], SPEED, DEFAULT_DECEL, DEFAULT_EMERGENCY_DECEL, FRICTION)


    # Update Vehicle Flows for Forcing Unprotected Right Action
    def update_flows(file_path, insert_probability):
        tree = ET.parse(file_path)
        root = tree.getroot()
        for flow in root.findall('flow'):
            match flow.attrib.get('id'):
                case 'southEast':
                    flow.set('period', f"exp({insert_probability})")
                case 'southNorth':
                    flow.set('period', f"exp({insert_probability})")
                case 'westEastTop':
                    flow.set('period', f"exp({2 * insert_probability})")
                case id if 'westEastBottom' in id:
                    flow.set('end', str(float(flow.get('begin')) + 600))
                    if float(flow.get('begin')) % 1200 == 0:
                        flow.set('period', f"exp({1 * insert_probability})")
                    else:
                        flow.set('period', f"exp({0.0001 * insert_probability})")
        tree.write(file_path, xml_declaration=True, encoding='UTF-8')


    update_flows(config_files['rou.xml'], INSERT_PROBABILITY)
    print("Finished training configuration")

    print("Begin initiating environment")
    from SumoEnvironmentGenerator import SumoEnvironmentGenerator
    from pathlib import Path

    net_name = '2lane_unprotected_right'

    environments = SumoEnvironmentGenerator(
        net_file=str(Path().joinpath('nets', net_name, f'{net_name}.net.xml')),
        route_file=str(Path().joinpath('nets', net_name, f'{net_name}.rou.xml')),
        sumocfg_file=str(Path().joinpath('nets', net_name, f'{net_name}.sumocfg')),
        duration=3600,
        learning_data_csv_name=str(Path().joinpath('env', 'training_data', 'output.csv')),
    )
    print("Finished initiating environment")

    print(f"Begin generating with Speed {SPEED} and friction {FRICTION}")
    from stable_baselines3.a2c import A2C

    model = A2C.load(Path().joinpath(current_agent))

    for i in range(500):
        simulation_output_path = Path().joinpath('traces', current_agent.stem + "_random")
        Path.mkdir(simulation_output_path, parents=True, exist_ok=True)
        experiment_string = str(i).zfill(4)
        env = environments.get_generation_env(output_prefix=str(simulation_output_path.joinpath(experiment_string)))
        model.set_env(env)

        if RANDOM_FRICTION:
            friction_coefficient = rng.normal(rng.choice([0.25, 0.5, 0.75, 1]), 0.1)
            current_friction = max(0.01, min(1.0, friction_coefficient))
        if RANDOM_SPEED:
            possible_speeds = [8.33, 13.89, 22.22, 27.78, 36.11]
            possible_speeds.remove(current_speed)
            current_speed = rng.choice(possible_speeds)

        metadata = {'desiredSpeed': current_speed, 'friction': current_friction}
        pd.DataFrame(metadata, index=['metadata']).to_xml(
            Path(simulation_output_path).joinpath(experiment_string + '_metadata.xml'))

        obs, info = env.reset()
        vehicletype = env.sumo.vehicletype

        if RANDOM_SPEED:
            vehicletype.setMaxSpeed('carCustom', current_speed)

        if RANDOM_FRICTION:
            vehicletype.setDecel('carCustom', vehicletype.getDecel('carCustom') * current_friction)
            vehicletype.setEmergencyDecel('carCustom',
                                          vehicletype.getEmergencyDecel('carCustom') * current_friction)
            for traffic_signal in env.traffic_signals.values():
                for lane in traffic_signal.lanes:
                    traffic_signal.sumo.lane.setParameter(lane, 'frictionCoefficient', current_friction)

        done = False
        while not done:
            action, _state = model.predict(obs, deterministic=True)
            obs, _reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
        env.close()
