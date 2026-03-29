import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import client from '../api/client';
import { useAuth } from '../auth/AuthContext';
import type { LeaderboardEntry } from '../types';

export default function LeaderboardPage() {
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const { profile } = useAuth();
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchLeaderboard = async () => {
    try {
      const res = await client.get('/api/leaderboard');
      setEntries(res.data || []);
    } catch {
      // Silently fail on refresh
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLeaderboard();
    intervalRef.current = setInterval(fetchLeaderboard, 15000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  const sorted = [...entries].sort((a, b) => b.points - a.points);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-indigo-950 to-slate-900">
      {/* Header */}
      <header className="sticky top-0 z-30 bg-slate-950/80 backdrop-blur-lg border-b border-white/10">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center gap-3">
          <Link to="/dashboard" className="p-2 hover:bg-white/10 rounded-xl transition-all">
            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </Link>
          <div>
            <h1 className="text-lg font-bold text-white">Leaderboard</h1>
            <div className="flex items-center gap-2 text-xs text-indigo-400">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-green-500" />
              </span>
              Auto-refreshes every 15s
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-6">
        {loading ? (
          <div className="flex justify-center py-16">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-400" />
          </div>
        ) : sorted.length === 0 ? (
          <div className="text-center py-16 text-indigo-300">No leaderboard data yet.</div>
        ) : (
          <>
            {/* Top 3 podium */}
            {sorted.length >= 3 && (
              <div className="flex items-end justify-center gap-3 mb-8 pt-4">
                {/* 2nd place */}
                <div className="flex flex-col items-center">
                  <div className="w-16 h-16 sm:w-20 sm:h-20 bg-slate-400/20 border-2 border-slate-400/40 rounded-2xl flex items-center justify-center mb-2">
                    <span className="text-2xl sm:text-3xl">&#x1F948;</span>
                  </div>
                  <p className="text-white text-sm font-medium text-center truncate max-w-[5rem]">{sorted[1].name}</p>
                  <p className="text-slate-300 text-xs font-bold">{sorted[1].points} pts</p>
                </div>

                {/* 1st place */}
                <div className="flex flex-col items-center -mt-4">
                  <div className="w-20 h-20 sm:w-24 sm:h-24 bg-amber-500/20 border-2 border-amber-400/50 rounded-2xl flex items-center justify-center mb-2 shadow-lg shadow-amber-500/20">
                    <span className="text-3xl sm:text-4xl">&#x1F947;</span>
                  </div>
                  <p className="text-white text-sm font-bold text-center truncate max-w-[5rem]">{sorted[0].name}</p>
                  <p className="text-amber-300 text-xs font-bold">{sorted[0].points} pts</p>
                </div>

                {/* 3rd place */}
                <div className="flex flex-col items-center mt-2">
                  <div className="w-16 h-16 sm:w-20 sm:h-20 bg-orange-700/20 border-2 border-orange-600/40 rounded-2xl flex items-center justify-center mb-2">
                    <span className="text-2xl sm:text-3xl">&#x1F949;</span>
                  </div>
                  <p className="text-white text-sm font-medium text-center truncate max-w-[5rem]">{sorted[2].name}</p>
                  <p className="text-orange-300 text-xs font-bold">{sorted[2].points} pts</p>
                </div>
              </div>
            )}

            {/* Full table */}
            <div className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden">
              <div className="divide-y divide-white/5">
                {sorted.map((entry, i) => {
                  const isCurrentUser = profile?.name === entry.name;
                  return (
                    <div
                      key={i}
                      className={`flex items-center px-4 py-3.5 transition-colors ${
                        isCurrentUser
                          ? 'bg-indigo-500/15 hover:bg-indigo-500/20'
                          : 'hover:bg-white/5'
                      }`}
                    >
                      <div className="w-10 text-center flex-shrink-0">
                        {i === 0 ? (
                          <span className="text-lg">&#x1F947;</span>
                        ) : i === 1 ? (
                          <span className="text-lg">&#x1F948;</span>
                        ) : i === 2 ? (
                          <span className="text-lg">&#x1F949;</span>
                        ) : (
                          <span className="text-indigo-400 font-semibold text-sm">{i + 1}</span>
                        )}
                      </div>
                      <div className="flex-1 min-w-0 ml-2">
                        <div className="flex items-center gap-2">
                          <span className={`text-sm font-medium truncate ${isCurrentUser ? 'text-indigo-200' : 'text-white'}`}>
                            {entry.name}
                          </span>
                          {isCurrentUser && (
                            <span className="flex-shrink-0 px-1.5 py-0.5 text-[10px] font-bold bg-indigo-500/30 text-indigo-300 rounded-md border border-indigo-500/40">
                              YOU
                            </span>
                          )}
                        </div>
                      </div>
                      <span className="text-green-400 font-bold text-sm flex-shrink-0">{entry.points} pts</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
