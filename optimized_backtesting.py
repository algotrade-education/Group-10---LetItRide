import pandas as pd
import numpy as np
import os
import json
from algo import TradingAlgo

def read_market_data(filepath):
    df = pd.read_csv(filepath)
    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.sort_values('datetime').reset_index(drop=True)
    return df

def calculate_metrics(equity_df):
    if equity_df.empty or len(equity_df) < 2:
        return {}
        
    # Ensure date is a datetime object
    equity_df['date'] = pd.to_datetime(equity_df['date'])
    
    # 1. Calculate Exact Elapsed Time using seconds (Perfect for 1-minute data)
    start_time = equity_df['date'].iloc[0]
    end_time = equity_df['date'].iloc[-1]
    
    total_seconds = (end_time - start_time).total_seconds()
    total_days_elapsed = total_seconds / (24 * 3600)
    
    # If the backtest is shorter than 1 day, we don't annualize (to prevent 10000% bizarre returns)
    # Otherwise, we divide by 365.25 calendar days to get the exact fraction of a year
    years = total_days_elapsed / 365.25 if total_days_elapsed >= 1 else 1.0

    # 2. Resample equity to DAILY to calculate standard financial risk metrics (Sharpe/Sortino)
    daily_equity = equity_df.set_index('date')['equity'].resample('D').last().dropna()
    daily_returns = daily_equity.pct_change().dropna()
    
    # 3. Return metrics
    initial_eq = equity_df['equity'].iloc[0]
    final_eq = equity_df['equity'].iloc[-1]
    
    hpr = (final_eq - initial_eq) / initial_eq
    annual_return = ((final_eq / initial_eq) ** (1 / years)) - 1 if final_eq > 0 else -1
    monthly_return = ((1 + annual_return) ** (1/12)) - 1
    
    # 4. Risk Metrics (Sharpe & Sortino)
    mean_return = daily_returns.mean()
    std_return = daily_returns.std()
    
    annual_rf_rate = 0.06
    daily_rf_rate = (1 + annual_rf_rate) ** (1 / 252.0) - 1
    
    if std_return > 0 and len(daily_returns) > 1:
        sharpe = ((mean_return - daily_rf_rate) / std_return) * np.sqrt(252)
    else:
        sharpe = 0.0
    
    downside_deviations = np.clip(daily_returns - daily_rf_rate, a_min=None, a_max=0)
    downside_risk = np.sqrt(np.mean(downside_deviations**2))
    
    if downside_risk > 0 and len(daily_returns) > 1:
        sortino = ((mean_return - daily_rf_rate) / downside_risk) * np.sqrt(252)
    else:
        sortino = 0.0 if mean_return == 0 else float('inf')
    
    # 5. Maximum Drawdown (MDD) - Calculated tick-by-tick to catch flash crashes
    roll_max = equity_df['equity'].cummax()
    drawdown = (equity_df['equity'] - roll_max) / roll_max
    mdd = drawdown.min()
    
    return {
        "Sharpe Ratio": round(sharpe, 4),
        "Sortino Ratio": round(sortino, 4) if sortino != float('inf') else "Infinity",
        "Maximum Drawdown (MDD)": round(mdd, 4),
        "HPR (%)": round(hpr * 100, 2),
        "Monthly return (%)": round(monthly_return * 100, 2),
        "Annual return (%)": round(annual_return * 100, 2)
    }

def print_evaluation(name, trades_df, metrics, final_asset, initial_asset):
    print(f"\n### {name} Evaluation ###")
    trades_count = len(trades_df[trades_df['type'].str.startswith('OPEN')]) if not trades_df.empty else 0
    print(f"Total Trades Executed: {trades_count}\n")
    
    print("| Metric                 | Value                              |")
    print("|------------------------|------------------------------------|")
    print(f"| Initial Asset          | ${initial_asset:<33,.2f} |")
    print(f"| Final Asset            | ${final_asset:<33,.2f} |")
    
    for key, value in metrics.items():
        print(f"| {key:<22} | {value:<34} |")

def run_backtest(df, name, config):
    simulator = TradingAlgo(
        initial_asset=config["initial_asset"], 
        k_days=config["k_days"], 
        rsi_ob=config["rsi_overbought"],
        rsi_os=config["rsi_oversold"], 
        t_vol=config["volume_multiplier_t"], 
        pat_thresh=config["pattern_threshold"],
        take_profit=config["take_profit_pct"], 
        stop_loss=config["stop_loss_pct"], 
        rsi_w=config["rsi_weight"],
        pat_w=1 - config["rsi_weight"], 
        long_thresh=config["long_confidence_threshold"],
        short_thresh=config["short_confidence_threshold"]
    )

    # Pass the exact minute 'datetime' to the algorithm
    for index, row in df.iterrows():
        simulator.on_tick(row['datetime'], row['open'], row['high'], row['low'], row['close'], row['volume'])

    if not df.empty:
        last_row = df.iloc[-1]
        simulator.close_all_positions(last_row['datetime'], last_row['close'])

    final_asset, trades_df, equity_df = simulator.get_results()
    metrics = calculate_metrics(equity_df)
    
    print_evaluation(name, trades_df, metrics, final_asset, config["initial_asset"])

    # --- GENERATE PLOTS ---
    file_prefix = name.replace(" ", "_").lower()
    
    print(f"Generating charts for {name}...")
    simulator.plot_hpr(path=f"result/optimization/{file_prefix}_hpr.png")
    simulator.plot_drawdown(path=f"result/optimization/{file_prefix}_drawdown.png")
    simulator.plot_inventory(path=f"result/optimization/{file_prefix}_inventory.png")
    
    simulator.plot_price_with_z_thresholds(df, threshold=1.5, path=f"result/optimization/{file_prefix}_price_bands.png", time_col="datetime")
    print(f"Charts saved in the 'result/optimization' folder.")

def main():
    # Load parameters from JSON
    config_path = 'parameter/optimized_parameter.json'
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Error: Could not find configuration file '{config_path}'.")
        return
    except json.JSONDecodeError:
        print(f"Error: '{config_path}' is not a valid JSON file.")
        return

    # Load data
    try:
        df = read_market_data(config["file_path"])
    except FileNotFoundError:
        print(f"Error: Could not find data file '{config['file_path']}'.")
        return

    # Set explicit boundaries from config
    train_start = pd.to_datetime(config["train_start_date"])
    train_end = pd.to_datetime(config["train_end_date"])
    test_start = pd.to_datetime(config["test_start_date"])
    end_dt = pd.to_datetime(config["end_date"])

    # Filter data based on explicit dates using the 'datetime' column
    train_df = df[(df['datetime'] >= train_start) & (df['datetime'] < train_end)].copy()
    test_df = df[(df['datetime'] >= test_start) & (df['datetime'] <= end_dt)].copy()

    # Create the result directory if it doesn't exist
    os.makedirs("result/backtest", exist_ok=True)

    if not train_df.empty:
        run_backtest(train_df, "Train Data", config)
    else:
        print("\nSkipping Train Data: No data found in the specified train date range.")

    if not test_df.empty:
        run_backtest(test_df, "Test Data", config)
    else:
        print("\nSkipping Test Data: No data found in the specified test date range.")

if __name__ == "__main__":
    main()