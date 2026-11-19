# =====================================================================
#  WINTER FROST -> MODAL (CPU ONLY, NO GPU)  |  ONE CELL, RUN IT ONCE
#  Paste this whole thing into ONE Colab cell and press Play.
#  Same 4 password boxes as before:
#    1) Modal Token ID (ak-...)
#    2) Modal Token Secret (as-...)
#    3) Your model API key (Enter = auto-generate)
#    4) HF token (Enter if your model is public)
#
#  How it works:
#   - Modal builds a CPU image with llama.cpp inside (first build is slow).
#   - On the first request, it downloads your model from Hugging Face,
#     converts it to GGUF (q8_0) and saves it on a Modal disk.
#   - After that it serves an OpenAI-style API on CPU.
#   - It shuts down when idle, so you pay only while it runs.
# =====================================================================

import os, subprocess, secrets, re
from getpass import getpass

MODEL_REPO = "brucoder/winter-frost-4.6"
MODEL_NAME = "winter-frost-4.6"

print("=" * 60)
print("Paste your keys in the boxes below (nothing shows as you type)")
print("=" * 60)
modal_id = getpass("1) Modal Token ID (ak-...): ").strip()
modal_secret = getpass("2) Modal Token Secret (as-...): ").strip()
api_key = getpass("3) Your model API key (Enter = auto-generate): ").strip()
hf_token = getpass("4) HF token (only if a model is private, else Enter): ").strip()

if not modal_id.startswith("ak-") or not modal_secret.startswith("as-"):
    raise SystemExit("Token ID must start with ak- and Token Secret with as-.")

if not api_key:
    api_key = secrets.token_urlsafe(32)
    print("\nGenerated API key (SAVE THIS, your gateway needs it):\n", api_key)

env = {**os.environ, "MODAL_TOKEN_ID": modal_id, "MODAL_TOKEN_SECRET": modal_secret}

server_code = '''
import os, subprocess
import modal

MODEL_REPO = "__MODEL_REPO__"
MODEL_NAME = "__MODEL_NAME__"
GGUF_PATH = "/models/model-q8_0.gguf"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("build-essential", "cmake", "git")
    # CPU-only torch (needed only for the one-time GGUF conversion)
    .pip_install("torch", index_url="https://download.pytorch.org/whl/cpu")
    .pip_install("transformers", "sentencepiece", "protobuf", "numpy",
                 "huggingface_hub")
    .run_commands(
        "git clone --depth 1 https://github.com/ggml-org/llama.cpp /opt/llama.cpp",
        "pip install /opt/llama.cpp/gguf-py",
    )
    # NATIVE=OFF so the build works on whatever CPU Modal gives us later
    .env({"CMAKE_ARGS": "-DGGML_NATIVE=OFF"})
    .pip_install("llama-cpp-python[server]")
)

models = modal.Volume.from_name("wf-cpu-models", create_if_missing=True)
app = modal.App("winter-frost-cpu")


def prepare_model():
    """Download from HF and convert to GGUF once, then reuse from the disk."""
    if os.path.exists(GGUF_PATH):
        return
    from huggingface_hub import snapshot_download
    os.makedirs("/models", exist_ok=True)
    print("Downloading model from Hugging Face...", flush=True)
    src = snapshot_download(MODEL_REPO, local_dir="/models/hf-src",
                            token=os.environ.get("HF_TOKEN") or None)
    print("Converting to GGUF (q8_0)...", flush=True)
    subprocess.run([
        "python", "/opt/llama.cpp/convert_hf_to_gguf.py", src,
        "--outfile", GGUF_PATH, "--outtype", "q8_0",
    ], check=True)
    models.commit()
    print("Model ready.", flush=True)


@app.function(
    image=image,
    cpu=4.0,
    memory=8192,
    scaledown_window=300,
    timeout=3600,
    volumes={"/models": models},
    secrets=[modal.Secret.from_name("winter-frost-secrets")],
)
@modal.concurrent(max_inputs=4)
@modal.web_server(port=8000, startup_timeout=1800)
def serve():
    prepare_model()
    subprocess.Popen([
        "python", "-m", "llama_cpp.server",
        "--model", GGUF_PATH,
        "--model_alias", MODEL_NAME,
        "--host", "0.0.0.0", "--port", "8000",
        "--api_key", os.environ["MODEL_API_KEY"],
        "--n_ctx", "4096",
        "--n_threads", "4",
    ])
'''
server_code = (server_code.replace("__MODEL_REPO__", MODEL_REPO)
                          .replace("__MODEL_NAME__", MODEL_NAME))
with open("modal_server_cpu.py", "w") as f:
    f.write(server_code)
print("\n[1/4] modal_server_cpu.py written")


def run(cmd, show=True):
    p = subprocess.Popen(cmd, shell=True, env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True)
    out = ""
    for line in p.stdout:
        out += line
        if show:
            print(line, end="")
    p.wait()
    return p.returncode, out

print("\n[2/4] Installing Modal...")
run("pip install -q -U modal", show=False)

print("\n[3/4] Saving your API key inside Modal...")
secret_cmd = f"modal secret create winter-frost-secrets MODEL_API_KEY='{api_key}'"
if hf_token:
    secret_cmd += f" HF_TOKEN='{hf_token}'"
code, out = run(secret_cmd + " --force", show=False)
print("Secret saved." if code == 0 else out[-1500:])

print("\n[4/4] Deploying. The first build can take 5-10 minutes (it compiles llama.cpp).")
print("Only the LAST lines matter if it fails.\n")
code, out = run("modal deploy modal_server_cpu.py", show=False)
print(out[-2500:])
if code != 0:
    raise SystemExit("\nDeploy failed. Paste the last lines above (keys removed) to Claude.")

urls = re.findall(r"https://[^\s]+\.modal\.run", out)
url = urls[-1] if urls else None
print("\n" + "=" * 60)
print("DONE. Your server URL:", url or "(look for the .modal.run link above)")
print("Your API key:", api_key)
print("=" * 60)

if url:
    import requests
    print("\nTesting. The FIRST call downloads and converts the model, so it can")
    print("take 5-15 minutes. If it times out, just run the test again.\n")
    try:
        r = requests.post(
            url.rstrip("/") + "/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": MODEL_NAME,
                  "messages": [{"role": "user", "content": "What is your name?"}],
                  "max_tokens": 80},
            timeout=1800,
        )
        print(r.status_code, r.text[:1000])
    except Exception as e:
        print("Test timed out or failed:", e)
        print("Run the test again in a few minutes. The model may still be converting.")
