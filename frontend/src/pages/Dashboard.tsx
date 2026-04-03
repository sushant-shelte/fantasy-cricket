import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import client from '../api/client';
import { useAuth } from '../auth/AuthContext';
import type { Match } from '../types';
import { getTeamTheme } from '../utils/teamTheme';
import { DashboardSkeleton } from '../components/Skeleton';

function useCountdown() {
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(id);
  }, []);

  const getCountdown = useCallback((match: Match) => {
    if (match.status !== 'future') return null;
    const matchTime = new Date(`${match.match_date}T${match.match_time}`).getTime();
    const diff = matchTime - now;
    if (diff <= 0) return null;

    const days = Math.floor(diff / 86400000);
    const hours = Math.floor((diff % 86400000) / 3600000);
    const mins = Math.floor((diff % 3600000) / 60000);

    if (days > 0) return `${days}d ${hours}h`;
    if (hours > 0) return `${hours}h ${mins}m`;
    return `${mins}m`;
  }, [now]);

  return getCountdown;
}

type MatchTab = 'today' | 'upcoming' | 'completed';
type TodayTeamLineupInfo = { announced: boolean; unannouncedSelected: number; substituteSelected: number };
type MatchContestant = { user_id: number; name: string; last_team_updated: string | null };

export default function DashboardPage() {
  const [matches, setMatches] = useState<Match[]>([]);
  const [myTeams, setMyTeams] = useState<Set<number>>(new Set());
  const [todayTeamLineup, setTodayTeamLineup] = useState<Record<number, TodayTeamLineupInfo>>({});
  const [showContestantsForMatch, setShowContestantsForMatch] = useState<Match | null>(null);
  const [matchContestants, setMatchContestants] = useState<MatchContestant[]>([]);
  const [contestantsLoading, setContestantsLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<MatchTab>('today');
  const { profile } = useAuth();
  const getCountdown = useCountdown();

  useEffect(() => {
    const loadDashboard = async () => {
      try {
        const [matchRes, teamsRes] = await Promise.all([
          client.get('/api/dashboard/matches'),
          client.get('/api/teams/my-matches'),
        ]);

        const loadedMatches: Match[] = matchRes.data;
        const loadedMyTeams = new Set<number>(teamsRes.data);
        setMatches(loadedMatches);
        setMyTeams(loadedMyTeams);

        const todayIST = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' });
        const todayMatches = loadedMatches.filter((match) => match.match_date === todayIST || match.status === 'live');
        const matchesToCheck = todayMatches.filter((match) => loadedMyTeams.has(match.id));

        if (matchesToCheck.length > 0) {
          const ids = matchesToCheck.map((match) => match.id).join(',');
          const lineupRes = await client.get(`/api/teams/my-lineup-statuses?match_ids=${ids}`);
          setTodayTeamLineup(lineupRes.data || {});
        } else {
          setTodayTeamLineup({});
        }
      } catch {
        setTodayTeamLineup({});
      } finally {
        setLoading(false);
      }
    };

    loadDashboard();
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

  const formatDateTime = (value: string | null) => {
    if (!value) return 'Unknown';
    try {
      const dt = new Date(value.replace(' ', 'T'));
      return dt.toLocaleString('en-IN', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return value;
    }
  };

  const openContestantsModal = async (match: Match) => {
    setShowContestantsForMatch(match);
    setContestantsLoading(true);
    setMatchContestants([]);
    try {
      const res = await client.get(`/api/teams/contestants?match_id=${match.id}`);
      setMatchContestants(res.data || []);
    } catch {
      setMatchContestants([]);
    } finally {
      setContestantsLoading(false);
    }
  };

  // Get today's date in IST
  const todayIST = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' });

  // Split matches into tabs
  // Today = today's matches + any live match (even if started yesterday)
  const todayMatches = matches.filter(m => m.match_date === todayIST || m.status === 'live');
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
        return <span className="px-2.5 py-1 bg-white/10 text-white/60 text-xs font-semibold rounded-full border border-white/10">UPCOMING</span>;
    }
  };

  const matchAction = (match: Match) => {
    switch (match.status) {
      case 'future': {
        const hasTeam = myTeams.has(match.id);
        return (
          <div className="flex flex-wrap justify-center gap-2">
            <Link to={`/select-team/${match.id}`}
              className={`inline-flex min-w-[8.5rem] items-center justify-center gap-2 px-5 py-2.5 text-sm font-semibold rounded-xl transition-all ${
                hasTeam ? 'bg-amber-500 hover:bg-amber-400 text-black shadow-lg shadow-amber-500/20' : 'bg-green-500 hover:bg-green-400 text-black shadow-lg shadow-green-500/20'
              }`}>
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                {hasTeam
                  ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  : <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />}
              </svg>
              {hasTeam ? 'Edit Team' : 'Pick Team'}
            </Link>
            <button
              type="button"
              onClick={() => openContestantsModal(match)}
              className="inline-flex min-w-[8.5rem] items-center justify-center gap-2 px-4 py-2.5 bg-white/10 hover:bg-white/15 text-white text-sm font-medium rounded-xl border border-white/10 transition-all"
            >
              Who&apos;s Playing
            </button>
          </div>
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
                Team Analysis
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
                Team Analysis
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
          <div className="absolute inset-0 bg-gradient-to-b from-black/40 via-black/60 to-black" />
        </div>
        <div className="relative z-10 px-4 pt-10 pb-8">
          <h2 className="text-2xl sm:text-3xl font-extrabold text-white">
            Welcome, <span className="inline-block max-w-[14rem] truncate align-bottom text-green-400 sm:max-w-[20rem]">{profile?.name || 'Player'}</span>
          </h2>
          <p className="text-white/40 text-sm mt-1">Hippies Mahasangram</p>

          {/* Quick Actions */}
          <div className="grid grid-cols-3 gap-3 mt-6">
          <Link to="/leaderboard"
            className="flex flex-col items-center gap-2 p-3 bg-amber-500/10 hover:bg-amber-500/15 border border-amber-500/20 rounded-2xl transition-all group">
            <div className="w-9 h-9 bg-amber-500/20 rounded-xl flex items-center justify-center group-hover:scale-110 transition-transform">
              <svg className="w-4 h-4 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
              </svg>
            </div>
            <span className="text-amber-300 text-xs font-medium">Leaderboard</span>
          </Link>
          <Link to="/points-table"
            className="flex flex-col items-center gap-2 p-3 bg-white/5 hover:bg-white/10 border border-white/10 rounded-2xl transition-all group">
            <div className="w-9 h-9 bg-white/10 rounded-xl flex items-center justify-center group-hover:scale-110 transition-transform">
              <svg className="w-4 h-4 text-white/70" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
            </div>
            <span className="text-white/50 text-xs font-medium">Points Table</span>
          </Link>
          <Link to="/rules"
            className="flex flex-col items-center gap-2 p-3 bg-green-500/10 hover:bg-green-500/15 border border-green-500/20 rounded-2xl transition-all group">
            <div className="w-9 h-9 bg-green-500/20 rounded-xl flex items-center justify-center group-hover:scale-110 transition-transform">
              <svg className="w-4 h-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <span className="text-green-300 text-xs font-medium">Rules</span>
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
                  ? 'bg-white text-black shadow-lg'
                  : 'text-white/50 hover:text-white hover:bg-white/5'
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
          <DashboardSkeleton />
        ) : currentMatches.length === 0 ? (
          <div className="text-center py-12 text-white/40 text-sm">
            {tab === 'today' ? "No matches today." : tab === 'upcoming' ? 'No upcoming matches.' : 'No completed matches yet.'}
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {currentMatches.map((match) => (
              <div key={match.id}
                className={`bg-gradient-to-br ${getTeamTheme(match.team1).tintClass} bg-white/5 hover:bg-white/[0.08] border border-white/10 rounded-2xl p-5 transition-all duration-200 md:backdrop-blur-sm`}>
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
                <p className="text-white/25 text-[11px] text-center mb-2">
                  Match #{match.id}
                </p>
                <div className="flex items-center justify-center gap-3 mb-2">
                  <span className={`inline-flex items-center gap-1.5 font-bold text-lg text-white`}>
                    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold ${getTeamTheme(match.team1).badgeClass}`}>
                      {getTeamTheme(match.team1).label}
                    </span>
                    {match.team1}
                  </span>
                  <span className="text-white/40 text-sm font-medium px-2 py-0.5 bg-white/5 rounded-lg">vs</span>
                  <span className={`inline-flex items-center gap-1.5 font-bold text-lg text-white`}>
                    {match.team2}
                    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold ${getTeamTheme(match.team2).badgeClass}`}>
                      {getTeamTheme(match.team2).label}
                    </span>
                  </span>
                </div>
                <p className="text-white/40 text-xs text-center mb-1">
                  {formatDate(match.match_date, match.match_time)}
                </p>
                {match.venue && (
                  <div className="mb-2 mx-auto max-w-[280px]">
                    <p className="text-white/50 text-[11px] text-center font-medium mb-1">
                      {match.venue.venue}, {match.venue.city}
                    </p>
                    <div className="flex items-center justify-center gap-2 text-[10px]">
                      <span className={`px-2 py-0.5 rounded-full border ${
                        match.venue.pitch_type === 'Batting-friendly'
                          ? 'bg-amber-500/10 border-amber-500/20 text-amber-300'
                          : match.venue.pitch_type === 'Bowling-friendly'
                          ? 'bg-sky-500/10 border-sky-500/20 text-sky-300'
                          : 'bg-white/5 border-white/10 text-white/50'
                      }`}>
                        {match.venue.pitch_type}
                      </span>
                      <span className="text-white/30">Avg {match.venue.avg_first_innings}</span>
                      <span className="text-white/30">Chase {match.venue.chase_win_pct}%</span>
                    </div>
                  </div>
                )}
                {tab === 'today' && match.status === 'future' && getCountdown(match) && (
                  <p className="text-center mb-2">
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-green-500/10 border border-green-500/20 text-green-400 text-[11px] font-semibold">
                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      Starts in {getCountdown(match)}
                    </span>
                  </p>
                )}
                {tab === 'today' && match.status === 'future' && myTeams.has(match.id) && todayTeamLineup[match.id]?.announced && (
                  <div className="mb-3 space-y-1 text-center text-xs font-medium">
                    <p className={todayTeamLineup[match.id].unannouncedSelected > 0 ? 'text-red-300' : 'text-emerald-300'}>
                      {todayTeamLineup[match.id].unannouncedSelected > 0
                        ? `${todayTeamLineup[match.id].unannouncedSelected} unannounced players in your team`
                        : 'All selected players are announced'}
                    </p>
                    {todayTeamLineup[match.id].substituteSelected > 0 && (
                      <p className="text-sky-300">
                        {todayTeamLineup[match.id].substituteSelected} substitutes selected
                      </p>
                    )}
                  </div>
                )}
                <div className="flex justify-center">{matchAction(match)}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="text-center text-white/10 text-xs py-6">
        Built by Fantasy Cricket Team
      </div>

      {showContestantsForMatch && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 md:bg-black/70 md:backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-2xl border border-white/10 bg-[#0f0f0f] p-5 shadow-2xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.2em] text-white/35">Who&apos;s Playing</p>
                <h3 className="mt-1 text-lg font-semibold text-white">
                  Match #{showContestantsForMatch.id}: {showContestantsForMatch.team1} vs {showContestantsForMatch.team2}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowContestantsForMatch(null)}
                className="rounded-lg p-2 text-white/50 transition hover:bg-white/10 hover:text-white"
              >
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="mt-4 max-h-[60vh] overflow-auto rounded-xl border border-white/10 bg-white/5">
              {contestantsLoading ? (
                <div className="flex justify-center py-10">
                  <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-white" />
                </div>
              ) : matchContestants.length === 0 ? (
                <div className="px-4 py-8 text-center text-sm text-white/40">
                  No contestants have joined this match yet.
                </div>
              ) : (
                <div className="divide-y divide-white/5">
                  {matchContestants.map((contestant, index) => (
                    <div key={`${contestant.user_id}-${index}`} className="flex items-center justify-between gap-4 px-4 py-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-white">{contestant.name}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-[11px] uppercase tracking-wide text-white/30">Last updated</p>
                        <p className="text-xs text-white/65">{formatDateTime(contestant.last_team_updated)}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
