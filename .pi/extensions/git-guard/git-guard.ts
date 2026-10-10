import { execFileSync } from "node:child_process";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const PROJECT_DIR = "/pi-trader";
const ALLOWED_BRANCH = "trader";
const ALLOWED_REMOTE = "personal";

function shellCommand(event: any): string | null {
  if (event?.toolName !== "bash" && event?.toolName !== "terminal") {
    return null;
  }
  const input = event.input ?? event.toolInput ?? {};
  return typeof input.command === "string" ? input.command : null;
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

function isBranchInspection(command: string): boolean {
  return /^\s*git\s+(?:-[^\s]+\s+)*branch\s+--show-current\s*$/.test(command);
}

function hasGit(command: string): boolean {
  return /\bgit(?:\s|$)/.test(command);
}

function hasOrigin(command: string): boolean {
  return /\borigin\b/.test(command);
}

function hasDeployOperation(command: string): boolean {
  return /\b(?:checkout|switch|push|pull|fetch)\b[^;&|]*\bdeploy\b/.test(command);
}

function hasImplicitRemotePush(command: string): boolean {
  return /\bgit\s+push(?:\s+(?:-[^\s]+|--[^\s]+))*\s*(?:$|[;&|])/.test(command);
}

function hasNonPersonalPush(command: string): boolean {
  const match = command.match(/\bgit\s+push\s+(?:(?:-[^\s]+|--[^\s]+)\s+)*([^\s;&|]+)/);
  return Boolean(match && match[1] !== ALLOWED_REMOTE && !match[1].startsWith("-"));
}

function block(reason: string) {
  return {
    block: true,
    reason: `Git Guard 已阻断该操作：${reason}\n允许条件：当前分支为 trader，远程仓库仅使用 personal。`,
  };
}

export default function gitGuard(pi: ExtensionAPI) {
  pi.on("tool_call", async (event: any) => {
    const command = shellCommand(event);
    if (!command || !hasGit(command)) {
      return;
    }

    if (isBranchInspection(command)) {
      return;
    }

    if (hasOrigin(command)) {
      return block("检测到 origin 远程仓库，只允许操作 personal。");
    }

    if (hasDeployOperation(command)) {
      return block("检测到 deploy 分支，AI 只允许在 trader 分支工作。");
    }

    const branch = currentBranch();
    if (branch !== ALLOWED_BRANCH) {
      return block(`当前分支为 ${branch ?? "未知分支"}，AI 只允许在 trader 分支执行 Git 操作。`);
    }

    if (hasImplicitRemotePush(command)) {
      return block("git push 未显式指定 personal 远程。");
    }

    if (hasNonPersonalPush(command)) {
      return block("git push 的目标远程不是 personal。");
    }
  });
}
