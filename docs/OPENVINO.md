# Local bouquet interpretation on Windows

OpenVINO runs Qwen3-VL 4B Instruct INT4 in the existing offer worker on Windows x64.
The model receives one prepared photo per call and the existing seller-bounded
conversation context. The offer graph still limits original chunks to two and
records additional photos as unprocessed. Output must pass the same Pydantic,
source-evidence and publication gates as hosted output. The runtime and model
revision are pinned. Model weights and compiled data belong outside Git.

From the repo root, install the locked extra and download the pinned OpenVINO
IR export from the official model repository. The first run loads the model
and compiles it for the selected device.

```powershell
uv sync --project apps/api --frozen --extra browser --extra local-model
hf download OpenVINO/Qwen3-VL-4B-Instruct-int4-ov --revision 3ffb805d532a250e5010c5aa5ce6579e60b31d71 --local-dir .data/models/Qwen3-VL-4B-Instruct-int4-ov
```

Set these values in the ignored root `.env` and restart the API and offer worker.
Use the actual absolute path to the downloaded directory.

```dotenv
MODEL_PROVIDER=openvino
EXTRACTION_PROVIDER=rules
OPENVINO_MODEL_DIR=D:/Flowery/.data/models/Qwen3-VL-4B-Instruct-int4-ov
OPENVINO_DEVICE=GPU
```

For a CPU trial, explicitly set `OPENVINO_DEVICE=CPU`. GPU and CPU have distinct
model identities. To process evidence previously queued with another provider
or device, use Studio to reprocess the candidate with the current configuration.
See [local operations](LOCAL-RECURRING-OPERATIONS.md) for worker commands. A
failed local call has a diagnostic receipt and requires explicit replay. The
provider incurs zero API spending and keeps the same retention and audit path.
The worker needs room for the weights, image encoding, and generation state.
Cold-load time and warm latency should be measured separately. A successful
smoke test leaves flower-label quality and release approval to the pilot proofs.
