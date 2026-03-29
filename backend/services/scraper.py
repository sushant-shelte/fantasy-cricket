import requests


def fetch_scorecard_html(match_code):
    url = f"https://www.howstat.com/Cricket/Statistics/IPL/MatchScorecard.asp?MatchCode={match_code}"
    try:
        res = requests.get(url, timeout=15)
        if res.status_code != 200:
            return None
        return res.text
    except Exception as e:
        print("Error fetching scorecard:", e)
        return None
