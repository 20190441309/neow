# Neow VS Code Extension

Official Visual Studio Code extension for [Neow](https://github.com/20190441309/neow) - the AI pair programmer that lives in your terminal and IDE.

---

## ✨ Features

- **Integrated Pair Programming Chat**: Chat with Neow directly inside VS Code's sidebar.
- **Interactive Tool Approvals**: Seamless modal or notification dialogs for dangerous commands and file edits.
- **Context-Aware Commands**: Right-click on any selected code block to **Explain Selection** or **Fix Selection**.
- **Real-Time Streaming**: Watch thinking reasoning and assistant replies stream in real-time.
- **Surgical Edits**: Powered by Neow's hashline content-addressable edits and atomic Git commits.

---

## 🚀 Getting Started

### 1. Prerequisites

Ensure `neow` CLI is installed and configured in your environment:

```bash
pip install -e .
neow  # Run once to set up your BYOK model or API keys
```

### 2. Extension Configuration

Configure the extension in your VS Code `settings.json`:

```json
{
  "neow.executablePath": "neow",
  "neow.approvalMode": "interactive",
  "neow.model": "auto"
}
```

- `neow.executablePath`: Path to the `neow` CLI executable (defaults to `neow` on PATH).
- `neow.approvalMode`: Set to `interactive` (asks permission via dialogs) or `yolo` (auto-approves tools).
- `neow.model`: Override the model (e.g. `claude`, `deepseek`, `gpt`, or `auto` for adaptive routing).

---

## 🛠️ Protocol & Architecture

The extension bridges VS Code and Neow CLI using the standard `--output-format stream-json --approval-interactive` protocol:

```
VS Code Extension                         Neow CLI
       |                                      |
       |--- spawn(neow -p "..." stream-json)->|
       |<-- {"type": "reasoning_delta"}-------|
       |<-- {"type": "content_delta"}---------|
       |<-- {"type": "approval_request"}------|
       |                                      |
       |  (User clicks "Allow Once")          |
       |--- stdin: {"id": 1, "approve": true}-|
       |                                      |
       |<-- {"type": "result"}----------------|
```
