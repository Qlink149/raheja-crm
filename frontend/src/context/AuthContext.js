import React, { createContext, useContext, useState, useEffect } from "react";
import axios from "axios";
import { getApiBase } from "../lib/api";

const API = getApiBase();

const AuthContext = createContext(null);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem("token"));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (token) {
      axios.defaults.headers.common["Authorization"] = `Bearer ${token}`;
      fetchUser();
    } else {
      setLoading(false);
    }
  }, [token]);

  const fetchUser = async () => {
    try {
      const response = await axios.get(`${API}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setUser(response.data);
    } catch (error) {
      console.error("Failed to fetch user:", error);
      logout();
    } finally {
      setLoading(false);
    }
  };

  const login = async (email, password) => {
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
  };

  const logout = async () => {
    try {
      if (token) {
        await axios.post(
          `${API}/auth/logout`,
          {},
          { headers: { Authorization: `Bearer ${token}` } }
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
  };

  const role = user?.role || "sales";
  const isAdmin = role === "admin";

  const value = {
    user,
    token,
    loading,
    login,
    logout,
    role,
    isAdmin,
    isAuthenticated: !!token && !!user,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export default AuthContext;
