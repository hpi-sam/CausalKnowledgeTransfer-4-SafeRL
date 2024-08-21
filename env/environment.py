# env = SumoEnvironment(
#     net_file="nets/simple_intersection/simple_intersection.net.xml",
#     route_file="nets/simple_intersection/simple_intersection.rou.xml",
#     out_csv_name="outputs/simple_intersection/a2c_collision",
#     reward_fn=collision_penalty_reward,
#     single_agent=True,
#     use_gui=False,
#     sumo_warnings=False,
#     num_seconds=3600,
#     additional_sumo_cmd="--collision.check-junctions"
# )
import numpy as np
from gymnasium import spaces
from sumo_rl import SumoEnvironment, TrafficSignal, ObservationFunction


class FrictionObservationFunction(ObservationFunction):

    def __call__(self) -> np.ndarray:
        """Return the default observation function."""
        phase_id = [1 if self.ts.green_phase == i else 0 for i in range(self.ts.num_green_phases)] # one-hot encoding
        min_green = [0 if self.ts.time_since_last_phase_change < self.ts.min_green + self.ts.yellow_time else 1]
        density = self.ts.get_lanes_density()
        queue = self.ts.get_lanes_queue()
        observation = np.array(phase_id + min_green + density + queue, dtype=np.float32)
        return observation

    def observation_space(self):
        """Return the observation space."""
        return spaces.Box(
            # this is very tightly coupled to the __call__ function.
            # the formula is: number_of_green_phases + min_green + density + queue (Observation Vector length)
            low=np.zeros(self.ts.num_green_phases + 1 + 2 * len(self.ts.lanes), dtype=np.float32),
            high=np.ones(self.ts.num_green_phases + 1 + 2 * len(self.ts.lanes), dtype=np.float32),
        )


# Right now, this is just the standard reward function out of Sumo-RL
def default_reward_fn(traffic_signal: TrafficSignal) -> float:
    ts_wait = sum(traffic_signal.get_accumulated_waiting_time_per_lane()) / 100.0
    reward = traffic_signal.last_measure - ts_wait
    traffic_signal.last_measure = ts_wait
    return reward


def get_environment(net_file: str, route_file: str, out_csv_name: str, use_gui: bool, num_seconds: int, sumocfg_file: str) -> SumoEnvironment:
    """

    :param use_gui: bool
    :param net_file: str
    :param route_file: str
    :param out_csv_name: str
    :param num_seconds: int
    :param sumocfg_file: str
    :return:
    :rtype: SumoEnvironment
    """
    env = SumoEnvironment(
        net_file=net_file,
        route_file=route_file,
        out_csv_name=out_csv_name,
        use_gui=use_gui,
        begin_time=0,
        num_seconds=num_seconds,
        delta_time=5, # seconds between actions
        yellow_time=2, # duration of the yellow phase
        min_green=5, # minimum green time per phase
        single_agent=True,
        reward_fn=default_reward_fn, # define reward function
        observation_class=FrictionObservationFunction, # subject to change
        add_system_info=True,
        add_per_agent_info=True,
        sumo_seed='random',
        sumo_warnings=use_gui, # show warnings when gui is active
        additional_sumo_cmd=f'--configuration-file {sumocfg_file}',
    )

    return env