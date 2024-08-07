#!/usr/bin/env python

from __future__ import print_function
import re
import subprocess

branches = dict()
for l in subprocess.check_output(["git", "log", "--oneline"]).split('\n'):
    m = re.search(r"^([0-9a-f]+) Merge (pull request #\d+ from |branch ')(.+?)('.*?)?( into .*)?$", l)
    if not m:
        continue
    sha = m.group(1)
    branch = m.group(3)

    # Some branch specs from GitHub are preceded by the org.
    branch = re.sub(r"^lsst.*?/", "", branch)

    # Do not consider merges _from_ master, draft, or next.
    if branch in ["master", "draft", "next", "integration"]:
        continue

    # Allow merges into what used to be the new-development branch.
    # These later got merged en masse into master.
#    if m.group(5) and m.group(5) != ' into next' and m.group(5) != ' into draft':
#        continue
    # Only take the latest merge in case a branch was merged twice.
    if branch not in branches:
        branches[branch] = sha

final_branch_list = []
with open("/dev/null", "w") as dev_null:
    for branch in sorted(branches):
        # Check that one of the merge commit's parents is the branch.

        try:
            sha_branch = subprocess.check_output(["git", "rev-parse",
                "--short", "origin/" + branch], stderr=dev_null).rstrip()
        except subprocess.CalledProcessError:
            # The branch has already been deleted or can't be found
            continue
        # Get the parents of the merge commit.
        out = subprocess.check_output(["git", "log", "-1", "--format=%p",
            branches[branch]]).rstrip().split(' ')
        if len(out) != 2:
            print("# Fast-forward merge for branch {}".format(branch))
            continue
        sha_merge_parent = out[1]
        if not sha_branch == sha_merge_parent:
            print("# Branch {} sha {} vs. parent {} in merge {}".format(
                    branch, sha_branch, sha_merge_parent, branches[branch]))
            continue

        # All of our checks have passed.
        final_branch_list.append(branch)

# Print the branch delete command.
if len(final_branch_list) > 0:
    print("git push --delete origin {}".format(" ".join(final_branch_list)))
