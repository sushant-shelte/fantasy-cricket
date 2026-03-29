import { useState, useEffect, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import client from '../api/client';
import type { PlayerScore, ContestantScore } from '../types';

export default function ViewScoresPage() {
  const { matchId } = useParams<{ matchId: string }>();
  const [playerScores, setPlayerScores] = useState<PlayerScore[]>([]);
  const [contestants, setContestants] = useState<ContestantScore[]>([]);
  const [myTeam, setMyTeam] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchScores = async () => {
    try {
      const [scoresRes, teamRes] = await Promise.all([
        client.get(`/api/scores/${matchId}`),
        client.get(`/api/scores/${matchId}/my-team`).catch(() => ({ data: [] })),
      ]);

      const data = scoresRes.data;
      setPlayerScores(data.players || []);
      setContestants(data.contestants || []);

      const team = teamRes.data || [];
      // API returns list of player names (strings)
      setMyTeam(new Set(team.map((t: string | { player_name: string }) => typeof t === 'string' ? t : t.player_name)));

      setLastUpdated(new Date());
    } catch {
      // Silently fail on refresh
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchScores();
    intervalRef.current = setInterval(fetchScores, 30000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [matchId]);

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

  // Sort contestants by points desc
  const sortedContestants = [...contestants].sort((a, b) => b.points - a.points);

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
              <h1 className="text-lg font-bold text-white">Match Scores</h1>
              <p className="text-xs text-indigo-300">Match #{matchId}</p>
            </div>
          </div>
          {lastUpdated && (
            <p className="text-xs text-indigo-400">
              Updated {lastUpdated.toLocaleTimeString()}
            </p>
          )}
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6 space-y-6">
        {/* Auto-refresh indicator */}
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
            <h2 className="text-white font-semibold">Player Statistics</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-white/5 text-indigo-300 text-xs uppercase tracking-wider">
                  <th className="sticky left-0 bg-slate-900 z-10 px-4 py-3 text-left font-medium">Player</th>
                  <th className="px-3 py-3 text-right font-medium">Pts</th>
                  <th className="px-3 py-3 text-left font-medium">Team</th>
                  <th className="px-3 py-3 text-left font-medium">Role</th>
                  <th className="px-3 py-3 text-right font-medium">Runs</th>
                  <th className="px-3 py-3 text-right font-medium">Balls</th>
                  <th className="px-3 py-3 text-right font-medium">4s</th>
                  <th className="px-3 py-3 text-right font-medium">6s</th>
                  <th className="px-3 py-3 text-right font-medium">SR</th>
                  <th className="px-3 py-3 text-right font-medium">Overs</th>
                  <th className="px-3 py-3 text-right font-medium">Wkts</th>
                  <th className="px-3 py-3 text-right font-medium">Econ</th>
                  <th className="px-3 py-3 text-right font-medium">Catches</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {playerScores.length === 0 ? (
                  <tr>
                    <td colSpan={13} className="px-4 py-8 text-center text-indigo-400">
                      No scores available yet.
                    </td>
                  </tr>
                ) : (
                  playerScores.map((p, i) => {
                    const isMyPlayer = myTeam.has(p.name);
                    return (
                      <tr
                        key={i}
                        className={`transition-colors ${
                          isMyPlayer
                            ? 'bg-yellow-500/10 hover:bg-yellow-500/15'
                            : 'hover:bg-white/5'
                        }`}
                      >
                        <td className={`sticky left-0 z-10 px-4 py-2.5 text-white font-medium whitespace-nowrap ${isMyPlayer ? 'bg-yellow-500/10' : 'bg-slate-900'}`}>
                          {p.name}
                          {isMyPlayer && (
                            <span className="ml-1.5 inline-block w-1.5 h-1.5 bg-yellow-400 rounded-full" />
                          )}
                        </td>
                        <td className="px-3 py-2.5 text-right font-bold text-green-400">{p.points}</td>
                        <td className="px-3 py-2.5 text-indigo-300">{p.team}</td>
                        <td className="px-3 py-2.5">
                          <span className="text-xs font-medium text-indigo-300">{p.role}</span>
                        </td>
                        <td className="px-3 py-2.5 text-right text-white">{p.runs}</td>
                        <td className="px-3 py-2.5 text-right text-indigo-300">{p.balls}</td>
                        <td className="px-3 py-2.5 text-right text-indigo-300">{p.fours}</td>
                        <td className="px-3 py-2.5 text-right text-indigo-300">{p.sixes}</td>
                        <td className="px-3 py-2.5 text-right text-indigo-300">{p.strike_rate?.toFixed(1)}</td>
                        <td className="px-3 py-2.5 text-right text-indigo-300">{p.overs}</td>
                        <td className="px-3 py-2.5 text-right text-white">{p.wickets}</td>
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
              <div className="px-4 py-8 text-center text-indigo-400">
                No contestant scores yet.
              </div>
            ) : (
              sortedContestants.map((c, i) => (
                <div
                  key={i}
                  className="flex items-center px-4 py-3 hover:bg-white/5 transition-colors"
                >
                  <div className="w-8 text-center">
                    {i === 0 ? (
                      <span className="text-lg">&#x1F947;</span>
                    ) : i === 1 ? (
                      <span className="text-lg">&#x1F948;</span>
                    ) : i === 2 ? (
                      <span className="text-lg">&#x1F949;</span>
                    ) : (
                      <span className="text-indigo-400 text-sm font-medium">{i + 1}</span>
                    )}
                  </div>
                  <div className="flex-1 ml-3">
                    <span className="text-white font-medium text-sm">{c.name}</span>
                  </div>
                  <span className="text-green-400 font-bold text-sm">{c.points} pts</span>
                </div>
              ))
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
