import configparser
import github
import io
import logging
import os
import re
import requests
import sys
import time


REAL = True
GITHUB_API = "https://api.github.com"

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("main")
logger.setLevel(logging.DEBUG)

workflow_content = """---
name: Check that 'main' is not merged into the development branch

on: pull_request

jobs:
  call-workflow:
    uses: lsst/rubin_workflows/.github/workflows/rebase_checker.yaml@main
"""

def rewrite_setup_cfg(contents: str) -> str:
    config = configparser.ConfigParser()
    config.read_string(contents)

    modified = False

    if "tool:pytest" in config:
        pytest = config["tool:pytest"]

        if "flake8-ignore" in pytest:
            modified = True
            del pytest["flake8-ignore"]
        if "addopts" in pytest:
            addopts = pytest["addopts"]
            newopts = addopts.replace("--flake8", "").strip()
            # Remove multiple spaces.
            newopts = re.sub(r"\s+", " ", newopts).strip()
            if newopts == "":
                modified = True
                del pytest["addopts"]
            elif addopts != newopts:
                modified = True
                pytest["addopts"] = newopts

    if not modified:
        # If the config was not modified avoid reformatting it.
        return contents

    buffer = io.StringIO()
    config.write(buffer)

    # Serialization can add trailing whitespace.
    content = buffer.getvalue()
    content = re.sub(r" +$", "", content, flags=re.MULTILINE)

    # Ensure a single trailing newline.
    return content.strip() + "\n"


def process_repo(repo, session):
    logger.info(f"Checking {repo.full_name}")
    if repo.fork:
        logger.info("* is a fork")
        return
    if repo.archived:
        logger.info("* is archived")
        return
    if repo.full_name.startswith("lsst/dm-sow-"):
        logger.info("* is dm-sow")
        return
    if repo.full_name.startswith("lsst-dm/legacy"):
        logger.info("* is legacy")
        return
    if repo.default_branch != "main":
        logger.info("* default branch is {repo.default_branch}")

    path = ".github/workflows/rebase_checker.yaml"
    do_rebase_checker = True
    try:
        _ = repo.get_contents(path)
        logger.info("* Already has a rebase_checker workflow")
        do_rebase_checker = False
    except github.GithubException:
        pass

    do_setup_cfg = False
    try:
        cfile = repo.get_contents("setup.cfg")
        text = str(cfile.decoded_content, encoding="utf-8")
        new_text = rewrite_setup_cfg(text)
        do_setup_cfg = new_text != text
        if not do_setup_cfg:
            logger.info("* setup.cfg is already modern")
    except github.GithubException:
        logger.info("* Does not have setup.cfg")
        pass

    if not do_rebase_checker and not do_setup_cfg:
        logger.info("* Nothing to do")
        return

    try:
        branch = repo.get_branch(repo.default_branch)
    except github.GithubException:
        logger.info("* Does not have a default branch")
        return

    if branch.protected:
        enforce = branch.get_admin_enforcement()
        if enforce:
            logger.debug("* removing admin enforcement")
            if REAL:
                branch.remove_admin_enforcement()

    # Add workflow
    if do_rebase_checker:
        logger.info("* Adding workflow")
        if REAL:
            repo.create_file(path, "Add rebase check workflow.", workflow_content)

    # Update setup.cfg
    if do_setup_cfg:
        logger.info(f"* Update setup.cfg")
        if REAL:
            repo.update_file(
                cfile.path,
                "Update flake8/pytest sections in setup.cfg.",
                new_text,
                cfile.sha,
            )

    if branch.protected:
        try:
            rsc = branch.get_required_status_checks()
            strict = rsc.strict
            orig_contexts = rsc.contexts
        except github.GithubException:
            strict = True
            orig_contexts = []
        new_contexts = orig_contexts
        rebase_context = "call-workflow / rebase-checker"
        if rebase_context not in new_contexts:
            logger.info("* Adding required status check")
            new_contexts.append(rebase_context)
        travis_context = "continuous-integration/travis-ci"
        if travis_context in new_contexts:
            logger.info("* Removing Travis status check")
            new_contexts.remove(travis_context)
        if new_contexts != orig_contexts:
            logger.debug(f"** was: {strict} {orig_contexts}")
            logger.debug(f"** now: {strict} {new_contexts}")
            if REAL:
                branch.edit_required_status_checks(strict=strict, contexts=new_contexts)

        logger.debug("* setting admin enforcement")
        if REAL:
            branch.set_admin_enforcement()


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
            if repo.full_name.startswith("lsst/") and repo.full_name.lower() < "lsst/qserv_deploy":
                continue
            process_repo(repo, session)
            rate = g.get_rate_limit().core
            time.sleep(1 if rate.remaining > 300 else 2)
