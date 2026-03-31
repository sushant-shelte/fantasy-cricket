import React, { useState, useEffect, useRef } from 'react';
import { useParams, Link, useSearchParams } from 'react-router-dom';
import client from '../api/client';
import { useAuth } from '../auth/AuthContext';
import type { PlayerScore, ContestantScore } from '../types';
import { getTeamTheme } from '../utils/teamTheme';

interface TeamDiffEntry {
  player_id: number;
  name: string;
  team: string;
  role: string;
  base_points: number;
  multiplier: number;
  tag: string;
  adjusted_points: number;
}

interface TeamDiffRow {
  left: TeamDiffEntry | null;
  right: TeamDiffEntry | null;
  diff_points?: number;
}

interface TeamDiffData {
  current_user: string;
  other_user: string;
  my_total: number;
  other_total: number;
  total_diff: number;
  different_players_diff: number;
  different_players: TeamDiffRow[];
  common_role_diff_total: number;
  common_role_diff: TeamDiffRow[];
  common_players: TeamDiffRow[];
  error?: string;
}

interface Contestant { id: number; name: string; }

interface BreakdownPlayer { name: string; team: string; role: string; base_points: number; multiplier: number; tag: string; adjusted_points: number; }
interface BreakdownData { user_name: string; total: number; players: BreakdownPlayer[]; error?: string; }

const ROLE_SYMBOLS: Record<string, { symbol: string; label: string }> = {
  Batter: { symbol: '🏏', label: 'Batter' },
  Bowler: { symbol: '◎', label: 'Bowler' },
  AllRounder: { symbol: '🏏◎', label: 'All-Rounder' },
  Wicketkeeper: { symbol: '|||', label: 'Wicketkeeper' },
};

export default function ViewScoresPage() {
  const { matchId } = useParams<{ matchId: string }>();
  const [searchParams] = useSearchParams();
  const { profile } = useAuth();
  const [playerScores, setPlayerScores] = useState<PlayerScore[]>([]);
  const [contestants, setContestants] = useState<ContestantScore[]>([]);
  const [myTeam, setMyTeam] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Tab state — read from URL param if present
  const initialTab = (searchParams.get('tab') as 'scores' | 'myteam' | 'diff') || 'scores';
  const [tab, setTab] = useState<'scores' | 'myteam' | 'diff'>(initialTab);
  const [expandedPlayer, setExpandedPlayer] = useState<number | null>(null);

  // Team breakdown state
  const [breakdown, setBreakdown] = useState<BreakdownData | null>(null);
  const [breakdownLoading, setBreakdownLoading] = useState(false);
  const [selectedContestantId, setSelectedContestantId] = useState<number | null>(null);
  const [selectedContestantBreakdown, setSelectedContestantBreakdown] = useState<BreakdownData | null>(null);
  const [selectedContestantLoading, setSelectedContestantLoading] = useState(false);

  // Team diff state
  const [diffContestants, setDiffContestants] = useState<Contestant[]>([]);
  const [selectedOther, setSelectedOther] = useState<number | null>(null);
  const [diffData, setDiffData] = useState<TeamDiffData | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);

  const fetchScores = async () => {
    try {
      const [scoresRes, teamRes] = await Promise.all([
        client.get(`/api/scores/${matchId}`),
        client.get(`/api/scores/${matchId}/my-team`).catch(() => ({ data: [] })),
      ]);
      setPlayerScores(scoresRes.data.players || []);
      setContestants(scoresRes.data.contestants || []);
      const team = teamRes.data || [];
      setMyTeam(new Set(team.map((t: string | { player_name: string }) => typeof t === 'string' ? t : t.player_name)));
      setLastUpdated(new Date());
    } catch { /* silent */ }
    finally { setLoading(false); }
  };

  const fetchBreakdown = async () => {
    setBreakdownLoading(true);
    try {
      const res = await client.get(`/api/scores/${matchId}/team-breakdown`);
      setBreakdown(res.data);
    } catch { setBreakdown(null); }
    finally { setBreakdownLoading(false); }
  };

  const fetchContestantBreakdown = async (userId: number) => {
    setSelectedContestantLoading(true);
    try {
      const res = await client.get(`/api/scores/${matchId}/team-breakdown?user_id=${userId}`);
      setSelectedContestantBreakdown(res.data);
    } catch {
      setSelectedContestantBreakdown(null);
    } finally {
      setSelectedContestantLoading(false);
    }
  };

  const fetchDiffContestants = async () => {
    try {
      const res = await client.get(`/api/scores/${matchId}/contestants`);
      setDiffContestants(res.data.filter((c: Contestant) => c.id !== profile?.id));
    } catch { /* silent */ }
  };

  const fetchDiff = async (otherId: number) => {
    setDiffLoading(true);
    try {
      const res = await client.get(`/api/scores/${matchId}/team-diff?other_user_id=${otherId}`);
      setDiffData(res.data);
    } catch { setDiffData(null); }
    finally { setDiffLoading(false); }
  };

  useEffect(() => {
    setLoading(true);
    setPlayerScores([]);
    setContestants([]);
    setMyTeam(new Set());
    setLastUpdated(null);
    setBreakdown(null);
    setDiffData(null);
    setDiffContestants([]);
  }, [matchId]);

  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);

    if (tab === 'scores') {
      setLoading(true);
      fetchScores();
      intervalRef.current = setInterval(fetchScores, 30000);
    } else if (tab === 'myteam') {
      setLoading(false);
      fetchBreakdown();
      intervalRef.current = setInterval(fetchBreakdown, 60000);
    } else if (tab === 'diff') {
      setLoading(false);
      fetchDiffContestants();
      if (selectedOther) {
        fetchDiff(selectedOther);
      }
    }

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [tab, matchId, selectedOther]);

  useEffect(() => {
    setSelectedContestantId(null);
    setSelectedContestantBreakdown(null);
    setSelectedContestantLoading(false);
  }, [matchId]);

  if (loading) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-white mx-auto mb-4" />
          <p className="text-white/50 text-sm">Loading scores...</p>
        </div>
      </div>
    );
  }

  const sortedContestants = [...contestants].sort((a, b) => b.points - a.points);
  const rankedContestants: (ContestantScore & { rank: number })[] = [];
  sortedContestants.forEach((entry, i) => {
    let rank = i + 1;
    if (i > 0 && entry.points === sortedContestants[i - 1].points) {
      rank = rankedContestants[i - 1].rank;
    }
    rankedContestants.push({ ...entry, rank });
  });

  const renderPlayerEntry = (entry: TeamDiffEntry | null, side: 'left' | 'right') => {
    if (!entry) return <div className="flex-1 p-3 bg-white/5 rounded-xl text-center text-white/30 text-xs">—</div>;
    const tagColor = entry.tag === 'C' ? 'bg-amber-500' : entry.tag === 'VC' ? 'bg-white/30' : '';
    const theme = getTeamTheme(entry.team);
    return (
      <div className={`flex-1 rounded-xl border p-3 bg-gradient-to-r ${theme.tintClass} ${side === 'left' ? 'border-white/20' : 'border-red-500/20'}`}>
        <div className="flex items-center justify-between mb-1">
          <span className="text-white text-sm font-medium truncate">{entry.name}</span>
          {entry.tag && <span className={`text-[10px] text-white font-bold px-1.5 py-0.5 rounded ${tagColor}`}>{entry.tag}</span>}
        </div>
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2 text-white/40">
            {renderTeamBadge(entry.team, true)}
            <span>{entry.role}</span>
          </div>
          <span className="text-green-400 font-bold">{entry.adjusted_points} pts</span>
        </div>
        {entry.multiplier > 1 && (
          <div className="text-[10px] text-white/30 mt-0.5">{entry.base_points} &times; {entry.multiplier}</div>
        )}
      </div>
    );
  };

  const renderRoleSymbol = (role: string) => {
    const config = ROLE_SYMBOLS[role] || { symbol: role.slice(0, 2).toUpperCase(), label: role };
    return (
      <span
        title={config.label}
        className="inline-flex min-w-[2.75rem] justify-center rounded-md border border-white/10 bg-white/5 px-2 py-1 text-[11px] font-semibold text-white/70"
      >
        {config.symbol}
      </span>
    );
  };

  const renderTeamBadge = (team: string, compact = false) => {
    const theme = getTeamTheme(team);
    return (
      <span className={`inline-flex items-center rounded-full border px-2 py-0.5 font-semibold ${compact ? 'text-[9px]' : 'text-[10px]'} ${theme.badgeClass}`}>
        {theme.label}
      </span>
    );
  };

  const handleContestantClick = (contestantId: number) => {
    if (selectedContestantId === contestantId) {
      setSelectedContestantId(null);
      setSelectedContestantBreakdown(null);
      setSelectedContestantLoading(false);
      return;
    }

    setSelectedContestantId(contestantId);
    setSelectedContestantBreakdown(null);
    fetchContestantBreakdown(contestantId);
  };

  return (
    <div className="min-h-screen bg-black">
      {/* Header */}
      <header className="sticky top-0 z-30 bg-black/80 backdrop-blur-lg border-b border-white/10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/dashboard" className="p-2 hover:bg-white/10 rounded-xl transition-all">
              <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </Link>
            <div>
              <h1 className="text-lg font-bold text-white">Match #{matchId}</h1>
              {lastUpdated && <p className="text-xs text-white/40">Updated {lastUpdated.toLocaleTimeString()}</p>}
            </div>
          </div>
          <div className="flex items-center gap-1 bg-white/5 rounded-xl p-1">
            <button onClick={() => setTab('scores')} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${tab === 'scores' ? 'bg-white text-black' : 'text-white/50 hover:text-white'}`}>Scores</button>
            <button onClick={() => setTab('myteam')} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${tab === 'myteam' ? 'bg-white text-black' : 'text-white/50 hover:text-white'}`}>Team Analysis</button>
            <button onClick={() => setTab('diff')} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${tab === 'diff' ? 'bg-white text-black' : 'text-white/50 hover:text-white'}`}>Compare</button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6 space-y-6">

        {tab === 'scores' && (
          <>
            {/* Auto-refresh */}
            <div className="flex items-center gap-2 text-xs text-white/40">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
              </span>
              Auto-refreshes every 30s
            </div>

            {/* Contestant Rankings */}
            <div className="max-w-2xl bg-white/5 border border-white/10 rounded-2xl overflow-hidden">
              <div className="px-4 py-3 border-b border-white/10">
                <h2 className="text-white font-semibold">Contestant Rankings</h2>
              </div>
              <div className="divide-y divide-white/5">
                {sortedContestants.length === 0 ? (
                  <div className="px-4 py-8 text-center text-white/40">No contestant scores yet.</div>
                ) : (
                  rankedContestants.map((c) => {
                    const isSelected = selectedContestantId === c.id;
                    return (
                      <div key={c.id}>
                        <button
                          type="button"
                          onClick={() => handleContestantClick(c.id)}
                          className={`flex w-full items-center px-4 py-3 text-left transition-colors ${isSelected ? 'bg-white/8' : 'hover:bg-white/5'}`}
                        >
                          <div className="w-8 flex-shrink-0 text-center">
                            {c.rank === 1 ? <span className="text-lg">&#x1F947;</span>
                              : c.rank === 2 ? <span className="text-lg">&#x1F948;</span>
                              : c.rank === 3 ? <span className="text-lg">&#x1F949;</span>
                              : <span className="text-white/40 text-sm font-medium">{c.rank}</span>}
                          </div>
                          <div className="ml-3 min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <span className="text-white font-medium text-sm">{c.name}</span>
                            </div>
                          </div>
                          <span className="ml-4 flex-shrink-0 text-green-400 font-bold text-sm">{c.points} pts</span>
                          <span className={`ml-3 text-[10px] text-white/40 transition-transform ${isSelected ? 'rotate-90' : ''}`}>&#9654;</span>
                        </button>

                        {isSelected && (
                          <div className="border-t border-white/5 bg-black/20 px-4 py-4">
                            {selectedContestantLoading ? (
                              <div className="flex items-center justify-center py-4">
                                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-white" />
                              </div>
                            ) : selectedContestantBreakdown?.error ? (
                              <p className="text-sm text-white/40">{selectedContestantBreakdown.error}</p>
                            ) : selectedContestantBreakdown ? (
                              <div className="space-y-3">
                                <div className="flex items-center justify-between gap-3">
                                  <div>
                                    <p className="text-xs uppercase tracking-[0.2em] text-white/35">Team View</p>
                                    <h3 className="text-sm font-semibold text-white">{selectedContestantBreakdown.user_name}</h3>
                                  </div>
                                  <p className="text-sm font-bold text-green-400">{selectedContestantBreakdown.total} pts</p>
                                </div>
                                <div className="grid gap-2 sm:grid-cols-2">
                                  {selectedContestantBreakdown.players.map((player, index) => (
                                    <div key={`${player.name}-${index}`} className={`rounded-xl border border-white/10 bg-gradient-to-r ${getTeamTheme(player.team).tintClass} px-3 py-2.5`}>
                                      <div className="flex items-start justify-between gap-3">
                                        <div className="min-w-0">
                                          <div className="flex items-center gap-2">
                                            <p className="truncate text-sm font-medium text-white">{player.name}</p>
                                            {player.tag && (
                                              <span className={`inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[10px] font-bold ${
                                                player.tag === 'C' ? 'bg-amber-500 text-black' : 'bg-sky-500 text-black'
                                              }`}>
                                                {player.tag}
                                              </span>
                                            )}
                                          </div>
                                          <div className="mt-1 flex items-center gap-2 text-xs text-white/40">
                                            {renderTeamBadge(player.team)}
                                            <span>{player.role}</span>
                                          </div>
                                        </div>
                                        <div className="text-right">
                                          <p className="text-sm font-bold text-green-400">{player.adjusted_points}</p>
                                          {player.multiplier > 1 && (
                                            <p className="text-[10px] text-white/30">{player.base_points} &times; {player.multiplier}</p>
                                          )}
                                        </div>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            ) : (
                              <p className="text-sm text-white/40">No team data available.</p>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </div>

            {/* Player Stats */}
            <div className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden">
              <div className="px-4 py-3 border-b border-white/10">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <h2 className="text-white font-semibold">Player Statistics</h2>
                  <div className="flex flex-wrap items-center gap-2 text-[11px] text-white/40">
                    <span className="whitespace-nowrap">Tap player for analysis</span>
                    <span className="inline-flex items-center gap-1 rounded-md border border-white/10 bg-white/5 px-2 py-1 text-white/70">🏏 Batter</span>
                    <span className="inline-flex items-center gap-1 rounded-md border border-white/10 bg-white/5 px-2 py-1 text-white/70">◎ Bowler</span>
                    <span className="inline-flex items-center gap-1 rounded-md border border-white/10 bg-white/5 px-2 py-1 text-white/70">🏏◎ All-Rounder</span>
                    <span className="inline-flex items-center gap-1 rounded-md border border-white/10 bg-white/5 px-2 py-1 text-white/70">||| WK</span>
                  </div>
                </div>
              </div>
              <div className="max-h-[72vh] overflow-auto">
                <table className="min-w-[1600px] w-full text-sm">
                  <thead>
                    <tr className="bg-white/5 text-white/50 text-xs uppercase tracking-wider">
                      <th className="sticky top-0 left-0 z-20 min-w-[220px] border-r border-white/10 bg-black px-4 py-3 text-left font-medium shadow-[10px_0_18px_-12px_rgba(15,23,42,0.95)]">Player</th>
                      <th className="sticky top-0 bg-black px-3 py-3 text-right font-medium">Pts</th>
                      <th className="sticky top-0 bg-black px-3 py-3 text-left font-medium">Team</th>
                      <th className="sticky top-0 bg-black px-3 py-3 text-center font-medium">Role</th>
                      <th className="sticky top-0 bg-black px-3 py-3 text-center font-medium">P</th>
                      <th className="sticky top-0 bg-black px-3 py-3 text-center font-medium">Out</th>
                      <th className="sticky top-0 bg-black px-3 py-3 text-right font-medium">Runs</th>
                      <th className="sticky top-0 bg-black px-3 py-3 text-right font-medium">Balls</th>
                      <th className="sticky top-0 bg-black px-3 py-3 text-right font-medium">4s</th>
                      <th className="sticky top-0 bg-black px-3 py-3 text-right font-medium">6s</th>
                      <th className="sticky top-0 bg-black px-3 py-3 text-right font-medium">SR</th>
                      <th className="sticky top-0 bg-black px-3 py-3 text-right font-medium">Overs</th>
                      <th className="sticky top-0 bg-black px-3 py-3 text-right font-medium">Mdns</th>
                      <th className="sticky top-0 bg-black px-3 py-3 text-right font-medium">Runs Ag</th>
                      <th className="sticky top-0 bg-black px-3 py-3 text-right font-medium">Wkts</th>
                      <th className="sticky top-0 bg-black px-3 py-3 text-right font-medium">Dots</th>
                      <th className="sticky top-0 bg-black px-3 py-3 text-right font-medium">Econ</th>
                      <th className="sticky top-0 bg-black px-3 py-3 text-right font-medium">Ct</th>
                      <th className="sticky top-0 bg-black px-3 py-3 text-right font-medium">St</th>
                      <th className="sticky top-0 bg-black px-3 py-3 text-right font-medium">RO-D</th>
                      <th className="sticky top-0 bg-black px-3 py-3 text-right font-medium">RO-I</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {playerScores.length === 0 ? (
                      <tr><td colSpan={20} className="px-4 py-8 text-center text-white/40">No scores available yet.</td></tr>
                    ) : (
                      playerScores.map((p, i) => {
                        const isMyPlayer = myTeam.has(p.name);
                        const isExpanded = expandedPlayer === i;
                        const bd = (p as any).breakdown || [];
                        return (
                          <React.Fragment key={i}>
                            <tr
                              onClick={() => setExpandedPlayer(isExpanded ? null : i)}
                              className={`cursor-pointer bg-gradient-to-r ${getTeamTheme(p.team).tintClass} transition-colors ${isMyPlayer ? 'bg-yellow-500/10 hover:bg-yellow-500/15' : 'hover:bg-white/5'}`}>
                              <td className={`sticky left-0 z-10 min-w-[220px] border-r border-white/10 px-4 py-2.5 text-white font-medium whitespace-nowrap shadow-[10px_0_18px_-12px_rgba(15,23,42,0.95)] bg-black`}>
                                <span className={`inline-block w-3 text-[10px] text-white/40 mr-1 transition-transform ${isExpanded ? 'rotate-90' : ''}`}>&#9654;</span>
                                {p.name}
                                {isMyPlayer && <span className="ml-1.5 inline-block w-1.5 h-1.5 bg-yellow-400 rounded-full" />}
                              </td>
                              <td className="px-3 py-2.5 text-right font-bold text-green-400">{p.points}</td>
                              <td className="px-3 py-2.5 text-white/50">{renderTeamBadge(p.team)}</td>
                              <td className="px-3 py-2.5 text-center">{renderRoleSymbol(p.role)}</td>
                              <td className="px-3 py-2.5 text-center text-white">{p.played ? 'Y' : 'N'}</td>
                              <td className="px-3 py-2.5 text-center text-white">{p.is_out ? 'Y' : 'N'}</td>
                              <td className="px-3 py-2.5 text-right text-white">{p.runs}</td>
                              <td className="px-3 py-2.5 text-right text-white/50">{p.balls}</td>
                              <td className="px-3 py-2.5 text-right text-white/50">{p.fours}</td>
                              <td className="px-3 py-2.5 text-right text-white/50">{p.sixes}</td>
                              <td className="px-3 py-2.5 text-right text-white/50">{p.strike_rate?.toFixed(1)}</td>
                              <td className="px-3 py-2.5 text-right text-white/50">{p.overs}</td>
                              <td className="px-3 py-2.5 text-right text-white/50">{p.maidens}</td>
                              <td className="px-3 py-2.5 text-right text-white/50">{p.runs_conceded}</td>
                              <td className="px-3 py-2.5 text-right text-white">{p.wickets}</td>
                              <td className="px-3 py-2.5 text-right text-white/50">{p.dot_balls}</td>
                              <td className="px-3 py-2.5 text-right text-white/50">{p.economy?.toFixed(1)}</td>
                              <td className="px-3 py-2.5 text-right text-white/50">{p.catches}</td>
                              <td className="px-3 py-2.5 text-right text-white/50">{p.stumpings}</td>
                              <td className="px-3 py-2.5 text-right text-white/50">{p.runout_direct}</td>
                              <td className="px-3 py-2.5 text-right text-white/50">{p.runout_indirect}</td>
                            </tr>
                            {isExpanded && bd.length > 0 && (
                              <tr className="bg-white/5">
                                <td colSpan={21} className="px-4 py-3">
                                  <p className="text-white/40 text-[10px] uppercase tracking-wider mb-2">Player Analysis</p>
                                  <div className="flex flex-wrap gap-2">
                                    {bd.map((item: { label: string; points: number }, j: number) => (
                                      <span key={j}
                                        className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium border ${
                                          item.points > 0
                                            ? 'bg-green-500/10 text-green-400 border-green-500/20'
                                            : 'bg-red-500/10 text-red-400 border-red-500/20'
                                        }`}>
                                        {item.label}
                                        <span className="font-bold">{item.points > 0 ? '+' : ''}{item.points}</span>
                                      </span>
                                    ))}
                                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-bold bg-white/10 text-white border border-white/20">
                                      Total: {p.points}
                                    </span>
                                  </div>
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>

          </>
        )}

        {tab === 'myteam' && (
          <div className="space-y-4">
            {breakdownLoading ? (
              <div className="flex justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white" />
              </div>
            ) : breakdown?.error ? (
              <div className="bg-white/5 border border-white/10 rounded-2xl p-6 text-center text-white/40">
                {breakdown.error}
              </div>
            ) : breakdown ? (
              <>
                {/* Ground Preview with Points */}
                <div className="rounded-2xl overflow-hidden shadow-2xl max-w-md mx-auto"
                  style={{ background: 'linear-gradient(180deg, #1a5e1a 0%, #2d8a2d 30%, #3da33d 50%, #2d8a2d 70%, #1a5e1a 100%)' }}>
                  <div className="text-center pt-4 pb-2">
                    <p className="text-white text-lg font-bold">{breakdown.total} <span className="text-sm text-white/60">pts</span></p>
                    <p className="text-white/40 text-[10px] uppercase tracking-widest">Team Analysis</p>
                  </div>
                  <div className="relative px-4 pb-5">
                    <div className="absolute inset-x-8 inset-y-4 border-2 border-white/15 rounded-[50%]" />
                    {(['Wicketkeeper', 'Batter', 'AllRounder', 'Bowler'] as const).map((role) => {
                      const rolePlayers = breakdown.players.filter(p => p.role === role);
                      if (rolePlayers.length === 0) return null;
                      const roleLabel = role === 'AllRounder' ? 'All-Rounders' : role === 'Wicketkeeper' ? 'Wicketkeeper' : role + 's';
                      return (
                        <div key={role} className="relative z-10 mb-3">
                          <p className="text-center text-white/30 text-[9px] uppercase tracking-widest mb-1.5">{roleLabel}</p>
                          <div className="flex justify-center gap-2 flex-wrap">
                            {rolePlayers.map((p, i) => (
                              <div key={i} className="flex flex-col items-center">
                                <div className={`w-10 h-10 rounded-full flex items-center justify-center text-[10px] font-bold shadow-lg ${
                                  p.tag === 'C' ? 'bg-amber-400 text-black ring-2 ring-amber-300' :
                                  p.tag === 'VC' ? 'bg-sky-400 text-black ring-2 ring-sky-300' :
                                  'bg-white text-green-900'
                                }`}>
                                  {p.tag || p.adjusted_points}
                                </div>
                                <p className="text-white text-[9px] font-medium mt-0.5 max-w-[55px] text-center truncate">{p.name.split(' ').pop()}</p>
                                <p className="text-green-300 text-[9px] font-bold">{p.adjusted_points}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  <div className="flex justify-center gap-4 pb-3 text-[9px] text-white/40">
                    <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-amber-400"></span> C (2x)</span>
                    <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-sky-400"></span> VC (1.5x)</span>
                  </div>
                </div>

                {/* Player breakdown list */}
                <div className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden">
                  <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between">
                    <h3 className="text-white font-semibold text-sm">Player Contributions</h3>
                    <span className="text-white/40 text-[10px]">Tap player for analysis</span>
                  </div>
                  <div className="divide-y divide-white/5">
                    {breakdown.players.map((p, i) => {
                      const isOpen = expandedPlayer === 1000 + i;
                      const bd = (p as any).breakdown || [];
                      return (
                        <div key={i}>
                          <div
                            onClick={() => setExpandedPlayer(isOpen ? null : 1000 + i)}
                            className={`flex items-center px-4 py-3 hover:bg-white/5 transition-colors cursor-pointer bg-gradient-to-r ${getTeamTheme(p.team).tintClass}`}>
                            <div className="w-5 text-center flex-shrink-0">
                              <span className={`text-[10px] text-white/40 transition-transform inline-block ${isOpen ? 'rotate-90' : ''}`}>&#9654;</span>
                            </div>
                            <div className="w-7 flex-shrink-0 ml-1">
                              {p.tag === 'C' && <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-amber-500 text-black text-[10px] font-bold">C</span>}
                              {p.tag === 'VC' && <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-sky-500 text-black text-[10px] font-bold">VC</span>}
                            </div>
                            <div className="min-w-0 flex-[1.35] ml-2">
                              <p className="text-white text-sm font-medium truncate">{p.name}</p>
                              <div className="mt-1 flex items-center gap-2 text-xs text-white/40">
                                {renderTeamBadge(p.team)}
                                <span>{p.role}</span>
                              </div>
                            </div>
                            <div className="text-right flex-shrink-0 ml-2 min-w-[56px]">
                              <p className="text-green-400 font-bold text-sm">{p.adjusted_points}</p>
                              {p.multiplier > 1 && (
                                <p className="text-white/30 text-[10px]">{p.base_points} &times; {p.multiplier}</p>
                              )}
                            </div>
                          </div>
                          {isOpen && bd.length > 0 && (
                            <div className="px-4 pb-3 pt-1">
                              <p className="text-white/30 text-[10px] uppercase tracking-wider mb-1.5">Player Analysis</p>
                              <div className="flex flex-wrap gap-1.5">
                                {bd.map((item: { label: string; points: number }, j: number) => (
                                  <span key={j}
                                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium border ${
                                      item.points > 0
                                        ? 'bg-green-500/10 text-green-400 border-green-500/20'
                                        : 'bg-red-500/10 text-red-400 border-red-500/20'
                                    }`}>
                                    {item.label} <span className="font-bold">{item.points > 0 ? '+' : ''}{item.points}</span>
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </>
            ) : (
              <div className="bg-white/5 border border-white/10 rounded-2xl p-6 text-center text-white/40">
                No team data available.
              </div>
            )}
          </div>
        )}

        {tab === 'diff' && (
          <div className="space-y-4">
            {/* Contestant selector */}
            <div className="bg-white/5 border border-white/10 rounded-2xl p-4">
              <h2 className="text-white font-semibold mb-3">Compare Teams</h2>
              {diffContestants.length === 0 ? (
                <p className="text-white/40 text-sm">No other contestants have picked teams for this match yet.</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {diffContestants.map((c) => (
                    <button
                      key={c.id}
                      onClick={() => setSelectedOther(c.id)}
                      className={`px-4 py-2 rounded-xl text-sm font-medium transition ${
                        selectedOther === c.id
                          ? 'bg-white text-black'
                          : 'bg-white/10 text-white/50 hover:bg-white/20'
                      }`}
                    >
                      {c.name}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {diffLoading && (
              <div className="flex justify-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white" />
              </div>
            )}

            {diffData && !diffLoading && !diffData.error && (
              <>
                {/* Score summary */}
                <div className="grid grid-cols-3 gap-3">
                  <div className="bg-white/10 border border-white/20 rounded-2xl p-4 text-center">
                    <p className="text-white/50 text-xs font-medium mb-1">You</p>
                    <p className="text-white text-2xl font-bold">{diffData.my_total}</p>
                  </div>
                  <div className={`${diffData.total_diff > 0 ? 'bg-red-500/10 border-red-500/20' : diffData.total_diff < 0 ? 'bg-green-500/10 border-green-500/20' : 'bg-white/5 border-white/10'} border rounded-2xl p-4 text-center`}>
                    <p className="text-white/50 text-xs font-medium mb-1">Diff</p>
                    <p className={`text-2xl font-bold ${diffData.total_diff > 0 ? 'text-red-400' : diffData.total_diff < 0 ? 'text-green-400' : 'text-white'}`}>
                      {diffData.total_diff > 0 ? '+' : ''}{diffData.total_diff}
                    </p>
                  </div>
                  <div className="bg-red-500/10 border border-red-500/20 rounded-2xl p-4 text-center">
                    <p className="text-red-300 text-xs font-medium mb-1">{diffData.other_user}</p>
                    <p className="text-white text-2xl font-bold">{diffData.other_total}</p>
                  </div>
                </div>

                {/* Different players */}
                {diffData.different_players.length > 0 && diffData.different_players.some(r => r.left || r.right) && (
                  <div className="bg-white/5 border border-white/10 rounded-2xl p-4">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-white font-semibold text-sm">Different Players</h3>
                      <span className={`text-xs font-bold px-2 py-1 rounded-full ${diffData.different_players_diff > 0 ? 'bg-red-500/20 text-red-400' : diffData.different_players_diff < 0 ? 'bg-green-500/20 text-green-400' : 'bg-white/10 text-white'}`}>
                        {diffData.different_players_diff > 0 ? '+' : ''}{diffData.different_players_diff} pts
                      </span>
                    </div>
                    <div className="space-y-2">
                      {diffData.different_players.map((row, i) => (
                        <div key={i} className="flex gap-2">
                          {renderPlayerEntry(row.left, 'left')}
                          {renderPlayerEntry(row.right, 'right')}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Common players with C/VC diff */}
                {diffData.common_role_diff.length > 0 && (
                  <div className="bg-white/5 border border-white/10 rounded-2xl p-4">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-white font-semibold text-sm">Same Players, Different C/VC</h3>
                      <span className={`text-xs font-bold px-2 py-1 rounded-full ${diffData.common_role_diff_total > 0 ? 'bg-red-500/20 text-red-400' : diffData.common_role_diff_total < 0 ? 'bg-green-500/20 text-green-400' : 'bg-white/10 text-white'}`}>
                        {diffData.common_role_diff_total > 0 ? '+' : ''}{diffData.common_role_diff_total} pts
                      </span>
                    </div>
                    <div className="space-y-2">
                      {diffData.common_role_diff.map((row, i) => (
                        <div key={i} className="flex gap-2">
                          {renderPlayerEntry(row.left, 'left')}
                          {renderPlayerEntry(row.right, 'right')}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Common players same assignment */}
                {diffData.common_players.length > 0 && (
                  <div className="bg-white/5 border border-white/10 rounded-2xl p-4">
                    <h3 className="text-white font-semibold text-sm mb-3">Common Players (Same Role)</h3>
                    <div className="space-y-2">
                      {diffData.common_players.map((row, i) => (
                        <div key={i} className="flex gap-2">
                          {renderPlayerEntry(row.left, 'left')}
                          {renderPlayerEntry(row.right, 'right')}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}

            {diffData?.error && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-2xl p-4 text-red-400 text-sm">
                {diffData.error}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
