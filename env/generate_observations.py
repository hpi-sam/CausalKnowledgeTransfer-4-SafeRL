import glob
import xml.etree.ElementTree as ElementTree
from statistics import mean

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
agents_path = Path().joinpath('env', 'agents')
rng = np.random.default_rng()
SPEED = float(80) / 3.6
FRICTION = 0.8

# Constants / Parameters
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
from stable_baselines3.a2c import A2C

model_name = 'scratch_s80_f1'
model = A2C.load(agents_path.joinpath(model_name + '.zip'))
simulation_output_path = Path().joinpath('distribution_shift', 'traces',
                                         model_name + f"_shift_s{int(SPEED * 3.6)}_f{FRICTION}.xml")

print(f"Begin generating with Speed {SPEED} and friction {FRICTION}")

for i in range(30):

    current_friction = FRICTION
    current_speed = SPEED

    Path.mkdir(simulation_output_path, parents=True, exist_ok=True)
    experiment_string = str(i).zfill(4)
    env = environments.get_generation_env(output_prefix=str(simulation_output_path.joinpath(experiment_string)))
    model.set_env(env)

    metadata = {'desiredSpeed': current_speed, 'friction': current_friction}
    pd.DataFrame(metadata, index=['metadata']).to_xml(
        Path(simulation_output_path).joinpath(experiment_string + '_metadata.xml'))

    obs, info = env.reset()
    vehicletype = env.sumo.vehicletype

    done = False
    while not done:
        action, _state = model.predict(obs, deterministic=True)
        obs, _reward, terminated, truncated, info = env.step(action)
        done = terminated or truncated
    env.close()

statistics_files = glob.glob(str(simulation_output_path.joinpath('*_statistics.xml')))
ids = [path.split('/')[-1].split('_')[0] for path in statistics_files]

data = []
for id in ids:
    statistics_file = simulation_output_path.joinpath(id + '_statistics.xml')
    collisions_file = simulation_output_path.joinpath(id + '_collisions.xml')
    # ssm_file = simulation_output_path.joinpath(id + '_ssm.xml')
    metadata_file = simulation_output_path.joinpath(id + '_metadata.xml')
    tripinfo_file = simulation_output_path.joinpath(id + '_tripinfo.xml')
    statistics_xml = ElementTree.parse(statistics_file).getroot()
    collisions_xml = ElementTree.parse(collisions_file).getroot()
    # ssm_xml = ElementTree.parse(ssm_file).getroot()
    metadata_xml = ElementTree.parse(metadata_file).getroot()
    tripinfo_xml = ElementTree.parse(tripinfo_file).getroot()

    row = {
        'agent': model_name,
        'shift': f's{int(SPEED*3.6)}_f{FRICTION}',
        'index': int(id),
        'desiredSpeed': float(metadata_xml.find('.//desiredSpeed').text),
        'friction': float(metadata_xml.find('.//friction').text)
    }

    for key, value in {**statistics_xml.find('vehicleTripStatistics').attrib,
                       **statistics_xml.find('safety').attrib}.items():
        match key:
            case 'count' | 'emergencyStops' | 'emergencyBraking':
                row[key] = int(value)
            case 'collisions':
                row[key] = int(value)
                row['rearEndCollisions'] = sum(
                    'southEast' in child.attrib.get('victim') for child in collisions_xml)
                row['lateralCollisions'] = sum(
                    'southEast' in child.attrib.get('collider') for child in collisions_xml)
                row[key] = row['rearEndCollisions'] + row['lateralCollisions']
            case _:
                row[key] = float(value)

    waiting_times = [float(tripinfo.attrib.get('waitingTime')) for tripinfo in tripinfo_xml.findall('tripinfo')]
    average_waiting_time = mean(waiting_times)
    row['waitingTime'] = average_waiting_time

    data.append(row)

    df = pd.DataFrame(data)
    df.to_csv(simulation_output_path.joinpath('.summary.csv'), index=False)
