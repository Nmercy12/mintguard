"""MintGuard — a free-mint safety auditor agent.

Ask it about any EVM contract and it returns a structured GO / CAUTION /
BLOCK verdict with replayable on-chain evidence. Standard library only.
"""

from .audit import VERSION, audit, audit_json, count_transient

__all__ = ["VERSION", "audit", "audit_json", "count_transient"]
