import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useMemo,
  useCallback,
} from "react";
import axios from "axios";
import { getApiBase } from "../lib/api";

const API = getApiBase();

const AuthStateContext = createContext(null);
const AuthActionsContext = createContext(null);

export const useAuth = () => {
  const state = useContext(AuthStateContext);
  const actions = useContext(AuthActionsContext);
  if (!state || !actions) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return { ...state, ...actions };
};

export const useAuthState = () => {
  const context = useContext(AuthStateContext);
  if (!context) {
    throw new Error("useAuthState must be used within an AuthProvider");
  }
  return context;
};

export const useAuthActions = () => {
  const context = useContext(AuthActionsContext);
  if (!context) {
    throw new Error("useAuthActions must be used within an AuthProvider");
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem("token"));
  const [loading, setLoading] = useState(true);

  const logout = useCallback(async () => {
    try {
      const currentToken = localStorage.getItem("token");
      if (currentToken) {
        await axios.post(
          `${API}/auth/logout`,
          {},
          { headers: { Authorization: `Bearer ${currentToken}` } }
        );
      }
    } catch {
      /* session clear locally even if API fails */
    }
    localStorage.removeItem("token");
    localStorage.removeItem("refresh_token");
    setToken(null);
    setUser(null);
    delete axios.defaults.headers.common["Authorization"];
  }, []);

  const fetchUser = useCallback(
    async (authToken) => {
      try {
        const response = await axios.get(`${API}/auth/me`, {
          headers: { Authorization: `Bearer ${authToken}` },
        });
        setUser(response.data);
      } catch (error) {
        console.error("Failed to fetch user:", error);
        logout();
      } finally {
        setLoading(false);
      }
    },
    [logout]
  );

  useEffect(() => {
    if (token) {
      axios.defaults.headers.common["Authorization"] = `Bearer ${token}`;
      fetchUser(token);
    } else {
      setLoading(false);
    }
  }, [token, fetchUser]);

  const login = useCallback(async (email, password) => {
    const formData = new URLSearchParams();
    formData.append("username", email);
    formData.append("password", password);

    const response = await axios.post(`${API}/auth/login`, formData, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });

    const { access_token, refresh_token } = response.data;

    localStorage.setItem("token", access_token);
    localStorage.setItem("refresh_token", refresh_token);
    setToken(access_token);
    axios.defaults.headers.common["Authorization"] = `Bearer ${access_token}`;

    const userResponse = await axios.get(`${API}/auth/me`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    const me = userResponse.data;
    setUser(me);
    return me;
  }, []);

  const role = user?.role || "sales";
  const isAdmin = role === "admin";

  const stateValue = useMemo(
    () => ({
      user,
      token,
      loading,
      role,
      isAdmin,
      isAuthenticated: !!token && !!user,
    }),
    [user, token, loading, role, isAdmin]
  );

  const actionsValue = useMemo(
    () => ({
      login,
      logout,
    }),
    [login, logout]
  );

  return (
    <AuthStateContext.Provider value={stateValue}>
      <AuthActionsContext.Provider value={actionsValue}>
        {children}
      </AuthActionsContext.Provider>
    </AuthStateContext.Provider>
  );
};

export default AuthStateContext;
