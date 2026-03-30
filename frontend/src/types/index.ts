export type User = {
  id: number;
  firebase_uid: string;
  email: string;
  name: string;
  mobile?: string;
  role: 'user' | 'admin';
  is_active: boolean;
};

export type Match = {
  id: number;
  team1: string;
  team2: string;
  match_date: string;
  match_time: string;
  status: 'future' | 'live' | 'over';
  locked: boolean;
};

export type Player = {
  id: number;
  name: string;
  team: string;
  role: string;
  aliases: string;
  total_points?: number;
  is_playing_xi?: boolean | null;
};

export type TeamSelection = {
  player_id: number;
  player_name: string;
  team: string;
  role: string;
  is_captain: boolean;
  is_vice_captain: boolean;
};

export type PlayerScore = {
  name: string;
  team: string;
  role: string;
  played: boolean;
  is_out: boolean;
  runs: number;
  balls: number;
  fours: number;
  sixes: number;
  strike_rate: number;
  overs: number;
  maidens: number;
  runs_conceded: number;
  wickets: number;
  dot_balls: number;
  bowled: number;
  lbw: number;
  economy: number;
  catches: number;
  runout_direct: number;
  runout_indirect: number;
  stumpings: number;
  points: number;
};

export type ContestantScore = {
  id: number;
  name: string;
  points: number;
};

export type LeaderboardEntry = {
  rank: number;
  name: string;
  user_id: number;
  points: number;
  balance: number;
};

export type PointsTableEntry = {
  user_id: number;
  name: string;
  match_id: number;
  points: number;
  last_updated: string;
};

export type AdminMatchWithTeamCount = {
  id: number;
  team1: string;
  team2: string;
  match_date: string;
  match_time: string;
  team_count: number;
};

export type AdminTeamPlayer = {
  player_id: number;
  player_name: string;
  team: string;
  role: string;
  is_captain: boolean;
  is_vice_captain: boolean;
};

export type AdminUserTeam = {
  user_id: number;
  user_name: string;
  user_email?: string;
  user_mobile?: string;
  players: AdminTeamPlayer[];
  team_counts: Record<string, number>;
  captain_name?: string | null;
  vice_captain_name?: string | null;
};
