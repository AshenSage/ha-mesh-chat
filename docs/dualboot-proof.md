# Milestone 0: reproducible Home Assistant dualboot

**Decision: 2026-10-25. Status: implementation prepared; hardware gate NOT PASSED.**

Make this the core of the repository. Prove the boot/control/storage foundation before investing in the chat product. The later requirements remain recorded but deferred.

## Pass condition

One Heltec WiFi LoRa 32 V4, ESP32-S3R2, 16 MB, 868 MHz can switch MeshCore ↔ Meshtastic from the Home Assistant UI, without reflashing app images or touching buttons during ordinary operation. The target runtime must respond, its original public identity and settings must persist, and USB must reconnect predictably. Initial provisioning/recovery can require buttons; record it separately. A button-assisted ordinary switch is a failed hands-off attempt.

Use the [lab instructions](../dualboot_lab/DOCS.md). The experimental transport changes boot-selection metadata through the USB ROM/stub; whether this works headlessly with the chosen bootloader/builds is a hypothesis to test, not an established capability.

## Sequence

1. Identify the board and host, establish USB/ROM access, preserve its original flash and prepare the compatible isolated layout and USB app builds.
2. Independently confirm both runtimes and record public identity, name, radio settings, channels and peer data. Start with test identities, not important production profiles.
3. Enrol/back up the prepared board, capture the active protocol baseline, and execute one switch each way. First observation of a profile is baseline establishment, not proof of retention.
4. Run 3 A→B→A rounds; diagnose failures before a longer run.
5. Run 20 A→B→A rounds with unchanged hardware/builds on Proxmox/HAOS (amd64). No retries hidden from the report. After a failure/fix, record the new version and begin a fresh run.
6. Repeat the same run on Raspberry Pi/HAOS (aarch64), including actual app installation and USB access. Architecture declarations/container builds alone do not pass this row.
7. Exercise the lifecycle/error cases below. Recheck both profiles after each case.

## Acceptance matrix

All rows start **NOT RUN**. Do not infer a hardware pass from software tests, static review or a successful flash write.

| Case | Evidence / pass criterion | Status |
| --- | --- | --- |
| Build/provisioning | Archive component sources/hashes; exact binary table matches allowlist; both USB protocols respond independently | NOT RUN |
| Initial round trips | Three complete rounds from HA, actual target runtime observed twice after each switch | NOT RUN |
| Proxmox/HAOS | Twenty complete rounds (40 actual transitions), zero failed attempts, no ordinary button presses | NOT RUN |
| Raspberry Pi/HAOS | Same proof, including app install and direct USB on actual aarch64 host | NOT RUN |
| Identity/settings | Public identity stable across every revisit; name/radio fingerprints stable; channels/keys/contacts checked separately | NOT RUN |
| Idle stability | Leave each firmware active for 30 minutes; reconnect/check at beginning and end, then switch both ways | NOT RUN |
| App restart | Restart app on each firmware; jobs not resumed; inspect/reconnect and both directions work | NOT RUN |
| HA Core restart | Restart HA Core on each firmware; app's actual lifecycle recorded; both directions work afterwards | NOT RUN |
| HAOS reboot | Reboot host/VM on each firmware; no schedule/auto-switch; runtime/profiles recover and both directions work | NOT RUN |
| Power cycle | Five radio power cycles per firmware; identity/settings retained and USB reconnects | NOT RUN |
| USB interruption | Interrupt a bench attempt; report fails/interrupts, no blind retries; device can be inspected/recovered | NOT RUN |
| Bad layout/device | Unsupported layout, wrong flash size, changed MAC/build and damaged snapshot block writes | NOT RUN |
| Recovery | Preserve original snapshot; document actual ROM/button recovery procedure and verify restored profiles | NOT RUN |

These are proposed engineering acceptance counts for this lab milestone, not claims of a statistically proven failure rate. If a test cannot be performed (e.g. no second host yet), keep it pending and state the narrower evidence.

## Evidence record per run

Copy this into a GitHub issue or attach a completed report. Keep secret/raw flash data private.

```text
Date/time (with timezone):
Operator / test location:
Board model / physical revision / confirmed variant / radio band:
Factory MAC (or private record reference):
Host model / architecture / Proxmox and USB mapping where applicable:
HAOS / Supervisor / HA Core versions:
Lab app version + repository commit:
Bootloader / selector source, version, SHA256:
Partition-table SHA256:
MeshCore source commit, build environment, patch set, app SHA256:
Meshtastic version, source/provenance, app SHA256:
Full-flash backup captured and checked (do not attach raw dump):
Starting firmware / completed transitions in each direction:
Maximum observed switch/reconnect duration:
Ordinary-operation button presses (must be zero to pass):
Setup/recovery button presses (separate):
Identity / selected settings / separate channel/contact checks:
Lifecycle and negative cases exercised:
Failures, recovery steps, and any changed software/build:
JSON report attachment:
Verdict: NOT RUN / BLOCKED / FAILED / PASSED for stated cases only
```

The JSON report contains per-step timestamps/results and stops at the first failure. Duration/host/build context and physical button use must currently be recorded by the operator. The lab does not certify every private setting or provide complete replacement restore.

## Scope gate

Until the required hardware evidence is passed: fix dualboot/USB/profile/recovery issues only. Chat UI, notifications, outbox, schedules, comparison reports and full guided installation are the next phase. Do not mark those features implemented or reopen their detailed product decisions as prerequisites for this bench test.

## Reviewed technical references

- [Espressif OTA boot-selection tool](https://github.com/espressif/esp-idf/blob/master/components/app_update/otatool.py) and [OTA documentation](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/system/ota.html).
- [Reference dualboot checkout](https://github.com/tkh1000/Meshtastic-Meshcore-Dualboot-Heltec-V4-/tree/b889b895a9ef96a07c217cbc02460cf8e64b0739). The root and selector source tables differ; USB control is not supplied by its OLED/button workflow.
- [MeshCore USB companion environment](https://github.com/meshcore-dev/MeshCore/blob/81dbae592ffad40b4212bc0b37e82b38da08f4bc/variants/heltec_v4/platformio.ini).
- [Home Assistant app configuration](https://contributors.home-assistant.io/apps/reference/configuration/), serial/USB access and admin Ingress.
