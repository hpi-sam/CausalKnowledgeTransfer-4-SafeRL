from pathlib import Path

print("Begin training configuration")
import xml.etree.ElementTree as ET

INSERT_PROBABILITY = 0.1

config_directory = Path().joinpath('nets', '2lane_unprotected_right')
route_file = config_directory.joinpath('2lane_unprotected_right.rou.xml')
tree = ET.parse(route_file)
root = tree.getroot()

for flow in root.findall('flow'):
    match flow.attrib.get('id'):
        case 'southEast':
            flow.set('period', f"exp({INSERT_PROBABILITY})")
        case 'southNorth':
            flow.set('period', f"exp({INSERT_PROBABILITY})")
        case 'westEastTop':
            flow.set('period', f"exp({2 * INSERT_PROBABILITY})")
        case id if 'westEastBottom' in id:
            flow.set('end', str(float(flow.get('begin')) + 600))
            if float(flow.get('begin')) % 1200 == 0:
                flow.set('period', f"exp({1 * INSERT_PROBABILITY})")
            else:
                flow.set('period', f"exp({0.0001 * INSERT_PROBABILITY})")

tree.write(route_file, xml_declaration=True, encoding='UTF-8')
print("Finished training configuration")

print("Begin initiating environment")
from env.SumoEnvironmentGenerator import SumoEnvironmentGenerator
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

print("Begin training")
from stable_baselines3.a2c import A2C

env = environments.get_training_env()
model = A2C(
    env=env,
    policy='MlpPolicy',
    n_steps=100,
    verbose=1,
    tensorboard_log='dqn_sumo_tensorboard'
)

model_name = 'a2c_100step_2lane_1delta_minute_1traffic_50speed_server'
model.learn(1_000_000, tb_log_name=model_name)
model.save(Path().joinpath('env', 'training_data_2lane', model_name))
print("Finished training")
