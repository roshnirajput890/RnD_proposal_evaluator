/**
 * Sidebar.jsx
 * Left navigation panel. Receives activeView + setActiveView from App.
 * Collapsible (icon-only mode). Bottom LLM status widget.
 * No external deps — pure React + inline SVGs.
 */
import { useState } from 'react'

// ─── SVG icon set ─────────────────────────────────────────────────────────────
// Each returns a 16×16 stroked icon to match the existing analysis-icon style.

const IconAnalysis = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
    <polyline points="14 2 14 8 20 8"/>
    <line x1="16" y1="13" x2="8" y2="13"/>
    <line x1="16" y1="17" x2="8" y2="17"/>
    <polyline points="10 9 9 9 8 9"/>
  </svg>
)

const IconHistory = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="12 8 12 12 14 14"/>
    <path d="M3.05 11a9 9 0 1 0 .5-4"/>
    <polyline points="3 3 3.05 11 11 10.9"/>
  </svg>
)

const IconAnalytics = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <line x1="18" y1="20" x2="18" y2="10"/>
    <line x1="12" y1="20" x2="12" y2="4"/>
    <line x1="6"  y1="20" x2="6"  y2="14"/>
    <line x1="2"  y1="20" x2="22" y2="20"/>
  </svg>
)

const IconSettings = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="3"/>
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06
             a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09
             A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83
             l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09
             A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83
             l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09
             a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83
             l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09
             a1.65 1.65 0 0 0-1.51 1z"/>
  </svg>
)

const IconCollapse = ({ collapsed }) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {collapsed
      ? <><polyline points="9 18 15 12 9 6"/></>
      : <><polyline points="15 18 9 12 15 6"/></>
    }
  </svg>
)

// ─── Nav items definition ──────────────────────────────────────────────────────

const NAV_ITEMS = [
  { id: 'analysis',  label: 'New Analysis',       Icon: IconAnalysis  },
  { id: 'history',   label: 'History & Archive',  Icon: IconHistory   },
  { id: 'analytics', label: 'Portfolio Analytics',Icon: IconAnalytics },
]

const ADVANCED_ITEMS = [
  { id: 'settings',  label: 'AI Engine Settings', Icon: IconSettings  },
]

// ─── Component ────────────────────────────────────────────────────────────────

export default function Sidebar({ activeView, setActiveView, llmHealth, llmChecking, backendStatus }) {
  const [collapsed, setCollapsed] = useState(false)
  const [advancedExpanded, setAdvancedExpanded] = useState(false)

  // LLM widget state string
  const llmLine = () => {
    if (llmChecking) return { text: 'checking…', cls: 'sb-status-warn' }
    if (!llmHealth)  return { text: 'unknown',   cls: 'sb-status-muted' }
    if (llmHealth.status === 'ok')            return { text: llmHealth.model, cls: 'sb-status-ok' }
    if (llmHealth.status === 'model_missing') return { text: 'model missing', cls: 'sb-status-warn' }
    return { text: 'offline', cls: 'sb-status-err' }
  }

  const apiLine = () => {
    if (backendStatus === 'checking')   return { text: 'checking…', cls: 'sb-status-warn' }
    if (backendStatus === 'connected')  return { text: 'connected',  cls: 'sb-status-ok' }
    return { text: 'offline', cls: 'sb-status-err' }
  }

  const llm = llmLine()
  const api = apiLine()

  return (
    <nav
      className={`sidebar${collapsed ? ' sidebar--collapsed' : ''}`}
      aria-label="Main navigation"
    >
      {/* ── Top: branding + collapse toggle ── */}
      <div className="sb-top">
        <div className="sb-brand">
          {!collapsed && (
            <span className="sb-brand-name">RnD Platform</span>
          )}
          <span className="sb-env-tag" title="Environment">local</span>
        </div>
        <button
          className="sb-collapse-btn"
          onClick={() => setCollapsed(c => !c)}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          title={collapsed ? 'Expand' : 'Collapse'}
        >
          <IconCollapse collapsed={collapsed} />
        </button>
      </div>

      {/* ── Nav section label ── */}
      {!collapsed && (
        <span className="sb-section-label">Navigation</span>
      )}

      {/* ── Nav links ── */}
      <ul className="sb-nav" role="list">
        {NAV_ITEMS.map(({ id, label, Icon }) => (
          <li key={id} role="listitem">
            <button
              className={`sb-nav-item${activeView === id ? ' sb-nav-item--active' : ''}`}
              onClick={() => setActiveView(id)}
              aria-current={activeView === id ? 'page' : undefined}
              title={collapsed ? label : undefined}
            >
              <span className="sb-nav-icon"><Icon /></span>
              {!collapsed && <span className="sb-nav-label">{label}</span>}
              {!collapsed && activeView === id && (
                <span className="sb-nav-active-bar" aria-hidden="true" />
              )}
            </button>
          </li>
        ))}
      </ul>

      {/* ── Advanced section (collapsible) ── */}
      {!collapsed && (
        <>
          <button
            className="sb-section-label sb-section-label--collapsible"
            onClick={() => setAdvancedExpanded(e => !e)}
            aria-expanded={advancedExpanded}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              width: '100%',
              padding: '8px 16px',
              marginTop: '8px',
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--ink-3)',
              fontSize: '0.7rem',
              fontWeight: '600',
              letterSpacing: '0.05em',
              textTransform: 'uppercase',
              transition: 'color 0.15s ease'
            }}
            onMouseEnter={(e) => e.currentTarget.style.color = 'var(--ink-2)'}
            onMouseLeave={(e) => e.currentTarget.style.color = 'var(--ink-3)'}
          >
            <span>Advanced</span>
            <span style={{ transform: advancedExpanded ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s ease' }}>
              <IconCollapse collapsed={!advancedExpanded} />
            </span>
          </button>
          
          {advancedExpanded && (
            <ul className="sb-nav" role="list" style={{ marginTop: '4px' }}>
              {ADVANCED_ITEMS.map(({ id, label, Icon }) => (
                <li key={id} role="listitem">
                  <button
                    className={`sb-nav-item${activeView === id ? ' sb-nav-item--active' : ''}`}
                    onClick={() => setActiveView(id)}
                    aria-current={activeView === id ? 'page' : undefined}
                  >
                    <span className="sb-nav-icon"><Icon /></span>
                    <span className="sb-nav-label">{label}</span>
                    {activeView === id && (
                      <span className="sb-nav-active-bar" aria-hidden="true" />
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {/* ── Bottom status widget ── */}
      <div className="sb-bottom">
        {!collapsed ? (
          <div className="sb-status-widget">
            <span className="sb-section-label" style={{ marginBottom: '8px', display: 'block' }}>
              System status
            </span>
            <div className="sb-status-row">
              <span className="sb-status-key">API</span>
              <span className={`sb-status-val ${api.cls}`}>
                <span className={`sb-dot ${backendStatus === 'connected' ? 'sb-dot--ok' : backendStatus === 'checking' ? 'sb-dot--warn' : 'sb-dot--err'}`} />
                {api.text}
              </span>
            </div>
            <div className="sb-status-row">
              <span className="sb-status-key">LLM</span>
              <span className={`sb-status-val ${llm.cls}`}>
                <span className={`sb-dot ${llmHealth?.status === 'ok' ? 'sb-dot--ok' : llmChecking ? 'sb-dot--warn' : 'sb-dot--err'}`} />
                {llm.text}
              </span>
            </div>
          </div>
        ) : (
          /* Collapsed: just the two indicator dots stacked */
          <div className="sb-status-dots">
            <span
              className={`sb-dot sb-dot--lg ${backendStatus === 'connected' ? 'sb-dot--ok' : backendStatus === 'checking' ? 'sb-dot--warn' : 'sb-dot--err'}`}
              title={`API: ${api.text}`}
            />
            <span
              className={`sb-dot sb-dot--lg ${llmHealth?.status === 'ok' ? 'sb-dot--ok' : llmChecking ? 'sb-dot--warn' : 'sb-dot--err'}`}
              title={`LLM: ${llm.text}`}
            />
          </div>
        )}
      </div>
    </nav>
  )
}
