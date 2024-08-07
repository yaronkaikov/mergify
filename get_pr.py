import uuid

from github import Github
import os
import re

# Replace with your GitHub personal access token
github_token = os.environ["GITHUB_TOKEN"]
REPO_OWNER = 'yaronkaikov'
REPO_NAME = 'mergify'
BACKPORT_PATTERN = re.compile(r'backport/(\d+\.\d+)')

# Initialize GitHub instance
g = Github(github_token)
repo = g.get_repo(f"{REPO_OWNER}/{REPO_NAME}")


def get_pr_commit(pr):
    """Get the commit that closed or merged the pull request."""
    if pr.merged:
        return pr.merge_commit_sha, 'merged'
    elif pr.closed_at:
        # Check events to find the commit that closed the PR
        events = pr.get_issue_events()
        for event in events:
            if event.event == 'closed':
                # Return the commit that closed the PR
                return event.commit_id, 'closed'
    return None, 'open', pr.labels


def cherry_pick_commit(repo, commit_sha, base_branch_name, new_branch_name):
    """Cherry-pick a commit and push it to a new branch."""
    commit = repo.get_commit(commit_sha)
    base_commit = repo.get_branch(base_branch_name).commit
    new_tree = commit.commit.tree

    new_commit = repo.create_git_commit(
        message=f"Cherry-picked commit {commit_sha}",
        tree=new_tree,
        parents=[base_commit.commit],
    )
    print(1)
    # Create a new branch with the new commit
    ref = repo.create_git_ref(ref=f"refs/heads/{new_branch_name}", sha=new_commit.sha)
    print(2)
    print(f"Successfully cherry-picked commit {commit_sha} to {new_branch_name}")
    return new_branch_name


def create_pull_request(repo, new_branch_name, base_branch_name, pr_title, pr_body):
    """Create a pull request on GitHub."""
    pr = repo.create_pull(
        title=pr_title,
        body=pr_body,
        head=new_branch_name,
        base=base_branch_name
    )
    print(f"Pull request created: {pr.html_url}")
    return pr


def main():
    prs = repo.get_pulls(state='closed')
    for pr in prs:
        pr_number = pr.number
        pr_title = pr.title
        labels = [label.name for label in pr.labels]
        for label in labels:
            match = BACKPORT_PATTERN.match(label)
            if match:
                version = match.group(1)
                new_branch_name = f"branch-{version}"
                temp_branch_name = f"temp-backport-{uuid.uuid4().hex[:8]}"  # Generate a unique temp branch name
                base_branch_name = repo.default_branch
                commit, status = get_pr_commit(pr)
                if commit and status:
                    print(f'PR #{pr_number} - "{pr_title}": {status} (Commit: {commit}), Branch: {new_branch_name}')
                    try:
                        cherry_pick_commit(repo, commit, base_branch_name, temp_branch_name)
                        # Create a pull request
                        pr_title = f"Backport {pr_title} to {version}"
                        pr_body = f"Cherry-pick of commit {commit} from PR #{pr_number}."
                        create_pull_request(repo, temp_branch_name, new_branch_name, pr_title, pr_body)

                    except Exception as e:
                        print(f"Failed to cherry-pick and create PR: {e}")


if __name__ == "__main__":
    main()
