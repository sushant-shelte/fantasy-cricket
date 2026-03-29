import { useState, useEffect } from 'react';
import client from '../api/client';
import { useAuth } from '../auth/AuthContext';
import type { PointsTableEntry } from '../types';

export default function PointsTablePage() {
  const [data, setData] = useState<(PointsTableEntry & { net?: number })[]>([]);
  const [loading, setLoading] = useState(true);
  const { profile } = useAuth();

  useEffect(() => {
    client
      .get('/api/points-table')
      .then((res) => setData(res.data || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const contestantSet = new Set<string>();
  const matchMap = new Map<string, Record<string, number>>();
  const netMap = new Map<string, Record<string, number>>();

  data.forEach((entry) => {
    contestantSet.add(entry.name);
    const mid = String(entry.match_id);
    if (!matchMap.has(mid)) matchMap.set(mid, {});
    if (!netMap.has(mid)) netMap.set(mid, {});
    matchMap.get(mid)![entry.name] = entry.points;
    netMap.get(mid)![entry.name] = entry.net || 0;
  });

  const contestants = Array.from(contestantSet);
  const matchIds = Array.from(matchMap.keys());

  const totalPoints: Record<string, number> = {};
  const totalBalance: Record<string, number> = {};
  contestants.forEach((c) => {
    totalPoints[c] = 0;
    totalBalance[c] = 0;
    matchIds.forEach((m) => {
      totalPoints[c] += matchMap.get(m)?.[c] || 0;
      totalBalance[c] += netMap.get(m)?.[c] || 0;
    });
  });

  const sortedContestants = [...contestants].sort((a, b) => totalPoints[b] - totalPoints[a]);
  const currentUserName = profile?.name || '';

  return (
    <div>
      <h2 className="text-xl font-bold text-white mb-4">Points Table</h2>

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-400" />
        </div>
      ) : data.length === 0 ? (
        <div className="text-center py-16 text-white/30">No points data available yet.</div>
      ) : (
        <div className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-white/5">
                  <th className="sticky left-0 z-20 bg-slate-900 px-4 py-3 text-left text-xs font-medium text-white/30 uppercase tracking-wider whitespace-nowrap border-r border-white/5 min-w-[7rem]">
                    Player
                  </th>
                  <th className="sticky left-[7rem] z-20 bg-slate-900 px-2 py-3 text-center text-xs font-medium text-white/30 uppercase tracking-wider whitespace-nowrap border-r border-white/5 min-w-[4.5rem]">
                    Total
                  </th>
                  <th className="sticky left-[11.5rem] z-20 bg-slate-900 px-2 py-3 text-center text-xs font-medium text-white/30 uppercase tracking-wider whitespace-nowrap border-r border-white/5 min-w-[4.5rem]">
                    Balance
                  </th>
                  {matchIds.map((mid) => (
                    <th key={mid} className="px-2 py-3 text-center text-xs font-medium text-white/30 uppercase tracking-wider whitespace-nowrap min-w-[5rem]">
                      <div>M{mid}</div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {sortedContestants.map((c) => {
                  const isMe = c === currentUserName;
                  const bal = totalBalance[c];
                  return (
                    <tr key={c} className={`transition-colors ${isMe ? 'bg-indigo-500/10' : 'hover:bg-white/5'}`}>
                      {/* Name */}
                      <td className={`sticky left-0 z-10 px-4 py-3 text-white font-medium whitespace-nowrap border-r border-white/5 min-w-[7rem] ${isMe ? 'bg-indigo-950' : 'bg-slate-900'}`}>
                        <div className="flex items-center gap-1.5">
                          <span className="truncate max-w-[5rem]">{c}</span>
                          {isMe && <span className="px-1 py-0.5 text-[8px] font-bold bg-indigo-500/30 text-indigo-300 rounded">YOU</span>}
                        </div>
                      </td>
                      {/* Total Points */}
                      <td className={`sticky left-[7rem] z-10 px-2 py-3 text-center font-bold text-white whitespace-nowrap border-r border-white/5 min-w-[4.5rem] ${isMe ? 'bg-indigo-950' : 'bg-slate-900'}`}>
                        {totalPoints[c]}
                      </td>
                      {/* Total Balance */}
                      <td className={`sticky left-[11.5rem] z-10 px-2 py-3 text-center font-bold whitespace-nowrap border-r border-white/5 min-w-[4.5rem] ${isMe ? 'bg-indigo-950' : 'bg-slate-900'} ${
                        bal > 0 ? 'text-green-400' : bal < 0 ? 'text-red-400' : 'text-white/30'
                      }`}>
                        {bal > 0 ? '+' : ''}{bal}
                      </td>
                      {/* Per match: points + net */}
                      {matchIds.map((mid) => {
                        const pts = matchMap.get(mid)?.[c] || 0;
                        const net = netMap.get(mid)?.[c] || 0;
                        return (
                          <td key={mid} className="px-2 py-3 text-center whitespace-nowrap min-w-[5rem]">
                            {pts ? (
                              <div>
                                <div className="text-white font-medium">{pts}</div>
                                <div className={`text-[10px] ${net > 0 ? 'text-green-400' : net < 0 ? 'text-red-400' : 'text-white/20'}`}>
                                  {net > 0 ? '+' : ''}{net}
                                </div>
                              </div>
                            ) : (
                              <span className="text-white/10">-</span>
                            )}
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
    </div>
  );
}
