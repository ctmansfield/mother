# All-history archive and Mother/Coach dataset

Instruction: [MSE-HEALTH-HISTORY-20261121-06 r1](https://github.com/ctmansfield/mother/pull/23#issuecomment-7057772764). Chad explicitly selected all available historical HealthKit categories, especially blood pressure, for Mother/Coach testing. Backup/restore remains deferred. This historical enrollment is separate from the running 14-type pilot and does not reset its anchors, scope or November 23 cutoff.

## Capture and retention

Preserve the exact native Apple Health export and attachments as original evidence, with authenticated encryption and a private coverage manifest. The private decryption identity remains with the custodian outside the archive VM. The ciphertext receiver cannot normalize or decrypt merely by accepting a file. Raw custody, typed normalization, and consumer-ready data are separate receipt states.

Local capture uses the verified private FileVault-protected Downloads landing directory, followed by a closed-file byte-verified copy into a dedicated encrypted APFS capture volume. The identity volume is separately encrypted and detached. An actual synthetic AirDrop round trip returned the same 215-byte ZIP and SHA-256; source and capture files were mode 0600. The user is preparing the real native export. No real historical file has yet been received, uploaded or parsed at this checkpoint. Native Health exports do not belong in chat or GitHub.

Apple's export is a candidate broad source, not proof that every HealthKit family is included. Inventory quantities, categories, characteristics, correlations, workouts/activity, series/routes, ECG/audiogram/vision, and clinical/medication families where supported. Distinguish SDK declarations, actual OS/API support, entitlement gates, visible records, permission uncertainty, empty results and unsupported formats. Preserve unknown original attachments and account for unnormalized records instead of silently discarding them.

## Blood pressure first

Chad confirmed KN-550BT readings in both Apple Health and MyVitals, including new readings. Use HealthKit first; no new vendor SDK, account or cuff synchronization is needed. The initial source candidate is [MotherHealthBridge #17](https://github.com/ctmansfield/mother-health-bridge/pull/17), `f6909a8f47f575857c13041aec5f4cbe1f4148c2`: 51 synthetic tests and a signed generic iOS build passed. It has no active capture screen or archive writer yet.

Preserve explicit systolic/diastolic correlation and component membership, mmHg units, source identities, original timestamps and deletion/correction lineage. Incomplete or orphan components are not fabricated into pairs. A cuff pulse is not linked to BP without source evidence. API UUIDs and export-local identities are distinct; equal time/value does not prove a shared source record.

BP pages use separate correlation, systolic and diastolic streams. Native HealthKit anchors stay protected on the phone; only enrollment-scoped opaque checkpoint tokens travel to the receiver. Persist one exact pending page before transmission, bind sequence/digest/output token/counts in a durable receipt, and advance the local native checkpoint only after that receipt matches. Query completion requires an explicit empty terminal query and its receipt for every feed. It does not establish complete read permission or an atomic global HealthKit snapshot.

## Mother/Coach and Nightscout

Prepare a purpose-scoped pseudonymous facts database or read-only API, separate from raw originals, identity mapping and decryption keys. Default views exclude direct identity, GPS, raw source IDs, free text and credentials. Preserve authorized BP/glucose alignment and exact units, while documenting any time transformation or utility loss. Physiology and timing can remain linkable; a separate database is not an anonymity guarantee.

Existing [parked MOTHER glucose-read work](https://github.com/ctmansfield/mother-health-bridge/pull/1) supplies latest/observations/coverage interface concepts. It does not establish current Nightscout acquisition, complete history, resolved upstream units, or a paired BP/CGM Coach interface. Review and synthetic adapter development are authorized; real Nightscout endpoint access, credentials, NAS deployment and LLM forwarding are not part of this capture step.

## Completion evidence

Report exact raw original/ciphertext/member inventory, per-family source and normalized counts, paired BP and orphan counts, unresolved identity overlaps, parser rejections, restart/resume and dedup tests, source/product/runtime pins, and consumer projection coverage. ZIP/XML resource and path controls must be qualified against real format features, including safe handling of Apple internal DTD declarations while forbidding entities and external resolution. Never equate an encrypted file receipt with populated analytical tables or all-category completeness.
