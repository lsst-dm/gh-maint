import github
import logging
import os
import re
import requests
import sys
import time

REAL = False
GITHUB_API = "https://api.github.com"

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("main")
logger.setLevel(logging.DEBUG)

def process_file(repo, cfile):
    text = str(cfile.decoded_content, encoding="utf-8")
    if "master" in text:
        # Don't change actions with "@master"
        # Do change branch names and URLs
        new_text = re.sub(r"(?<!@)master", "main", text)
        if text != new_text:
            logger.info(f"* {cfile.path} updated")
            logger.debug(new_text)
            if REAL:
                try:
                    repo.update_file(
                        path=cfile.path,
                        message="Change default branch to main in GHAs.",
                        content=new_text,
                        sha=cfile.sha,
                        branch=repo.default_branch,
                    )
                except Exception as e:
                    logger.warning("*** Update failed")
                    logger.debug(e)

def process_repo(repo, session):
    logger.info(f"Checking {repo.full_name}")
    if repo.fork:
        logger.info("* is a fork")
        return
    try:
        repo.get_branch("master")
    except (github.GithubException, github.UnknownObjectException):
        logger.info("* has no master branch")
        try:
            repo.get_branch("main")
            logger.info("* has main branch already")
            if repo.default_branch == "main":
                logger.info("* which is default")
        except:
            logger.info("* and no main branch either")
            return
        return
    if repo.default_branch != "master":
        logger.warning(f"* default branch = {repo.default_branch}")

    # Fix workflows
    file_list = []
    try:
        file_list = repo.get_contents(".github/workflows")
    except github.UnknownObjectException:
        pass
    branch = repo.get_branch(repo.default_branch)
    if branch.protected:
        enforce = branch.get_admin_enforcement()
        if enforce:
            logger.debug("* removing admin enforcement")
            branch.remove_admin_enforcement()
    for cfile in file_list:
        logger.info(f"* checking {cfile.path}")
        if cfile.type == "dir":
            subfile_list = repo.get_contents(cfile.path)
            for subcfile in subfile_list:
                process_file(repo, subcfile)
        else:
            process_file(repo, cfile)
    if branch.protected and enforce:
        logger.debug("* restoring admin enforcement")
        branch.set_admin_enforcement()

    # Do the rename
    logger.info("rename_branch(master, main)")
    if REAL:
        r = session.post(
            f"{GITHUB_API}/repos/{repo.full_name}/branches/master/rename",
            json=dict(new_name="main")
        )
        try:
            r.raise_for_status()
        except Exception as e:
            logger.warning(e)



with open(os.environ["GITHUB_TOKEN"]) as f:
    token = f.readline().rstrip()

g = github.Github(token)

if len(sys.argv) > 1:
    org_list = sys.argv[1:]
else:
    org_list = ["ktlim"]
logger.info(f"Orgs: {org_list}")

with requests.Session() as session:
    session.headers.update(
        {
            "Authorization":  f"token {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github.v3+json",
        }
    )

    for org in org_list:
        try:
            o = g.get_organization(org)
            logger.info(f"Working on organization {org}")
            repo_list = o.get_repos(type="all", sort="full_name")
        except:
            o = g.get_user(org)
            logger.info(f"Working on user {org}")
            repo_list = o.get_repos(type="owner", sort="full_name")
        for repo in repo_list:
            process_repo(repo, session)
            rate = g.get_rate_limit().core
            time.sleep(1 if rate.remaining > 300 else 2)
