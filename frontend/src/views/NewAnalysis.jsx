/**
 * NewAnalysis.jsx — Brick 8
 *
 * Flow:
 *   1. POST /api/analyze  → general_analysis + scoring + coordinator
 *   2. POST /api/evaluations → persist (includes scoring fields)
 *   3. onAnalysisComplete() → bumps evaluationVersion
 *
 * New in Brick 8:
 *   - ScoreBreakdown panel (horizontal bars per dimension + overall)
 *   - "How is this calculated?" collapsible explanation
 *   - Agent score display on each analysis card ("Novelty  3 / 5")
 *   - ReviewerPanel below coordinator summary
 */
import { useState, useRef } from 'react'
import { API_BASE_URL } from '../config'

// ── Recommendation config (dot class → existing CSS dots) ─────────────────────
const REC_CONFIG = {
  'Recommend':                { dot: 'dot-connected',    label: 'Recommend' },
  'Revise and Resubmit':      { dot: 'dot-checking',     label: 'Revise and Resubmit' },
  'Not Recommended':          { dot: 'dot-disconnected', label: 'Not Recommended' },
  'Insufficient Information': { dot: 'dot-checking',     label: 'Insufficient Information' },
}

const CONFIDENCE_CLS = { High: 'status-ok', Medium: 'status-warn', Low: 'status-err' }

// Dimension labels / weights — kept in sync with scoring.py (display only)
const DIMS = [
  { key: 'novelty_score',   label: 'Novelty',     weight: 25 },
  { key: 'technical_score', label: 'Technical',   weight: 30 },
  { key: 'financial_score', label: 'Financial',   weight: 20 },
  { key: 'impact_score',    label: 'Impact',      weight: 25 },
]

// ── DemoBadge component ────────────────────────────────────────────────────────

function DemoBadge() {
  return (
    <div style={{
      display: 'inline-block',
      background: '#e0f2fe',
      border: '1px solid #0284c7',
      color: '#0c4a6e',
      padding: '4px 10px',
      borderRadius: '4px',
      fontSize: '0.75rem',
      fontFamily: 'var(--font-mono)',
      fontWeight: 600,
      marginRight: '8px',
    }}>
      Demo result — precomputed
    </div>
  )
}

// ── ScoreBreakdown ─────────────────────────────────────────────────────────────

function ScoreBreakdown({ scoring }) {
  const [showCalc, setShowCalc] = useState(false)
  if (!scoring) return null

  const { overall_score, score_band, is_partial, active_weights } = scoring

  const bandConf = REC_CONFIG[score_band] || REC_CONFIG['Insufficient Information']

  return (
    <div className="analysis-section score-breakdown-section">
      <div className="analysis-section-header">
        <span className="analysis-section-title">Score breakdown</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {overall_score != null && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem',
              fontWeight: 600, color: 'var(--ink)', fontVariantNumeric: 'tabular-nums' }}>
              {overall_score.toFixed(2)} / 5.00
            </span>
          )}
          <span style={{ display: 'flex', alignItems: 'center', gap: '5px',
            fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--ink-2)' }}>
            <span className={`dot ${bandConf.dot}`} aria-hidden="true" />
            {score_band || '—'}
          </span>
          {is_partial && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem',
              color: 'var(--warn-text)', background: 'var(--warn-bg)',
              border: '1px solid var(--warn-dot)', padding: '1px 6px',
              borderRadius: 'var(--radius-sm)' }}>
              partial score
            </span>
          )}
        </div>
      </div>

      <div className="analysis-card" style={{ borderBottom: 'none' }}>
        {/* Per-dimension bars */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '12px' }}>
          {DIMS.map(({ key, label, weight }) => {
            const val = scoring[key]
            const aw  = active_weights?.[label.toLowerCase()]
            const pct = val != null ? (val / 5) * 100 : 0
            return (
              <div key={key} className="score-dim-row">
                <span className="score-dim-label">{label}</span>
                <div className="score-dim-track">
                  {val != null
                    ? <div className="score-dim-fill" style={{ width: `${pct}%` }} />
                    : <div className="score-dim-fill score-dim-null" style={{ width: '100%' }} />
                  }
                </div>
                <span className="score-dim-val">
                  {val != null ? `${val} / 5` : 'n/a'}
                </span>
                <span className="score-dim-weight">
                  {aw != null ? `${(aw * 100).toFixed(0)}%` : `${weight}%`}
                  {aw != null && Math.abs(aw * 100 - weight) > 0.5 ? '*' : ''}
                </span>
              </div>
            )
          })}
        </div>

        {/* How is this calculated? */}
        <button
          className="calc-toggle"
          onClick={() => setShowCalc(s => !s)}
          aria-expanded={showCalc}
        >
          {showCalc ? '▲ Hide calculation' : '▼ How is this calculated?'}
        </button>

        {showCalc && (
          <div className="calc-explanation">
            <p>The overall score is a weighted average of four dimension scores (each 1–5):</p>
            <ul>
              {DIMS.map(d => (
                <li key={d.key}>
                  <strong>{d.label}</strong> — {d.weight}% weight
                  {d.key === 'novelty_score' ? ' (assessed by general analysis agent)' : ' (not yet assessed — future agent)'}
                </li>
              ))}
            </ul>
            <p>
              If a dimension score is unavailable (agent failed or returned an invalid value),
              that dimension is excluded and the remaining weights are proportionally rescaled
              to still sum to 100%. The result is marked "partial".
            </p>
            <p>
              <strong>Score bands:</strong> ≥ 4.0 → Recommend · 3.0–3.9 → Revise and Resubmit ·
              &lt; 3.0 → Not Recommended · 2+ dimensions missing → Insufficient Information.
            </p>
            <p style={{ fontStyle: 'italic' }}>
              The LLM provides dimension scores; this arithmetic is computed by the backend in pure Python —
              the model never does the maths.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

// ── CoordinatorPanel ───────────────────────────────────────────────────────────

function CoordinatorPanel({ coordinator, coordinatorError, novelty }) {
  const [open, setOpen] = useState(true)

  if (coordinatorError && !coordinator) {
    return (
      <div className="analysis-section">
        <div className="analysis-section-header">
          <span className="analysis-section-title">Coordinator synthesis</span>
          <span className="analysis-model-tag">failed</span>
        </div>
        <div className="alert-banner error" role="alert"
          style={{ margin: 0, borderLeft: 'none', borderRight: 'none', borderTop: 'none', borderRadius: 0 }}>
          <div className="alert-body">
            <strong className="alert-title">Coordinator did not complete</strong>
            <p className="alert-text">{coordinatorError}</p>
          </div>
        </div>
      </div>
    )
  }

  if (!coordinator) return null

  const recConf = REC_CONFIG[coordinator.preliminary_recommendation] || REC_CONFIG['Insufficient Information']
  const confCls = CONFIDENCE_CLS[coordinator.coordinator_confidence] || 'status-muted'

  // Determine novelty disclaimer based on whether external papers were used
  const hasExternalEvidence = novelty?.external_evidence_used === true && novelty?.score != null
  const noveltyDisclaimer = hasExternalEvidence
    ? "Novelty assessment uses a limited automated search (OpenAlex, top 3 papers). It is not an exhaustive literature review."
    : "Novelty assessment has no external literature evidence in this version."

  return (
    <div className="analysis-section coord-section">
      <div className="analysis-section-header" style={{ cursor: 'pointer' }}
        onClick={() => setOpen(o => !o)}>
        <span className="analysis-section-title">Coordinator synthesis</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '6px',
            fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--ink-2)' }}>
            <span className={`dot ${recConf.dot}`} aria-hidden="true" />
            {recConf.label}
          </span>
          <span className={`status-cell-value ${confCls}`}
            style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem' }}>
            {coordinator.coordinator_confidence} confidence
          </span>
          <span className="analysis-model-tag">{open ? '▲ collapse' : '▼ expand'}</span>
        </div>
      </div>

      <div style={{ padding: '8px 20px', background: 'var(--surface)',
        borderBottom: '1px solid var(--border-subtle)',
        fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--ink-3)', lineHeight: 1.5 }}>
        AI-generated preliminary evaluation. A human reviewer makes the final decision.
        {noveltyDisclaimer}
      </div>

      {open && (
        <div className="analysis-cards">
          <div className="analysis-card">
            <div className="analysis-card-label"><span className="card-index">C1</span>Overall Summary</div>
            <p className="analysis-card-text">{coordinator.overall_summary || '—'}</p>
          </div>
          <div className="analysis-card">
            <div className="analysis-card-label"><span className="card-index">C2</span>Recommendation · Reasoning</div>
            <p className="analysis-card-text">{coordinator.recommendation_reasoning || '—'}</p>
          </div>

          {coordinator.key_strengths?.length > 0 && (
            <div className="analysis-card">
              <div className="analysis-card-label"><span className="card-index">C3</span>Key Strengths</div>
              <ul className="coord-list">
                {coordinator.key_strengths.map((s, i) => (
                  <li key={i} className="coord-list-item">
                    <span className="coord-item-text">{s.point}</span>
                    <span className="coord-agent-tag">{s.supported_by_agent}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {coordinator.key_risks?.length > 0 && (
            <div className="analysis-card">
              <div className="analysis-card-label"><span className="card-index">C4</span>Key Risks</div>
              <ul className="coord-list">
                {coordinator.key_risks.map((r, i) => (
                  <li key={i} className="coord-list-item">
                    <span className="coord-severity-tag" data-sev={r.severity?.toLowerCase()}>{r.severity}</span>
                    <span className="coord-item-text">{r.point}</span>
                    <span className="coord-agent-tag">{r.supported_by_agent}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {(coordinator.critical_missing_information?.length > 0 ||
            coordinator.questions_for_human_reviewer?.length > 0) && (
            <div className="analysis-card coord-two-col">
              {coordinator.critical_missing_information?.length > 0 && (
                <div className="coord-col">
                  <div className="analysis-card-label" style={{ marginBottom: 8 }}>
                    <span className="card-index">C5</span>Critical Missing Information
                  </div>
                  <ul className="coord-list">
                    {coordinator.critical_missing_information.map((m, i) => (
                      <li key={i} className="coord-list-item"><span className="coord-item-text">{m}</span></li>
                    ))}
                  </ul>
                </div>
              )}
              {coordinator.questions_for_human_reviewer?.length > 0 && (
                <div className="coord-col">
                  <div className="analysis-card-label" style={{ marginBottom: 8 }}>
                    <span className="card-index">C6</span>Questions for Reviewer
                  </div>
                  <ul className="coord-list">
                    {coordinator.questions_for_human_reviewer.map((q, i) => (
                      <li key={i} className="coord-list-item"><span className="coord-item-text">{q}</span></li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── ReviewerPanel ──────────────────────────────────────────────────────────────

function ReviewerPanel({ savedId, existingReview }) {
  const [overrides,   setOverrides]   = useState(existingReview?.overrides || {})
  const [decision,    setDecision]    = useState(existingReview?.final_decision || '')
  const [notes,       setNotes]       = useState(existingReview?.notes || '')
  const [saving,      setSaving]      = useState(false)
  const [saveResult,  setSaveResult]  = useState(null)  // 'ok' | 'err' | null
  const [saveMsg,     setSaveMsg]     = useState('')

  if (!savedId) return null

  const setOverrideDim = (dim, field, value) => {
    setOverrides(prev => ({
      ...prev,
      [dim]: { ...(prev[dim] || {}), [field]: value },
    }))
    setSaveResult(null)
  }

  const handleSave = async () => {
    setSaving(true); setSaveResult(null); setSaveMsg('')
    // Validate: each provided override needs a comment
    for (const [dim, ov] of Object.entries(overrides)) {
      if (ov.score && !ov.comment?.trim()) {
        setSaveMsg(`Comment required for ${dim} override.`)
        setSaveResult('err'); setSaving(false); return
      }
    }
    // Strip empty overrides
    const cleanOverrides = Object.fromEntries(
      Object.entries(overrides).filter(([, v]) => v.score)
    )
    try {
      const res = await fetch(`${API_BASE_URL}/api/evaluations/${savedId}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          overrides:      Object.keys(cleanOverrides).length ? cleanOverrides : null,
          final_decision: decision || null,
          notes:          notes || null,
        }),
      })
      if (res.ok) {
        setSaveResult('ok'); setSaveMsg('Review saved.')
      } else {
        const d = await res.json()
        setSaveResult('err'); setSaveMsg(d?.detail || `Error ${res.status}`)
      }
    } catch (err) {
      setSaveResult('err'); setSaveMsg(err.message || 'Network error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="analysis-section reviewer-section">
      <div className="analysis-section-header">
        <span className="analysis-section-title">Reviewer override</span>
        <span className="analysis-model-tag">human review</span>
      </div>

      <div className="analysis-cards">
        {/* Per-dimension score overrides */}
        <div className="analysis-card">
          <div className="analysis-card-label" style={{ marginBottom: 12 }}>
            Dimension scores
            <span style={{ marginLeft: 8, fontFamily: 'var(--font-mono)', fontSize: '0.68rem',
              color: 'var(--ink-3)', fontWeight: 400 }}>
              — leave blank to keep AI score; comment required when overriding
            </span>
          </div>
          <div className="reviewer-dims">
            {DIMS.map(({ key, label }) => {
              const dimKey = label.toLowerCase()
              const ov     = overrides[dimKey] || {}
              return (
                <div key={key} className="reviewer-dim-row">
                  <span className="reviewer-dim-label">{label}</span>
                  <select
                    className="reviewer-score-select"
                    value={ov.score || ''}
                    onChange={e => setOverrideDim(dimKey, 'score', e.target.value ? parseInt(e.target.value) : null)}
                  >
                    <option value="">—</option>
                    {[1,2,3,4,5].map(n => <option key={n} value={n}>{n}</option>)}
                  </select>
                  <input
                    className="reviewer-comment-input"
                    type="text"
                    placeholder="Justification (required if score set)"
                    value={ov.comment || ''}
                    onChange={e => setOverrideDim(dimKey, 'comment', e.target.value)}
                    disabled={!ov.score}
                  />
                </div>
              )
            })}
          </div>
        </div>

        {/* Final decision */}
        <div className="analysis-card">
          <div className="analysis-card-label" style={{ marginBottom: 10 }}>Final decision</div>
          <div className="reviewer-decision-row">
            {['Approve', 'Revise', 'Reject'].map(opt => (
              <button
                key={opt}
                className={`reviewer-decision-btn${decision === opt ? ' reviewer-decision-btn--active' : ''}`}
                data-dec={opt.toLowerCase()}
                onClick={() => { setDecision(d => d === opt ? '' : opt); setSaveResult(null) }}
                type="button"
              >
                {opt}
              </button>
            ))}
          </div>
        </div>

        {/* Notes */}
        <div className="analysis-card">
          <div className="analysis-card-label" style={{ marginBottom: 8 }}>Reviewer notes</div>
          <textarea
            className="reviewer-notes-textarea"
            rows={4}
            placeholder="Additional observations, context, or instructions for the proposal authors…"
            value={notes}
            onChange={e => { setNotes(e.target.value); setSaveResult(null) }}
          />
        </div>

        {/* Save bar */}
        <div className="analysis-card" style={{ display: 'flex', alignItems: 'center',
          gap: 12, background: 'var(--surface)', borderBottom: 'none' }}>
          <button
            className="primary-btn"
            onClick={handleSave}
            disabled={saving}
            type="button"
            style={{ minWidth: 140 }}
          >
            {saving ? <><span className="spinner" aria-hidden="true" />Saving…</> : 'Save review'}
          </button>
          {saveResult === 'ok' && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--ok-text)' }}>
              {saveMsg}
            </span>
          )}
          {saveResult === 'err' && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--err-text)' }}>
              {saveMsg}
            </span>
          )}
          <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: '0.68rem',
            color: 'var(--ink-3)' }}>
            AI scores are never modified · ID: {savedId?.slice(0,8)}…
          </span>
        </div>
      </div>
    </div>
  )
}

// ── Timeout configuration ────────────────────────────────────────────────────────
// REQUEST_TIMEOUT_MS must exceed: (4 agents × AGENT_TIMEOUT_SECONDS) + coordinator time
// With AGENT_TIMEOUT_SECONDS=180: 4 × 180 + ~200 = 920s. Use 1,500s (25 min) as safe limit.
const REQUEST_TIMEOUT_MS = 1500000  // 25 minutes (1,500,000 ms)

// ── Main component ─────────────────────────────────────────────────────────────

export default function NewAnalysis({ llmHealth, onAnalysisComplete }) {
  const [selectedFile,   setSelectedFile]   = useState(null)
  const [isAnalyzing,    setIsAnalyzing]    = useState(false)
  const [analysisPhase,  setAnalysisPhase]  = useState('')
  const [analyzeError,   setAnalyzeError]   = useState('')
  const [isOllamaError,  setIsOllamaError]  = useState(false)
  const [analysisResult, setAnalysisResult] = useState(null)
  const [savedId,        setSavedId]        = useState(null)
  const [isDragging,     setIsDragging]     = useState(false)
  const [showRawText,    setShowRawText]    = useState(false)
  const [isDemoResult,   setIsDemoResult]   = useState(false)
  const [demoLoading,    setDemoLoading]    = useState(false)
  const [progressInfo,   setProgressInfo]   = useState(null)
  const [evalId,         setEvalId]         = useState(null)
  const fileInputRef = useRef(null)

  const fmtSize = b => {
    if (!b) return '0 B'
    const k = 1024, u = ['B','KB','MB','GB'], i = Math.floor(Math.log(b)/Math.log(k))
    return `${parseFloat((b/Math.pow(k,i)).toFixed(1))} ${u[i]}`
  }

  const validateFile = f => {
    if (!f.name.toLowerCase().endsWith('.pdf') && f.type !== 'application/pdf')
      return 'Invalid file type — only PDF accepted.'
    if (f.size > 10*1024*1024) return `File too large (${fmtSize(f.size)}). Limit: 10 MB.`
    return null
  }

  const pickFile = f => {
    setAnalyzeError(''); setIsOllamaError(false)
    const e = validateFile(f); if (e) { setAnalyzeError(e); setSelectedFile(null); return }
    setSelectedFile(f)
  }

  const handleFileChange = e => { const f = e.target.files?.[0]; if (f) pickFile(f) }
  const handleDragOver  = e => { e.preventDefault(); e.stopPropagation(); setIsDragging(true) }
  const handleDragLeave = e => { e.preventDefault(); e.stopPropagation(); setIsDragging(false) }
  const handleDrop      = e => {
    e.preventDefault(); e.stopPropagation(); setIsDragging(false)
    const f = e.dataTransfer.files?.[0]; if (f) pickFile(f)
  }
  const triggerFileBrowser = () => { if (fileInputRef.current) { fileInputRef.current.value = ''; fileInputRef.current.click() } }
  const clearFile = e => {
    e.stopPropagation(); setSelectedFile(null); setAnalyzeError(''); setIsOllamaError(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }
  const reset = () => {
    setSelectedFile(null); setAnalysisResult(null); setSavedId(null)
    setAnalyzeError(''); setIsOllamaError(false); setShowRawText(false)
    setIsDemoResult(false); setProgressInfo(null); setEvalId(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const isOllamaMsg = msg => {
    if (!msg) return false
    const l = msg.toLowerCase()
    return l.includes('not running') || l.includes('start ollama') ||
           l.includes('connection refused') || l.includes('ollama') ||
           l.includes('not pulled') || 
           l.includes('local ai model')
  }
  
  // Format agent name for display
  const formatAgentName = (name) => {
    if (!name) return ''
    return name.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
  }

  const handleLoadDemo = async (demoId) => {
    setDemoLoading(true)
    setAnalyzeError('')
    setAnalysisResult(null)
    setIsDemoResult(false)
    setSavedId(null)

    try {
      const res = await fetch(`${API_BASE_URL}/api/evaluations/demo/${demoId}`)
      const data = await res.json()
      
      if (!res.ok) {
        setAnalyzeError(data?.detail || `Failed to load demo: ${res.status}`)
        return
      }

      setAnalysisResult(data)
      setIsDemoResult(true)
      setSelectedFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
    } catch (err) {
      setAnalyzeError(err.message || 'Failed to load demo result')
    } finally {
      setDemoLoading(false)
    }
  }

  const handleAnalyze = async () => {
    if (!selectedFile) { setAnalyzeError('No file selected.'); return }
    setIsAnalyzing(true); setAnalyzeError(''); setIsOllamaError(false)
    setAnalysisResult(null); setSavedId(null); setAnalysisPhase('extracting')
    setProgressInfo(null); setEvalId(null)

    const form = new FormData(); form.append('file', selectedFile)
    const phaseTimer = setTimeout(() => setAnalysisPhase('analyzing'), 1000)
    let pollInterval = null

    try {
      // Fetch with generous timeout to allow LLM processing (4 agents + coordinator)
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
      
      const res  = await fetch(`${API_BASE_URL}/api/analyze`, { 
        method: 'POST', 
        body: form,
        signal: controller.signal,
      })
      clearTimeout(timeoutId)
      
      const data = await res.json()
      if (!res.ok) {
        // Extract error code from detail
        const errorCode = data?.error_code || (typeof data?.detail === 'object' ? data.detail.error_code : null)
        const msg = typeof data?.detail === 'string' ? data.detail : data?.detail?.message || `Server error ${res.status}`
        
        // Handle different error codes
        if (errorCode === 'ollama_not_running' || errorCode === 'model_not_found') {
          setIsOllamaError(true)
        } else if (errorCode === 'agent_timeout') {
          setAnalyzeError('The model is slow on this machine. Try a shorter document or the sample demos.')
          setIsOllamaError(false)
          return
        } else {
          setIsOllamaError(isOllamaMsg(msg))
        }
        setAnalyzeError(msg)
        return
      }

      // Start progress polling if we have an evaluation ID
      if (data.evaluation_id) {
        setEvalId(data.evaluation_id)
        pollInterval = setInterval(async () => {
          try {
            const progRes = await fetch(`${API_BASE_URL}/api/evaluations/${data.evaluation_id}/progress`)
            if (progRes.ok) {
              const progData = await progRes.json()
              setProgressInfo(progData)
            }
          } catch {
            // Ignore errors (analysis may have completed)
          }
        }, 2000)
      }

      setAnalysisPhase('saving')
      try {
        const coord   = data.coordinator || null
        const scoring = data.scoring     || {}
        const saveRes = await fetch(`${API_BASE_URL}/api/evaluations`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            filename:                   data.filename,
            page_count:                 data.page_count,
            char_count:                 data.char_count,
            model_used:                 llmHealth?.model || 'unknown',
            analysis:                   data.analysis,
            full_result:                data,
            coordinator_summary:         coord,
            preliminary_recommendation:  coord?.preliminary_recommendation ?? scoring.score_band ?? null,
            recommendation_reasoning:    coord?.recommendation_reasoning   ?? null,
            novelty_score:               scoring.novelty_score   ?? null,
            technical_score:             scoring.technical_score ?? null,
            financial_score:             scoring.financial_score ?? null,
            impact_score:                scoring.impact_score    ?? null,
            overall_score:               scoring.overall_score   ?? null,
            score_band:                  scoring.score_band      ?? null,
          }),
        })
        if (saveRes.ok) {
          const saved = await saveRes.json(); setSavedId(saved.id)
          if (onAnalysisComplete) onAnalysisComplete()
        }
      } catch { /* non-fatal */ }

      setAnalysisResult(data)
    } catch (err) {
      const msg = err.name === 'AbortError' 
        ? 'The analysis took longer than expected and was stopped. The local model is slow on this machine. Try a shorter document or one of the sample demos.'
        : (err.message || 'Unexpected error.')
      setIsOllamaError(isOllamaMsg(msg)); setAnalyzeError(msg)
    } finally {
      clearTimeout(phaseTimer)
      if (pollInterval) clearInterval(pollInterval)
      setIsAnalyzing(false)
      setAnalysisPhase('')
      setProgressInfo(null)
      setEvalId(null)
    }
  }

  const PREVIEW_LIMIT = 1500
  const fullText      = analysisResult?.full_text || ''
  const isLong        = fullText.length > PREVIEW_LIMIT
  const displayedText = showRawText || !isLong
    ? fullText
    : fullText.slice(0, PREVIEW_LIMIT) +
      `\n\n… [first ${PREVIEW_LIMIT.toLocaleString()} of ${(analysisResult?.char_count||0).toLocaleString()} chars shown]`

  const analysis    = analysisResult?.analysis    || null
  const coordinator = analysisResult?.coordinator || null
  const scoring     = analysisResult?.scoring     || null
  const novelty     = analysisResult?.novelty     || null

  const loadingMsg = () => {
    if (analysisPhase === 'extracting') return { h: 'Extracting text from PDF',      s: 'reading pages in-memory · PyMuPDF' }
    if (analysisPhase === 'saving')     return { h: 'Saving to database',             s: 'persisting scores + coordinator to SQLite' }
    
    // Show progress if available
    if (progressInfo) {
      const agentName = formatAgentName(progressInfo.current_agent)
      const progress = `${agentName} (${progressInfo.completed}/${progressInfo.total})`
      return { h: 'Running local model inference', s: progress }
    }
    
    return { h: 'Running local model inference', s: 'general analysis + scoring + coordinator · please wait' }
  }

  return (
    <div className="view-shell">

      <div className="view-header">
        <div>
          <h1 className="view-title">New Analysis</h1>
          <p className="view-subtitle">Upload an R&amp;D proposal PDF for local LLM evaluation</p>
        </div>
      </div>

      {/* Error banner */}
      {analyzeError && (
        <div className={`alert-banner ${isOllamaError ? 'ollama-error' : 'error'}`} role="alert">
          <div className="alert-icon-wrap" aria-hidden="true">
            <svg className="alert-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
          </div>
          <div className="alert-body">
            <strong className="alert-title">{isOllamaError ? 'Local model error' : 'Analysis error'}</strong>
            <p className="alert-text">{analyzeError}</p>
            {isOllamaError && (
              <div className="ollama-help">
                <p className="ollama-help-step"><strong>1.</strong> Make sure Ollama is running.</p>
                <p className="ollama-help-step"><strong>2.</strong> Pull the model:{' '}
                  <code className="inline-code">ollama pull {llmHealth?.model || 'qwen3:4b'}</code>
                </p>
                <p className="ollama-help-step"><strong>3.</strong> Click ↺ in the status bar, then retry.</p>
              </div>
            )}
          </div>
          <button className="alert-dismiss-btn"
            onClick={() => { setAnalyzeError(''); setIsOllamaError(false) }}>×</button>
        </div>
      )}

      {/* Demo section — try a sample proposal */}
      {!analysisResult && (
        <section className="upload-section" aria-label="Try demo proposal">
          <span className="section-label">Demo &amp; Testing</span>
          <div style={{
            background: 'var(--surface)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md)',
            padding: '16px 20px',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            flexWrap: 'wrap',
          }}>
            <span style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.85rem',
              color: 'var(--ink-2)',
              fontWeight: 500,
            }}>
              Try a sample proposal:
            </span>
            <select
              value=""
              onChange={(e) => {
                if (e.target.value) {
                  handleLoadDemo(e.target.value)
                }
              }}
              disabled={demoLoading}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '0.85rem',
                padding: '6px 10px',
                border: '1px solid var(--border)',
                borderRadius: '4px',
                background: 'var(--bg)',
                color: 'var(--ink)',
                cursor: 'pointer',
              }}
            >
              <option value="">— Select demo —</option>
              <option value="strong_crispr">CRISPR Viral Detection (Strong)</option>
              <option value="budget_error_chatbot">Chatbot with Budget Error</option>
              <option value="mixed_blockchain">Mixed Blockchain Supply Chain</option>
            </select>
            {demoLoading && (
              <span style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.8rem',
                color: 'var(--ink-2)',
              }}>
                <span className="spinner" aria-hidden="true" style={{ width: '14px', height: '14px' }} />
                Loading…
              </span>
            )}
          </div>
        </section>
      )}

      {/* Upload area */}
      {!analysisResult && (
        <section className="upload-section" aria-label="Upload proposal">
          <span className="section-label">Document input</span>
          <div
            className={`upload-dropzone${isDragging ? ' dragging' : ''}${selectedFile ? ' has-file' : ''}`}
            onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop}
            onClick={!selectedFile ? triggerFileBrowser : undefined}
            role="button" tabIndex={selectedFile ? -1 : 0}
            aria-label="Drop PDF here or click to browse"
            onKeyDown={e => { if (!selectedFile && (e.key==='Enter'||e.key===' ')) triggerFileBrowser() }}
          >
            <input type="file" ref={fileInputRef} accept=".pdf,application/pdf"
              onChange={handleFileChange} style={{ display:'none' }} aria-hidden="true" />
            <div className="upload-icon-wrapper" aria-hidden="true">
              <svg className="upload-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><polyline points="9 15 12 12 15 15"/>
              </svg>
            </div>
            {!selectedFile ? (
              <>
                <p className="upload-title">Drop a PDF here, or <span className="browse-link">browse</span></p>
                <p className="upload-constraints">PDF · max 10 MB · scored analysis + coordinator · saved to SQLite</p>
              </>
            ) : (
              <div className="selected-file-card" onClick={e => e.stopPropagation()}>
                <div className="file-info-header">
                  <span className="pdf-tag">PDF</span>
                  <div className="file-meta">
                    <p className="file-name" title={selectedFile.name}>{selectedFile.name}</p>
                    <p className="file-size">{fmtSize(selectedFile.size)}</p>
                  </div>
                  <button className="remove-file-btn" onClick={clearFile} type="button">Remove</button>
                </div>
              </div>
            )}
          </div>
          <div className="action-bar">
            <button className="primary-btn" onClick={handleAnalyze} disabled={!selectedFile || isAnalyzing}>
              {isAnalyzing ? <><span className="spinner" aria-hidden="true" />Analyzing…</> : 'Run analysis'}
            </button>
            {selectedFile && !isAnalyzing && (
              <button className="secondary-btn" onClick={triggerFileBrowser} type="button">Change file</button>
            )}
          </div>
          {isAnalyzing && (
            <div className="loading-bar" role="status" aria-live="polite">
              <div className="loading-spinner-ring" aria-hidden="true" />
              <div className="loading-text-group">
                <p className="loading-heading">{loadingMsg().h}</p>
                <p className="loading-subheading">{loadingMsg().s}</p>
              </div>
            </div>
          )}
        </section>
      )}

      {/* Results */}
      {analysisResult && analysis && (
        <section className="results-section" aria-label="Analysis results">

          <div className="results-header">
            <div className="results-title-group">
              {isDemoResult && <DemoBadge />}
              <span className="status-tag">Analysis complete{savedId ? ' · saved' : ''}</span>
              <h2 className="results-doc-title">{analysisResult.filename}</h2>
            </div>
            <button className="secondary-btn" onClick={reset}>New document</button>
          </div>

          {/* Metrics */}
          <div className="metrics-grid" role="list">
            {[
              { label: 'Pages',     value: analysisResult.page_count },
              { label: 'Characters', value: (analysisResult.char_count||0).toLocaleString() },
              { label: 'Model',      value: llmHealth?.model || 'local', cls: 'text-sm' },
              { label: 'Persisted',  value: savedId ? savedId.slice(0,8)+'…' : 'not saved',
                cls: `text-sm${savedId ? '' : ' text-warn'}` },
            ].map(({label, value, cls}) => (
              <div key={label} className="metric-card" role="listitem">
                <span className="metric-label">{label}</span>
                <span className={`metric-value${cls ? ' '+cls : ''}`}>{value}</span>
              </div>
            ))}
            {analysis.truncated && (
              <div className="metric-card warning-metric" role="listitem">
                <span className="metric-label">Input</span>
                <span className="metric-value text-warn">truncated — first 40 k chars</span>
              </div>
            )}
          </div>

          {/* Truncation notice */}
          {analysisResult.truncation_applied && (
            <div style={{
              background: '#fef3c7',
              border: '1px solid #f59e0b',
              color: '#92400e',
              padding: '12px 16px',
              borderRadius: '6px',
              marginBottom: '16px',
              fontSize: '0.875rem',
              lineHeight: '1.5'
            }} role="alert">
              <strong>⚠️ Performance optimization applied:</strong> Each agent reads the ~3,000 most relevant characters of the document.
            </div>
          )}

          {/* Score breakdown panel — above coordinator */}
          <ScoreBreakdown scoring={scoring} />

          {/* Coordinator panel */}
          <CoordinatorPanel 
            coordinator={coordinator} 
            coordinatorError={analysisResult.coordinator_error}
            novelty={novelty}
          />

          {/* Reviewer panel */}
          <ReviewerPanel savedId={savedId} existingReview={null} />

          {/* General analysis cards */}
          <div className="analysis-section">
            <div className="analysis-section-header">
              <span className="analysis-section-title">General analysis</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                {analysis.score != null && (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem',
                    color: 'var(--ink-2)' }}>
                    Novelty&nbsp;
                    <strong style={{ color: 'var(--ink)' }}>{analysis.score} / 5</strong>
                  </span>
                )}
                <span className="analysis-model-tag">ollama · {llmHealth?.model || 'local'}</span>
              </div>
            </div>

            {analysis.error_detail && (
              <div className="alert-banner error" role="alert"
                style={{ margin: 0, borderLeft: 'none', borderRight: 'none', borderTop: 'none', borderRadius: 0 }}>
                <div className="alert-body">
                  <strong className="alert-title">Partial result</strong>
                  <p className="alert-text">Model responded but output could not be fully parsed.</p>
                </div>
              </div>
            )}

            <div className="analysis-cards">
              {[
                { idx: '01', label: 'Title / Topic',        text: analysis.title_or_topic,
                  icon: <svg className="analysis-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg> },
                { idx: '02', label: 'Main Idea & Summary',  text: analysis.main_idea_summary,
                  icon: <svg className="analysis-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg> },
                { idx: '03', label: 'Main Problem',         text: analysis.main_problem,
                  icon: <svg className="analysis-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg> },
                { idx: '04', label: 'Proposed Solution',    text: analysis.proposed_solution,
                  icon: <svg className="analysis-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg> },
              ].map(({ idx, icon, label, text }) => (
                <div key={idx} className="analysis-card">
                  <div className="analysis-card-label">
                    <span className="card-index">{idx}</span>{icon}{label}
                    {idx === '01' && analysis.score != null && (
                      <span className="agent-score-tag">Novelty {analysis.score}/5</span>
                    )}
                  </div>
                  <p className="analysis-card-text">{text || 'Not stated in proposal'}</p>
                  {idx === '01' && analysis.score_justification && (
                    <p className="agent-score-justification">{analysis.score_justification}</p>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Extracted text */}
          <div className="preview-card">
            <div className="preview-header">
              <div className="preview-heading-wrap">
                <h3 className="preview-title">Extracted text</h3>
                <span className="preview-subtitle">
                  {showRawText ? `all ${(analysisResult.char_count||0).toLocaleString()} chars`
                               : `first ${Math.min(PREVIEW_LIMIT, analysisResult.char_count||0).toLocaleString()} chars`}
                </span>
              </div>
              {isLong && (
                <button className="toggle-text-btn" onClick={() => setShowRawText(!showRawText)}>
                  {showRawText ? 'Collapse' : 'Show all'}
                </button>
              )}
            </div>
            <div className="preview-content-box">
              <pre className="extracted-text-display">{displayedText}</pre>
            </div>
          </div>

          {/* Page breakdown */}
          {analysisResult.pages?.length > 0 && (
            <div className="pages-breakdown-card">
              <div className="breakdown-header">
                <h3 className="breakdown-title">Page breakdown · {analysisResult.pages.length} pages</h3>
              </div>
              <div className="pages-list">
                {analysisResult.pages.map(p => (
                  <details key={p.page_number} className="page-item">
                    <summary className="page-summary">
                      <span className="page-badge">p.{String(p.page_number).padStart(2,'0')}</span>
                      <span className="page-char-count">{p.text.length.toLocaleString()} chars</span>
                    </summary>
                    <pre className="page-text-content">
                      {p.text.trim() || '[no extractable text on this page]'}
                    </pre>
                  </details>
                ))}
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  )
}
