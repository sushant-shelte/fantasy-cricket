import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import client from '../api/client';
import { useAuth } from '../auth/AuthContext';
import type { Match } from '../types';

type MatchTab = 'today' | 'upcoming' | 'completed';

export default function DashboardPage() {
  const [matches, setMatches] = useState<Match[]>([]);
  const [myTeams, setMyTeams] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<MatchTab>('today');
  const { profile } = useAuth();

  useEffect(() => {
    Promise.all([
      client.get('/api/matches'),
      client.get('/api/teams/my-matches'),
    ])
      .then(([matchRes, teamsRes]) => {
        setMatches(matchRes.data);
        setMyTeams(new Set(teamsRes.data));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const formatDate = (dateStr: string, timeStr: string) => {
    try {
      const dt = new Date(`${dateStr}T${timeStr}`);
      return dt.toLocaleDateString('en-IN', {
        day: 'numeric', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
      });
    } catch { return `${dateStr} ${timeStr}`; }
  };

  // Get today's date in IST
  const todayIST = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' });

  // Split matches into tabs
  const todayMatches = matches.filter(m => m.match_date === todayIST);
  const upcomingMatches = matches.filter(m => m.status === 'future' && m.match_date !== todayIST);
  const completedMatches = matches.filter(m => m.status === 'over');

  // Auto-select tab: if today has matches show today, else upcoming
  useEffect(() => {
    if (!loading) {
      if (todayMatches.length > 0) setTab('today');
      else if (upcomingMatches.length > 0) setTab('upcoming');
      else setTab('completed');
    }
  }, [loading]);

  const currentMatches = tab === 'today' ? todayMatches : tab === 'upcoming' ? upcomingMatches : completedMatches;

  const statusBadge = (status: Match['status']) => {
    switch (status) {
      case 'live':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-green-500/15 text-green-400 text-xs font-semibold rounded-full border border-green-500/20">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
            </span>
            LIVE
          </span>
        );
      case 'over':
        return <span className="px-2.5 py-1 bg-slate-500/15 text-slate-400 text-xs font-semibold rounded-full border border-slate-500/20">COMPLETED</span>;
      default:
        return <span className="px-2.5 py-1 bg-blue-500/15 text-blue-400 text-xs font-semibold rounded-full border border-blue-500/20">UPCOMING</span>;
    }
  };

  const matchAction = (match: Match) => {
    switch (match.status) {
      case 'future': {
        const hasTeam = myTeams.has(match.id);
        return (
          <Link to={`/select-team/${match.id}`}
            className={`inline-flex items-center gap-2 px-5 py-2.5 text-white text-sm font-semibold rounded-xl transition-all ${
              hasTeam ? 'bg-amber-500 hover:bg-amber-400 shadow-lg shadow-amber-500/20' : 'bg-indigo-500 hover:bg-indigo-400 shadow-lg shadow-indigo-500/20'
            }`}>
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              {hasTeam
                ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                : <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />}
            </svg>
            {hasTeam ? 'Edit Team' : 'Pick Team'}
          </Link>
        );
      }
      case 'live':
        return (
          <div className="flex gap-2">
            <Link to={`/view-scores/${match.id}`}
              className="inline-flex items-center gap-2 px-4 py-2.5 bg-green-500 hover:bg-green-400 text-white text-sm font-semibold rounded-xl shadow-lg shadow-green-500/20 transition-all">
              Live Scores
            </Link>
            {myTeams.has(match.id) && (
              <Link to={`/view-scores/${match.id}?tab=myteam`}
                className="inline-flex items-center gap-1 px-3 py-2.5 bg-white/10 hover:bg-white/15 text-white/70 text-xs font-medium rounded-xl border border-white/10 transition-all">
                My Team
              </Link>
            )}
          </div>
        );
      case 'over':
        return (
          <div className="flex gap-2">
            <Link to={`/view-scores/${match.id}`}
              className="inline-flex items-center gap-2 px-4 py-2 bg-slate-600 hover:bg-slate-500 text-white text-sm font-medium rounded-xl transition-all">
              View Scores
            </Link>
            {myTeams.has(match.id) && (
              <Link to={`/view-scores/${match.id}?tab=myteam`}
                className="inline-flex items-center gap-1 px-3 py-2 bg-white/10 hover:bg-white/15 text-white/70 text-xs font-medium rounded-xl border border-white/10 transition-all">
                My Team
              </Link>
            )}
          </div>
        );
    }
  };

  const tabs: { key: MatchTab; label: string; count: number }[] = [
    { key: 'today', label: "Today", count: todayMatches.length },
    { key: 'upcoming', label: 'Upcoming', count: upcomingMatches.length },
    { key: 'completed', label: 'Completed', count: completedMatches.length },
  ];

  return (
    <div className="-mx-4 -mt-6">
      {/* Hero with Sachin background */}
      <div className="relative overflow-hidden rounded-b-3xl mb-6">
        <div className="absolute inset-0">
          <img src="/sachin.png" alt="" className="w-full h-full object-cover opacity-40" />
          <div className="absolute inset-0 bg-gradient-to-b from-black/40 via-black/60 to-slate-900" />
        </div>
        <div className="relative z-10 px-4 pt-10 pb-8">
          <h2 className="text-2xl sm:text-3xl font-extrabold text-white">
            Welcome, <span className="text-green-400">{profile?.name || 'Player'}</span>
          </h2>
          <p className="text-white/40 text-sm mt-1">Hippies Mahasangram</p>

          {/* Quick Actions */}
          <div className="grid grid-cols-2 gap-3 mt-6">
          <Link to="/leaderboard"
            className="flex flex-col items-center gap-2 p-4 bg-amber-500/10 hover:bg-amber-500/15 border border-amber-500/20 rounded-2xl transition-all group">
            <div className="w-10 h-10 bg-amber-500/20 rounded-xl flex items-center justify-center group-hover:scale-110 transition-transform">
              <svg className="w-5 h-5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
              </svg>
            </div>
            <span className="text-amber-300 text-sm font-medium">Leaderboard</span>
          </Link>
          <Link to="/points-table"
            className="flex flex-col items-center gap-2 p-4 bg-indigo-500/10 hover:bg-indigo-500/15 border border-indigo-500/20 rounded-2xl transition-all group">
            <div className="w-10 h-10 bg-indigo-500/20 rounded-xl flex items-center justify-center group-hover:scale-110 transition-transform">
              <svg className="w-5 h-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
            </div>
            <span className="text-indigo-300 text-sm font-medium">Points Table</span>
          </Link>
          </div>
        </div>
      </div>

      <div className="px-4 space-y-6">
        {/* Tabs */}
        <div className="flex items-center gap-1 bg-white/5 rounded-xl p-1 border border-white/10">
          {tabs.map(t => (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                tab === t.key
                  ? 'bg-indigo-500 text-white shadow-lg shadow-indigo-500/20'
                  : 'text-indigo-300 hover:text-white hover:bg-white/5'
              }`}>
              {t.label}
              <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                tab === t.key ? 'bg-white/20' : 'bg-white/10'
              }`}>{t.count}</span>
            </button>
          ))}
        </div>

        {/* Match Cards */}
        {loading ? (
          <div className="flex justify-center py-16">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-400" />
          </div>
        ) : currentMatches.length === 0 ? (
          <div className="text-center py-12 text-indigo-400 text-sm">
            {tab === 'today' ? "No matches today." : tab === 'upcoming' ? 'No upcoming matches.' : 'No completed matches yet.'}
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {currentMatches.map((match) => (
              <div key={match.id}
                className="bg-white/5 hover:bg-white/[0.08] border border-white/10 rounded-2xl p-5 transition-all duration-200 backdrop-blur-sm">
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
                <div className="flex items-center justify-center gap-3 mb-2">
                  <span className="text-white font-bold text-lg">{match.team1}</span>
                  <span className="text-indigo-400 text-sm font-medium px-2 py-0.5 bg-indigo-500/15 rounded-lg">vs</span>
                  <span className="text-white font-bold text-lg">{match.team2}</span>
                </div>
                <p className="text-indigo-300/70 text-xs text-center mb-3">
                  {formatDate(match.match_date, match.match_time)}
                </p>
                <div className="flex justify-center">{matchAction(match)}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="text-center text-white/10 text-xs py-6">
        Built by Sushant & Rupesh
      </div>
    </div>
  );
}
