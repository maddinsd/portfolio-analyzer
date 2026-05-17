/* Lindner Research Platform — React SPA
   React 18 + Babel standalone, no build step required */

const { useState, useEffect, useRef, useCallback } = React;

// ── Helpers ──────────────────────────────────────────────────────────────────
const api = (path, opts = {}) =>
  fetch(path, { credentials: "same-origin", ...opts })
    .then(r => r.json());

function fileIcon(name) {
  if (name.endsWith(".xlsx")) return "📊";
  if (name.endsWith(".pdf"))  return "📄";
  if (name.endsWith(".pptx")) return "📑";
  if (name.endsWith(".md"))   return "📝";
  return "📁";
}
function fileLabel(name) {
  if (name.includes("Excel"))      return "Excel Report";
  if (name.includes("Research"))   return "Research PDF";
  if (name.includes("Pitch"))      return "Pitch Deck";
  if (name.includes("Education"))  return "Education Guide";
  if (name.includes("Analysis"))   return "Analysis Notes";
  return name;
}
function fmtDate(ts) {
  return new Date(ts * 1000).toLocaleDateString("en-US", { month:"short", day:"numeric", year:"numeric" });
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
    return <div className="quote-preview loading">⟳ Looking up {ticker}…</div>;
  if (!quote) return null;
  if (!quote.valid)
    return <div className="quote-preview invalid">✗ {quote.error || "Ticker not found"}</div>;
  const sign = quote.change_pct >= 0 ? "+" : "";
  return (
    <div className="quote-preview valid">
      <span>✓</span>
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
  const [pct, setPct]     = useState(0);
  const [error, setError] = useState(null);
  const esRef = useRef(null);

  useEffect(() => {
    if (!jobId) return;
    const es = new EventSource(`/api/progress/${jobId}`);
    esRef.current = es;

    es.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.heartbeat) return;

      if (msg.error) {
        setError(msg.error);
        es.close();
        return;
      }
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
        setSteps(prev => prev.map(s => ({ ...s, status: "done" })));
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
        <span className="progress-pct">{pct}%</span>
      </div>
      <div className="progress-bar-track">
        <div className="progress-bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="progress-steps">
        {steps.map((s, i) => (
          <div key={i} className={`progress-step ${s.status}`}>
            <div className="step-icon">
              {s.status === "done"    ? <div className="step-icon-done">✓</div> :
               s.status === "running" ? <div className="spinner" /> :
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
        <span className="results-tick">✓</span>
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
            <span>↓</span>
          </a>
        ))}
      </div>
      {stats.dcf && <div className="phone-sent mt-3">📱 Notification sent · {stats.dcf}</div>}
    </div>
  );
}

// ── AnalyzePage ───────────────────────────────────────────────────────────────
function AnalyzePage() {
  const [ticker,   setTicker]   = useState("");
  const [audience, setAudience] = useState("student");
  const [flags,    setFlags]    = useState(["--full"]);
  const [phase,    setPhase]    = useState("input"); // input | progress | results
  const [jobId,    setJobId]    = useState(null);
  const [result,   setResult]   = useState(null);
  const [loading,  setLoading]  = useState(false);
  const { quote, loading: qLoading } = useQuote(ticker);

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
    } catch (e) { alert("Failed to start analysis"); }
    setLoading(false);
  };

  const handleDone = (msg) => { setResult(msg); setPhase("results"); };
  const handleReset = () => { setPhase("input"); setTicker(""); setResult(null); setJobId(null); };

  const outputOptions = [
    { flag: "--full",      label: "Full Package" },
    { flag: "--pdf",       label: "Research PDF" },
    { flag: "--pitch",     label: "Pitch Deck" },
    { flag: "--education", label: "Education Guide" },
  ];

  // When --full is selected, others are implicit
  const isFull = flags.includes("--full");

  return (
    <div className="page">
      <div className="page-header">
        <h1>Stock Analysis</h1>
        <p>Full pipeline: DCF · Research agents · Competitive · Analyst coverage · SEC filings · Insider tracking</p>
      </div>

      <div className="card">
        {phase === "input" && (
          <div className="card-body">
            <div style={{ marginBottom: "1.25rem" }}>
              <label className="field-label">Ticker Symbol</label>
              <div className="input-row">
                <input
                  className={`input ${quote?.valid ? "valid" : ticker.length > 0 && !qLoading && quote ? "invalid" : ""}`}
                  value={ticker}
                  onChange={e => setTicker(e.target.value.toUpperCase())}
                  placeholder="AAPL"
                  maxLength={6}
                  onKeyDown={e => { if (e.key === "Enter" && quote?.valid) runAnalysis(); }}
                />
                <button
                  className="btn btn-primary"
                  disabled={!quote?.valid || loading}
                  onClick={runAnalysis}
                >
                  {loading ? "Starting…" : "Analyze →"}
                </button>
              </div>
              <QuotePreview ticker={ticker} quote={quote} loading={qLoading} />
            </div>

            <hr className="divider" />

            <div style={{ marginBottom: "1.25rem" }}>
              <label className="field-label">Output Package</label>
              <div className="options-grid">
                {outputOptions.map(o => {
                  const sel = flags.includes(o.flag) || (isFull && o.flag !== "--full");
                  return (
                    <div
                      key={o.flag}
                      className={`option-chip ${sel ? "selected" : ""}`}
                      onClick={() => toggleFlag(o.flag)}
                    >
                      {sel && <span className="check">✓</span>}
                      {o.label}
                    </div>
                  );
                })}
              </div>
            </div>

            <div>
              <label className="field-label">Education Audience</label>
              <div className="audience-toggle">
                {["student", "professional"].map(a => (
                  <button
                    key={a}
                    className={`audience-btn ${audience === a ? "active" : ""}`}
                    onClick={() => setAudience(a)}
                  >
                    {a.charAt(0).toUpperCase() + a.slice(1)}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {phase === "progress" && (
          <ProgressPanel jobId={jobId} onDone={handleDone} />
        )}

        {phase === "results" && result && (
          <ResultsPanel result={result} onReset={handleReset} />
        )}
      </div>
    </div>
  );
}

// ── LBOPage ───────────────────────────────────────────────────────────────────
function LBOPage() {
  const [ticker,    setTicker]    = useState("");
  const [entryMult, setEntryMult] = useState(null); // null = auto
  const [holdYears, setHoldYears] = useState(5);
  const [debtPct,   setDebtPct]   = useState(60);
  const [phase,     setPhase]     = useState("input");
  const [jobId,     setJobId]     = useState(null);
  const [result,    setResult]    = useState(null);
  const [loading,   setLoading]   = useState(false);
  const { quote, loading: qLoading } = useQuote(ticker);

  // Rough IRR estimate (simplified): IRR ≈ (MOIC^(1/n) - 1) where MOIC estimated from exit/entry
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
        body: JSON.stringify({
          ticker,
          entry_multiple: entryMult || null,
          hold_years: holdYears,
          debt_pct: debtPct / 100,
        }),
      });
      if (data.error) { alert(data.error); setLoading(false); return; }
      setJobId(data.job_id);
      setPhase("progress");
    } catch (e) { alert("Failed to start LBO"); }
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

        {phase === "progress" && (
          <ProgressPanel jobId={jobId} onDone={handleDone} />
        )}

        {phase === "results" && result && (
          <div className="results-panel">
            <div className="results-header">
              <span className="results-tick">✓</span>
              <div>
                <div className="results-title">LBO Model — {result.ticker}</div>
                <div className="results-sub">9-tab Excel workbook · IRR/MOIC · Sensitivity tables</div>
              </div>
              <button className="btn btn-ghost btn-sm" style={{ marginLeft: "auto" }} onClick={handleReset}>New Model</button>
            </div>
            <div className="files-grid">
              <a href={`/api/download/lbo/${result.file}`} className="file-btn" download>
                <span className="file-icon">📊</span>
                <span className="file-name">{result.file}</span>
                <span>↓</span>
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
        body: JSON.stringify({
          acquirer: acq,
          target: tgt,
          premium_pct: premium,
          cash_pct: cashPct,
          synergies_m: synergies ? parseFloat(synergies) : null,
        }),
      });
      if (data.error) { alert(data.error); setLoading(false); return; }
      setJobId(data.job_id);
      setPhase("progress");
    } catch (e) { alert("Failed to start M&A model"); }
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

        {phase === "progress" && (
          <ProgressPanel jobId={jobId} onDone={handleDone} />
        )}

        {phase === "results" && result && (
          <div className="results-panel">
            <div className="results-header">
              <span className="results-tick">✓</span>
              <div>
                <div className="results-title">{result.acquirer} acquires {result.target}</div>
                <div className="results-sub">8-tab merger consequences model · EPS accretion/dilution</div>
              </div>
              <button className="btn btn-ghost btn-sm" style={{ marginLeft: "auto" }} onClick={handleReset}>New Deal</button>
            </div>
            <div className="files-grid">
              <a href={`/api/download/ma/${result.file}`} className="file-btn" download>
                <span className="file-icon">📊</span>
                <span className="file-name">{result.file}</span>
                <span>↓</span>
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
    setSaving(false);
    setSaved(true);
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
    { key: "price_moves",        label: "Price Moves",       sub: `>${th.price_move || 3}% daily move` },
    { key: "analyst_changes",    label: "Analyst Changes",   sub: "Upgrades, downgrades, target changes" },
    { key: "insider_buying",     label: "Insider Buying",    sub: `Open market buys >$${th.insider_buy || 1}M` },
    { key: "earnings_surprises", label: "Earnings Surprises",sub: `EPS beat/miss >${th.earnings_surp || 5}%` },
    { key: "sec_filings",        label: "SEC Filings",       sub: "New 10-K and 10-Q filings" },
    { key: "morning_briefing",   label: "Morning Briefing",  sub: "Daily 7am market summary" },
  ];

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
              { key: "price_move",   label: "Price Move Alert",        unit: "%",  min: 1, max: 10, step: 1 },
              { key: "insider_buy",  label: "Insider Buy Minimum",      unit: "$M", min: 0.1, max: 5, step: 0.1 },
              { key: "earnings_surp",label: "Earnings Surprise Alert",  unit: "%",  min: 2, max: 15, step: 1 },
              { key: "target_change",label: "Analyst Target Change",    unit: "%",  min: 5, max: 25, step: 5 },
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

        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          <button className="btn btn-primary" onClick={save} disabled={saving}>
            {saving ? "Saving…" : saved ? "✓ Saved" : "Save Settings"}
          </button>
          <button className="btn btn-secondary" onClick={testNotify} disabled={testing}>
            {testing ? "Sending…" : "📱 Test Notification"}
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

  return (
    <div className="page">
      <div className="page-header">
        <h1>Analysis History</h1>
        <p>All past analyses saved to Desktop/reports/</p>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">{history ? `${filtered.length} analyses` : "Loading…"}</span>
          <input
            className="input"
            style={{ width: "160px", fontSize: "0.8rem", padding: "0.3rem 0.6rem" }}
            placeholder="Filter ticker…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>

        {history === null && (
          <div className="card-body"><div className="text-muted">Loading…</div></div>
        )}

        {history !== null && filtered.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon">📂</div>
            <h3>{search ? "No match" : "No analyses yet"}</h3>
            <p>{search ? `No analyses for "${search.toUpperCase()}"` : "Run your first analysis to see history here"}</p>
          </div>
        )}

        {filtered.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <table className="history-table">
              <thead>
                <tr>
                  <th>Ticker</th>
                  <th>Date Run</th>
                  <th>Outputs</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(h => (
                  <tr key={h.ticker}>
                    <td><span className="ticker-cell">{h.ticker}</span></td>
                    <td className="text-muted">{fmtDate(h.timestamp)}</td>
                    <td>
                      {h.files.map(f => (
                        <a key={f} href={`/api/download/${h.ticker}/${f}`}
                          className="file-badge" download title={f}>
                          {fileIcon(f)} {f.replace(/^\d{2}_[A-Z]+_/, "").replace(/\.[^.]+$/, "")}
                        </a>
                      ))}
                    </td>
                    <td>
                      <a href={`/api/download/${h.ticker}/05_${h.ticker}_Analysis.md`}
                        className="btn btn-ghost btn-sm" style={{ textDecoration: "none" }} download>
                        ↓ Notes
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────
function Sidebar({ page, onNavigate }) {
  const items = [
    { id: "analyze",       icon: "📊", label: "New Analysis" },
    { id: "lbo",           icon: "🏗",  label: "LBO Calculator" },
    { id: "ma",            icon: "🤝",  label: "M&A Deal Builder" },
    { id: "notifications", icon: "🔔",  label: "Notifications" },
    { id: "history",       icon: "📋",  label: "History" },
  ];
  return (
    <nav className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-uc-mark">
          <img src="/static/uc_logo.png" alt="UC" onError={(e) => e.target.style.display='none'} />
        </div>
        <div className="logo-text">
          <h2>Lindner Research</h2>
          <span>Equity Platform</span>
        </div>
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
  const [page, setPage] = useState("analyze");

  const pages = {
    analyze:       <AnalyzePage />,
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
