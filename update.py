#!/usr/bin/env python3
"""Auto-updates data.json: fits Dixon-Coles style models from football-data.co.uk,
builds fixtures, results, last matches and a rolling backtest. Runs in GitHub Actions."""
import io, json, math, os, sys, datetime as dt
import urllib.request
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd
from scipy.optimize import minimize

LEAGUES = ["E0", "SP1", "I1", "D1", "F1", "EGY"]
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
    if code == "EGY": return load_egy(today)
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

def fit(d, asof, xi=None):
    teams = sorted(set(d.HomeTeam) | set(d.AwayTeam)); ix = {t:i for i,t in enumerate(teams)}; T = len(teams)
    h = d.HomeTeam.map(ix).values; a = d.AwayTeam.map(ix).values
    gh = d.FTHG.values.astype(float); ga = d.FTAG.values.astype(float)
    w = np.exp(-(XI if xi is None else xi)*(asof - d.Date).dt.days.clip(lower=0).values)
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

def grid(lh, la, rho):
    k = np.arange(N); lg = np.array([math.lgamma(i+1) for i in k])
    p = np.exp(-lh+k*np.log(lh)-lg); q = np.exp(-la+k*np.log(la)-lg); M = np.outer(p, q)
    M[0,0]*=1-lh*la*rho; M[0,1]*=1+lh*rho; M[1,0]*=1+la*rho; M[1,1]*=1-rho
    return M / M.sum()

def wdl(lh, la, rho):
    M = grid(lh, la, rho); w = np.tril(M,-1).sum(); dr = np.trace(M)
    return w, dr, 1-w-dr

def lams(m, ht, at, k=1.0):
    if ht not in m["att"] or at not in m["att"]: return None
    sh, sa = sw(m["n"][ht]), sw(m["n"][at])
    return (math.exp(m["mu"]+m["ha"]+(m["att"][ht]*sh+m["def"][at]*sa)*k),
            math.exp(m["mu"]+(m["att"][at]*sa+m["def"][ht]*sh)*k))

def predict(m, ht, at):
    L = lams(m, ht, at)
    return None if L is None else wdl(L[0], L[1], m["rho"])

def rps(p, y):
    o = [0,0,0]; o[y] = 1
    return 0.5*((p[0]-o[0])**2 + (p[0]+p[1]-o[0]-o[1])**2)

S = np.add.outer(np.arange(N), np.arange(N))
CONF_EDGES = [0.0, 0.45, 0.55, 0.65, 1.01]      # 1X2 top-probability buckets
DC_EDGES = [0.0, 0.65, 0.75, 0.85, 1.01]        # double-chance buckets

def bucket(edges, v):
    for i in range(len(edges)-1):
        if edges[i] <= v < edges[i+1]: return i
    return len(edges)-2

XIS = [0.0010, 0.0018, 0.0030]      # time-decay candidates (per day)
KS = [0.80, 0.90, 1.00, 1.10]       # global strength scale (<1 = less extreme probabilities)
DEFAULT = (0.0018, 1.00)

def backtest(data, today, weeks=12):
    """Fit once per (week, league, xi); score each (xi, k); keep the best only if it beats the default by a margin."""
    pack = {xi: [] for xi in XIS}; W = {}
    for wk in range(weeks, 0, -1):
        end = today - dt.timedelta(days=7*(wk-1)); start = end - dt.timedelta(days=7)
        for code, d in data.items():
            tr = d[d.Date < start]; te = d[(d.Date >= start) & (d.Date < end)]
            if len(te) == 0 or len(tr) < 300: continue
            fr = [(tr.FTHG>tr.FTAG).mean(), (tr.FTHG==tr.FTAG).mean(), (tr.FTHG<tr.FTAG).mean()]
            for xi in XIS: pack[xi].append((wk, fit(tr, start, xi), te, fr))
    def yof(r): return 0 if r.FTHG > r.FTAG else 1 if r.FTHG == r.FTAG else 2
    def score(xi, k):
        R = n = 0
        for wk, m, te, fr in pack[xi]:
            for r in te.itertuples():
                L = lams(m, r.HomeTeam, r.AwayTeam, k)
                if L is None: continue
                R += rps(wdl(L[0], L[1], m["rho"]), yof(r)); n += 1
        return R/n if n else None
    sc = {(xi, k): score(xi, k) for xi in XIS for k in KS}
    ds = sc.get(DEFAULT)
    ok = [(v, c) for c, v in sc.items() if v is not None]
    if not ok: return None, {"xi": DEFAULT[0], "k": DEFAULT[1]}
    bv, bc = min(ok)
    if ds is None or bv > ds - 0.001: bc = DEFAULT          # not clearly better: keep the default
    xi, k = bc
    hits = n = 0; R = B = 0.0; byw = {}
    cf = [[0,0] for _ in CONF_EDGES[:-1]]; dcf = [[0,0] for _ in DC_EDGES[:-1]]
    mk = {q: [0,0] for q in ("dc","o15","o25","btts")}
    for wk, m, te, fr in pack[xi]:
        wh = wn = 0
        for r in te.itertuples():
            L = lams(m, r.HomeTeam, r.AwayTeam, k)
            if L is None: continue
            M = grid(L[0], L[1], m["rho"]); w = np.tril(M,-1).sum(); dr = np.trace(M); p = (w, dr, 1-w-dr); y = yof(r)
            ok1 = int(np.argmax(p) == y); wh += ok1; wn += 1; hits += ok1; n += 1; R += rps(p, y); B += rps(fr, y)
            i = bucket(CONF_EDGES, max(p)); cf[i][0] += 1; cf[i][1] += ok1
            pairs = [p[0]+p[1], p[0]+p[2], p[1]+p[2]]; j = int(np.argmax(pairs))
            okdc = int(y in ((0,1),(0,2),(1,2))[j]); mk["dc"][0] += 1; mk["dc"][1] += okdc
            i = bucket(DC_EDGES, pairs[j]); dcf[i][0] += 1; dcf[i][1] += okdc
            g = int(r.FTHG + r.FTAG)
            for name, pr_, real in (("o15", M[S>=2].sum(), g>=2), ("o25", M[S>=3].sum(), g>=3), ("btts", M[1:,1:].sum(), r.FTHG>0 and r.FTAG>0)):
                mk[name][0] += 1; mk[name][1] += int((pr_ > 0.5) == bool(real))
        a_, b_ = byw.get(wk, (0, 0)); byw[wk] = (a_+wh, b_+wn)
    Wk = [{"acc": round(a/b, 3)} for wk, (a, b) in sorted(byw.items(), reverse=True) if b >= 10]
    if not n: return None, {"xi": xi, "k": k}
    tbl = lambda E, A: [{"lo": E[i], "hi": min(E[i+1], 1.0), "n": a[0], "acc": round(a[1]/a[0], 3) if a[0] else None} for i, a in enumerate(A)]
    return ({"n": n, "acc": round(hits/n, 3), "rps": round(R/n, 4), "base_rps": round(B/n, 4), "rps_default": round(ds, 4) if ds else None,
             "tuned": bc != DEFAULT, "weeks": Wk, "conf": tbl(CONF_EDGES, cf), "dc_conf": tbl(DC_EDGES, dcf),
             "mkts": {q: {"n": v[0], "acc": round(v[1]/v[0], 3)} for q, v in mk.items() if v[0]}}, {"xi": xi, "k": k})

KO = {}


# ---------------- Egyptian Premier League (ESPN public API, no key) ----------------
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/egy.1/scoreboard"

def espn_events(a, b):
    """All events between dates a and b (inclusive), fetched in 30-day chunks."""
    import json as _j
    out, cur = [], a
    while cur <= b:
        end = min(cur + dt.timedelta(days=29), b)
        url = f"{ESPN}?dates={cur:%Y%m%d}-{end:%Y%m%d}&limit=500"
        try: out += _j.loads(get(url)).get("events", [])
        except Exception as e: print("espn skip", cur.date(), e)
        cur = end + dt.timedelta(days=1)
    return out

def espn_rows(ev):
    c = (ev.get("competitions") or [{}])[0]; tm = c.get("competitors") or []
    h = next((x for x in tm if x.get("homeAway") == "home"), None); a = next((x for x in tm if x.get("homeAway") == "away"), None)
    if not h or not a: return None
    nm = lambda x: (x.get("team") or {}).get("shortDisplayName") or (x.get("team") or {}).get("displayName")
    st = (ev.get("status") or {}).get("type") or {}
    return nm(h), nm(a), h.get("score"), a.get("score"), bool(st.get("completed")), ev.get("date")

def load_egy(today):
    ss = seasons(today)[0]; y0 = 2000 + int(ss[-1][:2])        # oldest of the 3 seasons
    evs = espn_events(dt.datetime(y0, 7, 1), today)
    rows = []
    for ev in evs:
        r = espn_rows(ev)
        if not r or not r[4] or r[2] in (None, "") or r[3] in (None, ""): continue
        try: rows.append((pd.to_datetime(r[5]).tz_localize(None), r[0], r[1], int(r[2]), int(r[3])))
        except Exception: continue
    if not rows: return None
    d = pd.DataFrame(rows, columns=["Date","HomeTeam","AwayTeam","FTHG","FTAG"]).drop_duplicates(["Date","HomeTeam","AwayTeam"])
    return d.sort_values("Date").reset_index(drop=True)

def egy_fixtures(today):
    out = []
    for ev in espn_events(today.replace(hour=0, minute=0), today + dt.timedelta(days=14)):
        r = espn_rows(ev)
        if not r or r[4]: continue
        try: u = pd.to_datetime(r[5]).tz_localize(None).to_pydatetime()
        except Exception: continue
        if u < today - dt.timedelta(hours=3): continue
        t = u.replace(tzinfo=dt.timezone.utc).astimezone(ZoneInfo("Africa/Cairo")).replace(tzinfo=None)
        KO[("EGY", r[0], r[1])] = u
        out.append((t, ["EGY", f"{WD[t.weekday()]} {t.day} {MON[t.month-1]} {t:%H:%M}", r[0], r[1]]))
    print("egy fixtures:", len(out)); return out

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
        KO[(r["Div"], r["HomeTeam"], r["AwayTeam"])] = d.replace(tzinfo=ZoneInfo("Europe/London")).astimezone(dt.timezone.utc).replace(tzinfo=None)
        if t.date() < today.date() or t.date() > today.date()+dt.timedelta(days=14): continue
        out.append((t, [r["Div"], f"{WD[t.weekday()]} {t.day} {MON[t.month-1]} {t:%H:%M}", r["HomeTeam"], r["AwayTeam"]]))
    try: out += egy_fixtures(today)
    except Exception as e: print("egy fixtures failed:", e)
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


def blk_pred(blk, h, a, k):
    T = blk["teams"]
    if h not in T or a not in T: return None
    sh, sa = sw(T[h][3]), sw(T[a][3])
    lh = math.exp(blk["mu"]+blk["ha"]+(T[h][0]*sh+T[a][1]*sa)*k); la = math.exp(blk["mu"]+(T[a][0]*sa+T[h][1]*sh)*k)
    M = grid(lh, la, blk["rho"]); w = float(np.tril(M,-1).sum()); dr = float(np.trace(M))
    return [round(w,4), round(dr,4), round(1-w-dr,4)], round(float(M[S>=3].sum()),4), round(float(M[1:,1:].sum()),4)

def new_agg():
    return {"n": 0, "hits": 0, "br": 0.0, "conf": [[0,0] for _ in CONF_EDGES[:-1]], "dc": [0,0], "o25": [0,0], "bt": [0,0], "lg": {}}

def agg_add(A, e):
    p, r = e["p"], e["r"]; y = 0 if r[0] > r[1] else 1 if r[0] == r[1] else 2; ok = int(int(np.argmax(p)) == y)
    A["n"] += 1; A["hits"] += ok; A["br"] += sum((p[i] - (1 if i == y else 0))**2 for i in range(3))
    i = bucket(CONF_EDGES, max(p)); A["conf"][i][0] += 1; A["conf"][i][1] += ok
    pairs = [p[0]+p[1], p[0]+p[2], p[1]+p[2]]; j = int(np.argmax(pairs))
    A["dc"][0] += 1; A["dc"][1] += int(y in ((0,1),(0,2),(1,2))[j])
    g = r[0] + r[1]; A["o25"][0] += 1; A["o25"][1] += int((e["o25"] > 0.5) == (g >= 3))
    A["bt"][0] += 1; A["bt"][1] += int((e["bt"] > 0.5) == (r[0] > 0 and r[1] > 0))
    lg = A["lg"].setdefault(e["f"][0], [0,0]); lg[0] += 1; lg[1] += ok

def agg_stats(A):
    n = A["n"]; f = lambda c: {"n": c[0], "acc": round(c[1]/c[0], 3) if c[0] else None}
    return {"n": n, "hits": A["hits"], "acc": round(A["hits"]/n, 3) if n else None, "brier": round(A["br"]/n, 3) if n else None,
            "conf": [{"lo": CONF_EDGES[i], "hi": min(CONF_EDGES[i+1], 1.0), "n": c[0], "acc": round(c[1]/c[0], 3) if c[0] else None} for i, c in enumerate(A["conf"])],
            "mkts": {"dc": f(A["dc"]), "o25": f(A["o25"]), "btts": f(A["bt"])}, "lg": {k: f(v) for k, v in A["lg"].items()}}

def log_update(old, out, data, fx, cfg, today):
    """Freeze each prediction before kickoff, attach the real result afterwards, and keep running statistics."""
    L = old or {}
    O = L.get("open", {}); A = L.get("agg") or new_agg(); R = L.get("recent", []); since = L.get("since")
    sc = seasons(today)[0][0]
    for f in fx:                                    # 1) record new upcoming matches (prediction is frozen now)
        code, h, a = f[0], f[2], f[3]; ko = KO.get((code, h, a))
        if not ko or ko <= today or code not in out: continue
        key = f"{code}|{h}|{a}|{sc}"
        if key in O: continue
        pr_ = blk_pred(out[code], h, a, cfg["k"])
        if pr_ is None: continue
        O[key] = {"f": f, "ko": ko.strftime("%Y-%m-%dT%H:%MZ"), "p": pr_[0], "o25": pr_[1], "bt": pr_[2]}
        since = since or ko.strftime("%Y-%m-%d")
    for key in list(O):                             # 2) attach results of finished matches
        e = O[key]; ko = dt.datetime.strptime(e["ko"], "%Y-%m-%dT%H:%MZ"); d = data.get(e["f"][0])
        if ko > today: continue
        if (today - ko).days > 30: del O[key]; continue          # postponed or never found: drop quietly
        if d is None: continue
        day = pd.Timestamp(ko.date())
        rows = d[(d.HomeTeam == e["f"][2]) & (d.AwayTeam == e["f"][3]) & (d.Date >= day - pd.Timedelta(days=1)) & (d.Date <= day + pd.Timedelta(days=5))]
        if len(rows):
            r0 = rows.iloc[0]; e["r"] = [int(r0.FTHG), int(r0.FTAG)]; agg_add(A, e); R.insert(0, e); del O[key]
    R = sorted(R, key=lambda e: e["ko"], reverse=True)[:40]
    return {"open": O, "agg": A, "recent": R, "since": since, "pending": len(O), "stats": agg_stats(A)}

def main():
    today = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    old = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    try: fx = fixtures(today)
    except Exception as e: print("fixtures failed:", e); fx = old.get("_fix", [])
    data = {}
    for code in LEAGUES:
        d = load_league(code, today)
        if d is not None and len(d) >= 200: data[code] = d
    if not data: sys.exit("no league updated; keeping old data.json")
    bt, cfg = None, {"xi": DEFAULT[0], "k": DEFAULT[1]}
    try: bt, cfg = backtest(data, today)
    except Exception as e: print("backtest failed:", e)
    print("model config:", cfg, "| tuned:", bool(bt and bt.get("tuned")))
    globals()["XI"] = cfg["xi"]
    out, last, res = {}, {}, {}
    for code in LEAGUES:
        if code not in data:
            if code in old: out[code] = old[code]
            continue
        ft = {x for f in fx if f[0]==code for x in (f[2], f[3])}
        out[code], l, r = build_league(code, data[code], today, ft); last.update(l); res.update(r)
        print(code, "teams", len(out[code]["teams"]), "rho", out[code]["rho"])
    out["_fix"] = fx or old.get("_fix", []); out["_last"] = last; out["_res"] = res; out["_cfg"] = cfg
    try: out["_log"] = log_update(old.get("_log"), out, data, fx, cfg, today)
    except Exception as e:
        print("log failed:", e); out["_log"] = old.get("_log")
    if bt: out["_bt"] = bt
    elif "_bt" in old: out["_bt"] = old["_bt"]
    strip = lambda j: {k: v for k, v in j.items() if k != "_ts"}
    print("data unchanged, refreshing timestamp only" if strip(out) == strip(old) else "data changed")
    out["_ts"] = today.strftime("%Y-%m-%dT%H:%M:%SZ")
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("data.json written")

if __name__ == "__main__": main()
