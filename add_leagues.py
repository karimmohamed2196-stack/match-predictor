#!/usr/bin/env python3
"""add_leagues.py — يضيف دوريات جديدة إلى data.json بنفس الشكل الحالي (من غير ما يلمس الدوريات الموجودة).
الاستخدام:  python add_leagues.py data.json            (يكتب نسخة احتياطية data.json.bak ثم يعدّل الملف)
            python add_leagues.py data.json --only BRA,P1 --out data_new.json
المتطلبات:  pip install numpy scipy
المصدر:     football-data.co.uk (نفس مصدر E0/SP1/I1/D1/F1 غالباً)."""
import argparse, csv, io, json, shutil, sys, urllib.request, datetime as dt
from zoneinfo import ZoneInfo
import numpy as np
from scipy.optimize import minimize

SRC_TZ, APP_TZ = ZoneInfo("Europe/London"), ZoneInfo("Africa/Cairo")   # لو مصدر الدوري بتوقيت تاني غيّره هنا
LEAGUES = {"P1": ("main", "P1"), "N1": ("main", "N1"), "T1": ("main", "T1"), "B1": ("main", "B1"),
           "SC0": ("main", "SC0"), "G1": ("main", "G1"),
           "BRA": ("new", "BRA"), "ARG": ("new", "ARG"), "MEX": ("new", "MEX"), "MLS": ("new", "USA")}
FIX_URLS = {"fixtures": "https://www.football-data.co.uk/fixtures.csv",
            "new_league_fixtures": "https://www.football-data.co.uk/new_league_fixtures.csv"}
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
XI, RIDGE = 0.001, 1.0          # نفس _cfg في data.json

def get(key, url, local):
    try:
        raw = open(f"{local}/{key}.csv", "rb").read() if local else urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read()
    except Exception as e:
        print("  ! تعذّر تحميل", key, "-", e); return []
    try: txt = raw.decode("utf-8-sig")
    except UnicodeDecodeError: txt = raw.decode("latin-1")
    return list(csv.DictReader(io.StringIO(txt)))

def pdate(s):
    for f in ("%d/%m/%Y", "%d/%m/%y"):
        try: return dt.datetime.strptime(s.strip(), f).date()
        except (ValueError, AttributeError): pass

def season_codes(today, n=3):
    y = today.year if today.month >= 7 else today.year - 1
    return [f"{(y-i)%100:02d}{(y-i+1)%100:02d}" for i in range(n)]

def load_matches(code, today, days, local):
    kind, fd = LEAGUES[code]
    if kind == "main": parts = [get(f"{fd}_{sc}", f"https://www.football-data.co.uk/mmz4281/{sc}/{fd}.csv", local) for sc in season_codes(today)]
    else: parts = [get(fd, f"https://www.football-data.co.uk/new/{fd}.csv", local)]
    out = []
    for rows in parts:
        for r in rows:
            d = pdate(r.get("Date", "")); h = (r.get("HomeTeam") or r.get("Home") or "").strip(); a = (r.get("AwayTeam") or r.get("Away") or "").strip()
            hg, ag = (r.get("FTHG") or r.get("HG") or "").strip(), (r.get("FTAG") or r.get("AG") or "").strip()
            if d and h and a and hg.isdigit() and ag.isdigit() and d <= today and (today - d).days <= days:
                out.append((d, h, a, int(hg), int(ag)))
    return sorted(set(out))

def fit(M, today):
    teams = sorted({m[1] for m in M} | {m[2] for m in M}); ix = {t: i for i, t in enumerate(teams)}; T = len(teams)
    hi, ai = np.array([ix[m[1]] for m in M]), np.array([ix[m[2]] for m in M])
    hg, ag = np.array([m[3] for m in M], float), np.array([m[4] for m in M], float)
    w = np.exp(-XI * np.array([(today - m[0]).days for m in M], float))
    def nll(p):
        mu, ha, att, df = p[0], p[1], p[2:2+T], p[2+T:]
        lh, la = mu + ha + att[hi] + df[ai], mu + att[ai] + df[hi]; eh, ea = np.exp(lh), np.exp(la)
        f = -(w * (hg*lh - eh + ag*la - ea)).sum() + RIDGE * (att @ att + df @ df)
        gh, ga = w * (hg - eh), w * (ag - ea); g = np.zeros_like(p)
        g[0], g[1] = -(gh + ga).sum(), -gh.sum()
        g[2:2+T] = -(np.bincount(hi, gh, T) + np.bincount(ai, ga, T)) + 2*RIDGE*att
        g[2+T:] = -(np.bincount(ai, gh, T) + np.bincount(hi, ga, T)) + 2*RIDGE*df
        return f, g
    p = minimize(nll, np.zeros(2+2*T), jac=True, method="L-BFGS-B").x
    mu, ha, att, df = p[0], p[1], p[2:2+T], p[2+T:]
    lh, la = np.exp(mu + ha + att[hi] + df[ai]), np.exp(mu + att[ai] + df[hi])
    best, rho = -1e18, 0.0
    for r in np.arange(-0.2, 0.2001, 0.02):                              # تصحيح Dixon-Coles للنتائج المنخفضة
        tau = np.ones(len(M)); a0, a1, b0, b1 = (hg == 0) & (ag == 0), (hg == 0) & (ag == 1), (hg == 1) & (ag == 0), (hg == 1) & (ag == 1)
        tau[a0] = 1 - lh[a0]*la[a0]*r; tau[a1] = 1 + lh[a1]*r; tau[b0] = 1 + la[b0]*r; tau[b1] = 1 - r
        if (tau <= 0).any(): continue
        s = (w * np.log(tau)).sum()
        if s > best: best, rho = s, r
    return teams, att, df, round(float(mu), 4), round(float(ha), 4), round(float(rho), 2)

def fx_dt(s, today):
    p = s.split(); d = dt.datetime.strptime(f"{p[1]} {p[2]} {today.year} {p[3]}", "%d %b %Y %H:%M")
    return d.replace(year=today.year + 1) if (today - d.date()).days > 60 else d

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("data"); ap.add_argument("--out"); ap.add_argument("--only")
    ap.add_argument("--local"); ap.add_argument("--days", type=int, default=1000); ap.add_argument("--min-matches", type=int, default=60)
    ap.add_argument("--today"); a = ap.parse_args()
    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
    d = json.load(open(a.data, encoding="utf8")); codes = a.only.split(",") if a.only else list(LEAGUES)
    fixrows = {k: get(k, u, a.local) for k, u in FIX_URLS.items()}; fixrows = [r for v in fixrows.values() for r in v]
    have = {(f[0], f[2], f[3]) for f in d.get("_fix", [])}; newfix, report = [], []
    for code in codes:
        M = load_matches(code, today, a.days, a.local); print(f"{code}: {len(M)} مباراة")
        if len(M) < a.min_matches: print("  ! بيانات قليلة، تخطّيت الدوري"); continue
        teams, att, df, mu, ha, rho = fit(M, today); ix = {t: i for i, t in enumerate(teams)}
        recent = {m[1] for m in M if (today - m[0]).days <= 120} | {m[2] for m in M if (today - m[0]).days <= 120}
        cnt, hist = {}, {t: [] for t in teams}
        for m in M:
            for t in (m[1], m[2]): cnt[t] = cnt.get(t, 0) + 1
            hist[m[1]].append((m[0], m[2], "H", m[3], m[4])); hist[m[2]].append((m[0], m[1], "A", m[4], m[3]))
        d[code] = {"mu": mu, "ha": ha, "rho": rho, "teams": {}}
        for t in sorted(recent):
            h = sorted(hist[t])
            form = "".join("W" if x[3] > x[4] else "D" if x[3] == x[4] else "L" for x in h[-5:])
            d[code]["teams"][t] = [round(float(att[ix[t]]), 3), round(float(df[ix[t]]), 3), form, cnt[t]]
            old = [list(x) for x in d.setdefault("_last", {}).get(t, [])]
            mine = [[x[1], x[2], x[3], x[4], x[0].isoformat()] for x in h]
            d["_last"][t] = sorted({tuple(x) for x in old + mine}, key=lambda x: x[4], reverse=True)[:10]
            d["_last"][t] = [list(x) for x in d["_last"][t]]
        for m in M:
            if (today - m[0]).days <= 21: d.setdefault("_res", {})[f"{code}|{m[1]}|{m[2]}"] = [m[3], m[4]]
        for r in fixrows:
            h = (r.get("HomeTeam") or r.get("Home") or "").strip(); aw = (r.get("AwayTeam") or r.get("Away") or "").strip()
            dd = pdate(r.get("Date", ""));
            if not (dd and h in d[code]["teams"] and aw in d[code]["teams"]) or (code, h, aw) in have: continue
            try: hh, mm = map(int, (r.get("Time") or "12:00").split(":")[:2])
            except ValueError: hh, mm = 12, 0
            t = dt.datetime(dd.year, dd.month, dd.day, hh, mm, tzinfo=SRC_TZ).astimezone(APP_TZ)
            if 0 <= (t.date() - today).days <= 14:
                newfix.append((t.replace(tzinfo=None), [code, f"{DAYS[t.weekday()]} {t.day} {MONS[t.month-1]} {t:%H:%M}", h, aw])); have.add((code, h, aw))
        report.append((code, len(d[code]["teams"]), mu, ha, rho))
    allfix = [(fx_dt(f[1], today), f) for f in d.get("_fix", [])] + newfix
    d["_fix"] = [f for _, f in sorted(allfix, key=lambda x: x[0])]
    out = a.out or a.data
    if not a.out: shutil.copy(a.data, a.data + ".bak")
    json.dump(d, open(out, "w", encoding="utf8"), ensure_ascii=False, separators=(",", ":"))
    print("\nتم. الدوريات المضافة:"); [print(f"  {c}: {n} فريق  mu={mu} ha={ha} rho={rho}") for c, n, mu, ha, rho in report]
    print(f"مباريات قادمة جديدة: {len(newfix)}  → كتبت {out}")
if __name__ == "__main__": main()
