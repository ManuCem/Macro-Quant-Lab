"""
S&P 500 Direction Predictor
----------------------------
Same architecture as predict_yield.py, adapted for an equity index: pulls
historical daily data for the S&P 500 (^GSPC), engineers technical features
(now including volume-based ones, since equities actually have real traded
volume unlike the treasury yield index), trains a classifier to predict
whether tomorrow's close will be UP or DOWN vs today, and validates it with
time-series cross-validation (never trains on the future to predict the past).

Run:
    pip install yfinance scikit-learn pandas numpy --break-system-packages
    python predict_sp500.py
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.metrics import classification_report, accuracy_score

TICKER = "^GSPC"         # S&P 500 index
LOOKBACK_PERIOD = "10y"  # how much history to pull
N_CV_SPLITS = 5          # number of time-series CV folds


def fetch_data(ticker: str = TICKER, period: str = LOOKBACK_PERIOD) -> pd.DataFrame:
    """Download historical daily data for the index."""
    df = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=False)
    if df.empty:
        raise RuntimeError(f"No data returned for {ticker}. Check your connection or ticker symbol.")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build technical features from the raw OHLCV series."""
    data = df.copy()

    # Daily return
    data["return_1d"] = data["Close"].pct_change()

    # Lagged returns
    for lag in (1, 2, 3, 5):
        data[f"lag_return_{lag}"] = data["return_1d"].shift(lag - 1)

    # Moving averages and price relative to them
    for window in (5, 10, 20, 50):
        data[f"ma_{window}"] = data["Close"].rolling(window).mean()
        data[f"dist_ma_{window}"] = (data["Close"] - data[f"ma_{window}"]) / data[f"ma_{window}"]

    # Rolling volatility
    for window in (5, 10):
        data[f"volatility_{window}"] = data["return_1d"].rolling(window).std()

    # Momentum: change vs N days ago
    for window in (5, 10):
        data[f"momentum_{window}"] = data["Close"] - data["Close"].shift(window)

    # RSI (14-day)
    delta = data["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    data["rsi_14"] = 100 - (100 / (1 + rs))

    # Bollinger Band %B (where price sits within its 20-day band, 0-1+ range)
    ma20 = data["Close"].rolling(20).mean()
    std20 = data["Close"].rolling(20).std()
    upper_band = ma20 + 2 * std20
    lower_band = ma20 - 2 * std20
    data["bollinger_pctb"] = (data["Close"] - lower_band) / (upper_band - lower_band)

    # High-low range as a proxy for daily volatility
    data["hl_range"] = (data["High"] - data["Low"]) / data["Close"]

    # Volume features (equities have real volume, unlike the yield index)
    data["volume_ma_20"] = data["Volume"].rolling(20).mean()
    data["relative_volume"] = data["Volume"] / data["volume_ma_20"]
    data["volume_change"] = data["Volume"].pct_change()

    # Target: 1 if tomorrow's close is higher than today's, else 0
    data["target"] = (data["Close"].shift(-1) > data["Close"]).astype(int)

    return data


def build_feature_matrix(data: pd.DataFrame):
    feature_cols = [c for c in data.columns if c not in
                    ("Open", "High", "Low", "Close", "Volume", "target")]
    clean = data.dropna(subset=feature_cols + ["target"])
    X = clean[feature_cols]
    y = clean["target"]
    return X, y, feature_cols, clean


def run_cross_validation(model, X, y, n_splits=N_CV_SPLITS):
    """Time-series CV: each fold trains only on the past, tests on the future."""
    tscv = TimeSeriesSplit(n_splits=n_splits)
    scores = cross_val_score(model, X, y, cv=tscv, scoring="accuracy")
    return scores, tscv


def main():
    print(f"Fetching {LOOKBACK_PERIOD} of daily data for {TICKER}...")
    raw = fetch_data()
    print(f"  {len(raw)} trading days downloaded ({raw.index.min().date()} to {raw.index.max().date()})")

    print("Engineering features...")
    featured = engineer_features(raw)
    X, y, feature_cols, clean = build_feature_matrix(featured)
    print(f"  {len(feature_cols)} features, {len(X)} usable rows after dropping NaNs")
    print(f"  Class balance -> UP: {y.mean():.1%}, DOWN: {1 - y.mean():.1%}")

    model = RandomForestClassifier(
        n_estimators=300,
        max_depth=5,
        min_samples_leaf=10,
        random_state=42,
        n_jobs=-1,
    )

    print(f"\nRunning {N_CV_SPLITS}-fold time-series cross-validation...")
    scores, tscv = run_cross_validation(model, X, y)
    for i, s in enumerate(scores, 1):
        print(f"  Fold {i}: accuracy = {s:.3f}")
    print(f"  Mean CV accuracy: {scores.mean():.3f}  (std: {scores.std():.3f})")

    # Holdout report on the final fold
    train_idx, test_idx = list(tscv.split(X))[-1]
    model.fit(X.iloc[train_idx], y.iloc[train_idx])
    holdout_preds = model.predict(X.iloc[test_idx])
    print("\nClassification report (last CV fold, held-out period):")
    print(classification_report(y.iloc[test_idx], holdout_preds, target_names=["DOWN", "UP"]))
    print(f"Holdout accuracy: {accuracy_score(y.iloc[test_idx], holdout_preds):.3f}")

    # Fit on ALL available labeled data, then predict tomorrow using the
    # most recent row (which had no label because "tomorrow" hasn't happened yet)
    model.fit(X, y)
    latest_row = featured[feature_cols].iloc[[-1]].dropna()
    if latest_row.empty:
        print("\nCould not build a feature row for the most recent day (missing data).")
        return

    pred = model.predict(latest_row)[0]
    proba = model.predict_proba(latest_row)[0]
    direction = "UP" if pred == 1 else "DOWN"
    confidence = proba[pred]

    last_date = featured.index[-1].date()
    last_close = featured["Close"].iloc[-1]
    print(f"\nAs of {last_date} (close = {last_close:.2f}):")
    print(f"  Prediction for next trading session: {direction}")
    print(f"  Model confidence: {confidence:.1%}  (P(down)={proba[0]:.1%}, P(up)={proba[1]:.1%})")
    print("\nReminder: this is a technical, backward-looking model on a noisy series.")
    print("Treat it as one input among many, not investment advice.")


if __name__ == "__main__":
    main()