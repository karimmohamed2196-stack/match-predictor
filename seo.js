// يولّد صفحة ثابتة لكل مباراة جاية (m/*.html) + m/index.html + sitemap.xml من data.json
const fs = require("fs");
const BASE = (process.env.SITE_URL || "https://karimmohamed2196-stack.github.io/match-predictor").replace(/\/$/, "") + "/";
const D = JSON.parse(fs.readFileSync("data.json", "utf8"));
const html = fs.readFileSync("index.html", "utf8");
function grab(name) {
  const i = html.indexOf("var " + name + "="); if (i < 0) return {};
  const s = html.indexOf("{", i); let d = 0, q = null, j = s;
  for (; j < html.length; j++) { const c = html[j];
    if (q) { if (c === "\\") j++; else if (c === q) q = null; }
    else if (c === '"' || c === "'") q = c; else if (c === "{") d++; else if (c === "}" && --d === 0) break; }
  try { return JSON.parse(html.slice(s, j + 1)); } catch (e) { return {}; }
}
const PN = grab("PN"), tn = n => PN[n] || n;
const LN = { E0: "الدوري الإنجليزي الممتاز", SP1: "الدوري الإسباني", I1: "الدوري الإيطالي", D1: "الدوري الألماني", F1: "الدوري الفرنسي", EGY: "الدوري المصري", KSA: "الدوري السعودي", UCL: "دوري أبطال أوروبا", UEL: "الدوري الأوروبي" };
const DAY = { Mon: "الإثنين", Tue: "الثلاثاء", Wed: "الأربعاء", Thu: "الخميس", Fri: "الجمعة", Sat: "السبت", Sun: "الأحد" };
const MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const MAR = ["يناير","فبراير","مارس","أبريل","مايو","يونيو","يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"];
const N = 10, sw = T => { const n = T[3] || 60; return Math.min(1, (n / (n + 10)) / .75); };
const KF = () => { const k = D._cfg && D._cfg.k; return k >= .6 && k <= 1.3 ? k : 1; };
const pois = (l, n) => { let p = Math.exp(-l); const a = [p]; for (let k = 1; k < n; k++) { p *= l / k; a.push(p); } return a; };
const tau = (i, j, l, m, r) => !r ? 1 : i === 0 && j === 0 ? 1 - l * m * r : i === 0 && j === 1 ? 1 + l * r : i === 1 && j === 0 ? 1 + m * r : i === 1 && j === 1 ? 1 - r : 1;
function pred(c, h, a) {
  const m = D[c], H = m && m.teams && m.teams[h], A = m && m.teams && m.teams[a]; if (!H || !A) return null;
  const lh = Math.exp(m.mu + m.ha + (H[0] * sw(H) + A[1] * sw(A)) * KF()), la = Math.exp(m.mu + (A[0] * sw(A) + H[1] * sw(H)) * KF());
  const ph = pois(lh, N), pa = pois(la, N), S = []; let t = 0;
  for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) { const p = ph[i] * pa[j] * tau(i, j, lh, la, m.rho || 0); S.push([i, j, p]); t += p; }
  let w = 0, d = 0, o = 0, b = 0; S.forEach(s => { s[2] /= t; if (s[0] > s[1]) w += s[2]; else if (s[0] === s[1]) d += s[2]; if (s[0] + s[1] > 2) o += s[2]; if (s[0] > 0 && s[1] > 0) b += s[2]; });
  return { w, d, l: 1 - w - d, o, b, lh, la, top: S.sort((x, y) => y[2] - x[2]).slice(0, 3), H, A };
}
const rank = (T, t, ix, asc) => { const a = Object.keys(T).sort((x, y) => asc ? T[x][ix] - T[y][ix] : T[y][ix] - T[x][ix]); return (a.indexOf(t) + 1) + " من " + a.length; };
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const slug = s => s.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const pc = x => Math.round(x * 100) + "%";
const now = new Date();
function when(f) { const p = f[1].split(" "), mi = MON.indexOf(p[2]), dd = +p[1]; let y = now.getUTCFullYear(); let dt = Date.UTC(y, mi, dd);
  if (dt < now - 60 * 864e5) y++; else if (dt > now.getTime() + 300 * 864e5) y--; return { y, mi, dd, p, ms: Date.UTC(y, mi, dd) }; }
fs.rmSync("m", { recursive: true, force: true }); fs.mkdirSync("m");
const pages = [], today = now.toISOString().slice(0, 10);
const css = "<style>:root{--bg:#fbfaf6;--tx:#1c1a14;--mu:#6b665a;--c:#fff;--bd:#e6e1d3;--g:#c9a24b}@media(prefers-color-scheme:dark){:root{--bg:#0b0d12;--tx:#eceae4;--mu:#9a9a9a;--c:#151821;--bd:#272b36}}body{margin:0;background:var(--bg);color:var(--tx);font:16px/1.8 system-ui,'Segoe UI',Tahoma,sans-serif}main{max-width:680px;margin:0 auto;padding:18px 14px 40px}.c{background:var(--c);border:1px solid var(--bd);border-radius:16px;padding:14px;margin:12px 0}h1{font-size:22px;line-height:1.5}h2{font-size:17px;margin:0 0 6px}.mu{color:var(--mu);font-size:14px}.r{display:flex;justify-content:space-between;border-bottom:1px dashed var(--bd);padding:7px 0}.bar{height:12px;border-radius:6px;background:var(--bd);overflow:hidden;direction:ltr}.bar i{display:block;height:100%;background:var(--g)}a.b{display:inline-block;background:var(--g);color:#000;font-weight:700;padding:10px 18px;border-radius:12px;text-decoration:none}a{color:inherit}</style>";
(D._fix || []).forEach(f => {
  if (!LN[f[0]]) return; const w = when(f); if (w.ms < Date.parse(today) - 864e5) return;
  const o = pred(f[0], f[2], f[3]); if (!o) return;
  const H = tn(f[2]), A = tn(f[3]), L = LN[f[0]], ds = (DAY[w.p[0]] || w.p[0]) + " " + w.dd + " " + MAR[w.mi] + " " + w.y + (w.p[3] ? " الساعة " + w.p[3] + " بتوقيت القاهرة" : "");
  const name = slug(f[2]) + "-vs-" + slug(f[3]) + "-" + w.dd + MON[w.mi].toLowerCase(); const url = BASE + "m/" + name + ".html";
  const T = D[f[0]].teams, fv = o.w >= o.l ? [H, o.w] : [A, o.l], title = `توقع مباراة ${H} ضد ${A} في ${L} | ${pc(o.w)} - ${pc(o.d)} - ${pc(o.l)}`;
  const desc = `توقع مباراة ${H} ضد ${A} يوم ${ds}: فرصة فوز ${H} ${pc(o.w)} والتعادل ${pc(o.d)} وفوز ${A} ${pc(o.l)}. تحليل بنموذج Dixon-Coles مع الأهداف المتوقعة والنتائج الأرجح.`;
  const form = n => { const s = (T[n] && T[n][2]) || ""; return s ? s + " (" + (s.match(/W/g) || []).length + " فوز من " + s.length + ")" : "غير متاح"; };
  const ld = { "@context": "https://schema.org", "@type": "SportsEvent", name: `${H} ضد ${A}`, startDate: `${w.y}-${String(w.mi + 1).padStart(2, "0")}-${String(w.dd).padStart(2, "0")}`, sport: "كرة القدم", homeTeam: { "@type": "SportsTeam", name: H }, awayTeam: { "@type": "SportsTeam", name: A }, description: desc, url };
  const row = (a, b) => `<div class="r"><span>${a}</span><b>${b}</b></div>`;
  const bar = (n, v) => `<div style="margin:8px 0"><div class="r" style="border:0;padding:0"><span>${esc(n)}</span><b dir="ltr">${pc(v)}</b></div><div class="bar"><i style="width:${Math.round(v * 100)}%"></i></div></div>`;
  fs.writeFileSync("m/" + name + ".html", `<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(title)}</title><meta name="description" content="${esc(desc)}"><link rel="canonical" href="${url}"><meta property="og:type" content="article"><meta property="og:title" content="${esc(title)}"><meta property="og:description" content="${esc(desc)}"><meta property="og:url" content="${url}"><meta property="og:locale" content="ar_AR"><meta name="twitter:card" content="summary"><script type="application/ld+json">${JSON.stringify(ld)}</script>${css}</head><body><main>
<p class="mu"><a href="${BASE}">متوقع المباريات PRO</a> › <a href="${BASE}m/">كل التوقعات</a> › ${esc(L)}</p>
<h1>توقع مباراة ${esc(H)} ضد ${esc(A)}</h1><p class="mu">${esc(L)} • ${esc(ds)}</p>
<div class="c"><h2>احتمالات النتيجة</h2>${bar("فوز " + H, o.w)}${bar("تعادل", o.d)}${bar("فوز " + A, o.l)}<p class="mu">النموذج بيرجّح <b>${esc(fv[0])}</b> بنسبة ${pc(fv[1])}${Math.max(o.w, o.d, o.l) < .4 ? "، والمباراة متقاربة جداً" : ""}.</p></div>
<div class="c"><h2>الأهداف والنتائج الأرجح</h2>${row("الأهداف المتوقعة", o.lh.toFixed(2) + " - " + o.la.toFixed(2))}${row("أكثر من 2.5 هدف", pc(o.o))}${row("الفريقان يسجّلان", pc(o.b))}${o.top.map((s, i) => row("نتيجة أرجح #" + (i + 1), `<span dir="ltr">${s[0]} - ${s[1]}</span> (${pc(s[2])})`)).join("")}</div>
<div class="c"><h2>الفريقان في الأرقام</h2>${row(esc(H) + " - الفورمة", esc(form(f[2])))}${row(esc(H) + " - ترتيب الهجوم / الدفاع", rank(T, f[2], 0, false) + " / " + rank(T, f[2], 1, true))}${row(esc(A) + " - الفورمة", esc(form(f[3])))}${row(esc(A) + " - ترتيب الهجوم / الدفاع", rank(T, f[3], 0, false) + " / " + rank(T, f[3], 1, true))}</div>
<p><a class="b" href="${BASE}">افتح التطبيق كامل (إصابات، قسايم، تنبيهات)</a></p>
<p class="mu">التوقع من نموذج إحصائي (Dixon-Coles) للتعلّم والتسلية، وليس ضماناً لأي نتيجة. الأرقام هنا قبل تعديلات الإصابات. +18 | العب بمسؤولية.</p></main></body></html>`);
  pages.push({ url, name, L, H, A, ms: w.ms, ds, lg: f[0] });
});
pages.sort((a, b) => a.ms - b.ms);
const by = {}; pages.forEach(p => (by[p.lg] = by[p.lg] || []).push(p));
fs.writeFileSync("m/index.html", `<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>توقعات مباريات كرة القدم اليوم وغداً | متوقع المباريات PRO</title><meta name="description" content="توقعات كل مباريات الدوريات الكبرى ودوري الأبطال والدوري المصري والسعودي بنسب الفوز والتعادل."><link rel="canonical" href="${BASE}m/">${css}</head><body><main><p class="mu"><a href="${BASE}">متوقع المباريات PRO</a></p><h1>توقعات مباريات كرة القدم</h1>${Object.keys(by).map(k => `<div class="c"><h2>${LN[k]}</h2>${by[k].map(p => `<div class="r"><a href="${p.name}.html">${esc(p.H)} × ${esc(p.A)}</a><span class="mu">${esc(p.ds.split(" الساعة")[0])}</span></div>`).join("")}</div>`).join("") || '<p class="mu">مفيش مباريات جاية دلوقتي.</p>'}</main></body></html>`);
fs.writeFileSync("sitemap.xml", `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n` + [BASE, BASE + "m/"].concat(pages.map(p => p.url)).map(u => `<url><loc>${u}</loc><lastmod>${today}</lastmod></url>`).join("\n") + "\n</urlset>\n");
console.log("pages:", pages.length);
