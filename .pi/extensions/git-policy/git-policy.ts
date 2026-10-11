import { execFileSync } from "node:child_process";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const PROJECT_DIR = "/pi-trader";
const WORK_BRANCH = "trader";
const PUSH_REMOTE = "personal";

function commandOf(event: any): string | null {
  if (event?.toolName !== "bash" && event?.toolName !== "terminal") return null;
  const input = event.input ?? event.toolInput ?? {};
  return typeof input.command === "string" ? input.command : null;
}

function isGit(command: string): boolean {
  return /(^|[;&|]\s*)(?:[A-Z_][A-Z0-9_]*=(?:"[^"]*"|'[^']*'|\S+)\s+)*git(?:\s|$)/.test(command);
}

function currentBranch(): string | null {
  try {
    return execFileSync("git", ["branch", "--show-current"], {
      cwd: PROJECT_DIR,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim() || null;
  } catch {
    return null;
  }
}

function isReadOnly(command: string): boolean {
  return /\bgit\s+(?:-C\s+\S+\s+)?(?:status|diff|log|show|rev-parse|branch\s+--show-current|remote\s+-v)\b/.test(command);
}

function isRecoveryToTrader(command: string): boolean {
  return /\bgit\s+(?:switch|checkout)\s+(?:--detach\s+)?trader(?:\s|$)/.test(command);
}

function isMutation(command: string): boolean {
  return /\bgit\s+(?:-[^\s]+\s+)*(?:add|commit|rm|mv|restore|reset|merge|rebase|cherry-pick|stash|tag|branch|switch|checkout|push|pull|fetch|remote)\b/.test(command);
}

function hasOriginRemoteOperation(command: string): boolean {
  return /\bgit\s+(?:[^;&|]*\s+)?(?:push|pull|fetch)\s+(?:[^;&|]*\s+)?origin(?:\s|$|[;&|])/.test(command)
    || /\bgit\s+remote\s+(?:set-url|remove|rename)\s+origin(?:\s|$|[;&|])/.test(command);
}

function hasDeployOperation(command: string): boolean {
  return /\bdeploy\b/.test(command) && isMutation(command) && !isRecoveryToTrader(command);
}

function pushIsAllowed(command: string): boolean {
  const match = command.match(/\bgit\s+push\s+(?:(?:-[^\s]+|--[^\s]+)\s+)*([^\s;&|]+)(?:\s+([^;&|]+))?/);
  if (!match) return false;
  const remote = match[1];
  const refspec = match[2] ?? "";
  return remote === PUSH_REMOTE && /(?:^|\s|:)trader(?:\s|$)/.test(refspec);
}

function block(reason: string) {
  return {
    block: true,
    reason: `Git Policy 已阻断该操作：${reason}\n规则：AI 只在 trader 工作，只向 personal 推送，禁止操作 origin。`,
  };
}

export default function gitPolicy(pi: ExtensionAPI) {
  pi.on("tool_call", async (event: any) => {
    const command = commandOf(event);
    if (!command || !isGit(command) || isReadOnly(command)) return;

    if (hasOriginRemoteOperation(command)) {
      return block("禁止对 origin 执行 push、pull 或 fetch。");
    }

    if (hasDeployOperation(command)) {
      return block("禁止操作 deploy 分支。");
    }

    const branch = currentBranch();
    if (branch !== WORK_BRANCH && !isRecoveryToTrader(command)) {
      return block(`当前分支为 ${branch ?? "未知分支"}，只能在 trader 分支执行 Git 操作。`);
    }

    if (/\bgit\s+push\b/.test(command) && !pushIsAllowed(command)) {
      return block("推送必须显式指定 personal 远程和 trader 分支。");
    }
  });
}
