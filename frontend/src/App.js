import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { Toaster } from "./components/ui/sonner";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import VirtualCustomerPage from "./pages/VirtualCustomerPage";
import CustomerDetailPage from "./pages/CustomerDetailPage";
import CampaignsPage from "./pages/CampaignsPage";
import AICallingPage from "./pages/AICallingPage";
import SettingsPage from "./pages/SettingsPage";
import SalesDashboardPage from "./pages/SalesDashboardPage";
import MyDashboardPage from "./pages/MyDashboardPage";
import MarketingDashboardPage from "./pages/MarketingDashboardPage";
import NotificationsPage from "./pages/NotificationsPage";
import DashboardLayout from "./components/layout/DashboardLayout";

const LoadingScreen = () => (
  <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center">
    <p className="text-[#C5A059] animate-pulse">Loading...</p>
  </div>
);

const ProtectedRoute = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();
  if (loading) return <LoadingScreen />;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return children;
};

const AdminRoute = ({ children }) => {
  const { isAuthenticated, loading, isAdmin } = useAuth();
  if (loading) return <LoadingScreen />;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (!isAdmin) return <Navigate to="/my-dashboard" replace />;
  return children;
};

const HomeRedirect = () => {
  const { isAdmin, loading } = useAuth();
  if (loading) return <LoadingScreen />;
  return <Navigate to={isAdmin ? "/dashboard" : "/my-dashboard"} replace />;
};

const PublicRoute = ({ children }) => {
  const { isAuthenticated, loading, isAdmin } = useAuth();
  if (loading) return <LoadingScreen />;
  if (isAuthenticated) {
    return <Navigate to={isAdmin ? "/dashboard" : "/my-dashboard"} replace />;
  }
  return children;
};

function AppRoutes() {
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <PublicRoute>
            <LoginPage />
          </PublicRoute>
        }
      />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <DashboardLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<HomeRedirect />} />
        <Route
          path="dashboard"
          element={
            <AdminRoute>
              <DashboardPage />
            </AdminRoute>
          }
        />
        <Route path="my-dashboard" element={<MyDashboardPage />} />
        <Route path="virtual-customer" element={<VirtualCustomerPage />} />
        <Route path="customer/:id" element={<CustomerDetailPage />} />
        <Route path="ai-calling" element={<AICallingPage />} />
        <Route
          path="campaigns"
          element={
            <AdminRoute>
              <CampaignsPage />
            </AdminRoute>
          }
        />
        <Route
          path="sales-dashboard"
          element={
            <AdminRoute>
              <SalesDashboardPage />
            </AdminRoute>
          }
        />
        <Route
          path="marketing-dashboard"
          element={
            <AdminRoute>
              <MarketingDashboardPage />
            </AdminRoute>
          }
        />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route
          path="settings"
          element={
            <AdminRoute>
              <SettingsPage />
            </AdminRoute>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
        <Toaster
          position="top-right"
          toastOptions={{
            style: {
              background: "#1A1A1A",
              color: "#EDEDED",
              border: "1px solid rgba(255,255,255,0.1)",
            },
          }}
        />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
