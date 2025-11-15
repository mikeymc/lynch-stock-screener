// API configuration
// In development (Vite dev server), use localhost:5001
// In production (deployed), use relative URLs since Flask serves the frontend
const API_BASE = import.meta.env.DEV
  ? 'http://localhost:5001/api'
  : '/api'

export { API_BASE }
