import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import client from '../api/client';
import { useAuth } from '../auth/AuthContext';
import type { PointsTableEntry } from '../types';

export default function PointsTablePage() {
  const [data, setData] = useState<PointsTableEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const { profile } = useAuth();

  useEffect(() => {
    client
      .get('/api/points-table')
      .then((res) => setData(res.data || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // Build matrix: collect unique matches and contestants
  const contestantSet = new Set<string>();
  const matchMap = new Map<string, Record<string, number>>();

  data.forEach((entry) => {
    contestantSet.add(entry.User);
    if (!matchMap.has(entry.MatchID)) {
      matchMap.set(entry.MatchID, {});
    }
    matchMap.get(entry.MatchID)![entry.User] = entry.Points;
  });

  const contestants = Array.from(contestantSet);
  const matchIds = Array.from(matchMap.keys());

  // Compute totals per contestant
  const totals: Record<string, number> = {};
  contestants.forEach((c) => {
    totals[c] = 0;
    matchIds.forEach((m) => {
      totals[c] += matchMap.get(m)?.[c] || 0;
    });
  });

  // Sort contestants by total desc
  const sortedContestants = [...contestants].sort((a, b) => totals[b] - totals[a]);

  const currentUserName = profile?.name || '';

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-indigo-950 to-slate-900">
      {/* Header */}
      <header className="sticky top-0 z-30 bg-slate-950/80 backdrop-blur-lg border-b border-white/10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-3">
          <Link to="/dashboard" className="p-2 hover:bg-white/10 rounded-xl transition-all">
            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </Link>
          <div>
            <h1 className="text-lg font-bold text-white">Points Table</h1>
            <p className="text-xs text-indigo-300">Match-wise breakdown</p>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6">
        {loading ? (
          <div className="flex justify-center py-16">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-400" />
          </div>
        ) : data.length === 0 ? (
          <div className="text-center py-16 text-indigo-300">No points data available yet.</div>
        ) : (
          <div className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-white/5">
                    <th className="sticky left-0 z-10 bg-slate-900 px-4 py-3 text-left text-xs font-medium text-indigo-300 uppercase tracking-wider whitespace-nowrap border-r border-white/10">
                      Match
                    </th>
                    {sortedContestants.map((c) => {
                      const isMe = c === currentUserName;
                      return (
                        <th
                          key={c}
                          className={`px-3 py-3 text-center text-xs font-medium uppercase tracking-wider whitespace-nowrap ${
                            isMe
                              ? 'bg-indigo-500/15 text-indigo-200'
                              : 'text-indigo-300'
                          }`}
                        >
                          <div className="flex flex-col items-center gap-0.5">
                            <span className="truncate max-w-[6rem]">{c}</span>
                            {isMe && (
                              <span className="px-1.5 py-0.5 text-[9px] font-bold bg-indigo-500/30 text-indigo-300 rounded border border-indigo-500/40">
                                YOU
                              </span>
                            )}
                          </div>
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {matchIds.map((matchId) => (
                    <tr key={matchId} className="hover:bg-white/5 transition-colors">
                      <td className="sticky left-0 z-10 bg-slate-900 px-4 py-3 text-white font-medium whitespace-nowrap border-r border-white/10">
                        Match {matchId}
                      </td>
                      {sortedContestants.map((c) => {
                        const pts = matchMap.get(matchId)?.[c] || 0;
                        const isMe = c === currentUserName;
                        return (
                          <td
                            key={c}
                            className={`px-3 py-3 text-center font-medium ${
                              isMe ? 'bg-indigo-500/10' : ''
                            } ${pts > 0 ? 'text-green-400' : pts < 0 ? 'text-red-400' : 'text-indigo-400'}`}
                          >
                            {pts}
                          </td>
                        );
                      })}
                    </tr>
                  ))}

                  {/* Totals row */}
                  <tr className="bg-white/5 border-t-2 border-white/20">
                    <td className="sticky left-0 z-10 bg-slate-800 px-4 py-3 text-white font-bold whitespace-nowrap border-r border-white/10">
                      TOTAL
                    </td>
                    {sortedContestants.map((c) => {
                      const isMe = c === currentUserName;
                      return (
                        <td
                          key={c}
                          className={`px-3 py-3 text-center font-bold ${
                            isMe ? 'bg-indigo-500/15 text-green-300' : 'text-green-400'
                          }`}
                        >
                          {totals[c]}
                        </td>
                      );
                    })}
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
