import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import client from '../api/client';
import { useAuth } from '../auth/AuthContext';
import type { Match } from '../types';

export default function DashboardPage() {
  const [matches, setMatches] = useState<Match[]>([]);
  const [myTeams, setMyTeams] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);
  const { profile, logout } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([
      client.get('/api/matches'),
      client.get('/api/matches').then(async (res) => {
        // Check which matches user has picked a team for
        const teamSet = new Set<number>();
        for (const m of res.data) {
          try {
            const teamRes = await client.get(`/api/teams/my?match_id=${m.id}`);
            if (teamRes.data && teamRes.data.length > 0) teamSet.add(m.id);
          } catch { /* skip */ }
        }
        return teamSet;
      }),
    ])
      .then(([matchRes, teamSet]) => {
        setMatches(matchRes.data);
        setMyTeams(teamSet);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const formatDate = (dateStr: string, timeStr: string) => {
    try {
      const dt = new Date(`${dateStr}T${timeStr}`);
      return dt.toLocaleDateString('en-IN', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return `${dateStr} ${timeStr}`;
    }
  };

  const statusBadge = (status: Match['status']) => {
    switch (status) {
      case 'live':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-green-500/20 text-green-400 text-xs font-semibold rounded-full">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
            </span>
            LIVE
          </span>
        );
      case 'over':
        return (
          <span className="px-2.5 py-1 bg-slate-500/20 text-slate-400 text-xs font-semibold rounded-full">
            COMPLETED
          </span>
        );
      default:
        return (
          <span className="px-2.5 py-1 bg-indigo-500/20 text-indigo-300 text-xs font-semibold rounded-full">
            UPCOMING
          </span>
        );
    }
  };

  const matchAction = (match: Match) => {
    switch (match.status) {
      case 'future': {
        const hasTeam = myTeams.has(match.id);
        return (
          <Link
            to={`/select-team/${match.id}`}
            className={`inline-flex items-center gap-2 px-5 py-2.5 text-white text-sm font-semibold rounded-xl shadow-lg transition-all duration-200 ${
              hasTeam
                ? 'bg-amber-600 hover:bg-amber-700 shadow-amber-600/30'
                : 'bg-indigo-600 hover:bg-indigo-700 shadow-indigo-600/30'
            }`}
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              {hasTeam ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
              )}
            </svg>
            {hasTeam ? 'Edit Team' : 'Pick Team'}
          </Link>
        );
      }
      case 'live':
        return (
          <Link
            to={`/view-scores/${match.id}`}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-green-600 hover:bg-green-700 text-white text-sm font-semibold rounded-xl shadow-lg shadow-green-600/30 transition-all duration-200"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
            Live Scores
          </Link>
        );
      case 'over':
        return (
          <Link
            to={`/view-scores/${match.id}`}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-slate-600 hover:bg-slate-700 text-white text-sm font-semibold rounded-xl shadow-lg shadow-slate-600/20 transition-all duration-200"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            View Scores
          </Link>
        );
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-indigo-950 to-slate-900">
      {/* Header */}
      <header className="sticky top-0 z-30 bg-slate-950/80 backdrop-blur-lg border-b border-white/10">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-white">Fantasy Cricket</h1>
            <p className="text-sm text-indigo-300">
              Welcome, <span className="text-green-400 font-medium">{profile?.name || 'Player'}</span>
            </p>
          </div>
          <button
            onClick={handleLogout}
            className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white text-sm font-medium rounded-xl border border-white/10 transition-all"
          >
            Logout
          </button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        {/* Quick Actions */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Link
            to="/leaderboard"
            className="flex flex-col items-center gap-2 p-4 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/20 rounded-2xl transition-all duration-200 group"
          >
            <div className="w-10 h-10 bg-amber-500/20 rounded-xl flex items-center justify-center group-hover:scale-110 transition-transform">
              <svg className="w-5 h-5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
              </svg>
            </div>
            <span className="text-amber-300 text-sm font-medium">Leaderboard</span>
          </Link>

          <Link
            to="/points-table"
            className="flex flex-col items-center gap-2 p-4 bg-indigo-500/10 hover:bg-indigo-500/20 border border-indigo-500/20 rounded-2xl transition-all duration-200 group"
          >
            <div className="w-10 h-10 bg-indigo-500/20 rounded-xl flex items-center justify-center group-hover:scale-110 transition-transform">
              <svg className="w-5 h-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
            </div>
            <span className="text-indigo-300 text-sm font-medium">Points Table</span>
          </Link>

          <button
            onClick={handleLogout}
            className="flex flex-col items-center gap-2 p-4 bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 rounded-2xl transition-all duration-200 group col-span-2 sm:col-span-1"
          >
            <div className="w-10 h-10 bg-red-500/20 rounded-xl flex items-center justify-center group-hover:scale-110 transition-transform">
              <svg className="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
            </div>
            <span className="text-red-300 text-sm font-medium">Logout</span>
          </button>
        </div>

        {/* Matches */}
        <div>
          <h2 className="text-lg font-semibold text-white mb-4">Matches</h2>

          {loading ? (
            <div className="flex justify-center py-16">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-400" />
            </div>
          ) : matches.length === 0 ? (
            <div className="text-center py-16 text-indigo-300">No matches available yet.</div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              {matches.map((match) => (
                <div
                  key={match.id}
                  className="bg-white/5 hover:bg-white/[0.08] border border-white/10 rounded-2xl p-5 transition-all duration-200"
                >
                  <div className="flex items-center justify-between mb-3">
                    {statusBadge(match.status)}
                    {match.locked && (
                      <span className="text-xs text-amber-400 flex items-center gap-1">
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                        </svg>
                        Locked
                      </span>
                    )}
                  </div>

                  <div className="flex items-center justify-center gap-3 mb-3">
                    <span className="text-white font-bold text-lg">{match.team1}</span>
                    <span className="text-indigo-400 text-sm font-medium px-2 py-0.5 bg-indigo-500/20 rounded-lg">vs</span>
                    <span className="text-white font-bold text-lg">{match.team2}</span>
                  </div>

                  <p className="text-indigo-300 text-sm text-center mb-4">
                    {formatDate(match.match_date, match.match_time)}
                  </p>

                  <div className="flex justify-center">{matchAction(match)}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
