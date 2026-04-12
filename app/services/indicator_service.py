import pandas as pd


class IndicatorService:
    @staticmethod
    def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = delta.clip(lower=0).rolling(window=period).mean()
        loss = (-delta.clip(upper=0)).rolling(window=period).mean()
        rs = gain / loss.replace(0, 1e-9)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        prev_close = df["close"].shift(1)
        tr = pd.concat(
            [
                (df["high"] - df["low"]),
                (df["high"] - prev_close).abs(),
                (df["low"] - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        return tr.rolling(window=period).mean()

    def calculate(self, bars: list[dict]) -> dict:
        if len(bars) < 30:
            return {}

        df = pd.DataFrame(bars)

        df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
        df["rsi"] = self._rsi(df["close"])
        df["atr"] = self._atr(df)

        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        cumulative_vp = (typical_price * df["volume"]).cumsum()
        cumulative_volume = df["volume"].cumsum().replace(0, 1e-9)
        df["vwap"] = cumulative_vp / cumulative_volume

        df["vol_ratio"] = df["volume"] / df["volume"].rolling(window=20).mean().replace(0, 1e-9)
        df["momentum_5"] = df["close"].pct_change(periods=5)

        latest = df.iloc[-1]
        prev = df.iloc[:-1]

        return {
            "price": float(latest["close"]),
            "ema20": float(latest["ema20"]),
            "ema50": float(latest["ema50"]),
            "rsi": float(latest["rsi"]),
            "vwap": float(latest["vwap"]),
            "atr": float(latest["atr"]),
            "volume_ratio": float(latest["vol_ratio"]),
            "short_momentum": float(latest["momentum_5"]),
            "day_open": float(df.iloc[0]["open"]),
            "previous_high": float(prev["high"].max()),
            "previous_low": float(prev["low"].min()),
        }