import pandas as pd
from typing import Dict, Any, List, Optional
from app.schemas.model import ExportConfig

def _unwrap_values(data: Any) -> Any:
    """Recursively unwrap {'value': ...} structures."""
    if isinstance(data, dict):
        if "value" in data and len(data) <= 4: # Typical DAOM output: value, confidence, bbox, _modifier
            return _unwrap_values(data["value"])
        return {k: _unwrap_values(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_unwrap_values(i) for i in data]
    return data

def apply_export_definition(
    raw_extracted: Dict[str, Any], 
    config: ExportConfig,
    metadata: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    결정론적 병합 엔진 (Deterministic Export Engine)
    """
    if not config or not config.definition:
        return []

    df_def = config.definition
    
    # Unwrap DAOM payload first
    clean_extracted = _unwrap_values(raw_extracted)

    # 1. Load Base Table
    base_data = clean_extracted.get(df_def.base_table, [])
    if not isinstance(base_data, list):
        return []

    try:
        df_base = pd.DataFrame(base_data)
    except Exception as e:
        # Failed to convert base table to DataFrame
        return []

    # If base table is empty, we return empty
    if df_base.empty:
        return []

    # [Phase 3.5] Metadata Injection
    if getattr(df_def, "inject_metadata", False) and metadata:
        for k, v in metadata.items():
            df_base[k] = str(v)

    # 2 & 3. Process Pivot Tables and Merge
    for pivot_def in df_def.pivot_tables:
        pivot_data = clean_extracted.get(pivot_def.table, [])
        if not pivot_data or not isinstance(pivot_data, list):
            continue

        df_pivot_raw = pd.DataFrame(pivot_data)
        if df_pivot_raw.empty:
            continue

        # Check required columns for pivoting
        required_cols = [pivot_def.category_field, pivot_def.subcategory_field, pivot_def.value_field]
        if not all(col in df_pivot_raw.columns for col in required_cols):
            continue

        # Prepare pivot index which are all columns EXCEPT the ones being pivoted
        index_cols = [c for c in df_pivot_raw.columns if c not in required_cols]
        # Keep only the merge keys (if they exist) as the index to avoid pivoting over unnecessary fields
        valid_merge_keys = [k for k in df_def.merge_keys if k in df_pivot_raw.columns]
        if not valid_merge_keys:
            continue # Needs merge keys to join back

        try:
            # Drop duplicates before pivot to avoid unstacking issues
            df_pivot_raw = df_pivot_raw.drop_duplicates(subset=valid_merge_keys + [pivot_def.category_field, pivot_def.subcategory_field])
            
            # Pivot table
            df_pivoted = df_pivot_raw.pivot(
                index=valid_merge_keys,
                columns=[pivot_def.category_field, pivot_def.subcategory_field],
                values=pivot_def.value_field
            )
            
            # Flatten multi-index columns according strictly to column naming
            df_pivoted.columns = [
                pivot_def.column_naming.format(
                    **{pivot_def.category_field: str(cat), pivot_def.subcategory_field: str(sub)}
                ) for cat, sub in df_pivoted.columns
            ]
            
            df_pivoted = df_pivoted.reset_index()

            # Merge with base table
            df_base = pd.merge(df_base, df_pivoted, on=valid_merge_keys, how="left")

        except Exception as e:
            # Safely skip this pivot table on exception (e.g., duplicated indices)
            # Log error if standard logging is available
            continue

    # 4. Conflict Policy (e.g., first_non_empty)
    # Pandas merge suffixes are _x and _y.
    # Currently, pd.merge handles identically named non-merge-key columns by suffixing them.
    # We resolve x/y conflicts if conflict_policy asks for it.
    if df_def.conflict_policy == "first_non_empty":
        for col in df_base.columns:
            if col.endswith("_x"):
                base_col = col[:-2]
                col_y = base_col + "_y"
                if col_y in df_base.columns:
                    # Fill na of x with values of y
                    df_base[base_col] = df_base[col].fillna(df_base[col_y])
                    df_base = df_base.drop(columns=[col, col_y])

    # 5. Final Column Mapping
    if df_def.final_column_mappings:
        # mapping format is now List of ColumnMappingDef objects
        # We need {"원본추출컬럼명": "결과컬럼명"} for pandas rename
        rename_map = {m.source: m.target for m in df_def.final_column_mappings if m.source and m.target}
        df_base = df_base.rename(columns=rename_map)
        
        # Keep only mapped target columns (plus any injected metadata columns)
        # Using the exact order defined in the UX (since final_column_mappings is an ordered list)
        mapped_target_cols = [m.target for m in df_def.final_column_mappings if m.target]
        
        if getattr(df_def, "inject_metadata", False) and metadata:
            # Append metadata keys
            for key in metadata.keys():
                if key not in mapped_target_cols:
                    mapped_target_cols.append(key)
            
        # Only keep existing columns while preserving user-defined order
        cols_to_keep = [c for c in mapped_target_cols if c in df_base.columns]
        
        if cols_to_keep:
            df_base = df_base[cols_to_keep]

    # [Phase 3.5] Grouping & Aggregation
    group_keys = getattr(df_def, "group_by_keys", [])
    valid_group_keys = [k for k in group_keys if k in df_base.columns]
    
    if valid_group_keys:
        agg_strategy = getattr(df_def, "aggregation_strategy", "first_non_empty")
        try:
            agg_funcs = {}
            for col in df_base.columns:
                if col not in valid_group_keys:
                    if agg_strategy == "first_non_empty":
                        agg_funcs[col] = "first"
                    elif agg_strategy == "sum":
                        if pd.api.types.is_numeric_dtype(df_base[col]):
                            agg_funcs[col] = "sum"
                        else:
                            agg_funcs[col] = "first"
                    else: # concat
                        agg_funcs[col] = lambda x: ', '.join(x.dropna().astype(str).unique())
            
            if agg_funcs:
                # Group by and aggregate, then reset index
                df_base = df_base.groupby(valid_group_keys, dropna=False).agg(agg_funcs).reset_index()
                import logging
                logging.getLogger(__name__).info(f"Grouped Dataframe by {valid_group_keys} using {agg_strategy}")
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to group dataframe by {valid_group_keys}: {e}")

    # Convert NaN back to None (standard JSON null)
    df_base = df_base.where(pd.notna(df_base), None)
    
    # Return as list of dicts
    return df_base.to_dict(orient="records")
