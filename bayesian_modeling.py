import warnings
from pathlib import Path
from typing import Optional, Dict, List

import arviz as az
import networkx as nx
import numpy as np
import pandas as pd
import pymc as pm
import pytensor
from matplotlib import pyplot as plt

from causal_discovery import run_causal_discovery
from utils import read_data

# Configure PyTensor
pytensor.config.cxx = ''
pytensor.config.floatX = "float64"


def generate_scm_layers(structural_causal_graph: nx.DiGraph) -> tuple[dict, dict]:
    """Generates layers and predecessors for nodes in a DAG.

    Args:
        structural_causal_graph: A directed acyclic graph (DAG).

    Returns:
        Tuple containing node layers and predecessors.
    """
    if not nx.is_directed_acyclic_graph(structural_causal_graph):
        raise ValueError("SCM must be a directed acyclic graph (DAG).")

    # Get topological generations (layers)
    layers = list(nx.topological_generations(structural_causal_graph))
    node_layers = {
        node: layer_number
        for layer_number, layer_nodes in enumerate(layers)
        for node in layer_nodes
    }
    predecessors = {
        node: list(structural_causal_graph.predecessors(node))
        for node in structural_causal_graph.nodes
    }
    return node_layers, predecessors


def _should_observe_node(effect: str, node: str, predecessors: List[str], outcome_variables: List[str]) -> bool:
    """Determines if a node should be modeled as observed."""
    if effect == 'total':
        return len(predecessors) > 0
    elif effect == 'direct':
        return node in outcome_variables
    raise ValueError(f"Invalid effect type: {effect}")


def _get_predictor(effect: str, predecessor: str, node_layers: Dict[str, int], independent_data: Dict,
                   obs_data: Dict):
    """Selects appropriate predictor variable based on effect type and node layer of predecessors"""
    if effect == 'direct':
        return independent_data[predecessor]
    return independent_data[predecessor] if node_layers[predecessor] == 0 else obs_data[predecessor]


def _get_beta_name(node, predecessors):
    current_predecessor_string = ', '.join(f'{index}:{name}' for index, name in enumerate(predecessors[node]))
    current_node_beta_name = f"{node} beta * ({current_predecessor_string})"
    return current_node_beta_name


def generate_scm_effect_model(data: pd.DataFrame, structural_causal_graph: nx.DiGraph,
                              effect: str = 'total') -> pm.Model:
    """Generates SCM model for total or direct effects."""
    if effect not in {'total', 'direct'}:
        raise ValueError("Effect must be 'total' or 'direct'")

    node_layers, predecessors = generate_scm_layers(structural_causal_graph)
    outcome_variables = [node for node, out_degree in structural_causal_graph.out_degree() if out_degree == 0]
    df_standardized = (data - data.mean()) / data.std()
    # values = {column: df_standardized[column].values for column in df_standardized.columns}

    with pm.Model() as model:
        independent_data: Dict[str, pm.Data] = {}
        observations: Dict[str, pm.Normal] = {}

        for node in sorted(node_layers, key=node_layers.get):
            should_observe = _should_observe_node(effect, node, predecessors[node], outcome_variables)

            if should_observe:
                # Create model variables
                alpha = pm.Normal(f"{node} alpha", mu=0, sigma=10)
                beta = pm.Normal(_get_beta_name(node, predecessors), mu=0, sigma=10, shape=len(predecessors[node]))
                # beta = pm.Normal(current_node_beta_name, mu=0, sigma=10, shape=len(predecessors[node]), dims="predictors")
                sigma = pm.HalfNormal(f"{node} sigma", sigma=1)

                # Create predictors list
                predictors = [
                    _get_predictor(effect, predecessor, node_layers, independent_data, observations)
                    for predecessor in predecessors[node]
                ]

                mu = alpha + pm.math.dot(beta, predictors)
                observations[node] = pm.Normal(f"{node}_obs", mu=mu, sigma=sigma, observed=df_standardized[node].values)
            else:
                independent_data[node] = pm.Data(f"{node}_data", df_standardized[node].values)

    return model


def _shorten_graph_nodes(graph: nx.DiGraph) -> nx.DiGraph:
    """Renames nodes in a graph copy according to specified abbreviation rules."""

    def _abbreviate(name: str) -> str:
        """Abbreviates variable names using first letter and uppercase letters."""
        if not name:
            return ""
        abbreviation = [name[0].lower()]
        for c in name[1:]:
            if c.isupper():
                abbreviation.append(c)
        return ''.join(abbreviation)

    def _process_name(name: str) -> str:
        """Processes a single node name through all transformation rules."""
        # Remove parentheses content
        clean_name = name.split('*')[0].strip()
        parts = clean_name.split('_') if '_' in clean_name else clean_name.split()

        if not parts:
            return name  # Return original if empty after cleaning

        # Process variable part
        variable = _abbreviate(parts[0])
        components = [variable]

        # Process remaining parts
        i = 1
        while i < len(parts):
            part = parts[i]
            if part == "alpha":
                components.append("α")
            elif part == "beta":
                components.append("β*")
            elif part == "sigma":
                components.append("σ")
            elif part in {"obs", "data"}:
                components.append(part)
            i += 1

        return ' '.join(components)

    # Create mapping and return relabeled graph
    return nx.relabel_nodes(graph, {n: _process_name(n) for n in graph.nodes}, copy=True)


def visualize_scm_model(model: pm.Model, title: str) -> None:
    """Visualizes a PyMC model as a network graph."""
    STYLE_OPTIONS = {
        'with_labels': True,
        'node_size': 2500,
        'node_color': 'skyblue',
        'edge_color': 'gray',
        'width': 3,
        'font_size': 14,
        'font_weight': 'bold',
        'arrowsize': 15
    }

    model_graph = pm.model_to_networkx(model)
    model_graph = _shorten_graph_nodes(model_graph)

    plt.figure(figsize=(20, 20))
    plt.title(title)
    pos = nx.planar_layout(model_graph, scale=1.5)
    nx.draw(model_graph, pos=pos, **STYLE_OPTIONS)
    plt.show()


def fit_model(model: pm.Model, cache_path: Optional[Path] = None) -> az.InferenceData:
    """Fits a model with optional caching."""
    if cache_path and not cache_path.exists():
        cache_path.parent.mkdir(parents=True, exist_ok=True)

    with model:
        if cache_path and cache_path.exists():
            warnings.warn(f"Loading cached results from {cache_path}", UserWarning, stacklevel=2)
            return az.from_netcdf(str(cache_path))

        idata = pm.sample()
        if cache_path:
            idata.to_netcdf(str(cache_path))
        return idata


def sample_posterior(model: pm.Model, idata: az.InferenceData, input_variables: List[str],
                     standardized_observation_data: pd.DataFrame) -> Dict[str, np.ndarray]:
    """Samples from the posterior predictive distribution."""
    with model:
        thinned_idata = idata.sel(chain=[0], draw=slice(None, None, 1000))

        # Match Observation Length to Original Input Length for Matrix Multiplication
        model_data_variables = list(idata.constant_data.data_vars.variables.mapping.keys())
        input_length = len(idata.constant_data[model_data_variables[0]])
        data_dict = {}
        observation_length = len(standardized_observation_data)
        number_of_repeats = (input_length + observation_length - 1) // observation_length
        for data_variable in input_variables:
            variable_values = standardized_observation_data[data_variable].values
            repeated_values = np.tile(variable_values, number_of_repeats)[:input_length]
            data_dict[f'{data_variable}_data'] = repeated_values

        pm.set_data(data_dict)

        try:
            predictions = pm.sample_posterior_predictive(thinned_idata, predictions=True, return_inferencedata=False)
        except ValueError as e:
            model.debug(verbose=True)
            raise e

    return predictions


def main():
    data_path = Path("structural_causal_models", "data", "scm_observational_data.csv")
    selected_columns = [
        "desiredSpeed",
        "friction",
        "speed",
        "waitingTime",
        "emergencyBraking",
        "collisions",
    ]
    data = read_data(data_path, selected_columns)
    independent_variables = ["desiredSpeed", "friction"]
    outcome_variables = ["waitingTime", "collisions"]

    causal_discovery = run_causal_discovery(data, independent_variables, outcome_variables,
                                            visualize=False)

    adjusted_graph = causal_discovery.causal_graph
    reversed_graph = causal_discovery.mediator_graph
    df = causal_discovery.traces

    scm_total_effect_model = generate_scm_effect_model(df, adjusted_graph, effect='total')
    scm_direct_effect_model = generate_scm_effect_model(df, adjusted_graph, effect='direct')
    scm_reverse_model = generate_scm_effect_model(df, reversed_graph, effect='total')

    full_model_path = Path().joinpath("structural_causal_models", "scm_total_effect.netcdf")
    trace_data = fit_model(scm_total_effect_model, cache_path=full_model_path)

    obs_path = Path().joinpath("distribution_shift", "traces", "scratch_s50_f0.5_shift_s50_f0.5", ".summary.csv")
    obs_data = read_data(obs_path, selected_columns)

    posterior = sample_posterior(scm_total_effect_model, trace_data, independent_variables, obs_data)
    print(posterior)
    print(scm_total_effect_model)

    visualize = True
    if visualize:
        visualize_scm_model(scm_total_effect_model, "Total Effect Model")
        visualize_scm_model(scm_reverse_model, "Reverse Effect Model")
        visualize_scm_model(scm_direct_effect_model, "Direct Effect Model")


if __name__ == "__main__":
    main()
