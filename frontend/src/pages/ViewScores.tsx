import { useState, useEffect, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import client from '../api/client';
import { useAuth } from '../auth/AuthContext';
import type { PlayerScore, ContestantScore } from '../types';

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

export default function ViewScoresPage() {
  const { matchId } = useParams<{ matchId: string }>();
  const { profile } = useAuth();
  const [playerScores, setPlayerScores] = useState<PlayerScore[]>([]);
  const [contestants, setContestants] = useState<ContestantScore[]>([]);
  const [myTeam, setMyTeam] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Team diff state
  const [tab, setTab] = useState<'scores' | 'diff'>('scores');
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
    fetchScores();
    fetchDiffContestants();
    intervalRef.current = setInterval(fetchScores, 30000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [matchId]);

  useEffect(() => {
    if (selectedOther) fetchDiff(selectedOther);
  }, [selectedOther]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-950 via-indigo-950 to-slate-900 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-400 mx-auto mb-4" />
          <p className="text-indigo-300 text-sm">Loading scores...</p>
        </div>
      </div>
    );
  }

  const sortedContestants = [...contestants].sort((a, b) => b.points - a.points);

  const renderPlayerEntry = (entry: TeamDiffEntry | null, side: 'left' | 'right') => {
    if (!entry) return <div className="flex-1 p-3 bg-white/5 rounded-xl text-center text-indigo-500 text-xs">—</div>;
    const tagColor = entry.tag === 'C' ? 'bg-amber-500' : entry.tag === 'VC' ? 'bg-indigo-500' : '';
    return (
      <div className={`flex-1 p-3 rounded-xl ${side === 'left' ? 'bg-blue-500/10 border border-blue-500/20' : 'bg-red-500/10 border border-red-500/20'}`}>
        <div className="flex items-center justify-between mb-1">
          <span className="text-white text-sm font-medium truncate">{entry.name}</span>
          {entry.tag && <span className={`text-[10px] text-white font-bold px-1.5 py-0.5 rounded ${tagColor}`}>{entry.tag}</span>}
        </div>
        <div className="flex items-center justify-between text-xs">
          <span className="text-indigo-400">{entry.team} &middot; {entry.role}</span>
          <span className="text-green-400 font-bold">{entry.adjusted_points} pts</span>
        </div>
        {entry.multiplier > 1 && (
          <div className="text-[10px] text-indigo-500 mt-0.5">{entry.base_points} &times; {entry.multiplier}</div>
        )}
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-indigo-950 to-slate-900">
      {/* Header */}
      <header className="sticky top-0 z-30 bg-slate-950/80 backdrop-blur-lg border-b border-white/10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/dashboard" className="p-2 hover:bg-white/10 rounded-xl transition-all">
              <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </Link>
            <div>
              <h1 className="text-lg font-bold text-white">Match #{matchId}</h1>
              {lastUpdated && <p className="text-xs text-indigo-400">Updated {lastUpdated.toLocaleTimeString()}</p>}
            </div>
          </div>
          <div className="flex items-center gap-1 bg-white/5 rounded-xl p-1">
            <button onClick={() => setTab('scores')} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${tab === 'scores' ? 'bg-indigo-600 text-white' : 'text-indigo-300 hover:text-white'}`}>Scores</button>
            <button onClick={() => setTab('diff')} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${tab === 'diff' ? 'bg-indigo-600 text-white' : 'text-indigo-300 hover:text-white'}`}>Compare</button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6 space-y-6">

        {tab === 'scores' && (
          <>
            {/* Auto-refresh */}
            <div className="flex items-center gap-2 text-xs text-indigo-400">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
              </span>
              Auto-refreshes every 30s
            </div>

            {/* Player Stats */}
            <div className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden">
              <div className="px-4 py-3 border-b border-white/10">
                <div className="flex items-center justify-between gap-3">
                  <h2 className="text-white font-semibold">Player Statistics</h2>
                  <span className="text-[11px] text-indigo-400 whitespace-nowrap">
                    Scroll to view all columns
                  </span>
                </div>
              </div>
              <div className="max-h-[70vh] overflow-auto">
                <table className="min-w-[1100px] w-full text-sm">
                  <thead>
                    <tr className="bg-white/5 text-indigo-300 text-xs uppercase tracking-wider">
                      <th className="sticky top-0 left-0 bg-slate-900 z-20 px-4 py-3 text-left font-medium">Player</th>
                      <th className="sticky top-0 bg-slate-900 px-3 py-3 text-right font-medium">Pts</th>
                      <th className="sticky top-0 bg-slate-900 px-3 py-3 text-left font-medium">Team</th>
                      <th className="sticky top-0 bg-slate-900 px-3 py-3 text-left font-medium">Role</th>
                      <th className="sticky top-0 bg-slate-900 px-3 py-3 text-right font-medium">Runs</th>
                      <th className="sticky top-0 bg-slate-900 px-3 py-3 text-right font-medium">Balls</th>
                      <th className="sticky top-0 bg-slate-900 px-3 py-3 text-right font-medium">4s</th>
                      <th className="sticky top-0 bg-slate-900 px-3 py-3 text-right font-medium">6s</th>
                      <th className="sticky top-0 bg-slate-900 px-3 py-3 text-right font-medium">SR</th>
                      <th className="sticky top-0 bg-slate-900 px-3 py-3 text-right font-medium">Overs</th>
                      <th className="sticky top-0 bg-slate-900 px-3 py-3 text-right font-medium">Wkts</th>
                      <th className="sticky top-0 bg-slate-900 px-3 py-3 text-right font-medium">Dots</th>
                      <th className="sticky top-0 bg-slate-900 px-3 py-3 text-right font-medium">Econ</th>
                      <th className="sticky top-0 bg-slate-900 px-3 py-3 text-right font-medium">Ct</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {playerScores.length === 0 ? (
                      <tr><td colSpan={14} className="px-4 py-8 text-center text-indigo-400">No scores available yet.</td></tr>
                    ) : (
                      playerScores.map((p, i) => {
                        const isMyPlayer = myTeam.has(p.name);
                        return (
                          <tr key={i} className={`transition-colors ${isMyPlayer ? 'bg-yellow-500/10 hover:bg-yellow-500/15' : 'hover:bg-white/5'}`}>
                            <td className={`sticky left-0 z-10 px-4 py-2.5 text-white font-medium whitespace-nowrap ${isMyPlayer ? 'bg-yellow-500/10' : 'bg-slate-900'}`}>
                              {p.name}
                              {isMyPlayer && <span className="ml-1.5 inline-block w-1.5 h-1.5 bg-yellow-400 rounded-full" />}
                            </td>
                            <td className="px-3 py-2.5 text-right font-bold text-green-400">{p.points}</td>
                            <td className="px-3 py-2.5 text-indigo-300">{p.team}</td>
                            <td className="px-3 py-2.5 text-xs text-indigo-300">{p.role}</td>
                            <td className="px-3 py-2.5 text-right text-white">{p.runs}</td>
                            <td className="px-3 py-2.5 text-right text-indigo-300">{p.balls}</td>
                            <td className="px-3 py-2.5 text-right text-indigo-300">{p.fours}</td>
                            <td className="px-3 py-2.5 text-right text-indigo-300">{p.sixes}</td>
                            <td className="px-3 py-2.5 text-right text-indigo-300">{p.strike_rate?.toFixed(1)}</td>
                            <td className="px-3 py-2.5 text-right text-indigo-300">{p.overs}</td>
                            <td className="px-3 py-2.5 text-right text-white">{p.wickets}</td>
                            <td className="px-3 py-2.5 text-right text-indigo-300">{(p as any).dot_balls || 0}</td>
                            <td className="px-3 py-2.5 text-right text-indigo-300">{p.economy?.toFixed(1)}</td>
                            <td className="px-3 py-2.5 text-right text-indigo-300">{p.catches}</td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Contestant Rankings */}
            <div className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden">
              <div className="px-4 py-3 border-b border-white/10">
                <h2 className="text-white font-semibold">Contestant Rankings</h2>
              </div>
              <div className="divide-y divide-white/5">
                {sortedContestants.length === 0 ? (
                  <div className="px-4 py-8 text-center text-indigo-400">No contestant scores yet.</div>
                ) : (
                  sortedContestants.map((c, i) => (
                    <div key={i} className="flex items-center px-4 py-3 hover:bg-white/5 transition-colors">
                      <div className="w-8 text-center">
                        {i === 0 ? <span className="text-lg">&#x1F947;</span>
                          : i === 1 ? <span className="text-lg">&#x1F948;</span>
                          : i === 2 ? <span className="text-lg">&#x1F949;</span>
                          : <span className="text-indigo-400 text-sm font-medium">{i + 1}</span>}
                      </div>
                      <div className="flex-1 ml-3"><span className="text-white font-medium text-sm">{c.name}</span></div>
                      <span className="text-green-400 font-bold text-sm">{c.points} pts</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </>
        )}

        {tab === 'diff' && (
          <div className="space-y-4">
            {/* Contestant selector */}
            <div className="bg-white/5 border border-white/10 rounded-2xl p-4">
              <h2 className="text-white font-semibold mb-3">Compare Teams</h2>
              {diffContestants.length === 0 ? (
                <p className="text-indigo-400 text-sm">No other contestants have picked teams for this match yet.</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {diffContestants.map((c) => (
                    <button
                      key={c.id}
                      onClick={() => setSelectedOther(c.id)}
                      className={`px-4 py-2 rounded-xl text-sm font-medium transition ${
                        selectedOther === c.id
                          ? 'bg-indigo-600 text-white'
                          : 'bg-white/10 text-indigo-300 hover:bg-white/20'
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
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-400" />
              </div>
            )}

            {diffData && !diffLoading && !diffData.error && (
              <>
                {/* Score summary */}
                <div className="grid grid-cols-3 gap-3">
                  <div className="bg-blue-500/10 border border-blue-500/20 rounded-2xl p-4 text-center">
                    <p className="text-blue-300 text-xs font-medium mb-1">You</p>
                    <p className="text-white text-2xl font-bold">{diffData.my_total}</p>
                  </div>
                  <div className={`${diffData.total_diff > 0 ? 'bg-red-500/10 border-red-500/20' : diffData.total_diff < 0 ? 'bg-green-500/10 border-green-500/20' : 'bg-white/5 border-white/10'} border rounded-2xl p-4 text-center`}>
                    <p className="text-indigo-300 text-xs font-medium mb-1">Diff</p>
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
