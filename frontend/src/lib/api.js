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

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && originalRequest && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        const refreshToken = localStorage.getItem("refresh_token");
        const response = await axios.post(`${getApiBase()}/auth/refresh`, {
          refresh_token: refreshToken,
        });
        const { access_token } = response.data;

        localStorage.setItem("token", access_token);
        api.defaults.headers.common["Authorization"] = `Bearer ${access_token}`;
        originalRequest.headers.Authorization = `Bearer ${access_token}`;

        return api(originalRequest);
      } catch (refreshError) {
        localStorage.removeItem("token");
        localStorage.removeItem("refresh_token");
        window.location.href = "/login";
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

export const analyticsAPI = {
  getSalesDashboard: () => api.get("/analytics/sales-dashboard"),
  getSalesRepLeads: (name, params) =>
    api.get("/analytics/sales-dashboard/rep-leads", { params: { name, ...params } }),
};

export const marketingAPI = {
  addSpend: (data) => api.post("/marketing/spends", data),
  getSpends: (params) => api.get("/marketing/spends", { params }),
  getDashboard: () => api.get("/marketing/dashboard"),
  deleteSpend: (id) => api.delete(`/marketing/spends/${id}`),
};

/**
 * Download a protected file via the authenticated API client (Bearer token).
 * @param {string} url - Path relative to api baseURL (e.g. /campaigns/.../download-original)
 * @param {string} filename - Suggested download filename
 */
export async function downloadAuthenticatedFile(url, filename) {
  const res = await api.get(url, { responseType: "blob" });
  const blob = res.data;
  const contentType = (res.headers["content-type"] || "").toLowerCase();

  if (contentType.includes("application/json") || blob.type?.includes("json")) {
    const text = await blob.text();
    let detail = "Download failed";
    try {
      const parsed = JSON.parse(text);
      detail = parsed.detail || detail;
    } catch {
      detail = text || detail;
    }
    throw new Error(typeof detail === "string" ? detail : "Download failed");
  }

  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename || "download";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

export const campaignsAPI = {
  getCurrent: (params) => api.get("/campaigns/current", { params }),
  getUploadHistory: (params) => api.get("/campaigns/current/upload-history", { params }),
  getUploadBatches: (params) => api.get("/campaigns/current/upload-batches", { params }),
  getBulkFutworkEligibleCount: () =>
    api.get("/campaigns/current/bulk-futwork-push/eligible-count"),
  startBulkFutworkPush: (data) =>
    api.post("/campaigns/current/bulk-futwork-push", data),
};

export const notificationsAPI = {
  getAll: (params) => api.get("/notifications", { params }),
  markRead: (id) => api.put(`/notifications/${id}/read`),
  markAllRead: () => api.put("/notifications/read-all"),
};

export const tasksAPI = {
  list: (params) => api.get("/tasks", { params }),
  create: (leadId, data) => api.post(`/leads/${leadId}/tasks`, data),
  createStandalone: (data) => api.post("/tasks", data),
  update: (taskId, data) => api.put(`/tasks/${taskId}`, data),
};

export const remindersAPI = {
  getRules: () => api.get("/reminders/rules"),
  updateRule: (ruleId, data) => api.put(`/reminders/rules/${ruleId}`, data),
  getHistory: (limit = 50) => api.get("/reminders/history", { params: { limit } }),
  trigger: () => api.post("/reminders/trigger"),
  sendManual: (data) => api.post("/reminders/send", data),
};
