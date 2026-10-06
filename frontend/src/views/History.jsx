/**
 * History.jsx — Proposal evaluation archive.
 *
 * Features added in this iteration:
 *   - "Download Report" → GET /api/evaluations/{id}/report.pdf  (browser download)
 *   - "Export JSON"     → GET /api/evaluations/{id}/export.json (browser download)
 *   - Date-range filter (from / to date inputs) applied on top of text search
 *   - All filter/sort state is lifted into filterState (a single object) so it
 *     can be passed as a prop from App.jsx and survive navigation. When the prop
 *     is not provided the component falls back to sensible defaults.
 *
 * Props:
 *   evaluationVersion    — int; increment triggers a re-fetch
 *   onNavigateToAnalysis — () => void
 *   filterState          — optional persisted filter object from parent
 *   onFilterChange       — optional (state) => void called on every filter change
 */
import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { API_BASE_URL } from '../config'

// ── Dimension list (mirrors scoring.py) ───────────────────────────────────────
const DIMS = [
  { key: 'novelty_score',   label: 'Novelty'   },
  { key: 'technical_score', label: 'Technical' },
  { key: 'financial_score', label: 'Financial' },
  { key: 'impact_score',    label: 'Impact'    },
]

// ── Inline reviewer form (used in expanded detail rows) ───────────────────────

function HistoryReviewerForm({ rowId, existing }) {
  const [overrides, setOverrides]  = useState(() => {
    const rv = existing?.reviewer_overrides
    if (!rv) return {}
    if (typeof rv === 'string') { try { return JSON.parse(rv) } catch { return {} } }
    return rv || {}
  })
  const [decision,  setDecision]   = useState(existing?.reviewer_final_decision || '')
  const [notes,     setNotes]      = useState(existing?.reviewer_notes || '')
  const [saving,    setSaving]     = useState(false)
  const [result,    setResult]     = useState(null)  // 'ok'|'err'
  const [msg,       setMsg]        = useState('')

  const setDim = (dim, field, val) => {
    setOverrides(p => ({ ...p, [dim]: { ...(p[dim] || {}), [field]: val } }))
    setResult(null)
  }

  const handleSave = async () => {
    setSaving(true); setResult(null); setMsg('')
    for (const [dim, ov] of Object.entries(overrides)) {
      if (ov.score && !ov.comment?.trim()) {
        setMsg(`Comment required for ${dim}.`); setResult('err'); setSaving(false); return
      }
    }
    const clean = Object.fromEntries(Object.entries(overrides).filter(([, v]) => v.score))
    try {
      const res = await fetch(`${API_BASE_URL}/api/evaluations/${rowId}/review`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          overrides:      Object.keys(clean).length ? clean : null,
          final_decision: decision || null,
          notes:          notes || null,
        }),
      })
      if (res.ok) { setResult('ok'); setMsg('Review saved.') }
      else { const d = await res.json(); setResult('err'); setMsg(d?.detail || `Error ${res.status}`) }
    } catch (e) { setResult('err'); setMsg(e.message || 'Network error') }
    finally { setSaving(false) }
  }

  const hasExisting = existing?.reviewer_final_decision

  return (
    <div style={{ marginTop: '16px', borderTop: '1px solid var(--border-subtle)', paddingTop: '12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
        <span className="detail-label" style={{ marginBottom: 0 }}>Reviewer override</span>
        {hasExisting && (
          <span className="reviewed-tag reviewed-tag--done">
            {existing.reviewer_final_decision}
          </span>
        )}
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--ink-3)' }}>
          AI scores are never modified
        </span>
      </div>

      <div className="reviewer-dims" style={{ marginBottom: '12px' }}>
        {DIMS.map(({ key, label }) => {
          const dim = label.toLowerCase()
          const ov  = overrides[dim] || {}
          const aiScore = existing?.[key]
          return (
            <div key={key} className="reviewer-dim-row">
              <span className="reviewer-dim-label">{label}</span>
              <select className="reviewer-score-select" value={ov.score || ''}
                onChange={e => setDim(dim, 'score', e.target.value ? parseInt(e.target.value) : null)}>
                <option value="">—</option>
                {[1,2,3,4,5].map(n => (
                  <option key={n} value={n}>{n}{aiScore != null && n === aiScore ? ' (AI)' : ''}</option>
                ))}
              </select>
              <input className="reviewer-comment-input" type="text"
                placeholder={aiScore != null ? `AI: ${aiScore}/5 — comment required to override` : 'Comment (required if score set)'}
                value={ov.comment || ''}
                onChange={e => setDim(dim, 'comment', e.target.value)}
                disabled={!ov.score} />
            </div>
          )
        })}
      </div>

      <div className="reviewer-decision-row" style={{ marginBottom: '10px' }}>
        {['Approve', 'Revise', 'Reject'].map(opt => (
          <button key={opt}
            className={`reviewer-decision-btn${decision === opt ? ' reviewer-decision-btn--active' : ''}`}
            data-dec={opt.toLowerCase()}
            onClick={() => { setDecision(d => d === opt ? '' : opt); setResult(null) }}
            type="button">
            {opt}
          </button>
        ))}
      </div>

      <textarea className="reviewer-notes-textarea" rows={3}
        placeholder="Reviewer notes…"
        value={notes} onChange={e => { setNotes(e.target.value); setResult(null) }}
        style={{ marginBottom: '10px' }} />

      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button className="primary-btn" onClick={handleSave} disabled={saving} type="button"
          style={{ minWidth: 130 }}>
          {saving ? <><span className="spinner" aria-hidden="true" />Saving…</> : 'Save review'}
        </button>
        {result === 'ok' && <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--ok-text)' }}>{msg}</span>}
        {result === 'err' && <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--err-text)' }}>{msg}</span>}
      </div>
    </div>
  )
}

// ── Constants ──────────────────────────────────────────────────────────────────

const STATUS_LABELS = {
  completed: 'Completed',
  failed:    'Failed',
}

const STATUS_FILTERS = ['all', 'completed', 'failed']

const DEFAULT_FILTERS = {
  query:        '',
  statusFilter: 'all',
  dateFrom:     '',
  dateTo:       '',
  sortKey:      'created_at',
  sortDir:      'desc',
}

// ── Helpers ────────────────────────────────────────────────────────────────────

export const fmtDate = (iso) => {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
    })
  } catch { return iso.slice(0, 10) }
}

const deriveScore = (row) => {
  let s = 0
  if (row.title_or_topic)    s += 25
  if (row.main_idea)         s += 25
  if (row.main_problem)      s += 25
  if (row.proposed_solution) s += 25
  return s
}

const deriveRisk = (row) => {
  if (row.truncated) return 'high'
  return deriveScore(row) < 75 ? 'medium' : 'low'
}

// Trigger a browser download from a URL without opening a new tab
const triggerDownload = (url, filename) => {
  const a = document.createElement('a')
  a.href        = url
  a.download    = filename || ''
  a.rel         = 'noopener'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

// ── Sub-components ─────────────────────────────────────────────────────────────

// Real score display (overall_score from DB, 1-5 scale)
const RealScoreDisplay = ({ value }) => {
  if (value == null) return <span className="mono-val" style={{ color: 'var(--ink-3)' }}>—</span>
  const pct = (value / 5) * 100
  return (
    <div className="score-bar-wrap" title={`${value.toFixed(2)} / 5`}>
      <div className="score-bar-track">
        <div
          className={`score-bar-fill ${value >= 4 ? 'score-high' : value >= 3 ? 'score-mid' : 'score-low'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="score-bar-label">{value.toFixed(1)}</span>
    </div>
  )
}

// Score band pill
const BandPill = ({ band }) => {
  if (!band) return <span className="mono-val" style={{ color: 'var(--ink-3)' }}>—</span>
  const DOT = {
    'Recommend':                'dot-connected',
    'Revise and Resubmit':      'dot-checking',
    'Not Recommended':          'dot-disconnected',
    'Insufficient Information': 'dot-checking',
  }
  return (
    <span className="band-pill">
      <span className={`dot ${DOT[band] || 'dot-checking'}`} aria-hidden="true" />
      {band}
    </span>
  )
}

const StatusPill = ({ status }) => (
  <span className={`status-pill status-pill--${status}`}>
    {STATUS_LABELS[status] || status}
  </span>
)

const RiskTag = ({ risk }) => (
  <span className={`risk-tag risk-tag--${risk}`}>
    {risk.charAt(0).toUpperCase() + risk.slice(1)}
  </span>
)

// Download button — small, outline-only, no fill
const DownloadBtn = ({ onClick, children, downloading }) => (
  <button
    className="dl-btn"
    onClick={(e) => { e.stopPropagation(); onClick() }}
    disabled={downloading}
    type="button"
  >
    {downloading
      ? <span className="dl-spinner" aria-hidden="true" />
      : <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="2" strokeLinecap="round"
          strokeLinejoin="round" aria-hidden="true">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="7 10 12 15 17 10"/>
          <line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
    }
    {children}
  </button>
)

// ── Component ──────────────────────────────────────────────────────────────────

export default function History({
  evaluationVersion,
  onNavigateToAnalysis,
  filterState,
  onFilterChange,
}) {
  // ── Data ────────────────────────────────────────────────────────────────────
  const [rows,    setRows]    = useState([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState('')

  // ── Filter state — use persisted parent state if available ─────────────────
  const [filters, setFiltersRaw] = useState(filterState ?? DEFAULT_FILTERS)

  // Keep parent in sync on every filter change
  const setFilters = useCallback((updater) => {
    setFiltersRaw(prev => {
      const next = typeof updater === 'function' ? updater(prev) : updater
      if (onFilterChange) onFilterChange(next)
      return next
    })
  }, [onFilterChange])

  // Sync incoming prop if parent resets it externally
  const prevVersion = useRef(evaluationVersion)
  useEffect(() => {
    if (filterState && prevVersion.current !== evaluationVersion) {
      // Don't overwrite on re-fetch — only sync if prop changes structurally
    }
    prevVersion.current = evaluationVersion
  }, [evaluationVersion, filterState])

  // ── Expand + per-row download state ────────────────────────────────────────
  const [expandedId,   setExpandedId]   = useState(null)
  const [downloading,  setDownloading]  = useState({})  // { [id]: 'pdf'|'json'|null }

  // ── Fetch ───────────────────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false
    setLoading(true); setError('')

    fetch(`${API_BASE_URL}/api/evaluations`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(data => { if (!cancelled) { setRows(data.evaluations || []); setLoading(false) } })
      .catch(err => { if (!cancelled) { setError(err.message || 'Failed to load.'); setLoading(false) } })

    return () => { cancelled = true }
  }, [evaluationVersion])

  // ── Download handlers ────────────────────────────────────────────────────────

  const handleDownloadPdf = (row) => {
    setDownloading(d => ({ ...d, [row.id]: 'pdf' }))
    const base = (row.filename || 'evaluation').replace(/\.pdf$/i, '')
    const safe = base.replace(/[^a-zA-Z0-9-_ ]/g, '_').trim() || 'evaluation'
    triggerDownload(
      `${API_BASE_URL}/api/evaluations/${row.id}/report.pdf`,
      `${safe}-report.pdf`,
    )
    // Clear spinner after a short delay (download is async in browser)
    setTimeout(() => setDownloading(d => ({ ...d, [row.id]: null })), 1500)
  }

  const handleExportJson = (row) => {
    setDownloading(d => ({ ...d, [row.id]: 'json' }))
    const base = (row.filename || 'evaluation').replace(/\.pdf$/i, '')
    const safe = base.replace(/[^a-zA-Z0-9-_ ]/g, '_').trim() || 'evaluation'
    triggerDownload(
      `${API_BASE_URL}/api/evaluations/${row.id}/export.json`,
      `${safe}-evaluation.json`,
    )
    setTimeout(() => setDownloading(d => ({ ...d, [row.id]: null })), 1500)
  }

  // ── Sort toggle ──────────────────────────────────────────────────────────────
  const toggleSort = (key) => {
    setFilters(f => ({
      ...f,
      sortKey: key,
      sortDir: f.sortKey === key ? (f.sortDir === 'asc' ? 'desc' : 'asc') : 'desc',
    }))
  }

  // ── Filtered + sorted rows ───────────────────────────────────────────────────
  const { query, statusFilter, dateFrom, dateTo, sortKey, sortDir } = filters

  const filtered = useMemo(() => {
    let data = rows.map(r => ({
      ...r,
      // Keep _score/_risk for backward compat with any remaining refs,
      // but use real DB columns where available
      _overall: r.overall_score,
      _band:    r.score_band,
      _reviewed: !!r.reviewer_final_decision,
    }))

    // Status filter
    if (statusFilter !== 'all')
      data = data.filter(r => r.status === statusFilter)

    // Text search — filename, title, model, ID
    if (query.trim()) {
      const q = query.toLowerCase()
      data = data.filter(r =>
        (r.filename       || '').toLowerCase().includes(q) ||
        (r.title_or_topic || '').toLowerCase().includes(q) ||
        (r.model_used     || '').toLowerCase().includes(q) ||
        (r.id             || '').toLowerCase().includes(q)
      )
    }

    // Date range filter — compare ISO date strings (YYYY-MM-DD prefix is enough)
    if (dateFrom) {
      data = data.filter(r => r.created_at && r.created_at.slice(0, 10) >= dateFrom)
    }
    if (dateTo) {
      data = data.filter(r => r.created_at && r.created_at.slice(0, 10) <= dateTo)
    }

    // Sort
    data.sort((a, b) => {
      let av = a[sortKey] ?? '', bv = b[sortKey] ?? ''
      if (typeof av === 'string') { av = av.toLowerCase(); bv = bv.toLowerCase() }
      if (av < bv) return sortDir === 'asc' ? -1 : 1
      if (av > bv) return sortDir === 'asc' ? 1 : -1
      return 0
    })

    return data
  }, [rows, query, statusFilter, dateFrom, dateTo, sortKey, sortDir])

  // ── Active filter count (for "clear all" badge) ────────────────────────────
  const activeFilterCount = [
    query, statusFilter !== 'all' ? statusFilter : '', dateFrom, dateTo,
  ].filter(Boolean).length

  const clearAll = () => setFilters(DEFAULT_FILTERS)

  const SortIndicator = ({ col }) => (
    <span className="sort-indicator" aria-hidden="true">
      {sortKey === col ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ' ↕'}
    </span>
  )

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="view-shell">

      {/* View header */}
      <div className="view-header">
        <div>
          <h1 className="view-title">History &amp; Archive</h1>
          <p className="view-subtitle">
            {loading
              ? 'Loading…'
              : `${rows.length} evaluation${rows.length !== 1 ? 's' : ''} · SQLite`}
          </p>
        </div>
        <button className="primary-btn" onClick={onNavigateToAnalysis}>+ New analysis</button>
      </div>

      {/* Fetch error */}
      {error && (
        <div className="alert-banner error" role="alert">
          <div className="alert-body">
            <strong className="alert-title">Could not load evaluations</strong>
            <p className="alert-text">{error}</p>
          </div>
        </div>
      )}

      {/* ── Toolbar ── */}
      {!error && (
        <div className="toolbar-block">

          {/* Row 1: search + status filters + result count */}
          <div className="toolbar">
            <div className="toolbar-search">
              <svg className="toolbar-search-icon" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="2" strokeLinecap="round"
                strokeLinejoin="round" aria-hidden="true">
                <circle cx="11" cy="11" r="8"/>
                <line x1="21" y1="21" x2="16.65" y2="16.65"/>
              </svg>
              <input
                className="toolbar-input"
                type="search"
                placeholder="Search filename, title, model, ID…"
                value={query}
                onChange={e => setFilters(f => ({ ...f, query: e.target.value }))}
                aria-label="Search evaluations"
              />
              {query && (
                <button className="toolbar-clear"
                  onClick={() => setFilters(f => ({ ...f, query: '' }))}
                  aria-label="Clear search">×</button>
              )}
            </div>

            <div className="toolbar-filters" role="group" aria-label="Filter by status">
              {STATUS_FILTERS.map(f => (
                <button key={f}
                  className={`filter-btn${statusFilter === f ? ' filter-btn--active' : ''}`}
                  onClick={() => setFilters(s => ({ ...s, statusFilter: f }))}>
                  {f === 'all' ? 'All' : STATUS_LABELS[f] || f}
                </button>
              ))}
            </div>

            <span className="toolbar-count">
              {filtered.length} result{filtered.length !== 1 ? 's' : ''}
            </span>

            {activeFilterCount > 0 && (
              <button className="filter-btn" onClick={clearAll} style={{ marginLeft: 'auto' }}>
                Clear filters ({activeFilterCount})
              </button>
            )}
          </div>

          {/* Row 2: date range */}
          <div className="toolbar toolbar--date-row">
            <span className="section-label" style={{ whiteSpace: 'nowrap' }}>Date range</span>

            <div className="date-range-group">
              <label className="date-label" htmlFor="date-from">From</label>
              <input
                id="date-from"
                className="date-input"
                type="date"
                value={dateFrom}
                max={dateTo || undefined}
                onChange={e => setFilters(f => ({ ...f, dateFrom: e.target.value }))}
                aria-label="Filter from date"
              />
            </div>

            <div className="date-range-group">
              <label className="date-label" htmlFor="date-to">To</label>
              <input
                id="date-to"
                className="date-input"
                type="date"
                value={dateTo}
                min={dateFrom || undefined}
                onChange={e => setFilters(f => ({ ...f, dateTo: e.target.value }))}
                aria-label="Filter to date"
              />
            </div>

            {(dateFrom || dateTo) && (
              <button className="filter-btn"
                onClick={() => setFilters(f => ({ ...f, dateFrom: '', dateTo: '' }))}>
                Clear dates
              </button>
            )}
          </div>

        </div>
      )}

      {/* ── Table ── */}
      {!error && (
        <div className="table-container">
          <table className="data-table" aria-label="Evaluation history">
            <thead>
              <tr>
                <th className="col-id">
                  <button className="th-btn" onClick={() => toggleSort('id')}>
                    ID <SortIndicator col="id" />
                  </button>
                </th>
                <th className="col-title">
                  <button className="th-btn" onClick={() => toggleSort('title_or_topic')}>
                    Title <SortIndicator col="title_or_topic" />
                  </button>
                </th>
                <th className="col-dept">
                  <button className="th-btn" onClick={() => toggleSort('model_used')}>
                    Model <SortIndicator col="model_used" />
                  </button>
                </th>
                <th className="col-budget">
                  <button className="th-btn" onClick={() => toggleSort('char_count')}>
                    Chars <SortIndicator col="char_count" />
                  </button>
                </th>
                <th className="col-score">
                  <button className="th-btn" onClick={() => toggleSort('overall_score')}>
                    Score <SortIndicator col="overall_score" />
                  </button>
                </th>
                <th className="col-dept" style={{ minWidth: 140 }}>
                  <button className="th-btn" onClick={() => toggleSort('score_band')}>
                    Band <SortIndicator col="score_band" />
                  </button>
                </th>
                <th className="col-risk">Reviewed</th>
                <th className="col-status">Status</th>
                <th className="col-date">
                  <button className="th-btn" onClick={() => toggleSort('created_at')}>
                    Date <SortIndicator col="created_at" />
                  </button>
                </th>
                {/* Actions column — wider to fit two buttons */}
                <th className="col-actions">Actions</th>
              </tr>
            </thead>

            <tbody>
              {loading && (
                <tr><td colSpan="10" className="table-empty">Loading evaluations…</td></tr>
              )}
              {!loading && filtered.length === 0 && (
                <tr>
                  <td colSpan="10" className="table-empty">
                    {rows.length === 0
                      ? 'No evaluations yet. Run an analysis to see results here.'
                      : 'No evaluations match the current filters.'}
                  </td>
                </tr>
              )}
              {!loading && filtered.map(row => (
                <>
                  <tr
                    key={row.id}
                    className={`data-row${expandedId === row.id ? ' data-row--expanded' : ''}`}
                    onClick={() => setExpandedId(expandedId === row.id ? null : row.id)}
                    style={{ cursor: 'pointer' }}
                    aria-expanded={expandedId === row.id}
                  >
                    <td>
                      <span className="mono-id" title={row.id}>{row.id.slice(0, 8)}…</span>
                    </td>
                    <td className="col-title">
                      <span className="row-title">
                        {row.title_or_topic && 
                         !row.title_or_topic.startsWith('Not stated') && 
                         !row.title_or_topic.startsWith('Analysis parsing')
                          ? row.title_or_topic
                          : row.filename}
                      </span>
                      <span className="row-pi">{row.filename}</span>
                    </td>
                    <td><span className="dept-tag">{row.model_used || '—'}</span></td>
                    <td><span className="mono-val">{(row.char_count || 0).toLocaleString()}</span></td>
                    <td><RealScoreDisplay value={row.overall_score} /></td>
                    <td><BandPill band={row.score_band} /></td>
                    <td>
                      <span className={`reviewed-tag ${row._reviewed ? 'reviewed-tag--done' : 'reviewed-tag--pending'}`}>
                        {row._reviewed ? 'Reviewed' : 'Pending'}
                      </span>
                    </td>
                    <td><StatusPill status={row.status || 'completed'} /></td>
                    <td><span className="mono-val">{fmtDate(row.created_at)}</span></td>

                    {/* Actions cell — stop propagation so clicks don't toggle expand */}
                    <td className="col-actions" onClick={e => e.stopPropagation()}>
                      <div className="row-actions">
                        <DownloadBtn
                          onClick={() => handleDownloadPdf(row)}
                          downloading={downloading[row.id] === 'pdf'}
                        >
                          PDF
                        </DownloadBtn>
                        <DownloadBtn
                          onClick={() => handleExportJson(row)}
                          downloading={downloading[row.id] === 'json'}
                        >
                          JSON
                        </DownloadBtn>
                      </div>
                    </td>
                  </tr>

                  {/* Inline expanded detail row */}
                  {expandedId === row.id && (
                    <tr key={`${row.id}-detail`} className="detail-row">
                      <td colSpan="10">
                        <div className="detail-panel">
                          <div className="detail-grid">
                            <div className="detail-cell">
                              <span className="detail-label">Record ID</span>
                              <span className="detail-val mono-val"
                                style={{ fontSize: '0.72rem' }}>{row.id}</span>
                            </div>
                            <div className="detail-cell">
                              <span className="detail-label">Pages</span>
                              <span className="detail-val mono-val">{row.page_count ?? '—'}</span>
                            </div>
                            <div className="detail-cell">
                              <span className="detail-label">Truncated</span>
                              <span className="detail-val mono-val">{row.truncated ? 'yes' : 'no'}</span>
                            </div>
                            <div className="detail-cell">
                              <span className="detail-label">Saved at</span>
                              <span className="detail-val mono-val" style={{ fontSize: '0.75rem' }}>
                                {row.created_at?.slice(0, 19).replace('T', ' ')} UTC
                              </span>
                            </div>
                          </div>

                          {/* LLM fields */}
                          {[
                            { label: 'Main idea',         text: row.main_idea },
                            { label: 'Main problem',      text: row.main_problem },
                            { label: 'Proposed solution', text: row.proposed_solution },
                          ].filter(s => s.text).map(s => (
                            <div key={s.label} className="detail-summary" style={{ marginTop: '8px' }}>
                              <span className="detail-label">{s.label}</span>
                              <p className="detail-summary-text">{s.text}</p>
                            </div>
                          ))}

                          {/* Coordinator summary — shown when present */}
                          {row.coordinator_summary && (() => {
                            const coord = typeof row.coordinator_summary === 'string'
                              ? (() => { try { return JSON.parse(row.coordinator_summary) } catch { return null } })()
                              : row.coordinator_summary

                            if (!coord) return null

                            const recConf = {
                              'Recommend':                { dot: 'dot-connected',    label: 'Recommend' },
                              'Revise and Resubmit':      { dot: 'dot-checking',     label: 'Revise and Resubmit' },
                              'Not Recommended':          { dot: 'dot-disconnected', label: 'Not Recommended' },
                              'Insufficient Information': { dot: 'dot-checking',     label: 'Insufficient Information' },
                            }[coord.preliminary_recommendation] || { dot: 'dot-checking', label: coord.preliminary_recommendation || '—' }

                            return (
                              <div style={{ marginTop: '16px', borderTop: '1px solid var(--border-subtle)', paddingTop: '12px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '10px' }}>
                                  <span className="detail-label" style={{ marginBottom: 0 }}>Coordinator synthesis</span>
                                  <span style={{ display: 'flex', alignItems: 'center', gap: '5px',
                                    fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--ink-2)' }}>
                                    <span className={`dot ${recConf.dot}`} aria-hidden="true" />
                                    {recConf.label}
                                  </span>
                                  {coord.coordinator_confidence && (
                                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--ink-3)' }}>
                                      · {coord.coordinator_confidence} confidence
                                    </span>
                                  )}
                                </div>

                                {coord.overall_summary && (
                                  <div className="detail-summary" style={{ marginBottom: '8px' }}>
                                    <span className="detail-label">Summary</span>
                                    <p className="detail-summary-text">{coord.overall_summary}</p>
                                  </div>
                                )}

                                {coord.recommendation_reasoning && (
                                  <div className="detail-summary" style={{ marginBottom: '8px' }}>
                                    <span className="detail-label">Reasoning</span>
                                    <p className="detail-summary-text">{coord.recommendation_reasoning}</p>
                                  </div>
                                )}

                                {coord.key_strengths?.length > 0 && (
                                  <div className="detail-summary" style={{ marginBottom: '8px' }}>
                                    <span className="detail-label">Key strengths</span>
                                    <ul className="coord-list" style={{ marginTop: '4px' }}>
                                      {coord.key_strengths.map((s, i) => (
                                        <li key={i} className="coord-list-item">
                                          <span className="coord-item-text">{s.point}</span>
                                          <span className="coord-agent-tag">{s.supported_by_agent}</span>
                                        </li>
                                      ))}
                                    </ul>
                                  </div>
                                )}

                                {coord.key_risks?.length > 0 && (
                                  <div className="detail-summary" style={{ marginBottom: '8px' }}>
                                    <span className="detail-label">Key risks</span>
                                    <ul className="coord-list" style={{ marginTop: '4px' }}>
                                      {coord.key_risks.map((r, i) => (
                                        <li key={i} className="coord-list-item">
                                          <span className="coord-severity-tag" data-sev={r.severity?.toLowerCase()}>
                                            {r.severity}
                                          </span>
                                          <span className="coord-item-text">{r.point}</span>
                                          <span className="coord-agent-tag">{r.supported_by_agent}</span>
                                        </li>
                                      ))}
                                    </ul>
                                  </div>
                                )}

                                {coord.questions_for_human_reviewer?.length > 0 && (
                                  <div className="detail-summary">
                                    <span className="detail-label">Questions for reviewer</span>
                                    <ul className="coord-list" style={{ marginTop: '4px' }}>
                                      {coord.questions_for_human_reviewer.map((q, i) => (
                                        <li key={i} className="coord-list-item">
                                          <span className="coord-item-text">{q}</span>
                                        </li>
                                      ))}
                                    </ul>
                                  </div>
                                )}

                                <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem',
                                  color: 'var(--ink-3)', marginTop: '10px', lineHeight: '1.4' }}>
                                  AI-generated preliminary evaluation. Human reviewer decides.
                                </p>
                              </div>
                            )
                          })()}

                          {/* Download links in the expanded panel too */}
                          <div className="detail-actions">
                            <DownloadBtn
                              onClick={() => handleDownloadPdf(row)}
                              downloading={downloading[row.id] === 'pdf'}
                            >
                              Download PDF report
                            </DownloadBtn>
                            <DownloadBtn
                              onClick={() => handleExportJson(row)}
                              downloading={downloading[row.id] === 'json'}
                            >
                              Export JSON
                            </DownloadBtn>
                          </div>

                          {/* ── Inline reviewer form ── */}
                          <HistoryReviewerForm rowId={row.id} existing={row} />
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
