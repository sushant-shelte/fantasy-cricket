#!/bin/bash
set -e

echo "=== Installing backend dependencies ==="
pip install -r backend/requirements.txt

echo "=== Installing Node.js ==="
if ! command -v node &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
fi

echo "=== Installing frontend dependencies ==="
cd frontend
npm install

echo "=== Building frontend ==="
npm run build
cd ..

echo "=== Initializing database + seeding ==="
python -c "
import os, sys
sys.path.insert(0, '.')
from backend.database import init_db, get_db

init_db()
db = get_db()

# Check if data already exists
row = db.execute('SELECT COUNT(*) as cnt FROM players').fetchone()
count = row['cnt'] if isinstance(row, dict) else row[0]

if count > 0:
    print(f'Database already has {count} players, skipping seed')
else:
    import openpyxl
    wb = openpyxl.load_workbook('FantasyCricket.xlsx')

    ws = wb['Players']
    pc = 0
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[0] is None: break
        db.execute(
            'INSERT INTO players (id, name, team, role, aliases) VALUES (?, ?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET name=?, team=?, role=?, aliases=?',
            (int(r[0]), r[1], r[2], r[3], r[4] or '', r[1], r[2], r[3], r[4] or '')
        )
        pc += 1

    ws = wb['Matches']
    mc = 0
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[0] is None: break
        date_str = r[1].strftime('%Y-%m-%d')
        time_str = r[2].strftime('%H:%M')
        db.execute(
            'INSERT INTO matches (id, team1, team2, match_date, match_time, status) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET team1=?, team2=?, match_date=?, match_time=?',
            (int(r[0]), r[3], r[4], date_str, time_str, 'future', r[3], r[4], date_str, time_str)
        )
        mc += 1

    db.commit()
    print(f'Seeded: {pc} players, {mc} matches')
"

echo "=== Build complete ==="
