"""
Loading data to csv file
"""

import os
from datetime import datetime
import pandas as pd
from database.data_service import DataService
from config.config import BACKTESTING_CONFIG


def init_folder(path: str):
    """
    Creates the folder if it does not exist.

    Args:
        path (str): Path to the folder you want to initialize.
    """
    os.makedirs(path, exist_ok=True)


def load_data(from_date, to_date, contract_type, validation=False):
    data_service = DataService()

    print("Loading close price data...")
    close_price = data_service.get_close_price(from_date, to_date, contract_type)
    close_price["date"] = (
        pd.to_datetime(close_price["date"], format="%Y-%m-%d").copy().dt.date
    )

    print("Loading matched data...")
    matched = data_service.get_matched_data(from_date, to_date, contract_type)
    matched = matched.astype({"price": float})

    matched["datetime"] = pd.to_datetime(
        matched["datetime"], format="%Y-%m-%d %H:%M:%S.%f"
    )

    matched = matched.sort_values("datetime")

    # Handle cumulative volume -> incremental trade size
    matched["date"] = matched["datetime"].dt.date

    matched["quantity"] = (
        matched
        .groupby("date")["quantity"]
        .diff()
    )

    matched["quantity"] = matched["quantity"].fillna(0)
    # Quantity should not be negative, if it is, set it to 0
    matched["quantity"] = matched["quantity"].clip(lower=0)

    matched = matched.set_index("datetime")
    matched = matched.reset_index()
    data = calculate_intraday_ohlc(matched)

    is_data = pd.merge(
        data, close_price, on=["date", "tickersymbol"], how="inner", sort=True
    )
    is_data.to_csv(
        (
            f"data/os/{contract_type}_data.csv"
            if validation
            else f"data/is/{contract_type}_data.csv"
        ),
        index=False,
    )

def calculate_intraday_ohlc(data, freq='1min'):
    """
    Calculate intraday OHLC bars from trade data.
    
    Args:
        data (pd.DataFrame): DataFrame with 'datetime' and 'price' columns
        freq (str): Resampling frequency (default: '1min' for 1-minute bars)
    
    Returns:
        pd.DataFrame: DataFrame with datetime, open, high, low, close, volume, and other columns
    """
    data_copy = data.copy()
    data_copy['datetime'] = pd.to_datetime(data_copy['datetime'])
    data_copy = data_copy.set_index('datetime')
    
    # Resample to specified frequency and calculate OHLC
    ohlc = data_copy.groupby(pd.Grouper(freq=freq)).agg({
        'price': ['first', 'max', 'min', 'last'],
        'quantity': 'sum',
        'tickersymbol': 'first',
        'date': 'first'
    })
    
    # Flatten column names
    ohlc.columns = ['open', 'high', 'low', 'close', 'volume', 'tickersymbol', 'date']
    
    # Reset index to make datetime a column
    ohlc = ohlc.reset_index()
    
    # Fill forward price data to handle gaps
    ohlc['open'] = ohlc['open'].ffill()
    ohlc['high'] = ohlc['high'].ffill()
    ohlc['low'] = ohlc['low'].ffill()
    ohlc['close'] = ohlc['close'].ffill()
    
    # Drop rows with no price data
    ohlc = ohlc.dropna(subset=['close'])
    
    return ohlc


if __name__ == "__main__":
    required_directories = [
        "data",
        "data/is",
        "data/os",
        "result/optimization",
        "result/backtest",
        "result/optimization",
    ]
    for dr in required_directories:
        init_folder(dr)

    is_from_date_str = BACKTESTING_CONFIG["is_from_date_str"]
    is_to_date_str = BACKTESTING_CONFIG["is_end_date_str"]
    os_from_date_str = BACKTESTING_CONFIG["os_from_date_str"]
    os_to_date_str = BACKTESTING_CONFIG["os_end_date_str"]
    is_from_date = datetime.strptime(is_from_date_str, "%Y-%m-%d %H:%M:%S").date()
    is_to_date = datetime.strptime(is_to_date_str, "%Y-%m-%d %H:%M:%S").date()
    os_from_date = datetime.strptime(os_from_date_str, "%Y-%m-%d %H:%M:%S").date()
    os_to_date = datetime.strptime(os_to_date_str, "%Y-%m-%d %H:%M:%S").date()

    print("Loading in-sample data")
    load_data(is_from_date, is_to_date, "VN30F1M")
    load_data(is_from_date, is_to_date, "VN30F2M")

    print("Loading out-sample data")
    load_data(os_from_date, os_to_date, "VN30F1M", validation=True)
    load_data(os_from_date, os_to_date, "VN30F2M", validation=True)