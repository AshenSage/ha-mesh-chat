# Automatic switching

**Stage: Later product requirements · Deferred behind the dualboot proof**

The current [Dualboot Lab](dualboot-proof.md) tests manual HA requests and bounded bench-test repetitions only. It has no operating schedules, comparison mode or message synchronization. Build these features only after stable, reproducible HA-controlled dualboot is demonstrated.

## Operating modes

| Mode | Expected behaviour |
| --- | --- |
| Manual | Keep the selected network active until changed. |
| Schedule | Select firmware by configurable time windows, including overnight windows. Example: Meshtastic 20:00–08:00, MeshCore 08:00–20:00. |
| Timer | Switch for a chosen duration, then return to the previous network. |
| Comparison | Alternate networks over a configurable evaluation period, for example 30 days, and report the observations. |

## Switching behaviour

- Reuse the same validated switching process as manual selection; no repeated firmware flashing.
- Preserve each firmware's identity, settings, contacts and recorded channel/DM history.
- Warn before automatic switches with a visible countdown and Snooze. Make the warning lead time and snooze duration configurable; persist snooze deadlines across HA restarts.
- Allow a manual override with an explicit hold or expiry, and a clear way to resume automation.
- Complete pending transmissions and acknowledgement waits before switching, with a bounded wait and visible outcome. Keep messages queued for the inactive network until it is confirmed active, and reconcile uncertain outcomes before retrying.
- Confirm the actual firmware after reconnecting. Before any schedule-driven change after an outage, try to import that firmware's available received messages and commit them durably to HA. Show recovery progress and deduplicate replayed messages.
- Synchronize the active firmware's available inbound backlog before ordinary switches too. Use a bounded synchronization pass; on read or storage failure, postpone automatic switching and report the cause. Do not equate unsupported retrieval with an empty queue. Exact unsupported-retrieval fallback and limits remain to be defined.
- Report failed switches and use bounded recovery rather than an endless reboot loop.
- Pause automatic switching during HA/controlling-service outages; a powered radio stays on its last selected firmware. No independent outage scheduler is part of the accepted baseline.
- Preserve schedules and timer deadlines across HA restarts. Recover available received messages first, then reconcile the current time and observed firmware; do not replay every missed switch.
- Use the configured HA timezone, handle daylight-saving changes, and skip switches when the requested firmware is already active.

## Comparison and reporting

- Use configurable observation blocks, initially considering four hours. Rotate network assignments across days so both networks receive comparable daytime/night-time and weekday/weekend exposure.
- Keep the radio location and antenna unchanged for a stationary comparison.
- Log actual connected observation time, startup periods, outages and switch failures separately.
- Compare received messages and distinct senders per observation hour, plus successful deliveries/replies to selected test peers and response times where available.
- Keep local send acceptance, repeater forwarding, peer acknowledgement and an actual reply as distinct outcomes.
- Treat node counts and signal readings as supporting diagnostics, not a universal score across protocols.
- Optional active tests require configured, consenting test peers and restrained traffic; no automatic public-channel test spam.

The report evaluates usefulness and reliability at the tested location. Geographic coverage or a specific route requires measurements at those locations and suitable counterparts. A fixed day/night split is a convenience schedule, not a fair comparison by itself.

## Interface

Show the confirmed active firmware, operating mode, next scheduled change or timer expiry, warning countdown, snooze/override state and switching/error progress. Browse either saved chat without changing firmware; only the active network can transmit. See [feature requirements](requirements.md) for the outbox and shared contact behaviour.

See [HA outage and message recovery](requirements.md#ha-outage-and-message-recovery) for recovery ordering and firmware-buffer limitations.

**Constraint:** one network is active at a time. Messages on the inactive network may be missed.
