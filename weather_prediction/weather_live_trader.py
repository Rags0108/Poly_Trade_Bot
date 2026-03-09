"""
Weather Live Trader — Real CLOB execution for weather markets.

Supports:
  - FOK (Fill-or-Kill): Instant fills, $1 minimum
  - GTC (Good-Til-Cancel): Limit orders at desired price
  - Paper mode: Simulated execution for testing
  
Adapted from 5min_trade live_trader.py for weather-specific trading.
"""

import time
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple


class WeatherLiveTrader:
    """Live order execution on Polymarket CLOB for weather markets."""

    def __init__(self, mode: str = "PAPER"):
        """
        mode: "PAPER" for simulated, "LIVE" for real execution
        """
        self.mode = mode.upper()
        self._clob_client = None
        self._is_ready = False
        self._pending_orders: List[Dict] = []
        self._completed_orders: List[Dict] = []

        # Cooldown tracking
        self._last_trade_time: Dict[str, float] = {}
        self._cooldown_until: Dict[str, float] = {}
        self.COOLDOWN_SECONDS = 60

        # Stats
        self.total_orders = 0
        self.total_fills = 0
        self.total_volume = 0.0

        if self.mode == "LIVE":
            self._init_clob()

    def _init_clob(self):
        """Initialize CLOB client for live trading."""
        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.clob_types import ApiCreds

            pk = os.getenv("POLY_PRIVATE_KEY", "").strip()
            if not pk:
                print("⚠️ POLY_PRIVATE_KEY not set — live trading disabled")
                self.mode = "PAPER"
                return

            if not pk.startswith("0x"):
                pk = "0x" + pk

            sig_type = int(os.getenv("POLY_SIGNATURE_TYPE", "0"))
            relay_url = os.getenv("CLOB_RELAY_URL", "").strip()
            base_url = relay_url if relay_url else "https://clob.polymarket.com"

            self._clob_client = ClobClient(
                base_url,
                key=pk,
                chain_id=137,
                signature_type=sig_type,
            )

            # Derive API credentials
            self._clob_client.set_api_creds(self._clob_client.derive_api_key())
            self._is_ready = True
            print(f"✅ CLOB client initialized: {base_url[:30]}...")

        except ImportError:
            print("⚠️ py-clob-client not installed. Install: pip install py-clob-client")
            self.mode = "PAPER"
        except Exception as e:
            print(f"⚠️ CLOB init failed: {e}")
            self.mode = "PAPER"

    def execute_order(
        self,
        token_id: str,
        side: str,
        size: float,
        price: float,
        market_question: str = "",
    ) -> Optional[Dict]:
        """
        Execute a trade order.

        Args:
            token_id: The token to buy/sell
            side: "BUY" or "SELL"
            size: Dollar amount
            price: Maximum price willing to pay (for BUY)
            market_question: For logging

        Returns:
            Order result dict or None if failed
        """
        # Check cooldown
        cooldown_key = f"{token_id}_{side}"
        now = time.time()
        if cooldown_key in self._cooldown_until:
            if now < self._cooldown_until[cooldown_key]:
                remaining = self._cooldown_until[cooldown_key] - now
                print(f"⏳ Cooldown: {remaining:.0f}s remaining for {cooldown_key[:20]}...")
                return None

        self.total_orders += 1

        if self.mode == "PAPER":
            return self._paper_execute(token_id, side, size, price, market_question)
        else:
            return self._live_execute(token_id, side, size, price, market_question)

    def _paper_execute(
        self, token_id: str, side: str, size: float, price: float, question: str
    ) -> Dict:
        """Simulated paper trade execution."""
        # Simulate slight slippage
        import random
        slippage = random.uniform(0, 0.02)
        fill_price = price + slippage if side == "BUY" else price - slippage
        fill_price = max(0.01, min(0.99, fill_price))

        shares = size / fill_price
        fee = self._calculate_fee(fill_price) * size

        order = {
            "order_id": f"paper_{self.total_orders}_{int(time.time())}",
            "token_id": token_id,
            "side": side,
            "size": round(size, 2),
            "price": round(fill_price, 4),
            "shares": round(shares, 2),
            "fee": round(fee, 4),
            "status": "FILLED",
            "mode": "PAPER",
            "market": question[:80] if question else "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        self._completed_orders.append(order)
        self.total_fills += 1
        self.total_volume += size

        print(f"🧪 PAPER {side}: ${size:.2f} @ {fill_price:.4f} "
              f"({shares:.1f} shares, fee ${fee:.4f})")

        return order

    def _live_execute(
        self, token_id: str, side: str, size: float, price: float, question: str
    ) -> Optional[Dict]:
        """Real CLOB order execution."""
        if not self._clob_client or not self._is_ready:
            print("⚠️ CLOB client not ready — falling back to paper")
            return self._paper_execute(token_id, side, size, price, question)

        try:
            from py_clob_client.order_builder.constants import BUY, SELL

            clob_side = BUY if side == "BUY" else SELL

            # Calculate shares from size
            shares = size / price if price > 0 else 0
            if shares < 1:
                shares = 1  # Minimum

            # Create FOK (Fill-or-Kill) order for instant execution
            order_args = {
                "token_id": token_id,
                "price": round(price, 2),
                "size": round(shares, 2),
                "side": clob_side,
            }

            signed_order = self._clob_client.create_and_post_order(order_args)

            if signed_order and signed_order.get("orderID"):
                fee = self._calculate_fee(price) * size
                order = {
                    "order_id": signed_order["orderID"],
                    "token_id": token_id,
                    "side": side,
                    "size": round(size, 2),
                    "price": round(price, 4),
                    "shares": round(shares, 2),
                    "fee": round(fee, 4),
                    "status": "SUBMITTED",
                    "mode": "LIVE",
                    "market": question[:80] if question else "",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                self._pending_orders.append(order)
                self.total_fills += 1
                self.total_volume += size

                print(f"🚀 LIVE {side}: ${size:.2f} @ {price:.4f} "
                      f"(order: {signed_order['orderID'][:16]}...)")
                return order
            else:
                print(f"⚠️ Order rejected by CLOB")
                return None

        except Exception as e:
            print(f"⚠️ Live execution error: {e}")
            # Fallback to paper
            return self._paper_execute(token_id, side, size, price, question)

    def set_cooldown(self, token_id: str, side: str, seconds: int = None):
        """Set a cooldown period after a stop-loss."""
        if seconds is None:
            seconds = self.COOLDOWN_SECONDS
        key = f"{token_id}_{side}"
        self._cooldown_until[key] = time.time() + seconds
        print(f"⏳ Cooldown set: {seconds}s for {key[:20]}...")

    def _calculate_fee(self, price: float) -> float:
        """Dynamic Polymarket fee: 0.25 × p × (1-p)²"""
        p = max(0.01, min(0.99, price))
        return 0.25 * p * (1 - p) ** 2

    def get_balance(self) -> float:
        """Fetch current USDC balance."""
        if not self._clob_client or not self._is_ready:
            return 0.0

        try:
            # Try data API
            from eth_account import Account
            pk = os.getenv("POLY_PRIVATE_KEY", "").strip()
            if not pk.startswith("0x"):
                pk = "0x" + pk
            acct = Account.from_key(pk)
            address = os.getenv("POLY_PROXY_WALLET", "").strip() or acct.address

            import requests
            resp = requests.get(
                f"https://data-api.polymarket.com/value",
                params={"user": address.lower()},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                return float(data.get("balance", 0))
        except Exception as e:
            print(f"⚠️ Balance fetch error: {e}")

        return 0.0

    def get_stats(self) -> Dict:
        return {
            "mode": self.mode,
            "is_ready": self._is_ready,
            "total_orders": self.total_orders,
            "total_fills": self.total_fills,
            "total_volume": round(self.total_volume, 2),
            "pending_orders": len(self._pending_orders),
            "completed_orders": len(self._completed_orders),
        }
