import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./auth/AuthContext";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { Layout } from "./components/Layout";
import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";
import { CustomersPage } from "./pages/CustomersPage";
import { CustomerDetailPage } from "./pages/CustomerDetailPage";
import { NewCustomerPage } from "./pages/NewCustomerPage";
import { NewPaymentPage } from "./pages/NewPaymentPage";
import { NotificationsPage } from "./pages/NotificationsPage";
import { AuditPage } from "./pages/AuditPage";
import { SchemePage } from "./pages/SchemePage";
import { OverviewTab } from "./pages/scheme/OverviewTab";
import { CustomersTab } from "./pages/scheme/CustomersTab";
import { PoliciesTab } from "./pages/scheme/PoliciesTab";
import { PlansTab } from "./pages/scheme/PlansTab";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: (count, err: any) => (err?.status === 401 ? false : count < 1),
      staleTime: 10_000,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
              <Route index element={<DashboardPage />} />
              <Route path="customers" element={<CustomersPage />} />
              <Route path="customers/new" element={<NewCustomerPage />} />
              <Route path="customers/:id" element={<CustomerDetailPage />} />
              <Route path="payments/new" element={<NewPaymentPage />} />
              <Route path="notifications" element={<NotificationsPage />} />
              <Route path="audit" element={<AuditPage />} />
              <Route path="schemes/:schemeType" element={<SchemePage />}>
                <Route index element={<OverviewTab />} />
                <Route path="customers" element={<CustomersTab />} />
                <Route path="policies" element={<PoliciesTab />} />
                <Route path="plans" element={<PlansTab />} />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
