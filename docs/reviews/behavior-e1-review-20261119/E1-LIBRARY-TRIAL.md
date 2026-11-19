# FW-004.14 — E1 local literature archive, v0.2

Local archive and access queues for the **27 numbered references in Meta-Research Project 001, Draft 0.2 (2026-11-05): 25 journal entries, one preprint and one dataset**. This is not the entire E1 evidence map. [Issue #145](https://github.com/ctmansfield/production-framework/issues/145), [draft PR #149](https://github.com/ctmansfield/production-framework/pull/149).

The unchanged seed contains 25 DOI and 23 PMID values. All 27 primary identifiers were compared with the original document. A supplementary binding retains two source PMCIDs omitted in v0.1: E1-015 PMC3063582 and E1-018 PMC1479766. It records the measured source DOCX hash.

## Verify a reviewed checkout

```bash
bash packages/fw00414/scripts/verify_local.sh
```

This checks manifests, **69 offline tests** and shell syntax, without provider access or external reports. The original v0.1 suite was separately reproduced at 39/39 before changes. Four original test fixtures/assertions were corrected for the new queue, PMCID and XML contracts; 30 new regressions cover the demonstrated defects.

The existing qualification script still requires FW00414_EXPECTED_SHA equal to the reviewed full commit. It now saves reports locally by default. Its existing GitHub issue-comment workflow requires explicit FW00414_POST_REPORT=1.

## Bounded trial on llm

After checking out and verifying the reviewed source:

```bash
python3 -B packages/fw00414/trial.py \
  --root /mnt/nas_storage/research/e1-literature \
  --limit 27 --enable-network --allow-open-access-fulltext
```

The default NAS destination is accepted only when /mnt/nas_storage is actually mounted; a missing mount stops before directory creation. The runner checks one exact identifier for connectivity **before creating an archive**. Failed preflight leaves the archive unchanged. On success it initializes a new archive or verifies an existing one, then attempts up to 27 unattempted references. The dataset follows a separate manual path. The first network failure stops the batch, preserving other entries as unattempted. A local receipt and five distinct queues describe the outcome.

Exit 2 means preflight/processing was held; exit 3 means the batch recorded held references; exit 0 means processing finished, not that all articles were obtained. Actual files and hashes establish download counts. A network timeout does not identify paywalled articles.

Connection check alone:

```bash
python3 -B packages/fw00414/library.py preflight --enable-network --ref-id E1-001
```

## Identity and retrieval

Exact DOI/PMID requests use the fixed Europe PMC REST endpoint. Every identifier supplied by the source must agree, including the two original PMCIDs. A matching DOI cannot override a contradictory PMID. Source/provider title differences become review records; comparison normalizes case, punctuation, markup and Greek-letter transliterations used in the source. Bounded raw metadata, request URL, UTC time, seed hash and collector hash are preserved even when identity/title is held.

Optional XML retrieval requires OA metadata, a PMCID and a recognized CC license. XML identity is checked under the main article's front/article-meta, accepting both pmc and pmcid identifier forms. Ordinary external JATS DOCTYPE declarations are accepted without loading DTDs. Internal subsets, entities and external expansion are refused. DOI/PMID values present in XML must also match. A missing or empty article body is held, rather than counted as archived full text. Retraction flags cause a hold; absence of a flag is not a comprehensive retraction check.

Automatic retrieval here is **OA XML**. Operator-downloaded PDFs can be imported. A future PDF adapter should use current supported repository APIs with identity and rights metadata. No university login is automated.

## Storage and queues

The owner-only archive uses records/ for immutable attempts and raw metadata, fulltext/ for OA XML, pdf/ for manual PDFs, imports/ for import hashes, and queues/ for CSV reports. Article bytes remain local.

| Output | Meaning |
|---|---|
| Requested CSV filename | Provider reports non-OA; university access candidate |
| *.review.csv | Unchecked entries and identity/title/license/validation/integrity review |
| *.retry.csv | Observed connectivity failures awaiting explicit retry |
| *.oa_pending.csv | OA metadata verified, full text not yet requested |
| *.dataset.csv | Related dataset, separate from journal requests |

Validated archived XML and imported PDFs disappear from pending queues. Missing or changed imported files become integrity review. The university CSV may be empty. Non-OA provider status does not prove university coverage or rule out other lawful OA copies.

```bash
python3 -B packages/fw00414/library.py queue \
  --root /mnt/nas_storage/research/e1-literature \
  --output /mnt/nas_storage/research/e1-literature/queues/access-review-001.csv
```

Use a new output filename; prior reports are preserved.

## Recovery and manual import

For a recorded transient/validation failure or an OA entry initially checked without full-text opt-in:

```bash
python3 -B packages/fw00414/library.py retry \
  --root /mnt/nas_storage/research/e1-literature --ref-id E1-001 \
  --enable-network --allow-open-access-fulltext
```

Retry appends a numbered, hash-linked receipt and preserves original metadata and events. Completed archives and source-review states are refused. Resolve identity/title discrepancies deliberately.

After obtaining and matching a PDF through university access:

```bash
python3 -B packages/fw00414/library.py import-pdf \
  --root /mnt/nas_storage/research/e1-literature \
  --ref-id E1-023 --file /path/to/verified-article.pdf
```

Replace the illustrative file path. The import validates framing and hashes the content; the operator establishes the article match and applicable institutional permission. The receipt explicitly labels reference identity as operator assigned, not independently verified. Re-run queue with a new name to reflect the import. Credentials stay in the university session. Full text is not sent to GitHub or external model providers.

## Evidence boundary

The 69 tests are synthetic source qualification. Host/provider retrieval, actual paper availability and comprehensive retraction/version checking remain separate evidence. This package does not run models, change production services, appraise every article or promote scientific claims. E1 remains the project's working premise.
