# Source capability and authoritative data-path inventory

This inventory distinguishes user-reported equipment, documented export
formats, implemented readers and evidence from the actual installation.
No representative personal source bundle or live device/server was inspected
during PF-001. Synthetic fixture support is not device qualification.

## Available sources and implemented boundaries

| Source | Established evidence | Implemented boundary | Still to qualify |
| --- | --- | --- | --- |
| Dedicated local Nightscout / Dexcom | User reports more than six months of glucose history; official v1 API describes bounded queries/count | Entries JSON and qualified read-only v1 acquisition; original bytes, native IDs, timestamps, revisions, rejects, deletion markers, full retained projection | Installed version, exact fields/units, count/query cap behavior, uploader/device identity, modification/availability semantics, corrections/hard deletions, complete history |
| Apple Watch Ultra / Apple Health | User reports most-night sleep wear; Apple documents XML export | Allowlisted XML measurements and workout/sleep records; vendor sleep estimates remain distinct; unsupported records retained/countable | Real field/native IDs, sample distribution, timezone, device/app lineage, exercise/sleep coverage, relayed Polar measurements, original availability |
| Polar H10 via Beat/Flow | User reports saved HR/workout summaries; Polar documents TCX/CSV/FIT export | TCX exported HR points and recording extent; no assumption of H10 origin, precise exercise cessation, ECG or RR | Actual export formats/fields, timing and sampling, exercise-end annotation, sensor identity, retained raw/beat data and future logging path |
| Bluetooth Omron BP | User-reported monitor; exact model unknown | Defined manual spot CSV with grouped systolic/diastolic records | Model, supported export/Bluetooth interface, protocol, units, timestamp and measurement groups |
| Ketone/lactate meters | User-reported meters; models/specimen/analyte unknown | Defined manual spot CSV with explicit or unknown specimen/analyte/method | Device/export fields, exact analyte and specimen, source timing and measurement conditions |
| Future garment/wet sessions | Design context only | Contract slots for session, body site, device/configuration, garment/contact and clock context; stream descriptors | Hardware, immersion behavior, raw streams, timebase, dropout and physical experiment decisions |

Apple's supported path is an XML health export. Polar supports several workout
export formats, but this release implements TCX only. Polar's RR documentation
explicitly excludes several Beat/phone and H10-memory recording paths; export
format availability does not prove this user's historical RR archive exists.
References are primary documentation, not checks of the user's devices:

- [Apple: Share your health data / export all health data](https://support.apple.com/en-euro/guide/iphone/iph5ede58c3d/ios)
- [Polar: Export training sessions from Flow](https://support.polar.com/us-en/export-training-sessions-flow)
- [Polar: RR data export](https://support.polar.com/en/rr-data-export)
- [Nightscout v1 Swagger](https://github.com/nightscout/cgm-remote-monitor/blob/master/lib/server/swagger.yaml)

## Reader details

Apple XML allows heart rate, resting heart rate, exact SDNN/RMSSD identifiers,
respiratory rate, oxygen saturation, wrist temperature and glucose when supplied
with supported units. A type being recognized does not imply Apple supplies it
in this user's export. Sleep/category and workout events retain their vendor
identity. `creationDate` is retained as source metadata; it is not promoted to
historical availability. Correlation and unknown record types remain archived
with unsupported accounting. Native UUID is used when present; otherwise a
payload/occurrence fingerprint is flagged as ambiguous.

TCX parsing preserves raw activity/trackpoint records and exported HR. A final
sample bounds a recording, not necessarily exercise cessation. No HR-derived
RR reconstruction or ECG waveform synthesis is performed.

The manual CSV is an interchange format, not an Omron or meter export adapter:

```csv
ts,channel,value,unit,native_id,measurement_group_id,method,specimen,analyte
2026-01-10T18:30:00+10:00,blood_pressure_systolic,118,mmHg,bp1-s,bp1,manual transcription,,
2026-01-10T18:30:00+10:00,blood_pressure_diastolic,76,mmHg,bp1-d,bp1,manual transcription,,
```

Required columns are `ts,channel,value,unit`. Optional identity/group/method/
specimen/analyte fields remain unknown when absent. These are reported meter
observations until an original device export is qualified. Inspect the supplied
synthetic `spots.csv` for the exact accepted field names before use. Units are
normalized through a channel-specific allowlist, with originals retained.

## Authority and runtime boundaries

The new selected SQLite archive is the authority for acquired originals,
immutable revisions, normalized versions and import runs. Parquet outputs are
derived compatibility views. Coach consumes a versioned replay bundle and
does not replace acquisition authority. Its old latest-entry flow has only
in-memory deduplication and preview output; it cannot establish retained
history, catch-up, completeness or live feed reliability.

Existing application behavior/reminder persistence is a separate path. Mother
contains both `mother_app.main:app` and `mother.api:app` launch families. The
root Dockerfile copies `mother_app`, not the new analytics/physiology modules;
this increment does not claim that building that image deploys the new path.
Inspect the actual host/Compose configuration before service integration.

The Nightscout live reader refuses unqualified v1 acquisition before making a
request. Operator qualification must establish the actual bounded query/count
behavior, provide its evidence through `NS_CAPABILITY_EVIDENCE`, and match
`NS_VERIFIED_V1_PAGE_SIZE` to the selected page size. These are evidence gates,
not suggested values to set blindly. Treatment timestamp normalization has its
own gate. Secrets remain in existing authorized configuration and are never
written into request manifests. A full acquisition range is not a transactional
snapshot and cannot discover hard-deleted records without further source support.

## First real-data acceptance and later live gate

Start with one overlapping exercise-to-next-sleep interval: Nightscout entries
including stable native IDs, relevant Apple Health XML, and one original Polar
session export. Include the preceding 24 hours and following waking period
where available, original offsets and any actual exercise-end/workload evidence.
The interval is a qualification sample, not a model-training sufficiency claim.

Check original counts/times/units, export omissions, native identity/revisions,
duplicates/relays, HR sampling, actual sleep intervals and unknown conditions.
Then qualify broader backfill and independent episode counts before model work.

A selected live feed must separately demonstrate observed freshness/latency,
disconnect gaps, buffering or declared loss, restart recovery, durable
checkpoints, and reconciliation against archived/replayed records. Actual
Nightscout/Watch/Polar/Omron capability and host evidence determine that choice.
