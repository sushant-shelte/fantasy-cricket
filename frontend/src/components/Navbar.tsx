import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

export default function Navbar() {
  const { profile, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <nav className="bg-gradient-to-r from-indigo-950 via-indigo-800 to-indigo-600 text-white shadow-lg sticky top-0 z-50">
      <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
        <Link
          to="/dashboard"
          className="flex items-center gap-2 font-bold text-lg tracking-tight"
        >
          <svg
            className="w-7 h-7"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="18" cy="6" r="3"/>
            <path d="M14 10L4 20"/>
            <path d="M6 16l4 4"/>
          </svg>
          Fantasy Cricket
        </Link>
        {profile && (
          <div className="flex items-center gap-3">
            <span className="text-sm text-indigo-200 hidden sm:block">
              {profile.name}
            </span>
            {profile.role === 'admin' && (
              <Link
                to="/admin"
                className="text-xs bg-amber-500/20 text-amber-300 px-2.5 py-1 rounded-lg font-medium hover:bg-amber-500/30 transition"
              >
                Admin
              </Link>
            )}
            <button
              onClick={handleLogout}
              className="text-xs bg-white/10 hover:bg-white/20 px-3 py-1.5 rounded-lg transition font-medium"
            >
              Logout
            </button>
          </div>
        )}
      </div>
    </nav>
  );
}
