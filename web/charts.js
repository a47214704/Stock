/* 圖表：手寫 inline SVG，零外部依賴。
 *
 * 幾個刻意的設計決定：
 * - 沒有任何雙 Y 軸圖。融資餘額與外資庫存的量級差好幾個數量級，
 *   硬疊在一張圖上會憑空製造出不存在的相關性，所以拆成各自獨立的圖。
 * - 資料密度高（一般 200 個交易日），逐點 hover 的命中率太低，
 *   因此折線與柱狀都用覆蓋層取「最近的日期索引」，指標只要靠近就好。
 * - 每張圖都有表格檢視。圖表的青色系列在淺色底下對比未達 3:1，
 *   規範要求提供替代讀值途徑，表格就是那條途徑。
 */

const NBSP = " ";

export const fmt = {
  num(v, digits = 2) {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    return v.toLocaleString("zh-TW", {
      minimumFractionDigits: digits, maximumFractionDigits: digits,
    });
  },
  int(v) {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    return Math.round(v).toLocaleString("zh-TW");
  },
  /** 大數字縮寫成「億／萬」，用於軸標籤與庫存數字。 */
  compact(v) {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    const abs = Math.abs(v);
    if (abs >= 1e8) return (v / 1e8).toFixed(abs >= 1e9 ? 0 : 1) + "億";
    if (abs >= 1e4) return (v / 1e4).toFixed(abs >= 1e5 ? 0 : 1) + "萬";
    return Math.round(v).toLocaleString("zh-TW");
  },
  pct(v, digits = 1) {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    return (v * 100).toFixed(digits) + "%";
  },
  date(iso) { return iso ? iso.slice(2) : "—"; },
};

const SVG_NS = "http://www.w3.org/2000/svg";

function el(name, attrs = {}, parent = null) {
  const node = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs)) {
    if (v !== null && v !== undefined) node.setAttribute(k, String(v));
  }
  if (parent) parent.appendChild(node);
  return node;
}

function text(parent, x, y, content, attrs = {}) {
  const node = el("text", { x, y, ...attrs }, parent);
  node.textContent = content;          // 系列名稱可能來自 API，一律走 textContent
  return node;
}

/** 把區間切成好看的刻度：1 / 2 / 2.5 / 5 × 10^n。
 *
 * 不能只取「第一個 >= 目標間距」的候選——候選之間的跳幅很大（0.5 直接跳到 1），
 * 挑到過粗的 step 會讓整張圖只剩一兩條刻度線。改成在多個數量級的候選中，
 * 挑實際刻度數最接近目標的那個。 */
function niceTicks(min, max, count = 4) {
  if (!(max > min)) return [min];
  const span = max - min;
  const base = Math.pow(10, Math.floor(Math.log10(span)));
  const steps = [];
  for (const mag of [base / 100, base / 10, base, base * 10]) {
    for (const m of [1, 2, 2.5, 5]) steps.push(m * mag);
  }
  steps.sort((a, b) => a - b);

  let best = null;
  for (const step of steps) {
    const n = Math.floor(max / step) - Math.ceil(min / step) + 1;
    if (n < 2) continue;
    const score = Math.abs(n - count);
    if (!best || score < best.score) best = { step, score };
  }
  const step = best ? best.step : span / count;

  // 用整數倍數累加，避免浮點誤差累積出 0.30000000000000004 這種刻度
  const ticks = [];
  for (let i = Math.ceil(min / step); i * step <= max + step * 1e-6; i += 1) {
    const t = i * step;
    ticks.push(Math.abs(t) < step * 1e-6 ? 0 : t);
  }
  return ticks;
}

/** 由刻度間距推小數位數。軸刻度要的是乾淨數字（120 而不是 120.00），
 *  數值本身則另用 format 保留精度。 */
function decimalsFor(step) {
  if (!(step > 0)) return 0;
  return Math.min(3, Math.max(0, Math.ceil(-Math.log10(step))));
}

function extent(arrays) {
  let lo = Infinity, hi = -Infinity;
  for (const arr of arrays) {
    for (const v of arr) {
      if (v === null || v === undefined || Number.isNaN(v)) continue;
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
  }
  return Number.isFinite(lo) ? [lo, hi] : [0, 1];
}

/* ------------------------------------------------------------------ 版面 */

const M = { top: 12, right: 62, bottom: 26, left: 58 };

function scaffold(plot, height) {
  plot.querySelector("svg")?.remove();
  const width = Math.max(plot.clientWidth || 640, 320);
  const svg = el("svg", {
    width, height, viewBox: `0 0 ${width} ${height}`,
    role: "img", "aria-hidden": "true",
  });
  plot.insertBefore(svg, plot.firstChild);
  return {
    svg, width, height,
    x0: M.left, x1: width - M.right,
    y0: M.top, y1: height - M.bottom,
  };
}

function drawGrid(g, box, ticks, yScale, format) {
  for (const t of ticks) {
    const y = yScale(t);
    el("line", {
      x1: box.x0, x2: box.x1, y1: y, y2: y,
      stroke: "var(--grid)", "stroke-width": 1, "shape-rendering": "crispEdges",
    }, g);
    text(g, box.x0 - 8, y + 4, format(t), {
      "text-anchor": "end", fill: "var(--ink-muted)", "font-size": 11,
      "font-variant-numeric": "tabular-nums",
    });
  }
}

function drawXAxis(g, box, dates, count = 6) {
  el("line", {
    x1: box.x0, x2: box.x1, y1: box.y1, y2: box.y1,
    stroke: "var(--axis)", "stroke-width": 1, "shape-rendering": "crispEdges",
  }, g);
  if (dates.length < 2) return;
  const step = Math.max(1, Math.floor((dates.length - 1) / (count - 1)));
  for (let i = 0; i < dates.length; i += step) {
    const x = box.x0 + (box.x1 - box.x0) * (i / (dates.length - 1));
    text(g, x, box.y1 + 16, fmt.date(dates[i]), {
      "text-anchor": i === 0 ? "start" : "middle",
      fill: "var(--ink-muted)", "font-size": 11,
      "font-variant-numeric": "tabular-nums",
    });
  }
}

/* -------------------------------------------------------------- 互動層 */

/** 透明覆蓋層：抓最近的日期索引，滑鼠與鍵盤共用同一套讀值。 */
function interactionLayer(plot, box, dates, onIndex) {
  const svg = plot.querySelector("svg");
  const layer = el("rect", {
    x: box.x0, y: box.y0, width: box.x1 - box.x0, height: box.y1 - box.y0,
    fill: "transparent", tabindex: 0, role: "application",
    "aria-label": "圖表資料，可用左右方向鍵逐日檢視",
    style: "cursor: crosshair; outline: none;",
  }, svg);

  const span = box.x1 - box.x0;
  const nearest = clientX => {
    const rect = svg.getBoundingClientRect();
    const ratio = (clientX - rect.left - box.x0) / span;
    return Math.max(0, Math.min(dates.length - 1,
      Math.round(ratio * (dates.length - 1))));
  };

  let current = dates.length - 1;
  layer.addEventListener("pointermove", e => onIndex(current = nearest(e.clientX)));
  layer.addEventListener("pointerleave", () => onIndex(null));
  layer.addEventListener("focus", () => onIndex(current));
  layer.addEventListener("blur", () => onIndex(null));
  layer.addEventListener("keydown", e => {
    const delta = { ArrowLeft: -1, ArrowRight: 1, Home: -1e9, End: 1e9 }[e.key];
    if (delta === undefined) return;
    e.preventDefault();
    current = Math.max(0, Math.min(dates.length - 1, current + delta));
    onIndex(current);
  });
  return layer;
}

function tooltip(plot) {
  let node = plot.querySelector(".tip");
  if (!node) {
    node = document.createElement("div");
    node.className = "tip";
    node.setAttribute("role", "status");
    plot.appendChild(node);
  }
  return {
    hide() { node.classList.remove("show"); },
    show(x, when, rows) {
      node.replaceChildren();
      const head = document.createElement("div");
      head.className = "when";
      head.textContent = when;
      node.appendChild(head);
      for (const r of rows) {
        const row = document.createElement("div");
        row.className = "row";
        if (r.color) {
          const key = document.createElement("span");
          key.className = "key";
          key.style.background = r.color;
          row.appendChild(key);
        }
        const name = document.createElement("span");
        name.className = "n";
        name.textContent = r.name;                 // 未信任字串，走 textContent
        const value = document.createElement("span");
        value.className = "v";
        value.textContent = r.value;
        row.append(name, value);
        node.appendChild(row);
      }
      node.classList.add("show");
      // 靠右時把提示框翻到左邊，避免被卡片邊界裁切
      const w = node.offsetWidth || 150;
      const max = plot.clientWidth - w - 8;
      node.style.left = Math.max(8, Math.min(max, x - w / 2)) + "px";
      node.style.top = "10px";
    },
  };
}

/* ------------------------------------------------------------ 表格檢視 */

export function renderTable(host, columns, rows) {
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const tr = document.createElement("tr");
  for (const c of columns) {
    const th = document.createElement("th");
    th.textContent = c.label;
    if (c.num) th.className = "num";
    tr.appendChild(th);
  }
  thead.appendChild(tr);
  const tbody = document.createElement("tbody");
  for (const row of rows) {
    const line = document.createElement("tr");
    row.forEach((cell, i) => {
      const td = document.createElement("td");
      td.textContent = cell;
      if (columns[i].num) td.className = "num";
      line.appendChild(td);
    });
    tbody.appendChild(line);
  }
  table.append(thead, tbody);
  host.replaceChildren(table);
}

/* -------------------------------------------------------------- 折線圖 */

/**
 * @param {{dates: string[], series: {name,color,values,dash?}[],
 *          height?: number, format?: (v:number)=>string}} opts
 */
export function lineChart(plot, opts) {
  const { dates, series, height = 260, format, tickFormat } = opts;
  const value = format ?? fmt.num;
  const draw = () => {
    const box = scaffold(plot, height);
    const [lo, hi] = extent(series.map(s => s.values));
    const pad = (hi - lo) * 0.08 || 1;
    const ticks = niceTicks(lo - pad, hi + pad);
    const step = ticks.length > 1 ? ticks[1] - ticks[0] : 0;
    const digits = decimalsFor(step);
    const tick = tickFormat ?? format ?? (v => fmt.num(v, digits));
    const min = Math.min(ticks[0], lo - pad);
    const max = Math.max(ticks[ticks.length - 1], hi + pad);
    const yScale = v => box.y1 - (v - min) / (max - min) * (box.y1 - box.y0);
    const xScale = i => box.x0 + (box.x1 - box.x0) * (i / Math.max(1, dates.length - 1));

    const g = el("g", {}, box.svg);
    drawGrid(g, box, ticks, yScale, tick);
    drawXAxis(g, box, dates);

    const endLabels = [];
    for (const s of series) {
      let path = "";
      let open = false;
      s.values.forEach((v, i) => {
        if (v === null || v === undefined || Number.isNaN(v)) { open = false; return; }
        path += `${open ? "L" : "M"}${xScale(i).toFixed(1)} ${yScale(v).toFixed(1)}`;
        open = true;
      });
      if (path) {
        el("path", {
          d: path, fill: "none", stroke: s.color, "stroke-width": 2,
          "stroke-linejoin": "round", "stroke-linecap": "round",
        }, g);
      }
      // 端點圓點：每個系列都畫，身分由圖例承擔
      const lastIdx = s.values.findLastIndex(v => v !== null && v !== undefined);
      if (lastIdx >= 0) {
        const cx = xScale(lastIdx), cy = yScale(s.values[lastIdx]);
        el("circle", {
          cx, cy, r: 4, fill: s.color,
          stroke: "var(--surface)", "stroke-width": 2,   // 2px 表面色環
        }, g);
        endLabels.push({ x: cx, y: cy, raw: s.values[lastIdx] });
      }
    }

    /* 端點標值只做選擇性標註。系列在右端收斂時（季線與扣抵值最後必然黏在一起）
     * 硬把標籤上下推開會讓標籤脫離自己的線、反而更難讀，規範也明確禁止。
     * 這裡按系列順序放置，與已放置標籤距離不足的就整個略過，
     * 該值仍可由 tooltip 與表格檢視讀到。 */
    const placed = [];
    const room = box.width - 6;
    for (const label of endLabels) {
      if (placed.some(y => Math.abs(y - label.y) < 13)) continue;
      // 精確值放不下時退回縮寫，仍放不下就整個略過。
      // 標籤是圖表註記，不是唯一的讀值途徑——tooltip 與表格檢視都有完整數字。
      const fitted = [value(label.raw), tick(label.raw)]
        .find(t => label.x + 9 + t.length * 6.4 <= room);
      if (!fitted) continue;
      placed.push(label.y);
      text(g, label.x + 9, label.y + 4, fitted, {
        fill: "var(--ink-2)", "font-size": 11.5,
        "font-variant-numeric": "tabular-nums",
      });
    }

    // 游標層
    const cursor = el("g", { style: "display:none" }, box.svg);
    const hair = el("line", {
      y1: box.y0, y2: box.y1, stroke: "var(--axis)", "stroke-width": 1,
      "shape-rendering": "crispEdges",
    }, cursor);
    const dots = series.map(s => el("circle", {
      r: 4.5, fill: s.color, stroke: "var(--surface)", "stroke-width": 2,
    }, cursor));

    const tip = tooltip(plot);
    interactionLayer(plot, box, dates, idx => {
      if (idx === null) { cursor.style.display = "none"; tip.hide(); return; }
      const x = xScale(idx);
      cursor.style.display = "";
      hair.setAttribute("x1", x); hair.setAttribute("x2", x);
      const rows = [];
      series.forEach((s, i) => {
        const v = s.values[idx];
        const shown = v !== null && v !== undefined && !Number.isNaN(v);
        dots[i].style.display = shown ? "" : "none";
        if (shown) {
          dots[i].setAttribute("cx", x);
          dots[i].setAttribute("cy", yScale(v));
        }
        rows.push({ name: s.name, color: s.color, value: shown ? value(v) : "—" });
      });
      tip.show(x, dates[idx], rows);
    });
  };

  draw();
  observe(plot, draw);
}

/* ------------------------------------------------- 零軸發散的柱狀圖 */

/**
 * MACD 柱狀體。正負由**零軸上下的位置**表達，顏色只是附帶台股慣例，
 * 因此紅綠對色盲不友善這件事不會讓任何資訊消失；仍提供色盲友善配色與表格。
 */
export function divergingBars(plot, opts) {
  const {
    dates, values, height = 170, format = v => fmt.num(v, 3),
    posColor = "var(--up)", negColor = "var(--down)", name = "柱狀體",
    posLabel = "紅", negLabel = "綠",
  } = opts;

  const draw = () => {
    const box = scaffold(plot, height);
    const [lo, hi] = extent([values]);
    const bound = Math.max(Math.abs(lo), Math.abs(hi)) * 1.12 || 1;
    const ticks = niceTicks(-bound, bound, 2);
    const tickStep = ticks.length > 1 ? ticks[1] - ticks[0] : 0;
    const tick = v => fmt.num(v, decimalsFor(tickStep));
    const yScale = v => box.y1 - (v + bound) / (2 * bound) * (box.y1 - box.y0);
    const slot = (box.x1 - box.x0) / Math.max(1, values.length);
    // 上限 24px，並保留 2px 表面間隙讓相鄰柱體自然分開
    const barW = Math.max(1, Math.min(24, slot - 2));
    const xCenter = i => box.x0 + slot * (i + 0.5);

    const g = el("g", {}, box.svg);
    drawGrid(g, box, ticks, yScale, tick);
    drawXAxis(g, box, dates);

    const zero = yScale(0);
    const bars = values.map((v, i) => {
      if (v === null || v === undefined || Number.isNaN(v)) return null;
      const y = yScale(v);
      const top = Math.min(y, zero), h = Math.max(1, Math.abs(y - zero));
      // 資料端 4px 圓角、零軸端保持方角
      const r = Math.min(4, barW / 2, h);
      const x = xCenter(i) - barW / 2;
      const up = v >= 0;
      const d = up
        ? `M${x} ${zero} L${x} ${top + r} Q${x} ${top} ${x + r} ${top}
           L${x + barW - r} ${top} Q${x + barW} ${top} ${x + barW} ${top + r}
           L${x + barW} ${zero} Z`
        : `M${x} ${zero} L${x} ${top + h - r} Q${x} ${top + h} ${x + r} ${top + h}
           L${x + barW - r} ${top + h} Q${x + barW} ${top + h} ${x + barW} ${top + h - r}
           L${x + barW} ${zero} Z`;
      return el("path", { d, fill: up ? posColor : negColor }, g);
    });

    // 零軸畫在柱體之上，保證「正負」這個資訊永遠讀得到
    el("line", {
      x1: box.x0, x2: box.x1, y1: zero, y2: zero,
      stroke: "var(--axis)", "stroke-width": 1, "shape-rendering": "crispEdges",
    }, box.svg);

    const cursor = el("g", { style: "display:none" }, box.svg);
    const highlight = el("rect", {
      y: box.y0, height: box.y1 - box.y0,
      fill: "var(--ink)", opacity: .06,
    }, cursor);

    const tip = tooltip(plot);
    interactionLayer(plot, box, dates, idx => {
      if (idx === null) { cursor.style.display = "none"; tip.hide(); return; }
      cursor.style.display = "";
      highlight.setAttribute("x", xCenter(idx) - Math.max(barW, 6) / 2);
      highlight.setAttribute("width", Math.max(barW, 6));
      const v = values[idx];
      const has = v !== null && v !== undefined && !Number.isNaN(v);
      tip.show(xCenter(idx), dates[idx], [{
        name: has ? `${name}（${v >= 0 ? posLabel : negLabel}）` : name,
        color: has ? (v >= 0 ? posColor : negColor) : null,
        value: has ? format(v) : "—",
      }]);
      void bars;
    });
  };

  draw();
  observe(plot, draw);
}

/* ---------------------------------------------------------------- 工具 */

/** 容器寬度改變時重繪。用 rAF 併批，避免 resize 期間狂重畫。 */
function observe(plot, draw) {
  if (plot._ro) plot._ro.disconnect();
  let width = plot.clientWidth;
  let queued = false;
  plot._ro = new ResizeObserver(() => {
    if (plot.clientWidth === width || queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      width = plot.clientWidth;
      draw();
    });
  });
  plot._ro.observe(plot);
}

export { NBSP };
