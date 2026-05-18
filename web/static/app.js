/* Lindner Research Platform — React SPA v2.0
   React 18 + Babel standalone. No build step. CSS-based animations throughout.
   Dark mode via data-theme="dark" on <html>. */

const { useState, useEffect, useRef, useCallback, useMemo, useLayoutEffect } = React;

// ── Helpers ──────────────────────────────────────────────────────────────────
const api = (path, opts = {}) =>
  fetch(path, { credentials: "same-origin", ...opts })
    .then(r => r.json());

function fmtPrice(n) {
  if (n == null) return "—";
  return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtDate(ts) {
  return new Date(ts * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
function fmtDateTime(ts) {
  const d = new Date(ts * 1000);
  const today = new Date();
  const isToday = d.toDateString() === today.toDateString();
  const time = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  return isToday
    ? `Today ${time}`
    : `${d.toLocaleDateString("en-US", { month: "short", day: "numeric" })} ${time}`;
}
function isMarketOpen() {
  const now = new Date();
  const day = now.getUTCDay();
  if (day === 0 || day === 6) return false;
  const mins = now.getUTCHours() * 60 + now.getUTCMinutes();
  return mins >= 13 * 60 + 30 && mins < 20 * 60;
}

// ── Dark Mode ─────────────────────────────────────────────────────────────────
function getInitialTheme() {
  const saved = localStorage.getItem("lindner_theme");
  if (saved) return saved;
  if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) return "dark";
  return "light";
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("lindner_theme", theme);
}

// Apply theme before first render to avoid flash
applyTheme(getInitialTheme());

// ============================================================
// ICON SYSTEM — Heroicons v2 Outline (MIT) · 24px viewBox
// strokeWidth 1.75, strokeLinecap/Join round, currentColor
// ============================================================
const Icon = ({ size = 18, className = '', style, children }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width={size} height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.75"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
    aria-hidden="true"
  >
    {children}
  </svg>
);

const ICONS = {
  Excel:        (p={}) => <Icon {...p}><path d="M3 3h18v18H3V3zm6 0v18m6-18v18M3 9h18M3 15h18"/></Icon>,
  PDF:          (p={}) => <Icon {...p}><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="13" y2="17"/></Icon>,
  Powerpoint:   (p={}) => <Icon {...p}><rect x="2" y="4" width="20" height="13" rx="2"/><path d="M12 17v3m-4 0h8M7 13V9m4 4V7m4 6v-3"/></Icon>,
  Education:    (p={}) => <Icon {...p}><path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"/></Icon>,
  Markdown:     (p={}) => <Icon {...p}><path d="M9 12h6m-6 4h4M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></Icon>,
  File:         (p={}) => <Icon {...p}><path d="M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z"/><polyline points="13 2 13 9 20 9"/></Icon>,
  FolderOpen:   (p={}) => <Icon {...p}><path d="M5 19a2 2 0 01-2-2V7a2 2 0 012-2h4l2 2h4a2 2 0 012 2v1M5 19h14a2 2 0 002-2v-5a2 2 0 00-2-2H9a2 2 0 00-2 2v5a2 2 0 01-2 2z"/></Icon>,
  Download:     (p={}) => <Icon {...p}><path d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3"/></Icon>,
  Check:        (p={}) => <Icon {...p}><path d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></Icon>,
  CheckMark:    (p={}) => <Icon {...p}><polyline points="20 6 9 17 4 12"/></Icon>,
  ErrorX:       (p={}) => <Icon {...p}><path d="M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></Icon>,
  Bell:         (p={}) => <Icon {...p}><path d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0"/></Icon>,
  TrendingUp:   (p={}) => <Icon {...p}><path d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941"/></Icon>,
  TrendingDown: (p={}) => <Icon {...p}><path d="M2.25 6L9 12.75l4.286-4.286a11.948 11.948 0 014.306 6.43l.776 2.898m0 0l3.182-5.511m-3.182 5.51l-5.511-3.181"/></Icon>,
  BarChart:     (p={}) => <Icon {...p}><path d="M3 3v18h18M18 17V9M12 17V3M6 17v-6"/></Icon>,
  ArrowUp:      (p={}) => <Icon {...p}><path d="M12 19.5v-15m0 0l-6.75 6.75M12 4.5l6.75 6.75"/></Icon>,
  ArrowDown:    (p={}) => <Icon {...p}><path d="M12 4.5v15m0 0l6.75-6.75M12 19.5l-6.75-6.75"/></Icon>,
  Phone:        (p={}) => <Icon {...p}><path d="M10.5 1.5H8.25A2.25 2.25 0 006 3.75v16.5a2.25 2.25 0 002.25 2.25h7.5A2.25 2.25 0 0018 20.25V3.75a2.25 2.25 0 00-2.25-2.25H13.5m-3 0V3h3V1.5m-3 0h3m-3 8.25h3"/></Icon>,
  ChartLine:    (p={}) => <Icon {...p}><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></Icon>,
  Sun:          (p={}) => <Icon {...p}><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32l1.41 1.41M2 12h2m16 0h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></Icon>,
  Moon:         (p={}) => <Icon {...p}><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></Icon>,
  Refresh:      (p={}) => <Icon {...p}><path d="M1 4v6h6M23 20v-6h-6"/><path d="M20.49 9A9 9 0 005.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 013.51 15"/></Icon>,
  Home:         (p={}) => <Icon {...p}><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></Icon>,
  PlusCircle:   (p={}) => <Icon {...p}><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></Icon>,
};

function fileIcon(name) {
  if (name.endsWith(".xlsx")) return ICONS.Excel({ size: 16 });
  if (name.endsWith(".pdf"))  return ICONS.PDF({ size: 16 });
  if (name.endsWith(".pptx")) return ICONS.Powerpoint({ size: 16 });
  if (name.endsWith(".md"))   return ICONS.Markdown({ size: 16 });
  return ICONS.File({ size: 16 });
}

function fileLabel(name) {
  if (name.includes("Excel"))      return "Excel Report";
  if (name.includes("Research"))   return "Research PDF";
  if (name.includes("Pitch"))      return "Pitch Deck";
  if (name.includes("Education"))  return "Education Guide";
  if (name.includes("Analysis"))   return "Analysis Notes";
  return name.replace(/^\d{2}_[A-Z]+_/, "").replace(/\.[^.]+$/, "");
}

function fileSubLabel(name) {
  if (name.includes("Excel"))     return "17 sheets · Goldman format";
  if (name.includes("Research"))  return "10-page equity report";
  if (name.includes("Pitch"))     return "12-slide PowerPoint";
  if (name.includes("Education")) return "Annotated companion guide";
  if (name.includes("Analysis"))  return "Structured markdown notes";
  return "";
}

function ratingClass(r) {
  if (!r) return "";
  const l = r.toLowerCase();
  if (l === "buy")  return "buy";
  if (l === "sell") return "sell";
  return "hold";
}

// ── Sparkline SVG ─────────────────────────────────────────────────────────────
function Sparkline({ prices, width = 64, height = 30 }) {
  if (!prices || prices.length < 2) return <div style={{ width, height }} />;
  const min = Math.min(...prices), max = Math.max(...prices);
  const range = max - min || 1;
  const pad = 2;
  const pts = prices.map((p, i) => [
    (i / (prices.length - 1)) * (width - pad * 2) + pad,
    height - pad - ((p - min) / range) * (height - pad * 2),
  ]);
  let d = `M ${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`;
  for (let i = 1; i < pts.length; i++) {
    const cpx = ((pts[i - 1][0] + pts[i][0]) / 2).toFixed(1);
    d += ` C ${cpx},${pts[i-1][1].toFixed(1)} ${cpx},${pts[i][1].toFixed(1)} ${pts[i][0].toFixed(1)},${pts[i][1].toFixed(1)}`;
  }
  const isUp = prices[prices.length - 1] >= prices[0];
  const strokeColor = isUp ? "var(--success-text)" : "var(--error-text)";
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ overflow: "visible", flexShrink: 0 }}>
      <path d={d} fill="none" stroke={strokeColor} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// ── Ticker Tape ───────────────────────────────────────────────────────────────
function TickerTape() {
  const [data, setData] = useState(null);
  const lastKnown = useRef(null);
  const tapeRef = useRef(null);
  const trackRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const r = await api("/api/market-bar");
      lastKnown.current = r;
      setData(r);
    } catch {
      if (lastKnown.current) setData(prev => ({ ...lastKnown.current }));
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, [load]);

  useLayoutEffect(() => {
    if (!trackRef.current || !tapeRef.current) return;
    const halfW = trackRef.current.scrollWidth / 2;
    if (halfW < 1) return;
    tapeRef.current.style.setProperty("--ticker-dur", `${(halfW / 40).toFixed(1)}s`);
  }, [data]);

  if (!data) return null;

  const stale = !data.timestamp || (Date.now() / 1000 - data.timestamp > 120);

  function fmtChg(chg) {
    const c = chg ?? 0;
    const dir = c > 0.02 ? "up" : c < -0.02 ? "down" : "flat";
    const arrow = c >= 0 ? "▲" : "▼";
    return React.createElement("span", { className: `ticker-chg ${dir}` },
      `${arrow} ${Math.abs(c).toFixed(2)}%`
    );
  }

  const items = [];
  if (data.spx && !data.spx.error) {
    items.push({ label: "S&P 500", price: `$${(data.spx.price || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}`, chg: data.spx.change_pct ?? 0 });
  }
  if (data.vix && !data.vix.error) {
    items.push({ label: "VIX", price: (data.vix.price || 0).toFixed(2), chg: data.vix.change_pct ?? 0 });
  }
  if (data.tsy && !data.tsy.error) {
    items.push({ label: "10yr", price: `${(data.tsy.price || 0).toFixed(2)}%`, chg: data.tsy.change_pct ?? 0 });
  }
  if (data.watchlist) {
    data.watchlist.forEach(w => {
      if (!w.error) items.push({ label: w.ticker, price: `$${(w.price || 0).toFixed(2)}`, chg: w.change_pct ?? 0 });
    });
  }

  if (!items.length) return null;

  function renderSet(prefix) {
    return items.map((it, i) => (
      <React.Fragment key={`${prefix}${it.label}${i}`}>
        <div className="ticker-item">
          <span className="ticker-label">{it.label}</span>
          <span className={`ticker-price${stale ? " stale" : ""}`}>{stale ? "~" : ""}{it.price}</span>
          {fmtChg(it.chg)}
        </div>
        <div className="ticker-sep" aria-hidden="true" />
      </React.Fragment>
    ));
  }

  return (
    <div className="ticker-tape" ref={tapeRef}>
      <div className="ticker-status">
        <div className={`ticker-dot ${data.market_open ? "live" : "closed"}`} />
        {data.market_open ? "Live" : "Closed"}
      </div>
      <div className="ticker-scroll-area">
        <div className="ticker-track" ref={trackRef}>
          {renderSet("a")}
          {renderSet("b")}
        </div>
      </div>
    </div>
  );
}

// ── Skeleton card ─────────────────────────────────────────────────────────────
function SkeletonCard() {
  return (
    <div className="ticker-card skeleton-card">
      <div className="skeleton skeleton-ticker" />
      <div className="skeleton skeleton-name" />
      <div className="ticker-card-body" style={{ marginTop: 8 }}>
        <div className="skeleton skeleton-price" />
        <div style={{ width: 64, height: 30 }} />
      </div>
      <div className="skeleton skeleton-change" />
      <div className="skeleton" style={{ height: 32, borderRadius: 6, marginTop: 4 }} />
    </div>
  );
}

// ── Ticker card ───────────────────────────────────────────────────────────────
function TickerCard({ quote, onAnalyze }) {
  if (quote.error) {
    return (
      <div className="ticker-card ticker-card-error">
        <div className="ticker-symbol">{quote.ticker}</div>
        <div className="ticker-error" style={{ marginTop: 8 }}>—</div>
        <div className="ticker-name" style={{ fontSize: 11 }}>Data unavailable</div>
      </div>
    );
  }
  const pct = quote.change_pct ?? 0;
  const changeClass = pct > 0.05 ? "up" : pct < -0.05 ? "down" : "flat";
  const sign = pct > 0 ? "▲ +" : pct < 0 ? "▼ " : "";
  return (
    <div className="ticker-card">
      <div className="ticker-card-header">
        <div style={{ minWidth: 0 }}>
          <div className="ticker-symbol">{quote.ticker}</div>
          <div className="ticker-name">{quote.name}</div>
        </div>
        {quote.last_analysis?.has_analysis && (
          <div className="analysis-dot" title="Prior analysis on file" />
        )}
      </div>
      <div className="ticker-card-body">
        <div className="ticker-price">
          {quote.price != null
            ? `$${quote.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
            : "—"}
        </div>
        <Sparkline prices={quote.sparkline} />
      </div>
      <div className={`ticker-change ${changeClass}`}>
        {quote.price != null ? `${sign}${Math.abs(pct).toFixed(2)}%` : "—"}
      </div>
      <button className="ticker-analyze-btn" onClick={() => onAnalyze(quote.ticker)}>
        Analyze →
      </button>
    </div>
  );
}

// ── Ticker validation hook ────────────────────────────────────────────────────
function useQuote(ticker) {
  const [quote, setQuote] = useState(null);
  const [loading, setLoading] = useState(false);
  const timer = useRef(null);

  useEffect(() => {
    if (!ticker || ticker.length < 1) { setQuote(null); return; }
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setLoading(true);
      fetch(`/api/quote/${ticker}`, { credentials: "same-origin" })
        .then(r => r.json())
        .then(d => { setQuote(d); setLoading(false); })
        .catch(() => { setQuote({ valid: false, error: "Network error" }); setLoading(false); });
    }, 500);
    return () => clearTimeout(timer.current);
  }, [ticker]);

  return { quote, loading };
}

// ── QuotePreview component ────────────────────────────────────────────────────
function QuotePreview({ ticker, quote, loading }) {
  if (!ticker) return null;
  if (loading)
    return (
      <div className="quote-preview loading">
        <span className="quote-preview-icon" style={{ opacity: 0.5 }}>{ICONS.ChartLine({ size: 14 })}</span>
        Validating {ticker}…
      </div>
    );
  if (!quote) return null;
  if (!quote.valid)
    return (
      <div className="quote-preview invalid">
        <span className="quote-preview-icon">{ICONS.ErrorX({ size: 14 })}</span>
        {quote.error || "Ticker not found"}
      </div>
    );
  const sign = quote.change_pct >= 0 ? "+" : "";
  return (
    <div className="quote-preview valid">
      <span className="quote-preview-icon">{ICONS.CheckMark({ size: 14 })}</span>
      <span className="quote-name">{quote.name}</span>
      <span className="quote-price">{fmtPrice(quote.price)}</span>
      <span className={`quote-change ${quote.change_pct >= 0 ? "up" : "down"}`}>
        {sign}{quote.change_pct?.toFixed(2)}%
      </span>
      <span className="text-dim text-sm">{quote.exchange}</span>
    </div>
  );
}

// ── ProgressPanel component ───────────────────────────────────────────────────
function ProgressPanel({ jobId, onDone }) {
  const [steps, setSteps] = useState([]);
  const [pct, setPct] = useState(0);
  const [displayPct, setDisplayPct] = useState(0);
  const [error, setError] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const esRef = useRef(null);
  const displayPctRef = useRef(0);
  const startRef = useRef(Date.now());
  const animRef = useRef(null);
  const timerRef = useRef(null);
  const stepTimers = useRef({});

  useEffect(() => {
    const from = displayPctRef.current;
    const to = pct;
    if (from === to) return;
    cancelAnimationFrame(animRef.current);
    const start = performance.now();
    const duration = 450;
    function tick(now) {
      const t = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      const val = Math.round(from + (to - from) * eased);
      displayPctRef.current = val;
      setDisplayPct(val);
      if (t < 1) animRef.current = requestAnimationFrame(tick);
      else displayPctRef.current = to;
    }
    animRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animRef.current);
  }, [pct]);

  useEffect(() => {
    if (!jobId) return;
    startRef.current = Date.now();
    timerRef.current = setInterval(() => {
      setElapsed(Math.round((Date.now() - startRef.current) / 1000));
    }, 1000);
    return () => clearInterval(timerRef.current);
  }, [jobId]);

  useEffect(() => {
    if (!jobId) return;
    const es = new EventSource(`/api/progress/${jobId}`);
    esRef.current = es;
    es.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.heartbeat) return;
      if (msg.error) { setError(msg.error); es.close(); return; }
      if (msg.percent !== undefined) {
        setPct(msg.percent);
        const now = Date.now();
        setSteps(prev => {
          const next = [...prev];
          if (next.length > 0) {
            const last = next[next.length - 1];
            if (last.status === "running") {
              const elapsed = ((now - (last.startedAt || now)) / 1000).toFixed(1);
              next[next.length - 1] = { ...last, status: "done", elapsed };
            }
          }
          if (!msg.done) next.push({ message: msg.message, detail: msg.detail || "", status: "running", startedAt: now });
          return next;
        });
      }
      if (msg.done) {
        setPct(100);
        setSteps(prev => prev.map(s => s.status === "running"
          ? { ...s, status: "done", elapsed: ((Date.now() - (s.startedAt || Date.now())) / 1000).toFixed(1) }
          : s
        ));
        clearInterval(timerRef.current);
        es.close();
        setTimeout(() => onDone(msg), 400);
      }
    };
    es.onerror = () => { setError("Connection lost. Check server."); es.close(); };
    return () => es.close();
  }, [jobId]);

  if (error) return <div className="progress-panel"><div className="error-box">{error}</div></div>;

  return (
    <div className="progress-panel">
      <div className="progress-header">
        <span className="progress-title">Running analysis…</span>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
          {elapsed > 0 && <span className="progress-elapsed">{elapsed}s</span>}
          <span className="progress-pct">{displayPct}%</span>
        </div>
      </div>
      <div className="progress-bar-track">
        <div className="progress-bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="progress-steps">
        {steps.map((s, i) => (
          <div key={i} className={`progress-step ${s.status}`}>
            <div className="step-icon">
              {s.status === "done"    ? <div className="step-icon-done">{ICONS.CheckMark({ size: 11 })}</div> :
               s.status === "running" ? <div className="step-icon-active" /> :
               <div className="step-icon-circle" />}
            </div>
            <div className="step-content">
              <div>{s.message}</div>
              {s.detail && <div className="step-detail">{s.detail}</div>}
            </div>
            {s.elapsed && <span className="step-elapsed">{s.elapsed}s</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── ResultsPanel component — v2 Hierarchy ─────────────────────────────────────
function ResultsPanel({ result, onReset, isVercel }) {
  const { ticker, company, stats = {}, files = [], job_id, ntfy_ok } = result;
  const rc = ratingClass(stats.rating);

  // Parse upside from formatted strings
  const targetNum  = stats.target ? parseFloat(stats.target.replace(/[$,]/g, "")) : null;
  const priceNum   = stats.price  ? parseFloat(stats.price.replace(/[$,]/g, ""))  : null;
  const upsidePct  = (targetNum && priceNum && targetNum > priceNum)
    ? `+${((targetNum - priceNum) / priceNum * 100).toFixed(1)}%`
    : (targetNum && priceNum)
    ? `${((targetNum - priceNum) / priceNum * 100).toFixed(1)}%`
    : null;

  // Categorize files
  const primaryFiles = files.filter(f => f.includes("Excel") || f.includes("Research"));
  const secondaryFiles = files.filter(f => !primaryFiles.includes(f) && !f.includes("Education"));
  const hasEduFile = files.some(f => f.includes("Education"));

  const [eduPhase, setEduPhase] = useState("idle");
  const [eduPct,   setEduPct]   = useState(0);
  const [eduFile,  setEduFile]  = useState(null);
  const [eduError, setEduError] = useState(null);

  const handleGenEdu = async () => {
    setEduPhase("running"); setEduPct(0); setEduError(null);
    const ctrl = new AbortController();
    const abort_timer = setTimeout(() => ctrl.abort(), 300000);
    try {
      const resp = await fetch("/api/education", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        signal: ctrl.signal,
        body: JSON.stringify({ ticker, audience: "student", job_id }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        setEduError(err.error || `HTTP ${resp.status}`); setEduPhase("error"); return;
      }
      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split("\n"); buf = lines.pop();
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const msg = JSON.parse(line.slice(6));
            if (msg.heartbeat) continue;
            if (msg.percent !== undefined) setEduPct(msg.percent);
            if (msg.done)  { setEduFile(msg.file); setEduPhase("done"); }
            if (msg.error) { setEduError(msg.error); setEduPhase("error"); }
          } catch {}
        }
      }
    } catch (err) {
      setEduError(err?.name === "AbortError" ? "Timed out — try again." : "Connection lost — try again.");
      setEduPhase("error");
    } finally { clearTimeout(abort_timer); }
  };

  return (
    <div className="results-panel">
      {/* Hero Stats Card */}
      <div className="results-hero">
        <div className="hero-rating-col">
          {rc ? (
            <span className={`hero-rating-badge ${rc}`}>{stats.rating}</span>
          ) : (
            <div className="hero-success-icon">{ICONS.Check({ size: 20 })}</div>
          )}
        </div>
        <div className="hero-company-col">
          <div className="hero-company-name">{company || ticker}</div>
          <div className="hero-company-ticker">{ticker}</div>
          {stats.target && stats.target !== "—" && (
            <div className="hero-meta">
              Target {stats.target}
              {upsidePct && <span className={`hero-upside`} style={{ marginLeft: 6 }}>· {upsidePct} upside</span>}
            </div>
          )}
          {stats.dcf && <div className="hero-meta" style={{ marginTop: 2 }}>{stats.dcf}</div>}
        </div>
        <div className="hero-price-col">
          <div className="hero-price">{stats.price || "—"}</div>
          <div className="hero-meta">Current Price</div>
        </div>
        <button className="btn btn-ghost btn-sm" style={{ marginLeft: "auto", alignSelf: "flex-start" }} onClick={onReset}>
          New Analysis
        </button>
      </div>

      {/* Primary Downloads */}
      {primaryFiles.length > 0 && (
        <>
          <div className="files-section-label">Primary Outputs</div>
          <div className="files-grid-primary">
            {primaryFiles.map(f => (
              <a key={f} href={`/api/download/job/${job_id}/${ticker}/${f}`} className="file-btn file-btn-primary" download>
                <span className="file-icon">{fileIcon(f)}</span>
                <div className="file-info">
                  <div className="file-name">{fileLabel(f)}</div>
                  <div className="file-sub">{fileSubLabel(f)}</div>
                </div>
                <span className="file-dl">{ICONS.Download({ size: 14 })}</span>
              </a>
            ))}
          </div>
        </>
      )}

      {/* Secondary Downloads */}
      {secondaryFiles.length > 0 && (
        <>
          <div className="files-section-label">Additional Outputs</div>
          <div className="files-grid-secondary">
            {secondaryFiles.map(f => (
              <a key={f} href={`/api/download/job/${job_id}/${ticker}/${f}`} className="file-btn" download>
                <span className="file-icon">{fileIcon(f)}</span>
                <span className="file-name">{fileLabel(f)}</span>
                <span className="file-dl">{ICONS.Download({ size: 13 })}</span>
              </a>
            ))}
          </div>
        </>
      )}

      {/* Education Guide (Vercel only, on-demand) */}
      {isVercel && (
        <div style={{ marginTop: 20 }}>
          <div className="files-section-label">Education Guide</div>
          {eduPhase === "idle" && !hasEduFile && (
            <button onClick={handleGenEdu} className="btn btn-secondary" style={{ width: "100%" }}>
              {ICONS.Education({ size: 16 })} Generate Education Guide →
            </button>
          )}
          {hasEduFile && !eduFile && (
            <a href={`/api/download/job/${job_id}/${ticker}/${files.find(f => f.includes("Education"))}`}
               className="file-btn" download>
              <span className="file-icon">{ICONS.Education({ size: 16 })}</span>
              <span className="file-name">Education Guide</span>
              <span className="file-dl">{ICONS.Download({ size: 13 })}</span>
            </a>
          )}
          {eduPhase === "running" && (
            <div>
              <div className="text-sm text-muted" style={{ marginBottom: 6 }}>Generating… {eduPct}%</div>
              <div style={{ height: 4, background: "var(--border)", borderRadius: 2, overflow: "hidden" }}>
                <div style={{ height: 4, width: `${eduPct}%`, background: "var(--accent-primary)", borderRadius: 2, transition: "width 0.4s ease" }} />
              </div>
            </div>
          )}
          {eduPhase === "done" && eduFile && (
            <a href={`/api/download/job/${job_id}/${ticker}/${eduFile}`} className="file-btn file-btn-primary" download>
              <span className="file-icon">{ICONS.Education({ size: 16 })}</span>
              <div className="file-info">
                <div className="file-name">Education Guide</div>
                <div className="file-sub">Annotated companion guide</div>
              </div>
              <span className="file-dl">{ICONS.Download({ size: 14 })}</span>
            </a>
          )}
          {eduPhase === "error" && (
            <div className="error-box" style={{ fontSize: "var(--text-body-sm)" }}>
              {eduError || "Education guide generation failed."}
            </div>
          )}
        </div>
      )}

      {/* Notification status */}
      <div className="phone-sent">
        {ICONS.Phone({ size: 13 })}
        {ntfy_ok ? "Push notification sent" : "Push notification unavailable"}
      </div>
    </div>
  );
}

// ── Recent Analyses Section ───────────────────────────────────────────────────
function RecentAnalyses({ onAnalyzeTicker, onNavigate }) {
  const [history, setHistory] = useState(null);

  useEffect(() => {
    api("/api/history").then(d => {
      if (!d.vercel_mode && d.items?.length > 0) {
        setHistory(d.items.slice(0, 3));
      } else {
        setHistory([]);
      }
    }).catch(() => setHistory([]));
  }, []);

  if (history === null) return null;
  if (history.length === 0) return null;

  return (
    <div className="recent-section">
      <div className="section-header">
        <span className="section-title">Recent Analyses</span>
        <span className="section-link" onClick={() => onNavigate("history")}>View all →</span>
      </div>
      <div className="recent-list">
        {history.map(h => (
          <div key={h.ticker} className="recent-row">
            <div className="recent-ticker">{h.ticker}</div>
            <div className="recent-company">{h.company || ""}</div>
            {h.rating && <span className={`rating-tag ${ratingClass(h.rating)}`}>{h.rating}</span>}
            {h.target && <div className="recent-target">{h.target}</div>}
            <div className="recent-date">{fmtDate(h.timestamp)}</div>
            <button className="recent-analyze-btn" onClick={() => onAnalyzeTicker(h.ticker)}>
              Analyze →
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── DashboardPage ─────────────────────────────────────────────────────────────
function DashboardPage({ onAnalyzeTicker, onNavigate, isAdmin }) {
  const [quotes, setQuotes] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  const fetchQuotes = useCallback(async () => {
    try {
      const data = await api("/api/watchlist/quotes");
      if (data.quotes) { setQuotes(data.quotes); setLastUpdated(new Date()); }
    } catch { setQuotes([]); }
  }, []);

  useEffect(() => {
    fetchQuotes();
    if (isMarketOpen()) {
      const interval = setInterval(fetchQuotes, 60000);
      return () => clearInterval(interval);
    }
  }, [fetchQuotes]);

  const updatedStr = lastUpdated
    ? lastUpdated.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })
    : null;
  const count = quotes?.length ?? 0;

  return (
    <div className="page">
      {!isAdmin && (
        <VisitorBanner storageKey="visitor_watchlist_notice_dismissed" heading="You're viewing Sam's Watchlist">
          This watchlist is Sam's personal configuration. Run any analysis from the home page using any ticker you like — results are yours and not saved to this watchlist.
        </VisitorBanner>
      )}
      <div className="dash-header">
        <div>
          <div className="dash-title">Watchlist</div>
          <div className="dash-meta">
            {quotes ? `${count} ticker${count !== 1 ? "s" : ""}` : "Loading…"}
            {" · "}
            {isMarketOpen()
              ? <span className="market-open">Markets Open</span>
              : <span className="market-closed">Markets Closed</span>}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-4)" }}>
          {updatedStr && <div className="dash-time">Updated {updatedStr}</div>}
          <button className="btn btn-ghost btn-sm" onClick={fetchQuotes}>
            {ICONS.Refresh({ size: 14 })} Refresh
          </button>
        </div>
      </div>

      <div className="ticker-grid">
        {quotes === null
          ? Array(6).fill(0).map((_, i) => <SkeletonCard key={i} />)
          : quotes.length === 0
          ? (
            <div className="empty-state" style={{ gridColumn: "1/-1" }}>
              <div className="empty-icon">{ICONS.ChartLine({ size: 48 })}</div>
              <h3>Watchlist is empty</h3>
              <p>Add tickers on the Notifications page to see live prices and sparklines here.</p>
              {isAdmin && (
                <div className="empty-action">
                  <button className="btn btn-primary" onClick={() => onNavigate("notifications")}>
                    {ICONS.PlusCircle({ size: 16 })} Add Tickers →
                  </button>
                </div>
              )}
            </div>
          )
          : quotes.map(q => (
            <TickerCard key={q.ticker} quote={q} onAnalyze={onAnalyzeTicker} />
          ))}
      </div>

      <RecentAnalyses onAnalyzeTicker={onAnalyzeTicker} onNavigate={onNavigate} />
    </div>
  );
}

// ── AnalyzePage ───────────────────────────────────────────────────────────────
function AnalyzePage({ prefilledTicker, isVercel, onNavigate }) {
  const [ticker,   setTicker]   = useState("");
  const [audience, setAudience] = useState("student");
  const [flags,    setFlags]    = useState(["--full"]);
  const [phase,    setPhase]    = useState("input");
  const [jobId,    setJobId]    = useState(null);
  const [result,   setResult]   = useState(null);
  const [loading,  setLoading]  = useState(false);
  const { quote, loading: qLoading } = useQuote(ticker);

  useEffect(() => {
    if (prefilledTicker) { setTicker(prefilledTicker); setPhase("input"); }
  }, [prefilledTicker]);

  const toggleFlag = (f) => setFlags(prev =>
    prev.includes(f) ? prev.filter(x => x !== f) : [...prev, f]
  );

  const runAnalysis = async () => {
    if (!quote?.valid) return;
    setLoading(true);
    try {
      const data = await api("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker, flags, audience }),
      });
      if (data.error) { window.toast && window.toast.error(data.error); setLoading(false); return; }
      setJobId(data.job_id);
      setPhase("progress");
    } catch { window.toast && window.toast.error("Failed to start analysis"); }
    setLoading(false);
  };

  const handleDone = (msg) => {
    setResult(msg);
    setPhase("results");
    window.toast && window.toast.success("Analysis complete — files ready to download");
  };
  const handleReset = () => { setPhase("input"); setTicker(""); setResult(null); setJobId(null); };

  const isFull = flags.includes("--full");

  const outcomeOptions = [
    { flag: "--full",      icon: ICONS.Excel,      label: "17-Sheet Excel",   sub: "Goldman-style workbook" },
    { flag: "--pdf",       icon: ICONS.PDF,        label: "10-Page PDF",      sub: "Equity research report" },
    { flag: "--pitch",     icon: ICONS.Powerpoint, label: "12-Slide Deck",    sub: "Pitch-ready PowerPoint" },
    { flag: "--education", icon: ICONS.Education,  label: "Education Guide",  sub: isVercel ? "Available locally only" : "Annotated companion PDF", disabled: isVercel },
  ];

  return (
    <div className="page">
      <div className="analyze-hero">
        <h1>Stock Analysis</h1>
        <p>Any public company. Full institutional research package in under 60 seconds — DCF, comps, SEC filings, insider tracking, and Claude AI synthesis.</p>
      </div>

      <div className="card">
        {phase === "input" && (
          <div className="card-body">
            <div style={{ marginBottom: "var(--space-6)" }}>
              <label className="field-label">Ticker Symbol</label>
              <div className="input-row">
                <input
                  className={`input input-hero ticker-input ${quote?.valid ? "valid" : ticker.length > 0 && !qLoading && quote ? "invalid" : ""}`}
                  value={ticker}
                  onChange={e => setTicker(e.target.value.toUpperCase())}
                  placeholder="AAPL, NVDA, LLY…"
                  maxLength={6}
                  onKeyDown={e => { if (e.key === "Enter" && quote?.valid) runAnalysis(); }}
                  autoFocus
                />
              </div>
              <QuotePreview ticker={ticker} quote={quote} loading={qLoading} />
            </div>

            <hr className="divider" />

            <div style={{ marginBottom: "var(--space-6)" }}>
              <label className="field-label">What you'll get</label>
              <div className="outcome-grid">
                {outcomeOptions.map(o => {
                  const sel = !o.disabled && (flags.includes(o.flag) || (isFull && o.flag !== "--full"));
                  return (
                    <div key={o.flag}
                      className={`outcome-card ${sel ? "selected" : ""} ${o.disabled ? "disabled" : ""}`}
                      onClick={() => !o.disabled && toggleFlag(o.flag)}
                      style={o.disabled ? { opacity: 0.45, cursor: "not-allowed" } : {}}>
                      <span className="outcome-card-icon">{o.icon({ size: 22 })}</span>
                      <div className="outcome-card-text">
                        <div className="outcome-card-label">{o.label}</div>
                        <div className="outcome-card-sub">{o.sub}</div>
                      </div>
                      <div className="outcome-check">{sel ? ICONS.CheckMark({ size: 14 }) : null}</div>
                    </div>
                  );
                })}
              </div>
            </div>

            {!isVercel && (
              <div>
                <label className="field-label">Education Audience</label>
                <div className="audience-toggle">
                  {["student", "professional"].map(a => (
                    <button key={a} className={`audience-btn ${audience === a ? "active" : ""}`}
                      onClick={() => setAudience(a)}>
                      {a.charAt(0).toUpperCase() + a.slice(1)}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div style={{ marginTop: "var(--space-6)" }}>
              <button className="btn btn-primary btn-run"
                disabled={!quote?.valid || loading} onClick={runAnalysis}>
                {loading ? "Starting…" : "Run Full Analysis →"}
              </button>
              <div className="run-estimate">~45–60 seconds · Claude Sonnet 4.6</div>
            </div>
          </div>
        )}

        {phase === "progress" && <ProgressPanel jobId={jobId} onDone={handleDone} />}
        {phase === "results" && result && (
          <>
            <ResultsPanel result={result} onReset={handleReset} isVercel={isVercel} />
            <div style={{ textAlign: "center", padding: "var(--space-2) var(--space-6) var(--space-6)" }}>
              <button
                onClick={() => onNavigate && onNavigate("history")}
                style={{ background: "none", border: "none", cursor: "pointer", fontSize: "var(--text-body-sm)", color: "var(--accent-primary)", fontFamily: "var(--font-sans)", textDecoration: "underline", textUnderlineOffset: "3px" }}
              >
                View in History →
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── LBOPage ───────────────────────────────────────────────────────────────────
function LBOPage() {
  const [ticker,    setTicker]    = useState("");
  const [entryMult, setEntryMult] = useState(null);
  const [holdYears, setHoldYears] = useState(5);
  const [debtPct,   setDebtPct]   = useState(60);
  const [phase,     setPhase]     = useState("input");
  const [jobId,     setJobId]     = useState(null);
  const [result,    setResult]    = useState(null);
  const [loading,   setLoading]   = useState(false);
  const { quote, loading: qLoading } = useQuote(ticker);

  const estMOIC = () => {
    if (!quote?.pe_fwd) return null;
    const entry = entryMult || (quote.pe_fwd ? quote.pe_fwd * 0.6 : 10);
    const exitMult = entry * 0.9;
    const equityFrac = 1 - debtPct / 100;
    return (exitMult / (entry * equityFrac)).toFixed(1);
  };
  const estIRR = () => {
    const m = parseFloat(estMOIC());
    if (!m) return null;
    return ((Math.pow(m, 1 / holdYears) - 1) * 100).toFixed(1);
  };
  const moic = estMOIC();
  const irr  = estIRR();
  const irrClass = irr ? (irr >= 20 ? "good" : irr >= 15 ? "warn" : "bad") : "";

  const runLBO = async () => {
    if (!quote?.valid) return;
    setLoading(true);
    try {
      const data = await api("/api/lbo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker, entry_multiple: entryMult || null, hold_years: holdYears, debt_pct: debtPct / 100 }),
      });
      if (data.error) { window.toast && window.toast.error(data.error); setLoading(false); return; }
      setJobId(data.job_id); setPhase("progress");
    } catch { window.toast && window.toast.error("Failed to start LBO"); }
    setLoading(false);
  };

  const handleDone = (msg) => { setResult(msg); setPhase("results"); };
  const handleReset = () => { setPhase("input"); setResult(null); setJobId(null); };

  return (
    <div className="page">
      <div className="page-header">
        <h1>LBO Calculator</h1>
        <p>9-tab Goldman-style model: debt schedule · 3 statements · IRR/MOIC · sensitivity</p>
      </div>

      {phase === "input" && (
        <div style={{ display: "grid", gap: "var(--space-3)" }}>
          <div className="card">
            <div className="card-body">
              <label className="field-label">Target Company</label>
              <div className="input-row">
                <input
                  className={`input ${quote?.valid ? "valid" : ticker.length > 0 && !qLoading && quote ? "invalid" : ""}`}
                  value={ticker}
                  onChange={e => setTicker(e.target.value.toUpperCase())}
                  placeholder="AAPL"
                  maxLength={6}
                />
                <button className="btn btn-primary" disabled={!quote?.valid || loading} onClick={runLBO}>
                  {loading ? "Starting…" : "Build Model →"}
                </button>
              </div>
              <QuotePreview ticker={ticker} quote={quote} loading={qLoading} />
            </div>
          </div>

          <div className="card">
            <div className="card-body">
              <div className="slider-field">
                <div className="slider-row">
                  <label className="field-label" style={{ margin: 0 }}>Entry EV/EBITDA</label>
                  <span className="slider-val">{entryMult ? `${entryMult}x` : "Auto"}</span>
                </div>
                <input type="range" min="5" max="20" step="0.5"
                  value={entryMult ?? 12.5}
                  onChange={e => setEntryMult(parseFloat(e.target.value))} />
                <div className="slider-bounds"><span>5x</span><span>Auto (market)</span><span>20x</span></div>
                <button className="btn btn-ghost btn-sm mt-2" onClick={() => setEntryMult(null)}>Reset to auto</button>
              </div>

              <div className="slider-field">
                <div className="slider-row">
                  <label className="field-label" style={{ margin: 0 }}>Hold Period</label>
                  <div className="toggle-group">
                    {[3, 4, 5].map(y => (
                      <button key={y} className={`toggle-btn ${holdYears === y ? "active" : ""}`}
                        onClick={() => setHoldYears(y)}>{y}yr</button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="slider-field">
                <div className="slider-row">
                  <label className="field-label" style={{ margin: 0 }}>Debt / TEV</label>
                  <span className="slider-val">{debtPct}%</span>
                </div>
                <input type="range" min="40" max="75" step="5"
                  value={debtPct}
                  onChange={e => setDebtPct(parseInt(e.target.value))} />
                <div className="slider-bounds"><span>40%</span><span>60%</span><span>75%</span></div>
              </div>

              {quote?.valid && (
                <div className="preview-box">
                  <h3>Preliminary Estimate (simplified)</h3>
                  <div className="preview-row"><span className="label">Entry Multiple</span><span className="val">{entryMult ? `${entryMult}x` : "Market + 10%"} EV/EBITDA</span></div>
                  <div className="preview-row"><span className="label">Hold Period</span><span className="val">{holdYears} years</span></div>
                  <div className="preview-row"><span className="label">Debt / TEV</span><span className="val">{debtPct}% / {100 - debtPct}% equity</span></div>
                  {moic && <div className="preview-row"><span className="label">Est. MOIC</span><span className={`val ${irrClass}`}>{moic}x</span></div>}
                  {irr  && <div className="preview-row"><span className="label">Est. IRR</span><span className={`val ${irrClass}`}>{irr}%</span></div>}
                  <div className="text-dim text-sm mt-2">Run full model for precise debt schedule, 3-statement model, and 5×5 sensitivity</div>
                </div>
              )}

              {!quote?.valid && (
                <div className="preview-box">
                  <h3>Example Returns</h3>
                  <div className="preview-row"><span className="label">8x entry → 5yr hold → 60% debt</span><span className="val good">~19% IRR, 2.3x MOIC</span></div>
                  <div className="preview-row"><span className="label">12x entry → 5yr hold → 60% debt</span><span className="val warn">~13% IRR, 1.8x MOIC</span></div>
                  <div className="preview-row"><span className="label">15x entry → 5yr hold → 60% debt</span><span className="val bad">~9% IRR, 1.5x MOIC</span></div>
                  <div className="text-dim text-sm mt-2">Enter a ticker to see a preliminary estimate based on live market data</div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {phase === "input" && <div style={{ marginTop: "var(--space-3)" }}>
        <button className="btn btn-primary btn-run" disabled={!quote?.valid || loading} onClick={runLBO}>
          {loading ? "Starting…" : "Build LBO Model →"}
        </button>
      </div>}

      {phase === "progress" && (
        <div className="card"><ProgressPanel jobId={jobId} onDone={handleDone} /></div>
      )}

      {phase === "results" && result && (
        <div className="card">
          <div className="results-panel">
            <div className="results-hero">
              <div className="hero-success-icon">{ICONS.Check({ size: 20 })}</div>
              <div className="hero-company-col">
                <div className="hero-company-name">LBO Model — {result.ticker}</div>
                <div className="hero-company-ticker">9-tab Excel workbook · IRR/MOIC · Sensitivity tables</div>
              </div>
              <button className="btn btn-ghost btn-sm" style={{ marginLeft: "auto" }} onClick={handleReset}>New Model</button>
            </div>
            <div className="files-section-label">Output</div>
            <div className="files-grid-primary">
              <a href={`/api/download/lbo/${result.file}`} className="file-btn file-btn-primary" download>
                <span className="file-icon">{ICONS.Excel({ size: 18 })}</span>
                <div className="file-info">
                  <div className="file-name">LBO Model</div>
                  <div className="file-sub">{result.file}</div>
                </div>
                <span className="file-dl">{ICONS.Download({ size: 14 })}</span>
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── MAPage ────────────────────────────────────────────────────────────────────
function MAPage() {
  const [acq,       setAcq]       = useState("");
  const [tgt,       setTgt]       = useState("");
  const [premium,   setPremium]   = useState(30);
  const [cashPct,   setCashPct]   = useState(50);
  const [synergies, setSynergies] = useState("");
  const [phase,     setPhase]     = useState("input");
  const [jobId,     setJobId]     = useState(null);
  const [result,    setResult]    = useState(null);
  const [loading,   setLoading]   = useState(false);
  const { quote: acqQuote, loading: acqLoading } = useQuote(acq);
  const { quote: tgtQuote, loading: tgtLoading } = useQuote(tgt);

  const tgtOfferPrice = tgtQuote?.valid
    ? (tgtQuote.price * (1 + premium / 100)).toFixed(2) : null;
  const totalDealVal = tgtQuote?.valid && tgtQuote.market_cap
    ? ((tgtQuote.market_cap * (1 + premium / 100)) / 1e9).toFixed(1) : null;

  const runMA = async () => {
    if (!acqQuote?.valid || !tgtQuote?.valid) return;
    setLoading(true);
    try {
      const data = await api("/api/ma", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ acquirer: acq, target: tgt, premium_pct: premium, cash_pct: cashPct,
          synergies_m: synergies ? parseFloat(synergies) : null }),
      });
      if (data.error) { window.toast && window.toast.error(data.error); setLoading(false); return; }
      setJobId(data.job_id); setPhase("progress");
    } catch { window.toast && window.toast.error("Failed to start M&A model"); }
    setLoading(false);
  };

  const handleDone = (msg) => { setResult(msg); setPhase("results"); };
  const handleReset = () => { setPhase("input"); setResult(null); setJobId(null); };
  const canRun = acqQuote?.valid && tgtQuote?.valid && !loading;

  return (
    <div className="page">
      <div className="page-header">
        <h1>M&amp;A Deal Builder</h1>
        <p>8-tab accretion/dilution model · synergies · pro forma EPS · 5×5 sensitivity</p>
      </div>

      <div className="card">
        {phase === "input" && (
          <div className="card-body">
            <div className="two-col" style={{ marginBottom: "var(--space-5)" }}>
              <div>
                <label className="field-label">Acquirer</label>
                <input className={`input ${acqQuote?.valid ? "valid" : acq.length > 0 && !acqLoading && acqQuote ? "invalid" : ""}`}
                  value={acq} onChange={e => setAcq(e.target.value.toUpperCase())} placeholder="MSFT" maxLength={6} />
                <QuotePreview ticker={acq} quote={acqQuote} loading={acqLoading} />
              </div>
              <div>
                <label className="field-label">Target</label>
                <input className={`input ${tgtQuote?.valid ? "valid" : tgt.length > 0 && !tgtLoading && tgtQuote ? "invalid" : ""}`}
                  value={tgt} onChange={e => setTgt(e.target.value.toUpperCase())} placeholder="AAPL" maxLength={6} />
                <QuotePreview ticker={tgt} quote={tgtQuote} loading={tgtLoading} />
              </div>
            </div>

            <hr className="divider" />

            <div className="slider-field">
              <div className="slider-row">
                <label className="field-label" style={{ margin: 0 }}>Offer Premium</label>
                <span className="slider-val">{premium}%</span>
              </div>
              <input type="range" min="10" max="60" step="5"
                value={premium} onChange={e => setPremium(parseInt(e.target.value))} />
              <div className="slider-bounds"><span>10%</span><span>30%</span><span>60%</span></div>
            </div>

            <div className="slider-field">
              <div className="slider-row">
                <label className="field-label" style={{ margin: 0 }}>Cash Consideration</label>
                <span className="slider-val">{cashPct}% cash / {100 - cashPct}% stock</span>
              </div>
              <input type="range" min="0" max="100" step="10"
                value={cashPct} onChange={e => setCashPct(parseInt(e.target.value))} />
              <div className="slider-bounds"><span>All stock</span><span>50/50</span><span>All cash</span></div>
            </div>

            <div style={{ marginBottom: "var(--space-5)" }}>
              <label className="field-label">Synergy Override (optional)</label>
              <input className="input" style={{ textTransform: "none" }}
                type="number" value={synergies} onChange={e => setSynergies(e.target.value)}
                placeholder="Leave blank for bottom-up estimate ($M)" />
            </div>

            {(acqQuote?.valid || tgtQuote?.valid) && (
              <div className="preview-box">
                <h3>Deal Preview</h3>
                {tgtQuote?.valid && <>
                  <div className="preview-row">
                    <span className="label">Target price</span>
                    <span className="val">{fmtPrice(tgtQuote.price)}</span>
                  </div>
                  {tgtOfferPrice && <div className="preview-row">
                    <span className="label">Offer price ({premium}% premium)</span>
                    <span className="val">${tgtOfferPrice}/share</span>
                  </div>}
                  {totalDealVal && <div className="preview-row">
                    <span className="label">Total equity value</span>
                    <span className="val">${totalDealVal}B</span>
                  </div>}
                </>}
                {acqQuote?.valid && <div className="preview-row">
                  <span className="label">Acquirer market cap</span>
                  <span className="val">${acqQuote.market_cap ? (acqQuote.market_cap / 1e9).toFixed(1) + "B" : "—"}</span>
                </div>}
                <div className="preview-row">
                  <span className="label">Mix</span>
                  <span className="val">{cashPct}% cash / {100 - cashPct}% stock</span>
                </div>
              </div>
            )}

            {!acqQuote?.valid && !tgtQuote?.valid && (
              <div className="preview-box">
                <h3>Example Deal</h3>
                <div className="preview-row"><span className="label">Try: MSFT acquires GOOGL at 25% premium</span><span className="val">60% cash</span></div>
                <div className="preview-row"><span className="label">$3,000M synergies</span><span className="val bad">Likely dilutive near-term</span></div>
                <div className="text-dim text-sm mt-2">Enter two tickers to model the deal in detail</div>
              </div>
            )}

            <div className="mt-4">
              <button className="btn btn-primary" disabled={!canRun} onClick={runMA}>
                {loading ? "Starting…" : "Build M&A Model →"}
              </button>
            </div>
          </div>
        )}

        {phase === "progress" && <ProgressPanel jobId={jobId} onDone={handleDone} />}

        {phase === "results" && result && (
          <div className="results-panel">
            <div className="results-hero">
              <div className="hero-success-icon">{ICONS.Check({ size: 20 })}</div>
              <div className="hero-company-col">
                <div className="hero-company-name">{result.acquirer} acquires {result.target}</div>
                <div className="hero-company-ticker">8-tab merger consequences model · EPS accretion/dilution</div>
              </div>
              <button className="btn btn-ghost btn-sm" style={{ marginLeft: "auto" }} onClick={handleReset}>New Deal</button>
            </div>
            <div className="files-section-label">Output</div>
            <div className="files-grid-primary">
              <a href={`/api/download/ma/${result.file}`} className="file-btn file-btn-primary" download>
                <span className="file-icon">{ICONS.Excel({ size: 18 })}</span>
                <div className="file-info">
                  <div className="file-name">M&A Model</div>
                  <div className="file-sub">{result.file}</div>
                </div>
                <span className="file-dl">{ICONS.Download({ size: 14 })}</span>
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── NotificationsPage ─────────────────────────────────────────────────────────
function NotificationsPage({ isAdmin }) {
  const [watchlist, setWatchlist] = useState({ tickers: [], thresholds: {}, alert_types: {} });
  const [newTicker, setNewTicker] = useState("");
  const [saving,    setSaving]    = useState(false);
  const [testing,   setTesting]   = useState(false);
  const [saved,     setSaved]     = useState(false);
  const [ntfyResult, setNtfyResult] = useState(null);
  const [alerts,    setAlerts]    = useState(null);
  const { quote, loading: qLoading } = useQuote(newTicker);

  const defaultThresholds = { price_move: 3, insider_buy: 1, earnings_surp: 5, target_change: 10 };
  const defaultAlertTypes = {
    price_moves: true, analyst_changes: true, insider_buying: true,
    earnings_surprises: true, sec_filings: false, morning_briefing: true,
  };

  useEffect(() => {
    api("/api/watchlist").then(d => setWatchlist({
      tickers:     d.tickers     || [],
      thresholds:  { ...defaultThresholds,  ...d.thresholds  },
      alert_types: { ...defaultAlertTypes, ...d.alert_types },
    }));
    api("/api/alerts/recent").then(d => setAlerts(d.alerts || []));
  }, []);

  const addTicker = () => {
    if (!quote?.valid) return;
    if (watchlist.tickers.includes(newTicker)) { setNewTicker(""); return; }
    setWatchlist(w => ({ ...w, tickers: [...w.tickers, newTicker] }));
    setNewTicker("");
  };
  const removeTicker = (t) => setWatchlist(w => ({ ...w, tickers: w.tickers.filter(x => x !== t) }));
  const setThreshold = (k, v) => setWatchlist(w => ({ ...w, thresholds: { ...w.thresholds, [k]: v } }));
  const toggleAlert  = (k)    => setWatchlist(w => ({ ...w, alert_types: { ...w.alert_types, [k]: !w.alert_types[k] } }));

  const save = async () => {
    setSaving(true);
    await api("/api/watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(watchlist),
    });
    setSaving(false); setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const testNotify = async () => {
    setTesting(true); setNtfyResult(null);
    try {
      const r = await api("/api/notify/test", { method: "POST" });
      setNtfyResult(r);
    } catch (e) { setNtfyResult({ ok: false, error: String(e) }); }
    setTesting(false);
  };

  const th = watchlist.thresholds;
  const at = watchlist.alert_types;

  const alertRows = [
    { key: "price_moves",        label: "Price Moves",        sub: `>${th.price_move || 3}% daily move` },
    { key: "analyst_changes",    label: "Analyst Changes",    sub: "Upgrades, downgrades, target changes" },
    { key: "insider_buying",     label: "Insider Buying",     sub: `Open market buys >$${th.insider_buy || 1}M` },
    { key: "earnings_surprises", label: "Earnings Surprises", sub: `EPS beat/miss >${th.earnings_surp || 5}%` },
    { key: "sec_filings",        label: "SEC Filings",        sub: "New 10-K and 10-Q filings" },
    { key: "morning_briefing",   label: "Morning Briefing",   sub: "Daily 7am market summary" },
  ];

  function alertIcon(type) {
    if (!type)                      return ICONS.Bell({ size: 15 });
    if (type.includes("price"))     return ICONS.TrendingUp({ size: 15 });
    if (type.includes("analysis"))  return ICONS.BarChart({ size: 15 });
    if (type.includes("brief"))     return ICONS.Bell({ size: 15 });
    if (type.includes("upgrade"))   return ICONS.ArrowUp({ size: 15 });
    if (type.includes("downgrade")) return ICONS.ArrowDown({ size: 15 });
    return ICONS.Bell({ size: 15 });
  }

  return (
    <div className="page">
      {!isAdmin && (
        <VisitorBanner storageKey="visitor_notifications_notice_dismissed" heading="Personal Notification Setup">
          These are Sam's personal alert settings delivered via ntfy.sh — a free, open-source push notification app. To set up your own alerts for any stock, download ntfy.sh, create a free topic, and build your own instance of this platform from the{" "}
          <a href="https://github.com/maddinsd/portfolio-analyzer" target="_blank" rel="noopener noreferrer">GitHub repo</a>{" "}
          linked in the About section.
        </VisitorBanner>
      )}
      <div className="page-header">
        <h1>Notifications</h1>
        <p>Manage watchlist, alert thresholds, and ntfy.sh push notifications</p>
      </div>

      <div className="gap-1">
        <div className="card">
          <div className="card-header">
            <span className="card-title">Watchlist</span>
            <span className="text-dim text-sm">{watchlist.tickers.length} ticker{watchlist.tickers.length !== 1 ? "s" : ""}</span>
          </div>
          <div className="card-body">
            {watchlist.tickers.length === 0 ? (
              <div style={{ padding: "var(--space-4) 0", color: "var(--text-tertiary)", fontSize: "var(--text-body)" }}>
                No tickers added yet. Add one below to start receiving alerts.
              </div>
            ) : (
              <div className="chip-list">
                {watchlist.tickers.map(t => (
                  <div key={t} className="ticker-chip">
                    {t}
                    {isAdmin && <button className="chip-remove" onClick={() => removeTicker(t)}>×</button>}
                  </div>
                ))}
              </div>
            )}
            {isAdmin && (
              <>
                <div className="input-row mt-3">
                  <input
                    className={`input ${quote?.valid ? "valid" : newTicker.length > 0 && !qLoading && quote ? "invalid" : ""}`}
                    value={newTicker}
                    onChange={e => setNewTicker(e.target.value.toUpperCase())}
                    placeholder="Add ticker…"
                    maxLength={6}
                    onKeyDown={e => { if (e.key === "Enter" && quote?.valid) addTicker(); }}
                  />
                  <button className="btn btn-secondary" disabled={!quote?.valid} onClick={addTicker}>Add</button>
                </div>
                {newTicker && <QuotePreview ticker={newTicker} quote={quote} loading={qLoading} />}
              </>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-header"><span className="card-title">Alert Thresholds</span></div>
          <div className="card-body">
            {[
              { key: "price_move",    label: "Price Move Alert",       unit: "%",  min: 1,   max: 10, step: 1 },
              { key: "insider_buy",   label: "Insider Buy Minimum",     unit: "$M", min: 0.1, max: 5,  step: 0.1 },
              { key: "earnings_surp", label: "Earnings Surprise Alert", unit: "%",  min: 2,   max: 15, step: 1 },
              { key: "target_change", label: "Analyst Target Change",   unit: "%",  min: 5,   max: 25, step: 5 },
            ].map(({ key, label, unit, min, max, step }) => (
              <div key={key} className="slider-field">
                <div className="slider-row">
                  <label className="field-label" style={{ margin: 0 }}>&gt;{th[key] || min}{unit} {label}</label>
                  <span className="slider-val">{th[key] || min}{unit}</span>
                </div>
                <input type="range" min={min} max={max} step={step}
                  value={th[key] || min}
                  disabled={!isAdmin}
                  onChange={e => isAdmin && setThreshold(key, parseFloat(e.target.value))} />
                <div className="slider-bounds"><span>{min}{unit}</span><span>{max}{unit}</span></div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-header"><span className="card-title">Alert Types</span></div>
          <div className="card-body" style={{ padding: "var(--space-2) var(--space-6)" }}>
            {alertRows.map(row => (
              <div key={row.key} className="switch-row">
                <div>
                  <div className="switch-label">{row.label}</div>
                  <div className="switch-sub">{row.sub}</div>
                </div>
                <label className="switch">
                  <input type="checkbox" checked={!!at[row.key]} disabled={!isAdmin} onChange={() => isAdmin && toggleAlert(row.key)} />
                  <div className="switch-track" />
                </label>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <span className="card-title">Recent Alerts</span>
            <span className="text-dim text-sm">Last 7 days</span>
          </div>
          <div className="card-body" style={{ padding: "0 var(--space-6)" }}>
            {alerts === null && <div className="text-dim text-sm" style={{ padding: "var(--space-4) 0" }}>Loading…</div>}
            {alerts !== null && alerts.length === 0 && (
              <div style={{ padding: "var(--space-5) 0", textAlign: "center" }}>
                <div style={{ color: "var(--text-tertiary)", fontSize: "var(--text-body)" }}>
                  Monitoring active. Alerts will appear here when triggered.
                </div>
              </div>
            )}
            {alerts && alerts.map((a, i) => (
              <div key={i} className="alert-row">
                <span className="alert-icon">{alertIcon(a.type)}</span>
                <span className="alert-ticker">{a.ticker || "—"}</span>
                <span className="alert-desc">{a.message || a.type || "Alert"}</span>
                <span className="alert-time">{a.timestamp ? fmtDateTime(a.timestamp) : "—"}</span>
              </div>
            ))}
          </div>
        </div>

        {isAdmin && (
          <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "center", flexWrap: "wrap" }}>
            <button className="btn btn-primary" onClick={save} disabled={saving}>
              {saving ? "Saving…" : saved ? "✓ Saved" : "Save Settings"}
            </button>
            <button className="btn btn-secondary" onClick={testNotify} disabled={testing}>
              {testing ? "Sending…" : <>{ICONS.Phone({ size: 14 })} Test Notification</>}
            </button>
            <span className="text-dim text-sm">ntfy.sh/sam-madding-finance-alerts</span>
            {ntfyResult && (
              <span style={{ fontSize: "var(--text-body-sm)", color: ntfyResult.ok ? "var(--success-text)" : "var(--error-text)" }}>
                {ntfyResult.ok
                  ? `✓ Sent (HTTP ${ntfyResult.status_code}) — check your phone`
                  : `✗ Failed — ${ntfyResult.error || ntfyResult.body || "unknown error"}`}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── HistoryPage ───────────────────────────────────────────────────────────────
function HistoryPage({ onAnalyzeTicker }) {
  const [history, setHistory] = useState(null);
  const [search,  setSearch]  = useState("");

  useEffect(() => {
    api("/api/history").then(setHistory);
  }, []);

  if (history?.vercel_mode) {
    return (
      <div className="page">
        <div className="page-header"><div><h1>Analysis History</h1><p>Not available on cloud version</p></div></div>
        <div className="card">
          <div className="empty-state">
            <div className="empty-icon">{ICONS.FolderOpen({ size: 48 })}</div>
            <h3>History Available Locally</h3>
            <p>Analysis history is stored on your machine. Run the platform at <strong>localhost:5001</strong> to access your full history and download past reports.</p>
          </div>
        </div>
      </div>
    );
  }

  // Show skeleton while loading
  if (history === null) {
    return (
      <div className="page">
        <div className="page-header"><h1>Analysis History</h1><p>Loading…</p></div>
        <div className="history-list">
          {Array(3).fill(0).map((_, i) => (
            <div key={i} className="history-card" style={{ padding: "var(--space-5) var(--space-6)" }}>
              <div className="skeleton" style={{ height: 24, width: 80, marginBottom: 8 }} />
              <div className="skeleton" style={{ height: 14, width: 160 }} />
            </div>
          ))}
        </div>
      </div>
    );
  }

  const filtered = (history?.items ?? []).filter(h =>
    h.ticker.includes(search.toUpperCase())
  );

  return (
    <div className="page">
      <div className="page-header" style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <h1>Analysis History</h1>
          <p>{`${filtered.length} ${filtered.length === 1 ? "analysis" : "analyses"}`}</p>
        </div>
        <input
          className="input"
          style={{ width: 160, fontSize: "var(--text-body-sm)", height: 36 }}
          placeholder="Filter ticker…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      {filtered.length === 0 && (
        <div className="card">
          <div className="empty-state">
            <div className="empty-icon">{ICONS.FolderOpen({ size: 48 })}</div>
            <h3>{search ? "No match" : "No analyses yet"}</h3>
            <p>{search
              ? `No analyses found for "${search.toUpperCase()}"`
              : "Run your first analysis to see it here. Any public company, results in under 60 seconds."}</p>
            {!search && (
              <div className="empty-action">
                <button className="btn btn-primary" onClick={() => onAnalyzeTicker && onAnalyzeTicker("")}>
                  Run First Analysis →
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {filtered.length > 0 && (
        <div className="history-list">
          {filtered.map(h => (
            <div key={h.ticker} className="history-card">
              <div className="history-card-header">
                <div>
                  <div className="history-card-ticker">{h.ticker}</div>
                  <div className="history-card-name">{h.company || ""}</div>
                </div>
                <div className="history-card-date">{fmtDate(h.timestamp)}</div>
              </div>

              {(h.rating || h.target) && (
                <div className="history-card-meta">
                  {h.rating && (
                    <span className={`rating-tag ${ratingClass(h.rating)}`}>{h.rating}</span>
                  )}
                  {h.target && (
                    <span className="history-card-target">{h.target} target</span>
                  )}
                </div>
              )}

              <div className="history-card-files">
                {h.files.map(f => (
                  <a key={f} href={`/api/download/${h.ticker}/${f}`}
                    className="history-dl-btn" download>
                    <span>{fileIcon(f)}</span>
                    <span>{fileLabel(f).split(" ")[0]}</span>
                  </a>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────
function Sidebar({ page, onNavigate, theme, onToggleTheme, onShowAbout, onLaunchTour }) {
  const items = [
    { id: "analyze",       label: "Home",           icon: ICONS.BarChart },
    { id: "watchlist",     label: "Watchlist",      icon: (p={}) => (
      <Icon {...p}><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></Icon>
    )},
    { id: "lbo",           label: "LBO Calculator", icon: (p={}) => (
      <Icon {...p}><rect x="4" y="2" width="16" height="20" rx="1"/><path d="M9 22V12h6v10"/><path d="M8 7h.01M16 7h.01M8 11h.01M16 11h.01"/></Icon>
    )},
    { id: "ma",            label: "M&A Builder",    icon: (p={}) => (
      <Icon {...p}><circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M13 6h3a2 2 0 012 2v7"/><line x1="6" y1="9" x2="6" y2="21"/></Icon>
    )},
    { id: "notifications", label: "Notifications",  icon: ICONS.Bell },
    { id: "history",       label: "History",        icon: (p={}) => (
      <Icon {...p}><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></Icon>
    )},
  ];

  return (
    <nav className="sidebar">
      <div className="sidebar-logo">
        <img
          src="/assets/uc_logo_white.png"
          alt="University of Cincinnati"
          style={{ height: "34px", width: "auto" }}
          onError={(e) => e.target.style.display = "none"}
        />
        <span className="sidebar-platform-label">Equity Platform</span>
      </div>
      <div className="sidebar-nav">
        <div className="nav-section-label">Tools</div>
        {items.map(item => (
          <div key={item.id}
            className={`nav-item ${page === item.id ? "active" : ""}`}
            onClick={() => onNavigate(item.id)}
          >
            <span className="nav-icon">{item.icon({ size: 17 })}</span>
            <span className="nav-label">{item.label}</span>
          </div>
        ))}
      </div>
      <div className="sidebar-footer">
        <div className="sidebar-avatar">SM</div>
        <div className="sidebar-user">
          <div className="sidebar-user-name">Samuel Madding</div>
          <button className="about-link" onClick={onShowAbout}>About</button>
        </div>
        <button
          className="theme-toggle"
          onClick={onToggleTheme}
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          aria-label="Toggle dark mode"
        >
          {theme === "dark" ? ICONS.Sun({ size: 14 }) : ICONS.Moon({ size: 14 })}
        </button>
      </div>
      <div className="sidebar-disclaimer">
        Sam Madding is a student at the University of Cincinnati. This project is not affiliated with, sponsored by, or endorsed by the University of Cincinnati.
      </div>
      <button className="tour-sidebar-link" onClick={onLaunchTour} aria-label="Launch platform tour">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
          <path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/><path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/>
        </svg>
        Platform tour
      </button>
    </nav>
  );
}

// ── About Modal ───────────────────────────────────────────────────────────────
const TECH_STACK = [
  "Python", "Flask", "Claude AI", "yfinance", "FMP API",
  "SEC EDGAR", "NewsAPI", "reportlab", "openpyxl", "Vercel",
];

function AboutModal({ onClose }) {
  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-label="About this platform">
      <div className="about-modal-box" onClick={e => e.stopPropagation()}>
        {/* Close */}
        <button className="modal-close about-modal-close" onClick={onClose} aria-label="Close">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round"/>
          </svg>
        </button>

        {/* Hero */}
        <div className="about-hero">
          <div className="about-logo-mark">L</div>
          <div className="about-hero-name">Lindner Research Platform</div>
          <div className="about-hero-sub">AI-powered equity research for any public company</div>
        </div>

        {/* Platform description */}
        <div className="about-section">
          <p className="about-body">
            A full-stack AI research tool that generates institutional-grade equity analysis for any public company.
            Enter a ticker and receive a DCF model, comparable company analysis, SEC filing review, insider transaction
            tracking, earnings history, a 12-slide pitch deck, and a 10-page research PDF — all in under 60 seconds.
          </p>
          <p className="about-body about-note">
            Analyses are rate-limited to 10 per hour per visitor and 20 per day total to manage API costs.
          </p>
        </div>

        <div className="about-divider" />

        {/* Builder card */}
        <div className="about-builder-card">
          <div className="about-avatar">SM</div>
          <div className="about-builder-info">
            <div className="about-builder-name">Sam Madding</div>
            <div className="about-builder-detail">Finance · University of Cincinnati · Carl H. Lindner College of Business</div>
          </div>
          <div className="about-links">
            <a href="https://www.linkedin.com/in/sam-madding" target="_blank" rel="noopener noreferrer"
               className="about-link-btn" aria-label="LinkedIn profile" title="LinkedIn">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
                <path d="M16 8a6 6 0 016 6v7h-4v-7a2 2 0 00-2-2 2 2 0 00-2 2v7h-4v-7a6 6 0 016-6zM2 9h4v12H2z"/>
                <circle cx="4" cy="4" r="2"/>
              </svg>
            </a>
            <a href="https://github.com/maddinsd/portfolio-analyzer" target="_blank" rel="noopener noreferrer"
               className="about-link-btn" aria-label="GitHub repository" title="GitHub">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
                <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 00-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0020 4.77 5.07 5.07 0 0019.91 1S18.73.65 16 2.48a13.38 13.38 0 00-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 005 4.77a5.44 5.44 0 00-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 009 18.13V22"/>
              </svg>
            </a>
          </div>
        </div>

        <div className="about-divider" />

        {/* Tech stack */}
        <div className="about-stack-label">Built with</div>
        <div className="about-stack-pills">
          {TECH_STACK.map(t => <span key={t} className="about-stack-pill">{t}</span>)}
        </div>

        {/* Disclaimer */}
        <p className="about-disclaimer">
          Sam Madding is a student at the University of Cincinnati. This project is not affiliated with,
          sponsored by, or endorsed by the University of Cincinnati.
        </p>
      </div>
    </div>
  );
}

// ── Feedback Button & Modal ────────────────────────────────────────────────────
function FeedbackModal({ onClose }) {
  const [message, setMessage] = useState("");
  const [name,    setName]    = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!message.trim()) return;
    setSending(true);
    try {
      const res = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: message.trim(), name: name.trim() }),
      });
      if (res.ok) {
        window.toast && window.toast.success("Feedback sent — thanks!");
        onClose();
      } else {
        window.toast && window.toast.error("Couldn't send feedback. Try again.");
      }
    } catch {
      window.toast && window.toast.error("Network error. Try again.");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-label="Send feedback">
      <div className="modal-box feedback-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">Send Feedback</span>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round"/>
            </svg>
          </button>
        </div>
        <form className="modal-body feedback-form" onSubmit={handleSubmit}>
          <div className="feedback-field">
            <label className="feedback-label" htmlFor="fb-message">What's on your mind?</label>
            <textarea
              id="fb-message"
              className="feedback-textarea"
              placeholder="Bugs, ideas, questions, or anything else..."
              value={message}
              onChange={e => setMessage(e.target.value)}
              required
              rows={4}
            />
          </div>
          <div className="feedback-field">
            <label className="feedback-label" htmlFor="fb-name">Your name <span className="feedback-optional">(optional)</span></label>
            <input
              id="fb-name"
              type="text"
              className="feedback-input"
              placeholder="Sam Madding"
              value={name}
              onChange={e => setName(e.target.value)}
            />
          </div>
          <button type="submit" className="feedback-submit" disabled={!message.trim() || sending}>
            {sending ? "Sending…" : "Send Feedback →"}
          </button>
        </form>
      </div>
    </div>
  );
}

function FeedbackButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        id="feedback-btn"
        className="feedback-fab"
        onClick={() => setOpen(true)}
        aria-label="Send feedback"
        title="Send feedback"
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" className="feedback-fab-icon">
          <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
        </svg>
        <span className="feedback-fab-label">Feedback</span>
      </button>
      {open && <FeedbackModal onClose={() => setOpen(false)} />}
    </>
  );
}

// ── Keyboard Shortcuts ────────────────────────────────────────────────────────
const SHORTCUTS = [
  { keys: ["/"],        action: "Focus ticker input" },
  { keys: ["d"],        action: "Toggle dark mode" },
  { keys: ["?"],        action: "Show keyboard shortcuts" },
  { keys: ["Esc"],      action: "Close modal" },
  { keys: ["g", "h"],   action: "Go to Home" },
  { keys: ["g", "w"],   action: "Go to Watchlist" },
  { keys: ["g", "l"],   action: "Go to LBO Calculator" },
  { keys: ["g", "m"],   action: "Go to M&A Builder" },
];

function ShortcutsModal({ onClose }) {
  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-label="Keyboard shortcuts">
      <div className="modal-box shortcuts-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">Keyboard Shortcuts</span>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round"/>
            </svg>
          </button>
        </div>
        <div className="modal-body shortcuts-body">
          <table className="shortcuts-table">
            <tbody>
              {SHORTCUTS.map((s, i) => (
                <tr key={i} className="shortcuts-row">
                  <td className="shortcuts-keys">
                    {s.keys.map((k, j) => (
                      <span key={j}>
                        <kbd className="kbd">{k}</kbd>
                        {j < s.keys.length - 1 && <span className="kbd-then">then</span>}
                      </span>
                    ))}
                  </td>
                  <td className="shortcuts-action">{s.action}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="shortcuts-hint">Press <kbd className="kbd">?</kbd> to close</p>
        </div>
      </div>
    </div>
  );
}

function useKeyboardShortcuts({ onNavigate, onToggleTheme, onShowShortcuts, showShortcuts }) {
  const gRef = useRef(null); // tracks pending "g" prefix

  useEffect(() => {
    const handler = (e) => {
      const tag = document.activeElement?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (document.activeElement?.isContentEditable) return;

      const key = e.key;

      // Escape closes any open modal — handled by individual modals already,
      // but also clear the "g" prefix state here.
      if (key === "Escape") { gRef.current = null; return; }

      // "g" prefix navigation
      if (gRef.current === "g") {
        gRef.current = null;
        if (key === "h") { onNavigate("analyze");       return; }
        if (key === "w") { onNavigate("watchlist");     return; }
        if (key === "l") { onNavigate("lbo");           return; }
        if (key === "m") { onNavigate("ma");            return; }
        return;
      }

      if (key === "g") { gRef.current = "g"; setTimeout(() => { gRef.current = null; }, 600); return; }
      if (key === "d") { onToggleTheme(); return; }
      if (key === "?") { onShowShortcuts(); return; }
      if (key === "/") {
        e.preventDefault();
        onNavigate("analyze");
        setTimeout(() => {
          const input = document.querySelector(".ticker-input");
          if (input) input.focus();
        }, 80);
        return;
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onNavigate, onToggleTheme, onShowShortcuts]);
}

// ── Onboarding Tour ───────────────────────────────────────────────────────────
const TOUR_SEEN_KEY   = "lindner_onboarding_seen";
const TOUR_REPEAT_KEY = "lindner_onboarding_repeat";

function shouldShowTour() {
  if (localStorage.getItem(TOUR_SEEN_KEY)) {
    return localStorage.getItem(TOUR_REPEAT_KEY) === "1";
  }
  return true;
}

const TOUR_SLIDES = [
  {
    key: "welcome",
    icon: () => (
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="var(--accent-primary)" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>
      </svg>
    ),
    heading: "Welcome to the Lindner Research Platform",
    sub: "Institutional-quality equity research in seconds. Built by Sam Madding at UC's Carl H. Lindner College of Business.",
  },
  {
    key: "analyze",
    icon: () => (
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="var(--accent-primary)" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
      </svg>
    ),
    heading: "Start with any ticker",
    sub: "Enter any public company's ticker symbol on the Home page to kick off a full analysis. The platform pulls live market data, SEC filings, and earnings history automatically.",
    tip: "Try AAPL, NVDA, or JPM to see the platform in action.",
  },
  {
    key: "outputs",
    icon: () => (
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="var(--accent-primary)" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/>
      </svg>
    ),
    heading: "Four research outputs",
    sub: "Every analysis generates a complete package:",
    outputs: [
      { icon: "📊", label: "Excel Workbook",    desc: "16-sheet Goldman-style financial model" },
      { icon: "📄", label: "Research PDF",       desc: "10-page institutional equity report" },
      { icon: "📋", label: "Pitch Deck",         desc: "12-slide investment thesis deck" },
      { icon: "🎓", label: "Education Guide",    desc: "Plain-English companion for each output" },
    ],
  },
  {
    key: "lbo-ma",
    icon: () => (
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="var(--accent-primary)" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <rect x="4" y="2" width="16" height="20" rx="1"/><path d="M9 22V12h6v10"/><line x1="9" y1="7" x2="15" y2="7"/>
      </svg>
    ),
    heading: "LBO & M&A models",
    sub: "Run standalone Leveraged Buyout and Merger & Acquisition models for any company. Get full return schedules, debt waterfalls, accretion/dilution analysis, and 5×5 sensitivity tables — all exported to Excel.",
  },
  {
    key: "watchlist",
    icon: () => (
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="var(--accent-primary)" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/>
      </svg>
    ),
    heading: "Watchlist & notifications",
    sub: "Add tickers to your Watchlist to monitor live quotes, analyst targets, and price alerts. The Notifications page shows recent market alerts and earnings calendar events.",
  },
  {
    key: "done",
    heading: "You're all set",
    sub: "Dive into your first analysis whenever you're ready. Come back to this tour any time via the sidebar.",
    isDone: true,
  },
];

function OnboardingTour({ onClose }) {
  const [slide,    setSlide]    = useState(0);
  const [repeat,   setRepeat]   = useState(false);
  const [animKey,  setAnimKey]  = useState(0);
  const total = TOUR_SLIDES.length;

  const dismiss = useCallback((showNext) => {
    localStorage.setItem(TOUR_SEEN_KEY, "1");
    localStorage.setItem(TOUR_REPEAT_KEY, repeat ? "1" : "0");
    onClose();
  }, [repeat, onClose]);

  const next = useCallback(() => {
    if (slide < total - 1) {
      setSlide(s => s + 1);
      setAnimKey(k => k + 1);
    } else {
      dismiss();
    }
  }, [slide, total, dismiss]);

  // Focus trap + Escape
  const cardRef = useRef(null);
  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") dismiss(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [dismiss]);

  useEffect(() => {
    if (cardRef.current) cardRef.current.focus();
  }, []);

  const s = TOUR_SLIDES[slide];

  return (
    <div className="tour-backdrop" onClick={dismiss} role="dialog" aria-modal="true" aria-label="Platform tour">
      <div className="tour-card" ref={cardRef} tabIndex={-1} onClick={e => e.stopPropagation()}>
        <div className="tour-top-bar">
          <button className="tour-skip" onClick={dismiss}>Skip tour</button>
        </div>

        <div className="tour-slide-wrap">
          <div className="tour-slide" key={animKey}>
            {s.isDone ? (
              <div className="tour-check-wrap">
                <div className="tour-check-circle">
                  <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#34C759" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="tour-check-svg">
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                </div>
              </div>
            ) : (
              <div className="tour-icon-wrap">
                {s.icon && s.icon()}
              </div>
            )}

            <div className="tour-heading">{s.heading}</div>
            <div className="tour-sub">{s.sub}</div>

            {s.tip && (
              <div className="tour-tip">💡 {s.tip}</div>
            )}

            {s.outputs && (
              <div className="tour-outputs">
                {s.outputs.map(o => (
                  <div key={o.label} className="tour-output-row">
                    <span className="tour-output-icon">{o.icon}</span>
                    <span><span className="tour-output-label">{o.label}</span> — {o.desc}</span>
                  </div>
                ))}
              </div>
            )}

            {s.isDone && (
              <label className="tour-repeat-row">
                <input
                  type="checkbox"
                  className="tour-repeat-checkbox"
                  checked={repeat}
                  onChange={e => setRepeat(e.target.checked)}
                />
                Show this tour next time I visit
              </label>
            )}
          </div>
        </div>

        <div className="tour-footer">
          <div className="tour-dots">
            {TOUR_SLIDES.map((_, i) => (
              <div key={i} className={`tour-dot${i === slide ? " active" : ""}`} />
            ))}
          </div>
          <button className="tour-next-btn" onClick={next}>
            {slide < total - 1 ? "Next →" : "Get Started →"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Notice Card (dismissable) ─────────────────────────────────────────────────
function NoticeCard() {
  const DISMISSED_KEY = "lindner_notice_dismissed";
  const [visible, setVisible] = useState(() => !localStorage.getItem(DISMISSED_KEY));

  const dismiss = () => {
    localStorage.setItem(DISMISSED_KEY, "1");
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div className="notice-card">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, color: "var(--accent-primary)" }}>
        <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
      </svg>
      <span className="notice-text">
        Personal research platform built by Sam Madding · University of Cincinnati · Analyses are rate limited to ensure availability
      </span>
      <button className="notice-dismiss" onClick={dismiss} aria-label="Dismiss">
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
          <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round"/>
        </svg>
      </button>
    </div>
  );
}

// ── VisitorBanner ─────────────────────────────────────────────────────────────
function VisitorBanner({ storageKey, heading, children }) {
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem(storageKey) === "1"
  );
  if (dismissed) return null;
  return (
    <div className="visitor-banner">
      <svg className="visitor-banner-icon" width="16" height="16" viewBox="0 0 16 16" fill="none">
        <rect x="3" y="7" width="10" height="8" rx="1.5" stroke="var(--accent-primary)" strokeWidth="1.5"/>
        <path d="M5 7V5a3 3 0 0 1 6 0v2" stroke="var(--accent-primary)" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
      <div className="visitor-banner-content">
        <div className="visitor-banner-heading">{heading}</div>
        <div className="visitor-banner-body">{children}</div>
      </div>
      <button
        className="visitor-banner-dismiss"
        aria-label="Dismiss"
        onClick={() => { localStorage.setItem(storageKey, "1"); setDismissed(true); }}
      >×</button>
    </div>
  );
}

// ── App root ──────────────────────────────────────────────────────────────────
function App() {
  const [page,            setPage]            = useState("analyze");
  const [prefilledTicker, setPrefilledTicker] = useState("");
  const [isVercel,        setIsVercel]        = useState(false);
  const [isAdmin,         setIsAdmin]         = useState(true);
  const [theme,           setTheme]           = useState(getInitialTheme);
  const [showAbout,       setShowAbout]       = useState(false);
  const [showTour,        setShowTour]        = useState(shouldShowTour);
  const [showShortcuts,   setShowShortcuts]   = useState(false);

  useEffect(() => {
    applyTheme(theme);
    const t = setTimeout(() => {
      document.documentElement.classList.add("theme-transition");
    }, 150);
    return () => clearTimeout(t);
  }, [theme]);

  useEffect(() => {
    api("/api/config").then(d => setIsVercel(!!d.is_vercel)).catch(() => {});
    api("/api/auth/status").then(d => setIsAdmin(!!d.is_admin)).catch(() => setIsAdmin(false));
  }, []);

  const handleAnalyzeTicker = useCallback((ticker) => {
    if (ticker) setPrefilledTicker(ticker);
    setPage("analyze");
  }, []);

  const handleNavigate = useCallback((p) => setPage(p), []);

  const toggleTheme = useCallback(() => {
    setTheme(t => t === "dark" ? "light" : "dark");
  }, []);

  useKeyboardShortcuts({
    onNavigate: handleNavigate,
    onToggleTheme: toggleTheme,
    onShowShortcuts: () => setShowShortcuts(s => !s),
    showShortcuts,
  });

  const pages = {
    analyze:       <AnalyzePage prefilledTicker={prefilledTicker} isVercel={isVercel} onNavigate={handleNavigate} />,
    watchlist:     <DashboardPage onAnalyzeTicker={handleAnalyzeTicker} onNavigate={handleNavigate} isAdmin={isAdmin} />,
    lbo:           <LBOPage />,
    ma:            <MAPage />,
    notifications: <NotificationsPage isAdmin={isAdmin} />,
    history:       <HistoryPage onAnalyzeTicker={handleAnalyzeTicker} />,
  };

  return (
    <div className="app-shell">
      <Sidebar page={page} onNavigate={handleNavigate} theme={theme} onToggleTheme={toggleTheme} onShowAbout={() => setShowAbout(true)} onLaunchTour={() => setShowTour(true)} />
      <div className="content-area">
        <TickerTape />
        {page === "analyze" && <NoticeCard />}
        {pages[page]}
      </div>
      <FeedbackButton />
      {showAbout     && <AboutModal     onClose={() => setShowAbout(false)} />}
      {showTour      && <OnboardingTour onClose={() => setShowTour(false)} />}
      {showShortcuts && <ShortcutsModal onClose={() => setShowShortcuts(false)} />}
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
