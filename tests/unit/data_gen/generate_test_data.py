from datetime import datetime, timedelta

import numpy as np
import polars as pl


def generate_synthetic_data(symbol: str, days: int = 100) -> pl.DataFrame:
    """Generates synthetic OHLCV data for testing."""
    np.random.seed(42)
    start_date = datetime(2025, 1, 1)
    dates = [start_date + timedelta(minutes=j) for j in range(days * 24 * 60 // 60)]  # Hourly data

    n = len(dates)
    price = 100.0
    prices = []
    for _ in range(n):
        price *= 1 + np.random.normal(0, 0.001)
        prices.append(price)

    df = pl.DataFrame(
        {
            "timestamp": dates,
            "open": prices,
            "high": [p * (1 + abs(np.random.normal(0, 0.0005))) for p in prices],
            "low": [p * (1 - abs(np.random.normal(0, 0.0005))) for p in prices],
            "close": [p * (1 + np.random.normal(0, 0.0002)) for p in prices],
            "volume": np.random.randint(1000, 10000, n),
        }
    )
    return df


if __name__ == "__main__":
    df = generate_synthetic_data("AAPL", days=5)
    df.write_csv("sample_data.csv")
    print("Generated sample_data.csv")
