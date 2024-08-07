import github
import os

GITHUB_API = "https://api.github.com"

with open(os.environ["GITHUB_TOKEN"]) as f:
    token = f.readline().rstrip()

g = github.Github(token)
for org in ["lsst-dm"]:
    o = g.get_organization(org)
    repo_list = o.get_repos(type="all", sort="full_name")
    for repo in repo_list:
        tags = [tag.name for tag in repo.get_tags() if not tag.name.startswith("w.")]
        if "24.0.0" not in tags:
            if "v24.0.0" in tags:
                print(f"{repo}: {tags}")
            else:
                print(f"{repo}: OK")
