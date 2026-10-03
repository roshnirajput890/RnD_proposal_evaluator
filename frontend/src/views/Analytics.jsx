/**
 * Analytics.jsx — Portfolio overview dashboard.
 *
 * Fetches real aggregate data from GET /api/analytics.
 * Re-fetches when evaluationVersion changes (same trigger as History).
 * Shows an empty-state panel when no evaluations have been saved yet.
 *
 * Props:
 *   evaluationVersion — int; increment triggers a re-fetch
 */
import { useState, useEffect } from 'react'
import { API_BASE_URL } from '../config'

// ── Helpers ────────────────────────────────────────────────────────────────────

const fmtBudget = (n) => {
  if (!n) return '—'
  if (n >= 1_000_000) return `£${(n / 1_000_000).toFixed(2)}M`
  return `£${(n / 1_000).toFixed(0)}k`
}

// ── Sub-components ─────────────────────────────────────────────────────────────

const KpiCard = ({ label, value, sub, accent }) => (
  <div className={`metric-card${accent ? ' metric-card--accent' : ''}`}>
    <span className="metric-label">{label}</span>
    <span className="metric-value">{value ?? '—'}</span>
    {sub && <span className="metric-sub">{sub}</span>}
  </div>
)

const HBar = ({ label, value, max, cls }) => (
  <div className="hbar-row">
    <span className="hbar-label">{label}</span>
    <div className="hbar-track">
      <div className={`hbar-fill ${cls || ''}`}
        style={{ width: max > 0 ? `${(value / max) * 100}%` : '0%' }} />
    </div>
    <span className="hbar-count">{value}</span>
  </div>
)

// ── Empty state ────────────────────────────────────────────────────────────────

const EmptyState = () => (
  <div className="analytics-panel" style={{ marginTop: 0 }}>
    <div className="panel-body" style={{ padding: '48px 24px', textAlign: 'center' }}>
      <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem', color: 'var(--ink-3)' }}>
        No evaluations saved yet.
      </p>
      <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--ink-3)', marginTop: '6px' }}>
        Run an analysis from the New Analysis page to populate this dashboard.
      </p>
    </div>
  </div>
)

// ── Component ──────────────────────────────────────────────────────────────────

export default function Analytics({ evaluationVersion }) {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true); setError('')

    fetch(`${API_BASE_URL}/api/analytics`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(d => { if (!cancelled) { setData(d); setLoading(false) } })
      .catch(err => { if (!cancelled) { setError(err.message || 'Failed to load analytics.'); setLoading(false) } })

    return () => { cancelled = true }
  }, [evaluationVersion])

  // ── Render ─────────────────────────────────────────────────────────────────

  const isEmpty = !loading && !error && data?.totals?.proposals === 0

  const subtitle = loading        ? 'Loading…'
                 : error          ? 'Error loading data'
                 : isEmpty        ? 'No evaluations yet'
                 : `${data.totals.proposals} evaluation${data.totals.proposals !== 1 ? 's' : ''} · SQLite`

  return (
    <div className="view-shell">

      <div className="view-header">
        <div>
          <h1 className="view-title">Portfolio Analytics</h1>
          <p className="view-subtitle">{subtitle}</p>
        </div>
      </div>

      {error && (
        <div className="alert-banner error" role="alert">
          <div className="alert-body">
            <strong className="alert-title">Could not load analytics</strong>
            <p className="alert-text">{error}</p>
          </div>
        </div>
      )}

      {loading && !error && (
        <div className="loading-bar" role="status">
          <div className="loading-spinner-ring" aria-hidden="true"></div>
          <div className="loading-text-group">
            <p className="loading-heading">Loading analytics</p>
            <p className="loading-subheading">querying SQLite</p>
          </div>
        </div>
      )}

      {isEmpty && <EmptyState />}

      {!loading && !error && !isEmpty && data && (() => {
        const { totals, scores, risk_breakdown, score_distribution,
                monthly_volume, by_model, top_evaluations,
                recommendation_breakdown } = data

        const completedRate = totals.proposals > 0
          ? Math.round((totals.completed / totals.proposals) * 100) : 0

        const maxDist = Math.max(...score_distribution.map(d => d.count), 1)
        const maxVol  = Math.max(...(monthly_volume || []).map(m => m.count), 1)
        const maxModel= Math.max(...(by_model || []).map(m => m.count), 1)

        return (
          <>
            {/* ── KPI row ── */}
            <section aria-label="Key performance indicators">
              <span className="section-label" style={{ display: 'block', marginBottom: '12px' }}>Overview</span>
              <div className="metrics-grid">
                <KpiCard label="Total evaluations" value={totals.proposals} />
                <KpiCard label="Completed"         value={totals.completed} sub={`${completedRate}% completion rate`} accent />
                <KpiCard label="Avg output score"  value={scores.avg_overall}
                         sub={`High: ${scores.highest} · Low: ${scores.lowest}`} />
                <KpiCard label="Truncated input"   value={risk_breakdown.high}
                         sub="input exceeded limit" />
              </div>
            </section>

            {/* ── Score dist + risk ── */}
            <div className="analytics-cols">

              <section className="analytics-panel" aria-label="Score distribution">
                <div className="panel-header"><span className="panel-title">Output score distribution</span></div>
                <div className="panel-body">
                  {score_distribution.map(({ label, count }) => (
                    <HBar key={label} label={label} value={count} max={maxDist}
                      cls={label.startsWith('9') ? 'hbar-fill--high' : label.startsWith('8') ? 'hbar-fill--mid' : 'hbar-fill--low'} />
                  ))}
                </div>
              </section>

              <section className="analytics-panel" aria-label="Risk classification">
                <div className="panel-header"><span className="panel-title">Input quality classification</span></div>
                <div className="panel-body">
                  <HBar label="Low risk"    value={risk_breakdown.low}    max={totals.proposals} cls="hbar-fill--high" />
                  <HBar label="Medium risk" value={risk_breakdown.medium} max={totals.proposals} cls="hbar-fill--mid" />
                  <HBar label="High risk"   value={risk_breakdown.high}   max={totals.proposals} cls="hbar-fill--low" />

                  <div className="risk-pct-row">
                    {[
                      { label: 'Low',    val: risk_breakdown.low,    cls: 'risk-pct--low'  },
                      { label: 'Medium', val: risk_breakdown.medium, cls: 'risk-pct--mid'  },
                      { label: 'High',   val: risk_breakdown.high,   cls: 'risk-pct--high' },
                    ].map(({ label, val, cls }) => (
                      <div key={label} className={`risk-pct-cell ${cls}`}>
                        <span className="risk-pct-num">
                          {totals.proposals > 0 ? Math.round((val / totals.proposals) * 100) : 0}%
                        </span>
                        <span className="risk-pct-label">{label}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </section>

            </div>

            {/* ── Monthly volume ── */}
            {monthly_volume?.length > 0 && (
              <section className="analytics-panel" aria-label="Monthly volume">
                <div className="panel-header"><span className="panel-title">Monthly evaluation volume</span></div>
                <div className="panel-body vol-bars">
                  {monthly_volume.map(({ month, count }) => (
                    <div key={month} className="vol-col">
                      <span className="vol-count">{count}</span>
                      <div className="vol-bar-track">
                        <div className="vol-bar-fill" style={{ height: `${(count / maxVol) * 100}%` }} />
                      </div>
                      <span className="vol-label">{month}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* ── By model ── */}
            {by_model?.length > 0 && (
              <section className="analytics-panel" aria-label="Evaluations by model">
                <div className="panel-header"><span className="panel-title">Evaluations by model</span></div>
                <div className="panel-body">
                  {by_model.map(({ model, count }) => (
                    <HBar key={model} label={model} value={count} max={maxModel} cls="hbar-fill--mid" />
                  ))}
                </div>
              </section>
            )}

            {/* ── Top evaluations ── */}
            {top_evaluations?.length > 0 && (
              <section className="analytics-panel" aria-label="Top scored evaluations">
                <div className="panel-header">
                  <span className="panel-title">Top evaluations by output score</span>
                </div>
                <div className="panel-body" style={{ padding: 0 }}>
                  {top_evaluations.map((e, i) => (
                    <div key={e.id} className="top-row">
                      <span className="top-rank">0{i + 1}</span>
                      <div className="top-info">
                        <span className="row-title">{e.title_or_topic || e.filename}</span>
                        <span className="row-pi">{e.filename} · {e.created_at?.slice(0, 10)}</span>
                      </div>
                      <div className="top-score-group">
                        <span className={`top-score mono-val ${e.score >= 75 ? 'score-text--high' : 'score-text--mid'}`}>
                          {e.score}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* ── Coordinator recommendation breakdown ── */}
            {recommendation_breakdown?.length > 0 && (() => {
              // Config: map recommendation string → dot class
              const REC_DOT = {
                'Recommend':                'dot-connected',
                'Revise and Resubmit':      'dot-checking',
                'Not Recommended':          'dot-disconnected',
                'Insufficient Information': 'dot-checking',
                'Not evaluated':            '',
              }
              const maxRec = Math.max(...recommendation_breakdown.map(r => r.count), 1)
              return (
                <section className="analytics-panel" aria-label="Coordinator recommendations">
                  <div className="panel-header">
                    <span className="panel-title">Coordinator preliminary recommendations</span>
                    <span className="panel-title-sub">from saved evaluations with coordinator output</span>
                  </div>
                  <div className="panel-body">
                    {recommendation_breakdown.map(({ recommendation, count }) => (
                      <div key={recommendation} className="hbar-row">
                        <span className="hbar-label" style={{ display:'flex', alignItems:'center', gap:'6px', minWidth:'180px' }}>
                          {REC_DOT[recommendation] && (
                            <span className={`dot ${REC_DOT[recommendation]}`} aria-hidden="true" />
                          )}
                          {recommendation}
                        </span>
                        <div className="hbar-track">
                          <div className="hbar-fill hbar-fill--mid"
                            style={{ width: `${(count / maxRec) * 100}%` }} />
                        </div>
                        <span className="hbar-count">{count}</span>
                      </div>
                    ))}
                    <p style={{ fontFamily:'var(--font-mono)', fontSize:'0.68rem',
                      color:'var(--ink-3)', marginTop:'10px', lineHeight:'1.4' }}>
                      Preliminary only. Human reviewer makes the final decision.
                    </p>
                  </div>
                </section>
              )
            })()}

          </>
        )
      })()}

    </div>
  )
}
