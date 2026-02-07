"""
Token Audit Utility for LLM Prompt Optimization

Provides accurate token counting using tiktoken (same tokenizer as GPT-4o).
Use this to diagnose token bloat in extraction prompts.

Usage:
    from app.services.token_audit import audit_prompt, count_tokens
    
    # Quick count
    tokens = count_tokens("some text")
    
    # Full audit
    report = audit_prompt(system_prompt, user_prompt, schema=schema_dict)
    print(report["summary"])
"""
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Lazy-load tiktoken to avoid import overhead
_encoding = None

def _get_encoding():
    """Get tiktoken encoding for GPT-4o (cl100k_base)."""
    global _encoding
    if _encoding is None:
        try:
            import tiktoken
            _encoding = tiktoken.get_encoding("cl100k_base")
        except ImportError:
            logger.warning("[TokenAudit] tiktoken not installed. Using char-based estimate.")
            return None
    return _encoding


def count_tokens(text: str) -> int:
    """Count tokens in text using tiktoken. Falls back to char estimate."""
    enc = _get_encoding()
    if enc:
        return len(enc.encode(text))
    # Fallback: rough estimate considering Korean/special chars
    return len(text) // 3


def audit_prompt(
    system_prompt: str,
    user_prompt: str,
    schema: Optional[Dict] = None,
    model_name: str = "gpt-4o",
) -> Dict[str, Any]:
    """
    Audit an LLM prompt for token usage.
    
    Returns detailed breakdown:
    - system_prompt tokens
    - user_prompt tokens  
    - schema tokens (if using Structured Outputs)
    - overhead (message framing, etc.)
    - total
    - recommendations
    """
    enc = _get_encoding()
    
    sys_tokens = count_tokens(system_prompt)
    user_tokens = count_tokens(user_prompt)
    schema_tokens = count_tokens(json.dumps(schema)) if schema else 0
    
    # Azure adds ~10-15 tokens for message framing
    overhead = 15
    total = sys_tokens + user_tokens + schema_tokens + overhead
    
    # Analyze user prompt components
    tab_count = user_prompt.count("\t")
    empty_cell_waste = 0
    if enc:
        # Count tokens that are just whitespace
        lines = user_prompt.split("\n")
        for line in lines:
            cells = line.split("\t")
            for cell in cells:
                if not cell.strip():
                    empty_cell_waste += 1  # Each empty cell between tabs ≈ 1 token
    
    # Build recommendations
    recommendations = []
    if tab_count > 100:
        recommendations.append(
            f"⚠️ {tab_count} tab characters detected. "
            f"Each tab = 1 token. Consider pipe-separated or compact format."
        )
    if empty_cell_waste > 50:
        recommendations.append(
            f"⚠️ ~{empty_cell_waste} empty cells wasting tokens. "
            f"Remove trailing empty cells per row."
        )
    if schema_tokens > 500:
        recommendations.append(
            f"⚠️ Structured Outputs schema uses {schema_tokens} tokens. "
            f"Consider json_object mode for simpler models."
        )
    if sys_tokens > 2000:
        recommendations.append(
            f"⚠️ System prompt is {sys_tokens} tokens. "
            f"Consider trimming reference_data or repetitive instructions."
        )
    
    # Percentage breakdown
    summary_lines = [
        f"═══ TOKEN AUDIT ({model_name}) ═══",
        f"  System prompt:   {sys_tokens:>6,} tokens ({sys_tokens*100//max(total,1):>2}%)",
        f"  User prompt:     {user_tokens:>6,} tokens ({user_tokens*100//max(total,1):>2}%)",
    ]
    if schema_tokens:
        summary_lines.append(
            f"  Schema (SO):     {schema_tokens:>6,} tokens ({schema_tokens*100//max(total,1):>2}%)"
        )
    summary_lines.extend([
        f"  Overhead:        {overhead:>6,} tokens",
        "  ─────────────────────────────",
        f"  TOTAL:           {total:>6,} tokens",
        "",
        f"  Tab chars:       {tab_count:>6,}",
        f"  Empty cells:     {empty_cell_waste:>6,}",
    ])
    
    if recommendations:
        summary_lines.append("")
        summary_lines.append("  RECOMMENDATIONS:")
        for r in recommendations:
            summary_lines.append(f"    {r}")
    
    summary = "\n".join(summary_lines)
    
    return {
        "system_tokens": sys_tokens,
        "user_tokens": user_tokens,
        "schema_tokens": schema_tokens,
        "overhead": overhead,
        "total": total,
        "tab_count": tab_count,
        "empty_cell_waste": empty_cell_waste,
        "recommendations": recommendations,
        "summary": summary,
    }


def audit_excel_content(content: str) -> Dict[str, Any]:
    """
    Audit Excel TSV content specifically for token efficiency.
    Shows per-row token counts and identifies waste.
    """
    lines = content.split("\n")
    
    total_tokens = 0
    row_details = []
    
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        tokens = count_tokens(line)
        total_tokens += tokens
        cells = line.split("\t")
        non_empty = sum(1 for c in cells if c.strip())
        empty = len(cells) - non_empty
        
        row_details.append({
            "row": i,
            "tokens": tokens,
            "cells": len(cells),
            "non_empty": non_empty,
            "empty": empty,
            "waste_ratio": empty / max(len(cells), 1),
        })
    
    # Find worst offenders
    worst_rows = sorted(row_details, key=lambda r: r["waste_ratio"], reverse=True)[:5]
    
    avg_waste = sum(r["waste_ratio"] for r in row_details) / max(len(row_details), 1)
    
    return {
        "total_tokens": total_tokens,
        "total_rows": len(row_details),
        "avg_tokens_per_row": total_tokens // max(len(row_details), 1),
        "avg_waste_ratio": round(avg_waste, 2),
        "worst_rows": worst_rows,
    }
