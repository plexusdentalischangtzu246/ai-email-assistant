from storage.data_store import (
    initialize, is_processed, store_email,
    fetch_recent, fetch_by_category, fetch_sensitive, get_summary_stats,
)
__all__ = [
    "initialize", "is_processed", "store_email",
    "fetch_recent", "fetch_by_category", "fetch_sensitive", "get_summary_stats",
]
