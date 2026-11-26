import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

from ibm_watsonx_orchestrate.agent_builder.tools import tool
from ibm_watsonx_orchestrate.run.context import AgentRun


@tool(name="stock_research_journal")
def research_journal(action: str, context: AgentRun, ticker: str = "", text: str = "", kind: str = "activity") -> dict:
    """Save or recall the current user's research across chats. Use action 'save' or 'recall'.
    Save activity after a lookup, a dated note for an insight, or the exact supplied text for a report.
    Recall without a ticker to list prior work, or with a ticker to retrieve matching entries.
    """
    from altk_evolve.config.evolve import EvolveConfig
    from altk_evolve.config.filesystem import FilesystemSettings
    from altk_evolve.frontend.client.evolve_client import EvolveClient
    from altk_evolve.schema.core import Entity

    caller = context.request_context
    user = caller.get("wxo_user_id") or caller.get("wxo_email_id")
    if not user:
        return {"error": "Orchestrate did not supply a caller identity. Research memory is unavailable."}
    namespace = hashlib.sha256(json.dumps(["stock_researcher", caller.get("wxo_tenant_id"), user]).encode()).hexdigest()
    directory = Path(__file__).resolve().parent / "stock-research-evolve"
    settings = FilesystemSettings(data_dir=str(directory))
    store = EvolveClient(EvolveConfig(backend="filesystem", settings=settings))
    store.ensure_namespace(namespace)
    location = {"namespace": namespace[:12], "directory": str(directory)}
    symbol = ticker.strip().upper()
    if action == "save":
        if kind not in ("activity", "note", "report") or not text.strip():
            return {"error": "Supply the research text and an activity, note or report kind."}
        record = {"ticker": symbol, "text": text, "saved_at": datetime.now(timezone.utc).isoformat()}
        store.update_entities(namespace, [Entity(type=kind, content=record)], enable_conflict_resolution=False)
        return {"storage": location, "retention": "Runtime-local file; cross-chat persistence is unverified.", "saved": True, "kind": kind, "ticker": symbol}
    if action != "recall":
        return {"error": "Choose save or recall."}
    records = []
    for entity in store.scan_entities(namespace, limit=1000):
        entry = json.loads(entity.content) if isinstance(entity.content, str) else entity.content
        if not symbol or entry["ticker"] == symbol:
            records.append({**entry, "kind": entity.type})
    records.sort(key=lambda record: record["saved_at"], reverse=True)
    return {"storage": location, "tickers": sorted({r["ticker"] for r in records if r["ticker"]}), "recent": records[:10]}
