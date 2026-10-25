"""Synthetic git checkouts only; no firmware/flash commands."""
import difflib
import hashlib
import json
import subprocess

import pytest

import prepare_meshcore_usb as builder


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    path = source / "main.cpp"
    original = 'SPIFFS.begin(true);\n'
    prepared = 'SPIFFS.begin(true, "/spiffs", 10, "mc_spiffs");\n'
    path.write_text(original)
    subprocess.run(["git", "init", "-q"], cwd=source, check=True)
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "commit", "-qm", "fixture"], cwd=source, check=True)
    ref = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    patch = tmp_path / "change.patch"
    patch.write_text(''.join(difflib.unified_diff(original.splitlines(True), prepared.splitlines(True),
                                                fromfile="a/main.cpp", tofile="b/main.cpp")))
    files = tmp_path / "files.json"
    files.write_text(json.dumps({"main.cpp": {"original": hashlib.sha256(original.encode()).hexdigest(),
                                            "prepared": hashlib.sha256(prepared.encode()).hexdigest()}}))
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps([{"path": "main.cpp", "text": text.strip()} for text in (original, prepared)]))
    for key, value in {"MESHCORE_REF": ref, "PATCH": patch, "FILES": files, "AUDIT": audit}.items():
        monkeypatch.setattr(builder, key, value)
    return source, path, original, prepared


def test_c1_preparation_is_idempotent_and_exactly_resettable(checkout):
    source, path, original, prepared = checkout
    builder.prepare(source)
    assert path.read_text() == prepared
    builder.prepare(source)
    assert path.read_text() == prepared
    builder.prepare(source, reset=True)
    assert path.read_text() == original


def test_c1_unknown_filesystem_call_aborts_before_changes(checkout):
    source, path, original, _ = checkout
    extra = source / "other.cpp"
    extra.write_text("SPIFFS.format();\n")
    subprocess.run(["git", "add", "other.cpp"], cwd=source, check=True)
    with pytest.raises(SystemExit, match="Unrelated local changes|Unreviewed filesystem"):
        builder.prepare(source)
    assert path.read_text() == original


def test_c1_changed_or_last_section_layout_is_an_explicit_error(checkout):
    source, path, _, _ = checkout
    changed = '[env:usb]\nSPIFFS.begin(true);\n'
    path.write_text(changed)
    with pytest.raises(SystemExit, match="Unsupported/partially modified source or section layout"):
        builder.prepare(source)
    assert path.read_text() == changed


@pytest.mark.parametrize("call", ["nvs_flash_erase();", 'nvs_flash_erase_partition("nvs");',
    "esp_partition_erase_range(p, 0, size);", "esp_partition_write(p, 0, bytes, size);",
    "esp_vfs_spiffs_register(&config);", "esp_spiffs_format(label);", "esp_littlefs_format(label);"])
def test_r2_4_shared_storage_calls_require_explicit_audit_entry(checkout, call):
    source, _, _, _ = checkout
    extra = source / "unsafe.cpp"
    extra.write_text(call + "\n")
    subprocess.run(["git", "add", "unsafe.cpp"], cwd=source, check=True)
    with pytest.raises(SystemExit, match="Unreviewed filesystem call"):
        builder.audit_filesystems(source)
