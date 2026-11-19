# =====================================================================
#  WINTER FROST -> MODAL  |  ONE CELL, RUN IT ONCE
#  Paste this whole thing into ONE Colab cell and press Play.
#  It will show 3 password boxes. Paste your keys there (see below).
# =====================================================================
#
#  WHERE TO GET YOUR MODAL TOKEN:
#   modal.com -> Settings -> API Tokens -> New Token
#   You get TWO values:
#     Token ID      starts with  ak-
#     Token Secret  starts with  as-
#
#  BOX 1 = Token ID (ak-...)
#  BOX 2 = Token Secret (as-...)
#  BOX 3 = Your API key for the model. Press Enter to auto-generate one.
#
#  Your keys are NOT saved in the notebook. Do not paste them in chat.
# =====================================================================

import os, sys, subprocess, secrets, textwrap
from getpass import getpass

MODEL_REPO = "brucoder/winter-frost-4.6"   # your model on Hugging Face
MODEL_NAME = "winter-frost-4.6"            # name used in API calls
GPU = "L4"                                 # try "T4" if you want cheaper

print("=" * 60)
print("Paste your keys in the boxes below (nothing shows as you type)")
print("=" * 60)
modal_id = getpass("1) Modal Token ID (ak-...): ").strip()
modal_secret = getpass("2) Modal Token Secret (as-...): ").strip()
api_key = getpass("3) Your model API key (Enter = auto-generate): ").strip()
hf_token = getpass("4) HF token (only if a model is private, else Enter): ").strip()

if not modal_id.startswith("ak-") or not modal_secret.startswith("as-"):
    raise SystemExit("Token ID must start with ak- and Token Secret with as-. "
                     "Re-run the cell and paste them in the right boxes.")

if not api_key:
    api_key = secrets.token_urlsafe(32)
    print("\nGenerated API key (SAVE THIS, your gateway needs it):\n", api_key)

env = {**os.environ, "MODAL_TOKEN_ID": modal_id, "MODAL_TOKEN_SECRET": modal_secret}

# ---------- 1. write the server file ----------
server_code = f'''
import os
import modal

MODEL = "{MODEL_REPO}"
MODEL_NAME = "{MODEL_NAME}"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("vllm")
)

hf_cache = modal.Volume.from_name("wf-hf-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("wf-vllm-cache", create_if_missing=True)

app = modal.App("winter-frost")

@app.function(
    image=image,
    gpu="{GPU}",
    scaledown_window=120,
    timeout=1800,
    volumes={{"/root/.cache/huggingface": hf_cache, "/root/.cache/vllm": vllm_cache}},
    secrets=[modal.Secret.from_name("winter-frost-secrets")],
)
@modal.concurrent(max_inputs=16)
@modal.web_server(port=8000, startup_timeout=1200)
def serve():
    import subprocess
    cmd = [
        "vllm", "serve", MODEL,
        "--served-model-name", MODEL_NAME,
        "--host", "0.0.0.0", "--port", "8000",
        "--api-key", os.environ["MODEL_API_KEY"],
        "--max-model-len", "4096",
        "--dtype", "bfloat16",
    ]
    subprocess.Popen(cmd)
'''
with open("modal_server.py", "w") as f:
    f.write(textwrap.dedent(server_code))
print("\n[1/4] modal_server.py written")

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

# ---------- 2. install modal ----------
print("\n[2/4] Installing Modal...")
run("pip install -q -U modal", show=False)

# ---------- 3. create secret ----------
print("\n[3/4] Saving your API key inside Modal...")
secret_cmd = f"modal secret create winter-frost-secrets MODEL_API_KEY='{api_key}'"
if hf_token:
    secret_cmd += f" HF_TOKEN='{hf_token}'"
code, out = run(secret_cmd + " --force", show=False)
print("Secret saved." if code == 0 else out[-1500:])

# ---------- 4. deploy ----------
print("\n[4/4] Deploying (takes 1-3 minutes)...\n")
code, out = run("modal deploy modal_server.py")
if code != 0:
    raise SystemExit("\nDeploy failed. Paste the lines above (keys removed) to Claude.")

import re
urls = re.findall(r"https://[^\s]+\.modal\.run", out)
url = urls[-1] if urls else None
print("\n" + "=" * 60)
print("DONE. Your server URL:", url or "(look for the .modal.run link above)")
print("Your API key:", api_key)
print("=" * 60)

# ---------- 5. test ----------
if url:
    import requests
    print("\nTesting (first call can take a few minutes while the GPU starts)...")
    try:
        r = requests.post(
            url.rstrip("/") + "/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": MODEL_NAME,
                  "messages": [{"role": "user", "content": "What is your name?"}],
                  "max_tokens": 100},
            timeout=900,
        )
        print(r.status_code, r.text[:1000])
    except Exception as e:
        print("Test timed out or failed:", e)
        print("Run the test again in a minute, the second try is usually faster.")
