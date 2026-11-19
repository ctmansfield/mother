# Native scientific GPU screens

**Prepared, locally tested source; no host model inference has been run by this preparation.** These commands extend the scientific round beyond the five Ollama language models. They use existing host environments and cached assets. They do not install packages, download weights, access a Hugging Face account, post reports, or activate model roles.

| Engine | Prepared experiment | Evaluation scope |
|---|---|---|
| MedCPT Query + Article encoders | Four synthetic queries over eight fictional article snippets, including four close negatives | Retrieval rank, hit at one, reciprocal rank, positive versus close negative, and a lexical overlap baseline |
| `google/txgemma-9b-chat` | The same 15 protected FW00412 cases, order, seeds and grader as the Ollama screen | Scientific evidence boundaries and output protocol under the native chat template |
| Boltz 2 | Inspect one local checkpoint cache only | File presence, without weight identity, input validation or structure inference claims |
| TimesFM | Check whether its previously declared Python environment exists | No forecast inference adapter or model validation in this package |

MedCPT is a retriever and does not receive chat questions requiring JSON answers. Its two encoders use the final hidden state at the CLS position, followed by raw inner-product ranking. These are the interfaces described in the [NCBI query model card](https://huggingface.co/ncbi/MedCPT-Query-Encoder), [article model card](https://huggingface.co/ncbi/MedCPT-Article-Encoder), and [NCBI retrieval example](https://github.com/ncbi/MedCPT). The four relevance labels are authored synthetic expectations, not real study findings or an independent scientific benchmark. The aggregate `positive_over_hard_negative_count` counts queries where the relevant article scores strictly above its close negative; ties do not count.

TxGemma uses the [Google model card's conversational template](https://huggingface.co/google/txgemma-9b-chat). Its fixed snapshot is `bc45665ceb345eea6acfc44d82706e8d8b689209`. The native run uses bfloat16, SDPA attention, greedy decoding and at most 520 generated tokens per case. It does not have Ollama's `format=json` constraint. Scores retain that runtime/protocol difference; they should not be presented as a controlled model-only ranking against quantized Ollama candidates.

## Readiness first

From this directory in the reviewed MOTHER checkout:

```bash
sha256sum -c SHA256SUMS
python3 -B native_science.py inspect
```

Inspection does not import model runtimes, load weights, initialize CUDA, or contact a provider. It resolves the existing MedCPT cache's `refs/main`, or the only local snapshot if there is no saved ref. Multiple unpinned snapshots are refused. It requires the exact TxGemma snapshot above. Missing tokenizer files and indexed weight shards are reported as held.

The default Hugging Face cache is `/mnt/llmstore/caches/hf/chad/hub`. The Boltz inspection defaults to `~/.boltz`, inspecting checkpoint candidates to a depth of three directories. If the existing installation uses another known cache, provide `--boltz-cache /absolute/existing/path`. Absence in this one path does not establish absence elsewhere on the host. No Boltz download or inference command is issued.

## Run the native scientific screens serially

Wait for the Ollama scientific screen to finish and inspect its exit and any hold reason before starting another GPU experiment. Use the existing virtual environments:

```bash
"$HOME/ai-envs/medcpt/bin/python" -B native_science.py medcpt
```

For TxGemma, use the clean framework checkout printed by the scientific runner under its attempt directory. The program requires exact commit `ba6fbb90c031f122b7db61d2f67f2b22ef1cf130`, clean Git status, the original manifests, inherited source blobs, and the benchmark's frozen source/graph fingerprints:

```bash
"$HOME/ai-envs/txgemma/bin/python" -B native_science.py txgemma \
  --source /absolute/path/to/scientific-attempt/framework
```

The program prints a new private evidence directory for every attempt under `~/.local/state/mother-native-science/`. An existing attempt is never reused. A missing environment, unsupported CUDA/bfloat16, unavailable asset, load error or memory error is a recorded failure; the program does not substitute a different model, CPU offload, precision, or environment.

## Execution and evidence

The controller holds the same cooperative `mother-fw00412/scientific-gpu.lock` used by the Ollama screen. It requires no loaded Ollama models and no NVIDIA compute processes before launch. Its loopback idle check ignores proxy settings and rejects redirects. During execution it samples NVIDIA processes and stops its own worker if a foreign process appears. This lock coordinates these scripts; it does not reserve the host scheduler or prevent another application from starting GPU work between samples.

The worker uses explicit local snapshot paths with `local_files_only=True`, `trust_remote_code=False`, and the [documented Hugging Face offline settings](https://huggingface.co/docs/transformers/installation#offline-mode). Every selected config, tokenizer and weight file is hashed before load. Snapshot links are checked again before load and at the end, together with file size, modification time and inode. The closing check is not a second complete weight hash. Cached PyTorch binary weights require an existing PyTorch version of at least 2.6 and weights-only loading; safetensors are preferred. TxGemma requires its cached safetensors.

CUDA availability alone is not a successful GPU result. The recorded proof includes all model parameter/buffer devices, input tensor devices, output tensor devices, synchronized CUDA completion, peak allocated/reserved memory, package versions and NVIDIA process/device observations. CPU placement is refused. MedCPT performs two bounded encoder forward calls and scores their embeddings on CUDA. TxGemma performs at most 15 generate calls. No warmup, retry, repair prompt, grade feedback, model training or scientific promotion is performed.

The parent process watches deadlines and can terminate only the child process group it created. Each encoder forward has a 120-second deadline. A TxGemma generate phase has a 125-second parent deadline and a 120-second Transformers generation time limit. A currently running bounded NVIDIA monitor command can add a short delay to a parent deadline. Asset hashing and loading have separate recorded limits; total limits are 1,500 seconds for MedCPT and 3,300 seconds for TxGemma. SIGINT, SIGTERM and SIGHUP cleanup preserves earlier records and stops the owned worker. An operating-system forced kill cannot provide that cleanup guarantee.

The evidence directory contains the request, worker log, phase/attempt events, runtime/device provenance, hashed asset manifests, NVIDIA observations, final supervisor status, and either a summary or failure record. TxGemma also preserves every completed raw response with prompt and response hashes. Abruptly interrupted generations remain visible in `attempts.jsonl` even when no answer is available. Exit zero means the bounded screen completed, regardless of its correctness score; it does not mean every answer was correct or that the scientific stack is qualified.

## Offline verification

```bash
python3 -B -m unittest -v test_native_science.py
```

The focused tests cover ambiguous caches, missing shards, snapshot symlinks, asset changes, source pin/cleanliness, hidden retrieval labels, rank ties, nonfinite scores, CPU-placement rejection and inspection without GPU/model access. Model loader compatibility, actual GPU memory fit, inference behavior and runtime performance still require the host run.
