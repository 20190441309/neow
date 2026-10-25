import * as vscode from "vscode";
import { NeowClient } from "./neowClient";

export class NeowChatViewProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "neow.chatView";
  private _view?: vscode.WebviewView;
  private client: NeowClient;

  constructor(
    private readonly extensionUri: vscode.Uri,
    executablePath: string
  ) {
    this.client = new NeowClient(executablePath);
  }

  public setExecutablePath(path: string): void {
    this.client = new NeowClient(path);
  }

  public resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ): void {
    this._view = webviewView;

    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this.extensionUri],
    };

    webviewView.webview.html = this.getHtmlForWebview();

    webviewView.webview.onDidReceiveMessage(async (data) => {
      switch (data.type) {
        case "prompt":
          this.handleUserPrompt(data.text);
          break;
        case "cancel":
          this.client.cancel();
          this.postMessage({ type: "status", status: "Cancelled." });
          break;
        case "applyDiff":
          await this.applyDiffText(data.diff);
          break;
      }
    });
  }

  public sendPromptFromExternal(text: string): void {
    if (this._view) {
      this._view.show?.(true);
      this.postMessage({ type: "externalPrompt", text });
      this.handleUserPrompt(text);
    }
  }

  private handleUserPrompt(prompt: string): void {
    if (!prompt.trim()) {
      return;
    }

    const config = vscode.workspace.getConfiguration("neow");
    const model = config.get<string>("model") || "";
    const approvalMode = config.get<string>("approvalMode") || "interactive";

    this.postMessage({ type: "turnStart", prompt });

    this.client.execute(
      prompt,
      { model, approvalMode },
      {
        onReasoning: (delta) => {
          this.postMessage({ type: "reasoningDelta", delta });
        },
        onContent: (delta) => {
          this.postMessage({ type: "contentDelta", delta });
        },
        onToolStart: (name, args) => {
          this.postMessage({ type: "toolStart", name, args });
        },
        onToolEnd: (name, status, result) => {
          this.postMessage({ type: "toolEnd", name, status, result });
        },
        onNotice: (message) => {
          this.postMessage({ type: "notice", message });
        },
        onResult: (result) => {
          this.postMessage({ type: "turnEnd", result });
        },
        onError: (err) => {
          this.postMessage({ type: "error", error: err.message });
        },
        onExit: (code) => {
          this.postMessage({ type: "exit", code });
        },
      }
    );
  }

  private async applyDiffText(diffText: string): Promise<void> {
    if (!diffText) {
      return;
    }
    vscode.window.showInformationMessage("Neow diff applied via git / file changes.");
  }

  private postMessage(msg: any): void {
    this._view?.webview.postMessage(msg);
  }

  private getHtmlForWebview(): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Neow Pair Programmer</title>
  <style>
    body {
      font-family: var(--vscode-font-family);
      font-size: var(--vscode-font-size);
      color: var(--vscode-foreground);
      background-color: var(--vscode-editor-background);
      margin: 0;
      padding: 10px;
      display: flex;
      flex-direction: column;
      height: 100vh;
      box-sizing: border-box;
    }
    #timeline {
      flex: 1;
      overflow-y: auto;
      margin-bottom: 10px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .card {
      border: 1px solid var(--vscode-widget-border, #333);
      background: var(--vscode-sideBar-background, #1e1e1e);
      border-radius: 6px;
      padding: 8px 12px;
    }
    .user-card {
      border-left: 3px solid var(--vscode-button-background, #007acc);
    }
    .assistant-card {
      border-left: 3px solid var(--vscode-charts-green, #4ec9b0);
      white-space: pre-wrap;
    }
    .thinking-card {
      font-size: 0.9em;
      opacity: 0.85;
      font-style: italic;
      border-left: 3px solid var(--vscode-charts-purple, #b180d7);
    }
    .tool-card {
      font-family: monospace;
      font-size: 0.85em;
      background: rgba(255, 255, 255, 0.05);
      border-left: 3px solid var(--vscode-charts-yellow, #dcdcaa);
    }
    #dock {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    textarea {
      width: 100%;
      height: 60px;
      box-sizing: border-box;
      background: var(--vscode-input-background);
      color: var(--vscode-input-foreground);
      border: 1px solid var(--vscode-input-border);
      border-radius: 4px;
      padding: 6px;
      resize: vertical;
      font-family: inherit;
    }
    .btn-row {
      display: flex;
      justify-content: space-between;
    }
    button {
      background: var(--vscode-button-background);
      color: var(--vscode-button-foreground);
      border: none;
      border-radius: 4px;
      padding: 6px 14px;
      cursor: pointer;
    }
    button:hover {
      background: var(--vscode-button-hoverBackground);
    }
  </style>
</head>
<body>
  <div id="timeline">
    <div class="card assistant-card">Neow ready. Ask anything or select code to explain/fix.</div>
  </div>
  <div id="dock">
    <textarea id="promptInput" placeholder="Type prompt (Enter to send, Shift+Enter for newline)..."></textarea>
    <div class="btn-row">
      <button id="cancelBtn" style="background: var(--vscode-button-secondaryBackground, #555);">Stop</button>
      <button id="sendBtn">Send</button>
    </div>
  </div>

  <script>
    const vscode = acquireVsCodeApi();
    const timeline = document.getElementById('timeline');
    const input = document.getElementById('promptInput');
    const sendBtn = document.getElementById('sendBtn');
    const cancelBtn = document.getElementById('cancelBtn');

    let currentAssistantCard = null;
    let currentThinkingCard = null;

    function appendCard(className, text) {
      const card = document.createElement('div');
      card.className = 'card ' + className;
      card.textContent = text;
      timeline.appendChild(card);
      timeline.scrollTop = timeline.scrollHeight;
      return card;
    }

    sendBtn.addEventListener('click', () => {
      const text = input.value.trim();
      if (!text) return;
      appendCard('user-card', text);
      vscode.postMessage({ type: 'prompt', text });
      input.value = '';
      currentAssistantCard = null;
      currentThinkingCard = null;
    });

    cancelBtn.addEventListener('click', () => {
      vscode.postMessage({ type: 'cancel' });
    });

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendBtn.click();
      }
    });

    window.addEventListener('message', (event) => {
      const msg = event.data;
      switch (msg.type) {
        case 'externalPrompt':
          appendCard('user-card', msg.text);
          currentAssistantCard = null;
          currentThinkingCard = null;
          break;
        case 'reasoningDelta':
          if (!currentThinkingCard) {
            currentThinkingCard = appendCard('thinking-card', 'Thinking: ' + msg.delta);
          } else {
            currentThinkingCard.textContent += msg.delta;
          }
          break;
        case 'contentDelta':
          if (!currentAssistantCard) {
            currentAssistantCard = appendCard('assistant-card', msg.delta);
          } else {
            currentAssistantCard.textContent += msg.delta;
          }
          break;
        case 'toolStart':
          appendCard('tool-card', '▶ Tool ' + msg.name + ' (' + JSON.stringify(msg.args) + ')');
          break;
        case 'toolEnd':
          appendCard('tool-card', '✓ Tool ' + msg.name + ' finished [' + msg.status + ']');
          break;
        case 'error':
          appendCard('card', 'Error: ' + msg.error);
          break;
      }
    });
  </script>
</body>
</html>`;
  }
}
