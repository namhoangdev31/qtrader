from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiohttp import web

logger = logging.getLogger("qtrader.monitoring.prometheus")


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = {}
        self._labels: dict[str, dict[str, str]] = {}

    def inc(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        key = self._make_key(name, labels)
        self._counters[key] = self._counters.get(key, 0) + value
        if labels:
            self._labels[key] = labels

    def set(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        key = self._make_key(name, labels)
        self._gauges[key] = value
        if labels:
            self._labels[key] = labels

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        key = self._make_key(name, labels)
        if key not in self._histograms:
            self._histograms[key] = []
        self._histograms[key].append(value)
        if len(self._histograms[key]) > 1000:
            self._histograms[key] = self._histograms[key][-1000:]
        if labels:
            self._labels[key] = labels

    def _make_key(self, name: str, labels: dict[str, str] | None) -> str:
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for (k, v) in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def get_metrics_text(self) -> str:
        lines: list[str] = []
        for key, value in self._counters.items():
            label_part = ""
            if key in self._labels:
                label_part = ",".join(f'{k}="{v}"' for (k, v) in self._labels[key].items())
                label_part = f"{{{label_part}}}"
            lines.append(f"{key}{label_part} {value}")
        for key, value in self._gauges.items():
            label_part = ""
            if key in self._labels:
                label_part = ",".join(f'{k}="{v}"' for (k, v) in self._labels[key].items())
                label_part = f"{{{label_part}}}"
            lines.append(f"{key}{label_part} {value}")
        for key, values in self._histograms.items():
            if not values:
                continue
            label_part = ""
            if key in self._labels:
                label_part = ",".join(f'{k}="{v}"' for (k, v) in self._labels[key].items())
                label_part = f"{{{label_part}}}"
            count = len(values)
            total = sum(values)
            avg = total / count if count > 0 else 0
            lines.append(f"{key}_count{label_part} {count}")
            lines.append(f"{key}_sum{label_part} {total}")
            lines.append(f"{key}_avg{label_part} {avg}")
        return "\n".join(lines)


class PrometheusMetricsExporter:
    def __init__(self, port: int = 9090) -> None:
        self.port = port
        self.registry = MetricsRegistry()
        self._running = False
        self._server_task: Any = None

    def start(self) -> None:
        self._running = True
        self._server_task = asyncio.create_task(self._run_server())
        logger.info(f"[PROMETHEUS] Metrics exporter started on port {self.port}")

    async def stop(self) -> None:
        self._running = False
        if self._server_task:
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass
        logger.info("[PROMETHEUS] Metrics exporter stopped")

    async def _run_server(self) -> None:
        try:

            async def handle_metrics(request: Any) -> web.Response:
                return web.Response(
                    text=self.registry.get_metrics_text(), content_type="text/plain"
                )

            async def handle_health(request: Any) -> web.Response:
                return web.Response(text="OK", content_type="text/plain")

            app = web.Application()
            app.router.add_get("/metrics", handle_metrics)
            app.router.add_get("/health", handle_health)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", self.port)  # noqa: S104
            await site.start()
            logger.info(f"[PROMETHEUS] HTTP server running on 0.0.0.0:{self.port}")
            while self._running:
                await asyncio.sleep(1)
            await runner.cleanup()
        except ImportError:
            logger.warning("[PROMETHEUS] aiohttp not available — metrics endpoint disabled")
            while self._running:
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"[PROMETHEUS] Server error: {e}")

    def record_order(self, submitted: bool = True, symbol: str = "", exchange: str = "") -> None:
        labels = {"symbol": symbol, "exchange": exchange}
        if submitted:
            self.registry.inc("qtrader_orders_submitted_total", labels=labels)
        else:
            self.registry.inc("qtrader_orders_rejected_total", labels=labels)

    def record_fill(self, symbol: str = "", exchange: str = "", latency_ms: float = 0.0) -> None:
        labels = {"symbol": symbol, "exchange": exchange}
        self.registry.inc("qtrader_fills_total", labels=labels)
        self.registry.observe("qtrader_fill_latency_ms", latency_ms, labels=labels)

    def record_cancel(self, symbol: str = "", exchange: str = "") -> None:
        labels = {"symbol": symbol, "exchange": exchange}
        self.registry.inc("qtrader_cancels_total", labels=labels)

    def update_pnl(self, realized: float = 0.0, unrealized: float = 0.0) -> None:
        self.registry.set("qtrader_pnl_realized", realized)
        self.registry.set("qtrader_pnl_unrealized", unrealized)
        self.registry.set("qtrader_pnl_total", realized + unrealized)

    def update_risk(self, var: float = 0.0, drawdown: float = 0.0, leverage: float = 1.0) -> None:
        self.registry.set("qtrader_var", var)
        self.registry.set("qtrader_drawdown", drawdown)
        self.registry.set("qtrader_leverage", leverage)

    def update_latency(self, stage: str, latency_ms: float) -> None:
        labels = {"stage": stage}
        self.registry.observe("qtrader_stage_latency_ms", latency_ms, labels=labels)

    def update_kill_switch(self, active: bool, reason: str = "") -> None:
        self.registry.set("qtrader_kill_switch_active", 1.0 if active else 0.0)
        if active:
            self.registry.set("qtrader_kill_switch_reason", 1.0, labels={"reason": reason})

    def update_exchange_health(
        self, exchange: str, connected: bool, latency_ms: float = 0.0
    ) -> None:
        labels = {"exchange": exchange}
        self.registry.set("qtrader_exchange_connected", 1.0 if connected else 0.0, labels=labels)
        self.registry.observe("qtrader_exchange_latency_ms", latency_ms, labels=labels)

    def update_market_maker(
        self, symbol: str, spread_bps: float = 0.0, inventory: float = 0.0, toxicity: float = 0.0
    ) -> None:
        labels = {"symbol": symbol}
        self.registry.set("qtrader_mm_spread_bps", spread_bps, labels=labels)
        self.registry.set("qtrader_mm_inventory", inventory, labels=labels)
        self.registry.set("qtrader_mm_toxicity", toxicity, labels=labels)

    def update_reconciliation(
        self, match: bool, oms_qty: float = 0.0, exchange_qty: float = 0.0
    ) -> None:
        self.registry.inc("qtrader_recon_checks_total")
        if match:
            self.registry.inc("qtrader_recon_matches_total")
        else:
            self.registry.inc("qtrader_recon_mismatches_total")
            self.registry.set("qtrader_recon_oms_qty", oms_qty)
            self.registry.set("qtrader_recon_exchange_qty", exchange_qty)
