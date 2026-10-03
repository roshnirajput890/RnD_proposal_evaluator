/**
 * NewAnalysis.jsx — PDF upload + full evaluation pipeline workspace.
 *
 * Flow:
 *   1. POST /api/analyze  → general_analysis + coordinator pipeline
 *   2. POST /api/evaluations  → persist result (including coordinator fields)
 *   3. Call onAnalysisComplete() → bumps evaluationVersion → History/Analytics re-fetch
 *
 * Displays:
 *   - CoordinatorPanel (preliminary recommendation + synthesis) ABOVE the four agent panels
 *   - General analysis cards (title, summary, problem, solution)
 *   - Extracted text + page breakdown
 *
 * Props:
 *   llmHealth          — { status, model, … }
 *   onAnalysisComplete — () => void
 */
import { useState, useRef } from 'react'
import { API_BASE_URL } from '../config'

// ── Recommendation display config ──────────────────────────────────────────────
// Maps the coordinator's preliminary_recommendation string to a dot class and label.
// Uses only the existing CSS status dot colors — no new colors introduced.
const REC_CONFIG = {
  'Recommend':                 { dot: 'dot-connected',    label: 'Recommend' },
  'Revise and Resubmit':       { dot: 'dot-checking',     label: 'Revise and Resubmit' },
  'Not Recommended':           { dot: 'dot-disconnected', label: 'Not Recommended' },
  'Insufficient Information':  { dot: 'dot-checking',     label: 'Insufficient Information' },
}

const CONFIDENCE_CLS = {
  'High':   'status-ok',
  'Medium': 'status-warn',
  'Low':    'status-err',
}

// ── CoordinatorPanel ──────────────────────────────────────────────────────────

function CoordinatorPanel({ coordinator, coordinatorError }) {
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
            <p className="alert-text" style={{ marginTop: '4px', opacity: 0.8 }}>
              The agent analysis below is still valid. Run again once Ollama is stable.
            </p>
          </div>
        </div>
      </div>
    )
  }

  if (!coordinator) return null

  const recConf  = REC_CONFIG[coordinator.preliminary_recommendation] || REC_CONFIG['Insufficient Information']
  const confCls  = CONFIDENCE_CLS[coordinator.coordinator_confidence] || 'status-muted'

  return (
    <div className="analysis-section coord-section">
      {/* Header row with toggle */}
      <div className="analysis-section-header" style={{ cursor: 'pointer' }}
        onClick={() => setOpen(o => !o)}>
        <span className="analysis-section-title">Coordinator synthesis</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {/* Recommendation dot + label */}
          <span style={{ display: 'flex', alignItems: 'center', gap: '6px',
            fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--ink-2)' }}>
            <span className={`dot ${recConf.dot}`} aria-hidden="true" />
            {recConf.label}
          </span>
          {/* Confidence */}
          <span className={`status-cell-value ${confCls}`}
            style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem' }}>
            {coordinator.coordinator_confidence} confidence
          </span>
          <span className="analysis-model-tag">{open ? '▲ collapse' : '▼ expand'}</span>
        </div>
      </div>

      {/* Disclaimer — always visible */}
      <div style={{ padding: '8px 20px', background: 'var(--surface)',
        borderBottom: '1px solid var(--border-subtle)',
        fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--ink-3)',
        lineHeight: '1.5' }}>
        AI-generated preliminary evaluation. A human reviewer makes the final decision.
        {' '}Novelty assessment has no external literature evidence in this version.
      </div>

      {open && (
        <div className="analysis-cards">

          {/* Overall summary */}
          <div className="analysis-card">
            <div className="analysis-card-label">
              <span className="card-index">C1</span>
              <svg className="analysis-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8" x2="12" y2="12"/>
                <line x1="8" y1="12" x2="16" y2="12"/>
              </svg>
              Overall Summary
            </div>
            <p className="analysis-card-text">{coordinator.overall_summary || '—'}</p>
          </div>

          {/* Recommendation reasoning */}
          <div className="analysis-card">
            <div className="analysis-card-label">
              <span className="card-index">C2</span>
              <svg className="analysis-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <polyline points="9 11 12 14 22 4"/>
                <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
              </svg>
              Preliminary Recommendation · Reasoning
            </div>
            <p className="analysis-card-text">{coordinator.recommendation_reasoning || '—'}</p>
          </div>

          {/* Key strengths */}
          {coordinator.key_strengths?.length > 0 && (
            <div className="analysis-card">
              <div className="analysis-card-label">
                <span className="card-index">C3</span>
                <svg className="analysis-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                  strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                  <polyline points="22 4 12 14.01 9 11.01"/>
                </svg>
                Key Strengths
              </div>
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

          {/* Key risks */}
          {coordinator.key_risks?.length > 0 && (
            <div className="analysis-card">
              <div className="analysis-card-label">
                <span className="card-index">C4</span>
                <svg className="analysis-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                  strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                  <line x1="12" y1="9" x2="12" y2="13"/>
                  <line x1="12" y1="17" x2="12.01" y2="17"/>
                </svg>
                Key Risks
              </div>
              <ul className="coord-list">
                {coordinator.key_risks.map((r, i) => (
                  <li key={i} className="coord-list-item">
                    <span className="coord-severity-tag" data-sev={r.severity?.toLowerCase()}>
                      {r.severity || '?'}
                    </span>
                    <span className="coord-item-text">{r.point}</span>
                    <span className="coord-agent-tag">{r.supported_by_agent}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Conflicts */}
          {coordinator.conflicts_or_tensions?.length > 0 && (
            <div className="analysis-card">
              <div className="analysis-card-label">
                <span className="card-index">C5</span>
                <svg className="analysis-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                  strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <line x1="18" y1="6" x2="6" y2="18"/>
                  <line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
                Tensions Between Agents
              </div>
              <ul className="coord-list">
                {coordinator.conflicts_or_tensions.map((c, i) => (
                  <li key={i} className="coord-list-item">
                    <span className="coord-item-text">{c.description}</span>
                    {c.between_agents?.length > 0 && (
                      <span className="coord-agent-tag">{c.between_agents.join(' vs ')}</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Critical missing info + questions — two-column on wide screens */}
          {(coordinator.critical_missing_information?.length > 0 ||
            coordinator.questions_for_human_reviewer?.length > 0) && (
            <div className="analysis-card coord-two-col">
              {coordinator.critical_missing_information?.length > 0 && (
                <div className="coord-col">
                  <div className="analysis-card-label" style={{ marginBottom: '8px' }}>
                    <span className="card-index">C6</span>
                    Critical Missing Information
                  </div>
                  <ul className="coord-list">
                    {coordinator.critical_missing_information.map((m, i) => (
                      <li key={i} className="coord-list-item">
                        <span className="coord-item-text">{m}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {coordinator.questions_for_human_reviewer?.length > 0 && (
                <div className="coord-col">
                  <div className="analysis-card-label" style={{ marginBottom: '8px' }}>
                    <span className="card-index">C7</span>
                    Questions for Reviewer
                  </div>
                  <ul className="coord-list">
                    {coordinator.questions_for_human_reviewer.map((q, i) => (
                      <li key={i} className="coord-list-item">
                        <span className="coord-item-text">{q}</span>
                      </li>
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

  const fileInputRef = useRef(null)

  // ── File helpers ───────────────────────────────────────────────────────────

  const fmtSize = (bytes) => {
    if (!bytes) return '0 B'
    const k = 1024, units = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${units[i]}`
  }

  const validateFile = (file) => {
    if (!file.name.toLowerCase().endsWith('.pdf') && file.type !== 'application/pdf')
      return 'Invalid file type — only PDF accepted.'
    if (file.size > 10 * 1024 * 1024)
      return `File too large (${fmtSize(file.size)}). Limit: 10 MB.`
    return null
  }

  const pickFile = (file) => {
    setAnalyzeError(''); setIsOllamaError(false)
    const err = validateFile(file)
    if (err) { setAnalyzeError(err); setSelectedFile(null); return }
    setSelectedFile(file)
  }

  const handleFileChange = (e) => { const f = e.target.files?.[0]; if (f) pickFile(f) }
  const handleDragOver   = (e) => { e.preventDefault(); e.stopPropagation(); setIsDragging(true) }
  const handleDragLeave  = (e) => { e.preventDefault(); e.stopPropagation(); setIsDragging(false) }
  const handleDrop       = (e) => {
    e.preventDefault(); e.stopPropagation(); setIsDragging(false)
    const f = e.dataTransfer.files?.[0]; if (f) pickFile(f)
  }

  const triggerFileBrowser = () => {
    if (fileInputRef.current) { fileInputRef.current.value = ''; fileInputRef.current.click() }
  }

  const clearFile = (e) => {
    e.stopPropagation()
    setSelectedFile(null); setAnalyzeError(''); setIsOllamaError(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const reset = () => {
    setSelectedFile(null); setAnalysisResult(null); setSavedId(null)
    setAnalyzeError(''); setIsOllamaError(false); setShowRawText(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const isOllamaMsg = (msg) => {
    if (!msg) return false
    const l = msg.toLowerCase()
    return l.includes('not running') || l.includes('start ollama') ||
           l.includes('connection refused') || l.includes('ollama') ||
           l.includes('not pulled') || l.includes('timed out') ||
           l.includes('local ai model')
  }

  // ── Analyze + persist ──────────────────────────────────────────────────────

  const handleAnalyze = async () => {
    if (!selectedFile) { setAnalyzeError('No file selected.'); return }

    setIsAnalyzing(true); setAnalyzeError(''); setIsOllamaError(false)
    setAnalysisResult(null); setSavedId(null); setAnalysisPhase('extracting')

    const form = new FormData()
    form.append('file', selectedFile)
    const phaseTimer = setTimeout(() => setAnalysisPhase('analyzing'), 1000)

    try {
      // Step 1: full evaluation pipeline (general_analysis + coordinator)
      const res  = await fetch(`${API_BASE_URL}/api/analyze`, { method: 'POST', body: form })
      const data = await res.json()

      if (!res.ok) {
        const msg = data?.detail || `Server error ${res.status}`
        setIsOllamaError(isOllamaMsg(msg)); setAnalyzeError(msg)
        return
      }

      // Step 2: persist — include coordinator fields
      setAnalysisPhase('saving')
      try {
        const coord = data.coordinator || null
        const saveRes = await fetch(`${API_BASE_URL}/api/evaluations`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            filename:                   data.filename,
            page_count:                 data.page_count,
            char_count:                 data.char_count,
            model_used:                 llmHealth?.model || 'unknown',
            analysis:                   data.analysis,
            full_result:                data,
            coordinator_summary:         coord,
            preliminary_recommendation:  coord?.preliminary_recommendation ?? null,
            recommendation_reasoning:    coord?.recommendation_reasoning   ?? null,
          }),
        })
        if (saveRes.ok) {
          const saved = await saveRes.json()
          setSavedId(saved.id)
          if (onAnalysisComplete) onAnalysisComplete()
        }
      } catch { /* Save failure is non-fatal */ }

      setAnalysisResult(data)
    } catch (err) {
      const msg = err.message || 'Unexpected error.'
      setIsOllamaError(isOllamaMsg(msg)); setAnalyzeError(msg)
    } finally {
      clearTimeout(phaseTimer); setIsAnalyzing(false); setAnalysisPhase('')
    }
  }

  // ── Derived ────────────────────────────────────────────────────────────────

  const PREVIEW_LIMIT = 1500
  const fullText      = analysisResult?.full_text || ''
  const isLong        = fullText.length > PREVIEW_LIMIT
  const displayedText = showRawText || !isLong
    ? fullText
    : fullText.slice(0, PREVIEW_LIMIT) +
      `\n\n… [first ${PREVIEW_LIMIT.toLocaleString()} of ${(analysisResult?.char_count||0).toLocaleString()} chars shown]`

  const analysis    = analysisResult?.analysis    || null
  const coordinator = analysisResult?.coordinator || null

  const loadingMsg = () => {
    if (analysisPhase === 'extracting') return { h: 'Extracting text from PDF',      s: 'reading pages in-memory · PyMuPDF' }
    if (analysisPhase === 'saving')     return { h: 'Saving to database',             s: 'persisting result to SQLite' }
    return                                     { h: 'Running local model inference', s: 'general analysis + coordinator · please wait' }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

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
            <svg className="alert-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
          </div>
          <div className="alert-body">
            <strong className="alert-title">{isOllamaError ? 'Local model error' : 'Analysis error'}</strong>
            <p className="alert-text">{analyzeError}</p>
            {isOllamaError && (
              <div className="ollama-help">
                <p className="ollama-help-step"><strong>1.</strong> Make sure Ollama is running.</p>
                <p className="ollama-help-step"><strong>2.</strong> Pull the model if needed:{' '}
                  <code className="inline-code">ollama pull {llmHealth?.model || 'qwen3:4b'}</code>
                </p>
                <p className="ollama-help-step"><strong>3.</strong> Click ↺ next to LLM in the status bar, then retry.</p>
              </div>
            )}
          </div>
          <button className="alert-dismiss-btn"
            onClick={() => { setAnalyzeError(''); setIsOllamaError(false) }} aria-label="Dismiss">×</button>
        </div>
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
            onKeyDown={(e) => { if (!selectedFile && (e.key==='Enter'||e.key===' ')) triggerFileBrowser() }}
          >
            <input type="file" ref={fileInputRef} accept=".pdf,application/pdf"
              onChange={handleFileChange} style={{ display: 'none' }} aria-hidden="true" />

            <div className="upload-icon-wrapper" aria-hidden="true">
              <svg className="upload-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
                <line x1="12" y1="18" x2="12" y2="12"/>
                <polyline points="9 15 12 12 15 15"/>
              </svg>
            </div>

            {!selectedFile ? (
              <>
                <p className="upload-title">Drop a PDF here, or <span className="browse-link">browse</span></p>
                <p className="upload-constraints">PDF · max 10 MB · general analysis + coordinator · saved to SQLite</p>
              </>
            ) : (
              <div className="selected-file-card" onClick={(e) => e.stopPropagation()}>
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
              {isAnalyzing ? <><span className="spinner" aria-hidden="true"></span>Analyzing…</> : 'Run analysis'}
            </button>
            {selectedFile && !isAnalyzing && (
              <button className="secondary-btn" onClick={triggerFileBrowser} type="button">Change file</button>
            )}
          </div>

          {isAnalyzing && (
            <div className="loading-bar" role="status" aria-live="polite">
              <div className="loading-spinner-ring" aria-hidden="true"></div>
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
              <span className="status-tag">Analysis complete{savedId ? ' · saved' : ''}</span>
              <h2 className="results-doc-title">{analysisResult.filename}</h2>
            </div>
            <button className="secondary-btn" onClick={reset}>New document</button>
          </div>

          {/* Metrics */}
          <div className="metrics-grid" role="list">
            <div className="metric-card" role="listitem">
              <span className="metric-label">Pages</span>
              <span className="metric-value">{analysisResult.page_count}</span>
            </div>
            <div className="metric-card" role="listitem">
              <span className="metric-label">Characters</span>
              <span className="metric-value">{(analysisResult.char_count||0).toLocaleString()}</span>
            </div>
            <div className="metric-card" role="listitem">
              <span className="metric-label">Model</span>
              <span className="metric-value text-sm">{llmHealth?.model || 'local'}</span>
            </div>
            <div className="metric-card" role="listitem">
              <span className="metric-label">Persisted</span>
              <span className={`metric-value text-sm${savedId ? '' : ' text-warn'}`}>
                {savedId ? savedId.slice(0,8)+'…' : 'not saved'}
              </span>
            </div>
            {analysis.truncated && (
              <div className="metric-card warning-metric" role="listitem">
                <span className="metric-label">Input</span>
                <span className="metric-value text-warn">truncated — first 40 k chars</span>
              </div>
            )}
          </div>

          {/* ── Coordinator panel — ABOVE agent panels ── */}
          <CoordinatorPanel
            coordinator={coordinator}
            coordinatorError={analysisResult.coordinator_error}
          />

          {/* ── General analysis cards ── */}
          <div className="analysis-section">
            <div className="analysis-section-header">
              <span className="analysis-section-title">General analysis</span>
              <span className="analysis-model-tag">ollama · {llmHealth?.model || 'local'}</span>
            </div>

            {analysis.error_detail && (
              <div className="alert-banner error" role="alert"
                style={{ margin:0, borderLeft:'none', borderRight:'none', borderTop:'none', borderRadius:0 }}>
                <div className="alert-body">
                  <strong className="alert-title">Partial result</strong>
                  <p className="alert-text">Model responded but output could not be fully parsed.</p>
                </div>
              </div>
            )}

            <div className="analysis-cards">
              {[
                { idx:'01', label:'Title / Topic',        text: analysis.title_or_topic,
                  icon: <svg className="analysis-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg> },
                { idx:'02', label:'Main Idea & Summary',  text: analysis.main_idea_summary,
                  icon: <svg className="analysis-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg> },
                { idx:'03', label:'Main Problem',         text: analysis.main_problem,
                  icon: <svg className="analysis-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg> },
                { idx:'04', label:'Proposed Solution',    text: analysis.proposed_solution,
                  icon: <svg className="analysis-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg> },
              ].map(({ idx, icon, label, text }) => (
                <div key={idx} className="analysis-card">
                  <div className="analysis-card-label">
                    <span className="card-index">{idx}</span>{icon}{label}
                  </div>
                  <p className="analysis-card-text">{text || 'Not stated in proposal'}</p>
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
                {analysisResult.pages.map((p) => (
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
