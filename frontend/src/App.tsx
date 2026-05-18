import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import { DashboardPage } from "./pages/DashboardPage";
import { CustomersPage } from "./pages/CustomersPage";
import { CustomerDetailPage } from "./pages/CustomerDetailPage";
import { NewCustomerPage } from "./pages/NewCustomerPage";
import { NewPaymentPage } from "./pages/NewPaymentPage";
import { NotificationsPage } from "./pages/NotificationsPage";
import { AuditPage } from "./pages/AuditPage";
import { FieldApp } from "./pages/field/FieldApp";
import { DevicesPage } from "./pages/DevicesPage";

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
            <Route path="/login" element={<Navigate to="/" replace />} />
            <Route path="/field/*" element={<FieldApp />} />
            <Route path="/devices" element={<DevicesPage />} />
            <Route element={<Layout />}>
              <Route index element={<DashboardPage />} />
              <Route path="customers" element={<CustomersPage />} />
              <Route path="customers/new" element={<NewCustomerPage />} />
              <Route path="customers/:id" element={<CustomerDetailPage />} />
              <Route path="payments/new" element={<NewPaymentPage />} />
              <Route path="notifications" element={<NotificationsPage />} />
              <Route path="audit" element={<AuditPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
