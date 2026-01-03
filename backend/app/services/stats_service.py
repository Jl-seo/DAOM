"""
Stats Service - Aggregates extraction logs for dashboard analytics
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any
from app.services import extraction_logs, models
from app.core.enums import ExtractionStatus

logger = logging.getLogger(__name__)

def get_dashboard_stats(days: int = 30) -> Dict[str, Any]:
    """
    Get aggregated statistics for the dashboard
    """
    try:
        # Get all recent logs
        # Note: In a production scenario with millions of logs, 
        # this should be replaced with a proper Cosmos DB aggregate query
        # or a dedicated analytics store.
        logs = extraction_logs.get_all_logs(limit=1000)
        all_models = models.load_models()
        model_map = {m.id: m.name for m in all_models}
        
        # Initialize counters
        total_extractions = len(logs)
        success_count = sum(1 for log in logs if log.status == ExtractionStatus.SUCCESS.value)
        error_count = sum(1 for log in logs if log.status == ExtractionStatus.ERROR.value)
        
        # Calculate success rate
        success_rate = round((success_count / total_extractions * 100) if total_extractions > 0 else 0, 1)
        
        # 1. Daily Trend (Last 7 days)
        daily_trend = _calculate_daily_trend(logs, days=7)
        
        # 2. Model Usage Distribution
        model_usage = _calculate_model_usage(logs, model_map)
        
        # 3. Recent Activity (Top 5)
        recent_activity = [
            {
                "id": log.id,
                "model": model_map.get(log.model_id, "Unknown Model"),
                "filename": log.filename,
                "status": log.status,
                "timestamp": log.created_at,
                "user": log.user_name or log.user_email or "Unknown"
            }
            for log in logs[:5]
        ]
        
        return {
            "summary": {
                "total_extractions": total_extractions,
                "success_rate": success_rate,
                "active_models": len(model_map)
            },
            "daily_trend": daily_trend,
            "model_usage": model_usage,
            "recent_activity": recent_activity
        }
        
    except Exception as e:
        logger.error(f"[StatsService] Failed to calculate stats: {e}")
        return {
            "summary": {"total_extractions": 0, "success_rate": 0, "active_models": 0},
            "daily_trend": [],
            "model_usage": [],
            "recent_activity": []
        }

def _calculate_daily_trend(logs: List[Any], days: int) -> List[Dict[str, Any]]:
    """Aggregate logs by day"""
    trend = {}
    today = datetime.utcnow().date()
    
    # Initialize last N days with 0
    for i in range(days):
        date = (today - timedelta(days=i)).isoformat()
        trend[date] = 0
        
    for log in logs:
        try:
            # Parse created_at (ISO format)
            log_date = log.created_at.split('T')[0]
            if log_date in trend:
                trend[log_date] += 1
        except:
            continue
            
    # Sort by date
    return [
        {"date": date, "count": count}
        for date, count in sorted(trend.items())
    ]

def _calculate_model_usage(logs: List[Any], model_map: Dict[str, str]) -> List[Dict[str, Any]]:
    """Aggregate logs by model"""
    usage = {}
    
    for log in logs:
        model_name = model_map.get(log.model_id, "Unknown")
        usage[model_name] = usage.get(model_name, 0) + 1
        
    # Convert to list and sort by count desc
    return sorted(
        [{"name": name, "value": count} for name, count in usage.items()],
        key=lambda x: x["value"],
        reverse=True
    )
