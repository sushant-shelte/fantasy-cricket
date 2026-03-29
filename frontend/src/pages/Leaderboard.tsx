import { useState, useEffect, useRef } from 'react';
import client from '../api/client';
import { useAuth } from '../auth/AuthContext';
import type { LeaderboardEntry } from '../types';

export default function LeaderboardPage() {
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const { profile } = useAuth();
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchLeaderboard = async () => {
    try {
      const res = await client.get('/api/leaderboard');
      setEntries(res.data || []);
    } catch { /* silent */ }
    finally { setLoading(false); }
  };

  useEffect(() => {
    fetchLeaderboard();
    intervalRef.current = setInterval(fetchLeaderboard, 1800000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, []);

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchLeaderboard();
    setRefreshing(false);
  };

  const sorted = [...entries].sort((a, b) => b.points - a.points);
  const ranked: (LeaderboardEntry & { rank: number })[] = [];
  sorted.forEach((entry, i) => {
    let rank = i + 1;
    if (i > 0 && entry.points === sorted[i - 1].points) {
      rank = ranked[i - 1].rank;
    }
    ranked.push({ ...entry, rank });
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold text-white">Leaderboard</h2>
        <button onClick={handleRefresh} disabled={refreshing}
          className="p-2 hover:bg-white/10 rounded-xl transition-all disabled:opacity-50" title="Refresh">
          <svg className={`w-5 h-5 text-indigo-300 ${refreshing ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-400" />
        </div>
      ) : ranked.length === 0 ? (
        <div className="text-center py-16 text-indigo-400">No leaderboard data yet.</div>
      ) : (
        <>
          {ranked.length >= 3 && (
            <div className="flex items-end justify-center gap-4 mb-8 pt-4">
              <div className="flex flex-col items-center">
                <div className="w-16 h-16 sm:w-20 sm:h-20 bg-slate-500/10 border-2 border-slate-400/20 rounded-2xl flex items-center justify-center mb-2">
                  <span className="text-2xl sm:text-3xl">&#x1F948;</span>
                </div>
                <p className="text-white text-sm font-medium text-center truncate max-w-[5rem]">{ranked[1].name}</p>
                <p className="text-slate-400 text-xs font-bold">{ranked[1].points} pts</p>
              </div>
              <div className="flex flex-col items-center -mt-4">
                <div className="w-20 h-20 sm:w-24 sm:h-24 bg-amber-500/15 border-2 border-amber-400/30 rounded-2xl flex items-center justify-center mb-2 shadow-lg shadow-amber-500/10">
                  <span className="text-3xl sm:text-4xl">&#x1F947;</span>
                </div>
                <p className="text-white text-sm font-bold text-center truncate max-w-[5rem]">{ranked[0].name}</p>
                <p className="text-amber-400 text-xs font-bold">{ranked[0].points} pts</p>
              </div>
              <div className="flex flex-col items-center mt-2">
                <div className="w-16 h-16 sm:w-20 sm:h-20 bg-orange-500/10 border-2 border-orange-500/20 rounded-2xl flex items-center justify-center mb-2">
                  <span className="text-2xl sm:text-3xl">&#x1F949;</span>
                </div>
                <p className="text-white text-sm font-medium text-center truncate max-w-[5rem]">{ranked[2].name}</p>
                <p className="text-orange-400 text-xs font-bold">{ranked[2].points} pts</p>
              </div>
            </div>
          )}

          <div className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden backdrop-blur-sm">
            <div className="divide-y divide-white/5">
              {ranked.map((entry, i) => {
                const isMe = profile?.name === entry.name;
                return (
                  <div key={i}
                    className={`flex items-center px-4 py-3.5 transition-colors ${isMe ? 'bg-indigo-500/10' : 'hover:bg-white/5'}`}>
                    <div className="w-10 text-center flex-shrink-0">
                      {entry.rank === 1 ? <span className="text-lg">&#x1F947;</span>
                        : entry.rank === 2 ? <span className="text-lg">&#x1F948;</span>
                        : entry.rank === 3 ? <span className="text-lg">&#x1F949;</span>
                        : <span className="text-indigo-400 font-semibold text-sm">{entry.rank}</span>}
                    </div>
                    <div className="flex-1 min-w-0 ml-2">
                      <div className="flex items-center gap-2">
                        <span className={`text-sm font-medium truncate ${isMe ? 'text-indigo-200' : 'text-white'}`}>{entry.name}</span>
                        {isMe && <span className="flex-shrink-0 px-1.5 py-0.5 text-[10px] font-bold bg-indigo-500/30 text-indigo-300 rounded-md border border-indigo-500/30">YOU</span>}
                      </div>
                    </div>
                    <span className={`font-bold text-sm flex-shrink-0 ${isMe ? 'text-green-400' : 'text-green-400/80'}`}>{entry.points} pts</span>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
