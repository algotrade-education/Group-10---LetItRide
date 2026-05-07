"""
Optimization module for TradingAlgo
"""

import os
import json
import numpy as np
import pandas as pd
import logging
import optuna
from optuna.samplers import TPESampler

# Import your algorithm
from algo import TradingAlgo

# Load configuration from JSON
with open("parameter/optimization_parameter.json", "r") as f:
    OPTIMIZATION_CONFIG = json.load(f)


class OptunaCallBack:
    """
    Optuna callback class to log results dynamically to a CSV
    """

    def __init__(self) -> None:
        """Init optuna callback"""
        os.makedirs("result/optimization", exist_ok=True)
        
        logging.basicConfig(
            filename="result/optimization/optimization.log.csv",
            format="%(message)s",
            filemode="w",
        )
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)
        self.logger = logger
        
        # We will write the header once the first trial finishes
        self.header_written = False

    def __call__(self, study: optuna.study.Study, trial: optuna.trial.FrozenTrial) -> None:
        """Log trial results"""
        
        if not self.header_written:
            # Dynamically generate headers based on the parameters suggested in the objective
            param_keys = list(trial.params.keys())
            header = "trial_number," + ",".join(param_keys) + ",sharpe_ratio"
            self.logger.info(header)
            self.header_written = True

        param_values = [str(trial.params[k]) for k in trial.params.keys()]
        row = f"{trial.number}," + ",".join(param_values) + f",{trial.value}"
        self.logger.info(row)


def read_market_data(filepath, start_date, end_date):
    """Helper to load and strictly filter data for optimization"""
    df = pd.read_csv(filepath)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    
    # Filter for training period
    mask = (df['date'] >= pd.to_datetime(start_date)) & (df['date'] <= pd.to_datetime(end_date))
    return df[mask].copy()


def calculate_sharpe(equity_df):
    """Calculates annualized Sharpe Ratio directly from the equity curve"""
    if equity_df.empty or len(equity_df) < 2:
        return -99.0 # Heavy penalty for failing to execute
        
    equity_df['return'] = equity_df['equity'].pct_change()
    daily_returns = equity_df['return'].dropna()
    
    mean_return = daily_returns.mean()
    std_return = daily_returns.std()
    
    if std_return > 0:
        return (mean_return / std_return) * np.sqrt(252)
    return 0.0


if __name__ == "__main__":
    
    # Pre-load data once so we aren't reading the CSV 200 times
    print("Loading training data for optimization...")
    TRAIN_DATA = read_market_data(
        OPTIMIZATION_CONFIG["file_path"],
        OPTIMIZATION_CONFIG["train_start_date"],
        OPTIMIZATION_CONFIG["train_end_date"]
    )

    def objective(trial):
        """
        Optuna Objective Function to maximize Sharpe Ratio
        """
        
        # 1. Suggest parameters from the search space
        k_days = trial.suggest_int("k_days", *OPTIMIZATION_CONFIG["k_days"])
        rsi_ob = trial.suggest_int("rsi_ob", *OPTIMIZATION_CONFIG["rsi_overbought"])
        rsi_os = trial.suggest_int("rsi_os", *OPTIMIZATION_CONFIG["rsi_oversold"])
        t_vol = trial.suggest_float("t_vol", *OPTIMIZATION_CONFIG["volume_multiplier_t"])
        pat_thresh = trial.suggest_float("pat_thresh", *OPTIMIZATION_CONFIG["pattern_threshold"])
        tp = trial.suggest_float("tp", *OPTIMIZATION_CONFIG["take_profit_pct"])
        sl = trial.suggest_float("sl", *OPTIMIZATION_CONFIG["stop_loss_pct"])
        
        rsi_w = trial.suggest_float("rsi_w", *OPTIMIZATION_CONFIG["rsi_weight"])
        pat_w = 1.0 - rsi_w # Keep weights normalized to 1.0
        
        long_thresh = trial.suggest_float("long_thresh", *OPTIMIZATION_CONFIG["long_confidence_thresh"])
        short_thresh = trial.suggest_float("short_thresh", *OPTIMIZATION_CONFIG["short_confidence_thresh"])

        # 2. Initialize the simulator with suggested parameters
        simulator = TradingAlgo(
            initial_asset=OPTIMIZATION_CONFIG["initial_asset"], 
            k_days=k_days, 
            rsi_ob=rsi_ob,
            rsi_os=rsi_os, 
            t_vol=t_vol, 
            pat_thresh=pat_thresh,
            take_profit=tp, 
            stop_loss=sl, 
            rsi_w=rsi_w,
            pat_w=pat_w, 
            long_thresh=long_thresh,
            short_thresh=short_thresh
        )

        # 3. Run the backtest loop over the training data
        for index, row in TRAIN_DATA.iterrows():
            simulator.on_tick(
                row['date'], row['open'], row['high'], 
                row['low'], row['close'], row['volume']
            )

        if not TRAIN_DATA.empty:
            last_row = TRAIN_DATA.iloc[-1]
            simulator.close_all_positions(last_row['date'], last_row['close'])

        # 4. Extract results and return Sharpe Ratio
        final_asset, trades_df, equity_df = simulator.get_results()
        sharpe = calculate_sharpe(equity_df)
        
        # Penalize strategies that don't trade to avoid 0.0 Sharpe dead zones
        if len(trades_df) < 5:
            return -99.0 
            
        return sharpe


    print(f"Starting Optuna optimization for {OPTIMIZATION_CONFIG['no_trials']} trials...")
    optunaCallBack = OptunaCallBack()
    
    study = optuna.create_study(
        sampler=TPESampler(seed=OPTIMIZATION_CONFIG["random_seed"]),
        direction="maximize", # Maximizing Sharpe Ratio
    )
    
    study.optimize(
        objective, 
        n_trials=OPTIMIZATION_CONFIG["no_trials"], 
        callbacks=[optunaCallBack]
    )
    
    print("\nOptimization Finished!")
    print("Best Trial:")
    print(f"  Sharpe Ratio: {study.best_trial.value}")
    print("  Parameters: ")
    for key, value in study.best_trial.params.items():
        print(f"    {key}: {value}")