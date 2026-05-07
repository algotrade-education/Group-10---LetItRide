import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from collections import deque

class TradingAlgo:
    def __init__(self, initial_asset, k_days, rsi_ob, rsi_os, t_vol, pat_thresh, 
                 take_profit, stop_loss, rsi_w, pat_w, long_thresh, short_thresh):
        self.initial_asset = initial_asset
        self.current_asset = initial_asset
        # NOTE: Since you are feeding 1-minute data, k_days is now effectively k_minutes.
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
        self.trade_history = []
        self.equity_curve = [] # Tracks portfolio value and inventory per minute

    def _is_shooting_star(self, high, low, close):
        if high == low: return False
        return (high - close) / (high - low) > self.pattern_thresh

    def _is_hammer(self, high, low, open_p, close_p):
        if high == low: return False
        body_top = max(open_p, close_p)
        return (body_top - low) / (high - low) > self.pattern_thresh

    def _get_total_asset_value(self, current_price, active_positions=None):
        if active_positions is None:
            active_positions = self.positions
            
        total = self.current_asset
        for p in active_positions:
            if p['type'] == 'LONG':
                total += p['shares'] * current_price
            elif p['type'] == 'SHORT':
                pnl = p['shares'] * (p['entry_price'] - current_price)
                total += p['initial_margin'] + pnl
        return total

    def on_tick(self, timestamp, open_p, high, low, close_p, volume):
        self.price_window.append(close_p)
        self.volume_window.append(volume)

        # If we don't have enough data yet, log cash and zero inventory
        if len(self.price_window) < self.k + 1:
            self.equity_curve.append({'date': timestamp, 'equity': self.current_asset, 'inventory': 0})
            return

        diffs = [self.price_window[i] - self.price_window[i-1] for i in range(1, len(self.price_window))]
        gains = sum(d for d in diffs if d > 0) / self.k
        losses = sum(-d for d in diffs if d < 0) / self.k
        
        rsi = 100.0 if losses == 0 else 100 - (100 / (1 + (gains / losses)))
        
        past_vols = list(self.volume_window)[:-1]
        avg_vol = sum(past_vols) / self.k
        vol_ratio = volume / avg_vol if avg_vol > 0 else 0

        positions_to_close = []
        for idx, pos in enumerate(self.positions):
            entry_price = pos['entry_price']
            
            if pos['type'] == 'LONG':
                profit_pct = (close_p - entry_price) / entry_price
                if profit_pct >= self.take_profit or profit_pct <= -self.stop_loss:
                    positions_to_close.append(idx)
                    pnl = pos['shares'] * (close_p - entry_price)
                    self.current_asset += pos['shares'] * entry_price + pnl
                    self.trade_history.append({
                        'date': timestamp, 'type': 'CLOSE_LONG', 'price': close_p, 'pnl': pnl
                    })
                    
            elif pos['type'] == 'SHORT':
                profit_pct = (entry_price - close_p) / entry_price
                if profit_pct >= self.take_profit or profit_pct <= -self.stop_loss:
                    positions_to_close.append(idx)
                    pnl = pos['shares'] * (entry_price - close_p)
                    self.current_asset += pos['initial_margin'] + pnl
                    self.trade_history.append({
                        'date': timestamp, 'type': 'CLOSE_SHORT', 'price': close_p, 'pnl': pnl
                    })

        for idx in sorted(positions_to_close, reverse=True):
            self.positions.pop(idx)

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
                    self.positions.append({
                        'type': 'SHORT', 'entry_price': close_p, 'entry_date': timestamp, 
                        'shares': shares_to_short, 'initial_margin': shares_to_short * close_p
                    })
                    self.trade_history.append({'date': timestamp, 'type': 'OPEN_SHORT', 'price': close_p})
                    
            elif aggregate_long_conf > self.long_thresh:
                trade_amount = self.current_asset * aggregate_long_conf
                shares_to_buy = int(trade_amount / close_p)
                if shares_to_buy > 0:
                    self.current_asset -= shares_to_buy * close_p
                    self.positions.append({'type': 'LONG', 'entry_price': close_p, 'entry_date': timestamp, 'shares': shares_to_buy})
                    self.trade_history.append({'date': timestamp, 'type': 'OPEN_LONG', 'price': close_p})

        # Calculate net inventory (Positive for Long, Negative for Short)
        net_inventory = sum(p['shares'] for p in self.positions if p['type'] == 'LONG') - \
                        sum(p['shares'] for p in self.positions if p['type'] == 'SHORT')

        current_total = self._get_total_asset_value(close_p)
        self.equity_curve.append({'date': timestamp, 'equity': current_total, 'inventory': net_inventory})

    def close_all_positions(self, final_date, final_price):
        for pos in self.positions:
            if pos['type'] == 'LONG':
                pnl = pos['shares'] * (final_price - pos['entry_price'])
                self.current_asset += pos['shares'] * pos['entry_price'] + pnl
                self.trade_history.append({'date': final_date, 'type': 'FORCE_CLOSE_LONG', 'price': final_price, 'pnl': pnl})
            elif pos['type'] == 'SHORT':
                pnl = pos['shares'] * (pos['entry_price'] - final_price)
                self.current_asset += pos['initial_margin'] + pnl
                self.trade_history.append({'date': final_date, 'type': 'FORCE_CLOSE_SHORT', 'price': final_price, 'pnl': pnl})
        
        self.positions = []
        self.equity_curve.append({'date': final_date, 'equity': self.current_asset, 'inventory': 0})

    def get_results(self):
        return self.current_asset, pd.DataFrame(self.trade_history), pd.DataFrame(self.equity_curve)

    # --- PLOTTING FUNCTIONS ---

    def plot_hpr(self, path="result/hpr.png"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        df = pd.DataFrame(self.equity_curve)
        if df.empty: return
        
        df['date'] = pd.to_datetime(df['date']) # Ensure proper datetime format
        df['hpr'] = (df['equity'] / self.initial_asset - 1) * 100
        
        plt.figure(figsize=(10, 6))
        plt.plot(df['date'], df['hpr'], color='black', label="Portfolio")
        plt.title('Holding Period Return Over Time')
        plt.xlabel('Time')
        plt.ylabel('Holding Period Return (%)')
        plt.grid(True)
        plt.legend()
        plt.gcf().autofmt_xdate() # Auto-rotates timestamps so they don't overlap
        plt.savefig(path, dpi=300, bbox_inches='tight')
        plt.close()

    def plot_drawdown(self, path="result/drawdown.png"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        df = pd.DataFrame(self.equity_curve)
        if df.empty: return
        
        df['date'] = pd.to_datetime(df['date'])
        roll_max = df['equity'].cummax()
        df['drawdown'] = (df['equity'] - roll_max) / roll_max * 100
        
        plt.figure(figsize=(10, 6))
        plt.plot(df['date'], df['drawdown'], color='black', label="Drawdown")
        plt.title('Drawdown Value Over Time')
        plt.xlabel('Time')
        plt.ylabel('Percentage (%)')
        plt.grid(True)
        plt.legend()
        plt.gcf().autofmt_xdate()
        plt.savefig(path, dpi=300, bbox_inches='tight')
        plt.close()

    def plot_inventory(self, path="result/inventory.png"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        df = pd.DataFrame(self.equity_curve)
        if df.empty: return
        
        df['date'] = pd.to_datetime(df['date'])
        
        plt.figure(figsize=(10, 6))
        plt.plot(df['date'], df['inventory'], color='black', label="Net Exposure")
        plt.title('Inventory (Net Shares) Over Time')
        plt.xlabel('Time')
        plt.grid(True)
        plt.legend()
        plt.gcf().autofmt_xdate()
        plt.tight_layout()
        plt.savefig(path, dpi=300, bbox_inches='tight')
        plt.close()

    def plot_price_with_z_thresholds(self, data: pd.DataFrame, threshold=1.5, path="result/price_with_z_thresholds.png", price_col="close", time_col="datetime"):
        """Calculates Z-score bands purely for visualization against the raw data"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        plot_data = data.copy()
        
        # Fallback if the user passes 'date' instead of 'datetime'
        if time_col not in plot_data.columns and "date" in plot_data.columns:
            time_col = "date"
            
        x_axis = pd.to_datetime(plot_data[time_col])
        price_series = pd.to_numeric(plot_data[price_col], errors="coerce")
        
        rolling_mean = price_series.rolling(window=self.k, min_periods=self.k).mean()
        rolling_std = price_series.rolling(window=self.k, min_periods=self.k).std(ddof=0)
        
        z_threshold = float(threshold)
        upper_threshold = rolling_mean + z_threshold * rolling_std
        lower_threshold = rolling_mean - z_threshold * rolling_std
        
        fig, ax_price = plt.subplots(figsize=(12, 6))
        ax_price.plot(x_axis, price_series, label="Price", color="black", linewidth=1.1)
        ax_price.plot(x_axis, upper_threshold, label=f"Upper z-threshold (+{z_threshold})", color="red", linestyle="--", linewidth=1.0)
        ax_price.plot(x_axis, lower_threshold, label=f"Lower z-threshold (-{z_threshold})", color="blue", linestyle="--", linewidth=1.0)
        
        ax_price.set_title("Price With Z-Score Threshold Bands")
        ax_price.set_xlabel("Time")
        ax_price.set_ylabel("Price")
        ax_price.grid(True, alpha=0.3)
        ax_price.legend(loc="best")
        
        fig.autofmt_xdate() # Auto-rotates timestamps
        fig.tight_layout()
        fig.savefig(path, dpi=300, bbox_inches="tight")
        plt.close(fig)