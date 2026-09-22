import { Bot } from "lucide-react";
import { CopyField } from "../../components/ui/CopyField";
import { Card } from "../../components/ui/States";

const SKILL_PATH = "skills/deploy-website/SKILL.md";
const SKILL_RAW = `https://raw.githubusercontent.com/nyx-ulrix/deployer/main/${SKILL_PATH}`;
const SKILL_PAGE = `https://github.com/nyx-ulrix/deployer/blob/main/${SKILL_PATH}`;

// One-liners that drop the skill where Claude Code looks for user skills (~/.claude/skills/<name>/SKILL.md).
const INSTALL_POWERSHELL = `$d="$HOME\\.claude\\skills\\deploy-website"; New-Item -ItemType Directory -Force $d | Out-Null; Invoke-WebRequest -UseBasicParsing ${SKILL_RAW} -OutFile "$d\\SKILL.md"`;
const INSTALL_BASH = `mkdir -p ~/.claude/skills/deploy-website && curl -fsSL ${SKILL_RAW} -o ~/.claude/skills/deploy-website/SKILL.md`;

/** How to give an AI coding agent the Deployer "deploy-website" skill (project Overview). */
export function AgentSkillCard() {
  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <Bot className="size-4 text-accent" /> Use Deployer from an AI agent
        </span>
      }
      description="A skill file teaches agents like Claude Code how to back a website with this project and how to deploy the site."
    >
      <div className="space-y-3 text-sm">
        <p className="text-muted">
          Install it once on the computer where the agent runs. The skill always asks which platform to deploy to and
          orders the choices by your past deployments — it never deploys on its own.
        </p>
        <CopyField label="Windows (PowerShell)" value={INSTALL_POWERSHELL} />
        <CopyField label="macOS / Linux" value={INSTALL_BASH} />
        <p className="text-xs text-muted">
          Other agents can read the same file from the repository at <code className="font-mono">{SKILL_PATH}</code>.{" "}
          <a href={SKILL_PAGE} target="_blank" rel="noreferrer" className="font-medium text-accent hover:underline">
            View on GitHub
          </a>
        </p>
      </div>
    </Card>
  );
}
