type TeamTheme = {
  label: string;
  badgeClass: string;
  tintClass: string;
};

const TEAM_ALIASES: Record<string, string> = {
  "CHENNAI SUPER KINGS": "CSK",
  "MUMBAI INDIANS": "MI",
  "ROYAL CHALLENGERS BENGALURU": "RCB",
  "KOLKATA KNIGHT RIDERS": "KKR",
  "RAJASTHAN ROYALS": "RR",
  "GUJARAT TITANS": "GT",
  "DELHI CAPITALS": "DC",
  "LUCKNOW SUPER GIANTS": "LSG",
  "PUNJAB KINGS": "PBKS",
  "SUNRISERS HYDERABAD": "SRH",
};

const TEAM_THEMES: Record<string, TeamTheme> = {
  CSK: {
    label: "CSK",
    badgeClass: "border-amber-300/35 bg-gradient-to-r from-yellow-300/30 to-blue-500/18 text-amber-50",
    tintClass: "from-yellow-300/18 via-amber-400/12 to-blue-500/12",
  },
  MI: {
    label: "MI",
    badgeClass: "border-blue-300/35 bg-gradient-to-r from-blue-500/28 to-yellow-300/18 text-blue-50",
    tintClass: "from-blue-500/18 via-sky-400/12 to-yellow-300/12",
  },
  RCB: {
    label: "RCB",
    badgeClass: "border-red-400/35 bg-gradient-to-r from-red-600/30 to-zinc-500/18 text-red-50",
    tintClass: "from-red-600/18 via-red-500/12 to-zinc-500/12",
  },
  KKR: {
    label: "KKR",
    badgeClass: "border-fuchsia-400/35 bg-gradient-to-r from-purple-600/28 to-amber-300/18 text-fuchsia-50",
    tintClass: "from-purple-600/18 via-fuchsia-500/12 to-amber-300/12",
  },
  RR: {
    label: "RR",
    badgeClass: "border-pink-400/35 bg-gradient-to-r from-pink-500/30 to-blue-500/18 text-pink-50",
    tintClass: "from-pink-500/18 via-rose-400/12 to-blue-500/12",
  },
  GT: {
    label: "GT",
    badgeClass: "border-sky-300/35 bg-gradient-to-r from-sky-600/24 to-teal-300/18 text-sky-50",
    tintClass: "from-sky-600/16 via-sky-400/10 to-teal-300/12",
  },
  DC: {
    label: "DC",
    badgeClass: "border-blue-400/35 bg-gradient-to-r from-blue-600/28 to-red-500/18 text-blue-50",
    tintClass: "from-blue-600/18 via-blue-500/12 to-red-500/12",
  },
  LSG: {
    label: "LSG",
    badgeClass: "border-cyan-300/35 bg-gradient-to-r from-cyan-400/28 to-orange-400/18 text-cyan-50",
    tintClass: "from-cyan-400/18 via-sky-300/10 to-orange-400/12",
  },
  PBKS: {
    label: "PBKS",
    badgeClass: "border-rose-400/35 bg-gradient-to-r from-rose-600/28 to-slate-300/18 text-rose-50",
    tintClass: "from-rose-600/18 via-rose-500/12 to-slate-300/12",
  },
  SRH: {
    label: "SRH",
    badgeClass: "border-orange-400/35 bg-gradient-to-r from-orange-500/28 to-zinc-500/18 text-orange-50",
    tintClass: "from-orange-500/18 via-amber-400/10 to-zinc-500/12",
  },
};

export function getTeamTheme(team: string): TeamTheme {
  const normalized = (team || "").trim().toUpperCase();
  const key = TEAM_ALIASES[normalized] || normalized;
  return TEAM_THEMES[key] || {
    label: team,
    badgeClass: "border-white/15 bg-white/5 text-white/70",
    tintClass: "from-white/8 to-white/[0.02]",
  };
}
