"""
RR-RS (Regime & Range-Adjusted Relative Strength) for the Nifty PSU Bank universe.

Usage:
  python rr_rs_psu.py                 # downloads ~2y daily data via yfinance
  python rr_rs_psu.py --csv-dir data  # reads data/<SYMBOL>.csv (Date,Open,High,Low,Close,Volume)

Assumptions (edit the constants below):
  - Market benchmark = Nifty 500; industry index = Nifty PSU Bank
  - Swing legs = zigzag on benchmark close with a 6% reversal, last 126 sessions
  - Deep-DD knockout: 63d MaxDD worse than 2.5x Nifty 500's AND worse than -10%
  - Weights: Bear 30 / Bull 25 / Trend 20 / Position 15 / RS line 10
"""
import argparse, os
import numpy as np, pandas as pd

STOCKS = ["SBIN", "BANKBARODA", "PNB", "CANBK", "UNIONBANK", "INDIANB",
          "BANKINDIA", "IOB", "CENTRALBK", "MAHABANK", "UCOBANK", "PSB"]
MARKET, INDUSTRY = "NIFTY500", "NIFTYPSUBANK"
YF = {MARKET: "^CRSLDX", INDUSTRY: "^CNXPSUBANK"}
WIN, POS_WIN, PIVOT = 126, 63, 0.06
LEG_W = [0.5, 0.3, 0.2]                       # most recent leg first
W = dict(bear=.30, bull=.25, trend=.20, pos=.15, rsl=.10)


def load(csv_dir):
    syms = STOCKS + [MARKET, INDUSTRY]
    if csv_dir:
        f = {s: pd.read_csv(os.path.join(csv_dir, f"{s}.csv"), parse_dates=["Date"], index_col="Date")
             for s in syms}
    else:
        import yfinance as yf
        f = {}
        for s in syms:
            d = yf.download(YF.get(s, s + ".NS"), period="2y", auto_adjust=True, progress=False)
            d.columns = d.columns.get_level_values(0)
            f[s] = d
    close = pd.DataFrame({s: d["Close"] for s, d in f.items()}).dropna(how="all").ffill().dropna()
    high = pd.DataFrame({s: d["High"] for s, d in f.items()}).reindex(close.index).ffill()
    low = pd.DataFrame({s: d["Low"] for s, d in f.items()}).reindex(close.index).ffill()
    vol = pd.DataFrame({s: d["Volume"] for s, d in f.items() if s in STOCKS}).reindex(close.index).ffill()
    return close, high, low, vol


def zigzag(c, th):
    """Return pivot positions of a close series using a % reversal threshold."""
    c = np.asarray(c); piv, trend, hi, lo = [], 0, 0, 0
    for i in range(1, len(c)):
        if trend == 0:
            hi = i if c[i] > c[hi] else hi; lo = i if c[i] < c[lo] else lo
            if c[i] <= c[hi] * (1 - th): piv, trend, ext = [hi], -1, i
            elif c[i] >= c[lo] * (1 + th): piv, trend, ext = [lo], 1, i
            continue
        if trend == 1:
            if c[i] > c[ext]: ext = i
            elif c[i] <= c[ext] * (1 - th): piv.append(ext); trend, ext = -1, i
        else:
            if c[i] < c[ext]: ext = i
            elif c[i] >= c[ext] * (1 + th): piv.append(ext); trend, ext = 1, i
    if trend: piv.append(ext)
    if piv and piv[-1] != len(c) - 1 and abs(c[-1] / c[piv[-1]] - 1) >= th / 2:
        piv.append(len(c) - 1)                   # open leg into today
    return piv


def legs(bench):
    p = zigzag(bench.values, PIVOT)
    out = [(a, b, "down" if bench.iloc[b] < bench.iloc[a] else "up") for a, b in zip(p, p[1:])]
    return out[::-1]                             # most recent first


def wavg(vals):
    if not vals: return np.nan
    w = (LEG_W + [LEG_W[-1]] * len(vals))[:len(vals)]
    return float(np.dot(vals, w) / sum(w))


def maxdd(s): return float((s / s.cummax() - 1).min())


def regime_spread(s, b, lg, kind):
    """Recency-weighted (stock - bench) return across legs of one kind; day-split fallback."""
    sel = [(a, e) for a, e, k in lg if k == kind]
    if sel:
        return wavg([(s.iloc[e] / s.iloc[a] - 1) - (b.iloc[e] / b.iloc[a] - 1) for a, e in sel]), "legs"
    rb, rs = b.pct_change().dropna(), s.pct_change().dropna()
    m = rb < 0 if kind == "down" else rb > 0
    return float((1 + rs[m]).prod() - (1 + rb[m]).prod()), "days"


def metrics(s, b, lg, h, l, bh, bl):
    dr, src = regime_spread(s, b, lg, "down")
    uo, _ = regime_spread(s, b, lg, "up")
    rng = lambda hh, ll: hh.max() / ll.min() - 1
    hh63, ll63 = h.iloc[-POS_WIN:].max(), l.iloc[-POS_WIN:].min()
    ratio = s / b
    # bottom lead: days the stock bottomed before the benchmark in the latest down leg
    lead = np.nan
    dl = [(a, e) for a, e, k in lg if k == "down"]
    if dl:
        a, e = dl[0]
        lead = e - (a + int(np.argmin(s.iloc[a:e + 1].values)))
    return dict(DR=dr, UO=uo, DDR=maxdd(s) - maxdd(b), RHE=rng(h, l) - rng(bh, bl),
                RP63=(s.iloc[-1] - ll63) / (hh63 - ll63), RSL=ratio.iloc[-1] / ratio.max() - 1,
                Off63High=s.iloc[-1] / hh63 - 1, MaxDD63=maxdd(s.iloc[-POS_WIN:]),
                BottomLead=lead, RegimeSrc=src)


def wroc(c):
    r = lambda n: c.iloc[-1] / c.iloc[-1 - n] - 1 if len(c) > n else np.nan
    return 0.4 * r(63) + 0.2 * r(126) + 0.2 * r(189) + 0.2 * r(252)


def pct(x): return 1 + 98 * (x.rank(method="average") - 1) / max(len(x.dropna()) - 1, 1)


def setup(c, v):
    sma20 = c.rolling(20).mean()
    near = abs(c.iloc[-1] / sma20.iloc[-1] - 1) <= 0.04
    rising = sma20.iloc[-1] > sma20.iloc[-6]
    dry = v.iloc[-10:].mean() < v.iloc[-50:].mean()
    return "YES" if near and rising and dry else ""


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--csv-dir"); a = ap.parse_args()
    close, high, low, vol = load(a.csv_dir)
    cw, hw, lw = close.iloc[-WIN:], high.iloc[-WIN:], low.iloc[-WIN:]
    mkt = cw[MARKET]; lg = legs(mkt)

    print(f"Data to {close.index[-1].date()} | {len(lg)} Nifty 500 legs in last {WIN} sessions:")
    for s_, e_, k in lg[::-1]:
        print(f"  {k:4s} {cw.index[s_].date()} -> {cw.index[e_].date()}  {mkt.iloc[e_]/mkt.iloc[s_]-1:+.1%}")

    ind = metrics(cw[INDUSTRY], mkt, lg, hw[INDUSTRY], lw[INDUSTRY], hw[MARKET], lw[MARKET])
    print(f"\nPSU Bank index vs Nifty 500: DR {ind['DR']:+.1%} | UO {ind['UO']:+.1%} | "
          f"DDR {ind['DDR']:+.1%} | RHE {ind['RHE']:+.1%} | RP63 {ind['RP63']:.2f} | "
          f"RS line {ind['RSL']:+.1%} from high | WROC spread {wroc(close[INDUSTRY]) - wroc(close[MARKET]):+.1%}")

    rows = {}
    for s in STOCKS:
        m = metrics(cw[s], mkt, lg, hw[s], lw[s], hw[MARKET], lw[MARKET]); m["WROC"] = wroc(close[s])
        m["Setup"] = setup(close[s], vol[s]); rows[s] = m
    df = pd.DataFrame(rows).T
    num = ["DR", "UO", "DDR", "RHE", "RP63", "RSL", "WROC"]
    df[num] = df[num].astype(float)

    df["Bear-RS"] = pct((pct(df.DR) + pct(df.DDR)) / 2)
    df["Bull-RS"] = pct((pct(df.UO) + pct(df.RHE)) / 2)
    raw = (W["bear"] * df["Bear-RS"] + W["bull"] * df["Bull-RS"] + W["trend"] * pct(df.WROC)
           + W["pos"] * pct(df.RP63) + W["rsl"] * pct(df.RSL))
    df["RR-RS"] = pct(raw).round(0).astype(int)
    mkt_dd63 = maxdd(mkt.iloc[-POS_WIN:])
    df["Knockout"] = np.where(df.Off63High < -0.15, "far from high",
                     np.where(df.MaxDD63.astype(float) < min(2.5 * mkt_dd63, -0.10), "deep DD", ""))
    df["Both>=60"] = np.where((df["Bear-RS"] >= 60) & (df["Bull-RS"] >= 60), "YES", "")
    df = df.sort_values(["RR-RS", "BottomLead"], ascending=False)

    show = df[["RR-RS", "Bear-RS", "Bull-RS", "DR", "UO", "DDR", "RHE", "WROC", "RP63",
               "RSL", "Off63High", "BottomLead", "Both>=60", "Knockout", "Setup"]].copy()
    for c in ["DR", "UO", "DDR", "RHE", "WROC", "RSL", "Off63High"]:
        show[c] = show[c].astype(float).map("{:+.1%}".format)
    for c in ["Bear-RS", "Bull-RS"]: show[c] = show[c].round(0).astype(int)
    show["RP63"] = show["RP63"].astype(float).round(2)
    pd.set_option("display.width", 250)
    print(f"\nRegime source: {df.RegimeSrc.iloc[0]}\n"); print(show.to_string())
    df.to_csv("rr_rs_psu_banks.csv"); print("\nSaved rr_rs_psu_banks.csv")


if __name__ == "__main__":
    main()
