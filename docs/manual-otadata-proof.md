# A5 — manual boot-selection hypothesis

**Status: NOT RUN. No radio is available to this review task.** This document is a future operator procedure, not execution evidence. Do not start lab automation or unattended tests until this hypothesis is demonstrated on the provisioned board. Safety fixes may be reviewed offline in the meantime.

Question: does the exact external bootloader select the requested runtime from OTA data alone, or can selector NVS override it? Merely reading OTA data back does not answer this. The reference source and prebuilt bootloader do not establish equivalent provenance.

Attestation limit (N6): a lab baseline proves only **"protocol N responded while otadata selected slot S"**, not **"slot S actually ran"**. The selector/bootloader may override that selection, which is exactly what A5 must independently establish. Generic or empty project descriptors add no slot evidence. Matching app hashes freeze the bytes observed, not their actual execution. No fake, protocol response or registry record closes this hardware assumption.

Future, separately authorised manual bench procedure (do not use the lab worker):

1. Independently identify both manually booted USB runtimes with external tools (keep the lab stopped; no lab registry/attestation prerequisite), observe the real R2 PSRAM cap, verify the reference allowlist, preserve original flash, record the written bootloader readback hash, and configure both test identities. Identify the physical board and both runtimes independently.
2. Stop the HA app and all serial owners. Read the actual table and both OTA sectors with external esptool; archive these private files and `nvs_sel`. Check CRC/state and select the inactive OTA copy. Retain the other valid sector.
3. Prepare and independently inspect a single-sector OTA selection update with the ESP-IDF-compatible sequence and CRC. Have a second person/tool verify address, size, target slot and preserved recovery copy. Do not erase the whole OTA partition or profile data.
4. In a separately authorised physical test, write that sector with esptool, reset, and observe the actual USB runtime/identity independently. Do not run the lab controller. Record whether a selector screen, button or other mechanism intervened.
5. Repeat for the reverse direction, including a normal power cycle from each selection. Compare the private `nvs_sel` dump before/after; investigate any changes. Repeat after deliberately entering/exiting the selector, without altering test identities.
6. Restore/check both identities and profile data. On any mismatch or button-assisted ordinary switch, stop and mark the hypothesis FAILED/BLOCKED. Never regenerate keys to conceal a lost profile.

Record: date/operator, exact hardware, host/USB mapping, all source/written component hashes, OTA old/new sequence/state/CRC and sector address, selector NVS hash, actual firmware response in both directions, identity fingerprints, button use, power-cycle results and private evidence location. Do not publish raw flash, namespace contents or keys.

No result is recorded yet. When the operator supplies evidence, add a dated result referencing immutable builds and actual observations. A checkbox, unit test, compilation or this procedure cannot mark the hypothesis hardware-validated.


R2-9 stability subtest — NOT RUN: before testing OTA writes, read nvs_sel MD5 before and after several ordinary boots of EACH manually selected firmware and after entering/leaving the selector. Record app hashes, boot source/sequence, normal versus selector-assisted boot, MD5 sequence and any changes; reads must not write NVS. Until this proves normal-boot stability, selector_nvs_md5 remains an observed warning field, never a hard device-binding gate. Every warning is retained in the lab report; table, MAC, app and bootloader checks remain strict. Meshtastic shared-NVS use remains unknown.
