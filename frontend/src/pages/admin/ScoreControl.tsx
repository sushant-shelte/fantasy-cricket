import { useEffect, useState } from 'react';
import client from '../../api/client';
import type { Match } from '../../types';

const statusBadge = (status: string) => {
  switch (status) {
    case 'live':
      return (
        <span className="inline-flex items-center gap-1 bg-green-100 text-green-700 text-xs font-semibold px-2.5 py-1 rounded-full">
          <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
          Live
        </span>
      );
    case 'over':
      return (
        <span className="inline-block bg-gray-100 text-gray-600 text-xs font-semibold px-2.5 py-1 rounded-full">
          Over
        </span>
      );
    default:
      return (
        <span className="inline-block bg-blue-100 text-blue-700 text-xs font-semibold px-2.5 py-1 rounded-full">
          Upcoming
        </span>
      );
  }
};

interface Toast {
  id: number;
  type: 'success' | 'error';
  message: string;
}

export default function ScoreControl() {
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(true);
  const [recalculating, setRecalculating] = useState<Record<number, boolean>>({});
  const [recalcAllLoading, setRecalcAllLoading] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);

  let toastId = 0;

  const addToast = (type: 'success' | 'error', message: string) => {
    const id = ++toastId;
    setToasts((prev) => [...prev, { id, type, message }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  };

  const fetchMatches = async () => {
    try {
      const res = await client.get('/api/admin/matches');
      setMatches(res.data);
    } catch (err) {
      console.error('Failed to fetch matches', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMatches();
  }, []);

  const recalculate = async (matchId: number) => {
    setRecalculating((prev) => ({ ...prev, [matchId]: true }));
    try {
      await client.post(`/api/admin/recalculate/${matchId}`);
      addToast('success', `Match #${matchId} scores recalculated successfully.`);
    } catch (err) {
      console.error('Recalculation failed', err);
      addToast('error', `Failed to recalculate match #${matchId}.`);
    } finally {
      setRecalculating((prev) => ({ ...prev, [matchId]: false }));
    }
  };

  const recalculateAll = async () => {
    setRecalcAllLoading(true);
    try {
      await Promise.all(matches.map((m) => client.post(`/api/admin/recalculate/${m.id}`)));
      addToast('success', 'All matches recalculated successfully.');
    } catch (err) {
      console.error('Recalculate all failed', err);
      addToast('error', 'Failed to recalculate some matches.');
    } finally {
      setRecalcAllLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600" />
      </div>
    );
  }

  return (
    <div>
      {/* Toast container */}
      <div className="fixed top-4 right-4 z-50 flex flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`px-4 py-3 rounded-lg shadow-lg text-sm font-medium text-white transition-all ${
              toast.type === 'success' ? 'bg-green-600' : 'bg-red-600'
            }`}
          >
            {toast.message}
          </div>
        ))}
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <h1 className="text-2xl font-bold text-gray-800">Score Control</h1>
        <button
          onClick={recalculateAll}
          disabled={recalcAllLoading}
          className="inline-flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
        >
          {recalcAllLoading ? (
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
          ) : (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          )}
          Recalculate All
        </button>
      </div>

      {/* Clear Data Section */}
      <div className="mb-8 bg-white rounded-2xl shadow-sm p-5">
        <h2 className="text-lg font-bold text-gray-800 mb-1">Clear Table Data</h2>
        <p className="text-sm text-gray-500 mb-4">Permanently delete all rows from a table. This cannot be undone.</p>
        <div className="flex flex-wrap gap-2">
          {['players', 'matches', 'user_teams', 'contestant_points', 'player_points'].map((table) => (
            <button
              key={table}
              onClick={async () => {
                if (!confirm(`Are you sure you want to delete ALL data from "${table}"? This cannot be undone.`)) return;
                try {
                  await client.delete(`/api/admin/clear/${table}`);
                  addToast('success', `Cleared all data from ${table}`);
                  fetchMatches();
                } catch (err) {
                  console.error(err);
                  addToast('error', `Failed to clear ${table}`);
                }
              }}
              className="inline-flex items-center gap-1.5 bg-red-50 text-red-700 border border-red-200 px-3 py-2 rounded-lg text-sm font-medium hover:bg-red-100 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
              {table}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {matches.map((match) => (
          <div
            key={match.id}
            className="bg-white rounded-2xl shadow-sm p-5 flex flex-col gap-3 hover:shadow-md transition-shadow"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-400 font-medium">Match #{match.id}</span>
              {statusBadge(match.status)}
            </div>
            <div className="text-center">
              <p className="text-lg font-bold text-gray-800">
                {match.team1} <span className="text-gray-400 font-normal">vs</span> {match.team2}
              </p>
              <p className="text-sm text-gray-500 mt-1">
                {match.match_date} at {match.match_time}
              </p>
            </div>
            <button
              onClick={() => recalculate(match.id)}
              disabled={recalculating[match.id]}
              className="mt-auto w-full inline-flex items-center justify-center gap-2 bg-gray-100 text-gray-700 px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-200 disabled:opacity-50 transition-colors"
            >
              {recalculating[match.id] ? (
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gray-600" />
              ) : (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              )}
              {recalculating[match.id] ? 'Recalculating...' : 'Recalculate'}
            </button>
          </div>
        ))}
        {matches.length === 0 && (
          <div className="col-span-full text-center text-gray-400 py-12">
            No matches found.
          </div>
        )}
      </div>
    </div>
  );
}
