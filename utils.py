from pathlib import Path
from typing import Optional

import pandas as pd


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
