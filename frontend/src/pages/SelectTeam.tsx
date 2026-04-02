import { useState, useEffect, type FormEvent } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import client from '../api/client';
import type { Player, TeamSelection } from '../types';
import { getTeamTheme } from '../utils/teamTheme';

interface SelectedPlayer {
  player_id: number;
  is_captain: boolean;
  is_vice_captain: boolean;
}

interface PlayingXiState {
  announced: boolean;
  url: string | null;
  substituteCount?: number;
}

const ROLE_CONFIG: Record<string, { label: string; color: string; bg: string; border: string }> = {
  Wicketkeeper: { label: 'WK', color: 'text-white/70', bg: 'bg-white/10', border: 'border-white/20' },
  Batter: { label: 'BAT', color: 'text-white/70', bg: 'bg-white/10', border: 'border-white/20' },
  AllRounder: { label: 'AR', color: 'text-green-300', bg: 'bg-green-500/20', border: 'border-green-500/30' },
  Bowler: { label: 'BOWL', color: 'text-red-300', bg: 'bg-red-500/20', border: 'border-red-500/30' },
};

const REQUIRED_ROLES = ['Wicketkeeper', 'Batter', 'AllRounder', 'Bowler'] as const;

/* Ground view player node */
function GroundPlayer({
  player,
  isCaptain,
  isVC,
  teamBadge,
  onTap,
}: {
  player: Player;
  isCaptain: boolean;
  isVC: boolean;
  teamBadge: React.ReactNode;
  onTap: () => void;
}) {
  return (
    <button type="button" onClick={onTap} className="flex flex-col items-center group">
      <div
        className={`w-9 h-9 rounded-full flex items-center justify-center text-[10px] font-bold shadow-lg transition-transform group-active:scale-90 ${
          isCaptain
            ? 'bg-amber-400 text-black ring-2 ring-amber-300'
            : isVC
            ? 'bg-sky-400 text-black ring-2 ring-sky-300'
            : 'bg-white text-green-900'
        }`}
      >
        {isCaptain ? 'C' : isVC ? 'VC' : player.name.charAt(0)}
      </div>
      <p className="text-white text-[9px] font-medium mt-0.5 max-w-[56px] text-center truncate leading-tight">
        {player.name.split(' ').pop()}
      </p>
      <span className="mt-0.5">{teamBadge}</span>
    </button>
  );
}

/* Empty slot placeholder */
function EmptySlot({ label }: { label?: string }) {
  return (
    <div className="flex flex-col items-center opacity-30">
      <div className="w-9 h-9 rounded-full border-2 border-dashed border-white/40 flex items-center justify-center">
        <svg className="w-4 h-4 text-white/40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
        </svg>
      </div>
      {label && <p className="text-white/30 text-[8px] mt-0.5">{label}</p>}
    </div>
  );
}

export default function SelectTeamPage() {
  const { matchId } = useParams<{ matchId: string }>();
  const navigate = useNavigate();

  const [players, setPlayers] = useState<Player[]>([]);
  const [selected, setSelected] = useState<Map<number, SelectedPlayer>>(new Map());
  const [activeRole, setActiveRole] = useState<(typeof REQUIRED_ROLES)[number]>('Wicketkeeper');
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
        const data = playersRes.data || {};
        const groupedPlayers = data.players || data;
        const flat = Array.isArray(groupedPlayers)
          ? groupedPlayers
          : (Object.values(groupedPlayers).flat() as Player[]);
        setPlayers(flat);
        setPlayingXi({
          announced: Boolean(data.playing_xi?.announced),
          url: data.playing_xi?.url || null,
          substituteCount: data.playing_xi?.substitute_count || 0,
        });

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
        next.set(k, { ...v, is_captain: k === playerId, is_vice_captain: k === playerId ? false : v.is_vice_captain });
      });
      return next;
    });
  };

  const setViceCaptain = (playerId: number) => {
    setSelected((prev) => {
      const next = new Map(prev);
      next.forEach((v, k) => {
        next.set(k, { ...v, is_vice_captain: k === playerId, is_captain: k === playerId ? false : v.is_captain });
      });
      return next;
    });
  };

  const selectedCount = selected.size;
  const captainId = [...selected.values()].find((s) => s.is_captain)?.player_id;
  const vcId = [...selected.values()].find((s) => s.is_vice_captain)?.player_id;
  const selectedByTeam: Record<string, number> = {};
  const selectedPlayers = players.filter((player) => selected.has(player.id));
  const selectedRoleCounts = REQUIRED_ROLES.reduce<Record<string, number>>((acc, role) => {
    acc[role] = selectedPlayers.filter((player) => player.role === role).length;
    return acc;
  }, {});

  players.forEach((player) => {
    if (!selected.has(player.id)) return;
    selectedByTeam[player.team] = (selectedByTeam[player.team] || 0) + 1;
  });

  const teamsInMatch = [...new Set(players.map((player) => player.team))].sort();

  const canSelectPlayer = (player: Player) => {
    if (selected.has(player.id)) return true;
    if (selectedCount >= 11) return false;

    const simulatedCounts = { ...selectedRoleCounts };
    if (player.role in simulatedCounts) {
      simulatedCounts[player.role] += 1;
    }

    const remainingSlots = 11 - (selectedCount + 1);
    const missingRolesAfterSelection = REQUIRED_ROLES.filter((role) => simulatedCounts[role] === 0).length;
    return remainingSlots >= missingRolesAfterSelection;
  };

  const renderTeamBadge = (team: string, compact = false) => {
    const theme = getTeamTheme(team);
    return (
      <span
        className={`inline-flex items-center rounded-full border px-2 py-0.5 font-semibold ${compact ? 'text-[9px]' : 'text-[10px]'} ${theme.badgeClass}`}
      >
        {theme.label}
      </span>
    );
  };

  const validate = (): string | null => {
    if (selectedCount !== 11) return `Select exactly 11 players (currently ${selectedCount}).`;
    if (!captainId) return 'Select a Captain.';
    if (!vcId) return 'Select a Vice Captain.';
    if (captainId === vcId) return 'Captain and Vice Captain must be different players.';
    for (const role of REQUIRED_ROLES) {
      if (selectedRoleCounts[role] === 0) return `Select at least 1 ${ROLE_CONFIG[role]?.label || role}.`;
    }
    return null;
  };

  const availabilityRank = (player: Player) => {
    if (player.availability_status === 'available') return 3;
    if (player.availability_status === 'substitute') return 2;
    if (player.availability_status === 'unavailable') return 1;
    return 0;
  };

  const sortPlayersForDisplay = (list: Player[]) =>
    [...list].sort((a, b) => {
      const availabilityDiff = availabilityRank(b) - availabilityRank(a);
      if (availabilityDiff !== 0) return availabilityDiff;
      const pointsDiff = (b.total_points || 0) - (a.total_points || 0);
      if (pointsDiff !== 0) return pointsDiff;
      return a.name.localeCompare(b.name);
    });

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

  const rolePlayers = REQUIRED_ROLES.reduce<Record<string, Player[]>>((acc, role) => {
    acc[role] = sortPlayersForDisplay(players.filter((player) => player.role === role));
    return acc;
  }, {});

  const selectedUnavailableCounts = REQUIRED_ROLES.reduce<Record<string, number>>((acc, role) => {
    acc[role] = players.filter(
      (player) => player.role === role && player.availability_status === 'unavailable' && selected.has(player.id)
    ).length;
    return acc;
  }, {});
  const selectedSubstituteCounts = REQUIRED_ROLES.reduce<Record<string, number>>((acc, role) => {
    acc[role] = players.filter(
      (player) => player.role === role && player.availability_status === 'substitute' && selected.has(player.id)
    ).length;
    return acc;
  }, {});

  /* Ground view helpers */
  const getSelectedByRole = (role: string) => players.filter((p) => selected.has(p.id) && p.role === role);

  if (loading) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black pb-24">
      {/* Sticky header */}
      <header className="sticky top-0 z-30 bg-black/80 backdrop-blur-lg border-b border-white/10">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/dashboard" className="p-2 hover:bg-white/10 rounded-xl transition-all">
              <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </Link>
            <div>
              <h1 className="text-lg font-bold text-white">Select Your Team</h1>
              <p className="text-xs text-white/50">Match #{matchId}</p>
            </div>
          </div>
          <div
            className={`px-3 py-1.5 rounded-xl font-bold text-sm ${
              selectedCount === 11
                ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                : 'bg-white/10 text-white/70 border border-white/20'
            }`}
          >
            {selectedCount}/11
          </div>
        </div>
      </header>

      {/* Two-column layout: player list left, ground right */}
      <div className="max-w-7xl mx-auto px-4 py-4 flex flex-col lg:flex-row gap-4">
        {/* LEFT — Player selection */}
        <div className="flex-1 min-w-0 space-y-4">
          {/* Team counts */}
          <div className="flex flex-wrap gap-2">
            {teamsInMatch.map((team) => (
              <div
                key={team}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold border bg-gradient-to-r ${getTeamTheme(team).tintClass} border-white/10 text-white/80`}
              >
                <span className="mr-1.5">{getTeamTheme(team).label}</span>
                <span className="text-emerald-300">{selectedByTeam[team] || 0}</span>
              </div>
            ))}
          </div>

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
          <div className="flex items-center gap-4 text-xs text-white/50">
            <span className="flex items-center gap-1.5">
              <span className="w-5 h-5 bg-amber-500/30 border border-amber-500/50 rounded-full flex items-center justify-center text-[10px] font-bold text-amber-300">
                C
              </span>
              Captain (2x)
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-5 h-5 bg-sky-500/30 border border-sky-500/50 rounded-full flex items-center justify-center text-[10px] font-bold text-sky-300">
                VC
              </span>
              Vice Captain (1.5x)
            </span>
          </div>

          <div
            className={`rounded-2xl border px-4 py-3 text-sm ${
              playingXi.announced
                ? 'bg-emerald-500/10 border-emerald-400/20 text-emerald-100'
                : 'bg-amber-500/10 border-amber-400/20 text-amber-100'
            }`}
          >
            <div className="font-semibold">
              {playingXi.announced ? 'Playing XI announced' : 'Playing XI not announced'}
            </div>
            {playingXi.url && (
              <a
                href={playingXi.url}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-flex text-xs font-semibold text-cyan-300 hover:text-cyan-200"
              >
                Open lineup page
              </a>
            )}
          </div>

          {playingXi.announced && (
            <div className="flex flex-wrap items-center gap-4 text-xs text-white/50">
              <span className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
                Avl
              </span>
              <span className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-sky-400"></span>
                Sub
              </span>
              <span className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-red-400"></span>
                Unavl
              </span>
            </div>
          )}

          {/* Role Tabs */}
          <form onSubmit={handleSubmit}>
            <div className="flex items-center gap-1 rounded-xl border border-white/10 bg-white/5 p-1">
              {REQUIRED_ROLES.map((role) => {
                const hasUnavailableSelected = playingXi.announced && selectedUnavailableCounts[role] > 0;
                const hasSubstituteSelected = playingXi.announced && selectedSubstituteCounts[role] > 0;
                return (
                  <button
                    key={role}
                    type="button"
                    onClick={() => setActiveRole(role)}
                    className={`min-w-0 flex-1 rounded-lg px-2 py-2 text-xs sm:px-3 sm:text-sm font-medium transition-all ${
                      activeRole === role
                        ? hasUnavailableSelected
                          ? 'bg-red-500 text-white shadow-lg shadow-red-500/20'
                          : hasSubstituteSelected
                          ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/20'
                          : 'bg-white text-black shadow-lg'
                        : hasUnavailableSelected
                        ? 'bg-red-500/10 text-red-200 hover:bg-red-500/15'
                        : hasSubstituteSelected
                        ? 'bg-sky-500/10 text-sky-200 hover:bg-sky-500/15'
                        : 'text-white/50 hover:bg-white/5 hover:text-white'
                    }`}
                  >
                    <span className="truncate">{ROLE_CONFIG[role].label}</span>
                    <span
                      className={`ml-1 rounded-full px-1.5 py-0.5 text-[10px] ${
                        activeRole === role
                          ? hasUnavailableSelected || hasSubstituteSelected
                            ? 'bg-white/15 text-white'
                            : 'bg-black/10 text-black/70'
                          : hasUnavailableSelected
                          ? 'bg-red-500/20 text-red-100'
                          : hasSubstituteSelected
                          ? 'bg-sky-500/20 text-sky-100'
                          : 'bg-white/10 text-white/60'
                      }`}
                    >
                      {rolePlayers[role].filter((player) => selected.has(player.id)).length}
                    </span>
                  </button>
                );
              })}
            </div>

            {/* Player List — tap row to select/deselect */}
            <div className="mt-4 bg-white/5 border border-white/10 rounded-2xl overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
                <div className="flex items-center gap-2">
                  <span
                    className={`px-2 py-0.5 text-xs font-bold rounded-lg ${ROLE_CONFIG[activeRole].bg} ${ROLE_CONFIG[activeRole].color} ${ROLE_CONFIG[activeRole].border} border`}
                  >
                    {activeRole}
                  </span>
                  <span className="text-white/40 text-xs">
                    ({rolePlayers[activeRole].filter((player) => selected.has(player.id)).length} selected)
                  </span>
                </div>
                {playingXi.announced && selectedUnavailableCounts[activeRole] > 0 && (
                  <span className="rounded-full border border-red-500/25 bg-red-500/15 px-2 py-1 text-[10px] font-semibold text-red-200">
                    {selectedUnavailableCounts[activeRole]} unavailable selected
                  </span>
                )}
              </div>
              <div className="border-t border-white/5">
                {rolePlayers[activeRole].map((player) => {
                  const isSelected = selected.has(player.id);
                  const isCaptain = captainId === player.id;
                  const isVC = vcId === player.id;
                  const availabilityStatus = player.availability_status || 'unavailable';
                  const selectionAllowed = canSelectPlayer(player);

                  return (
                    <div
                      key={player.id}
                      onClick={() => {
                        if (isSelected || selectionAllowed) togglePlayer(player.id);
                      }}
                      className={`flex items-center gap-3 px-4 py-3 border-b border-white/5 last:border-b-0 transition-all cursor-pointer select-none ${
                        isSelected
                          ? availabilityStatus === 'available'
                            ? 'bg-emerald-500/10'
                            : 'bg-white/10'
                          : !selectionAllowed
                          ? 'opacity-45 cursor-not-allowed'
                          : availabilityStatus === 'available'
                          ? 'bg-emerald-500/[0.08] hover:bg-emerald-500/[0.12]'
                          : availabilityStatus === 'unavailable'
                          ? 'bg-white/[0.03] hover:bg-white/[0.06]'
                          : 'hover:bg-white/5'
                      } bg-gradient-to-r ${getTeamTheme(player.team).tintClass}`}
                    >
                      {/* Selected indicator */}
                      <div
                        className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center transition-all ${
                          isSelected ? 'bg-green-500 shadow-lg shadow-green-500/30' : 'bg-white/10 border border-white/20'
                        }`}
                      >
                        {isSelected ? (
                          <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                          </svg>
                        ) : (
                          <span className="text-white/30 text-[10px] font-bold">{player.name.charAt(0)}</span>
                        )}
                      </div>

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          {renderTeamBadge(player.team)}
                          <p className="min-w-0 truncate text-sm font-medium text-white">{player.name}</p>
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                          <span className="text-emerald-300 font-semibold">
                            {(player.total_points || 0).toFixed(2)} pts
                          </span>
                          {playingXi.announced && availabilityStatus === 'available' && (
                            <span className="inline-flex items-center gap-1 rounded-full border border-emerald-400/30 bg-emerald-500/15 px-2 py-0.5 font-semibold text-emerald-200">
                              <span className="h-2 w-2 rounded-full bg-emerald-400"></span>
                              Avl
                            </span>
                          )}
                          {playingXi.announced && availabilityStatus === 'substitute' && (
                            <span className="inline-flex items-center gap-1 rounded-full border border-sky-400/30 bg-sky-500/15 px-2 py-0.5 font-semibold text-sky-200">
                              <span className="h-2 w-2 rounded-full bg-sky-400"></span>
                              Sub
                            </span>
                          )}
                          {playingXi.announced && availabilityStatus === 'unavailable' && (
                            <span className="inline-flex items-center gap-1 rounded-full border border-red-400/25 bg-red-500/10 px-2 py-0.5 font-semibold text-red-200">
                              <span className="h-2 w-2 rounded-full bg-red-400"></span>
                              Unavl
                            </span>
                          )}
                        </div>
                      </div>

                      {/* C / VC buttons */}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (isSelected) setCaptain(player.id);
                        }}
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

                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (isSelected) setViceCaptain(player.id);
                        }}
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
            </div>
          </form>
        </div>

        {/* RIGHT — Live Ground View (sticky on desktop) */}
        <div className="lg:w-[340px] flex-shrink-0">
          <div className="lg:sticky lg:top-[73px]">
            <div
              className="rounded-2xl overflow-hidden shadow-xl"
              style={{
                background: 'linear-gradient(180deg, #1a5e1a 0%, #2d8a2d 30%, #3da33d 50%, #2d8a2d 70%, #1a5e1a 100%)',
              }}
            >
              <div className="text-center pt-3 pb-1">
                <p className="text-white/50 text-[10px] font-medium uppercase tracking-wider">Your XI</p>
                <p className={`text-sm font-bold ${selectedCount === 11 ? 'text-green-300' : 'text-white/70'}`}>
                  {selectedCount}/11 Selected
                </p>
              </div>

              <div className="relative px-3 py-3">
                {/* Oval border */}
                <div className="absolute inset-x-6 inset-y-2 border-2 border-white/15 rounded-[50%]" />

                {/* Wicketkeeper */}
                <div className="relative z-10 mb-3">
                  <p className="text-center text-white/40 text-[9px] uppercase tracking-widest mb-1.5">WK</p>
                  <div className="flex justify-center gap-2.5 flex-wrap min-h-[52px] items-start">
                    {getSelectedByRole('Wicketkeeper').map((p) => (
                      <GroundPlayer
                        key={p.id}
                        player={p}
                        isCaptain={captainId === p.id}
                        isVC={vcId === p.id}
                        teamBadge={renderTeamBadge(p.team, true)}
                        onTap={() => togglePlayer(p.id)}
                      />
                    ))}
                    {getSelectedByRole('Wicketkeeper').length === 0 && <EmptySlot label="WK" />}
                  </div>
                </div>

                {/* Batters */}
                <div className="relative z-10 mb-3">
                  <p className="text-center text-white/40 text-[9px] uppercase tracking-widest mb-1.5">BAT</p>
                  <div className="flex justify-center gap-2.5 flex-wrap min-h-[52px] items-start">
                    {getSelectedByRole('Batter').map((p) => (
                      <GroundPlayer
                        key={p.id}
                        player={p}
                        isCaptain={captainId === p.id}
                        isVC={vcId === p.id}
                        teamBadge={renderTeamBadge(p.team, true)}
                        onTap={() => togglePlayer(p.id)}
                      />
                    ))}
                    {getSelectedByRole('Batter').length === 0 && <EmptySlot label="BAT" />}
                  </div>
                </div>

                {/* All-Rounders */}
                <div className="relative z-10 mb-3">
                  <p className="text-center text-white/40 text-[9px] uppercase tracking-widest mb-1.5">AR</p>
                  <div className="flex justify-center gap-2.5 flex-wrap min-h-[52px] items-start">
                    {getSelectedByRole('AllRounder').map((p) => (
                      <GroundPlayer
                        key={p.id}
                        player={p}
                        isCaptain={captainId === p.id}
                        isVC={vcId === p.id}
                        teamBadge={renderTeamBadge(p.team, true)}
                        onTap={() => togglePlayer(p.id)}
                      />
                    ))}
                    {getSelectedByRole('AllRounder').length === 0 && <EmptySlot label="AR" />}
                  </div>
                </div>

                {/* Bowlers */}
                <div className="relative z-10">
                  <p className="text-center text-white/40 text-[9px] uppercase tracking-widest mb-1.5">BOWL</p>
                  <div className="flex justify-center gap-2.5 flex-wrap min-h-[52px] items-start">
                    {getSelectedByRole('Bowler').map((p) => (
                      <GroundPlayer
                        key={p.id}
                        player={p}
                        isCaptain={captainId === p.id}
                        isVC={vcId === p.id}
                        teamBadge={renderTeamBadge(p.team, true)}
                        onTap={() => togglePlayer(p.id)}
                      />
                    ))}
                    {getSelectedByRole('Bowler').length === 0 && <EmptySlot label="BOWL" />}
                  </div>
                </div>
              </div>

              {/* Ground footer legend */}
              <div className="flex justify-center gap-3 pb-3 text-[10px] text-white/50">
                <span className="flex items-center gap-1">
                  <span className="w-3 h-3 rounded-full bg-amber-400" /> C
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-3 h-3 rounded-full bg-sky-400" /> VC
                </span>
                <span className="text-white/30">Tap to remove</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Sticky submit bar */}
      <div className="fixed bottom-0 left-0 right-0 z-30 bg-black/90 backdrop-blur-lg border-t border-white/10">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
          <div className="text-sm min-w-0">
            <span className={`font-bold ${selectedCount === 11 ? 'text-green-400' : 'text-white/70'}`}>
              {selectedCount}/11
            </span>
            <span className="text-white/50 ml-2">
              {captainId ? 'C' : ''}
              {captainId && vcId ? ' / ' : ''}
              {vcId ? 'VC' : ''}
              {!captainId && !vcId && 'No C/VC'}
            </span>
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

      {/* Team Preview Modal — after save */}
      {showPreview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div className="w-full max-w-md relative">
            <div
              className="rounded-3xl overflow-hidden shadow-2xl"
              style={{
                background: 'linear-gradient(180deg, #1a5e1a 0%, #2d8a2d 30%, #3da33d 50%, #2d8a2d 70%, #1a5e1a 100%)',
              }}
            >
              <div className="text-center pt-4 pb-2">
                <p className="text-white/60 text-xs font-medium uppercase tracking-wider">Your Team</p>
                <p className="text-white text-lg font-bold">Fantasy Cricket</p>
              </div>

              <div className="relative px-4 pb-6">
                <div className="absolute inset-x-8 inset-y-4 border-2 border-white/15 rounded-[50%]" />

                {REQUIRED_ROLES.map((role) => (
                  <div key={role} className="relative z-10 mb-4 last:mb-0">
                    <p className="text-center text-white/40 text-[10px] uppercase tracking-widest mb-2">
                      {ROLE_CONFIG[role].label}
                    </p>
                    <div className="flex justify-center gap-3 flex-wrap">
                      {getSelectedByRole(role).map((p) => (
                        <div key={p.id} className="flex flex-col items-center">
                          <div
                            className={`w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold shadow-lg ${
                              captainId === p.id
                                ? 'bg-amber-400 text-black ring-2 ring-amber-300'
                                : vcId === p.id
                                ? 'bg-sky-400 text-black ring-2 ring-sky-300'
                                : 'bg-white text-green-900'
                            }`}
                          >
                            {captainId === p.id ? 'C' : vcId === p.id ? 'VC' : p.name.charAt(0)}
                          </div>
                          <p className="text-white text-[10px] font-medium mt-1 max-w-[60px] text-center truncate">
                            {p.name.split(' ').pop()}
                          </p>
                          <span className="mt-1">{renderTeamBadge(p.team, true)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex justify-center gap-4 pb-4 text-[10px] text-white/50">
                <span className="flex items-center gap-1">
                  <span className="w-3 h-3 rounded-full bg-amber-400"></span> Captain (2x)
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-3 h-3 rounded-full bg-sky-400"></span> Vice Captain (1.5x)
                </span>
              </div>
            </div>

            <button
              onClick={() => {
                setShowPreview(false);
                navigate('/dashboard');
              }}
              className="mt-4 w-full py-3 bg-white text-black hover:bg-white/90 font-semibold rounded-xl shadow-lg transition-all"
            >
              Go to Dashboard
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
