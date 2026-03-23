"""
Utility Functions Module
=======================
Helper functions for data validation and processing.
"""

import pandas as pd
from typing import List, Optional


def has_section_data(df: pd.DataFrame, required_cols: Optional[List[str]] = None) -> bool:
    """
    Return True if the dataframe has at least one non-empty value in the required columns
    or any non-empty column if required_cols is None.
    Treats NaN and empty strings as empty.
    
    Args:
        df: DataFrame to check
        required_cols: Optional list of column names to check
        
    Returns:
        True if data exists, False otherwise
    """
    if df is None or df.empty:
        return False

    # If specific columns are required, only consider those that exist
    if required_cols:
        existing = [c for c in required_cols if c in df.columns]
        if not existing:
            return False
        for c in existing:
            series = df[c]
            # drop NaN, strip empty strings and check if any remain
            non_empty = series.dropna().astype(str).str.strip().replace('', pd.NA).dropna()
            if not non_empty.empty:
                return True
        return False
    else:
        # If no required_cols specified, check if any column has data
        for c in df.columns:
            series = df[c]
            non_empty = series.dropna().astype(str).str.strip().replace('', pd.NA).dropna()
            if not non_empty.empty:
                return True
        return False
