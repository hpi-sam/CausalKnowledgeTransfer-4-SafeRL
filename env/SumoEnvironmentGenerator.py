import numpy as np
from gymnasium import spaces
from sumo_rl import SumoEnvironment, TrafficSignal, ObservationFunction


class SumoEnvironmentGenerator:

    def __init__(self, net_file: str, route_file: str, sumocfg_file: str, duration: int, learning_data_csv_name: str):
        self.net_file = net_file
        self.route_file = route_file
        self.sumocfg_file = sumocfg_file
        self.duration = duration
        self.learning_data_csv_name = learning_data_csv_name

    def get_training_env(self):
        return self._get_environment(self.net_file, self.route_file, self.sumocfg_file, False, self.duration,
                                     out_csv_name=self.learning_data_csv_name)

    def get_generation_env(self, output_prefix: str):
        return self._get_environment(self.net_file, self.route_file, self.sumocfg_file, False, self.duration,
                                     output_prefix=output_prefix)

    def get_demonstration_env(self):
        return self._get_environment(self.net_file, self.route_file, self.sumocfg_file, True, self.duration)

    @staticmethod
    def _reward_fn(traffic_signal: TrafficSignal) -> float:
        ts_wait = sum(traffic_signal.get_accumulated_waiting_time_per_lane()) / 100.0
        reward = traffic_signal.last_measure - ts_wait
        traffic_signal.last_measure = ts_wait
        return reward

    @staticmethod
    def _get_environment(net_file: str, route_file: str, sumocfg_file: str, use_gui: bool, num_seconds: int,
                         out_csv_name: str = None, output_prefix: str = ''):

        sumo_cmd_options = {'--configuration-file': sumocfg_file}
        if output_prefix:
            sumo_cmd_options['--output-prefix'] = output_prefix + '_'
            sumo_cmd_options['--statistic-output'] = 'statistics.xml'
            sumo_cmd_options['--collision-output'] = 'collisions.xml'
        sumo_cmd = ' '.join(key + " " + value for key, value in sumo_cmd_options.items())

        env: SumoEnvironment = SumoEnvironment(
            net_file=net_file,
            route_file=route_file,
            out_csv_name=out_csv_name,
            use_gui=use_gui,
            begin_time=0,
            num_seconds=num_seconds,
            delta_time=5,  # seconds between actions
            yellow_time=2,  # duration of the yellow phase
            min_green=5,  # minimum green time per phase
            single_agent=True,
            reward_fn=SumoEnvironmentGenerator._reward_fn,  # define reward function
            observation_class=FrictionObservationFunction,  # subject to change
            add_system_info=True,
            add_per_agent_info=True,
            sumo_seed='random',
            sumo_warnings=use_gui,  # show warnings when gui is active
            additional_sumo_cmd=sumo_cmd,
        )

        return env


class FrictionObservationFunction(ObservationFunction):

    def __call__(self) -> np.ndarray:
        phase_id = [1 if self.ts.green_phase == i else 0 for i in range(self.ts.num_green_phases)]  # one-hot encoding
        min_green = [0 if self.ts.time_since_last_phase_change < self.ts.min_green + self.ts.yellow_time else 1]
        density = self.ts.get_lanes_density()
        queue = self.ts.get_lanes_queue()
        lane_friction = [self.ts.sumo.lane.getFriction(lane) for lane in self.ts.lanes]
        lane_mean_speeds = [self.ts.sumo.lane.getLastStepMeanSpeed(lane) for lane in self.ts.lanes]
        observation = np.array(phase_id + min_green + density + queue + lane_friction + lane_mean_speeds,
                               dtype=np.float32)
        return observation

    def observation_space(self):
        return spaces.Box(
            # this is very tightly coupled to the __call__ function.
            # the formula is: number_of_green_phases + min_green + density + queue + lane_friction + lane_mean_speeds (Observation Vector length)
            low=np.zeros(self.ts.num_green_phases + 1 + 4 * len(self.ts.lanes), dtype=np.float32),
            high=np.ones(self.ts.num_green_phases + 1 + 4 * len(self.ts.lanes), dtype=np.float32),
        )
