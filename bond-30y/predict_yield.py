"""
30-Year Treasury Yield Direction Predictor
-------------------------------------------
Pulls historical data for the 30-year Treasury yield (CBOE ^TYX index),
engineers a set of technical features, trains a classifier to predict
whether tomorrow's yield will close UP or DOWN vs today, and validates
the model with time-series cross-validation (no shuffling — this avoids
leaking future information into the past, which a normal k-fold CV would do).
 
Run:
    pip install yfinance scikit-learn pandas numpy --break-system-packages
    python predict_yield.py
 
Data source note:
    ^TYX is the CBOE 30-Year Treasury Yield Index. Values are already in
    percentage points (e.g. 4.35 means 4.35%). If you'd rather use FRED's
    DGS30 series, swap out the download section — the rest of the pipeline
    (features, CV, prediction) doesn't care where the yield series came from.
"""
 
import warnings
warnings.filterwarnings("ignore")
 
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.metrics import classification_report, accuracy_score
 
TICKER = "^TYX"          # CBOE 30-Year Treasury Yield Index
LOOKBACK_PERIOD = "10y"  # how much history to pull
N_CV_SPLITS = 5          # number of time-series CV folds
 
 
def fetch_data(ticker: str = TICKER, period: str = LOOKBACK_PERIOD) -> pd.DataFrame:
    """Download historical daily data for the yield series."""
    df = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=False)
    if df.empty:
        raise RuntimeError(f"No data returned for {ticker}. Check your connection or ticker symbol.")
    # yfinance sometimes returns a MultiIndex column layout — flatten it
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    return df
 
 
def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build technical features from the raw OHLC yield series."""
    data = df.copy()
 
    # Daily return
    data["return_1d"] = data["Close"].pct_change()
 
    # Lagged returns
    for lag in (1, 2, 3, 5):
        data[f"lag_return_{lag}"] = data["return_1d"].shift(lag - 1)
 
    # Moving averages and price relative to them
    for window in (5, 10, 20):
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
 
    # High-low range as a proxy for daily volatility
    data["hl_range"] = (data["High"] - data["Low"]) / data["Close"]
 
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
 
    # Holdout report on the final fold for a closer look at precision/recall
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
    print(f"\nAs of {last_date} (yield = {last_close:.3f}%):")
    print(f"  Prediction for next trading session: {direction}")
    print(f"  Model confidence: {confidence:.1%}  (P(down)={proba[0]:.1%}, P(up)={proba[1]:.1%})")
    print("\nReminder: this is a technical, backward-looking model on a noisy series.")
    print("Treat it as one input among many, not investment advice.")
 
 
if __name__ == "__main__":
    main()