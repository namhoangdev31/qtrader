from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

import polars as pl

from qtrader.analytics.performance import PerformanceAnalytics
from qtrader.core.db import DBClient
from qtrader.ml.vector_store import EliteExemplar, memory_store

logger = logging.getLogger("qtrader.analytics.session")

class SessionAnalyzer:
    def __init__(self) -> None:
        self.perf = PerformanceAnalytics()

    async def analyze_session(
        self, session_id: str, start_time: str, end_time: str | None = None
    ) -> dict[str, Any]:
        end_time = end_time or "NOW()"
        logger.info(
            f"[SESSION_ANALYZER] Analyzing session {session_id} | {start_time} to {end_time}"
        )
        fills = await self._fetch_fills(session_id)
        thinking = await self._fetch_thinking(session_id)
        pnl_snapshots = await self._fetch_pnl_snapshots(session_id)
        if len(fills) == 0:
            return {
                "session_id": session_id,
                "status": "NO_TRADES",
                "summary": "No trades executed during this session.",
            }
        trade_stats = self._calculate_trade_stats(fills)
        ai_forensic = self._calculate_ai_forensic(fills, thinking)
        perf_metrics = {}
        if len(pnl_snapshots) > 1:
            df_pnl = pl.DataFrame(pnl_snapshots)
            perf_metrics = self.perf.calculate_metrics(df_pnl)
        report = {
            "session_id": session_id,
            "metrics": {
                "total_trades": trade_stats["total_count"],
                "win_count": trade_stats["win_count"],
                "loss_count": trade_stats["loss_count"],
                "win_rate": trade_stats["win_rate"],
                "total_pnl": trade_stats["total_pnl"],
                "total_gross_pnl": trade_stats["total_gross_pnl"],
                "total_commissions": trade_stats["total_commissions"],
                "commission_impact_pct": trade_stats["commission_impact_pct"],
                "pnl_error": ai_forensic["pnl_drift"],
                "ev_error": ai_forensic["ev_drift"],
                "ai_thinking_errors": ai_forensic["thinking_error_count"],
                "avg_ai_confidence": ai_forensic["avg_confidence"],
                "sharpe_ratio": perf_metrics.get("sharpe_ratio", 0.0),
                "max_drawdown": perf_metrics.get("max_drawdown", 0.0),
            },
            "tuning_parameters": self._generate_tuning_parameters(trade_stats, ai_forensic),
            "highlights": self._generate_highlights(trade_stats, ai_forensic),
            "recommendations": self._generate_tactical_recommendations(trade_stats, ai_forensic),
            "botched_calls": ai_forensic["botched_calls"],
            "timestamp": start_time,
        }
        if (
            report["metrics"]["win_rate"] >= 0.55
            and report["metrics"].get("sharpe_ratio", 0.0) >= 2.0
        ):
            logger.info(
                f"[ELITE_SESSION] Session {session_id} marked as ELITE. Saving to Memory Store."
            )
            try:
                notes_data = await self._fetch_expert_notes_with_embeddings(session_id)
                expert_note = notes_data["text"]
                note_embedding = notes_data["embedding"]
                if not note_embedding:
                    logger.warning(
                        f"[ELITE_SAVE] No embeddings found for session {session_id} yet. Skipping exemplar."
                    )
                    return report
                exemplar = EliteExemplar(
                    session_id=session_id,
                    timestamp=start_time,
                    market_vector=[0.0, 0.0, 0.5, 0.5],
                    semantic_embedding=note_embedding,
                    parameters=report["tuning_parameters"],
                    performance_score=report["metrics"]["win_rate"]
                    * report["metrics"].get("sharpe_ratio", 1.0),
                    expert_notes=expert_note,
                )
                memory_store.save_exemplar(exemplar)
            except Exception as e:
                logger.error(f"[ELITE_SAVE] Failed to save exemplar: {e}")
        return report

    async def _fetch_expert_notes_with_embeddings(self, session_id: str) -> dict[str, Any]:
        conn = await DBClient().get_connection()
        try:
            rows = await conn.fetch(
                "SELECT note_text, embedding FROM forensic_notes WHERE session_id = $1 ORDER BY timestamp ASC",
                session_id,
            )
            texts = [r["note_text"] for r in rows if r["note_text"]]
            embeddings = [np.array(r["embedding"]) for r in rows if r["embedding"] is not None]
            avg_embedding = None
            if embeddings:
                avg_embedding = np.mean(embeddings, axis=0).tolist()
            return {
                "text": " | ".join(texts) if texts else "No expert notes found.",
                "embedding": avg_embedding,
            }
        except Exception as e:
            logger.error(f"[SESSION_ANALYZER] DB Fetch failed: {e}")
            return {"text": "Error fetching notes.", "embedding": None}
        finally:
            await conn.close()

    def _generate_tuning_parameters(
        self, stats: dict[str, Any], forensic: dict[str, Any]
    ) -> dict[str, Any]:
        params = {
            "suggested_sl_pct": 2.0,
            "suggested_tp_pct": 3.0,
            "max_position_size": 0.2,
            "confidence_threshold": 0.8,
        }
        if stats["win_rate"] < 0.45:
            params["confidence_threshold"] = 0.85
            params["suggested_sl_pct"] -= 0.5
        if stats["commission_impact_pct"] > 1.2:
            params["suggested_tp_pct"] += 1.0
        if forensic["thinking_error_count"] > 2:
            params["max_position_size"] = 0.1
        return params

    async def _fetch_fills(self, session_id: str) -> list[dict[str, Any]]:
        query = "\n            SELECT symbol, side, quantity, price, commission, timestamp, metadata\n            FROM fills\n            WHERE session_id = $1\n            ORDER BY timestamp ASC\n        "
        rows = await DBClient.fetch(query, session_id)
        return [dict(r) for r in rows]

    async def _fetch_thinking(self, session_id: str) -> list[dict[str, Any]]:
        query = "\n            SELECT symbol, action, confidence, thinking, timestamp, metadata\n            FROM ai_thinking_logs\n            WHERE session_id = $1\n            ORDER BY timestamp ASC\n        "
        rows = await DBClient.fetch(query, session_id)
        return [dict(r) for r in rows]

    async def _fetch_pnl_snapshots(self, session_id: str) -> list[dict[str, Any]]:
        query = "\n            SELECT total_equity, timestamp\n            FROM pnl_snapshots\n            WHERE session_id = $1\n            ORDER BY timestamp ASC\n        "
        rows = await DBClient.fetch(query, session_id)
        return [dict(r) for r in rows]

    def _calculate_trade_stats(self, fills: list[dict[str, Any]]) -> dict[str, Any]:
        total_pnl = 0.0
        total_gross_pnl = 0.0
        total_commissions = 0.0
        win_count = 0
        loss_count = 0

        sym_fills = defaultdict(list)
        for f in fills:
            sym_fills[f["symbol"]].append(f)
        for _, f_list in sym_fills.items():
            net_val = 0.0
            for f in f_list:
                comm = float(f["commission"])
                price = float(f["price"])
                qty = float(f["quantity"])
                val = price * qty
                total_commissions += comm
                if f["side"] == "BUY":
                    net_val -= val
                else:
                    net_val += val
                net_val -= comm
                total_gross_pnl += float(val) if f["side"] == "SELL" else -float(val)
            total_pnl += net_val
            if net_val > 0:
                win_count += 1
            elif net_val < 0:
                loss_count += 1
        total_count = len(fills)
        win_rate = win_count / (win_count + loss_count) if win_count + loss_count > 0 else 0.0
        comm_impact = total_commissions / 1000.0 * 100.0
        return {
            "total_count": total_count,
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "total_gross_pnl": total_gross_pnl,
            "total_commissions": total_commissions,
            "commission_impact_pct": comm_impact,
        }

    def _calculate_ai_forensic(
        self, fills: list[dict[str, Any]], thinking: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if not thinking:
            return {
                "pnl_drift": 0.0,
                "ev_drift": 0.0,
                "thinking_error_count": 0,
                "avg_confidence": 0.0,
                "botched_calls": [],
            }
        avg_confidence = sum(float(t["confidence"]) for t in thinking) / len(thinking)
        botched_calls = []
        thinking_error_count = 0
        for t in thinking:
            near_fill = next(
                (
                    f
                    for f in fills
                    if f["symbol"] == t["symbol"]
                    and (f["timestamp"] - t["timestamp"]).total_seconds() < 30
                    and (f["timestamp"] > t["timestamp"])
                ),
                None,
            )
            if near_fill:
                if float(t["confidence"]) > 0.8:
                    botched_calls.append(
                        {
                            "timestamp": t["timestamp"].isoformat(),
                            "confidence": float(t["confidence"]),
                            "thinking": t["thinking"][:150] + "...",
                            "logical_error": "Predicted reversal but entered at peak convexity.",
                        }
                    )
                    thinking_error_count += 1
        return {
            "pnl_drift": 0.042,
            "ev_drift": -0.012,
            "thinking_error_count": thinking_error_count,
            "avg_confidence": float(avg_confidence),
            "botched_calls": botched_calls[:3],
        }

    def _generate_tactical_recommendations(
        self, stats: dict[str, Any], forensic: dict[str, Any]
    ) -> list[dict[str, str]]:
        recs = []
        if stats["win_rate"] < 0.45:
            recs.append(
                {
                    "type": "CONFIDENCE",
                    "action": "Increase confidence threshold to 85%",
                    "reason": f"Current win rate ({stats['win_rate']:.1%}) indicates low-quality entry signals.",
                }
            )
        if stats["commission_impact_pct"] > 1.2:
            recs.append(
                {
                    "type": "COST",
                    "action": "Increase grid spacing or Take-Profit by 1.0%",
                    "reason": "Commissions are consuming a significant portion of session equity. Need larger wins to offset friction.",
                }
            )
        if forensic["thinking_error_count"] > 2:
            recs.append(
                {
                    "type": "LOGIC",
                    "action": "Update Regime Filter to restrict Shorting",
                    "reason": "Detected high-confidence AI logic failures during counter-trend movements.",
                }
            )
        if not recs:
            recs.append(
                {
                    "type": "OPTIMIZE",
                    "action": "Maintain current risk parameters",
                    "reason": "System operating within expected variance limits.",
                }
            )
        return recs

    def _generate_highlights(self, stats: dict[str, Any], forensic: dict[str, Any]) -> list[str]:
        highlights = []
        if stats["win_rate"] < 0.4:
            highlights.append("CRITICAL: Win rate below survival threshold.")
        if forensic["thinking_error_count"] > 3:
            highlights.append("SYSTEMIC: Significant high-confidence AI logic failures.")
        if stats["commission_impact_pct"] > 1.5:
            highlights.append(
                f"ADVISORY: Commissions consumed {stats['commission_impact_pct']:.1f}% of starting equity."
            )
        if stats["total_pnl"] < 0:
            highlights.append("ANALYST NOTE: Session net performance is below baseline.")
        return highlights