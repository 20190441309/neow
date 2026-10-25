import * as vscode from "vscode";
import { NeowChatViewProvider } from "./chatViewProvider";

export function activate(context: vscode.ExtensionContext) {
  const config = vscode.workspace.getConfiguration("neow");
  const executablePath = config.get<string>("executablePath") || "neow";

  const provider = new NeowChatViewProvider(context.extensionUri, executablePath);

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(NeowChatViewProvider.viewType, provider)
  );

  // Command: Open Chat
  context.subscriptions.push(
    vscode.commands.registerCommand("neow.openChat", () => {
      vscode.commands.executeCommand("workbench.view.extension.neow-sidebar");
    })
  );

  // Command: Explain Selection
  context.subscriptions.push(
    vscode.commands.registerCommand("neow.explainSelection", () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        vscode.window.showInformationMessage("No active editor found.");
        return;
      }
      const selection = editor.document.getText(editor.selection);
      if (!selection.trim()) {
        vscode.window.showInformationMessage("No code selected.");
        return;
      }
      const fileName = editor.document.fileName;
      const prompt = `Explain the following code from ${fileName}:\n\`\`\`\n${selection}\n\`\`\``;
      provider.sendPromptFromExternal(prompt);
    })
  );

  // Command: Fix Selection
  context.subscriptions.push(
    vscode.commands.registerCommand("neow.fixSelection", () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        vscode.window.showInformationMessage("No active editor found.");
        return;
      }
      const selection = editor.document.getText(editor.selection);
      if (!selection.trim()) {
        vscode.window.showInformationMessage("No code selected.");
        return;
      }
      const fileName = editor.document.fileName;
      const prompt = `Review and fix potential bugs in this code from ${fileName}:\n\`\`\`\n${selection}\n\`\`\``;
      provider.sendPromptFromExternal(prompt);
    })
  );

  // Command: Apply Diff
  context.subscriptions.push(
    vscode.commands.registerCommand("neow.applyDiff", () => {
      vscode.window.showInformationMessage("Neow file operations apply directly to workspace.");
    })
  );

  // Listen for config changes
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("neow.executablePath")) {
        const newPath = vscode.workspace.getConfiguration("neow").get<string>("executablePath") || "neow";
        provider.setExecutablePath(newPath);
      }
    })
  );
}

export function deactivate() {}
