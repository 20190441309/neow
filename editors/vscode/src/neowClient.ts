import * as child_process from "child_process";
import * as readline from "readline";
import * as vscode from "vscode";

export interface StreamEvent {
  type: string;
  [key: string]: any;
}

export interface ApprovalRequest {
  id: number;
  tool: string;
  args: Record<string, any>;
  reason: string;
}

export interface NeowCallbacks {
  onReasoning?: (delta: string) => void;
  onContent?: (delta: string) => void;
  onToolStart?: (name: string, args: any) => void;
  onToolEnd?: (name: string, status: string, result: string) => void;
  onNotice?: (message: string) => void;
  onResult?: (result: any) => void;
  onError?: (err: Error) => void;
  onExit?: (code: number | null) => void;
}

export class NeowClient {
  private currentProcess: child_process.ChildProcessWithoutNullStreams | null = null;
  private isCancelled: boolean = false;

  constructor(
    private readonly executablePath: string,
    private readonly workspaceRoot?: string
  ) {}

  public execute(
    prompt: string,
    options: {
      model?: string;
      approvalMode?: string;
      additionalArgs?: string[];
    },
    callbacks: NeowCallbacks
  ): void {
    this.cancel();
    this.isCancelled = false;

    const args = [
      "-p",
      prompt,
      "--output-format",
      "stream-json",
    ];

    if (options.approvalMode === "yolo") {
      args.push("--approval", "yolo");
    } else {
      args.push("--approval-interactive");
    }

    if (options.model && options.model.trim()) {
      args.push("--model", options.model.trim());
    }

    if (options.additionalArgs) {
      args.push(...options.additionalArgs);
    }

    const spawnOptions: child_process.SpawnOptionsWithoutNullStreams = {
      cwd: this.workspaceRoot || (vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? process.cwd()),
      env: { ...process.env },
    };

    try {
      this.currentProcess = child_process.spawn(this.executablePath, args, spawnOptions);
    } catch (err: any) {
      callbacks.onError?.(new Error(`Failed to launch Neow executable '${this.executablePath}': ${err.message}`));
      return;
    }

    const rl = readline.createInterface({
      input: this.currentProcess.stdout,
      crlfDelay: Infinity,
    });

    rl.on("line", async (line: string) => {
      const trimmed = line.trim();
      if (!trimmed) {
        return;
      }
      try {
        const event: StreamEvent = JSON.parse(trimmed);
        await this.handleEvent(event, callbacks);
      } catch (err) {
        // Not a JSON event line or raw stderr output
      }
    });

    this.currentProcess.stderr.on("data", (data: Buffer) => {
      const text = data.toString();
      if (text.includes("WARNING") || text.includes("ERROR")) {
        callbacks.onNotice?.(text.trim());
      }
    });

    this.currentProcess.on("error", (err: Error) => {
      if (!this.isCancelled) {
        callbacks.onError?.(err);
      }
    });

    this.currentProcess.on("close", (code: number | null) => {
      this.currentProcess = null;
      if (!this.isCancelled) {
        callbacks.onExit?.(code);
      }
    });
  }

  private async handleEvent(event: StreamEvent, callbacks: NeowCallbacks): Promise<void> {
    switch (event.type) {
      case "reasoning_delta":
        callbacks.onReasoning?.(event.text || "");
        break;
      case "content_delta":
        callbacks.onContent?.(event.text || "");
        break;
      case "tool_start":
        callbacks.onToolStart?.(event.name || "", event.args || {});
        break;
      case "tool_end":
        callbacks.onToolEnd?.(event.name || "", event.status || "ok", event.result || "");
        break;
      case "notice":
        callbacks.onNotice?.(event.message || "");
        break;
      case "result":
        callbacks.onResult?.(event);
        break;
      case "approval_request":
        await this.handleApproval(event as any);
        break;
    }
  }

  private async handleApproval(req: ApprovalRequest): Promise<void> {
    const title = `Neow Approval: Run tool '${req.tool}'?`;
    const details = req.reason ? `Reason: ${req.reason}` : "";
    const message = details ? `${title} (${details})` : title;

    const choice = await vscode.window.showWarningMessage(
      message,
      { modal: false },
      "Allow Once",
      "Deny"
    );

    const approve = choice === "Allow Once";
    this.sendApprovalResponse(req.id, approve);
  }

  public sendApprovalResponse(id: number, approve: boolean): void {
    if (this.currentProcess && this.currentProcess.stdin.writable) {
      const payload = JSON.stringify({ id, approve }) + "\n";
      this.currentProcess.stdin.write(payload);
    }
  }

  public cancel(): void {
    if (this.currentProcess) {
      this.isCancelled = true;
      this.currentProcess.kill();
      this.currentProcess = null;
    }
  }
}
