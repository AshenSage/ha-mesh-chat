"""Static supply-chain policies plus local import smoke; no container/device."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_c2_all_workflow_actions_pinned_and_credentials_not_retained():
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        text = path.read_text()
        assert "permissions:\n  contents: read" in text
        for action in re.findall(r"uses: ([^\s]+)", text):
            assert re.fullmatch(r"[\w/-]+@[0-9a-f]{40}", action), action
        assert text.count("persist-credentials: false") == text.count("uses: actions/checkout@")


def test_c2_runtime_and_development_locks_have_versions_and_hashes():
    for name in ("requirements.lock", "requirements-dev.lock", "requirements-bootstrap.lock"):
        text = (ROOT / "dualboot_lab" / name).read_text()
        records = re.split(r"\n(?=[a-zA-Z])", text)
        for record in records:
            if record.startswith("#"):
                record = '\n'.join(line for line in record.splitlines() if not line.startswith("#"))
            if not record.strip():
                continue
            assert re.match(r"[\w.-]+==[\w.+-]+", record)
            assert re.search(r"--hash=sha256:[0-9a-f]{64}", record)


def test_c2_container_installs_locked_packages_and_runs_import_smoke():
    text = (ROOT / "dualboot_lab/Dockerfile").read_text()
    assert "--require-hashes" in text and "--no-build-isolation" in text
    assert 'RUN python -c "import lab.server"' in text
    import lab.server  # actual local smoke, not proof of either container architecture


def test_c2_platformio_patch_does_not_reintroduce_floating_versions():
    patch = (ROOT / "firmware/meshcore-usb-lab.patch").read_text()
    additions = '\n'.join(line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++'))
    assert "platform = platformio/espressif32@6.11.0" in additions
    assert "~" not in additions and "^" not in additions
    assert "ArduinoJson @ 7.4.3" in additions



def test_r2_8_supervisor_stop_budget_exceeds_http_and_worker_cleanup():
    import yaml
    from lab.server import TERMINATION_GRACE, HTTP_SHUTDOWN_TIMEOUT
    config = yaml.safe_load((ROOT / "dualboot_lab/config.yaml").read_text())
    assert 10 <= config["timeout"] <= 300
    assert config["timeout"] >= TERMINATION_GRACE + HTTP_SHUTDOWN_TIMEOUT + 10



def test_r2_p3_container_base_is_an_immutable_multiarch_digest():
    line = (ROOT / "dualboot_lab/Dockerfile").read_text().splitlines()[0]
    assert re.fullmatch(r"FROM python:3\.12-slim-bookworm@sha256:[0-9a-f]{64}", line)
