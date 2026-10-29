import { Bot } from "lucide-react";
import { Card } from "../../components/ui/States";

const SKILL_LISTING = "https://www.agensi.io";
const SKILL_NAME = "Deploy a Website with Deployer";

/** Where to get the Deployer "deploy-website" skill for an AI coding agent (project Overview). */
export function AgentSkillCard() {
  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <Bot className="size-4 text-accent" /> Use Deployer from an AI agent
        </span>
      }
      description="A skill teaches agents like Claude Code how to back a website with this project and how to deploy the site."
    >
      <div className="space-y-3 text-sm">
        <p className="text-muted">
          Install it once on the computer where the agent runs. The skill always asks which platform to deploy to and
          orders the choices by your past deployments — it never deploys on its own.
        </p>
        <p>
          Get it on Agensi: search for <span className="font-medium">{SKILL_NAME}</span>.{" "}
          <a href={SKILL_LISTING} target="_blank" rel="noreferrer" className="font-medium text-accent hover:underline">
            Open Agensi
          </a>
        </p>
      </div>
    </Card>
  );
}
