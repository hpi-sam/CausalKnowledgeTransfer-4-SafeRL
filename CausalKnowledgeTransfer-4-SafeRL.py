import pytensor
from pathlib import Path
import pandas as pd
import pymc as pm
import arviz as az
import networkx as nx
from matplotlib import pyplot as plt
from pymc_experimental.model_builder import ModelBuilder

pytensor.config.cxx = ''
pytensor.config.floatX = "float64"


def generate_scm_layers(structural_causal_graph: nx.DiGraph) -> [dict, dict]:
    assert nx.is_directed_acyclic_graph(structural_causal_graph)
    node_layers = {node: 0 for node in structural_causal_graph.nodes}
    predecessors = {node: list(structural_causal_graph.predecessors(node)) for node in structural_causal_graph.nodes}
    visited = set(node for node, predecessor_nodes in predecessors.items() if len(predecessor_nodes) == 0)

    # Find layers for each node
    current_layer = max(node_layers.values()) + 1
    while len(visited) < len(structural_causal_graph.nodes):
        unprocessed = set(structural_causal_graph.nodes) - visited
        current_nodes = [node for node in unprocessed if visited.issuperset(predecessors[node])]
        for node in current_nodes:
            node_layers[node] = current_layer
        visited.update(current_nodes)
        current_layer += 1
    return node_layers, predecessors


def generate_scm_effect_model(data: pd.DataFrame, structural_causal_graph: nx.DiGraph,
                              effect: str = 'total') -> pm.Model:
    """Generate SCM model for either total or direct effects."""

    if effect not in {'total', 'direct'}:
        raise ValueError("Effect must be either 'total' or 'direct'")

    node_layers, predecessors = generate_scm_layers(structural_causal_graph)
    outcome_variables = [node for node in structural_causal_graph.nodes if
                         structural_causal_graph.out_degree(node) == 0]
    df_standardized = (data - data.mean()) / data.std()
    values = {column: df_standardized[column].values for column in df_standardized.columns}
    alpha, beta, sigma, mu, obs, independent_data = {}, {}, {}, {}, {}, {}

    with pm.Model() as structural_causal_model:
        for node in sorted(node_layers.keys(), key=node_layers.__getitem__):
            node_should_be_observed = (effect == 'total' and predecessors[node]) or (
                    effect == 'direct' and node in outcome_variables)
            if node_should_be_observed:
                alpha[node] = pm.Normal(f"{node} alpha", mu=0, sigma=10)

                current_predecessor_string = ', '.join(
                    f'{index}:{name}' for index, name in enumerate(predecessors[node]))
                current_node_beta_name = f"{node} beta * ({current_predecessor_string})"

                beta[node] = pm.Normal(current_node_beta_name, mu=0, sigma=10, shape=len(predecessors[node]))
                sigma[node] = pm.HalfNormal(f"{node} sigma", sigma=1)

                mu[node] = alpha[node]
                for i, predecessor in enumerate(predecessors[node]):
                    if effect == 'total':
                        predictor = independent_data[predecessor] if node_layers[predecessor] == 0 else obs[predecessor]
                    else:
                        predictor = independent_data[predecessor]
                    mu[node] += beta[node][i] * predictor

                obs[node] = pm.Normal(f"{node} obs", mu=mu[node], sigma=sigma[node], observed=values[node])
            else:
                # Make sure independent variables are modeled
                independent_data[node] = pm.Data(f"{node}_data", values[node])
    return structural_causal_model


def shorten_graph_nodes(graph: nx.DiGraph) -> nx.DiGraph:
    """Renames nodes in a graph copy according to specified abbreviation rules."""

    def abbreviate(name: str) -> str:
        """Abbreviates variable names using first letter and uppercase letters."""
        if not name:
            return ""
        abbreviation = [name[0].lower()]
        for c in name[1:]:
            if c.isupper():
                abbreviation.append(c)
        return ''.join(abbreviation)

    def process_name(name: str) -> str:
        """Processes a single node name through all transformation rules."""
        # Remove parentheses content
        clean_name = name.split('*')[0].strip()
        parts = clean_name.split('_') if '_' in clean_name else clean_name.split()

        if not parts:
            return name  # Return original if empty after cleaning

        # Process variable part
        variable = abbreviate(parts[0])
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
    return nx.relabel_nodes(graph, {n: process_name(n) for n in graph.nodes}, copy=True)


def visualize_scm_model(model: pm.Model) -> None:
    model_graph = pm.model_to_networkx(model)
    model_graph = shorten_graph_nodes(model_graph)

    plt.figure(figsize=(20, 20))  # Set viewport size (width, height in inches)

    nx.draw(
        model_graph,
        pos=nx.planar_layout(model_graph, scale=1),  # Increase node spacing
        with_labels=True,
        node_size=2500,  # Increase node size (default 300)
        node_color='skyblue',  # Better visibility
        edge_color='gray',  # Better visibility
        width=3,  # Increase edge thickness (default 1)
        font_size=14,  # Increase label size
        font_weight='bold',  # Improve label readability
        arrowsize=15  # Increase arrow size for directed edges
    )

    plt.show()


df = pd.DataFrame()
adjusted_graph = nx.DiGraph()
reversed_graph = nx.DiGraph()

scm_total_effect_model = generate_scm_effect_model(df, adjusted_graph, effect='total')
scm_direct_effect_model = generate_scm_effect_model(df, adjusted_graph, effect='direct')
scm_reverse_model = generate_scm_effect_model(df, reversed_graph, effect='total')

visualize_scm_model(scm_total_effect_model)
visualize_scm_model(scm_direct_effect_model)
visualize_scm_model(scm_reverse_model)

class SomeModel(ModelBuilder)