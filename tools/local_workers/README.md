# LW-001 — Local Ollama runtime probe

Version: `local-worker-probe/1.0.0`. Python 3.9 or newer; standard library only.
This is a bounded compatibility check before assigning repository work. It
temporarily loads an already-installed model and uses only synthetic prompts.

## Scope

The probe records the serving daemon version, complete installed model digest,
model metadata, requested context/output budgets, host clock/OS/Python metadata,
GPU snapshots, model residency, native timing/token counters, and two bounded
checks:

1. Schema-constrained JSON must preserve a synthetic measurement identity,
   numeric zero, unit, and unknown availability.
2. If the installed model advertises native tools, its response must contain
   the expected structured `message.tool_calls` entry and arguments.

The tool check never executes a generated function or command. The probe does
not pull models, change configuration, restart services, read personal health
records, edit application files, or publish anything. It accepts a loopback
HTTP endpoint only, disables HTTP proxies/redirects, bounds response size and
request duration, and refuses to overwrite an existing report.

## Run on a local Linux installation

```bash
python3 probe.py \
  --model qwen2.5-coder:7b \
  --expected-digest-prefix dae161e27b0e \
  --output lw001-report.json
```

Default endpoint: `http://127.0.0.1:11434`. Use `--url` only if the local daemon
uses another loopback port. The example digest prefix identifies the linked
published artifact. Inspect the intended installed artifact and select its pin
before running. A mismatch or missing model stops before inference. A supplied
prefix must have 12–64 hexadecimal characters; empty or
short pins are rejected. Choose a new report filename on a repeat run.

Each inference request uses `num_ctx=4096`, `num_predict=192`, temperature 0 and
seed 0, with a 60-second request timeout and `keep_alive="2m"`. The model may
remain loaded for up to that retention period after the final request. The
probe does not unload another model or alter server-wide settings. If the
installed artifact advertises no native tool support, that check is explicitly
`not_advertised`; the structured-output result remains separately reported.

The same Python script can be used from Windows with a local Python install,
for example `py -3 probe.py --output lw001-windows-report.json`. Windows execution
has not been verified in this development environment. Its model store/digest
must be inspected independently; the Linux inventory does not establish which
model artifact is installed on Windows. Qualify each intended execution
environment separately and account for shared physical compute resources.

## Interpret the report

`smoke_checks_passed` means the serving API, selected artifact and performed
synthetic checks succeeded. It does not establish coding-agent reliability,
correct repository edits, a functioning remote coordinator, or live physiology
operation. `repository_work_qualified` remains false in every report.

- `structured_output.passed` is an independently checked value/schema result.
- `native_tools.status=call_shape_passed` confirms a parsed synthetic native
  call shape. `not_advertised`, `unknown`, and failure are distinct outcomes.
- `placement_after_generation` reports Ollama's actual resident-model metadata:
  total size, VRAM bytes, context and digest where supplied. On-disk model size
  alone is not a GPU-memory measurement.
- GPU snapshots are observed inventory. An unavailable `nvidia-smi` is recorded
  as unknown and does not become evidence of CPU-only inference.
- API durations are nanoseconds. The reported generation rate uses
  `eval_count * 1e9 / eval_duration`; it is null when those counters cannot
  establish a rate. Cold loading and total client elapsed time remain separate.
- A failed required check returns a nonzero process status and a report naming
  the failed stage. Existing reports are preserved. A Python child process
  returning an error does not close the invoking terminal.

Send the resulting JSON report privately to the project coordinator. It contains
synthetic model responses and limited technical inventory, with no prompts from
physiological records. Keep installation reports out of public commits and
review descriptions. The next gate is the four-task repository
qualification described in `docs/physiology/LOCAL_WORKERS.md`.

## Offline verification

From this directory:

```bash
python3 -m unittest discover -s . -p test_probe.py -v
```

The test suite uses controlled loopback HTTP fixtures and a mocked GPU inventory.
It needs neither Ollama nor a GPU and does not establish behavior on the user's
machine. Report those results separately from the actual installation's JSON.

## Pinned protocol evidence

The probe uses Ollama's native v0.12.0 API, not newer compatibility endpoints:

- [v0.12.0 API documentation](https://github.com/ollama/ollama/blob/v0.12.0/docs/api.md)
- [v0.12.0 request/response types](https://github.com/ollama/ollama/blob/v0.12.0/api/types.go)
- [v0.12.0 server handlers](https://github.com/ollama/ollama/blob/v0.12.0/server/routes.go)
- [v0.12.0 capability detection](https://github.com/ollama/ollama/blob/v0.12.0/server/images.go)
- [Published Qwen2.5-Coder 7B artifact](https://ollama.com/library/qwen2.5-coder:7b)

The tag resolves to Ollama commit
`9f3a37fd36bf1c46cc86a47bc5372535f8ee3547`. Documentation compatibility is source
evidence; only a returned local report can establish this installation's
runtime behavior. A model's advertised tool capability is not itself a passed
native-tool test.
