import github
import os

GITHUB_API = "https://api.github.com"

with open(os.environ["GITHUB_TOKEN"]) as f:
    token = f.readline().rstrip()

g = github.Github(token)

o = g.get_organization("rubin-dp0")
t = o.get_team_by_slug("Delegates")
for m in t.get_members():
    print(m.login)
