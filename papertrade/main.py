import os
import json
import asyncio
from datetime import datetime
from collections import deque
from dotenv import load_dotenv

from paperbroker.client import PaperBrokerClient
from paperbroker.market_data import KafkaMarketDataClient
from utils import *

load_dotenv()

def buy(client, sub_account_id, symbol, quantity, price):
    print(f"--> [ORDER EXECUTED] BUY {quantity} of {symbol} at {price}")
    with client.use_sub_account(sub_account_id):
        return client.place_order(
            symbol,
            side="BUY",
            qty=quantity,
            price=price
        )

def sell(client, sub_account_id, symbol, quantity, price):
    print(f"--> [ORDER EXECUTED] SELL {quantity} of {symbol} at {price}")
    with client.use_sub_account(sub_account_id):
        return client.place_order(
            symbol,
            side="SELL",
            qty=quantity,
            price=price
        )

class LiveTradingAlgo:
    """A modified version of TradingAlgo that triggers live API orders."""
    def __init__(self, client, sub_account_id, symbol, initial_asset, k_days, rsi_ob, rsi_os, t_vol, 
                 pat_thresh, take_profit, stop_loss, rsi_w, pat_w, long_thresh, short_thresh):
        self.client = client
        self.sub_account_id = sub_account_id
        self.symbol = symbol
        
        self.current_asset = initial_asset
        self.k = k_days 
        self.rsi_ob = rsi_ob
        self.rsi_os = rsi_os
        self.t_vol_multiplier = t_vol
        self.pattern_thresh = pat_thresh
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.rsi_weight = rsi_w
        self.pattern_weight = pat_w
        self.long_thresh = long_thresh
        self.short_thresh = short_thresh
        
        self.price_window = deque(maxlen=self.k + 1)
        self.volume_window = deque(maxlen=self.k + 1)
        self.positions = []

    def _is_shooting_star(self, high, low, close):
        if high == low: return False
        return (high - close) / (high - low) > self.pattern_thresh

    def _is_hammer(self, high, low, open_p, close_p):
        if high == low: return False
        body_top = max(open_p, close_p)
        return (body_top - low) / (high - low) > self.pattern_thresh

    def on_tick(self, timestamp, open_p, high, low, close_p, volume):
        self.price_window.append(close_p)
        self.volume_window.append(volume)

        # Wait for enough data
        if len(self.price_window) < self.k + 1:
            print(f"[{timestamp.strftime('%H:%M')}] Warming up indicators... ({len(self.price_window)}/{self.k + 1})")
            return

        # Calculate Indicators
        diffs = [self.price_window[i] - self.price_window[i-1] for i in range(1, len(self.price_window))]
        gains = sum(d for d in diffs if d > 0) / self.k
        losses = sum(-d for d in diffs if d < 0) / self.k
        rsi = 100.0 if losses == 0 else 100 - (100 / (1 + (gains / losses)))
        
        past_vols = list(self.volume_window)[:-1]
        avg_vol = sum(past_vols) / self.k
        vol_ratio = volume / avg_vol if avg_vol > 0 else 0

        # 1. CHECK OPEN POSITIONS (Take Profit / Stop Loss)
        positions_to_close = []
        for idx, pos in enumerate(self.positions):
            entry_price = pos['entry_price']
            
            if pos['type'] == 'LONG':
                profit_pct = (close_p - entry_price) / entry_price
                if profit_pct >= self.take_profit or profit_pct <= -self.stop_loss:
                    positions_to_close.append(idx)
                    # To close a LONG, we SELL
                    sell(self.client, self.sub_account_id, self.symbol, pos['shares'], close_p)
                    self.current_asset += pos['shares'] * entry_price + (pos['shares'] * (close_p - entry_price))
                    
            elif pos['type'] == 'SHORT':
                profit_pct = (entry_price - close_p) / entry_price
                if profit_pct >= self.take_profit or profit_pct <= -self.stop_loss:
                    positions_to_close.append(idx)
                    # To close a SHORT, we BUY
                    buy(self.client, self.sub_account_id, self.symbol, pos['shares'], close_p)
                    self.current_asset += pos['initial_margin'] + (pos['shares'] * (entry_price - close_p))

        for idx in sorted(positions_to_close, reverse=True):
            self.positions.pop(idx)

        # 2. CHECK FOR NEW SIGNALS
        rsi_confidence = (50 - rsi) / 50.0 
        shoot_star_conf = self._is_shooting_star(high, low, close_p) 
        hammer_conf = self._is_hammer(high, low, open_p, close_p)
        
        aggregate_long_conf = self.rsi_weight * rsi_confidence + self.pattern_weight * hammer_conf
        aggregate_short_conf = self.rsi_weight * -rsi_confidence + self.pattern_weight * shoot_star_conf

        if vol_ratio <= self.t_vol_multiplier:
            if aggregate_short_conf > self.short_thresh:
                trade_amount = self.current_asset * aggregate_short_conf
                shares_to_short = int(trade_amount / close_p)
                if shares_to_short > 0:
                    self.current_asset -= shares_to_short * close_p
                    # To open a SHORT, we SELL
                    sell(self.client, self.sub_account_id, self.symbol, shares_to_short, close_p)
                    self.positions.append({
                        'type': 'SHORT', 'entry_price': close_p, 'shares': shares_to_short, 
                        'initial_margin': shares_to_short * close_p
                    })
                    
            elif aggregate_long_conf > self.long_thresh:
                trade_amount = self.current_asset * aggregate_long_conf
                shares_to_buy = int(trade_amount / close_p)
                if shares_to_buy > 0:
                    self.current_asset -= shares_to_buy * close_p
                    # To open a LONG, we BUY
                    buy(self.client, self.sub_account_id, self.symbol, shares_to_buy, close_p)
                    self.positions.append({'type': 'LONG', 'entry_price': close_p, 'shares': shares_to_buy})

        print(f"[{timestamp.strftime('%H:%M')}] Price: {close_p:.2f} | RSI: {rsi:.2f} | Open Pos: {len(self.positions)}")


from datetime import datetime

def get_vn30f_symbol(month_offset=0):
    """
    Dynamically generates the VN30F symbol based on the current date.
    month_offset=0 gives the current month's contract (e.g., 2605 for May 2026).
    month_offset=1 gives the next month's contract (e.g., 2606 for June 2026).
    """
    now = datetime.now()
    
    # Calculate the target month and handle year rollovers (e.g., Dec to Jan)
    target_month = now.month + month_offset
    target_year = now.year + (target_month - 1) // 12
    target_month = (target_month - 1) % 12 + 1
    
    # Format Year as YY (last two digits) and Month as MM (zero-padded)
    yy = str(target_year)[-2:]
    mm = f"{target_month:02d}"
    
    return f"HNXDS:VN30F{yy}{mm}"

async def main():
    # Setup Broker
    client = PaperBrokerClient(
        default_sub_account=os.getenv("DEFAULT_SUB_ACCOUNT", "D1"),
        username=os.getenv("PAPER_USERNAME", "BL01"),
        password=os.getenv("PAPER_PASSWORD", "123"),
        rest_base_url=os.getenv("PAPER_REST_BASE_URL", "http://localhost:9090"),
        socket_connect_host=os.getenv("SOCKET_HOST", "localhost"),
        socket_connect_port=int(os.getenv("SOCKET_PORT", "5001")),
        sender_comp_id=os.getenv("SENDER_COMP_ID", "cross-FIX"),
        target_comp_id=os.getenv("TARGET_COMP_ID", "SERVER"),
        console=True,
    )

    client.on("fix:logon", lambda session_id, **kw: print(f"✅ Logged in: {session_id}"))
    client.connect()

    if client.wait_until_logged_on(timeout=10):
        cash_data = client.get_cash_balance()
        initial_cash = cash_data.get('remainCash', 0)
        print(f"💰 Available: {initial_cash:,.0f} VND")
        print(client.get_portfolio_by_sub())
    else:
        print("❌ Failed to login to broker.")
        return

    # Setup Market Data
    md_client = KafkaMarketDataClient(
        bootstrap_servers=os.getenv("PAPERBROKER_KAFKA_BOOTSTRAP_SERVERS"),
        username=os.getenv("PAPERBROKER_KAFKA_USERNAME"),
        password=os.getenv("PAPERBROKER_KAFKA_PASSWORD"),
        env_id=os.getenv("PAPERBROKER_ENV_ID"),
        merge_updates=True
    )
    
    symbol = get_vn30f_symbol(0) 
    sub_account = os.getenv("DEFAULT_SUB_ACCOUNT", "D1")
    
    # Load configuration
    try:
        with open('papertrade/parameter/papertrade.json', 'r') as f:
            config = json.load(f)
    except Exception as e:
        print(f"Could not load config: {e}. Using default values.")
        config = {
            "k_days": 14, "rsi_overbought": 70, "rsi_oversold": 30, "volume_multiplier_t": 1.5,
            "pattern_threshold": 0.6, "take_profit_pct": 0.05, "stop_loss_pct": 0.02,
            "rsi_weight": 0.5, "long_confidence_threshold": 0.7, "short_confidence_threshold": 0.7
        }

    # Initialize Live Algorithm
    algo = LiveTradingAlgo(
        client=client, sub_account_id=sub_account, symbol=symbol,
        initial_asset=initial_cash, k_days=config["k_days"], 
        rsi_ob=config["rsi_overbought"], rsi_os=config["rsi_oversold"], 
        t_vol=config["volume_multiplier_t"], pat_thresh=config["pattern_threshold"],
        take_profit=config["take_profit_pct"], stop_loss=config["stop_loss_pct"], 
        rsi_w=config["rsi_weight"], pat_w=1 - config["rsi_weight"], 
        long_thresh=config["long_confidence_threshold"], short_thresh=config["short_confidence_threshold"]
    )

    await md_client.start()
    
    current_minute = None
    minute_open = minute_high = minute_low = minute_close = 0
    minute_volume = 0


    while True:
        try:
            query_result = md_client.query(symbol)
            quote = await query_result if asyncio.iscoroutine(query_result) else query_result
        except Exception as e:
            print(f"Query error: {e}")
            await asyncio.sleep(1)
            continue
        
        if not quote or quote.latest_matched_price is None:
            await asyncio.sleep(0.5)
            continue

        # Extract live data
        price = quote.latest_matched_price
        # Using matched quantity if available, fallback to 1 tick
        vol = getattr(quote, 'latest_matched_quantity', 1) 
        
        now = datetime.now()

        # Initialize the first bar
        if current_minute is None:
            current_minute = now.minute
            minute_open = minute_high = minute_low = minute_close = price
            minute_volume = vol

        # If minute changes, feed the complete bar to the Algo
        if now.minute != current_minute:
            timestamp = now.replace(second=0, microsecond=0)
            algo.on_tick(timestamp, minute_open, minute_high, minute_low, minute_close, minute_volume)
            
            # Reset aggregator for the new minute
            current_minute = now.minute
            minute_open = minute_high = minute_low = minute_close = price
            minute_volume = vol
        else:
            # Update the current minute's bar dynamically
            minute_high = max(minute_high, price)
            minute_low = min(minute_low, price)
            minute_close = price
            minute_volume += vol

        # Sleep slightly so we don't spam the CPU while polling Kafka
        await asyncio.sleep(0.5)

if __name__ == "__main__":
    asyncio.run(main())