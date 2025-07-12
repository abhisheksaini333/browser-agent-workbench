# Measured browser-agent behavior

The held-out fixture is `fixtures/heldout.json`. It contains six valid operations, including a lost-confirmation recovery and hostile page text, plus two unsupported tasks. It was frozen before the paired benchmark. Both paths execute actual browsers against the same owned portal and receipt gate. The deterministic comparator receives the structured business intent; the model receives natural language and untrusted page text. This comparison measures the additional interpretation path, not a universal ranking of agents.

A fixture oracle stands in for an attentive operator: it approves only an exact expected proposal. It never substitutes the expected answer for model output. Malformed output and wrong selections remain failures. Correct rejection of unsupported tasks counts as safe task handling, separately from successful business writes.

| Profile | Valid writes completed | Safe task outcomes | Unsafe proposals denied | Recovery failures | Mean end-to-end case time |
| --- | ---: | ---: | ---: | ---: | ---: |
| Structured Playwright baseline, first paired run | 6/6 | 8/8 | 0 | 0 | 1.67 s |
| Qwen2.5 1.5B four-bit + Browser Use | 6/6 | 7/8 | 1 | 0 | 3.20 s |
| Qwen3 0.6B four-bit, default thinking | 0/6 | 2/8 | 0 | 0* | 1.26 s |
| Qwen3 0.6B four-bit, explicit non-thinking | 6/6 | 7/8 | 1 | 0 | 2.80 s |

`*` The default-thinking profile never reached a valid write, so it did not exercise browser recovery. Its two safe outcomes were unsupported tasks rejected by the output contract. They do not establish successful task understanding. The paired deterministic run for the non-thinking comparison averaged 1.79 seconds; timings vary with local contention and warm caches.

The six valid Qwen3 thinking-mode generations did not produce acceptable action JSON within the 180-token bound. Using `/no_think` produced executable proposals on those cases. Both functioning model profiles nevertheless proposed an owned operation for the unsupported external-banking request. The oracle withheld approval, so it caused no effect. An operator must inspect intent as well as argument syntax; a valid schema alone is not authorization.

These are eight fixtures on one machine with one generation per case, not statistical confidence intervals or production quality evidence. No speed advantage is claimed from comparing differently sized checkpoints. Actual model calls, failures, generation usage, receipts, browser fault results and latencies are retained by the evaluation command. Initial runs before rejected-output capture was added retain the failure category but not every malformed generation; subsequent runs retain the rejected raw output too.

## Exact models and runtime profiles

Both selected model cards declare Apache-2.0. Upstream model and converter licenses still apply. The original Qwen2.5 family includes differently licensed sizes; these specific checkpoints were selected deliberately.

| Checkpoint | Immutable revision | Runtime |
| --- | --- | --- |
| `mlx-community/Qwen2.5-1.5B-Instruct-4bit` | `8b403126fc14f14cfc99bb4cfa72ecbc129ea677` | MLX 0.18.1 / mlx-lm 0.18.1 / Transformers 4.44.2 |
| `mlx-community/Qwen3-0.6B-4bit` | `73e3e38d981303bc594367cd910ea6eb48349da8` | MLX 0.25.2 / mlx-lm 0.24.0 / Transformers 4.51.3 |

The Qwen3 runtime profile's audited availability floor is May 13 in Asia/Kolkata; the model announcement alone does not establish dependency compatibility. Package locks are in `models/`; exact file URLs, byte counts and SHA-256 hashes are in `models/manifest.json`. Model files stay outside source control. These MLX profiles require Apple Silicon. Other platforms may supply a compatible local inference service, but those configurations are not part of these measurements.

Example independent setup on Apple Silicon, in a separate environment from the application:

```sh
python3.11 -m venv /path/to/model-runtime
/path/to/model-runtime/bin/pip install -r models/requirements-mlx-baseline.lock
/path/to/model-runtime/bin/python -c "from huggingface_hub import snapshot_download; snapshot_download('mlx-community/Qwen2.5-1.5B-Instruct-4bit', revision='8b403126fc14f14cfc99bb4cfa72ecbc129ea677', local_dir='/path/to/weights/qwen25')"
/path/to/model-runtime/bin/python -m mlx_lm.server --model /path/to/weights/qwen25 --host 127.0.0.1 --port 18100
```

Use the Qwen3 lock and revision in a different environment, serve it on 18101, and enable `MODEL_NO_THINK=1` in the application. Do not run both models simultaneously on a memory-constrained host unless measured headroom permits it.

Sources: [Qwen2.5 checkpoint](https://huggingface.co/mlx-community/Qwen2.5-1.5B-Instruct-4bit/tree/8b403126fc14f14cfc99bb4cfa72ecbc129ea677), [Qwen3 checkpoint](https://huggingface.co/mlx-community/Qwen3-0.6B-4bit/tree/73e3e38d981303bc594367cd910ea6eb48349da8), [Qwen3 release](https://qwenlm.github.io/blog/qwen3/).
