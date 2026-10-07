/**
 * App.jsx — Layout shell.
 *
 * Owns:
 *   activeView        — which page is visible (state-based routing, no react-router)
 *   health state      — shared by Sidebar + Settings topbar
 *   sessionConfig     — lifted here so Settings changes survive navigation
 *   evaluationVersion — integer bumped after every saved analysis; History and
 *                       Analytics watch it to know when to re-fetch
 *   live clock
 */
import { useState, useEffect } from 'react'
import { API_BASE_URL } from './config'
import Sidebar     from './components/Sidebar'
import NewAnalysis from './views/NewAnalysis'
import History     from './views/History'
import Analytics   from './views/Analytics'
import Settings    from './views/Settings'
import './App.css'

export default function App() {

  // ── Navigation ───────────────────────────────────────────────────────────────
  const [activeView, setActiveView] = useState('analysis')

  // ── Health (shared: Sidebar widget + topbar + Settings) ─────────────────────
  const [backendStatus, setBackendStatus] = useState('checking')
  const [healthError,   setHealthError]   = useState('')
  const [llmHealth,     setLlmHealth]     = useState(null)
  const [llmChecking,   setLlmChecking]   = useState(false)

  const checkBackendHealth = async () => {
    setBackendStatus('checking'); setHealthError('')
    try {
      const res  = await fetch(`${API_BASE_URL}/api/health`, { headers: { Accept: 'application/json' } })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setBackendStatus(data?.status === 'ok' ? 'connected' : 'disconnected')
      if (data?.status !== 'ok') setHealthError('Unexpected server response')
    } catch (err) {
      setBackendStatus('disconnected')
      setHealthError(err.message || 'Unreachable')
    }
  }

  const checkLlmHealth = async () => {
    setLlmChecking(true)
    try {
      const res  = await fetch(`${API_BASE_URL}/api/health/llm`, { headers: { Accept: 'application/json' } })
      const data = await res.json()
      setLlmHealth(data)
    } catch {
      setLlmHealth({ status: 'offline', reachable: false, model_available: false,
                     model: '—', message: 'Could not reach backend.' })
    } finally {
      setLlmChecking(false)
    }
  }

  useEffect(() => {
    checkBackendHealth()
    checkLlmHealth()
  }, [])

  // ── Session config — lifted so Settings changes survive page navigation ──────
  // Initialised to null; Settings fetches real values from GET /api/config on
  // first mount, then writes them back here via onConfigChange.
  const [sessionConfig, setSessionConfig] = useState(null)

  // ── Evaluation version — bumped after every successful save ─────────────────
  // History and Analytics useEffect deps include this, so they re-fetch
  // automatically whenever a new analysis is saved.
  const [evaluationVersion, setEvaluationVersion] = useState(0)

  const handleAnalysisComplete = () => {
    setEvaluationVersion(v => v + 1)
  }

  // ── Live clock ───────────────────────────────────────────────────────────────
  const [clockStr, setClockStr] = useState('')

  useEffect(() => {
    const tick = () => {
      const now = new Date()
      setClockStr(
        `${String(now.getHours()).padStart(2,'0')}:` +
        `${String(now.getMinutes()).padStart(2,'0')}:` +
        `${String(now.getSeconds()).padStart(2,'0')}`
      )
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  // ── Status helpers ────────────────────────────────────────────────────────────
  const beState  = backendStatus === 'connected' ? 'ok' : backendStatus === 'checking' ? 'warn' : 'err'
  const llmState = llmChecking ? 'warn' : llmHealth?.status === 'ok' ? 'ok' : llmHealth ? 'err' : 'muted'
  const llmText  = llmChecking          ? 'checking…'
                 : llmHealth?.status === 'ok'            ? `ready · ${llmHealth.model}`
                 : llmHealth?.status === 'model_missing' ? `not pulled · ${llmHealth.model}`
                 : llmHealth                             ? 'ollama offline' : '—'

  // ── View routing ─────────────────────────────────────────────────────────────
  const renderView = () => {
    switch (activeView) {
      case 'analysis':
        return (
          <NewAnalysis
            llmHealth={llmHealth}
            onAnalysisComplete={handleAnalysisComplete}
          />
        )
      case 'history':
        return (
          <History
            evaluationVersion={evaluationVersion}
            onNavigateToAnalysis={() => setActiveView('analysis')}
          />
        )
      case 'analytics':
        return <Analytics evaluationVersion={evaluationVersion} />
      case 'settings':
        return (
          <Settings
            llmHealth={llmHealth}
            llmChecking={llmChecking}
            onRefreshLlm={checkLlmHealth}
            sessionConfig={sessionConfig}
            onConfigChange={setSessionConfig}
          />
        )
      default:
        return <NewAnalysis llmHealth={llmHealth} onAnalysisComplete={handleAnalysisComplete} />
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────────
  return (
    <div className="layout-root">

      <Sidebar
        activeView={activeView}
        setActiveView={setActiveView}
        llmHealth={llmHealth}
        llmChecking={llmChecking}
        backendStatus={backendStatus}
      />

      <div className="layout-main">

        {/* Top bar */}
        <header className="topbar" role="banner">
          <div className="topbar-status" role="status" aria-live="polite">

            <div className="status-cell">
              <span className="status-cell-label">API</span>
              <span className={`status-cell-value status-${beState}`}>
                <span className={`dot dot-${backendStatus === 'connected' ? 'connected' : backendStatus === 'checking' ? 'checking' : 'disconnected'}`} aria-hidden="true" />
                {backendStatus === 'connected' ? 'connected' : backendStatus === 'checking' ? 'checking' : 'offline'}
              </span>
              <button className="btn-refresh" onClick={checkBackendHealth}
                disabled={backendStatus === 'checking'} aria-label="Refresh backend status">↺</button>
            </div>

            <div className="status-cell">
              <span className="status-cell-label">LLM</span>
              <span className={`status-cell-value status-${llmState}`}>
                <span className={`dot dot-${llmState === 'ok' ? 'connected' : llmState === 'warn' ? 'checking' : 'disconnected'}`} aria-hidden="true" />
                {llmText}
              </span>
              <button className="btn-refresh" onClick={checkLlmHealth}
                disabled={llmChecking} aria-label="Refresh LLM status">↺</button>
            </div>

            {(healthError || (llmHealth && llmHealth.status !== 'ok' && !llmChecking)) && (
              <div className="status-cell topbar-error">
                <span className="status-cell-label">note</span>
                <span className="status-cell-value status-err">
                  {healthError || llmHealth?.message}
                </span>
              </div>
            )}
          </div>

          <time className="header-clock" aria-label="Current time">{clockStr}</time>
        </header>

        <main className="layout-view" id="main-content">
          {renderView()}
        </main>

        <footer className="layout-footer">
          <span className="footer-text">R&amp;D Proposal Evaluator</span>
        </footer>
      </div>

    </div>
  )
}
