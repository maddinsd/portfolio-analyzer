/* Lindner Research Platform — React SPA
   React 18 + Babel standalone, no build step required */

const { useState, useEffect, useRef, useCallback } = React;

// ── Helpers ──────────────────────────────────────────────────────────────────
const api = (path, opts = {}) =>
  fetch(path, { credentials: "same-origin", ...opts })
    .then(r => r.json());

// ============================================================
// ICON SYSTEM — single source of truth
// Heroicons v2 Outline (MIT) · 24px viewBox · stroke only
// All: strokeWidth 1.75, strokeLinecap round, strokeLinejoin round
// Color: currentColor (inherits from parent text color)
// ============================================================
const Icon = ({ size = 18, className = '', style, children }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width={size}
    height={size}
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
  // ── File types ────────────────────────────────────────────
  Excel:       (p = {}) => <Icon {...p}><path d="M3 3h18v18H3V3zm6 0v18m6-18v18M3 9h18M3 15h18"/></Icon>,
  PDF:         (p = {}) => <Icon {...p}><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="13" y2="17"/></Icon>,
  Powerpoint:  (p = {}) => <Icon {...p}><rect x="2" y="4" width="20" height="13" rx="2"/><path d="M12 17v3m-4 0h8M7 13V9m4 4V7m4 6v-3"/></Icon>,
  Education:   (p = {}) => <Icon {...p}><path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"/></Icon>,
  Markdown:    (p = {}) => <Icon {...p}><path d="M9 12h6m-6 4h4M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></Icon>,
  File:        (p = {}) => <Icon {...p}><path d="M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z"/><polyline points="13 2 13 9 20 9"/></Icon>,
  FolderOpen:  (p = {}) => <Icon {...p}><path d="M5 19a2 2 0 01-2-2V7a2 2 0 012-2h4l2 2h4a2 2 0 012 2v1M5 19h14a2 2 0 002-2v-5a2 2 0 00-2-2H9a2 2 0 00-2 2v5a2 2 0 01-2 2z"/></Icon>,
  // ── Actions ───────────────────────────────────────────────
  Download:    (p = {}) => <Icon {...p}><path d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3"/></Icon>,
  Check:       (p = {}) => <Icon {...p}><path d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></Icon>,
  CheckMark:   (p = {}) => <Icon {...p}><polyline points="20 6 9 17 4 12"/></Icon>,
  ErrorX:      (p = {}) => <Icon {...p}><path d="M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></Icon>,
  // ── Status / Alerts ───────────────────────────────────────
  Bell:        (p = {}) => <Icon {...p}><path d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0"/></Icon>,
  TrendingUp:  (p = {}) => <Icon {...p}><path d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941"/></Icon>,
  TrendingDown:(p = {}) => <Icon {...p}><path d="M2.25 6L9 12.75l4.286-4.286a11.948 11.948 0 014.306 6.43l.776 2.898m0 0l3.182-5.511m-3.182 5.51l-5.511-3.181"/></Icon>,
  BarChart:    (p = {}) => <Icon {...p}><path d="M3 3v18h18M18 17V9M12 17V3M6 17v-6"/></Icon>,
  ArrowUp:     (p = {}) => <Icon {...p}><path d="M12 19.5v-15m0 0l-6.75 6.75M12 4.5l6.75 6.75"/></Icon>,
  ArrowDown:   (p = {}) => <Icon {...p}><path d="M12 4.5v15m0 0l6.75-6.75M12 19.5l-6.75-6.75"/></Icon>,
  Phone:       (p = {}) => <Icon {...p}><path d="M10.5 1.5H8.25A2.25 2.25 0 006 3.75v16.5a2.25 2.25 0 002.25 2.25h7.5A2.25 2.25 0 0018 20.25V3.75a2.25 2.25 0 00-2.25-2.25H13.5m-3 0V3h3V1.5m-3 0h3m-3 8.25h3"/></Icon>,
  ChartLine:   (p = {}) => <Icon {...p}><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></Icon>,
};

function fileIcon(name) {
  if (name.endsWith(".xlsx")) return ICONS.Excel({ size: 16 });
  if (name.endsWith(".pdf"))  return ICONS.PDF({ size: 16 });
  if (name.endsWith(".pptx")) return ICONS.Powerpoint({ size: 16 });
  if (name.endsWith(".md"))   return ICONS.Markdown({ size: 16 });
  return ICONS.File({ size: 16 });
}
function fileLabel(name) {
  if (name.includes("Excel"))      return "Excel";
  if (name.includes("Research"))   return "PDF";
  if (name.includes("Pitch"))      return "Deck";
  if (name.includes("Education"))  return "Guide";
  if (name.includes("Analysis"))   return "Notes";
  return name.replace(/^\d{2}_[A-Z]+_/, "").replace(/\.[^.]+$/, "");
}
function fmtDate(ts) {
  return new Date(ts * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
function fmtDateTime(ts) {
  const d = new Date(ts * 1000);
  const today = new Date();
  const isToday = d.toDateString() === today.toDateString();
  const time = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  return isToday ? `Today ${time}` : `${d.toLocaleDateString("en-US", { month: "short", day: "numeric" })} ${time}`;
}
function isMarketOpen() {
  const now = new Date();
  const day = now.getUTCDay(); // 0=Sun, 6=Sat
  if (day === 0 || day === 6) return false;
  const h = now.getUTCHours(), m = now.getUTCMinutes();
  const mins = h * 60 + m;
  return mins >= 13 * 60 + 30 && mins < 20 * 60; // 9:30am–4pm ET (EDT offset)
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
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ overflow: "visible", flexShrink: 0 }}>
      <path d={d} fill="none" stroke={isUp ? "#34C759" : "#FF3B30"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
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
    </div>
  );
}

// ── Ticker card ───────────────────────────────────────────────────────────────
function TickerCard({ quote, onAnalyze }) {
  if (quote.error) {
    return (
      <div className="ticker-card ticker-card-error">
        <div className="ticker-symbol">{quote.ticker}</div>
        <div className="ticker-error" style={{ fontSize: 22, color: "var(--text-tertiary)", marginTop: 8 }}>—</div>
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
    return <div className="quote-preview loading"><span className="quote-preview-icon" style={{ opacity: 0.5 }}>{ICONS.ChartLine({ size: 14 })}</span> Validating {ticker}…</div>;
  if (!quote) return null;
  if (!quote.valid)
    return <div className="quote-preview invalid"><span className="quote-preview-icon">{ICONS.ErrorX({ size: 14 })}</span> {quote.error || "Ticker not found"}</div>;
  const sign = quote.change_pct >= 0 ? "+" : "";
  return (
    <div className="quote-preview valid">
      <span className="quote-preview-icon">{ICONS.CheckMark({ size: 14 })}</span>
      <span className="quote-name">{quote.name}</span>
      <span className="quote-price">${quote.price?.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
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

  // Animate percentage counter
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

  // Elapsed timer
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
        setSteps(prev => {
          const next = [...prev];
          if (next.length > 0) next[next.length - 1] = { ...next[next.length - 1], status: "done" };
          if (!msg.done) next.push({ message: msg.message, detail: msg.detail || "", status: "running" });
          return next;
        });
      }
      if (msg.done) {
        setPct(100);
        setSteps(prev => prev.map(s => ({ ...s, status: "done" })));
        clearInterval(timerRef.current);
        es.close();
        onDone(msg);
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
              {s.status === "done"    ? <div className="step-icon-done">{ICONS.CheckMark({ size: 12 })}</div> :
               s.status === "running" ? <div className="step-icon-active" /> :
               <div className="step-icon-circle" />}
            </div>
            <div className="step-content">
              <div>{s.message}</div>
              {s.detail && <div className="step-detail">{s.detail}</div>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── ResultsPanel component ────────────────────────────────────────────────────
function ResultsPanel({ result, onReset }) {
  const { ticker, company, stats = {}, files = [] } = result;
  const ratingClass = stats.rating === "Buy" ? "buy" : stats.rating === "Sell" ? "sell" : "";
  return (
    <div className="results-panel">
      <div className="results-header">
        <span className="results-tick">{ICONS.Check({ size: 20 })}</span>
        <div>
          <div className="results-title">{ticker} Analysis Complete</div>
          <div className="results-sub">{company}</div>
        </div>
        <button className="btn btn-ghost btn-sm" style={{ marginLeft: "auto" }} onClick={onReset}>
          New Analysis
        </button>
      </div>
      <div className="stats-grid">
        <div className="stat-block">
          <div className="stat-label">Consensus</div>
          <div className={`stat-value ${ratingClass}`}>{stats.rating || "—"}</div>
        </div>
        <div className="stat-block">
          <div className="stat-label">Price Target</div>
          <div className="stat-value">{stats.target || "—"}</div>
        </div>
        <div className="stat-block">
          <div className="stat-label">Current Price</div>
          <div className="stat-value">{stats.price || "—"}</div>
        </div>
      </div>
      <div className="files-grid">
        {files.map(f => (
          <a key={f} href={`/api/download/${ticker}/${f}`} className="file-btn" download>
            <span className="file-icon">{fileIcon(f)}</span>
            <span className="file-name">{fileLabel(f)}</span>
            <span className="file-dl">{ICONS.Download({ size: 13 })}</span>
          </a>
        ))}
      </div>
      {stats.dcf && <div className="phone-sent mt-3">{ICONS.Phone({ size: 14 })} Notification sent · {stats.dcf}</div>}
    </div>
  );
}

// ── DashboardPage ─────────────────────────────────────────────────────────────
function DashboardPage({ onAnalyzeTicker }) {
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
      <div className="dash-header">
        <div>
          <div className="dash-title">Watchlist</div>
          <div className="dash-meta">
            {quotes ? `${count} tickers` : "Loading…"}
            {" · "}
            {isMarketOpen()
              ? <span className="market-open">Markets Open</span>
              : <span className="market-closed">Markets Closed</span>}
          </div>
        </div>
        {updatedStr && <div className="dash-time">Updated {updatedStr}</div>}
      </div>

      <div className="ticker-grid">
        {quotes === null
          ? Array(8).fill(0).map((_, i) => <SkeletonCard key={i} />)
          : quotes.length === 0
          ? (
            <div className="empty-state" style={{ gridColumn: "1/-1" }}>
              <div className="empty-icon">{ICONS.ChartLine({ size: 40 })}</div>
              <h3>Watchlist is empty</h3>
              <p>Add tickers on the Notifications page to see live prices here.</p>
            </div>
          )
          : quotes.map(q => (
            <TickerCard key={q.ticker} quote={q} onAnalyze={onAnalyzeTicker} />
          ))}
      </div>
    </div>
  );
}

// ── AnalyzePage ───────────────────────────────────────────────────────────────
function AnalyzePage({ prefilledTicker }) {
  const [ticker,   setTicker]   = useState("");
  const [audience, setAudience] = useState("student");
  const [flags,    setFlags]    = useState(["--full"]);
  const [phase,    setPhase]    = useState("input");
  const [jobId,    setJobId]    = useState(null);
  const [result,   setResult]   = useState(null);
  const [loading,  setLoading]  = useState(false);
  const { quote, loading: qLoading } = useQuote(ticker);

  // Pre-fill ticker from dashboard "Analyze →" click
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
      if (data.error) { alert(data.error); setLoading(false); return; }
      setJobId(data.job_id);
      setPhase("progress");
    } catch { alert("Failed to start analysis"); }
    setLoading(false);
  };

  const handleDone = (msg) => { setResult(msg); setPhase("results"); };
  const handleReset = () => { setPhase("input"); setTicker(""); setResult(null); setJobId(null); };

  const isFull = flags.includes("--full");

  const outcomeOptions = [
    { flag: "--full",      icon: ICONS.Excel,      label: "17-Sheet Excel",   sub: "Goldman-style workbook" },
    { flag: "--pdf",       icon: ICONS.PDF,        label: "10-Page PDF",      sub: "Equity research report" },
    { flag: "--pitch",     icon: ICONS.Powerpoint, label: "12-Slide Deck",    sub: "Pitch-ready PowerPoint" },
    { flag: "--education", icon: ICONS.Education,  label: "Education Guide",  sub: "Annotated companion PDF" },
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
            <div style={{ marginBottom: "1.5rem" }}>
              <label className="field-label">Ticker Symbol</label>
              <div className="input-row">
                <input
                  className={`input input-hero ${quote?.valid ? "valid" : ticker.length > 0 && !qLoading && quote ? "invalid" : ""}`}
                  value={ticker}
                  onChange={e => setTicker(e.target.value.toUpperCase())}
                  placeholder="AAPL, NVDA, LLY…"
                  maxLength={6}
                  onKeyDown={e => { if (e.key === "Enter" && quote?.valid) runAnalysis(); }}
                />
              </div>
              <QuotePreview ticker={ticker} quote={quote} loading={qLoading} />
            </div>

            <hr className="divider" />

            <div style={{ marginBottom: "1.5rem" }}>
              <label className="field-label">What you'll get</label>
              <div className="outcome-grid">
                {outcomeOptions.map(o => {
                  const sel = flags.includes(o.flag) || (isFull && o.flag !== "--full");
                  return (
                    <div key={o.flag} className={`outcome-card ${sel ? "selected" : ""}`}
                      onClick={() => toggleFlag(o.flag)}>
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

            <div style={{ marginTop: "1.5rem" }}>
              <button className="btn btn-primary btn-run"
                disabled={!quote?.valid || loading} onClick={runAnalysis}>
                {loading ? "Starting…" : "Run Full Analysis →"}
              </button>
              <div className="run-estimate">~45–60 seconds · Claude Sonnet 4.6</div>
            </div>
          </div>
        )}

        {phase === "progress" && <ProgressPanel jobId={jobId} onDone={handleDone} />}
        {phase === "results" && result && <ResultsPanel result={result} onReset={handleReset} />}
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
    const debtFrac = debtPct / 100;
    const equityFrac = 1 - debtFrac;
    const moic = exitMult / (entry * equityFrac);
    return moic.toFixed(1);
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
      if (data.error) { alert(data.error); setLoading(false); return; }
      setJobId(data.job_id);
      setPhase("progress");
    } catch { alert("Failed to start LBO"); }
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

      <div className="card">
        {phase === "input" && (
          <div className="card-body">
            <div style={{ marginBottom: "1.25rem" }}>
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

            <hr className="divider" />

            <div className="slider-field">
              <div className="slider-row">
                <label className="field-label" style={{ margin: 0 }}>Entry EV/EBITDA</label>
                <span className="slider-val">{entryMult ? `${entryMult}x` : "Auto"}</span>
              </div>
              <input type="range" min="5" max="20" step="0.5"
                value={entryMult || 10}
                onChange={e => setEntryMult(parseFloat(e.target.value))}
              />
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
                onChange={e => setDebtPct(parseInt(e.target.value))}
              />
              <div className="slider-bounds"><span>40%</span><span>60%</span><span>75%</span></div>
            </div>

            {quote?.valid && (
              <div className="preview-box">
                <h3>Preliminary Estimate (simplified)</h3>
                <div className="preview-row">
                  <span className="label">Entry Multiple</span>
                  <span className="val">{entryMult ? `${entryMult}x` : "Market + 10%"} EV/EBITDA</span>
                </div>
                <div className="preview-row">
                  <span className="label">Hold Period</span>
                  <span className="val">{holdYears} years</span>
                </div>
                <div className="preview-row">
                  <span className="label">Debt / TEV</span>
                  <span className="val">{debtPct}% / {100 - debtPct}% equity</span>
                </div>
                {moic && <div className="preview-row">
                  <span className="label">Est. MOIC (rough)</span>
                  <span className={`val ${irrClass}`}>{moic}x</span>
                </div>}
                {irr && <div className="preview-row">
                  <span className="label">Est. IRR (rough)</span>
                  <span className={`val ${irrClass}`}>{irr}%</span>
                </div>}
                <div className="text-dim text-sm mt-2">Run full model for precise debt schedule, 3-statement model, and 5×5 sensitivity</div>
              </div>
            )}
          </div>
        )}

        {phase === "progress" && <ProgressPanel jobId={jobId} onDone={handleDone} />}

        {phase === "results" && result && (
          <div className="results-panel">
            <div className="results-header">
              <span className="results-tick">{ICONS.Check({ size: 20 })}</span>
              <div>
                <div className="results-title">LBO Model — {result.ticker}</div>
                <div className="results-sub">9-tab Excel workbook · IRR/MOIC · Sensitivity tables</div>
              </div>
              <button className="btn btn-ghost btn-sm" style={{ marginLeft: "auto" }} onClick={handleReset}>New Model</button>
            </div>
            <div className="files-grid">
              <a href={`/api/download/lbo/${result.file}`} className="file-btn" download>
                <span className="file-icon">{ICONS.Excel({ size: 16 })}</span>
                <span className="file-name">{result.file}</span>
                <span className="file-dl">{ICONS.Download({ size: 13 })}</span>
              </a>
            </div>
          </div>
        )}
      </div>
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
    ? (tgtQuote.price * (1 + premium / 100)).toFixed(2)
    : null;
  const totalDealVal = tgtQuote?.valid && tgtQuote.market_cap
    ? ((tgtQuote.market_cap * (1 + premium / 100)) / 1e9).toFixed(1)
    : null;

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
      if (data.error) { alert(data.error); setLoading(false); return; }
      setJobId(data.job_id);
      setPhase("progress");
    } catch { alert("Failed to start M&A model"); }
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
            <div className="two-col" style={{ marginBottom: "1.25rem" }}>
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

            <div style={{ marginBottom: "1.25rem" }}>
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
                    <span className="val">${tgtQuote.price?.toFixed(2)}</span>
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
            <div className="results-header">
              <span className="results-tick">{ICONS.Check({ size: 20 })}</span>
              <div>
                <div className="results-title">{result.acquirer} acquires {result.target}</div>
                <div className="results-sub">8-tab merger consequences model · EPS accretion/dilution</div>
              </div>
              <button className="btn btn-ghost btn-sm" style={{ marginLeft: "auto" }} onClick={handleReset}>New Deal</button>
            </div>
            <div className="files-grid">
              <a href={`/api/download/ma/${result.file}`} className="file-btn" download>
                <span className="file-icon">{ICONS.Excel({ size: 16 })}</span>
                <span className="file-name">{result.file}</span>
                <span className="file-dl">{ICONS.Download({ size: 13 })}</span>
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── NotificationsPage ─────────────────────────────────────────────────────────
function NotificationsPage() {
  const [watchlist, setWatchlist] = useState({ tickers: [], thresholds: {}, alert_types: {} });
  const [newTicker, setNewTicker] = useState("");
  const [saving,    setSaving]    = useState(false);
  const [testing,   setTesting]   = useState(false);
  const [saved,     setSaved]     = useState(false);
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
    setTesting(true);
    await api("/api/notify/test", { method: "POST" });
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
      <div className="page-header">
        <h1>Notifications</h1>
        <p>Manage watchlist, alert thresholds, and ntfy.sh push notifications</p>
      </div>

      <div className="gap-1">
        <div className="card">
          <div className="card-header">
            <span className="card-title">Watchlist</span>
            <span className="text-dim text-sm">{watchlist.tickers.length} tickers</span>
          </div>
          <div className="card-body">
            <div className="chip-list">
              {watchlist.tickers.map(t => (
                <div key={t} className="ticker-chip">
                  {t}
                  <button className="chip-remove" onClick={() => removeTicker(t)}>×</button>
                </div>
              ))}
              {watchlist.tickers.length === 0 && <span className="text-dim text-sm">No tickers — add one below</span>}
            </div>
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
                  <label className="field-label" style={{ margin: 0 }}>{">"}{th[key] || min}{unit} {label}</label>
                  <span className="slider-val">{th[key] || min}{unit}</span>
                </div>
                <input type="range" min={min} max={max} step={step}
                  value={th[key] || min}
                  onChange={e => setThreshold(key, parseFloat(e.target.value))} />
                <div className="slider-bounds"><span>{min}{unit}</span><span>{max}{unit}</span></div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-header"><span className="card-title">Alert Types</span></div>
          <div className="card-body" style={{ padding: "0.5rem 1.25rem" }}>
            {alertRows.map(row => (
              <div key={row.key} className="switch-row">
                <div>
                  <div className="switch-label">{row.label}</div>
                  <div className="switch-sub">{row.sub}</div>
                </div>
                <label className="switch">
                  <input type="checkbox" checked={!!at[row.key]} onChange={() => toggleAlert(row.key)} />
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
          <div className="card-body" style={{ padding: "0 1.5rem" }}>
            {alerts === null && <div className="text-dim text-sm" style={{ padding: "16px 0" }}>Loading…</div>}
            {alerts !== null && alerts.length === 0 && (
              <div className="text-dim text-sm" style={{ padding: "16px 0" }}>
                Monitoring active. Alerts will appear here when triggered.
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

        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          <button className="btn btn-primary" onClick={save} disabled={saving}>
            {saving ? "Saving…" : saved ? "Saved" : "Save Settings"}
          </button>
          <button className="btn btn-secondary" onClick={testNotify} disabled={testing}>
            {testing ? "Sending…" : <>{ICONS.Phone({ size: 14 })} Test Notification</>}
          </button>
          <span className="text-dim text-sm">ntfy.sh/sam-madding-finance-alerts</span>
        </div>
      </div>
    </div>
  );
}

// ── HistoryPage ───────────────────────────────────────────────────────────────
function HistoryPage() {
  const [history, setHistory] = useState(null);
  const [search,  setSearch]  = useState("");

  useEffect(() => {
    api("/api/history").then(setHistory);
  }, []);

  const filtered = history?.filter(h =>
    h.ticker.includes(search.toUpperCase())
  ) || [];

  const ratingCls = (r) => {
    if (!r) return "";
    const l = r.toLowerCase();
    if (l === "buy")  return "buy";
    if (l === "sell") return "sell";
    return "hold";
  };

  return (
    <div className="page">
      <div className="page-header" style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <h1>Analysis History</h1>
          <p>{history ? `${filtered.length} ${filtered.length === 1 ? "analysis" : "analyses"}` : "Loading…"}</p>
        </div>
        <input
          className="input"
          style={{ width: 160, fontSize: "0.8rem", height: 36 }}
          placeholder="Filter ticker…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      {history === null && (
        <div className="card"><div className="card-body text-muted">Loading…</div></div>
      )}

      {history !== null && filtered.length === 0 && (
        <div className="empty-state">
          <div className="empty-icon">{ICONS.FolderOpen({ size: 40 })}</div>
          <h3>{search ? "No match" : "No analyses yet"}</h3>
          <p>{search ? `No analyses for "${search.toUpperCase()}"` : "Run your first analysis to see it here."}</p>
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
                    <span className={`rating-tag ${ratingCls(h.rating)}`}>{h.rating}</span>
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
                    <span>{fileLabel(f)}</span>
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
function Sidebar({ page, onNavigate }) {
  const items = [
    { id: "dashboard", label: "Home", icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>
        <polyline points="9 22 9 12 15 12 15 22"/>
      </svg>
    )},
    { id: "analyze", label: "New Analysis", icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
      </svg>
    )},
    { id: "lbo", label: "LBO Calculator", icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="4" y="2" width="16" height="20" rx="1"/><path d="M9 22V12h6v10"/><path d="M8 7h.01M16 7h.01M8 11h.01M16 11h.01"/>
      </svg>
    )},
    { id: "ma", label: "M&A Deal Builder", icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M13 6h3a2 2 0 012 2v7"/><line x1="6" y1="9" x2="6" y2="21"/>
      </svg>
    )},
    { id: "notifications", label: "Notifications", icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/>
      </svg>
    )},
    { id: "history", label: "History", icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
      </svg>
    )},
  ];

  return (
    <nav className="sidebar">
      <div className="sidebar-logo">
        <img
          src="/assets/uc_logo_white.png"
          alt="University of Cincinnati"
          style={{ height: "36px", width: "auto" }}
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
            <span className="nav-icon">{item.icon}</span>
            <span className="nav-label">{item.label}</span>
          </div>
        ))}
      </div>
      <div className="sidebar-footer">
        <div className="sidebar-avatar">SM</div>
        <div className="sidebar-user">
          <div className="sidebar-user-name">Samuel Madding</div>
          <a href="/logout">Sign out</a>
        </div>
      </div>
    </nav>
  );
}

// ── App root ──────────────────────────────────────────────────────────────────
function App() {
  const [page, setPage] = useState("dashboard");
  const [prefilledTicker, setPrefilledTicker] = useState("");

  const handleAnalyzeTicker = useCallback((ticker) => {
    setPrefilledTicker(ticker);
    setPage("analyze");
  }, []);

  const pages = {
    dashboard:     <DashboardPage onAnalyzeTicker={handleAnalyzeTicker} />,
    analyze:       <AnalyzePage prefilledTicker={prefilledTicker} />,
    lbo:           <LBOPage />,
    ma:            <MAPage />,
    notifications: <NotificationsPage />,
    history:       <HistoryPage />,
  };

  return (
    <div className="app-shell">
      <Sidebar page={page} onNavigate={setPage} />
      <div className="content-area">
        {pages[page]}
      </div>
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
