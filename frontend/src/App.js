import { useState, useEffect } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import VirtualCustomerPage from "./pages/VirtualCustomerPage";
import CustomerDetailPage from "./pages/CustomerDetailPage";
import CampaignsPage from "./pages/CampaignsPage";
import AICallingPage from "./pages/AICallingPage";
import SettingsPage from "./pages/SettingsPage";

const STORAGE_KEY = "rustomjee.currentUser";

function App() {
  const [currentUser, setCurrentUser] = useState(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });

  useEffect(() => {
    if (currentUser) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(currentUser));
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  }, [currentUser]);

  const handleLogin = (user) => setCurrentUser(user);
  const handleLogout = () => setCurrentUser(null);

  const isAuthenticated = Boolean(currentUser);

  return (
    <div className="App min-h-screen bg-[#0A0A0A]">
      <Toaster
        position="top-right"
        theme="dark"
        richColors
        closeButton
        expand={false}
        toastOptions={{
          style: {
            background: "rgba(20, 20, 20, 0.92)",
            border: "1px solid rgba(197, 160, 89, 0.25)",
            color: "#F5F5F5",
            fontFamily: "Inter, system-ui, sans-serif",
          },
          className: "rounded-xl backdrop-blur",
        }}
      />
      <BrowserRouter>
        <Routes>
          <Route
            path="/"
            element={
              isAuthenticated ? (
                <Navigate to="/dashboard" replace />
              ) : (
                <LoginPage onLogin={handleLogin} />
              )
            }
          />
          <Route
            path="/dashboard"
            element={
              isAuthenticated ? (
                <DashboardPage onLogout={handleLogout} currentUser={currentUser} />
              ) : (
                <Navigate to="/" replace />
              )
            }
          />
          <Route
            path="/virtual-customer"
            element={
              isAuthenticated ? (
                <VirtualCustomerPage onLogout={handleLogout} currentUser={currentUser} />
              ) : (
                <Navigate to="/" replace />
              )
            }
          />
          <Route
            path="/customer/:id"
            element={
              isAuthenticated ? (
                <CustomerDetailPage onLogout={handleLogout} currentUser={currentUser} />
              ) : (
                <Navigate to="/" replace />
              )
            }
          />
          <Route
            path="/ai-calling"
            element={
              isAuthenticated ? (
                <AICallingPage onLogout={handleLogout} currentUser={currentUser} />
              ) : (
                <Navigate to="/" replace />
              )
            }
          />
          <Route
            path="/campaigns"
            element={
              isAuthenticated ? (
                <CampaignsPage onLogout={handleLogout} currentUser={currentUser} />
              ) : (
                <Navigate to="/" replace />
              )
            }
          />
          <Route
            path="/settings"
            element={
              isAuthenticated ? (
                <SettingsPage onLogout={handleLogout} currentUser={currentUser} />
              ) : (
                <Navigate to="/" replace />
              )
            }
          />
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
