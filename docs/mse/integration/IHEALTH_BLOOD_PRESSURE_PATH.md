# iHealth Track KN-550BT — archive integration investigation

Chad identified his Bluetooth cuff as iHealth KN-550BT and requested blood pressure as a priority. He then confirmed that readings are visible in both MyVitals and Apple Health, including new readings. [The all-history directive](https://github.com/ctmansfield/mother/pull/23#issuecomment-7057772764) authorizes paired BP preparation and a separate historical import. This does not silently expand the current pilot's 14-type allowlist, create an iHealth account, pair a device or authorize a new cloud service.

## Preferred route to verify

`KN-550BT → iHealth MyVitals → Apple Health → MotherHealthBridge → private archive`

iHealth's [model-specific connection instructions](https://support.ihealthlabs.com/hc/en-us/articles/8492779460877-FAQ-Problems-connecting-to-my-phone-Track-KN-550BT) identify Track as a Bluetooth LE device connected through MyVitals rather than the phone's ordinary Bluetooth pairing menu. Its [Apple Health authorization guide](https://support.ihealthlabs.com/hc/en-us/articles/38770628862093-FAQ-How-to-authorize-3rd-party-apps-in-iHealth-MyVitals-app-iOS) describes linking MyVitals to Apple Health. This establishes a supported candidate route; the user's installed app, permissions and actual exported records still require verification.

Do not reset or synchronize the cuff blindly: the [manufacturer's synchronization instructions](https://support.ihealthlabs.com/hc/en-us/articles/8164119201037-FAQ-How-to-take-a-measurement-iHealth-Track-KN-550BT) state that app synchronization resets onboard memory. Establish existing cuff/app custody and whether an export is needed before taking that step. Do not request or publish actual measurement numbers in chat.

MyVitals can involve an iHealth account/cloud. Routing through HealthKit avoids a separate MOTHER cloud integration; it does not demonstrate that the vendor app itself stays local. If vendor-cloud involvement is unacceptable, investigate the manufacturer's direct native Bluetooth SDK and its exact KN-550BT support, licensing and app-registration requirements before choosing that route. The [official developer platform](https://developer.ihealthlabs.com/) offers both cloud API/webhooks and mobile Bluetooth SDKs; no account registration, OAuth grant or license acceptance has occurred here.

## Required application and archive work

- Request separate HealthKit read access for systolic and diastolic data. Query actual blood-pressure correlations when present; [Apple's correlation type](https://developer.apple.com/documentation/healthkit/hkcorrelationtypeidentifier/bloodpressure/) represents the two values as a paired reading.
- Add a versioned paired record shape with explicit mmHg units, measurement interval, correlation and component identities, opaque source attribution, collector clock and revision/deletion lineage. Preserve the relationship; never match unrelated values merely because their timestamps are close.
- Treat orphan quantities and missing pair/source information explicitly. Do not infer a cuff pulse association from an unrelated heart-rate sample.
- Preserve originals and corrections without an automatic age purge. A HealthKit deletion changes the current view while retained archive history remains subject to the selected retention policy.
- Use one canonical ingestion route for a measurement. Do not simultaneously import iHealth cloud and HealthKit copies without verified cross-source identity reconciliation; equal values/time are not sufficient deduplication evidence.
- Test new permission/empty/partial states, pair integrity, corrections/deletions, units, exact-byte outbox, receipt and original/export round trip with synthetic data before an independently qualified in-place build and separately scoped live addition.

## Remaining facts

The working cuff→MyVitals→Apple Health path and current reading visibility are user-confirmed. The exact installed app/version, paired correlation/component representation and per-source history counts still require independent verification. No cuff or blood-pressure value was accessed for this investigation. The current 48-hour pilot has actual first and natural follow-up acknowledgments; BP remains outside that existing live schema. Historical/BP work uses a separate enrollment and must not overwrite its window, queued bytes or anchors. Backup/restore remains deferred.
