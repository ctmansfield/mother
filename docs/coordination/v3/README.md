# Worker v3 migration — 2026-11-21

Explicit user request: save all eight worker contexts and launch v3 replacements in waves. All eight predecessor handoffs were saved. V2 chats are preserved on standby; no thread was deleted or archived. PM published NICKY's sanitized handoff after its predecessor saved locally.

Controlling boundary: [MSE-ALL-ZIP-DATA-20261121-07 revision 2](https://github.com/ctmansfield/mother/pull/23#issuecomment-7060675355). Every personal-data operation is user-run only, including metadata, preflight, admissions, verification and cleanup. Worker work is source/docs and ordinary fabricated functional tests in isolated development; no live/adversarial probing or alert workarounds. Backups/restores remain deferred.

Each pair launches only after the preceding pair completes handoff intake. Readiness is separate from implementation, independent qualification or manual release. Candidate at intake: Mother PR65 `80cdb29d33b5627e9f7552e867065e131764ede4`; full universal acceptance and manual pipeline remain pending.

| Wave | Worker | Saved handoff | New chat ID |
|---|---|---|---|
| 1 | ATLASv3 | [Operating and state blocks](https://github.com/ctmansfield/mother/blob/cee8de8168cd6c70d5ac7f24bf53983cf6d293f5/docs/mse/integration/ATLAS_V3_HANDOFF_2026-11-21.md) | `01a1fd7b-3e34-7833-9392-bca50d2dc932` |
| 1 | ORACLEv3 | [Operating and state blocks](https://github.com/ctmansfield/mother-health-bridge/tree/778a9ef614c022d17f30348aa6d3439a6fd73b10/context/handoffs/oracle-v3) | `01a1fd7b-3f19-72f0-9873-dc5092c64452` |
| 2 | SENTINELv3 | [Operating and state blocks](https://github.com/ctmansfield/mother/blob/21c2570ac382c616e62e35e2d20cb05f434be83b/docs/mse/integration/SENTINEL_V3_HANDOFF.md) | `01a1fd7d-3c5e-72d2-a9d1-483184ae7def` |
| 2 | PROVENANCEv3 | [Operating and state blocks](https://github.com/ctmansfield/mother/blob/aa6b929c3bd0360fa8bf72dc1e6a4f787d668a27/docs/mse/integration/PROVENANCE_V3_HANDOFF.md) | `01a1fd7d-3d79-7740-97b0-e3e7a012a86b` |
| 3 | FORGEv3 | [Operating and state blocks](https://github.com/ctmansfield/mother/blob/f79bdca5ccc8944f68f2ab84b1f60041cd51f0df/docs/mse/integration/FORGE_V3_HANDOFF.md) | `01a1fd7e-cd71-77b2-a268-65fb169265cb` |
| 3 | PHOENIXv3 | [Operating and state blocks](https://github.com/ctmansfield/mother/blob/9c47147fe27f25c71e3f4ea78a872a1051f9f78f/tools/mse_integration/recovery/health_history_vault/PHOENIX_V3_HANDOFF.md) | `01a1fd7e-ceb1-7130-b323-be09fba3c0af` |
| 4 | NICKYv3 | [Operating and state blocks](https://github.com/ctmansfield/mother/blob/0353986/docs/coordination/v3/NICKY_V3_HANDOFF.md) | `01a1fd80-7ed2-7352-8695-74c7772f3c38` |
| 4 | LONESTARv3 | [Operating and state blocks](https://github.com/ctmansfield/mother/blob/7ebe3c8f3d64247d542229114ec2884480553e0e/docs/mse/integration/LONESTAR_V3_HANDOFF.md) | `01a1fd80-7ffd-7f12-89e0-ed8fcf77d99e` |

The adjacent machine-readable registry routes future assignments to v3. Old evidence remains valid only within its recorded scope; original runtime knowledge is historical and must not be refreshed by automated personal-data or live-system inspection. Predecessors must not receive new work. Missing task capsules in some old branches were explicitly reported during intake; their current directive and pinned handoff remain the documented fallback, not authority inferred from a reader hash.


All eight replacements completed V3_READY and acknowledged revision 2 before PM activation. Activation dispatches are delivered; subsequent implementation results are separate. All v2 predecessors remain preserved on standby.
