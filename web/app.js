import { divergingBars, fmt, lineChart, renderTable } from "./charts.js";

/* ---------------------------------------------------------- 資料來源 */

/* 依序試這幾個位置，第一個能取到 signals.json 的就是資料來源。
 * 這樣同一份程式在 GitHub Pages（data/ 與 index.html 同層）、
 * 本機從 repo 根目錄起靜態伺服器（web/../data）、
 * 以及還沒跑過 ETL 只有示範資料時，都不必改設定。 */
const CANDIDATES = ["data", "../data", "demo"];

const store = {
  base: null, isDemo: false,
  signals: null, screenAll: null,
  // 全市場精簡結果，以代號索引。個股頁在名單外的個股靠它顯示摘要，
  // 否則點進去會是一片空白。
  compact: new Map(),
  screenAllReady: null,
  history: new Map(),
};

async function getJSON(url) {
  const resp = await fetch(url, { cache: "no-cache" });
  if (!resp.ok) throw new Error(`${resp.status} ${url}`);
  return resp.json();
}

async function resolveBase() {
  const param = new URLSearchParams(location.search).get("data");
  const candidates = param ? [param, ...CANDIDATES] : CANDIDATES;
  const failures = [];
  for (const base of candidates) {
    try {
      store.signals = await getJSON(`${base}/signals.json`);
      store.base = base;
      store.isDemo = base === "demo";
      return;
    } catch (err) {
      failures.push(`${base}（${err.message}）`);
    }
  }
  throw new Error(`找不到資料。已嘗試：${failures.join("、")}`);
}

/* ------------------------------------------------------------ 條件定義 */

const CONDITIONS = {
  consolidation: {
    label: "盤整三個月以上", group: "consolidation",
    rows: c => [
      // 判定看固定 60 日窗口，這裡另外顯示箱型實際已經走了多久
      ["已盤整", c.run_days ? `${c.run_days} 個交易日` : "—"],
      ["區間幅度（60 日）", fmt.pct(c.range_pct)],
      ["區間高／低", `${fmt.num(c.high)} / ${fmt.num(c.low)}`],
      ["現價在區間位置", c.position === null ? "—" : fmt.pct(c.position, 0)],
      ["淨漂移／箱寬", c.drift_ratio === null || c.drift_ratio === undefined
        ? "—" : fmt.num(c.drift_ratio, 2)],
      ["季線斜率", c.ma_slope_pct === null ? "—" : fmt.pct(c.ma_slope_pct, 3) + "/日"],
    ],
  },
  ma_turn_up: {
    label: "季線扣底翻揚", group: "ma_turn_up",
    rows: c => [
      ["季線", fmt.num(c.ma)],
      // 「往下剛剛要往上」是轉折：中期下彎、近期斜率翻正
      ["中期下彎", c.was_falling ? "是" : "否"],
      ["季線中期變化", c.downtrend_pct === null || c.downtrend_pct === undefined
        ? "—" : fmt.pct(c.downtrend_pct)],
      ["近期斜率", c.ma_slope_pct === null ? "—" : fmt.pct(c.ma_slope_pct, 3) + "/日"],
      ["目前扣抵值", fmt.num(c.deduction)],
      ["未來扣抵均價", fmt.num(c.future_deduction_mean)],
      ["扣抵值分位", c.deduction_percentile === null ? "—" : fmt.pct(c.deduction_percentile, 0)],
      ["明日季線上揚", c.rises_tomorrow ? "是" : "否"],
    ],
  },
  margin_declining: {
    label: "融資三個月遞減", group: "chips",
    rows: c => [
      ["期間變化", fmt.pct(c.change_pct)],
      ["期初／期末", `${fmt.compact(c.first)} / ${fmt.compact(c.last)}`],
      ["迴歸斜率", fmt.int(c.slope) + " 張/日"],
    ],
  },
  foreign_increasing: {
    label: "外資庫存增加", group: "chips",
    // 上櫃的來源只提供持股比例、沒有股數，這時判斷依據會是比例。
    // 兩者通常一致，但遇到現金增資這類股本變動會不同，所以要標明。
    rows: c => {
      const byRatio = c.basis === "ratio";
      const unit = byRatio ? "%" : "股";
      return [
        ["判斷依據", byRatio ? "持股比例" : "持有股數"],
        ["期間變化", fmt.pct(c.change_pct)],
        ["期初／期末", byRatio
          ? `${fmt.num(c.first)}% / ${fmt.num(c.last)}%`
          : `${fmt.compact(c.first)} / ${fmt.compact(c.last)}`],
        ["迴歸斜率", (byRatio ? fmt.num(c.slope, 4) : fmt.compact(c.slope))
          + ` ${unit}/日`],
      ];
    },
  },
  institutional_net_buy: {
    label: "三大法人合計買超", group: "chips",
    rows: c => [
      ["合計買超", fmt.compact(c.net_shares) + " 股"],
      ["觀察天數", `${c.days ?? "—"} 日`],
    ],
  },
  macd: {
    label: "MACD 收斂轉紅", group: "macd",
    rows: c => [
      ["柱狀體", fmt.num(c.osc, 3)],
      ["前一日", fmt.num(c.prev_osc, 3)],
      ["翻紅距今", c.days_since_cross === null || c.days_since_cross === undefined
        ? "—" : `${c.days_since_cross} 日`],
      ["收斂天數", `${c.converge_days ?? 0} 日`],
    ],
  },
};

const GROUPS = {
  consolidation: "盤整",
  ma_turn_up: "季線扣底",
  chips: "籌碼面",
  macd: "MACD",
};

/* --------------------------------------------------------------- 元件 */

function h(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;      // 一律 textContent
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) node.setAttribute(k, String(v));
  }
  for (const child of [].concat(children)) {
    if (child) node.appendChild(child);
  }
  return node;
}

/** 條件標記。圖示 + 文字，顏色只是輔助，不單獨承載意義。 */
function badge(label, status) {
  const icon = { pass: "✓", fail: "·", insufficient: "?" }[status] ?? "·";
  const cls = { pass: "on", fail: "off", insufficient: "na" }[status] ?? "off";
  const title = { pass: "符合", fail: "不符合", insufficient: "資料不足，尚無法判斷" }[status];
  return h("span", { class: `badge ${cls}`, title: `${label}：${title}` }, [
    h("span", { class: "ic", text: icon, "aria-hidden": "true" }),
    h("span", { text: label }),
    h("span", { class: "vh", text: title }),
  ]);
}

function tile(label, value, sub, hero = false) {
  return h("div", { class: `tile${hero ? " hero" : ""}` }, [
    h("div", { class: "label", text: label }),
    h("div", { class: "value", text: value }),
    sub ? h("div", { class: "sub", text: sub }) : null,
  ]);
}

/** 圖表卡。附「圖／表」切換——青色系列在淺色底對比不足，表格是規範要求的替代讀值途徑。 */
function chartCard(title, sub, legend, render, tableSpec) {
  const plot = h("div", { class: "plot" });
  const tbl = h("div", { class: "tbl" });
  plot.appendChild(tbl);

  const toggle = h("button", {
    class: "btn", type: "button", "aria-pressed": "false",
    text: "表格",
    onclick: () => {
      const asTable = plot.classList.toggle("as-table");
      toggle.setAttribute("aria-pressed", String(asTable));
      toggle.textContent = asTable ? "圖表" : "表格";
      if (asTable && !tbl.dataset.filled) {
        renderTable(tbl, tableSpec.columns, tableSpec.rows());
        tbl.dataset.filled = "1";
      }
    },
  });

  const card = h("div", { class: "chart-card" }, [
    h("div", { class: "chart-head" }, [
      h("h3", { text: title }),
      sub ? h("span", { class: "sub", text: sub }) : null,
      h("span", { class: "spacer" }),
      toggle,
    ]),
    legend,
    plot,
  ]);
  // 進 DOM 後才知道寬度，交由呼叫端在 append 後執行 render
  card._render = () => render(plot);
  return card;
}

function legendOf(items) {
  if (items.length < 2) return null;      // 單一系列不需要圖例，標題已說明
  return h("div", { class: "legend" }, items.map(it =>
    h("span", { class: "item" }, [
      h("span", { class: `key${it.rect ? " rect" : ""}`, style: `background:${it.color}` }),
      h("span", { text: it.name }),
    ])));
}

/* ------------------------------------------------------------- 名單頁 */

const ui = {
  onlyMatched: true,
  group: "all",
  query: "",
  sort: "score",
};

function listRows() {
  const listed = store.signals.results ?? [];
  if (ui.onlyMatched) {
    return listed.map(r => ({
      id: r.stock_id, name: r.name, market: r.market, close: r.close,
      score: r.score, groups: r.groups, detail: r,
      runDays: r.conditions?.consolidation?.run_days ?? null,
      statuses: Object.fromEntries(
        Object.entries(r.conditions).map(([k, v]) => [k, v.status])),
    }));
  }
  const all = store.screenAll;
  if (!all) return [];
  const idx = Object.fromEntries(all.columns.map((c, i) => [c, i]));
  const listedIds = new Set(listed.map(r => r.stock_id));
  return all.rows.map(row => ({
    id: row[idx.stock_id], name: row[idx.name], market: row[idx.market],
    close: row[idx.close], score: row[idx.score],
    runDays: idx.run_days === undefined ? null : row[idx.run_days],
    groups: {
      consolidation: !!row[idx.consolidation], ma_turn_up: !!row[idx.ma_turn_up],
      chips: !!row[idx.chips], macd: !!row[idx.macd],
    },
    detail: listedIds.has(row[idx.stock_id])
      ? listed.find(r => r.stock_id === row[idx.stock_id]) : null,
    statuses: null,
  }));
}

function renderList(root) {
  const s = store.signals;
  const matched = (s.results ?? []).filter(r => r.pass_all).length;

  root.replaceChildren();

  // 有任一條件因歷史不足而無法判斷的檔數。剛上線那幾個月這個數字會很大，
  // 顯示出來才不會讓人把「還不知道」誤讀成「不符合」。
  const pending = (s.results ?? []).filter(r => (r.insufficient ?? []).length).length;

  const gaps = s.missing_breakdown ?? {};
  const topGap = Object.entries(gaps).sort((a, b) => b[1] - a[1])[0];

  root.appendChild(h("div", { class: "hero-row" }, [
    tile("符合全部條件", String(matched),
      `可交易 ${s.tradable ?? "—"} / 全市場 ${s.universe ?? "—"} 檔`, true),
    // 四項同時成立於可交易個股的機率極低，「差一項」才是實用的觀察名單
    tile("差一項", String(s.near_miss ?? 0),
      topGap && topGap[1] ? `多數缺「${GROUPS[topGap[0]] ?? topGap[0]}」` : "—"),
    tile("累積交易日", String(s.trading_days ?? 0), `資料至 ${s.data_date ?? "—"}`),
    tile("資料不足", String(pending), pending ? "尚無法完整判斷" : "全部條件均可判斷"),
  ]));

  if (!matched) {
    root.appendChild(h("div", { class: "notice" }, [
      h("div", {}, [
        h("strong", { text: "今日沒有個股符合全部四組條件。" }),
        h("span", {
          text: "這是常態而非異常——MACD 由綠轉紅是單日事件，要和季線剛翻揚"
            + "在同一天發生本就罕見。下方名單依符合項數排序，並標出各檔缺哪一組。",
        }),
      ]),
    ]));
  }

  // 篩選列：單獨一排，位於所有內容之上，所有下方內容共用同一份切片
  const search = h("input", {
    type: "search", placeholder: "代號或名稱", value: ui.query,
    "aria-label": "搜尋代號或名稱",
    oninput: e => { ui.query = e.target.value.trim(); repaint(); },
  });
  const groupSel = h("select", {
    "aria-label": "只看符合特定條件的個股",
    onchange: e => { ui.group = e.target.value; repaint(); },
  }, [
    h("option", { value: "all", text: "全部條件" }),
    ...Object.entries(GROUPS).map(([k, v]) =>
      h("option", { value: k, text: `符合：${v}` })),
  ]);
  groupSel.value = ui.group;
  const sortSel = h("select", {
    "aria-label": "排序方式",
    onchange: e => { ui.sort = e.target.value; repaint(); },
  }, [
    h("option", { value: "score", text: "符合項數" }),
    h("option", { value: "run", text: "盤整天數" }),
    h("option", { value: "code", text: "代號" }),
    h("option", { value: "close", text: "收盤價" }),
  ]);
  sortSel.value = ui.sort;
  const scopeBtn = h("button", {
    class: "btn", type: "button", "aria-pressed": String(!ui.onlyMatched),
    text: ui.onlyMatched ? "顯示全市場" : "只看入選名單",
    onclick: () => {
      ui.onlyMatched = !ui.onlyMatched;
      renderList(root);
    },
  });

  root.appendChild(h("div", { class: "filters" }, [
    h("div", { class: "group" }, [h("label", { text: "搜尋" }), search]),
    h("div", { class: "group" }, [h("label", { text: "條件" }), groupSel]),
    h("div", { class: "group" }, [h("label", { text: "排序" }), sortSel]),
    h("span", { class: "spacer", style: "flex:1" }),
    scopeBtn,
  ]));

  const body = h("div");
  root.appendChild(body);

  function repaint() {
    let rows = listRows();
    if (ui.group !== "all") rows = rows.filter(r => r.groups[ui.group]);
    if (ui.query) {
      const q = ui.query.toLowerCase();
      rows = rows.filter(r =>
        r.id.includes(q) || (r.name ?? "").toLowerCase().includes(q));
    }
    rows.sort((a, b) => (
      ui.sort === "code" ? a.id.localeCompare(b.id)
        : ui.sort === "close" ? (b.close ?? 0) - (a.close ?? 0)
          : ui.sort === "run" ? (b.runDays ?? -1) - (a.runDays ?? -1)
            || a.id.localeCompare(b.id)
            : (b.score - a.score) || a.id.localeCompare(b.id)
    ));

    if (!rows.length) {
      body.replaceChildren(h("div", { class: "card" }, [
        h("div", { class: "empty", text: "沒有符合條件的個股。" }),
      ]));
      return;
    }

    const table = h("table");
    const thead = h("thead", {}, [h("tr", {}, [
      h("th", { text: "代號 / 名稱" }),
      h("th", { text: "市場" }),
      h("th", { class: "num", text: "收盤" }),
      h("th", { class: "num", text: "已盤整" }),
      h("th", { class: "num", text: "符合" }),
      h("th", { text: "條件" }),
      h("th", { text: "缺" }),
    ])]);
    const tbody = h("tbody");
    for (const r of rows) {
      // 每一列都能點。名單外的個股沒有 K 線圖，但個股頁會顯示現有摘要並
      // 說明原因——點了完全沒反應是最糟的，使用者無從得知為什麼。
      const tr = h("tr", {
        class: "clickable", tabindex: 0, role: "link",
        "aria-label": `查看 ${r.id} ${r.name} 的詳細分析`,
        onclick: () => { location.hash = `#/${r.id}`; },
        onkeydown: e => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault(); location.hash = `#/${r.id}`;
          }
        },
      }, [
        h("td", {}, [
          h("span", { class: "code", text: r.id }),
          h("span", { class: "nm", text: r.name ?? "" }),
        ]),
        h("td", { text: r.market === "tpex" ? "上櫃" : "上市" }),
        h("td", { class: "num", text: fmt.num(r.close) }),
        h("td", { class: "num", text: r.runDays ? `${r.runDays} 日` : "—" }),
        h("td", { class: "num", text: `${r.score} / 6` }),
        h("td", {}, [h("div", { class: "badges" },
          Object.entries(GROUPS).map(([key, label]) => {
            // 有完整明細時用真實狀態（可區分「資料不足」），否則只有過／不過
            const status = r.statuses
              ? groupStatus(r.detail, key)
              : (r.groups[key] ? "pass" : "fail");
            return badge(label, status);
          }))]),
        h("td", {
          text: Object.entries(GROUPS)
            .filter(([key]) => !r.groups[key])
            .map(([, label]) => label).join("、") || "—",
        }),
      ]);
      tbody.appendChild(tr);
    }
    table.append(thead, tbody);

    body.replaceChildren(h("div", { class: "card" }, [
      h("h2", { text: ui.onlyMatched ? "入選名單" : "全市場" }),
      h("p", {
        class: "card-sub",
        text: ui.onlyMatched
          ? "點一列可看該檔的完整判斷依據與圖表。"
          : "全市場只有各條件的過／不過。名單外的個股點進去會有摘要，"
            + "但沒有 K 線圖——歷史圖表只為入選名單產生。",
      }),
      h("div", { class: "scroll" }, [table]),
    ]));
  }

  repaint();
}

/** 群組狀態：任一子條件資料不足就是「資料不足」，全過才是「符合」。 */
function groupStatus(detail, group) {
  if (!detail) return "fail";
  const keys = Object.entries(CONDITIONS)
    .filter(([, meta]) => meta.group === group).map(([k]) => k);
  const states = keys.map(k => detail.conditions[k]?.status ?? "fail");
  if (states.every(s => s === "pass")) return "pass";
  if (states.some(s => s === "insufficient")) return "insufficient";
  return "fail";
}

/* ------------------------------------------------------------- 個股頁 */

async function renderDetail(root, stockId) {
  root.replaceChildren(h("div", { class: "empty", text: "載入中…" }));

  const result = (store.signals.results ?? []).find(r => r.stock_id === stockId);
  // 名單外的個股靠 screen_all 顯示摘要；深連結進來時它可能還在下載
  if (!result && store.screenAllReady) {
    try { await store.screenAllReady; } catch { /* 抓不到就降級 */ }
  }
  const compact = store.compact.get(stockId) ?? null;

  // 圖資在部署時為全市場每一檔現算（見 etl/build.py 的 export_history），
  // 所以任何個股都試著抓。本機只跑過 build 時只有入選名單有檔案，抓不到就降級。
  let history = store.history.get(stockId) ?? null;
  if (!history) {
    try {
      history = await getJSON(`${store.base}/history/${stockId}.json`);
      store.history.set(stockId, history);
    } catch {
      history = null;
    }
  }

  root.replaceChildren();
  root.appendChild(h("div", { class: "crumb" }, [
    h("a", { href: "#/", text: "← 回名單" }),
  ]));

  if (!result && !compact) {
    root.appendChild(h("div", { class: "card" }, [
      h("div", { class: "empty", text: `資料中沒有 ${stockId} 這檔。` }),
    ]));
    return;
  }

  const info = result ?? compact;
  const name = info.name ?? history?.name ?? "";
  const close = info.close ?? history?.close?.at(-1);
  const market = (info.market ?? history?.market) === "tpex" ? "上櫃" : "上市";
  const runDays = result
    ? result.conditions?.consolidation?.run_days
    : compact?.runDays;

  root.appendChild(h("div", { class: "hero-row" }, [
    tile(`${stockId}${name ? "　" + name : ""}`, fmt.num(close), "最新收盤價", true),
    tile("符合項數", `${info.score ?? "—"} / 6`,
      info.pass_all ? "四組條件全數符合" : "未全數符合"),
    tile("市場", market, `資料至 ${store.signals.data_date ?? "—"}`),
    tile("已盤整", runDays ? `${runDays} 日` : "—",
      runDays ? "箱型實際持續天數" : "不構成盤整"),
  ]));

  if (result) {
    root.appendChild(reasonCards(result));
  } else {
    // 只有精簡資料時，至少把四組條件的過／不過顯示出來
    root.appendChild(h("div", { class: "card" }, [
      h("h2", { text: "四組條件" }),
      h("p", {
        class: "card-sub",
        text: "此檔不在入選名單，只有各組的過／不過。每一項條件的實際數字"
          + "（區間幅度、扣抵值、融資變化率等）只為入選名單產生，"
          + "下方圖表則是全市場都有。",
      }),
      h("div", { style: "padding: 14px 20px 20px" }, [
        h("div", { class: "badges" }, Object.entries(GROUPS).map(([key, label]) =>
          badge(label, compact.groups[key] ? "pass" : "fail"))),
      ]),
    ]));
    if (compact.tradable === false) {
      root.appendChild(h("div", { class: "notice" }, [
        h("div", {}, [
          h("strong", { text: "流動性不足。" }),
          h("span", {
            text: "20 日中位成交額低於門檻，這種量級不但難成交，"
              + "融資與外資的百分比變化也多半是雜訊，因此不列入名單。",
          }),
        ]),
      ]));
    }
  }

  if (history) {
    root.appendChild(chartsFor(history));
  } else {
    root.appendChild(h("div", { class: "notice" }, [
      h("div", {}, [
        h("strong", { text: "沒有歷史圖表。" }),
        h("span", {
          text: "圖資是在部署時為全市場現算的，本機只跑過 build 時只有入選名單"
            + "有檔案。跑 python -m etl export --out web/demo/history 即可補上。",
        }),
      ]),
    ]));
  }
}


function reasonCards(result) {
  const wrap = h("div", { class: "reasons" });
  for (const [key, meta] of Object.entries(CONDITIONS)) {
    const cond = result.conditions[key];
    if (!cond) continue;
    const rows = cond.status === "insufficient"
      ? [["需要天數", `${cond.need ?? "—"} 日`], ["目前天數", `${cond.have ?? 0} 日`]]
      : meta.rows(cond);
    wrap.appendChild(h("div", { class: "reason" }, [
      h("div", { class: "rh" }, [badge(meta.label, cond.status)]),
      h("dl", {}, rows.flatMap(([k, v]) => [
        h("dt", { text: k }), h("dd", { text: String(v) }),
      ])),
    ]));
  }
  return wrap;
}

function chartsFor(history) {
  const dates = history.dates ?? [];
  const cards = h("div", { class: "charts" });

  // 1. 價格、季線與扣抵值。三者同一量級、共用一條 Y 軸。
  const priceSeries = [
    { name: "收盤價", color: "var(--series-1)", values: history.close ?? [] },
    { name: "季線 MA60", color: "var(--series-2)", values: history.ma60 ?? [] },
    { name: "扣抵值", color: "var(--series-3)", values: history.deduction ?? [] },
  ];
  cards.appendChild(chartCard(
    "價格、季線與扣抵值",
    "收盤價高於扣抵值，季線隔日就會上揚",
    legendOf(priceSeries),
    plot => lineChart(plot, { dates, series: priceSeries, height: 300 }),
    {
      columns: [{ label: "日期" }, { label: "收盤", num: true },
        { label: "季線", num: true }, { label: "扣抵值", num: true }],
      rows: () => dates.map((d, i) => [
        d, fmt.num(history.close?.[i]), fmt.num(history.ma60?.[i]),
        fmt.num(history.deduction?.[i]),
      ]).reverse(),
    },
  ));

  // 2. MACD 柱狀體。正負由零軸上下的位置表達，紅綠只是附帶台股慣例。
  cards.appendChild(chartCard(
    "MACD 柱狀體",
    "零軸之上為紅、之下為綠",
    null,
    plot => divergingBars(plot, {
      dates, values: history.macd_osc ?? [], height: 180,
    }),
    {
      columns: [{ label: "日期" }, { label: "柱狀體", num: true }, { label: "紅／綠" }],
      rows: () => dates.map((d, i) => {
        const v = history.macd_osc?.[i];
        return [d, fmt.num(v, 3),
          v === null || v === undefined ? "—" : (v >= 0 ? "紅" : "綠")];
      }).reverse(),
    },
  ));

  // 3、4. 融資與外資庫存量級差好幾個數量級，各自一張圖，絕不共用 Y 軸。
  cards.appendChild(chartCard(
    "融資餘額", "三個月持續遞減代表散戶籌碼鬆動", null,
    plot => lineChart(plot, {
      dates, height: 180, format: fmt.int, tickFormat: fmt.compact,
      series: [{ name: "融資餘額（張）", color: "var(--series-1)", values: history.margin_balance ?? [] }],
    }),
    {
      columns: [{ label: "日期" }, { label: "融資餘額（張）", num: true }],
      rows: () => dates.map((d, i) => [d, fmt.int(history.margin_balance?.[i])]).reverse(),
    },
  ));

  cards.appendChild(chartCard(
    "外資庫存", "官方僅提供當日快照，此序列由每日累積而成", null,
    plot => lineChart(plot, {
      dates, height: 180, format: fmt.int, tickFormat: fmt.compact,
      series: [{ name: "外資持有股數", color: "var(--series-1)", values: history.foreign_shares ?? [] }],
    }),
    {
      columns: [{ label: "日期" }, { label: "外資持有股數", num: true }],
      rows: () => dates.map((d, i) => [d, fmt.int(history.foreign_shares?.[i])]).reverse(),
    },
  ));

  requestAnimationFrame(() => {
    for (const card of cards.children) card._render?.();
  });
  return cards;
}

/* ------------------------------------------------------- 偏好與主題 */

function pref(key, fallback) {
  try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
}
function setPref(key, value) {
  try { localStorage.setItem(key, value); } catch { /* 隱私模式下忽略 */ }
}

function mountControls() {
  const host = document.getElementById("controls");
  const theme = pref("theme", "");
  if (theme) document.documentElement.dataset.theme = theme;

  const themeBtn = h("button", {
    class: "btn", type: "button", text: "深／淺色",
    onclick: () => {
      const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      setPref("theme", next);
    },
  });


  host.replaceChildren(themeBtn);
}

/* --------------------------------------------------------------- 路由 */

function route() {
  const root = document.getElementById("view");
  const match = location.hash.match(/^#\/(\d{4})$/);
  if (match) renderDetail(root, match[1]);
  else renderList(root);
}

async function main() {
  const root = document.getElementById("view");
  try {
    await resolveBase();
  } catch (err) {
    root.replaceChildren(h("div", { class: "card" }, [
      h("div", { class: "empty" }, [
        h("p", { text: err.message }),
        h("p", { text: "請先執行 python -m etl fetch && python -m etl build，或用 tools/gen_demo_data.py 產生示範資料。" }),
      ]),
    ]));
    return;
  }

  // 全市場精簡結果較大，名單頁不一定馬上用到，所以不阻擋首次渲染；
  // 但個股頁可能需要它，因此保留 promise 供等待。抓不到就降級。
  store.screenAllReady = getJSON(`${store.base}/screen_all.json`)
    .then(data => {
      store.screenAll = data;
      const idx = Object.fromEntries(data.columns.map((c, i) => [c, i]));
      for (const row of data.rows) {
        store.compact.set(row[idx.stock_id], {
          stock_id: row[idx.stock_id], name: row[idx.name],
          market: row[idx.market], close: row[idx.close],
          score: row[idx.score], runDays: row[idx.run_days],
          tradable: idx.tradable === undefined ? true : !!row[idx.tradable],
          groups: {
            consolidation: !!row[idx.consolidation],
            ma_turn_up: !!row[idx.ma_turn_up],
            chips: !!row[idx.chips], macd: !!row[idx.macd],
          },
        });
      }
    })
    .catch(() => { store.screenAll = null; });

  const stamp = (store.signals.generated_at ?? "").replace("T", " ").replace("Z", " UTC");
  document.getElementById("data-date").textContent =
    `資料日期 ${store.signals.data_date ?? "—"}${stamp ? `　·　更新於 ${stamp}` : ""}`;

  if (store.isDemo) {
    document.getElementById("banner").appendChild(
      h("div", { class: "notice" }, [
        h("div", {}, [
          h("strong", { text: "示範資料。" }),
          h("span", { text: "這是合成的走勢，不是真實行情。跑過 python -m etl fetch 與 build 之後，頁面會自動改讀 data/ 的實際資料。" }),
        ]),
      ]));
  }

  mountControls();
  addEventListener("hashchange", route);
  route();
}

main();
