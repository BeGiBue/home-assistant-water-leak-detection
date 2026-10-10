"""Execute the release script against an atomic, concurrently shared API model."""

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

SHA = "a" * 40
OTHER = "b" * 40
SCRIPT = Path(".github/release_checked_commit.sh").resolve()


@pytest.fixture
def release_model(tmp_path):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"tag": None, "release": False, "commands": []}))
    executable = tmp_path / "bin"
    executable.mkdir()
    driver = tmp_path / "driver.py"
    driver.write_text("""import fcntl,json,os,sys
from pathlib import Path
state=Path(os.environ['MODEL_STATE'])
with open(str(state)+'.lock','w') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 data=json.loads(state.read_text())
 command=sys.argv[1:]
 data['commands'].append(command)
 code=0;output='';error=''
 if command[0]=='git':
  action=command[1]
  if data.get('remote_error')==action: code=128;error='remote failure'
  elif action=='ls-remote': code=0 if data['tag'] else 2
  elif action=='fetch':
   data['fetches']=data.get('fetches',0)+1
   if data.get('move_before_release') and data['fetches']==2: data['tag']='b'*40
  elif action=='rev-parse':
   assert command[2]=='FETCH_HEAD^{commit}'
   # Both annotated and lightweight refs resolve to the pointed-to commit.
   output=data['tag'] or ''
 elif command[0]=='gh':
  if command[1]=='api':
   if data.get('remote_error')=='api': code=1;error='HTTP 503'
   else:
    if data.get('race_sha'): data['tag']=data.pop('race_sha')
    if data['tag']: code=1;error='HTTP 422 Reference already exists'
    else:
     assert command[command.index('-f')+1]=='ref=refs/tags/'+os.environ['MODEL_VERSION']
     assert 'sha='+os.environ['GITHUB_SHA'] in command
     data['tag']=os.environ['GITHUB_SHA'];data['kind']='lightweight'
  elif command[2]=='view':
   if data.get('remote_error')=='view': code=1;error='HTTP 503'
   elif not data['release']: code=1;error='release not found'
   elif '--json' in command: output=data.get('release_tag',os.environ['MODEL_VERSION'])
  elif command[2]=='create':
   assert '--verify-tag' in command
   assert command[command.index('--target')+1]==os.environ['GITHUB_SHA']
   if data.get('remote_error')=='create': code=1;error='HTTP 503'
   elif data['release']: code=1;error='HTTP 422 Release already exists'
   else: data['release']=True;data['creates']=data.get('creates',0)+1
   if data.get('move_during_create'): data['tag']='b'*40
 state.write_text(json.dumps(data))
if output: print(output)
if error: print(error,file=sys.stderr)
sys.exit(code)
""")
    for name in ("git", "gh"):
        file = executable / name
        file.write_text(
            "#!/usr/bin/env python3\nimport runpy,sys\n"
            f'sys.argv.insert(1,"{name}")\n'
            f'runpy.run_path({str(driver)!r},run_name="__main__")\n'
        )
        file.chmod(0o755)

    def launch(version="1.0.2", **changes):
        data = json.loads(state.read_text())
        data.update(changes)
        state.write_text(json.dumps(data))
        env = {
            **os.environ,
            "PATH": str(executable) + os.pathsep + os.environ["PATH"],
            "MODEL_STATE": str(state),
            "MODEL_VERSION": version,
            "GITHUB_SHA": SHA,
            "GITHUB_REPOSITORY": "local/review",
        }
        return ["bash", str(SCRIPT), version, "--target", SHA], env, state

    return launch


@pytest.mark.parametrize("version", ["1.0.1", "1.0.2"])
@pytest.mark.parametrize(
    "tag,kind,release",
    [
        (None, None, False),
        (SHA, "lightweight", False),
        (SHA, "annotated", False),
        (SHA, "lightweight", True),
        (SHA, "annotated", True),
        (OTHER, "lightweight", False),
        (OTHER, "annotated", True),
    ],
)
def test_f20_sha_verified_for_lightweight_annotated_and_existing_release(
    release_model, version, tag, kind, release
):
    command, env, state = release_model(version, tag=tag, kind=kind, release=release)
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)
    assert (result.returncode == 0) is (tag != OTHER)
    data = json.loads(state.read_text())
    assert data.get("creates", 0) == (int(not release) if tag != OTHER else 0)
    if result.returncode == 0:
        assert data["tag"] == SHA
        again = subprocess.run(command, env=env, capture_output=True, timeout=10)
        assert again.returncode == 0
        assert json.loads(state.read_text()).get("creates", 0) == int(not release)


@pytest.mark.parametrize("race_sha", [SHA, OTHER])
def test_f20_atomic_ref_collision_is_reread_and_verified(release_model, race_sha):
    command, env, state = release_model(race_sha=race_sha)
    result = subprocess.run(command, env=env, capture_output=True, timeout=10)
    assert (result.returncode == 0) is (race_sha == SHA)
    data = json.loads(state.read_text())
    assert data.get("creates", 0) == int(race_sha == SHA)
    assert data["tag"] == race_sha  # Never overwrite a ref that someone else created.


def test_f20_two_concurrent_runs_share_atomic_tag_and_single_release(release_model):
    command, env, state = release_model()
    first = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    second = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    first.communicate(timeout=10)
    second.communicate(timeout=10)
    assert first.returncode == second.returncode == 0
    data = json.loads(state.read_text())
    assert data["tag"] == SHA
    assert data["creates"] == 1


@pytest.mark.parametrize("movement", ["move_before_release", "move_during_create"])
def test_f20_tag_movement_is_hard_failure_never_false_success(release_model, movement):
    command, env, state = release_model(tag=SHA, **{movement: True})
    result = subprocess.run(command, env=env, capture_output=True, timeout=10)
    assert result.returncode != 0
    assert json.loads(state.read_text()).get("creates", 0) == int(movement == "move_during_create")


@pytest.mark.parametrize("error", ["ls-remote", "fetch", "rev-parse", "api", "view", "create"])
def test_f20_remote_failures_are_closed(release_model, error):
    command, env, state = release_model(tag=None if error == "api" else SHA, remote_error=error)
    result = subprocess.run(command, env=env, capture_output=True, timeout=10)
    assert result.returncode != 0
    assert not json.loads(state.read_text()).get("creates")


def test_f20_generic_workflow_serializes_release_publication():
    config = yaml.load(
        Path(".github/workflows/release.yml").read_text(), Loader=yaml.BaseLoader
    )
    assert config["concurrency"]["group"] == "release-publish-${{ github.ref }}"
    assert config["concurrency"]["cancel-in-progress"] == "false"
    assert config["jobs"]["release"]["needs"] == "validate"
    assert config["jobs"]["cleanup-merged-branches"]["needs"] == "release"
    assert not list(Path(".github/workflows").glob("release-*.yml"))


@pytest.mark.parametrize("tag_kind", ["lightweight", "annotated", "nested"])
@pytest.mark.parametrize("wrong_commit", [False, True])
def test_f20_real_git_objects_are_fully_peeled(tmp_path, tag_kind, wrong_commit):
    repo = tmp_path / "repo"
    repo.mkdir()
    remote = tmp_path / "remote.git"

    def git(*args):
        return subprocess.check_output(
            [
                "git",
                "-c",
                "user.name=Release Test",
                "-c",
                "user.email=test@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "tag.gpgsign=false",
                "-c",
                "core.hooksPath=/dev/null",
                "-C",
                str(repo),
                *args,
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()

    git("init")
    git("commit", "--allow-empty", "-m", "validated")
    sha = git("rev-parse", "HEAD")
    git("commit", "--allow-empty", "-m", "other")
    target = "HEAD" if wrong_commit else sha
    if tag_kind == "nested":
        git("tag", "-a", "inner", target, "-m", "inner annotated tag")
        target = "inner"
    if tag_kind == "lightweight":
        git("tag", "1.0.2", target)
    else:
        git("tag", "-a", "1.0.2", target, "-m", "annotated release tag")
    git("init", "--bare", str(remote))
    git("remote", "add", "origin", str(remote))
    git("push", "origin", "refs/tags/1.0.2")
    executable = tmp_path / "bin"
    executable.mkdir()
    created = tmp_path / "created"
    gh = executable / "gh"
    gh.write_text("""#!/usr/bin/env python3
import os,sys
from pathlib import Path
marker=Path(os.environ['TEST_CREATED'])
if sys.argv[2]=='view':
 if not marker.exists():
  print('release not found',file=sys.stderr)
  sys.exit(1)
 if '--json' in sys.argv: print('1.0.2')
elif sys.argv[2]=='create': marker.touch()
else: sys.exit(1)
""")
    gh.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(executable) + os.pathsep + os.environ["PATH"],
        "GITHUB_SHA": sha,
        "GITHUB_REPOSITORY": "local/test",
        "TEST_CREATED": str(created),
    }
    result = subprocess.run(
        ["bash", str(SCRIPT), "1.0.2", "--target", sha],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert (result.returncode == 0) is (not wrong_commit)
    assert created.exists() is (not wrong_commit)


def test_f20_existing_release_tag_name_must_match(release_model):
    command, env, _ = release_model(tag=SHA, release=True, release_tag="other-version")
    assert subprocess.run(command, env=env, capture_output=True, timeout=10).returncode != 0
