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
    contestantSet.add(entry.name);
    const mid = String(entry.match_id);
    if (!matchMap.has(mid)) {
      matchMap.set(mid, {});
    }
    matchMap.get(mid)![entry.name] = entry.points;
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
                    <th className="sticky left-0 z-20 bg-slate-900 px-4 py-3 text-left text-xs font-medium text-indigo-300 uppercase tracking-wider whitespace-nowrap border-r border-white/10 min-w-[8rem]">
                      Contestant
                    </th>
                    <th className="sticky left-[8rem] z-20 bg-slate-900 px-3 py-3 text-center text-xs font-medium text-indigo-300 uppercase tracking-wider whitespace-nowrap border-r border-white/10 min-w-[5rem]">
                      Total
                    </th>
                    {matchIds.map((mid, i) => (
                      <th
                        key={mid}
                        className="px-3 py-3 text-center text-xs font-medium text-indigo-300 uppercase tracking-wider whitespace-nowrap"
                      >
                        M{i + 1}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {sortedContestants.map((c) => {
                    const isMe = c === currentUserName;
                    return (
                      <tr key={c} className={`hover:bg-white/5 transition-colors ${isMe ? 'bg-indigo-500/10' : ''}`}>
                        <td className={`sticky left-0 z-10 px-4 py-3 text-white font-medium whitespace-nowrap border-r border-white/10 min-w-[8rem] ${isMe ? 'bg-indigo-950' : 'bg-slate-900'}`}>
                          <div className="flex items-center gap-2">
                            <span className="truncate max-w-[6rem]">{c}</span>
                            {isMe && (
                              <span className="px-1.5 py-0.5 text-[9px] font-bold bg-indigo-500/30 text-indigo-300 rounded border border-indigo-500/40">
                                YOU
                              </span>
                            )}
                          </div>
                        </td>
                        <td className={`sticky left-[8rem] z-10 px-3 py-3 text-center font-bold text-green-400 whitespace-nowrap border-r border-white/10 min-w-[5rem] ${isMe ? 'bg-indigo-950' : 'bg-slate-900'}`}>
                          {totals[c]}
                        </td>
                        {matchIds.map((mid) => {
                          const pts = matchMap.get(mid)?.[c] || 0;
                          return (
                            <td
                              key={mid}
                              className={`px-3 py-3 text-center font-medium ${pts > 0 ? 'text-green-400' : pts < 0 ? 'text-red-400' : 'text-indigo-400'}`}
                            >
                              {pts}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
