/**
 * CRM dashboard — its own page (/app/crm-dashboard): KPIs, trend, funnel, "call now" leads with
 * next best action, agenda, sources, pipeline, channel mix, agent leaderboard, at-risk deals, the
 * AI copilot (text / voice) and the lead drawer with AI brief, drafts and voice notes.
 * Records (leads, pipeline, deals, customers, tasks …) stay on the CRM page.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { Bot, Table2 } from "lucide-react";
import { useApi } from "@/hooks/useApi";
import { Button, Card, PageHeader } from "@/components/ui";
import { CrmLeadDrawer } from "@/components/biz/CrmLeadDrawer";
import type { AgentsRes } from "@/components/biz/crm-types";
import { CrmDashboardTab } from "@/components/crm/CrmDashboardTab";
import { CrmCopilot } from "@/components/crm/CrmCopilot";

export default function CrmDashboard() {
  const agentsQ = useApi<AgentsRes>("/crm/agents");
  const agents = agentsQ.data?.agents ?? [];
  const [leadId, setLeadId] = useState<string | null>(null);
  const [copilot, setCopilot] = useState(false);
  const [question, setQuestion] = useState<string | undefined>();

  return (
    <div className="space-y-6">
      <PageHeader
        title="CRM dashboard"
        subtitle="Today's priorities, pipeline health and your team — with an AI copilot that answers from live CRM data"
        actions={
          <>
            <Link to="/app/crm" className="btn btn-outline btn-sm">
              <Table2 className="h-4 w-4" /> CRM records
            </Link>
            <Button
              variant="gold"
              size="sm"
              icon={<Bot className="h-4 w-4" />}
              onClick={() => {
                setQuestion(undefined);
                setCopilot(true);
              }}
            >
              AI copilot
            </Button>
          </>
        }
      />
      <Card className="overflow-hidden">
        <CrmDashboardTab
          agents={agents}
          onOpenLead={setLeadId}
          onAsk={(q) => {
            setQuestion(q || undefined);
            setCopilot(true);
          }}
        />
      </Card>
      <CrmLeadDrawer leadId={leadId} agents={agents} onClose={() => setLeadId(null)} />
      <CrmCopilot
        open={copilot}
        initial={question}
        onClose={() => setCopilot(false)}
        onOpenLead={(id) => {
          setCopilot(false);
          setLeadId(id);
        }}
      />
    </div>
  );
}
