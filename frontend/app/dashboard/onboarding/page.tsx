"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import {
  getImportTemplate,
  importCustomers,
  importEquipment,
  provisionOnboarding,
  setupDriveFolder,
  updateOrganizationSettings,
  uploadKnowledgeDocument,
  type CsvImportResult,
} from "@/lib/api";

const STEPS = [
  "Business Details",
  "Import Customers",
  "Import Equipment",
  "Knowledge Base",
  "Configure Agent",
  "Complete",
];

const ISSUE_DEFAULTS: Record<string, string> = {
  hvac: "AC_NO_COOLING, AC_LEAKING, FURNACE_NO_HEAT, MAINTENANCE, EMERGENCY",
  plumbing:
    "DRAIN_BLOCKED, PIPE_LEAK, WATER_HEATER, EMERGENCY, MAINTENANCE",
  electrical:
    "POWER_OUTAGE, CIRCUIT_BREAKER, WIRING, INSTALLATION, EMERGENCY",
};

const DEFAULT_BUSINESS_HOURS: Record<
  string,
  { open: string; close: string } | null
> = {
  monday: { open: "08:00", close: "17:00" },
  tuesday: { open: "08:00", close: "17:00" },
  wednesday: { open: "08:00", close: "17:00" },
  thursday: { open: "08:00", close: "17:00" },
  friday: { open: "08:00", close: "17:00" },
  saturday: null,
  sunday: null,
};

const VAPI_TOOLS = [
  "schedule_dispatch",
  "query_churn_score",
  "get_customer_info",
  "get_equipment_info",
  "rag_knowledge_query",
  "create_support_ticket",
  "create_customer",
  "update_customer",
  "create_equipment",
  "update_dispatch",
  "lookup_service_info",
  "check_availability",
];

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [orgId, setOrgId] = useState<string | null>(null);
  const [orgName, setOrgName] = useState("");
  const [agentName, setAgentName] = useState("");
  const [industry, setIndustry] = useState("hvac");
  const [error, setError] = useState<string | null>(null);
  const [provisioning, setProvisioning] = useState(false);
  const [provisionComplete, setProvisionComplete] = useState(false);

  const [biz, setBiz] = useState({
    org_name: "",
    industry: "hvac",
    timezone: "America/Los_Angeles",
    business_phone: "",
    agent_name: "Alex",
    notification_email: "",
    service_zip_codes: "",
    business_hours: DEFAULT_BUSINESS_HOURS,
  });

  const [customerFile, setCustomerFile] = useState<File | null>(null);
  const [customerPreview, setCustomerPreview] = useState<CsvImportResult | null>(
    null,
  );
  const [customersImported, setCustomersImported] = useState(0);

  const [equipmentFile, setEquipmentFile] = useState<File | null>(null);
  const [equipmentPreview, setEquipmentPreview] = useState<CsvImportResult | null>(
    null,
  );
  const [equipmentImported, setEquipmentImported] = useState(0);

  const [docsIndexed, setDocsIndexed] = useState(0);
  const [driveUrl, setDriveUrl] = useState<string | null>(null);

  const [agent, setAgent] = useState({
    system_prompt_override: "",
    first_message: "Thanks for calling — how can we help you today?",
    issue_taxonomy: ISSUE_DEFAULTS.hvac,
  });

  const next = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));
  const back = () => setStep((s) => Math.max(s - 1, 0));

  const handleStep1 = () => {
    setError(null);
    if (!biz.org_name.trim()) {
      setError("Business name is required");
      return;
    }
    if (!biz.business_phone.trim()) {
      setError("Business phone is required");
      return;
    }
    if (!biz.notification_email.trim()) {
      setError("Notification email is required");
      return;
    }
    setAgent((a) => ({
      ...a,
      issue_taxonomy: ISSUE_DEFAULTS[biz.industry] || ISSUE_DEFAULTS.hvac,
    }));
    next();
  };

  const runCustomerImport = async (dryRun: boolean) => {
    if (!orgId || !customerFile) return;
    const result = await importCustomers(orgId, customerFile, dryRun);
    if (dryRun) setCustomerPreview(result);
    else {
      setCustomersImported(result.imported);
      setCustomerPreview(result);
    }
  };

  const runEquipmentImport = async (dryRun: boolean) => {
    if (!orgId || !equipmentFile) return;
    const result = await importEquipment(orgId, equipmentFile, dryRun);
    if (dryRun) setEquipmentPreview(result);
    else {
      setEquipmentImported(result.imported);
      setEquipmentPreview(result);
    }
  };

  const handleDocUpload = async (file: File) => {
    if (!orgId) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("namespace", "faq_general");
    await uploadKnowledgeDocument(orgId, fd);
    setDocsIndexed((n) => n + 1);
  };

  const handleDriveSetup = async () => {
    if (!orgId) return;
    const res = await setupDriveFolder(orgId);
    setDriveUrl(res.folder_url);
  };

  const handleComplete = async () => {
    setError(null);
    setProvisioning(true);
    try {
      const zipCodes = biz.service_zip_codes
        .split(",")
        .map((z) => z.trim())
        .filter(Boolean);

      const result = await provisionOnboarding({
        business_name: biz.org_name.trim(),
        trade_type: biz.industry,
        phone_number: biz.business_phone.trim(),
        agent_name: biz.agent_name.trim(),
        timezone: biz.timezone,
        business_hours: biz.business_hours,
        notification_email: biz.notification_email.trim(),
        service_zip_codes: zipCodes.length ? zipCodes : undefined,
      });

      setOrgId(result.org_id);
      setOrgName(result.org_name);
      setAgentName(result.agent_name);
      setIndustry(biz.industry);

      await updateOrganizationSettings(result.org_id, {
        system_prompt_override: agent.system_prompt_override || undefined,
        first_message: agent.first_message,
        issue_taxonomy: agent.issue_taxonomy.split(",").map((t) => t.trim()),
        pinecone_namespace: "faq_general",
      });

      setProvisionComplete(true);
      next();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Failed to provision organization",
      );
    } finally {
      setProvisioning(false);
    }
  };

  return (
    <div className="p-8">
      <h1 className="mb-2 text-2xl font-bold">Client Onboarding</h1>
      <div className="mb-8 flex gap-2">
        {STEPS.map((label, i) => (
          <div
            key={label}
            className={`flex-1 rounded py-1 text-center text-xs ${
              i === step
                ? "bg-indigo-600 text-white"
                : i < step
                  ? "bg-indigo-100 text-indigo-800 dark:bg-indigo-950"
                  : "bg-gray-100 text-gray-500 dark:bg-slate-800"
            }`}
          >
            {i + 1}. {label}
          </div>
        ))}
      </div>

      {error && (
        <p className="mb-4 text-sm text-red-700 dark:text-red-300">{error}</p>
      )}

      {step === 0 && (
        <div className="max-w-lg space-y-3">
          <input
            className="w-full rounded border px-3 py-2 text-sm dark:bg-slate-800"
            placeholder="Business name"
            value={biz.org_name}
            onChange={(e) => setBiz((b) => ({ ...b, org_name: e.target.value }))}
          />
          <select
            className="w-full rounded border px-3 py-2 text-sm dark:bg-slate-800"
            value={biz.industry}
            onChange={(e) => setBiz((b) => ({ ...b, industry: e.target.value }))}
          >
            {Object.keys(ISSUE_DEFAULTS).map((i) => (
              <option key={i} value={i}>
                {i}
              </option>
            ))}
            <option value="other">other</option>
          </select>
          <select
            className="w-full rounded border px-3 py-2 text-sm dark:bg-slate-800"
            value={biz.timezone}
            onChange={(e) => setBiz((b) => ({ ...b, timezone: e.target.value }))}
          >
            <option value="America/Los_Angeles">America/Los_Angeles</option>
            <option value="America/Denver">America/Denver</option>
            <option value="America/Chicago">America/Chicago</option>
            <option value="America/New_York">America/New_York</option>
          </select>
          <input
            className="w-full rounded border px-3 py-2 text-sm dark:bg-slate-800"
            placeholder="Business phone"
            value={biz.business_phone}
            onChange={(e) =>
              setBiz((b) => ({ ...b, business_phone: e.target.value }))
            }
          />
          <input
            className="w-full rounded border px-3 py-2 text-sm dark:bg-slate-800"
            placeholder="AI agent name (e.g. Alex)"
            value={biz.agent_name}
            onChange={(e) =>
              setBiz((b) => ({ ...b, agent_name: e.target.value }))
            }
          />
          <input
            className="w-full rounded border px-3 py-2 text-sm dark:bg-slate-800"
            placeholder="Notification email"
            type="email"
            value={biz.notification_email}
            onChange={(e) =>
              setBiz((b) => ({ ...b, notification_email: e.target.value }))
            }
          />
          <input
            className="w-full rounded border px-3 py-2 text-sm dark:bg-slate-800"
            placeholder="Service ZIP codes (optional, comma-separated)"
            value={biz.service_zip_codes}
            onChange={(e) =>
              setBiz((b) => ({ ...b, service_zip_codes: e.target.value }))
            }
          />
          <button
            type="button"
            onClick={handleStep1}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white"
          >
            Continue
          </button>
        </div>
      )}

      {step === 1 && (
        <ImportStep
          title="Import customers"
          note={
            orgId
              ? undefined
              : "Complete setup on the final step to enable imports, or skip for now."
          }
          file={customerFile}
          setFile={setCustomerFile}
          preview={customerPreview}
          onDryRun={() => void runCustomerImport(true)}
          onImport={() => void runCustomerImport(false)}
          onDownload={() => orgId && void getImportTemplate(orgId, "customers")}
          onSkip={next}
          disabled={!orgId}
        />
      )}

      {step === 2 && (
        <ImportStep
          title="Import equipment"
          note={
            orgId
              ? "Links equipment to customers by phone or email."
              : "Complete setup on the final step to enable imports, or skip for now."
          }
          file={equipmentFile}
          setFile={setEquipmentFile}
          preview={equipmentPreview}
          onDryRun={() => void runEquipmentImport(true)}
          onImport={() => void runEquipmentImport(false)}
          onDownload={() => orgId && void getImportTemplate(orgId, "equipment")}
          onSkip={next}
          disabled={!orgId}
        />
      )}

      {step === 3 && (
        <div className="max-w-lg space-y-4">
          <p className="text-sm text-gray-600">
            {orgId
              ? "Upload PDF, Word, or text files."
              : "Complete setup on the final step to upload documents, or skip for now."}
          </p>
          <input
            type="file"
            disabled={!orgId}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void handleDocUpload(f);
            }}
          />
          <p className="text-sm">Documents indexed: {docsIndexed}</p>
          <button
            type="button"
            disabled={!orgId}
            onClick={() => void handleDriveSetup()}
            className="rounded border px-4 py-2 text-sm disabled:opacity-50"
          >
            Set up Google Drive folder
          </button>
          {driveUrl && (
            <a href={driveUrl} target="_blank" rel="noreferrer" className="text-sm text-indigo-600 underline">
              Open Drive folder
            </a>
          )}
          <button type="button" onClick={next} className="block text-sm text-gray-500">
            Skip
          </button>
        </div>
      )}

      {step === 4 && (
        <div className="max-w-lg space-y-3">
          <textarea
            className="w-full rounded border px-3 py-2 text-sm dark:bg-slate-800"
            rows={5}
            placeholder="System prompt override (optional)"
            value={agent.system_prompt_override}
            onChange={(e) =>
              setAgent((a) => ({ ...a, system_prompt_override: e.target.value }))
            }
          />
          <input
            className="w-full rounded border px-3 py-2 text-sm dark:bg-slate-800"
            value={agent.first_message}
            onChange={(e) => setAgent((a) => ({ ...a, first_message: e.target.value }))}
          />
          <input
            className="w-full rounded border px-3 py-2 text-sm dark:bg-slate-800"
            value={agent.issue_taxonomy}
            onChange={(e) =>
              setAgent((a) => ({ ...a, issue_taxonomy: e.target.value }))
            }
          />
          <button
            type="button"
            onClick={() => void handleComplete()}
            disabled={provisioning}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-60"
          >
            {provisioning ? "Setting up your AI receptionist…" : "Complete setup"}
          </button>
        </div>
      )}

      {step === 5 && provisionComplete && (
        <div className="max-w-lg space-y-4">
          <h2 className="text-xl font-semibold text-green-700 dark:text-green-300">
            Your AI receptionist is ready!
          </h2>
          <p className="text-sm text-gray-700 dark:text-gray-300">
            <span className="font-medium">{orgName}</span> is live with agent{" "}
            <span className="font-medium">{agentName}</span>.
          </p>
          {customersImported > 0 && (
            <p className="text-sm">✅ {customersImported} customers imported</p>
          )}
          {equipmentImported > 0 && (
            <p className="text-sm">✅ {equipmentImported} equipment records imported</p>
          )}
          {docsIndexed > 0 && (
            <p className="text-sm">✅ {docsIndexed} documents indexed</p>
          )}
          <button
            type="button"
            onClick={() => router.push("/dashboard")}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white"
          >
            Go to Dashboard
          </button>
          <div className="mt-6 rounded border p-4 dark:border-slate-700">
            <p className="font-medium">Vapi setup — add these 12 tools:</p>
            <ul className="mt-2 list-inside list-disc text-xs">
              {VAPI_TOOLS.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-gray-500">
              See docs/vapi_tool_schemas.md for JSON schemas.
            </p>
          </div>
        </div>
      )}

      {step > 0 && step < 5 && (
        <button type="button" onClick={back} className="mt-6 text-sm text-gray-500">
          Back
        </button>
      )}
    </div>
  );
}

function ImportStep({
  title,
  note,
  file,
  setFile,
  preview,
  onDryRun,
  onImport,
  onDownload,
  onSkip,
  disabled = false,
}: {
  title: string;
  note?: string;
  file: File | null;
  setFile: (f: File | null) => void;
  preview: CsvImportResult | null;
  onDryRun: () => void;
  onImport: () => void;
  onDownload: () => void;
  onSkip: () => void;
  disabled?: boolean;
}) {
  return (
    <div className="max-w-lg space-y-3">
      <h2 className="text-lg font-semibold">{title}</h2>
      {note && <p className="text-sm text-gray-600">{note}</p>}
      <button
        type="button"
        disabled={disabled}
        onClick={onDownload}
        className="text-sm text-indigo-600 underline disabled:opacity-50"
      >
        Download template
      </button>
      <input
        type="file"
        accept=".csv"
        disabled={disabled}
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      <div className="flex gap-2">
        <button
          type="button"
          disabled={!file || disabled}
          onClick={onDryRun}
          className="rounded border px-3 py-1 text-sm disabled:opacity-50"
        >
          Preview (dry run)
        </button>
        <button
          type="button"
          disabled={!file || disabled}
          onClick={onImport}
          className="rounded bg-indigo-600 px-3 py-1 text-sm text-white disabled:opacity-50"
        >
          Import
        </button>
      </div>
      {preview && (
        <p className="text-sm text-green-700">
          {preview.imported} ready to import, {preview.skipped} skipped,{" "}
          {preview.errors.length} errors
        </p>
      )}
      <button type="button" onClick={onSkip} className="text-sm text-gray-500">
        Skip
      </button>
    </div>
  );
}
