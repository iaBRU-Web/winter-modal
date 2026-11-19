# Winter Frost on Modal

Deploy `brucoder/winter-frost-4.6` as an OpenAI-style API on Modal.

## Files
- `colab_modal_cpu_deploy.py`: CPU version (GGUF + llama.cpp). Slow, no GPU.
- `colab_modal_deploy.py`: GPU version (vLLM on an L4). Needs a payment method on Modal.

## How to run
1. Open a new Google Colab notebook.
2. Paste the whole file you want into ONE cell and run it.
3. Paste your keys in the password boxes when asked:
   - Modal Token ID (`ak-...`) and Token Secret (`as-...`) from modal.com > Settings > API Tokens
   - A model API key (press Enter to auto-generate)
   - An HF token only if your model is private
4. Copy the printed URL and API key somewhere private.

## Safety
The files contain NO keys. Never paste tokens into the code, commit them, or share them.
If a token leaks, delete it in the Modal or Hugging Face dashboard and create a new one.
