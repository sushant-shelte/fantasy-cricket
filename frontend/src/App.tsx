import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './auth/AuthContext';
import { ProtectedRoute, AdminRoute } from './auth/ProtectedRoute';
import Navbar from './components/Navbar';
import { lazy, Suspense } from 'react';
import LoadingSpinner from './components/LoadingSpinner';

const Login = lazy(() => import('./pages/Login'));
const Register = lazy(() => import('./pages/Register'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const SelectTeam = lazy(() => import('./pages/SelectTeam'));
const ViewScores = lazy(() => import('./pages/ViewScores'));
const Leaderboard = lazy(() => import('./pages/Leaderboard'));
const PointsTable = lazy(() => import('./pages/PointsTable'));

const AdminLayout = lazy(() => import('./pages/admin/AdminLayout'));
const AdminDashboard = lazy(() => import('./pages/admin/AdminDashboard'));
const ManagePlayers = lazy(() => import('./pages/admin/ManagePlayers'));
const ManageMatches = lazy(() => import('./pages/admin/ManageMatches'));
const ManageUsers = lazy(() => import('./pages/admin/ManageUsers'));
const ScoreControl = lazy(() => import('./pages/admin/ScoreControl'));
const ManageTeams = lazy(() => import('./pages/admin/ManageTeams'));

function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900">
      <Navbar />
      <main className="max-w-6xl mx-auto px-4 py-6">{children}</main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Suspense fallback={<LoadingSpinner />}>
          <Routes>
            {/* Public */}
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />

            {/* Protected user routes */}
            <Route path="/dashboard" element={<ProtectedRoute><AppLayout><Dashboard /></AppLayout></ProtectedRoute>} />
            <Route path="/select-team/:matchId" element={<ProtectedRoute><AppLayout><SelectTeam /></AppLayout></ProtectedRoute>} />
            <Route path="/view-scores/:matchId" element={<ProtectedRoute><AppLayout><ViewScores /></AppLayout></ProtectedRoute>} />
            <Route path="/leaderboard" element={<ProtectedRoute><AppLayout><Leaderboard /></AppLayout></ProtectedRoute>} />
            <Route path="/points-table" element={<ProtectedRoute><AppLayout><PointsTable /></AppLayout></ProtectedRoute>} />

            {/* Admin routes with nested layout */}
            <Route path="/admin" element={<AdminRoute><AdminLayout /></AdminRoute>}>
              <Route index element={<AdminDashboard />} />
              <Route path="players" element={<ManagePlayers />} />
              <Route path="matches" element={<ManageMatches />} />
              <Route path="teams" element={<ManageTeams />} />
              <Route path="users" element={<ManageUsers />} />
              <Route path="scores" element={<ScoreControl />} />
            </Route>

            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </Suspense>
      </AuthProvider>
    </BrowserRouter>
  );
}
