import { readFile, writeFile, mkdir } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

type Level = "off" | "lite" | "full" | "ultra";
const LEVELS: Level[] = ["off", "lite", "full", "ultra"];
const CONFIG_DIR = process.env.PI_CODING_AGENT_DIR
  ? process.env.PI_CODING_AGENT_DIR
  : process.env.XDG_CONFIG_HOME
    ? join(process.env.XDG_CONFIG_HOME, "pi", "agent")
    : join(homedir(), ".pi", "agent");
const CONFIG_PATH = join(CONFIG_DIR, "caveman.json");
let level: Level = "off";

const prompts: Record<Exclude<Level, "off">, string> = {
  lite: "CAVEMAN lite: 用简体中文，结论前置，删除寒暄和空话；保留完整句子、技术细节、风险和不确定性。",
  full: "CAVEMAN full: 用简体中文，极简表达；短句和列表优先，保留技术细节、风险、前提和验证状态。",
  ultra: "CAVEMAN ultra: 用简体中文，最大限度压缩表达；可用缩写和箭头，但代码、命令、错误、风险和确认信息必须完整准确。",
};

async function loadLevel(): Promise<void> {
  try {
    const value = JSON.parse(await readFile(CONFIG_PATH, "utf8")).defaultLevel;
    if (LEVELS.includes(value)) level = value;
  } catch {
    level = "off";
  }
}

async function saveLevel(): Promise<void> {
  await mkdir(CONFIG_DIR, { recursive: true });
  await writeFile(CONFIG_PATH, JSON.stringify({ defaultLevel: level }, null, 2) + "\n", "utf8");
}

function appendPrompt(systemPrompt: unknown, addition: string): string | string[] {
  if (Array.isArray(systemPrompt)) return [...systemPrompt, addition];
  const base = typeof systemPrompt === "string" ? systemPrompt : "";
  return base ? `${base}\n\n${addition}` : addition;
}

export default function caveman(pi: ExtensionAPI) {
  pi.on("session_start", async () => {
    await loadLevel();
  });

  pi.registerCommand("caveman", {
    description: "切换 CAVEMAN 压缩模式：off、lite、full、ultra",
    handler: async (args, ctx) => {
      const value = args.trim().toLowerCase();
      level = (value ? value : level === "off" ? "full" : "off") as Level;
      if (!LEVELS.includes(level)) {
        ctx.ui.notify("可用模式：off、lite、full、ultra", "error");
        return;
      }
      await saveLevel();
      ctx.ui.notify(level === "off" ? "CAVEMAN 已关闭" : `CAVEMAN：${level}`, "info");
    },
  });

  pi.on("before_agent_start", async (event) => {
    if (level === "off") return;
    return { systemPrompt: appendPrompt(event.systemPrompt, prompts[level]) };
  });
}
