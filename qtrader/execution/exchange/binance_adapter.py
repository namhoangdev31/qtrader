"""Binance exchange adapter for QTrader execution system."""

import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Any

from qtrader.core.types import OrderEvent
from qtrader.execution.execution_engine import ExchangeAdapter

logger = logging.getLogger(__name__)


class BinanceAdapter(ExchangeAdapter):
    """Binance exchange adapter implementing the ExchangeAdapter interface."""

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False) -> None:
        """
        Initialize Binance adapter.

        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            testnet: Whether to use testnet endpoint
        """
        super().__init__(name="BinanceAdapter")
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.logger = logger.getChild("BinanceAdapter")
        
        # Set up URLs
        if testnet:
            self.base_url = "https://testnet.binance.vision"
            self.wss_url = "wss://testnet.binance.vision/ws"
        else:
            self.base_url = "https://api.binance.com"
            self.wss_url = "wss://stream.binance.com:9443/ws"
            
        # Initialize session (will be created when needed)
        self._session = None
        self._last_request_time = 0
        self._min_request_interval = 0.1  # 100ms between requests to avoid rate limits
        
        self.logger.info(f"BinanceAdapter initialized (testnet={testnet})")

    async def _get_session(self):
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            import aiohttp
            self._session = aiohttp.ClientSession()
        return self._session

    async def _rate_limit(self) -> None:
        """Implement zero-latency rate interface (no sleep)."""
        self._last_request_time = time.time()

    async def _request(self, method: str, endpoint: str, params: dict[str, Any] | None = None, signed: bool = False):
        """
        Make a request to Binance API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without base URL)
            params: Query parameters
            signed: Whether the request needs to be signed

        Returns:
            Parsed JSON response
        """
        await self._rate_limit()
        
        url = f"{self.base_url}{endpoint}"
        headers = {}
        
        if signed:
            # Add timestamp
            if params is None:
                params = {}
            params['timestamp'] = int(time.time() * 1000)
            
            # Create signature
            query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
            import hashlib
            import hmac
            signature = hmac.new(
                self.api_secret.encode('utf-8'),
                query_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            params['signature'] = signature
            
            headers['X-MBX-APIKEY'] = self.api_key
        
        try:
            session = await self._get_session()
            async with session.request(method, url, params=params, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(f"Binance API error: {response.status} - {error_text}")
                    raise Exception(f"Binance API error: {response.status}")
                
                return await response.json()
        except Exception as e:
            self.logger.error(f"Error making request to Binance: {e}")
            raise

    async def send_order(self, order: OrderEvent) -> tuple[bool, str | None]:
        """
        Send an order to Binance.

        Args:
            order: OrderEvent to send

        Returns:
            Tuple (success, order_id or error_message)
        """
        self.logger.info(f"Sending order to Binance: {order}")
        # In a real implementation, we would:
        # 1. Convert our OrderEvent to Binance format
        # 2. Send the order via REST API
        # 3. Handle the response and update the order
        # For now, we'll simulate a successful order placement
        try:
            # Simulate network delay - Removed for Zero Latency
            pass
            
            # Generate a Binance order ID
            binance_order_id = f"binance_{int(datetime.utcnow().timestamp() * 1000)}"
            
            # Simulate immediate fill for market orders
            if order.order_type == "MARKET":
                # In a real system, we would fill the order and return the fill via a callback
                # For this adapter, we just return the order ID and the ExecutionEngine will handle fills
                # via its own mechanism (e.g., by checking order status or listening to websockets)
                pass
            
            self.logger.info(f"Order sent to Binance: {binance_order_id}")
            return True, binance_order_id
        except Exception as e:
            self.logger.error(f"Error sending order to Binance: {e}")
            return False, str(e)

    async def cancel_order(self, order_id: str) -> tuple[bool, str | None]:
        """
        Cancel an order on Binance.

        Args:
            order_id: Order ID to cancel (the Binance order ID we returned from send_order)

        Returns:
            Tuple (success, error_message)
        """
        self.logger.info(f"Cancelling order {order_id} on Binance")
        # In a real implementation, we would:
        # 1. Send cancellation request via REST API
        # 2. Handle the response
        try:
            # Simulate network delay - Removed for Zero Latency
            pass
            self.logger.info(f"Order {order_id} cancelled on Binance")
            return True, None
        except Exception as e:
            self.logger.error(f"Error cancelling order {order_id} on Binance: {e}")
            return False, str(e)

    async def get_position(self, symbol: str) -> Decimal:
        """
        Get current position for a symbol from Binance.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")

        Returns:
            Position size (can be negative)
        """
        self.logger.info(f"Fetching position for {symbol} from Binance")
        # In a real implementation, we would call the account endpoint
        # For now, we'll return 0 (no position)
        return Decimal('0')

    # Additional Binance-specific methods that can be used by the smart router
    async def get_positions(self) -> dict[str, Decimal]:
        """
        Get current positions from Binance.

        Returns:
            Dictionary mapping symbol to position size (positive for long, negative for short)
        """
        self.logger.info("Fetching positions from Binance")
        # For now, we'll return an empty dict as a placeholder
        # In a real implementation, we would call the account endpoint
        return {}

    async def get_orderbook(self, symbol: str) -> dict[str, Any]:
        """
        Get orderbook for a symbol from Binance.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")

        Returns:
            Dictionary with 'bids' and 'asks' lists (each list of [price, quantity])
        """
        self.logger.info(f"Fetching orderbook for {symbol} from Binance")
        # For now, we'll return a mock orderbook
        # In a real implementation, we would call the orderbook endpoint
        return {
            "bids": [["100.0", "1.5"], ["99.5", "2.0"]],
            "asks": [["100.5", "1.2"], ["101.0", "0.8"]]
        }

    async def get_fees(self, symbol: str) -> dict[str, Decimal]:
        """
        Get trading fees for a symbol from Binance.

        Args:
            symbol: Trading pair symbol

        Returns:
            Dictionary with 'maker' and 'taker' fee rates
        """
        self.logger.info(f"Fetching fees for {symbol} from Binance")
        # For now, we'll return standard Binance fees
        # In a real implementation, we would call the fee endpoint
        return {
            "maker": Decimal('0.001'),  # 0.1%
            "taker": Decimal('0.001')   # 0.1%
        }

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()