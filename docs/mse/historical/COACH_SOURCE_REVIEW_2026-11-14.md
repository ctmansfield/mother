# GADGET / Coach read-only coordination review

Reviewed 2026-11-13 15:04 UTC / 2026-11-14 01:04 Pacific/Guam. GitHub GET operations only. No host access, runtime commands, repository writes, CI reruns, credential access, comments or external-worker contact.

## 1. Nightscout: source defect established; deployment attested separately

[MOTHER issue 10](https://github.com/ctmansfield/mother/issues/10) is open and currently has five comments. Its latest [comment 6856217695](https://github.com/ctmansfield/mother/issues/10#issuecomment-6856217695), created/updated **2026-11-13 14:42:45 UTC**, still says the fix has not been deployed and the pilot remains blocked. There is no later repository comment documenting deployment.

The user's newer report—read-only handler bind on a pinned image, verified-TLS status exactly `{"entries":"r"}` with the Keychain Subject, anonymous 401, and backup `/var/backups/nightscout-status-v3-20261113T145507Z`—is **later operator attestation**. It supersedes the comment's chronology for the reported scope check; it is not current-host verification by this review. No exact deployed image digest, handler SHA-256, Compose override bytes or restart persistence evidence was supplied to this reviewer. No secret was requested or accessed.

The defect is independently corroborated by both linked upstream source files:

- [15.0.3 pinned handler](https://github.com/nightscout/cgm-remote-monitor/blob/91cd601038a3bce00f92655cc6b1cc02fa3589d3/lib/api3/specific/status.js): `permsForCol` accesses `col.colName`, while the loop passes the string key `col` at line 44.
- [15.0.9 pinned handler](https://github.com/nightscout/cgm-remote-monitor/blob/c6a0d8ed65637bc90d3090e6e7a0f752041c57fd/lib/api3/specific/status.js): identical file blob `5ec28929fbe55f287afe8da614f2d28e9f173cc8`.

The one-line proposed correction `permsForCol(cols[col], opCtx.auth)` matches that object-versus-key defect. These source reads verify the two named versions, not every later upstream release. A status permission map is reporting evidence; it does not itself prove pagination, complete history, correction/deletion semantics, uploader continuity or ingestion readiness.

## 2. Durable source/release gap in Coach

Current Coach main remains `1dd63725dbed112fc33d9c9a64b60b1d7263c246`; latest I01 head remains `184606fe9d5022997f09a2e4d6ef38e5dca4a9bc`. The complete branch listing contains main and six PF001/I01 branches only. The six PRs likewise contain those increments. [Releases API](https://api.github.com/repos/ctmansfield/coach/releases?per_page=100) returns `[]`.

The [tracked Compose file](https://github.com/ctmansfield/coach/blob/1dd63725dbed112fc33d9c9a64b60b1d7263c246/vm/coach/docker/compose/docker-compose.yml) has `nightscout/cgm-remote-monitor:latest` at line 59, no Nightscout service volume/bind, no image digest pin, and no `AUTH_DEFAULT_ROLES` override. Its blob `e1a757c142bc0da0ea2acc7e13b49b2f308d3000` is identical at the latest I01 head. Complete, untruncated main/latest-I01 trees contain no Nightscout status-handler source, patch or dedicated regression test. The tracked [Nightscout setup guide](https://github.com/ctmansfield/coach/blob/1dd63725dbed112fc33d9c9a64b60b1d7263c246/docs/nightscout_setup.md) is the older functionality-first/v1 polling guide; [release notes](https://github.com/ctmansfield/coach/blob/184606fe9d5022997f09a2e4d6ef38e5dca4a9bc/RELEASE_NOTES.md) remain a 2025 design-only v0.1.0 document.

**Conclusion:** a durable repository/release path for the reported runtime fix was not found in the checked Coach refs. This does not prove no host-local artifact or other repository exists. The tracked Compose file must not be treated as a faithful record of the newly attested runtime configuration.

**Next-image upgrade implication:** pinning the base image does not identify the bytes in an external bind mount. An upgrade can lose the bind or keep an old handler against a changed API. Preserve a reviewed source patch and test with upstream commit, original/modified handler hashes, image digest, exact read-only target path, override manifest, rollback provenance and a compatibility decision. A future release gate should require the denied-default/entries-only synthetic regression and the already specified scope-only TLS/anonymous checks. This is a proposal, not a change performed here; no reason to broaden the credential or weaken the scope gate was found.

## 3. Coach PF001/I01 PR state and exact-head CI

All six PRs are **open, draft, unmerged, mergeable=true, mergeable_state=clean** against their immediate named bases at this read. Clean does not mean approved, deployed or fully tested together. GitHub's temporary `merge_commit_sha` for these unmerged PRs is not a completed merge.

| PR | Exact head SHA | Base | Current exact-head Actions evidence |
|---|---|---|---|
| [1 PF001](https://github.com/ctmansfield/coach/pull/1) | `1b0ba6faa89c52d2a85452b07339b846b92d1ad0` | main `1dd63725dbed112fc33d9c9a64b60b1d7263c246` | Zero check runs and zero Actions runs at this SHA; prior local 54-pass/7-skip report is separate evidence |
| [2 manual drafts](https://github.com/ctmansfield/coach/pull/2) | `da96f5f91027a746aa4b2ef1bd2c03ff74cdb378` | PF001 | [42370767585](https://github.com/ctmansfield/coach/actions/runs/42370767585), isolated job success |
| [3 offline handoff](https://github.com/ctmansfield/coach/pull/3) | `9fbe9b1580203be78ac8e06ae12dfae9f882c24d` | manual drafts | [42374232872](https://github.com/ctmansfield/coach/actions/runs/42374232872), offline job success |
| [4 manual capture](https://github.com/ctmansfield/coach/pull/4) | `c3c68cfec74e0d65936b16ed3723844872d9cd78` | offline handoff | [42379270713](https://github.com/ctmansfield/coach/actions/runs/42379270713), unit job success |
| [5 browser QA](https://github.com/ctmansfield/coach/pull/5) | `1900d64b4b73706bd0a06871985502b8967f2911` | manual capture | [42446774386](https://github.com/ctmansfield/coach/actions/runs/42446774386), browser-offline job success |
| [6 delivery viewer](https://github.com/ctmansfield/coach/pull/6) | `184606fe9d5022997f09a2e4d6ef38e5dca4a9bc` | browser QA | [42511517020](https://github.com/ctmansfield/coach/actions/runs/42511517020), node and chromium success |

The Checks API independently reports the exact head SHAs above; additional push-triggered checks for PRs 3–6 also succeeded. Legacy commit-status arrays are empty, which must not be interpreted as failure or as proof of passing CI. The inspected latest [delivery workflow](https://github.com/ctmansfield/coach/blob/184606fe9d5022997f09a2e4d6ef38e5dca4a9bc/.github/workflows/i01-delivery-status.yml) runs dedicated status-viewer tests. Success of each increment at its own head is **not a whole-stack rerun at PR 6**, and none exercises the deployed Nightscout status fix.

## 4. Boundaries and prioritized follow-up

1. Reconcile issue chronology with the newer deployment attestation in the eventual coordination record; do not repeat the older comment's blocked-on-status condition as if no subsequent scope result exists.
2. Locate/capture the exact durable status patch, test, image digest, bind manifest and rollback evidence before treating runtime repair as reproducible release work. Keep secrets out of those records.
3. Advance remaining N0 source-capability checks separately from the scope repair; do not infer entries/history qualification from a successful status-only check.
4. Keep PF001/I01 PR review and eventual integration separate from the Nightscout hotfix. Recheck resulting heads and combined behavior if the stacked bases change.

Raw selected metadata is in `gadget_readonly_review_20261114.json`. The direct tags collection URL is unsupported by this connector and `git/refs/tags` returned 404; no broad claim about every tag is made. Default-branch code search returned no Nightscout results despite tracked guides, so the negative source/release conclusion relies on actual tree/file inspection and the branch/PR/release listings instead.
