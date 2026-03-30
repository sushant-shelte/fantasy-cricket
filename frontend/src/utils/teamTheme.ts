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
    badgeClass: "border-amber-300/30 bg-gradient-to-r from-amber-300/20 to-blue-400/12 text-amber-100",
    tintClass: "from-amber-300/12 to-blue-400/6",
  },
  MI: {
    label: "MI",
    badgeClass: "border-blue-300/30 bg-gradient-to-r from-blue-400/18 to-yellow-300/10 text-blue-100",
    tintClass: "from-blue-400/12 to-yellow-300/6",
  },
  RCB: {
    label: "RCB",
    badgeClass: "border-red-400/30 bg-gradient-to-r from-red-500/18 to-zinc-500/12 text-red-100",
    tintClass: "from-red-500/12 to-zinc-500/8",
  },
  KKR: {
    label: "KKR",
    badgeClass: "border-fuchsia-400/30 bg-gradient-to-r from-fuchsia-500/18 to-amber-300/12 text-fuchsia-100",
    tintClass: "from-fuchsia-500/12 to-amber-300/8",
  },
  RR: {
    label: "RR",
    badgeClass: "border-pink-400/30 bg-gradient-to-r from-pink-500/20 to-blue-400/12 text-pink-100",
    tintClass: "from-pink-500/12 to-blue-400/8",
  },
  GT: {
    label: "GT",
    badgeClass: "border-sky-300/30 bg-gradient-to-r from-sky-500/14 to-teal-300/12 text-sky-100",
    tintClass: "from-sky-500/10 to-teal-300/8",
  },
  DC: {
    label: "DC",
    badgeClass: "border-blue-400/30 bg-gradient-to-r from-blue-500/18 to-red-500/12 text-blue-100",
    tintClass: "from-blue-500/12 to-red-500/8",
  },
  LSG: {
    label: "LSG",
    badgeClass: "border-cyan-300/30 bg-gradient-to-r from-cyan-400/18 to-orange-400/12 text-cyan-100",
    tintClass: "from-cyan-400/12 to-orange-400/8",
  },
  PBKS: {
    label: "PBKS",
    badgeClass: "border-rose-400/30 bg-gradient-to-r from-rose-500/18 to-slate-300/12 text-rose-100",
    tintClass: "from-rose-500/12 to-slate-300/8",
  },
  SRH: {
    label: "SRH",
    badgeClass: "border-orange-400/30 bg-gradient-to-r from-orange-500/18 to-zinc-500/12 text-orange-100",
    tintClass: "from-orange-500/12 to-zinc-500/8",
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
