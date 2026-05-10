import axios from "axios";

const rawRoot = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");

/** Base URL for `/api/*` routes (matches other pages: `${BACKEND_URL}/api`). */
export const getApiBase = () => (rawRoot ? `${rawRoot}/api` : "/api");

/** True when REACT_APP_BACKEND_URL points at the FastAPI server (required for this app). */
export const isBackendConfigured = () => Boolean(rawRoot);

/** Shared Axios instance for authenticated app calls. */
export const api = axios.create({
  baseURL: getApiBase(),
  timeout: 120000,
});
