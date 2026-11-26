// Cloudflare Worker: نتائج مباشرة + أهم الأحداث (أهداف وكروت) بنفس صيغة الموقع
// المصدر: ESPN (واجهة غير رسمية) — انشره بدل كود الـ Worker الحالي أو ادمجه معه.
const LG = { E0: "eng.1", SP1: "esp.1", I1: "ita.1", D1: "ger.1", F1: "fra.1", UCL: "uefa.champions", UEL: "uefa.europa", EGY: "egy.1", KSA: "ksa.1" };
const HDR = { "Access-Control-Allow-Origin": "*", "Content-Type": "application/json; charset=utf-8", "Cache-Control": "public, max-age=20" };
const ymd = (t) => new Date(t).toISOString().slice(0, 10).replace(/-/g, "");

function events(c, homeId) {
  const out = [];
  for (const d of c.details || []) {
    const t = d.scoringPlay ? (d.ownGoal ? "OG" : d.penaltyKick ? "PG" : "G") : d.redCard ? "R" : d.yellowCard ? "Y" : null;
    if (!t) continue;
    const a = (d.athletesInvolved || [])[0] || {};
    out.push({
      t, // G هدف | PG ركلة جزاء | OG عكسي | Y إنذار | R طرد
      m: String((d.clock && d.clock.displayValue) || "").replace(/'/g, ""),
      p: a.displayName || a.shortName || "",
      s: d.team && String(d.team.id) === String(homeId) ? "h" : "a",
      _v: (d.clock && d.clock.value) || 0,
    });
  }
  return out.sort((x, y) => x._v - y._v).map(({ _v, ...e }) => e);
}

async function league(code, slug) {
  const now = Date.now();
  const url = `https://site.api.espn.com/apis/site/v2/sports/soccer/${slug}/scoreboard?dates=${ymd(now - 864e5)}-${ymd(now)}`;
  const r = await fetch(url, { cf: { cacheTtl: 20, cacheEverything: true } });
  if (!r.ok) return [];
  const j = await r.json(), res = [];
  for (const e of j.events || []) {
    const c = (e.competitions || [])[0];
    if (!c) continue;
    const S = c.status || e.status || {}, ty = S.type || {};
    if (ty.state === "pre") continue;
    if (ty.state === "post" && now - Date.parse(e.date) > 6 * 36e5) continue; // انتهت من أكثر من 6 ساعات
    const h = (c.competitors || []).find((x) => x.homeAway === "home"), a = (c.competitors || []).find((x) => x.homeAway === "away");
    if (!h || !a) continue;
    res.push({
      c: code,
      hn: h.team.displayName, hs: h.team.shortDisplayName || h.team.displayName,
      an: a.team.displayName, ans: a.team.shortDisplayName || a.team.displayName,
      u: e.date,
      sh: +h.score || 0, sa: +a.score || 0,
      mn: parseInt(String(S.displayClock || "").replace(/[^0-9+]/g, "")) || 0,
      st: ty.state === "post" ? "FINISHED" : ty.name === "STATUS_HALFTIME" ? "PAUSED" : "IN_PLAY",
      ev: events(c, h.team.id),
    });
  }
  return res;
}

export default {
  async fetch(req) {
    if (req.method === "OPTIONS") return new Response(null, { headers: HDR });
    const all = await Promise.all(Object.entries(LG).map(([k, v]) => league(k, v).catch(() => [])));
    return new Response(JSON.stringify({ m: all.flat(), t: Date.now() }), { headers: HDR });
  },
};
