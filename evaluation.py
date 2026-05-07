import json
import pandas as pd
import os
from backtesting import calculate_indicators, run_simulation, evaluate

def main():
    ticker = 'AAV'
    print(f"Running out-of-sample evaluation for {ticker}...")
    try:
        df = pd.read_csv(f'data/os/{ticker}_data.csv')
    except FileNotFoundError:
        print("Run data_loader.py first.")
        return
        
    try:
        with open('parameter/optimized_parameter.json', 'r') as f:
            params = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("Run optimization.py first, falling back to backtesting_parameter.json")
        try:
            with open('parameter/backtesting_parameter.json', 'r') as f:
                params = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print("No parameters found.")
            return
            
    df = calculate_indicators(df, params['k_days'])
    initial, asset_df = run_simulation(df, params)
    evaluate(df, asset_df, 'result/optimization')

if __name__ == '__main__':
    main()
