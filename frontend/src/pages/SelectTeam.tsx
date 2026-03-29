import { useState, useEffect, type FormEvent } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import client from '../api/client';
import type { Player, TeamSelection } from '../types';

interface SelectedPlayer {
  player_id: number;
  is_captain: boolean;
  is_vice_captain: boolean;
}

interface PlayingXiState {
  announced: boolean;
  url: string | null;
}

const ROLE_CONFIG: Record<string, { label: string; color: string; bg: string; border: string }> = {
  Wicketkeeper: { label: 'Wicket-Keeper', color: 'text-purple-300', bg: 'bg-purple-500/20', border: 'border-purple-500/30' },
  Batter: { label: 'Batsman', color: 'text-blue-300', bg: 'bg-blue-500/20', border: 'border-blue-500/30' },
  AllRounder: { label: 'All-Rounder', color: 'text-green-300', bg: 'bg-green-500/20', border: 'border-green-500/30' },
  Bowler: { label: 'Bowler', color: 'text-red-300', bg: 'bg-red-500/20', border: 'border-red-500/30' },
};

export default function SelectTeamPage() {
  const { matchId } = useParams<{ matchId: string }>();
  const navigate = useNavigate();

  const [players, setPlayers] = useState<Player[]>([]);
  const [selected, setSelected] = useState<Map<number, SelectedPlayer>>(new Map());
  const [expandedRoles, setExpandedRoles] = useState<Set<string>>(new Set(['Wicketkeeper', 'Batter', 'AllRounder', 'Bowler']));
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [showPreview, setShowPreview] = useState(false);
  const [playingXi, setPlayingXi] = useState<PlayingXiState>({ announced: false, url: null });

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [playersRes, teamRes] = await Promise.all([
          client.get(`/api/players?match_id=${matchId}`),
          client.get(`/api/teams/my?match_id=${matchId}`).catch(() => ({ data: [] })),
        ]);
        // API returns {Wicketkeeper: [...], Batter: [...], ...} — flatten to array
        const data = playersRes.data || {};
        const groupedPlayers = data.players || data;
        const flat = Array.isArray(groupedPlayers)
          ? groupedPlayers
          : Object.values(groupedPlayers).flat() as Player[];
        setPlayers(flat);
        setPlayingXi({
          announced: Boolean(data.playing_xi?.announced),
          url: data.playing_xi?.url || null,
        });

        // Pre-select existing team
        const existing: TeamSelection[] = teamRes.data || [];
        if (existing.length > 0) {
          const map = new Map<number, SelectedPlayer>();
          existing.forEach((t) => {
            map.set(t.player_id, {
              player_id: t.player_id,
              is_captain: t.is_captain,
              is_vice_captain: t.is_vice_captain,
            });
          });
          setSelected(map);
        }
      } catch {
        setError('Failed to load players.');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [matchId]);

  const toggleRole = (role: string) => {
    setExpandedRoles((prev) => {
      const next = new Set(prev);
      if (next.has(role)) next.delete(role);
      else next.add(role);
      return next;
    });
  };

  const togglePlayer = (playerId: number) => {
    setSelected((prev) => {
      const next = new Map(prev);
      if (next.has(playerId)) {
        next.delete(playerId);
      } else {
        next.set(playerId, { player_id: playerId, is_captain: false, is_vice_captain: false });
      }
      return next;
    });
  };

  const setCaptain = (playerId: number) => {
    setSelected((prev) => {
      const next = new Map(prev);
      next.forEach((v, k) => {
        next.set(k, { ...v, is_captain: k === playerId });
      });
      return next;
    });
  };

  const setViceCaptain = (playerId: number) => {
    setSelected((prev) => {
      const next = new Map(prev);
      next.forEach((v, k) => {
        next.set(k, { ...v, is_vice_captain: k === playerId });
      });
      return next;
    });
  };

  const groupedPlayers = () => {
    const groups: Record<string, Player[]> = {};
    players.forEach((p) => {
      const role = p.role || 'OTHER';
      if (!groups[role]) groups[role] = [];
      groups[role].push(p);
    });

    Object.values(groups).forEach((group) => {
      group.sort((a, b) => {
        const playingDiff = Number(Boolean(b.is_playing_xi)) - Number(Boolean(a.is_playing_xi));
        if (playingDiff !== 0) return playingDiff;
        const pointsDiff = (b.total_points || 0) - (a.total_points || 0);
        if (pointsDiff !== 0) return pointsDiff;
        return a.name.localeCompare(b.name);
      });
    });

    return groups;
  };

  const selectedCount = selected.size;
  const captainId = [...selected.values()].find((s) => s.is_captain)?.player_id;
  const vcId = [...selected.values()].find((s) => s.is_vice_captain)?.player_id;
  const selectedByTeam: Record<string, number> = {};

  players.forEach((player) => {
    if (!selected.has(player.id)) return;
    selectedByTeam[player.team] = (selectedByTeam[player.team] || 0) + 1;
  });

  const teamsInMatch = [...new Set(players.map((player) => player.team))].sort();

  const validate = (): string | null => {
    if (selectedCount !== 11) return `Select exactly 11 players (currently ${selectedCount}).`;
    if (!captainId) return 'Select a Captain.';
    if (!vcId) return 'Select a Vice Captain.';
    if (captainId === vcId) return 'Captain and Vice Captain must be different players.';

    // Check at least 1 per role
    const groups = groupedPlayers();
    const roles = Object.keys(groups);
    for (const role of roles) {
      const count = groups[role].filter((p) => selected.has(p.id)).length;
      if (count === 0) return `Select at least 1 ${ROLE_CONFIG[role]?.label || role}.`;
    }

    return null;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }

    setSubmitting(true);
    try {
      const payload = {
        match_id: Number(matchId),
        players: [...selected.values()],
      };
      await client.post('/api/teams', payload);
      setSuccess('Team saved successfully!');
      setShowPreview(true);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.response?.data?.error || 'Failed to save team.';
      setError(msg);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } finally {
      setSubmitting(false);
    }
  };

  const groups = groupedPlayers();
  const roleOrder = ['Wicketkeeper', 'Batter', 'AllRounder', 'Bowler'];
  const sortedRoles = [...new Set([...roleOrder, ...Object.keys(groups)])].filter((r) => groups[r]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-950 via-indigo-950 to-slate-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-400" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-indigo-950 to-slate-900 pb-24">
      {/* Sticky header */}
      <header className="sticky top-0 z-30 bg-slate-950/80 backdrop-blur-lg border-b border-white/10">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/dashboard" className="p-2 hover:bg-white/10 rounded-xl transition-all">
              <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </Link>
            <div>
              <h1 className="text-lg font-bold text-white">Select Your Team</h1>
              <p className="text-xs text-indigo-300">Match #{matchId}</p>
            </div>
          </div>
          <div
            className={`px-3 py-1.5 rounded-xl font-bold text-sm ${
              selectedCount === 11
                ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                : 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30'
            }`}
          >
            {selectedCount}/11
          </div>
        </div>
        <div className="max-w-3xl mx-auto px-4 pb-3 flex flex-wrap gap-2">
          {teamsInMatch.map((team) => (
            <div
              key={team}
              className="px-3 py-1.5 rounded-xl text-xs font-semibold bg-white/5 border border-white/10 text-indigo-100"
            >
              {team}: <span className="text-emerald-300">{selectedByTeam[team] || 0}</span>
            </div>
          ))}
        </div>
      </header>

      <form onSubmit={handleSubmit} className="max-w-3xl mx-auto px-4 py-4 space-y-4">
        {error && (
          <div className="p-3 bg-red-500/20 border border-red-400/30 rounded-xl text-red-200 text-sm text-center">
            {error}
          </div>
        )}
        {success && (
          <div className="p-3 bg-green-500/20 border border-green-400/30 rounded-xl text-green-200 text-sm text-center">
            {success}
          </div>
        )}

        {/* Captain / VC legend */}
        <div className="flex items-center gap-4 text-xs text-indigo-300">
          <span className="flex items-center gap-1.5">
            <span className="w-5 h-5 bg-amber-500/30 border border-amber-500/50 rounded-full flex items-center justify-center text-[10px] font-bold text-amber-300">C</span>
            Captain (2x)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-5 h-5 bg-sky-500/30 border border-sky-500/50 rounded-full flex items-center justify-center text-[10px] font-bold text-sky-300">VC</span>
            Vice Captain (1.5x)
          </span>
        </div>

        <div className={`rounded-2xl border px-4 py-3 text-sm ${
          playingXi.announced
            ? 'bg-emerald-500/10 border-emerald-400/20 text-emerald-100'
            : 'bg-amber-500/10 border-amber-400/20 text-amber-100'
        }`}>
          <div className="font-semibold">
            {playingXi.announced ? 'Playing XI announced' : 'Playing XI not announced yet'}
          </div>
          <div className="mt-1 text-xs opacity-90">
            {playingXi.announced
              ? 'Players tagged as Playing XI are from the current post-toss lineup.'
              : 'The app starts checking ESPN around 30 minutes before match start and will highlight confirmed starters once they appear.'}
          </div>
          {playingXi.url && (
            <a
              href={playingXi.url}
              target="_blank"
              rel="noreferrer"
              className="mt-2 inline-flex text-xs font-semibold text-cyan-300 hover:text-cyan-200"
            >
              Open ESPN playing XI page
            </a>
          )}
        </div>

        {sortedRoles.map((role) => {
          const config = ROLE_CONFIG[role] || { label: role, color: 'text-gray-300', bg: 'bg-gray-500/20', border: 'border-gray-500/30' };
          const rolePlayers = groups[role];
          const roleSelected = rolePlayers.filter((p) => selected.has(p.id)).length;
          const isExpanded = expandedRoles.has(role);

          return (
            <div key={role} className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden">
              {/* Role header */}
              <button
                type="button"
                onClick={() => toggleRole(role)}
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/5 transition-all"
              >
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-0.5 text-xs font-bold rounded-lg ${config.bg} ${config.color} ${config.border} border`}>
                    {role}
                  </span>
                  <span className="text-white font-medium text-sm">{config.label}</span>
                  <span className="text-indigo-400 text-xs">({roleSelected} selected)</span>
                </div>
                <svg
                  className={`w-4 h-4 text-indigo-400 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {/* Player rows */}
              {isExpanded && (
                <div className="border-t border-white/5">
                  {rolePlayers.map((player) => {
                    const isSelected = selected.has(player.id);
                    const isCaptain = captainId === player.id;
                    const isVC = vcId === player.id;

                    return (
                      <div
                        key={player.id}
                        className={`flex items-center gap-3 px-4 py-3 border-b border-white/5 last:border-b-0 transition-all ${
                          isSelected
                            ? 'bg-indigo-500/10'
                            : player.is_playing_xi === false
                              ? 'bg-white/[0.03] hover:bg-white/[0.06]'
                              : 'hover:bg-white/5'
                        }`}
                      >
                        {/* Checkbox */}
                        <button
                          type="button"
                          onClick={() => togglePlayer(player.id)}
                          className={`flex-shrink-0 w-5 h-5 rounded-md border-2 flex items-center justify-center transition-all ${
                            isSelected
                              ? 'bg-green-500 border-green-500'
                              : 'border-white/30 hover:border-white/50'
                          }`}
                        >
                          {isSelected && (
                            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                            </svg>
                          )}
                        </button>

                        {/* Player info */}
                        <div className="flex-1 min-w-0">
                          <p className="text-white text-sm font-medium truncate">{player.name}</p>
                          <div className="flex flex-wrap items-center gap-2 text-xs">
                            <span className="text-indigo-400">{player.team}</span>
                            <span className="text-emerald-300 font-semibold">
                              {(player.total_points || 0).toFixed(2)} pts
                            </span>
                            {player.is_playing_xi === true && (
                              <span className="rounded-full border border-emerald-400/30 bg-emerald-500/15 px-2 py-0.5 font-semibold text-emerald-200">
                                Playing XI
                              </span>
                            )}
                            {player.is_playing_xi === false && (
                              <span className="rounded-full border border-slate-500/30 bg-slate-500/10 px-2 py-0.5 font-semibold text-slate-300">
                                Squad
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Captain radio */}
                        <button
                          type="button"
                          onClick={() => isSelected && setCaptain(player.id)}
                          disabled={!isSelected}
                          className={`flex-shrink-0 w-7 h-7 rounded-full border-2 flex items-center justify-center text-[10px] font-bold transition-all ${
                            isCaptain
                              ? 'bg-amber-500 border-amber-500 text-white'
                              : isSelected
                              ? 'border-amber-500/50 text-amber-400/50 hover:border-amber-500 hover:text-amber-400'
                              : 'border-white/10 text-white/10 cursor-not-allowed'
                          }`}
                        >
                          C
                        </button>

                        {/* Vice Captain radio */}
                        <button
                          type="button"
                          onClick={() => isSelected && setViceCaptain(player.id)}
                          disabled={!isSelected}
                          className={`flex-shrink-0 w-7 h-7 rounded-full border-2 flex items-center justify-center text-[10px] font-bold transition-all ${
                            isVC
                              ? 'bg-sky-500 border-sky-500 text-white'
                              : isSelected
                              ? 'border-sky-500/50 text-sky-400/50 hover:border-sky-500 hover:text-sky-400'
                              : 'border-white/10 text-white/10 cursor-not-allowed'
                          }`}
                        >
                          VC
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </form>

      {/* Sticky submit bar */}
      <div className="fixed bottom-0 left-0 right-0 z-30 bg-slate-950/90 backdrop-blur-lg border-t border-white/10">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
          <div className="text-sm min-w-0">
            <span className={`font-bold ${selectedCount === 11 ? 'text-green-400' : 'text-indigo-300'}`}>
              {selectedCount}/11
            </span>
            <span className="text-indigo-400 ml-2">
              {captainId ? 'C' : ''}{captainId && vcId ? ' / ' : ''}{vcId ? 'VC' : ''}
              {!captainId && !vcId && 'No C/VC'}
            </span>
            <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-300">
              {teamsInMatch.map((team) => (
                <span key={team}>
                  {team}: <span className="text-emerald-300 font-semibold">{selectedByTeam[team] || 0}</span>
                </span>
              ))}
            </div>
          </div>
          <button
            onClick={(e) => {
              e.preventDefault();
              const form = document.querySelector('form');
              form?.requestSubmit();
            }}
            disabled={submitting}
            className="px-6 py-2.5 bg-green-500 hover:bg-green-600 text-white font-semibold rounded-xl shadow-lg shadow-green-500/30 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? (
              <span className="inline-flex items-center gap-2">
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Saving...
              </span>
            ) : (
              'Save Team'
            )}
          </button>
        </div>
      </div>

      {/* Team Preview Modal */}
      {showPreview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div className="w-full max-w-md relative">
            {/* Ground */}
            <div className="rounded-3xl overflow-hidden shadow-2xl"
              style={{ background: 'linear-gradient(180deg, #1a5e1a 0%, #2d8a2d 30%, #3da33d 50%, #2d8a2d 70%, #1a5e1a 100%)' }}>

              {/* Header */}
              <div className="text-center pt-4 pb-2">
                <p className="text-white/60 text-xs font-medium uppercase tracking-wider">Your Team</p>
                <p className="text-white text-lg font-bold">Fantasy Cricket</p>
              </div>

              {/* Pitch lines */}
              <div className="relative px-4 pb-6">
                {/* Oval border */}
                <div className="absolute inset-x-8 inset-y-4 border-2 border-white/15 rounded-[50%]" />

                {/* Wicketkeeper */}
                <div className="relative z-10 mb-4">
                  <p className="text-center text-white/40 text-[10px] uppercase tracking-widest mb-2">Wicketkeeper</p>
                  <div className="flex justify-center gap-3 flex-wrap">
                    {players.filter(p => selected.has(p.id) && p.role === 'Wicketkeeper').map(p => (
                      <div key={p.id} className="flex flex-col items-center">
                        <div className={`w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold shadow-lg ${
                          captainId === p.id ? 'bg-amber-400 text-black ring-2 ring-amber-300' :
                          vcId === p.id ? 'bg-sky-400 text-black ring-2 ring-sky-300' :
                          'bg-white text-green-900'
                        }`}>
                          {captainId === p.id ? 'C' : vcId === p.id ? 'VC' : p.name.charAt(0)}
                        </div>
                        <p className="text-white text-[10px] font-medium mt-1 max-w-[60px] text-center truncate">{p.name.split(' ').pop()}</p>
                        <span className="text-white/40 text-[8px]">{p.team}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Batters */}
                <div className="relative z-10 mb-4">
                  <p className="text-center text-white/40 text-[10px] uppercase tracking-widest mb-2">Batters</p>
                  <div className="flex justify-center gap-3 flex-wrap">
                    {players.filter(p => selected.has(p.id) && p.role === 'Batter').map(p => (
                      <div key={p.id} className="flex flex-col items-center">
                        <div className={`w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold shadow-lg ${
                          captainId === p.id ? 'bg-amber-400 text-black ring-2 ring-amber-300' :
                          vcId === p.id ? 'bg-sky-400 text-black ring-2 ring-sky-300' :
                          'bg-white text-green-900'
                        }`}>
                          {captainId === p.id ? 'C' : vcId === p.id ? 'VC' : p.name.charAt(0)}
                        </div>
                        <p className="text-white text-[10px] font-medium mt-1 max-w-[60px] text-center truncate">{p.name.split(' ').pop()}</p>
                        <span className="text-white/40 text-[8px]">{p.team}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* All-Rounders */}
                <div className="relative z-10 mb-4">
                  <p className="text-center text-white/40 text-[10px] uppercase tracking-widest mb-2">All-Rounders</p>
                  <div className="flex justify-center gap-3 flex-wrap">
                    {players.filter(p => selected.has(p.id) && p.role === 'AllRounder').map(p => (
                      <div key={p.id} className="flex flex-col items-center">
                        <div className={`w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold shadow-lg ${
                          captainId === p.id ? 'bg-amber-400 text-black ring-2 ring-amber-300' :
                          vcId === p.id ? 'bg-sky-400 text-black ring-2 ring-sky-300' :
                          'bg-white text-green-900'
                        }`}>
                          {captainId === p.id ? 'C' : vcId === p.id ? 'VC' : p.name.charAt(0)}
                        </div>
                        <p className="text-white text-[10px] font-medium mt-1 max-w-[60px] text-center truncate">{p.name.split(' ').pop()}</p>
                        <span className="text-white/40 text-[8px]">{p.team}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Bowlers */}
                <div className="relative z-10">
                  <p className="text-center text-white/40 text-[10px] uppercase tracking-widest mb-2">Bowlers</p>
                  <div className="flex justify-center gap-3 flex-wrap">
                    {players.filter(p => selected.has(p.id) && p.role === 'Bowler').map(p => (
                      <div key={p.id} className="flex flex-col items-center">
                        <div className={`w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold shadow-lg ${
                          captainId === p.id ? 'bg-amber-400 text-black ring-2 ring-amber-300' :
                          vcId === p.id ? 'bg-sky-400 text-black ring-2 ring-sky-300' :
                          'bg-white text-green-900'
                        }`}>
                          {captainId === p.id ? 'C' : vcId === p.id ? 'VC' : p.name.charAt(0)}
                        </div>
                        <p className="text-white text-[10px] font-medium mt-1 max-w-[60px] text-center truncate">{p.name.split(' ').pop()}</p>
                        <span className="text-white/40 text-[8px]">{p.team}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Footer legend */}
              <div className="flex justify-center gap-4 pb-4 text-[10px] text-white/50">
                <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-amber-400"></span> Captain (2x)</span>
                <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-sky-400"></span> Vice Captain (1.5x)</span>
              </div>
            </div>

            {/* Close button */}
            <button
              onClick={() => { setShowPreview(false); navigate('/dashboard'); }}
              className="mt-4 w-full py-3 bg-indigo-500 hover:bg-indigo-400 text-white font-semibold rounded-xl shadow-lg transition-all"
            >
              Go to Dashboard
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
