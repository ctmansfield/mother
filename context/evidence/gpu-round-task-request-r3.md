# Current user steering: scientific GPU first

20 November 2026, Pacific/Guam. Captured from the current visible ChatGPT message; no external message ID was supplied. This supersedes the earlier next action to run E1 literature acquisition.

> Let’s leave the literature download as an open issue and move on. We still need to test the scientific models with the gpu then run the same for the behavioral ones. Let’s run scientific first then continue working on behavioral while we wait for the results.

Authorized work: prepare and execute bounded scientific GPU trials where host access is available, develop and verify the behavioral model benchmark while science runs, then evaluate behavior in sequence. Literature issue #145 is left open and deferred. No credentials, service reconfiguration, source merges or runtime deployments were requested.

Observed access boundary: the SSH client refused before a remote connection because its system proxy configuration has unsuitable owner/permissions. No configuration was changed, and no remote command executed. The current host launch therefore requires the operator to run the provided pinned command from llm.
