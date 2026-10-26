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



def test_r2_p3_platform_metadata_comes_from_versioned_patch(tmp_path):
    patch = tmp_path / "platform.patch"
    patch.write_text("+platform = platformio/espressif32@9.8.7\n")
    assert builder.pinned_platform(patch) == "platformio/espressif32@9.8.7"
    patch.write_text("+platform = platformio/espressif32@latest\n")
    with pytest.raises(SystemExit, match="pinned Espressif"):
        builder.pinned_platform(patch)


@pytest.mark.parametrize("call", ["Update.begin(size);", "Update.write(data, len);", "Update.writeStream(stream);",
    "esp_ota_begin(partition, size, &handle);", "esp_ota_write(handle, data, size);",
    "esp_ota_get_running_partition();", "spi_flash_erase_range(0, size);", "spi_flash_write(0, data, size);",
    "esp_flash_erase_region(chip, 0, size);", "esp_flash_write(chip, data, 0, size);"])
def test_n5_ota_and_direct_flash_calls_need_an_explicit_allowlist_entry(checkout, call):
    source, _, _, _ = checkout
    extra = source / "unreviewed.cpp"
    extra.write_text(call + "\n")
    subprocess.run(["git", "add", "unreviewed.cpp"], cwd=source, check=True)
    with pytest.raises(SystemExit, match="Unreviewed filesystem call"):
        builder.audit_filesystems(source)


def test_n5_build_rejects_wifi_ota_marker_before_export(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    source = tmp_path / "source"
    binary = source / ".pio/build" / builder.ENVIRONMENT / "firmware.bin"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"\xe9mc_spiffs\0MeshCore-OTA\0")
    output = tmp_path / "output"
    monkeypatch.setattr(builder, "prepare", lambda *_, **__: None)
    monkeypatch.setattr(builder, "pinned_platform", lambda: "platformio/espressif32@6.11.0")
    monkeypatch.setattr(builder.subprocess, "run", lambda *_, **__: SimpleNamespace(returncode=0))
    monkeypatch.setattr(sys, "argv", ["prepare_meshcore_usb.py", str(source), "--build", "--output", str(output)])
    with pytest.raises(SystemExit, match="MeshCore-OTA marker"):
        builder.main()
    assert not (output / "meshcore-usb-lab.bin").exists()
    builder.validate_image(b"\xe9mc_spiffs\0valid synthetic app")
