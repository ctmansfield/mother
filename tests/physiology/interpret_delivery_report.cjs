"use strict";

// Synthetic cross-repository acceptance against the actual Coach status module.
// Input is a single JSON object via stdin; no network or file mutation.
const {readFileSync} = require("node:fs");
const {webcrypto} = require("node:crypto");
const path = require("node:path");

async function main() {
  const checkout = process.env.COACH_CHECKOUT;
  if (!checkout) throw new Error("Pinned Coach checkout required");
  const viewer = require(path.join(checkout, "coach_app/physiology/delivery_status.js"));
  const payload = JSON.parse(readFileSync(0, "utf8"));
  const envelope = Uint8Array.from(Buffer.from(payload.envelope_base64, "base64"));
  const info = await viewer.decodeEnvelope(envelope, {subtle: webcrypto.subtle});
  const outcome = viewer.interpretStatus(info, payload.report, payload.attempted);
  process.stdout.write(JSON.stringify(outcome) + "\n");
}

main().catch(error => {
  process.stderr.write(JSON.stringify({status: "rejected", error_type: error.name}) + "\n");
  process.exitCode = 2;
});
