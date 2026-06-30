import React, { Suspense, lazy } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { Toaster } from "./components/ui/sonner";
import PremiumLockedPage from "./components/shared/PremiumLockedPage";
import { isFeatureLocked, isVcPreviewMode } from "./lib/featureAccess";

const LoginPage = lazy(() => import("./pages/LoginPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const VirtualCustomerPage = lazy(() => import("./pages/VirtualCustomerPage"));
const VirtualCustomerPreview = lazy(() => import("./pages/VirtualCustomerPreview"));
const CustomerDetailPage = lazy(() => import("./pages/CustomerDetailPage"));
const CampaignsPage = lazy(() => import("./pages/CampaignsPage"));
const AICallingPage = lazy(() => import("./pages/AICallingPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const SalesDashboardPage = lazy(() => import("./pages/SalesDashboardPage"));
const MyDashboardPage = lazy(() => import("./pages/MyDashboardPage"));
const MarketingDashboardPage = lazy(() => import("./pages/MarketingDashboardPage"));
const NotificationsPage = lazy(() => import("./pages/NotificationsPage"));
const DashboardLayout = lazy(() => import("./components/layout/DashboardLayout"));

const LoadingScreen = () => (
  <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: 'var(--bg-primary)' }}>
    <p className="text-[#C5A059] animate-pulse">Loading...</p>
  </div>
);

const PageSuspense = ({ children }) => (
  <Suspense fallback={<LoadingScreen />}>{children}</Suspense>
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

const SalesRoute = ({ children }) => {
  const { isAuthenticated, loading, isAdmin } = useAuth();
  if (loading) return <LoadingScreen />;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (isAdmin) return <Navigate to="/dashboard" replace />;
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

const FeatureGate = ({ featureKey, lockedTitle, children }) =>
  isFeatureLocked(featureKey) ? (
    <PremiumLockedPage title={lockedTitle} />
  ) : (
    children
  );

function AppRoutes() {
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <PublicRoute>
            <PageSuspense>
              <LoginPage />
            </PageSuspense>
          </PublicRoute>
        }
      />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <PageSuspense>
              <DashboardLayout />
            </PageSuspense>
          </ProtectedRoute>
        }
      >
        <Route index element={<HomeRedirect />} />
        <Route
          path="dashboard"
          element={
            <AdminRoute>
              <PageSuspense>
                <DashboardPage />
              </PageSuspense>
            </AdminRoute>
          }
        />
        <Route
          path="my-dashboard"
          element={
            <SalesRoute>
              <PageSuspense>
                <MyDashboardPage />
              </PageSuspense>
            </SalesRoute>
          }
        />
        <Route
          path="virtual-customer"
          element={
            <FeatureGate featureKey="virtualCustomer" lockedTitle="Virtual Customer">
              <PageSuspense>
                {isVcPreviewMode() ? <VirtualCustomerPreview /> : <VirtualCustomerPage />}
              </PageSuspense>
            </FeatureGate>
          }
        />
        <Route
          path="customer/:id"
          element={
            <PageSuspense>
              <CustomerDetailPage />
            </PageSuspense>
          }
        />
        <Route
          path="ai-calling"
          element={
            <PageSuspense>
              <AICallingPage />
            </PageSuspense>
          }
        />
        <Route
          path="campaigns"
          element={
            <AdminRoute>
              <PageSuspense>
                <CampaignsPage />
              </PageSuspense>
            </AdminRoute>
          }
        />
        <Route
          path="sales-dashboard"
          element={
            <AdminRoute>
              <FeatureGate featureKey="salesDashboard" lockedTitle="Sales Dashboard">
                <PageSuspense>
                  <SalesDashboardPage />
                </PageSuspense>
              </FeatureGate>
            </AdminRoute>
          }
        />
        <Route
          path="marketing-dashboard"
          element={
            <AdminRoute>
              <FeatureGate featureKey="marketingDashboard" lockedTitle="Marketing">
                <PageSuspense>
                  <MarketingDashboardPage />
                </PageSuspense>
              </FeatureGate>
            </AdminRoute>
          }
        />
        <Route
          path="notifications"
          element={
            <FeatureGate featureKey="notifications" lockedTitle="Notifications">
              <PageSuspense>
                <NotificationsPage />
              </PageSuspense>
            </FeatureGate>
          }
        />
        <Route
          path="settings"
          element={
            <AdminRoute>
              <PageSuspense>
                <SettingsPage />
              </PageSuspense>
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
        <Toaster position="top-right" />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
