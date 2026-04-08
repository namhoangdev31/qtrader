"""Coinbase Advanced Trade Broker Adapter with Paper Trading Simulator.

Supports:
- Live execution via Coinbase Advanced Trade REST API (JWT auth)
- Paper Trading with realistic slippage, latency, and orderbook simulation
- WebSocket for real-time market data and order updates
- Auto-reconnect with exponential backoff
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import aiohttp

from qtrader.core.config import Config, settings
from qtrader.core.decimal_adapter import d

try:
    import redis.asyncio as redis_lib

    HAS_REDIS = True
except ImportError:
    redis_lib = None
    HAS_REDIS = False
from qtrader.core.events import FillEvent, FillPayload, OrderEvent
from qtrader.execution.brokers.base import BrokerAdapter
from qtrader.execution.brokers.coinbase_jwt import build_rest_jwt
from qtrader.execution.http import RetryConfig, request_json
from qtrader.execution.paper_engine import AdaptiveConfig

if TYPE_CHECKING:
    from collections.abc import Callable

    from qtrader.risk.kill_switch import GlobalKillSwitch
    from qtrader.security.order_signing import OrderSigner

logger = logging.getLogger("qtrader.broker.coinbase")


@dataclass
class PaperAccount:
    """Paper trading account state."""

    initial_balance: Decimal = Decimal("100000.0")
    cash: Decimal = Decimal("100000.0")
    positions: dict[str, Decimal] = field(default_factory=dict)
    orders: dict[str, OrderEvent] = field(default_factory=dict)
    fills: dict[str, list[FillEvent]] = field(default_factory=dict)
    order_history: deque = field(default_factory=lambda: deque(maxlen=10000))
    fill_history: deque = field(default_factory=lambda: deque(maxlen=10000))
    total_commissions: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    avg_entry_prices: dict[str, Decimal] = field(default_factory=dict)
    active_session_id: str | None = None
    adaptive: AdaptiveConfig = field(default_factory=AdaptiveConfig)

    @property
    def equity(self) -> Decimal:
        """Total equity (Cash + Market Value of all positions)."""
        position_value = Decimal("0")
        for asset, qty in self.positions.items():
            price = Decimal("0")
            if asset in self.avg_entry_prices:
                price = self.avg_entry_prices[asset]
            position_value += abs(qty) * price
        return self.cash + position_value

    def update_position(self, asset: str, qty: Decimal, price: Decimal, side: str) -> None:
        """Update position and track PnL correctly for both long and short."""
        current = self.positions.get(asset, Decimal("0"))
        avg_price = self.avg_entry_prices.get(asset, Decimal("0"))
        side_upper = side.upper()

        if side_upper == "BUY":
            if current >= 0:
                total_cost = avg_price * current + price * qty
                new_qty = current + qty
                if new_qty != 0:
                    self.avg_entry_prices[asset] = total_cost / new_qty
                self.positions[asset] = new_qty
                self.cash -= price * qty
            else:
                closing_qty = min(qty, abs(current))
                if avg_price > 0:
                    realized = (avg_price - price) * closing_qty
                    self.realized_pnl += realized
                new_qty = current + qty
                if new_qty == 0:
                    self.positions.pop(asset, None)
                    self.avg_entry_prices.pop(asset, None)
                elif new_qty > 0:
                    self.avg_entry_prices[asset] = price
                    self.positions[asset] = new_qty
                    self.cash -= price * new_qty
                else:
                    self.positions[asset] = new_qty
                    self.cash -= price * qty
        elif current <= 0:
            total_cost = avg_price * abs(current) + price * qty
            new_qty = current - qty
            if new_qty != 0:
                self.avg_entry_prices[asset] = total_cost / abs(new_qty)
            self.positions[asset] = new_qty
            self.cash += price * qty
        else:
            closing_qty = min(qty, current)
            if avg_price > 0:
                realized = (price - avg_price) * closing_qty
                self.realized_pnl += realized
            new_qty = current - qty
            if new_qty == 0:
                self.positions.pop(asset, None)
                self.avg_entry_prices.pop(asset, None)
            elif new_qty < 0:
                self.avg_entry_prices[asset] = price
                self.positions[asset] = new_qty
                self.cash += price * abs(new_qty)
            else:
                self.positions[asset] = new_qty
                self.cash += price * qty

        if self.positions.get(asset, d(0)) == 0:
            self.positions.pop(asset, None)
            self.avg_entry_prices.pop(asset, None)


class CoinbaseBrokerAdapter(BrokerAdapter):
    """
    Broker adapter for Coinbase Advanced Trade.

    Supports live execution and paper trading simulation with:
    - Realistic slippage modeling
    - Network latency simulation
    - Orderbook-aware fill pricing
    - WebSocket market data streaming
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        simulate: bool | None = None,
        *,
        rest_base: str | None = None,
        key_name: str | None = None,
        private_key_pem: str | None = None,
        request_timeout_s: float = 10.0,
        max_retries: int = 3,
        retry_backoff_ms: int = 200,
        # Paper trading config
        paper_slippage_bps: float = 5.0,
        paper_latency_ms: float = 50.0,
        paper_commission_rate: float = 0.001,
        # Kill switch for critical failure handling
        kill_switch: GlobalKillSwitch | None = None,
        # Order signing (Standash §5.3)
        order_signer: OrderSigner | None = None,
        # Shared simulation engine (unifies engine/UI)
        sim_engine: Any | None = None,
    ) -> None:
        self.api_key = api_key or Config.COINBASE_API_KEY
        self.api_secret = api_secret or Config.COINBASE_API_SECRET
        self.simulate = simulate if simulate is not None else True
        self._rest_base = rest_base or Config.COINBASE_REST_BASE
        self._key_name = key_name or Config.COINBASE_KEY_NAME
        self._private_key_pem = private_key_pem or Config.COINBASE_PRIVATE_KEY
        self._retry = RetryConfig(
            request_timeout_s=request_timeout_s,
            max_retries=max_retries,
            retry_backoff_ms=retry_backoff_ms,
        )
        self._session: aiohttp.ClientSession | None = None
        self.kill_switch = kill_switch
        self.order_signer = order_signer
        self.sim_engine = sim_engine

        # Initialize paper account with adaptive strategy
        self.paper_account = PaperAccount()
        self.paper_slippage_bps = paper_slippage_bps
        self.paper_latency_ms = paper_latency_ms
        self.paper_commission_rate = paper_commission_rate
        self.performance_fee_rate = 0.15

        # Paper trading state
        initial_balance = Decimal("1000.0")
        self.paper_account = PaperAccount(initial_balance=initial_balance, cash=initial_balance)
        logger.info(
            f"[BROKER] Paper account initialized | simulate={self.simulate} | initial_balance={initial_balance}"
        )
        self._quotes: dict[str, dict[str, Decimal]] = {}
        self._orderbook_snapshots: dict[str, dict[str, list[tuple[Decimal, Decimal]]]] = {}

        # Redis support for paper account persistence
        self._redis: Any | None = None
        if HAS_REDIS and redis_lib and settings.redis_host:
            try:
                self._redis = redis_lib.Redis(
                    host=settings.redis_host,
                    port=settings.redis_port,
                    password=settings.redis_password,
                    db=settings.redis_db,
                    decode_responses=True,
                )
            except Exception:
                pass

        # WebSocket state
        self._ws_task: asyncio.Task | None = None
        self._ws_running = False
        self._ws_product_ids: list[str] = []
        self._on_order_update: Callable[[dict[str, Any]], Any] | None = None
        self._on_balance_update: Callable[[dict[str, Any]], Any] | None = None
        self._on_market_data: Callable[[dict[str, Any]], Any] | None = None
        self._ws_base_url = "wss://ws-feed.exchange.coinbase.com/"

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _auth_headers(self, *, method: str, path: str) -> dict[str, str]:
        if not self._key_name or not self._private_key_pem:
            raise PermissionError(
                "Missing COINBASE_KEY_NAME / COINBASE_PRIVATE_KEY for live REST mode"
            )
        # Sign order before submission (Standash §5.3)

        parsed = urlparse(self._rest_base)
        full_path = f"{parsed.path.rstrip('/')}{path}"
        raw_key = self._private_key_pem.replace("\\n", "\n")
        token = build_rest_jwt(
            rest_base=self._rest_base,
            method=method,
            path=full_path,
            key_name=self._key_name,
            private_key_pem=raw_key,
        )
        return {"Authorization": f"Bearer {token}"}

    # ========================================================================
    # Paper Trading Simulator
    # ========================================================================

    def update_quote(self, symbol: str, bid: Decimal, ask: Decimal) -> None:
        """Update the current bid/ask quote for a symbol."""
        self._quotes[symbol] = {"bid": bid, "ask": ask}

    def update_orderbook(
        self, symbol: str, bids: list[tuple[Decimal, Decimal]], asks: list[tuple[Decimal, Decimal]]
    ) -> None:
        """Update the orderbook snapshot for realistic fill simulation."""
        self._orderbook_snapshots[symbol] = {"bids": bids, "asks": asks}
        if bids and asks:
            self._quotes[symbol] = {"bid": bids[0][0], "ask": asks[0][0]}

    async def get_paper_balance(self) -> dict[str, Any]:
        """Get current paper trading account state (synced with Redis or Sim Engine)."""
        if self.sim_engine:
            # High-fidelity shared state
            return {
                "cash": float(self.sim_engine._cash),
                "positions": {k: sum(l.qty for l in v) for k, v in self.sim_engine._open_positions.items()},
                "equity": float(self.sim_engine.equity),
                "realized_pnl": float(self.sim_engine.realized_pnl),
                "total_commissions": float(self.sim_engine._total_commissions),
                "order_count": len(self.sim_engine.closed_trades),
                "fill_count": len(self.sim_engine.closed_trades),
            }

        if self._redis:
            try:
                cash_val = await self._redis.get(f"{settings.redis_prefix}:paper_cash")
                if cash_val:
                    self.paper_account.cash = Decimal(cash_val)

                pos_data = await self._redis.hgetall(f"{settings.redis_prefix}:paper_positions")
                if pos_data:
                    self.paper_account.positions = {k: Decimal(v) for k, v in pos_data.items()}
            except Exception:
                pass

        return {
            "cash": float(self.paper_account.cash),
            "positions": {k: float(v) for k, v in self.paper_account.positions.items()},
            "equity": float(self.paper_account.equity),
            "realized_pnl": float(self.paper_account.realized_pnl),
            "total_commissions": float(self.paper_account.total_commissions),
            "order_count": len(self.paper_account.orders),
            "fill_count": sum(len(v) for v in self.paper_account.fills.values()),
        }

    def reset_paper_account(self, initial_balance: Decimal = Decimal("100000.0")) -> None:
        """Reset the paper trading account."""
        self.paper_account = PaperAccount(initial_balance=initial_balance, cash=initial_balance)
        self.paper_account.orders.clear()
        self.paper_account.fills.clear()
        logger.info(f"[BROKER] Paper account reset | initial_balance={initial_balance}")

    def _simulate_fill(self, order: OrderEvent, broker_order_id: str) -> FillEvent | None:
        """Simulate a realistic fill with slippage and commission.

        Returns None if the order should not be filled (e.g., limit order not crossed).
        """
        quote = self._quotes.get(order.symbol, {})
        bid = quote.get("bid", d(0))
        ask = quote.get("ask", d(0))

        # Determine fill price
        if order.order_type and order.order_type.upper() == "MARKET":
            # Market order: take liquidity + slippage
            if order.side and order.side.upper() == "BUY":
                base_price = ask or order.price or d(0)
                slippage = base_price * d(str(self.paper_slippage_bps / 10000))
                price = base_price + slippage
            else:
                base_price = bid or order.price or d(0)
                slippage = base_price * d(str(self.paper_slippage_bps / 10000))
                price = base_price - slippage
        elif order.price is not None:
            # Limit order: fill at limit price or better
            if order.side and order.side.upper() == "BUY" and ask > 0 and order.price >= ask:
                price = ask  # Fill at ask (better than limit)
            elif order.side and order.side.upper() == "SELL" and bid > 0 and order.price <= bid:
                price = bid  # Fill at bid (better than limit)
            else:
                # Limit order not crossed — don't fill
                return None
        elif bid > 0 and ask > 0:
            price = (bid + ask) / d(2)
        else:
            price = order.price or d(0)

        # Performance-Based Fee Model:
        # 0% on entry, 15% of GROSS PROFIT on exit.
        commission = d(0)
        asset = order.symbol.split("-")[0]
        current_qty = self.paper_account.positions.get(asset, d(0))
        avg_entry = self.paper_account.avg_entry_prices.get(asset, d(0))

        is_exit = (current_qty > 0 and order.side == "SELL") or (
            current_qty < 0 and order.side == "BUY"
        )

        if is_exit:
            # Calculate realized gross profit
            closing_qty = min(abs(current_qty), order.quantity)
            if current_qty > 0:
                gross_profit = (price - avg_entry) * closing_qty
            else:
                gross_profit = (avg_entry - price) * closing_qty

            if gross_profit > 0:
                commission = gross_profit * d(str(self.performance_fee_rate))
                # Self-learning: Record win
                self.paper_account.adaptive.record_win(float(gross_profit))
                logger.info(f"[ADAPTIVE] Profit realized. Win streak optimized: {self.paper_account.adaptive.win_streak}")
            else:
                # Self-learning: Record loss
                self.paper_account.adaptive.record_loss(float(gross_profit))
                logger.warning(f"[ADAPTIVE] Loss realized. Loss streak detected: {self.paper_account.adaptive.loss_streak}. Adjusting risk...")

        session_id = (
            getattr(order.payload, "session_id", None) or self.paper_account.active_session_id
        )

        fill = FillEvent(
            source="CoinbasePaperTrading",
            payload=FillPayload(
                order_id=order.order_id or broker_order_id,
                symbol=order.symbol,
                side=order.side or "BUY",
                quantity=order.quantity,
                price=price,
                commission=commission,
                session_id=session_id,
            ),
        )

        # Update paper account
        self.paper_account.update_position(asset, order.quantity, price, order.side or "BUY")
        self.paper_account.total_commissions += commission

        # Sync to Redis if available
        if self._redis:
            asyncio.create_task(self._sync_paper_to_redis(asset))

        self.paper_account.order_history.append(
            {
                "order_id": broker_order_id,
                "symbol": order.symbol,
                "side": order.side,
                "type": order.order_type,
                "qty": float(order.quantity),
                "price": float(order.price) if order.price else None,
                "timestamp": time.time(),
            }
        )
        self.paper_account.fill_history.append(
            {
                "fill_id": fill.payload.order_id,
                "order_id": fill.payload.order_id,
                "symbol": fill.payload.symbol,
                "side": fill.payload.side,
                "qty": float(fill.payload.quantity),
                "price": float(fill.payload.price),
                "commission": float(fill.payload.commission),
                "session_id": fill.payload.session_id,
                "timestamp": time.time(),
            }
        )

        return fill

    async def _sync_paper_to_redis(self, asset: str) -> None:
        """Helper to persist paper state to Redis."""
        if not self._redis:
            return
        try:
            await self._redis.set(
                f"{settings.redis_prefix}:paper_cash", str(self.paper_account.cash)
            )
            await self._redis.hset(
                f"{settings.redis_prefix}:paper_positions",
                asset,
                str(self.paper_account.positions.get(asset, Decimal("0"))),
            )
        except Exception:
            pass

    # ========================================================================
    # Order Management
    # ========================================================================

    async def submit_order(self, order: OrderEvent) -> str:
        """Submit order and return broker order id (simulation/live)."""
        broker_oid = str(uuid.uuid4())
        self.paper_account.orders[broker_oid] = order
        logger.info(
            "Placing %s %s for %s (PAPER TRADING MODE)",
            order.order_type,
            order.side,
            order.symbol,
        )

        if True:  # Forced simulate mode
            # 1. Use high-fidelity shared engine if available
            if self.sim_engine:
                # Mock market state for fill simulation
                ref_symbol = order.symbol
                quote = self._quotes.get(ref_symbol, {})
                market_state = {
                    "bid": float(quote.get("bid", 0.0)),
                    "ask": float(quote.get("ask", 0.0)),
                    "top_depth": 10.0,
                    "venue": "SIMULATED_COINBASE"
                }
                fill = self.sim_engine.simulate_fill(order, market_state)
                return fill.payload.order_id

            # 2. Fallback to basic internal simulation
            # Simulate network latency
            if self.paper_latency_ms > 0:
                await asyncio.sleep(self.paper_latency_ms / 1000.0)

            fill = self._simulate_fill(order=order, broker_order_id=broker_oid)
            if fill is not None:
                self.paper_account.fills.setdefault(broker_oid, []).append(fill)

                # Notify WebSocket listeners
                if self._on_order_update:
                    self._on_order_update(
                        {
                            "type": "order_fill",
                            "order_id": broker_oid,
                            "symbol": order.symbol,
                            "side": order.side,
                            "quantity": float(order.quantity),
                            "price": float(fill.payload.price),
                            "commission": float(fill.payload.commission),
                        }
                    )

            return broker_oid

        # Sign order before submission (Standash §5.3)
        if self.order_signer:
            order_data = {
                "symbol": order.symbol,
                "side": order.side,
                "quantity": str(order.quantity),
                "price": str(order.price) if order.price else None,
                "order_type": order.order_type,
            }
            signed_order = self.order_signer.sign_order(order_data)
            logger.info(
                "Order signed: %s (key=%s, nonce=%d)",
                broker_oid,
                signed_order.signing_key_id,
                self.order_signer._nonce_counter - 1,
            )

        # Live mode: Coinbase Advanced Trade REST (JWT).
        path = "/brokerage/orders"
        url = f"{self._rest_base}{path}"

        client_order_id = order.order_id or broker_oid
        side = (order.side or "BUY").upper()
        if side not in ("BUY", "SELL"):
            raise ValueError(f"Unsupported side: {order.side}")

        order_type = (order.order_type or "MARKET").upper()
        base_size = str(order.quantity)
        if order_type == "MARKET":
            order_config = {"market_market_ioc": {"base_size": base_size}}
        elif order_type == "LIMIT":
            if order.price is None:
                raise ValueError("LIMIT order requires price")
            order_config = {
                "limit_limit_gtc": {
                    "base_size": base_size,
                    "limit_price": str(order.price),
                }
            }
        else:
            raise ValueError(f"Unsupported order_type: {order.order_type}")

        body = {
            "client_order_id": client_order_id,
            "product_id": order.symbol,
            "side": side,
            "order_configuration": order_config,
        }

        session = await self._get_session()
        try:
            resp = await request_json(
                session=session,
                method="POST",
                url=url,
                headers=self._auth_headers(method="POST", path=path),
                json_body=body,
                retry=self._retry,
            )
        except ConnectionError as e:
            logger.critical(f"[COINBASE] CRITICAL: Exchange connection lost: {e}")
            if self.kill_switch:
                self.kill_switch.trigger_on_critical_failure("BROKER_DISCONNECT", str(e))
            raise
        except Exception as e:
            logger.error(f"[COINBASE] Order submit failed: {e}", exc_info=True)
            raise RuntimeError(f"Coinbase order submit failed: {e}")

        if isinstance(resp, dict) and resp.get("success") is True:
            success = resp.get("success_response") or {}
            order_id = success.get("order_id") or success.get("orderId") or ""
            if order_id:
                self.paper_account.orders[order_id] = order
                return str(order_id)
        raise RuntimeError(f"Coinbase order submit failed: {resp}")

    async def cancel_order(self, order_id: str) -> bool:
        logger.info("Canceling order %s (simulate=%s)", order_id, self.simulate)
        if self.simulate:
            self.paper_account.orders.pop(order_id, None)
            return True

        path = "/brokerage/orders/batch_cancel"
        url = f"{self._rest_base}{path}"
        session = await self._get_session()
        resp = await request_json(
            session=session,
            method="POST",
            url=url,
            headers=self._auth_headers(method="POST", path=path),
            json_body={"order_ids": [order_id]},
            retry=self._retry,
        )

        if isinstance(resp, dict):
            results = resp.get("results") or []
            for r in results:
                if str(r.get("order_id") or r.get("orderId") or "") == str(order_id):
                    return bool(r.get("success"))
        raise RuntimeError(f"Coinbase cancel failed: {resp}")

    async def get_fills(self, order_id: str) -> list[FillEvent]:
        if self.simulate:
            return list(self.paper_account.fills.get(order_id, []))

        path = "/brokerage/orders/historical/fills"
        url = f"{self._rest_base}{path}"
        session = await self._get_session()
        resp = await request_json(
            session=session,
            method="GET",
            url=url,
            headers=self._auth_headers(method="GET", path=path),
            params={"order_ids": [order_id]},
            retry=self._retry,
        )

        fills: list[FillEvent] = []
        if not isinstance(resp, dict):
            return fills
        for f in resp.get("fills") or []:
            if str(f.get("order_id") or "") != str(order_id):
                continue
            size = d(str(f.get("size") or "0.0"))
            price = d(str(f.get("price") or "0.0"))
            commission = d(str(f.get("commission") or "0.0"))
            side = str(f.get("side") or "").upper() or "BUY"
            str(f.get("trade_id") or f.get("tradeId") or uuid.uuid4())
            fills.append(
                FillEvent(
                    source="CoinbaseLive",
                    payload=FillPayload(
                        symbol=str(f.get("product_id") or f.get("symbol") or ""),
                        quantity=size,
                        price=price,
                        commission=commission,
                        side=side,
                        order_id=order_id,
                    ),
                )
            )
        return fills

    async def get_balance(self) -> dict:
        if self.simulate:
            # Sync from Redis first
            await self.get_paper_balance()

            # Return flat mapping of Asset -> Quantity for ReconciliationEngine
            balances = {"USD": self.paper_account.cash}
            for asset, qty in self.paper_account.positions.items():
                balances[asset] = qty
            return balances

        path = "/brokerage/accounts"
        url = f"{self._rest_base}{path}"
        session = await self._get_session()
        resp = await request_json(
            session=session,
            method="GET",
            url=url,
            headers=self._auth_headers(method="GET", path=path),
            retry=self._retry,
        )
        balances: dict[str, Decimal] = {}
        if isinstance(resp, dict):
            for acct in resp.get("accounts") or []:
                currency = str(acct.get("currency") or "")
                avail = acct.get("available_balance") or {}
                value = d(str(avail.get("value") or "0.0"))
                if currency:
                    balances[currency] = value
        return balances

    async def close(self) -> None:
        await self.stop_websocket()
        if self._session is not None and not self._session.closed:
            await self._session.close()

    # ========================================================================
    # WebSocket Market Data & Order Updates
    # ========================================================================

    def set_order_update_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Set callback for order update events from WebSocket."""
        self._on_order_update = handler

    def set_balance_update_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Set callback for balance update events from WebSocket."""
        self._on_balance_update = handler

    def set_market_data_handler(self, handler: Callable[[dict[str, Any]], Any]) -> None:
        """Set callback for market data events (level2, ticker)."""
        self._on_market_data = handler

    def add_product(self, product_id: str) -> None:
        """Add a product (e.g., 'BTC-USD') to subscribe to."""
        if product_id not in self._ws_product_ids:
            self._ws_product_ids.append(product_id)

    async def start_websocket(self) -> None:
        """Start WebSocket connection for real-time market data and order updates."""
        if self._ws_running:
            logger.warning("[COINBASE_WS] WebSocket already running, skipping start")
            return
        self._ws_running = True
        self._ws_task = asyncio.create_task(self._websocket_loop())
        logger.info(
            f"[COINBASE_WS] WebSocket loop started | products={self._ws_product_ids} | simulate={self.simulate}"
        )

    async def stop_websocket(self) -> None:
        """Stop WebSocket connection."""
        self._ws_running = False
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
        logger.info("[COINBASE_WS] WebSocket loop stopped")

    async def _websocket_loop(self) -> None:
        """Main WebSocket loop with auto-reconnect and TCP_NODELAY."""
        while self._ws_running:
            try:
                connector = aiohttp.TCPConnector(force_close=True)
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.ws_connect(self._ws_base_url) as ws:
                        transport = ws._response.connection.transport
                        if transport and hasattr(transport, "get_extra_info"):
                            sock = transport.get_extra_info("socket")
                            if sock:
                                sock.setsockopt(6, 1, 1)  # TCP_NODELAY = 1
                                logger.debug("[COINBASE_WS] TCP_NODELAY enabled")

                        logger.info(f"[COINBASE_WS] Connected to {self._ws_base_url}")

                        subscribe_msg = {
                            "type": "subscribe",
                            "product_ids": self._ws_product_ids,
                            "channels": [
                                "level2",
                                "heartbeat",
                                {"name": "ticker", "product_ids": self._ws_product_ids},
                            ],
                        }
                        await ws.send_json(subscribe_msg)
                        logger.info(
                            f"[COINBASE_WS] Subscribed to level2, heartbeat, ticker for {self._ws_product_ids}"
                        )

                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await self._handle_ws_message(json.loads(msg.data))
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                logger.warning(
                                    "[COINBASE_WS] Connection closed/error, reconnecting..."
                                )
                                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[COINBASE_WS] Error: {e}, reconnecting in 5s...")
                await asyncio.sleep(5)

    async def _handle_ws_message(self, data: dict[str, Any]) -> None:
        """Handle incoming WebSocket message from Standard Exchange Feed."""
        msg_type = data.get("type")

        # Market data updates (Ticker)
        if msg_type == "ticker":
            product_id = data.get("product_id", "")
            bid = d(str(data.get("best_bid", "0")))
            ask = d(str(data.get("best_ask", "0")))
            
            # Ensure price is present for TradingSystem handler
            price = d(str(data.get("price", "0")))
            if price <= 0 and bid > 0 and ask > 0:
                price = (bid + ask) / d(2)
                data["price"] = str(price)
            
            if bid > 0 and ask > 0:
                self.update_quote(product_id, bid, ask)

            if self._on_market_data:
                if asyncio.iscoroutinefunction(self._on_market_data):
                    await self._on_market_data(data)
                else:
                    self._on_market_data(data)

        # Level 2 updates (Orderbook)
        elif msg_type in ("l2update", "snapshot"):
            if self._on_market_data:
                self._on_market_data(data)

        # Heartbeat
        elif msg_type == "heartbeat":
            # logger.debug(f"[COINBASE_WS] Heartbeat for {data.get('product_id')}")
            pass
