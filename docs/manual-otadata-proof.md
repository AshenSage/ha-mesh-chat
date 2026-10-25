# A5 — manual boot-selection hypothesis

**Status: NOT RUN. No radio is available to this review task.** This document is a future operator procedure, not execution evidence. Do not start lab automation or unattended tests until this hypothesis is demonstrated on the provisioned board. Safety fixes may be reviewed offline in the meantime.

Question: does the exact external bootloader select the requested runtime from OTA data alone, or can selector NVS override it? Merely reading OTA data back does not answer this. The reference source and prebuilt bootloader do not establish equivalent provenance.

Future, separately authorised manual bench procedure (do not use the lab worker):

1. Resolve A2's generic descriptors, verify the reference allowlist, preserve original flash, record the written bootloader readback hash, and configure both test identities. Identify the physical board and both runtimes independently.
2. Stop the HA app and all serial owners. Read the actual table and both OTA sectors with external esptool; archive these private files and `nvs_sel`. Check CRC/state and select the inactive OTA copy. Retain the other valid sector.
3. Prepare and independently inspect a single-sector OTA selection update with the ESP-IDF-compatible sequence and CRC. Have a second person/tool verify address, size, target slot and preserved recovery copy. Do not erase the whole OTA partition or profile data.
4. In a separately authorised physical test, write that sector with esptool, reset, and observe the actual USB runtime/identity independently. Do not run the lab controller. Record whether a selector screen, button or other mechanism intervened.
5. Repeat for the reverse direction, including a normal power cycle from each selection. Compare the private `nvs_sel` dump before/after; investigate any changes. Repeat after deliberately entering/exiting the selector, without altering test identities.
6. Restore/check both identities and profile data. On any mismatch or button-assisted ordinary switch, stop and mark the hypothesis FAILED/BLOCKED. Never regenerate keys to conceal a lost profile.

Record: date/operator, exact hardware, host/USB mapping, all source/written component hashes, OTA old/new sequence/state/CRC and sector address, selector NVS hash, actual firmware response in both directions, identity fingerprints, button use, power-cycle results and private evidence location. Do not publish raw flash, namespace contents or keys.

No result is recorded yet. When the operator supplies evidence, add a dated result referencing immutable builds and actual observations. A checkbox, unit test, compilation or this procedure cannot mark the hypothesis hardware-validated.
