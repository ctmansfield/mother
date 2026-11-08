"use strict";

// Synthetic fixture generator using the *actual pinned Coach browser module*.
// This script is test-only; it never opens a browser or contacts a service.

const path = require("node:path");
const {webcrypto} = require("node:crypto");

const checkout = process.env.COACH_CHECKOUT;
if (!checkout) throw new Error("COACH_CHECKOUT is required");
const capture = require(path.join(checkout, "coach_app/physiology/capture_ui.js"));

const kind = process.argv[2] || "marker";
const eventConfig = {
  marker: {
    event_kind: "user_marker",
    text: "Changed electrode contact; one gap noted — 皮肤",
    occurrence_start: "2026-11-07T14:05:00+10:00",
    parent_id: "", parent_kind: ""
  },
  action: {
    event_kind: "reported_action",
    text: "Adjusted the garment pocket",
    occurrence_start: "2026-11-07T14:05:00+10:00",
    parent_id: "", parent_kind: ""
  },
  outcome: {
    event_kind: "outcome",
    text: "Reported condition unchanged; no measured outcome",
    occurrence_start: "2026-11-07T14:08:00+10:00",
    parent_id: "coach-manual:00000000-0000-4000-8000-000000000002",
    parent_kind: "reported_action"
  }
};
if (!Object.prototype.hasOwnProperty.call(eventConfig, kind)) {
  throw new Error("Unknown synthetic scenario");
}
const suffix = {marker: "1", action: "2", outcome: "3"}[kind];
const runtime = {
  randomUUID: () => "00000000-0000-4000-8000-00000000000" + suffix,
  subtle: webcrypto.subtle
};
const fields = {
  subject_id: "synthetic-subject",
  occurrence_end: "",
  known_at: "",
  session_id: "",
  ...eventConfig[kind]
};

async function main() {
  const event = capture.createDraft(fields, runtime, new Date("2026-11-07T04:12:00Z"));
  const packet = await capture.makeEnvelope(event, runtime);
  process.stdout.write(Buffer.from(packet.bytes).toString("base64") + "\n");
}
main().catch(error => {
  process.stderr.write("Synthetic generation failed: " + error.name + "\n");
  process.exitCode = 1;
});
