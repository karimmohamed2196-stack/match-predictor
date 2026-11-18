#!/usr/bin/env python3
"""Auto-updates data.json: fits Dixon-Coles style models from football-data.co.uk,
builds fixtures, results, last matches and a rolling backtest. Runs in GitHub Actions."""
import io, json, math, os, sys, datetime as dt
import urllib.request
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd
from scipy.optimize import minimize

LEAGUES = ["E0", "SP1", "I1", "D1", "F1"]
BASE = "https://www.football-data.co.uk/"
OUT = "data.json"
XI, RIDGE, N = 0.0018, 1.0, 10          # time decay per day, ridge, goal grid
MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
WD = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]

def decode(raw):
    try: return raw.decode("utf-8-sig")
    except UnicodeDecodeError: return raw.decode("latin-1")

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return decode(urllib.request.urlopen(req, timeout=60).read())

def seasons(today):
    y = today.year if today.month >= 7 else today.year - 1
    return [f"{(y-i)%100:02d}{(y-i+1)%100:02d}" for i in range(3)], dt.datetime(y, 7, 1)

def load_league(code, today):
    frames = []
    for s in seasons(today)[0]:
        try:
            df = pd.read_csv(io.StringIO(get(f"{BASE}mmz4281/{s}/{code}.csv")), on_bad_lines="skip")
            df = df[["Date","HomeTeam","AwayTeam","FTHG","FTAG"]].dropna()
            try: df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, format="mixed", errors="coerce")
            except Exception: df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
            frames.append(df.dropna())
        except Exception as e:
            print("skip", code, s, e)
    if not frames: return None
    d = pd.concat(frames).sort_values("Date").reset_index(drop=True)
    d["FTHG"] = d["FTHG"].astype(int); d["FTAG"] = d["FTAG"].astype(int)
    return d

def est_rho(lh, la, gh, ga, w):
    best, bl = 0.0, -1e18
    m00=(gh==0)&(ga==0); m01=(gh==0)&(ga==1); m10=(gh==1)&(ga==0); m11=(gh==1)&(ga==1)
    for r in np.arange(-0.2, 0.0501, 0.02):
        t = np.ones_like(lh)
        t[m00]=1-lh[m00]*la[m00]*r; t[m01]=1+lh[m01]*r; t[m10]=1+la[m10]*r; t[m11]=1-r
        if (t <= 0).any(): continue
        l = (w*np.log(t)).sum()
        if l > bl: bl, best = l, r
    return round(float(best), 2)

def fit(d, asof):
    teams = sorted(set(d.HomeTeam) | set(d.AwayTeam)); ix = {t:i for i,t in enumerate(teams)}; T = len(teams)
    h = d.HomeTeam.map(ix).values; a = d.AwayTeam.map(ix).values
    gh = d.FTHG.values.astype(float); ga = d.FTAG.values.astype(float)
    w = np.exp(-XI*(asof - d.Date).dt.days.clip(lower=0).values)
    def f(p):
        mu, ha = p[0], p[1]; att = p[2:2+T]; de = p[2+T:]
        eh = mu+ha+att[h]+de[a]; ea = mu+att[a]+de[h]; lh = np.exp(eh); la = np.exp(ea)
        nll = -(w*(gh*eh-lh+ga*ea-la)).sum() + RIDGE*((att**2).sum()+(de**2).sum())
        rh = w*(lh-gh); ra = w*(la-ga); g = np.zeros_like(p)
        g[0] = rh.sum()+ra.sum(); g[1] = rh.sum()
        np.add.at(g, 2+h, rh); np.add.at(g, 2+a, ra); np.add.at(g, 2+T+a, rh); np.add.at(g, 2+T+h, ra)
        g[2:2+T] += 2*RIDGE*att; g[2+T:] += 2*RIDGE*de
        return nll, g
    p0 = np.zeros(2+2*T); p0[0] = math.log(max(0.5, (gh.mean()+ga.mean())/2))
    r = minimize(f, p0, jac=True, method="L-BFGS-B", options={"maxiter": 300})
    mu, ha = r.x[0], r.x[1]; att = r.x[2:2+T].copy(); de = r.x[2+T:].copy()
    mu += att.mean() + de.mean(); att -= att.mean(); de -= de.mean()
    lh = np.exp(mu+ha+att[h]+de[a]); la = np.exp(mu+att[a]+de[h])
    n = {t: int(((d.HomeTeam==t)|(d.AwayTeam==t)).sum()) for t in teams}
    return {"mu": float(mu), "ha": float(ha), "rho": est_rho(lh, la, gh, ga, w),
            "att": dict(zip(teams, att)), "def": dict(zip(teams, de)), "n": n}

def sw(n): return min(1.0, (n/(n+20))/0.75)          # same small-sample shrinkage as the app

def wdl(lh, la, rho):
    k = np.arange(N); lg = np.array([math.lgamma(i+1) for i in k])
    p = np.exp(-lh+k*np.log(lh)-lg); q = np.exp(-la+k*np.log(la)-lg); M = np.outer(p, q)
    M[0,0]*=1-lh*la*rho; M[0,1]*=1+lh*rho; M[1,0]*=1+la*rho; M[1,1]*=1-rho
    M /= M.sum(); w = np.tril(M,-1).sum(); dr = np.trace(M)
    return w, dr, 1-w-dr

def predict(m, ht, at):
    if ht not in m["att"] or at not in m["att"]: return None
    sh, sa = sw(m["n"][ht]), sw(m["n"][at])
    lh = math.exp(m["mu"]+m["ha"]+m["att"][ht]*sh+m["def"][at]*sa)
    la = math.exp(m["mu"]+m["att"][at]*sa+m["def"][ht]*sh)
    return wdl(lh, la, m["rho"])

def rps(p, y):
    o = [0,0,0]; o[y] = 1
    return 0.5*((p[0]-o[0])**2 + (p[0]+p[1]-o[0]-o[1])**2)

def backtest(data, today, weeks=12):
    W, hits, R, B, n = [], 0, 0.0, 0.0, 0
    for k in range(weeks, 0, -1):
        end = today - dt.timedelta(days=7*(k-1)); start = end - dt.timedelta(days=7); wh = wn = 0
        for code, d in data.items():
            tr = d[d.Date < start]; te = d[(d.Date >= start) & (d.Date < end)]
            if len(te) == 0 or len(tr) < 300: continue
            m = fit(tr, start)
            fr = [(tr.FTHG>tr.FTAG).mean(), (tr.FTHG==tr.FTAG).mean(), (tr.FTHG<tr.FTAG).mean()]
            for r in te.itertuples():
                p = predict(m, r.HomeTeam, r.AwayTeam)
                if p is None: continue
                y = 0 if r.FTHG > r.FTAG else 1 if r.FTHG == r.FTAG else 2
                ok = int(np.argmax(p) == y); wh += ok; wn += 1; hits += ok; n += 1
                R += rps(p, y); B += rps(fr, y)
        if wn >= 10: W.append({"acc": round(wh/wn, 3)})
    if not n: return None
    return {"n": n, "acc": round(hits/n, 3), "rps": round(R/n, 4), "base_rps": round(B/n, 4), "weeks": W}

def fixtures(today):
    df = pd.read_csv(io.StringIO(get(BASE+"fixtures.csv")), on_bad_lines="skip")
    df.columns = [str(c).strip().lstrip("\ufeff") for c in df.columns]
    if "Div" not in df.columns:
        print("fixtures columns:", list(df.columns)[:8]); df = df.rename(columns={df.columns[0]: "Div"})
    n0 = len(df); df = df[df["Div"].isin(LEAGUES)].dropna(subset=["Date","HomeTeam","AwayTeam"]); out = []; print("fixtures.csv rows:", n0, "ours:", len(df))
    for r in df.to_dict("records"):
        tm = r.get("Time") if isinstance(r.get("Time"), str) else "15:00"; d = None
        for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%y %H:%M"):
            try: d = dt.datetime.strptime(f"{r['Date']} {tm}", fmt); break
            except ValueError: pass
        if d is None: continue
        t = d.replace(tzinfo=ZoneInfo("Europe/London")).astimezone(ZoneInfo("Africa/Cairo")).replace(tzinfo=None)
        if t.date() < today.date() or t.date() > today.date()+dt.timedelta(days=14): continue
        out.append((t, [r["Div"], f"{WD[t.weekday()]} {t.day} {MON[t.month-1]} {t:%H:%M}", r["HomeTeam"], r["AwayTeam"]]))
    out.sort(key=lambda x: x[0]); print("fixtures kept:", len(out)); return [x[1] for x in out]

def build_league(code, d, today, fix_teams):
    m = fit(d, today); start = seasons(today)[1]
    cur = (set(d[d.Date >= start].HomeTeam) | set(d[d.Date >= start].AwayTeam) | fix_teams) & set(m["att"])
    form, last = {}, {}
    for t in cur:
        g = d[(d.HomeTeam==t)|(d.AwayTeam==t)].sort_values("Date")
        rows = []
        for r in g.itertuples():
            home = r.HomeTeam == t; gf, ga = (r.FTHG, r.FTAG) if home else (r.FTAG, r.FTHG)
            rows.append((r.AwayTeam if home else r.HomeTeam, "H" if home else "A", int(gf), int(ga), r.Date.strftime("%Y-%m-%d")))
        form[t] = "".join("W" if x[2]>x[3] else "D" if x[2]==x[3] else "L" for x in rows[-5:])
        last[t] = [list(x) for x in rows[::-1][:10]]
    teams = {t: [round(m["att"][t],3), round(m["def"][t],3), form[t], m["n"][t]] for t in cur}
    res = {f"{code}|{r.HomeTeam}|{r.AwayTeam}": [int(r.FTHG), int(r.FTAG)]
           for r in d[d.Date >= today-dt.timedelta(days=21)].itertuples()}
    return {"mu": round(m["mu"],4), "ha": round(m["ha"],4), "rho": m["rho"], "teams": teams}, last, res

def main():
    today = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    old = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    try: fx = fixtures(today)
    except Exception as e: print("fixtures failed:", e); fx = old.get("_fix", [])
    out, data, last, res, ok = {}, {}, {}, {}, 0
    for code in LEAGUES:
        d = load_league(code, today)
        if d is None or len(d) < 200:
            if code in old: out[code] = old[code]
            continue
        ft = {x for f in fx if f[0]==code for x in (f[2], f[3])}
        out[code], l, r = build_league(code, d, today, ft); last.update(l); res.update(r); data[code] = d; ok += 1
        print(code, "teams", len(out[code]["teams"]), "rho", out[code]["rho"])
    if not ok: sys.exit("no league updated; keeping old data.json")
    out["_fix"] = fx or old.get("_fix", []); out["_last"] = last; out["_res"] = res
    try:
        bt = backtest(data, today)
        if bt: out["_bt"] = bt
    except Exception as e: print("backtest failed:", e); 
    if "_bt" not in out and "_bt" in old: out["_bt"] = old["_bt"]
    strip = lambda j: {k: v for k, v in j.items() if k != "_ts"}
    if strip(out) == strip(old): print("no change"); return
    out["_ts"] = today.strftime("%Y-%m-%dT%H:%M:%SZ")
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("data.json written")

if __name__ == "__main__": main()
