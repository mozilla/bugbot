import subprocess


def _batch_cinnabar(op, repo_dir, hashes):
    p = subprocess.Popen(
        ["git", "cinnabar", op, "--batch"],
        cwd=repo_dir,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )

    for h in hashes:
        p.stdin.write(f"{h}\n".encode("ascii"))
        p.stdin.flush()
        result_h = p.stdout.readline().strip().decode("ascii")
        if result_h == "0000000000000000000000000000000000000000":
            raise Exception(f"Missing mapping for {h}")
        yield result_h

    p.terminate()
    p.wait()


def mercurial_to_git(repo_dir, mercurial_hashes):
    yield from _batch_cinnabar("hg2git", repo_dir, mercurial_hashes)


def git_to_mercurial(repo_dir, git_hashes):
    yield from _batch_cinnabar("git2hg", repo_dir, git_hashes)


if __name__ == "__main__":
    import argparse
    import collections

    import hglib

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "repository_dir", help="Path to the Mercurial repository", action="store"
    )
    parser.add_argument(
        "git_repository_dir", help="Path to the git-cinnabar repository", action="store"
    )
    args = parser.parse_args()

    hg = hglib.open(args.repository_dir)
    cmd_args = hglib.util.cmdbuilder(b"log", template="{node}\n")
    x = hg.rawcommand(cmd_args)
    revs = x.splitlines()

    it = git_to_mercurial(
        args.git_repository_dir,
        mercurial_to_git(
            args.git_repository_dir, (rev.decode("ascii") for rev in revs)
        ),
    )
    collections.deque(it, maxlen=0)
