import { useState, useEffect, useRef } from 'react'
import { API_BASE_URL } from './config'
import './App.css'

/**
 * App Component - Brick 2: PDF Upload & Text Extraction
 *
 * Capabilities:
 * - Monitors backend connectivity via /api/health
 * - Validates PDF uploads (file picker, drag & drop, file type, 10MB limit)
 * - In-memory page-by-page text extraction via POST /api/upload
 * - Displays extraction metrics (page count, char count) and first ~1500 chars preview
 * - Displays user-friendly error banners for invalid files, corruption, password protection,
 *   scanned images without OCR, and unexpected server failures.
 */
function App() {
  // Backend health status: 'checking' | 'connected' | 'disconnected'
  const [backendStatus, setBackendStatus] = useState('checking')
  const [healthError, setHealthError] = useState('')

  // Upload and extraction state
  const [selectedFile, setSelectedFile] = useState(null)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [extractionResult, setExtractionResult] = useState(null)
  const [showFullText, setShowFullText] = useState(false)
  const [isDragging, setIsDragging] = useState(false)

  // Ref to hidden file input
  const fileInputRef = useRef(null)

  // 1. Query the backend health check endpoint
  const checkBackendHealth = async () => {
    setBackendStatus('checking')
    setHealthError('')

    try {
      const response = await fetch(`${API_BASE_URL}/api/health`, {
        method: 'GET',
        headers: {
          Accept: 'application/json',
        },
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      const data = await response.json()
      if (data && data.status === 'ok') {
        setBackendStatus('connected')
      } else {
        setBackendStatus('disconnected')
        setHealthError('Unexpected response payload from server')
      }
    } catch (err) {
      setBackendStatus('disconnected')
      setHealthError(err.message || 'Unable to reach backend service')
    }
  }

  // Initial health check on mount
  useEffect(() => {
    checkBackendHealth()
  }, [])

  // Format bytes into readable string (KB / MB)
  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  // Handle file selection from input
  const handleFileChange = (e) => {
    const file = e.target.files && e.target.files[0]
    setUploadError('')
    if (!file) return

    // Quick client-side check
    if (!file.name.toLowerCase().endsWith('.pdf') && file.type !== 'application/pdf') {
      setUploadError('Invalid file type. Please select a document ending in .pdf.')
      setSelectedFile(null)
      return
    }

    if (file.size > 10 * 1024 * 1024) {
      setUploadError(
        `File is too large (${formatFileSize(file.size)}). The maximum allowed size is 10 MB.`
      )
      setSelectedFile(null)
      return
    }

    setSelectedFile(file)
  }

  // Drag and Drop handlers
  const handleDragOver = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }

  const handleDragLeave = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
    setUploadError('')

    const files = e.dataTransfer.files
    if (files && files.length > 0) {
      const file = files[0]
      if (!file.name.toLowerCase().endsWith('.pdf') && file.type !== 'application/pdf') {
        setUploadError('Invalid file type. Only PDF documents are supported.')
        setSelectedFile(null)
        return
      }

      if (file.size > 10 * 1024 * 1024) {
        setUploadError(
          `File is too large (${formatFileSize(file.size)}). The maximum allowed size is 10 MB.`
        )
        setSelectedFile(null)
        return
      }

      setSelectedFile(file)
    }
  }

  // Trigger file browser click
  const triggerFileBrowser = () => {
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
      fileInputRef.current.click()
    }
  }

  // Clear selected file
  const handleClearFile = (e) => {
    e.stopPropagation()
    setSelectedFile(null)
    setUploadError('')
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  // Reset all and upload another proposal
  const handleReset = () => {
    setSelectedFile(null)
    setExtractionResult(null)
    setUploadError('')
    setShowFullText(false)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  // 2. Upload file to backend and extract text
  const handleUploadAndAnalyze = async () => {
    if (!selectedFile) {
      setUploadError('No file selected. Please select an R&D proposal PDF.')
      return
    }

    setIsUploading(true)
    setUploadError('')
    setExtractionResult(null)

    const formData = new FormData()
    formData.append('file', selectedFile)

    try {
      const response = await fetch(`${API_BASE_URL}/api/upload`, {
        method: 'POST',
        body: formData,
      })

      const data = await response.json()

      if (!response.ok) {
        // Extract server error detail
        const errorMessage =
          data && data.detail
            ? data.detail
            : `Server returned error (${response.status}: ${response.statusText})`
        throw new Error(errorMessage)
      }

      // Successful extraction
      setExtractionResult(data)
    } catch (err) {
      setUploadError(err.message || 'An unexpected error occurred during extraction.')
    } finally {
      setIsUploading(false)
    }
  }

  // Compute text preview string (first ~1500 chars)
  const PREVIEW_LIMIT = 1500
  const isTextTruncated =
    extractionResult && extractionResult.full_text.length > PREVIEW_LIMIT

  const displayedText =
    extractionResult &&
    (showFullText || !isTextTruncated
      ? extractionResult.full_text
      : extractionResult.full_text.slice(0, PREVIEW_LIMIT) +
        `\n\n... [Preview truncated: showing first ${PREVIEW_LIMIT.toLocaleString()} of ${extractionResult.char_count.toLocaleString()} characters. Click "Show Full Text" below to expand.]`)

  return (
    <div className="container">
      {/* Header section with branding and status indicator */}
      <header className="header">
        <div className="brand-group">
          <span className="brick-badge">Brick 2: PDF Upload & Text Extraction</span>
          <h1 className="title">
            AI-Based Multi-Agent R&D Proposal Evaluation System
          </h1>
          <p className="description">
            An intelligent evaluation platform designed to assess research and
            development proposals across novelty, technical feasibility,
            financial viability, and strategic impact.
          </p>
        </div>

        {/* Backend Connectivity Status Card */}
        <div className="status-card">
          <div className="status-header">
            <span className="status-label">Backend Status</span>
            <button
              className="refresh-btn"
              onClick={checkBackendHealth}
              title="Refresh health check"
              disabled={backendStatus === 'checking'}
            >
              {backendStatus === 'checking' ? 'Checking...' : 'Refresh'}
            </button>
          </div>

          <div className="status-display">
            {backendStatus === 'connected' && (
              <span className="status-badge connected">
                <span className="dot dot-connected"></span>
                Connected
              </span>
            )}

            {backendStatus === 'disconnected' && (
              <span className="status-badge disconnected">
                <span className="dot dot-disconnected"></span>
                Not connected
              </span>
            )}

            {backendStatus === 'checking' && (
              <span className="status-badge checking">
                <span className="dot dot-checking"></span>
                Checking connection...
              </span>
            )}
          </div>

          <p className="endpoint-info">
            Health Check: <code>{API_BASE_URL}/api/health</code>
          </p>

          {healthError && (
            <p className="error-note">
              <strong>Connection Error:</strong> {healthError}
            </p>
          )}
        </div>
      </header>

      {/* Main Content Area */}
      <main className="main-content">
        {/* Error Notification Banner */}
        {uploadError && (
          <div className="alert-banner error" role="alert">
            <div className="alert-icon-wrap">
              <svg
                className="alert-icon"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="8" x2="12" y2="12"></line>
                <line x1="12" y1="16" x2="12.01" y2="16"></line>
              </svg>
            </div>
            <div className="alert-body">
              <strong className="alert-title">Upload / Extraction Error</strong>
              <p className="alert-text">{uploadError}</p>
            </div>
            <button
              className="alert-dismiss-btn"
              onClick={() => setUploadError('')}
              title="Dismiss error"
            >
              &times;
            </button>
          </div>
        )}

        {/* Upload & File Selection Area (shown when no result yet) */}
        {!extractionResult && (
          <section className="upload-section">
            <div
              className={`upload-dropzone ${isDragging ? 'dragging' : ''} ${
                selectedFile ? 'has-file' : ''
              }`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={triggerFileBrowser}
            >
              {/* Hidden HTML5 File Picker */}
              <input
                type="file"
                ref={fileInputRef}
                accept=".pdf,application/pdf"
                onChange={handleFileChange}
                style={{ display: 'none' }}
              />

              <div className="upload-icon-wrapper">
                <svg
                  className="upload-icon"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.75"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                  <polyline points="14 2 14 8 20 8"></polyline>
                  <line x1="12" y1="18" x2="12" y2="12"></line>
                  <polyline points="9 15 12 12 15 15"></polyline>
                </svg>
              </div>

              {!selectedFile ? (
                <>
                  <h2 className="upload-title">Select R&D Proposal PDF</h2>
                  <p className="upload-subtitle">
                    Drag and drop your research proposal here, or{' '}
                    <span className="browse-link">browse files</span>
                  </p>
                  <p className="upload-constraints">
                    Supports PDF documents up to 10 MB (processed strictly in-memory)
                  </p>
                </>
              ) : (
                <div className="selected-file-card" onClick={(e) => e.stopPropagation()}>
                  <div className="file-info-header">
                    <span className="pdf-tag">PDF</span>
                    <div className="file-meta">
                      <p className="file-name" title={selectedFile.name}>
                        {selectedFile.name}
                      </p>
                      <p className="file-size">{formatFileSize(selectedFile.size)}</p>
                    </div>
                    <button
                      className="remove-file-btn"
                      onClick={handleClearFile}
                      title="Remove selected file"
                      type="button"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Action Bar */}
            <div className="action-bar">
              <button
                className="primary-btn"
                onClick={handleUploadAndAnalyze}
                disabled={!selectedFile || isUploading}
              >
                {isUploading ? (
                  <>
                    <span className="spinner"></span>
                    Extracting Text...
                  </>
                ) : (
                  'Upload & Analyze'
                )}
              </button>

              {selectedFile && !isUploading && (
                <button
                  className="secondary-btn"
                  onClick={triggerFileBrowser}
                  type="button"
                >
                  Change File
                </button>
              )}
            </div>

            {/* Loading Indicator Notification */}
            {isUploading && (
              <div className="loading-card">
                <div className="loading-spinner-ring"></div>
                <div className="loading-text-group">
                  <p className="loading-heading">Extracting text from PDF...</p>
                  <p className="loading-subheading">
                    Reading pages page-by-page in memory with PyMuPDF.
                  </p>
                </div>
              </div>
            )}
          </section>
        )}

        {/* Extraction Results & Preview Area */}
        {extractionResult && (
          <section className="results-section">
            <div className="results-header-card">
              <div className="results-title-group">
                <div className="success-badge">
                  <svg
                    className="check-icon"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <polyline points="20 6 9 17 4 12"></polyline>
                  </svg>
                  Extraction Complete
                </div>
                <h2 className="results-doc-title">{extractionResult.filename}</h2>
              </div>

              <button className="secondary-btn" onClick={handleReset}>
                Upload Another Proposal
              </button>
            </div>

            {/* Metrics Grid */}
            <div className="metrics-grid">
              <div className="metric-card">
                <span className="metric-label">Total Pages</span>
                <span className="metric-value">{extractionResult.page_count}</span>
              </div>
              <div className="metric-card">
                <span className="metric-label">Total Characters</span>
                <span className="metric-value">
                  {extractionResult.char_count.toLocaleString()}
                </span>
              </div>
              <div className="metric-card">
                <span className="metric-label">Processing Mode</span>
                <span className="metric-value text-sm">In-Memory (0 disk writes)</span>
              </div>
            </div>

            {/* Text Preview Area */}
            <div className="preview-card">
              <div className="preview-header">
                <div className="preview-heading-wrap">
                  <h3 className="preview-title">Extracted Text Preview</h3>
                  <span className="preview-subtitle">
                    {showFullText
                      ? `Showing all ${extractionResult.char_count.toLocaleString()} characters`
                      : `Showing first ${Math.min(
                          PREVIEW_LIMIT,
                          extractionResult.char_count
                        ).toLocaleString()} characters`}
                  </span>
                </div>

                {isTextTruncated && (
                  <button
                    className="toggle-text-btn"
                    onClick={() => setShowFullText(!showFullText)}
                  >
                    {showFullText ? 'Show First 1,500 Chars' : 'Show Full Text'}
                  </button>
                )}
              </div>

              <div className="preview-content-box">
                <pre className="extracted-text-display">{displayedText}</pre>
              </div>
            </div>

            {/* Page Breakdown Accordion / List */}
            {extractionResult.pages && extractionResult.pages.length > 0 && (
              <div className="pages-breakdown-card">
                <h3 className="breakdown-title">
                  Page Breakdown ({extractionResult.pages.length} Pages)
                </h3>
                <div className="pages-list">
                  {extractionResult.pages.map((p) => (
                    <details key={p.page_number} className="page-item">
                      <summary className="page-summary">
                        <span className="page-badge">Page {p.page_number}</span>
                        <span className="page-char-count">
                          {p.text.length.toLocaleString()} characters
                        </span>
                      </summary>
                      <pre className="page-text-content">
                        {p.text.trim() ? p.text : '[No text on this page]'}
                      </pre>
                    </details>
                  ))}
                </div>
              </div>
            )}
          </section>
        )}
      </main>

      {/* Footer */}
      <footer className="footer">
        <p>
          AI-Based Multi-Agent R&D Proposal Evaluation System • Brick 2: PDF Upload & Text Extraction
        </p>
      </footer>
    </div>
  )
}

export default App
