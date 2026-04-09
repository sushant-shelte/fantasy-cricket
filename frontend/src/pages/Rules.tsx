export default function RulesPage() {
  const sections = [
    {
      title: 'Team Selection',
      icon: '🏏',
      rules: [
        'Select exactly 11 players per match',
        'At least 1 player from each role (WK, BAT, AR, BWL)',
        'Choose 1 Captain (2x points) and 1 Vice Captain (1.5x points)',
        'Team locks at match start time — no changes after',
      ],
    },
    {
      title: 'Batting Points',
      icon: '🏏',
      rules: [
        'Playing in match: +4 pts',
        'Runs scored: +1 per run',
        'Fours: +4 per boundary',
        'Sixes: +6 per six',
        '30 runs: +4 bonus',
        '50 runs: +8 bonus',
        '75 runs: +12 bonus',
        '100 runs: +16 bonus',
        'Duck (out for 0): -2 pts (WK/BAT/AR only)',
      ],
    },
    {
      title: 'Strike Rate (min 10 balls, WK/BAT/AR only)',
      icon: '⚡',
      rules: [
        'SR > 170: +6 pts',
        'SR > 150: +4 pts',
        'SR ≥ 130: +2 pts',
        'SR ≤ 70: -2 pts',
        'SR < 60: -4 pts',
        'SR ≤ 50: -6 pts',
      ],
    },
    {
      title: 'Bowling Points',
      icon: '🎯',
      rules: [
        'Wickets: +30 per wicket',
        'Bowled/LBW dismissal: +8 pts',
        '3 wickets: +4 bonus',
        '4 wickets: +8 bonus',
        '5 wickets: +16 bonus',
        'Maiden over: +12 pts',
        'Dot balls: +1 per dot ball',
      ],
    },
    {
      title: 'Economy Rate (min 2 overs)',
      icon: '📊',
      rules: [
        'Economy < 5: +6 pts',
        'Economy < 6: +4 pts',
        'Economy ≤ 7: +2 pts',
        'Economy ≥ 10: -2 pts',
        'Economy > 11: -4 pts',
        'Economy > 12: -6 pts',
      ],
    },
    {
      title: 'Fielding Points',
      icon: '🧤',
      rules: [
        'Catch: +8 per catch',
        '3+ catches: +4 bonus',
        'Stumping: +12 pts',
        'Direct run out: +12 pts',
        'Indirect run out: +6 pts (shared)',
      ],
    },
    {
      title: 'Captain & Vice Captain',
      icon: '👑',
      rules: [
        'Captain (C): All points × 2',
        'Vice Captain (VC): All points × 1.5',
        'Other players: Points × 1',
      ],
    },
    {
      title: 'Prize Pool',
      icon: '💰',
      rules: [
        'Entry fee: ₹50 per match per participant',
        'Prize pool = Total participants × ₹50',
        '1st place: 50% of prize pool',
        '2nd place: 30% of prize pool',
        '3rd place: 20% of prize pool',
        'Others: -₹50 (entry fee lost)',
      ],
    },
  ];

  return (
    <div>
      <h2 className="text-xl font-bold text-white mb-6">Scoring Rules</h2>

      <div className="space-y-4">
        {sections.map((section, i) => (
          <div key={i} className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden backdrop-blur-sm">
            <div className="px-4 py-3 border-b border-white/5 flex items-center gap-2">
              <span className="text-lg">{section.icon}</span>
              <h3 className="text-white font-semibold text-sm">{section.title}</h3>
            </div>
            <div className="px-4 py-3">
              <ul className="space-y-1.5">
                {section.rules.map((rule, j) => {
                  const isPositive = rule.includes('+');
                  const isNegative = rule.includes('-') && rule.includes('pts');
                  return (
                    <li key={j} className="flex items-start gap-2 text-sm">
                      <span className={`mt-0.5 text-xs ${isPositive ? 'text-blue-400' : isNegative ? 'text-red-400' : 'text-white/40'}`}>
                        {isPositive ? '▲' : isNegative ? '▼' : '•'}
                      </span>
                      <span className={`${isPositive ? 'text-white/80' : isNegative ? 'text-white/60' : 'text-white/70'}`}>
                        {rule}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
