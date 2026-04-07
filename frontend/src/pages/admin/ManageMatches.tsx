import { useEffect, useState } from 'react';
import client from '../../api/client';
import type { Match } from '../../types';

const IPL_TEAMS = ['CSK', 'RCB', 'MI', 'KKR', 'RR', 'GT', 'DC', 'LSG', 'PBKS', 'SRH'];

interface MatchForm {
  team1: string;
  team2: string;
  match_date: string;
  match_time: string;
}

const emptyForm: MatchForm = { team1: 'CSK', team2: 'RCB', match_date: '', match_time: '' };

const statusBadge = (status: string) => {
  switch (status) {
    case 'live':
      return (
        <span className="inline-flex items-center gap-1 bg-green-100 text-green-700 text-xs font-semibold px-2.5 py-1 rounded-full">
          <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
          Live
        </span>
      );
    case 'completed':
      return (
        <span className="inline-block bg-gray-100 text-gray-600 text-xs font-semibold px-2.5 py-1 rounded-full">
          Completed
        </span>
      );
    case 'nr':
      return (
        <span className="inline-block bg-rose-100 text-rose-700 text-xs font-semibold px-2.5 py-1 rounded-full">
          No Result
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

export default function ManageMatches() {
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<MatchForm>(emptyForm);
  const [saving, setSaving] = useState(false);

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

  const openAdd = () => {
    setEditingId(null);
    setForm(emptyForm);
    setModalOpen(true);
  };

  const openEdit = (match: Match) => {
    setEditingId(match.id);
    setForm({
      team1: match.team1,
      team2: match.team2,
      match_date: match.match_date,
      match_time: match.match_time,
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (editingId) {
        await client.put(`/api/admin/matches/${editingId}`, form);
      } else {
        await client.post('/api/admin/matches', form);
      }
      setModalOpen(false);
      await fetchMatches();
    } catch (err) {
      console.error('Failed to save match', err);
      alert('Failed to save match');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Are you sure you want to delete this match?')) return;
    try {
      await client.delete(`/api/admin/matches/${id}`);
      await fetchMatches();
    } catch (err) {
      console.error('Failed to delete match', err);
      alert('Failed to delete match');
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
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <h1 className="text-2xl font-bold text-gray-800">Manage Matches</h1>
        <button
          onClick={openAdd}
          className="inline-flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Add Match
        </button>
      </div>

      <div className="bg-white rounded-2xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="bg-gray-50 text-gray-600 uppercase text-xs">
              <tr>
                <th className="px-6 py-3">ID</th>
                <th className="px-6 py-3">Team 1</th>
                <th className="px-6 py-3">Team 2</th>
                <th className="px-6 py-3">Date</th>
                <th className="px-6 py-3">Time</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {matches.map((match) => (
                <tr key={match.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-4 text-gray-500">{match.id}</td>
                  <td className="px-6 py-4 font-medium text-gray-800">{match.team1}</td>
                  <td className="px-6 py-4 font-medium text-gray-800">{match.team2}</td>
                  <td className="px-6 py-4 text-gray-600">{match.match_date}</td>
                  <td className="px-6 py-4 text-gray-600">{match.match_time}</td>
                  <td className="px-6 py-4">{statusBadge(match.status)}</td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => openEdit(match)}
                        className="text-indigo-600 hover:text-indigo-800 text-xs font-medium"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleDelete(match.id)}
                        className="text-red-600 hover:text-red-800 text-xs font-medium"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {matches.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-6 py-8 text-center text-gray-400">
                    No matches found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="fixed inset-0 bg-black/50" onClick={() => setModalOpen(false)} />
          <div className="relative bg-white rounded-2xl shadow-xl w-full max-w-md mx-4 p-6 z-10">
            <h2 className="text-lg font-bold text-gray-800 mb-4">
              {editingId ? 'Edit Match' : 'Add Match'}
            </h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Team 1</label>
                <select
                  value={form.team1}
                  onChange={(e) => setForm({ ...form, team1: e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  {IPL_TEAMS.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Team 2</label>
                <select
                  value={form.team2}
                  onChange={(e) => setForm({ ...form, team2: e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  {IPL_TEAMS.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Date</label>
                <input
                  type="date"
                  value={form.match_date}
                  onChange={(e) => setForm({ ...form, match_date: e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Time</label>
                <input
                  type="time"
                  value={form.match_time}
                  onChange={(e) => setForm({ ...form, match_time: e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setModalOpen(false)}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving || !form.match_date || !form.match_time}
                className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
