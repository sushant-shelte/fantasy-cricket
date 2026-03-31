import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import client from '../api/client';
import { useAuth } from '../auth/AuthContext';

export default function SettingsPage() {
  const navigate = useNavigate();
  const { profile, refreshProfile } = useAuth();
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setName(profile?.name || '');
  }, [profile?.name]);

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    const cleanedName = name.trim();
    if (!cleanedName) {
      setError('Name is required.');
      return;
    }

    setSaving(true);
    setError('');
    try {
      await client.patch('/api/auth/me', { name: cleanedName });
      await refreshProfile();
      navigate('/dashboard');
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to update name.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-xl px-4 py-4">
      <div className="mb-6 flex items-center gap-3">
        <Link to="/dashboard" className="rounded-xl p-2 transition-all hover:bg-white/10">
          <svg className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </Link>
        <div>
          <h1 className="text-lg font-bold text-white">Settings</h1>
          <p className="text-xs text-white/45">Update the name shown in the app.</p>
        </div>
      </div>

      <form onSubmit={handleSave} className="rounded-2xl border border-white/10 bg-white/5 p-5">
        <label className="block text-sm font-medium text-white/80" htmlFor="display-name">
          Display Name
        </label>
        <input
          id="display-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={50}
          className="mt-2 w-full rounded-xl border border-white/10 bg-black/40 px-4 py-3 text-white outline-none transition-all placeholder:text-white/25 focus:border-green-500/40"
          placeholder="Your name"
        />
        <p className="mt-2 text-xs text-white/35">This name is shown across the app.</p>

        {error && (
          <div className="mt-4 rounded-xl border border-red-400/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            {error}
          </div>
        )}

        <div className="mt-6 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={() => navigate('/dashboard')}
            className="rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm font-medium text-white/75 transition-all hover:bg-white/10"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="rounded-xl bg-green-500 px-5 py-2.5 text-sm font-semibold text-black transition-all hover:bg-green-400 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </form>
    </div>
  );
}
