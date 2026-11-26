# يجيب عناوين الأخبار من Google News RSS لكل دوري ويكتبها في news.json (عناوين + رابط المصدر فقط)
import json, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

LEAGUES = {
    "E0": "الدوري الإنجليزي الممتاز",
    "SP1": "الدوري الإسباني",
    "I1": "الدوري الإيطالي",
    "D1": "الدوري الألماني",
    "F1": "الدوري الفرنسي",
    "UCL": "دوري أبطال أوروبا",
    "UEL": "الدوري الأوروبي",
    "EGY": "الدوري المصري",
    "KSA": "الدوري السعودي",
}
PER_LEAGUE = 8

def fetch(q):
    url = "https://news.google.com/rss/search?q=%s&hl=ar&gl=EG&ceid=EG:ar" % urllib.parse.quote(q + " when:3d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (match-predictor news bot)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()

def parse(xml_bytes):
    out, seen = [], set()
    for it in ET.fromstring(xml_bytes).iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        src = (it.findtext("source") or "").strip()
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3].strip()
        try:
            d = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc).isoformat()
        except Exception:
            d = datetime.now(timezone.utc).isoformat()
        key = re.sub(r"\W+", "", title)[:60]
        if not title or not link.startswith("http") or key in seen:
            continue
        seen.add(key)
        out.append({"t": title, "s": src or "Google News", "u": link, "d": d})
        if len(out) >= PER_LEAGUE:
            break
    return out

def main():
    items, ok = {}, 0
    for k, q in LEAGUES.items():
        try:
            items[k] = parse(fetch(q))
            ok += 1
        except Exception as e:
            print("skip", k, e, file=sys.stderr)
        time.sleep(1)
    if not ok:
        sys.exit("no league fetched; keeping old news.json")
    with open("news.json", "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now(timezone.utc).isoformat(), "items": items}, f, ensure_ascii=False, separators=(",", ":"))
    print("ok", ok, "leagues")

if __name__ == "__main__":
    main()
