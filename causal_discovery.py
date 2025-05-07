"""
Causal discovery pipeline with PC algorithm and edge direction confidence analysis.
"""

from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from castle.algorithms import PC
from castle.common.priori_knowledge import PrioriKnowledge
from scipy.stats import spearmanr
from sklearn.linear_model import LinearRegression


def create_priori_knowledge(data: pd.DataFrame, independent_variables: list[str],
                            outcome_variables: list[str]) -> PrioriKnowledge:
    """Create prior knowledge constraints for causal discovery.

    Args:
        data: DataFrame containing the observational data with column names.
        independent_variables: List of independent variables.
        outcome_variables: List of outcome variables.

    Returns:
        PrioriKnowledge object configured with forbidden edges:
        - No incoming edges to independent variables
        - No edges between outcome variables
    """
    number_of_vars = len(data.columns)
    pk = PrioriKnowledge(number_of_vars)
    forbidden_edges = []

    # Prevent any edges pointing to independent variables
    for variable in independent_variables:
        forbidden_edges.extend(
            (column, variable) for column in data.columns if column != variable
        )

    # Prevent any edges coming from outcome variables
    for variable in outcome_variables:
        forbidden_edges.extend(
            (variable, column) for column in data.columns if column != variable
        )

    # Convert column names to indices for PrioriKnowledge
    edge_indices = [
        (data.columns.get_loc(source), data.columns.get_loc(target))
        for source, target in forbidden_edges
    ]
    pk.add_forbidden_edges(edge_indices)

    return pk


def compute_edge_direction_confidence(graph: nx.DiGraph, data: pd.DataFrame) -> dict[tuple[str, str], float]:
    """Calculate confidence scores for edge directions using residual analysis.

    Args:
        graph: Initial causal graph from PC algorithm
        data: Observational data for variables

    Returns:
        Dictionary mapping edges (as tuples) to confidence scores in [0,1],
        where higher values indicate stronger directional confidence
    """
    edge_confidence = {}

    for source, target in graph.edges():
        # Prepare data for both regression directions
        source_data = data[source].values.reshape(-1, 1)
        target_data = data[target].values.reshape(-1, 1)

        # Calculate residuals for both regression directions
        residuals_source = _calculate_residuals(source_data, target_data)
        residuals_target = _calculate_residuals(target_data, source_data)

        # Compute Spearman correlations between variables and opposing residuals
        correlation_source_to_target_residuals, _ = spearmanr(source_data, residuals_target)
        correlation_target_to_source_residuals, _ = spearmanr(target_data, residuals_source)

        # Determine confidence and optimal edge direction
        confidence = abs(abs(correlation_target_to_source_residuals) - abs(correlation_source_to_target_residuals))
        if abs(correlation_source_to_target_residuals) > abs(correlation_target_to_source_residuals):
            optimal_edge = (source, target)
        else:
            optimal_edge = (target, source)

        edge_confidence[optimal_edge] = confidence
    return edge_confidence


def _calculate_residuals(independent_variable: np.ndarray, dependent_variable: np.ndarray) -> np.ndarray:
    """Calculate residuals from linear regression of X ~ Y."""
    model = LinearRegression()
    model.fit(independent_variable, dependent_variable)
    return dependent_variable - model.predict(independent_variable)


def adjust_edges(original_graph: nx.DiGraph, edge_confidence: dict[tuple[str, str], float],
                 independent_variables: list[str], outcome_variables: list[str]) -> list[tuple[str, str]]:
    """Adjust edge directions based on confidence scores and domain constraints.

    Args:
        original_graph: Initial causal graph from PC algorithm
        edge_confidence: Confidence scores for suggested edges
        independent_variables: List of independent variables

    Returns:
        List of adjusted edges following rules:
        - Prevent edges pointing to independent variables
        - Prevent edges coming from outcome variables
    """
    adjusted_edges = []

    for suggested_edge, confidence in edge_confidence.items():
        current_edge = suggested_edge

        # Check if edge direction was changed from original
        if suggested_edge not in original_graph.edges():
            # Revert if invalid source or target
            if suggested_edge[1] in independent_variables or suggested_edge[0] in outcome_variables:
                current_edge = (suggested_edge[1], suggested_edge[0])

        adjusted_edges.append(current_edge)

    return adjusted_edges


def create_adjusted_graph(original_graph: nx.DiGraph, adjusted_edges: list[tuple[str, str]]) -> nx.DiGraph:
    """Create new graph with adjusted edge directions.

    Args:
        original_graph: Base graph structure
        adjusted_edges: Modified edge directions

    Returns:
        New directed graph with updated edges
    """
    new_graph = original_graph.copy()
    new_graph.clear_edges()
    new_graph.add_edges_from(adjusted_edges)
    if not nx.is_directed_acyclic_graph(new_graph):
        raise RuntimeError("New graph is not a directed acyclic graph. Please adjust edge directions manually.")
    return new_graph


def visualize_causal_graph(graph: nx.DiGraph, title: str) -> None:
    """Visualize causal graph with color-coded nodes.

    Color scheme:
    - Green: Independent variables
    - Red: Outcome variables
    - Yellow: Mediator nodes

    Args:
        graph: Causal graph to visualize
        title: Display title for the plot
    """
    plt.figure(figsize=(10, 6))
    plt.title(title)

    color_map = [
        "green" if graph.in_degree(node) == 0
        else "red" if graph.out_degree(node) == 0
        else "yellow"
        for node in graph.nodes
    ]

    nx.draw(
        G=graph,
        node_color=color_map,
        node_size=1200,
        arrowsize=30,
        with_labels=True,
        pos=nx.circular_layout(graph),
    )

    plt.show()


def read_data(data_path: Path, columns: Optional[list[str]]) -> pd.DataFrame:
    """Read observational data from CSV file.

    Args:
        data_path: Path to CSV file
        columns: Optional subset of columns to load

    Returns:
        DataFrame with selected columns
    """
    df = pd.read_csv(data_path)
    return df[columns] if columns else df


def generate_causal_graph(data: pd.DataFrame, independent_variables: list[str], outcome_variables: list[str],
                          adjust_edge_direction: bool = True) -> nx.DiGraph:
    """Execute full causal discovery pipeline.

    Args:
        data: Observational data
        adjust_edge_direction: Whether to refine edge directions
        independent_variables: List of independent variables
        outcome_variables: List of outcome variables

    Returns:
        Final causal graph after optional adjustments
    """
    pk = create_priori_knowledge(data, independent_variables, outcome_variables)
    pc = PC(variant="stable", priori_knowledge=pk)
    pc.learn(data.values.tolist())

    # Convert to NetworkX graph with proper node labels
    causal_graph = nx.DiGraph(pc.causal_matrix)
    nx.relabel_nodes(causal_graph, {i: col for i, col in enumerate(data.columns)}, copy=False)

    if adjust_edge_direction:
        confidence_scores = compute_edge_direction_confidence(causal_graph, data)
        adjusted_edges = adjust_edges(causal_graph, confidence_scores, independent_variables, outcome_variables)
        causal_graph = create_adjusted_graph(causal_graph, adjusted_edges)

    return causal_graph


def get_mediator_graph(causal_graph: nx.DiGraph, independent_variables: list[str]) -> nx.DiGraph:
    """Create reversed mediator graph excluding independent variables.

    Args:
        causal_graph: Original causal graph
        independent_variables: List of independent variables to exclude from causal_graph.

    Returns:
        Reversed graph focused on mediators and outcomes
    """
    reversed_graph = causal_graph.reverse()
    reversed_graph.remove_nodes_from(independent_variables)
    return reversed_graph


def run_causal_discovery(data_path: Path, columns: list[str], independent_variables: list[str],
                         outcome_variables: list[str], visualize: bool = True) -> dict[
    str, nx.DiGraph]:
    """Main execution pipeline for causal discovery.

    Args:
        data_path: Path to observational data
        columns: Optional subset of columns to analyze
        visualize: Whether to display generated graphs
        independent_variables: List of independent variables
        outcome_variables: List of outcome variables

    Returns:
        Dictionary containing:
        - causal_graph: Final adjusted causal graph
        - mediator_graph: Reversed mediator-focused graph
    """
    if not (set(independent_variables) | (set(outcome_variables))).issubset(set(columns)):
        raise ValueError("Independent and outcome variables must be a subset of columns.")

    data = read_data(data_path, columns)
    causal_graph = generate_causal_graph(data, independent_variables, outcome_variables)

    mediator_graph = get_mediator_graph(causal_graph, independent_variables)

    if visualize:
        visualize_causal_graph(causal_graph, "Discovered Causal Graph")
        visualize_causal_graph(mediator_graph, "Reversed Mediator Causal Graph")

    return {"causal_graph": causal_graph, "mediator_graph": mediator_graph}


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
    independent_variables = ["desiredSpeed", "friction"]
    outcome_variables = ["waitingTime", "collisions"]

    run_causal_discovery(data_path, selected_columns, independent_variables, outcome_variables, visualize=True)


if __name__ == "__main__":
    main()
