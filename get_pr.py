import uuid

from github import Github, InputGitAuthor, GithubException
import os
import re

# Replace with your GitHub personal access token
github_token = os.environ["GITHUB_TOKEN"]
REPO_OWNER = 'yaronkaikov'
REPO_NAME = 'mergify'

# Initialize GitHub instance
g = Github(github_token)
repo = g.get_repo(f"{REPO_OWNER}/{REPO_NAME}")


def get_pr_commits(pr):
    """Get the commit that closed or merged the pull request."""
    if pr.merged:
        return pr.merge_commit_sha
    elif pr.closed_at:
        # Check events to find the commit that closed the PR
        events = pr.get_issue_events()
        for event in events:
            if event.event == 'closed':
                # Return the commit that closed the PR
                return event.commit_id
    return None


def check_for_conflicts(repo, base_branch_name, compare_branch_name):
    """Check if there are conflicts between base and compare branches."""
    try:
        comparison = repo.compare(base_branch_name, compare_branch_name)
        print(comparison.status)
        return comparison.status == 'diverged'
    except GithubException as e:
        print(f"Failed to compare branches: {e}")
        return False


def cherry_pick_commits(repo, commits, base_branch_name, temp_branch_name):
    """Cherry-pick commits and push them to a temporary branch."""
    base_commit = repo.get_branch(base_branch_name).commit
    parent_commit = base_commit.commit
    author = InputGitAuthor(
        name="github-actions[bot]",
        email="41898282+github-actions[bot]@users.noreply.github.com"
    )

    # Store commit messages for the new PR body
    commit_messages = []

    # Iterate through each commit and cherry-pick
    for commit in commits:
        # Recreate the commit tree
        new_tree = commit.commit.tree
        new_commit = repo.create_git_commit(
            message=f'{commit.commit.message}',
            author=author,
            tree=new_tree,
            parents=[parent_commit],
        )
        parent_commit = new_commit  # Update parent for the next commit

        # Add commit message to the list
        commit_messages.append(f"- (cherry picked from commit {commit.sha})")

    # Create a new temporary branch with the final cherry-picked commit
    try:
        ref = repo.create_git_ref(ref=f"refs/heads/{temp_branch_name}", sha=new_commit.sha)
        print(f"Successfully created temp branch {temp_branch_name} with commits.")
    except Exception as e:
        print(f"Failed to create temp branch {temp_branch_name}: {e}")
        raise
    return new_commit.sha, commit_messages


# def get_pr_commits(pr):
#     """Get all commits in the pull request."""
#     return pr.get_commits()


def create_pull_request(repo, new_branch_name, base_branch_name, pr_title, pr_body, pr_number, commit_messages, author):
    """Create a pull request on GitHub."""
    # Format the new PR body with original body and list of commits
    new_pr_body = f"{pr_body}\n\n"
    new_pr_body += "\n".join(commit_messages)
    new_pr_body += f'\n\nParent PR: #{pr_number}'

    if not check_for_conflicts(repo, base_branch_name, new_branch_name):
        is_draft = False
    else:
        print(f"Conflicts detected between {base_branch_name} and {new_branch_name}. Creating as draft.")
        is_draft = True

    pr = repo.create_pull(
        title=pr_title,
        body=new_pr_body,
        head=new_branch_name,
        base=base_branch_name,
        draft=is_draft
    )
    try:
        pr.add_to_assignees(author)
        print(f"Assigned PR to original author: {author}")
    except Exception as e:
        print(f"Failed to assign PR to {author}: {e}")
    print(f"Pull request created: {pr.html_url}")
    return pr


def main():
    prs = repo.get_pulls(state='closed')
    for pr in prs:
        pr_number = pr.number
        pr_title = pr.title
        pr_body = pr.body
        original_author = pr.user.login
        labels = [label.name for label in pr.labels]
        backport_pattern = r'backport/(\d+\.\d+)'
        matches = 'promoted-to-master' in labels and any(re.match(backport_pattern, label) for label in labels)
        backport_label_list = [label for label in labels if re.match(backport_pattern, label)]
        if matches and backport_label_list:
            for label in backport_label_list:
                version = label.replace('backport/', '')
                backport_base_branch = f'branch-{version}'
                temp_branch_name = f'backport/{pr.number}/to-{version}'
                base_branch_name = repo.default_branch
                commit = get_pr_commits(pr)
                print(f'PR #{pr_number} - "{pr_title}": Base Branch: {base_branch_name} will backport to: {backport_base_branch} using Temp Branch: {temp_branch_name}')
                try:
                    # Cherry-pick the commits into the temporary branch
                    new_commit_sha, commit_messages = cherry_pick_commits(repo, commit, backport_base_branch, temp_branch_name)
                    # Create a pull request with the original PR body and list of commits
                    pr_title = f"[Backport {version}] {pr_title}"
                    create_pull_request(repo, temp_branch_name, backport_base_branch, pr_title, pr_body, pr_number, commit_messages, original_author)

                except Exception as e:
                    print(f"Failed to cherry-pick and create PR: {e}")


if __name__ == "__main__":
    main()
