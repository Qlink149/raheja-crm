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

export const notificationsAPI = {
  getAll: (params) => api.get("/notifications", { params }),
  markRead: (id) => api.put(`/notifications/${id}/read`),
  markAllRead: () => api.put("/notifications/read-all"),
};
