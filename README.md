# Let It Ride - Group 2

> A Confidence-Weighted Algorithmic Strategy Using Momentum and Price Action

## Abstract

Let It Ride is a multi-factor algorithmic trading strategy designed to identify high-probability entry points by blending momentum oscillators, volume analysis, and candlestick geometry. The strategy utilizes the Relative Strength Index (RSI) to gauge market momentum and specific price action patterns—Shooting Stars and Hammers—to detect potential reversals. Unlike static strategies, "Let It Ride" calculates a dynamic Confidence Score for every trade, which determines the capital allocation (position sizing) for each entry. A volume filter is applied to ensure trades are only executed when market activity aligns with the strategy’s parameters, preventing entries during periods of extreme, irrational volatility. Risk is managed through a disciplined framework of fixed percentage take-profit and stop-loss thresholds.

## Introduction

Markets are driven by a combination of statistical momentum and psychological exhaustion. A strategy that relies solely on indicators often misses the "human" element of price rejection, while a strategy based only on patterns lacks statistical grounding.

Let It Ride is a multi-factor algorithmic strategy designed for the VN30 Futures market It blends the Relative Strength Index (RSI) with Candlestick Pattern Recognition to identify high-probability reversal points. Rather than using fixed position sizes, the strategy calculates a Confidence Score that dictates how much capital to risk on any given trade. By applying a volume filter, the strategy ensures it only enters trades when market participation is "healthy" and not undergoing an irrational blow-off phase.

## Hypothesis

Momentum Exhaustion: When RSI deviates significantly from the midpoint (50), the price is increasingly likely to undergo a mean-reversion move.

Price Rejection: Long wicks (Hammers and Shooting Stars) provide visual evidence that a trend is losing steam and that counter-parties are taking control.Volume Validation: High-volume spikes often precede "exhaustion gaps." 

By limiting entries during extreme volume ($t$), the strategy avoids "catching falling knives."Confidence Sizing: Not all signals are equal. 

A trade where both RSI and a Candlestick pattern align deserves a larger capital allocation than a trade based on a single factor.

## Trading Logic
The strategy merges statistical momentum with geometric price action.

### 1. Indicators
* **RSI Confidence:** Calculated as the normalized distance from the 50-level.
    $$RSI_{conf} = \frac{|50 - RSI|}{50}$$
* **Volume Ratio:** Comparing current volume to the $k$-day moving average.
    $$Vol_{ratio} = \frac{Volume}{MA_{k}(Volume)}$$

### 2. Pattern Detection
The strategy uses a `PATTERN_THRESHOLD` (e.g., 0.6) to identify significant wicks.
* **Shooting Star (Short Signal):** $\frac{High - Close}{High - Low} > Threshold$
* **Hammer (Long Signal):** $\frac{Body\_Top - Low}{High - Low} > Threshold$

### 3. Entry Rules
Entries are triggered only if $Vol_{ratio} \le t$.
* **LONG:** $(RSI_{weight} \times RSI_{conf}) + (Pattern_{weight} \times Hammer) > Long\_Threshold$
* **SHORT:** $(RSI_{weight} \times RSI_{conf}) + (Pattern_{weight} \times ShootingStar) > Short\_Threshold$

### 4. Exit Logic
Positions are closed based on fixed risk-to-reward parameters:
* **Take Profit:** 10%
* **Stop Loss:** 5%
* **Force Close:** Positions are liquidated on the final day of the simulation.

## Data
* **Data Source:** Algotrade database
* **Asset:** VN30F
* **Period:** 2021-02-17 to 2024-02-17
* **Frequency:** 1-min HLCV (Open, High, Low, Close, Volume)

## Where to find this data

Data is store locally at data/data.csv

## Implementation

### Environment Setup

1. Set up python virtual environment

```bash
python -m venv venv
source venv/bin/activate # for Linux/MacOS
.\venv\Scripts\activate.bat # for Windows command line
.\venv\Scripts\Activate.ps1 # for Windows PowerShell
```

2. Install the required packages. This requires the paperbroker client package, which can be installed from [here](https://papertrade.algotrade.vn/static/docs/downloads/paperbroker_client-0.2.4-py3-none-any.64a14680f78f.whl).

```bash
pip install -r requirements.txt
pip install paperbroker_client-0.2.4-py3-none-any.whl
```

3. Create `.env` file in the root directory of the project and fill in the required information. The `.env` file is used to store environment variables that are used in the project. The following is an example of a `.env` file:

```env
PAPER_USERNAME=<paperbroker_password>
PAPER_PASSWORD=<paperbroker_username>
DEFAULT_SUB_ACCOUNT=<default_sub_account>

PAPER_REST_BASE_URL=<paperbroker_rest_base_url>
SOCKET_HOST=<paperbroker_socket_host>
SOCKET_PORT=<paperbroker_socket_port>

SENDER_COMP_ID=<paperbroker_sender_comp_id>
TARGET_COMP_ID=<paperbroker_target_comp_id>

PAPERBROKER_KAFKA_BOOTSTRAP_SERVERS=<kafka_bootstrap_servers>
PAPERBROKER_KAFKA_USERNAME=<kafka_username>
PAPERBROKER_KAFKA_PASSWORD=<kafka_password>
PAPERBROKER_ENV_ID=<paperbroker_env_id>

MARKET_REDIS_HOST=<redis_host>
MARKET_REDIS_PORT=<redis_port>
MARKET_REDIS_PASSWORD=<redis_password>
```

## In-sample Backtesting

Specify period and parameters in `parameter/backtesting_parameter.json` file. If test_start_date and test_end_date is set, then out-of-sample backtest will also been run.

```bash
python backtesting.py
```

The results are stored in the `result/backtest/` folder.

### Evaluation Metrics

- Backtesting results are stored in the `result/backtest/` folder.
- Used metrics:
  - Sortino ratio (SoR)
  - Maximum drawdown (MDD)
- We use a risk-free rate of 6% per annum, equivalent to approximately 0.023% per day, as a benchmark for evaluating the Sharpe Ratio (SR) and Sortino Ratio (SoR).

### In-sample Backtesting Result

Here is the result for the backtesting with the parameter defined in parameter/backtesting_parameter.json.

```
| Metric                 | Value                              |
|------------------------|------------------------------------|
| Initial Asset          | $10,000.00                         |
| Final Asset            | $11,716.00                         |
| Sharpe Ratio           | 0.6094                             |
| Sortino Ratio          | 0.8131                             |
| Maximum Drawdown (MDD) | -0.187                             |
| HPR (%)                | 17.16                              |
| Monthly return (%)     | 1.35                               |
| Annual return (%)      | 17.42                              |
```

## Optimization

The strategy parameters are optimized using the in-sample data to maximize risk-adjusted returns. The configuration for optimization is stored in `parameter/optimization_parameter.json`. A random seed is used for reproducibility. The optimized parameters are stored in `parameter/optimized_parameter.json`.

The optimization process can be reproduced by executing:

```bash
python optimization.py
```

### Optimization Result

The current best result for seed 2024 is as follow.

```
{
    "file_path": "data/data.csv",
    "train_start_date": "2022-01-04",
    "train_end_date": "2023-01-04",
    "test_start_date": "2024-01-04",
    "end_date": "2025-01-04",
    "k_days": 11,
    "rsi_overbought": 78,
    "rsi_oversold": 16,
    "volume_multiplier_t": 2.2880202432981416,
    "pattern_threshold": 0.7320011152862379,
    "initial_asset": 10000.0,
    "take_profit_pct": 0.02206918257898533,
    "stop_loss_pct": 0.019322090918190753,
    "rsi_weight": 0.13308597399857056,
    "long_confidence_threshold": 0.6487354737357189,
    "short_confidence_threshold":  0.6568967787274855
}
```

Here the result for the result above:

```
| Metric                 | Value                              |
|------------------------|------------------------------------|
| Initial Asset          | $10,000.00                         |
| Final Asset            | $11,197.20                         |
| Sharpe Ratio           | 0.6399                             |
| Sortino Ratio          | 0.9971                             |
| Maximum Drawdown (MDD) | -0.0488                            |
| HPR (%)                | 11.97                              |
| Monthly return (%)     | 0.95                               |
| Annual return (%)      | 11.97                              |
```

## Out-of-sample Backtesting

Specify period and parameters in `parameter/backtesting_parameter.json` file. Only if test_start_date and test_end_date is set, then out-of-sample backtest will also been run.

```bash
python backtesting.py
```

The results are stored in the `result/backtest/` folder.

### Out-of-sample Backtesting Result

```
| Metric                 | Value                              |
| Initial Asset          | $10,000.00                         |
| Final Asset            | $11,679.80                         |
| Sortino Ratio          | 0.0573                             |
| Maximum Drawdown (MDD) | -0.0508                            |
| HPR (%)                | 16.8                               |
| Monthly return (%)     | 0.01                               |
```

## Paper Trading


Specify period and parameters in `papertrade/parameter/papertrade.json` file.

Create `.env` file in the `/papertrade` directory of the project and fill in the required information. The `.env` file is used to store environment variables that are used in the project. The following is an example of a `.env` file:

```env
PAPER_USERNAME=<paperbroker_password>
PAPER_PASSWORD=<paperbroker_username>
DEFAULT_SUB_ACCOUNT=<default_sub_account>

PAPER_REST_BASE_URL=<paperbroker_rest_base_url>
SOCKET_HOST=<paperbroker_socket_host>
SOCKET_PORT=<paperbroker_socket_port>

SENDER_COMP_ID=<paperbroker_sender_comp_id>
TARGET_COMP_ID=<paperbroker_target_comp_id>

PAPERBROKER_KAFKA_BOOTSTRAP_SERVERS=<kafka_bootstrap_servers>
PAPERBROKER_KAFKA_USERNAME=<kafka_username>
PAPERBROKER_KAFKA_PASSWORD=<kafka_password>
PAPERBROKER_ENV_ID=<paperbroker_env_id>

MARKET_REDIS_HOST=<redis_host>
MARKET_REDIS_PORT=<redis_port>
MARKET_REDIS_PASSWORD=<redis_password>
```

And run 

```bash
python papertrade/main.py
```

### Paper Trading Result

Here is the result for the trading period

```
| Metric                 | Value                              |
| Initial Asset          | VND500.000.000.00                  |
| Final Asset            | VND485.290.440.80                  |
| Sharpe  Ratio          | -2.87                              |
| Sortino Ratio          | -3.39                              |
| Maximum Drawdown (MDD) | -3.45%                             |
```

## Reference
[1] ALGOTRADE, Algorithmic Trading Theory and Practice - A Practical Guide with Applications on the Vietnamese Stock Market, 1st ed. DIMI BOOK, 2023, pp. 52–53. Accessed: March 3, 2026. [Online]. Available: [Link](https://hub.algotrade.vn/knowledge-hub/mean-reversion-strategy/)
