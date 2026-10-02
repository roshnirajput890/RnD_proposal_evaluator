/**
 * Application Configuration
 *
 * Central configuration file for frontend settings and API endpoints.
 * Keeping the API base URL in one place makes it easy to update or point
 * to different backend environments (local, staging, production).
 */

// Base URL for the FastAPI backend server
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
