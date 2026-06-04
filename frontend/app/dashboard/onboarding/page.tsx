"use client";

import Link from "next/link";
import { useState } from "react";

import {
  createOrganization,
  getImportTemplate,
  importCustomers,
  importEquipment,
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

function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 100);
}

export default function OnboardingPage() {
  const [step, setStep] = useState(0);
  const [orgId, setOrgId] = useState<string | null>(null);
  const [orgName, setOrgName] = useState("");
  const [industry, setIndustry] = useState("hvac");
  const [error, setError] = useState<string | null>(null);

  const [biz, setBiz] = useState({
    org_name: "",
    industry: "hvac",
    timezone: "America/Los_Angeles",
    business_phone: "",
    plan_tier: "starter",
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

  const handleStep1 = async () => {
    setError(null);
    try {
      const created = await createOrganization({
        org_name: biz.org_name,
        slug: slugify(biz.org_name),
        industry: biz.industry,
        business_phone: biz.business_phone || undefined,
        plan_tier: biz.plan_tier,
        settings: { timezone: biz.timezone, pinecone_namespace: "faq_general" },
      });
      setOrgId(created.org_id);
      setOrgName(created.org_name);
      setIndustry(created.industry);
      setAgent((a) => ({
        ...a,
        issue_taxonomy: ISSUE_DEFAULTS[created.industry] || ISSUE_DEFAULTS.hvac,
      }));
      next();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create organization");
    }
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

  const handleStep5 = async () => {
    if (!orgId) return;
    setError(null);
    try {
      await updateOrganizationSettings(orgId, {
        system_prompt_override: agent.system_prompt_override || undefined,
        first_message: agent.first_message,
        issue_taxonomy: agent.issue_taxonomy.split(",").map((t) => t.trim()),
        pinecone_namespace: "faq_general",
      });
      next();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save agent settings");
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
          <select
            className="w-full rounded border px-3 py-2 text-sm dark:bg-slate-800"
            value={biz.plan_tier}
            onChange={(e) => setBiz((b) => ({ ...b, plan_tier: e.target.value }))}
          >
            <option value="starter">starter</option>
            <option value="professional">professional</option>
            <option value="enterprise">enterprise</option>
          </select>
          <button
            type="button"
            onClick={() => void handleStep1()}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white"
          >
            Create organization & continue
          </button>
        </div>
      )}

      {step === 1 && orgId && (
        <ImportStep
          title="Import customers"
          file={customerFile}
          setFile={setCustomerFile}
          preview={customerPreview}
          onDryRun={() => void runCustomerImport(true)}
          onImport={() => void runCustomerImport(false)}
          onDownload={() => void getImportTemplate(orgId, "customers")}
          onSkip={next}
        />
      )}

      {step === 2 && orgId && (
        <ImportStep
          title="Import equipment"
          note="Links equipment to customers by phone or email."
          file={equipmentFile}
          setFile={setEquipmentFile}
          preview={equipmentPreview}
          onDryRun={() => void runEquipmentImport(true)}
          onImport={() => void runEquipmentImport(false)}
          onDownload={() => void getImportTemplate(orgId, "equipment")}
          onSkip={next}
        />
      )}

      {step === 3 && orgId && (
        <div className="max-w-lg space-y-4">
          <p className="text-sm text-gray-600">Upload PDF, Word, or text files.</p>
          <input
            type="file"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void handleDocUpload(f);
            }}
          />
          <p className="text-sm">Documents indexed: {docsIndexed}</p>
          <button
            type="button"
            onClick={() => void handleDriveSetup()}
            className="rounded border px-4 py-2 text-sm"
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

      {step === 4 && orgId && (
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
            onClick={() => void handleStep5()}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white"
          >
            Save & continue
          </button>
        </div>
      )}

      {step === 5 && (
        <div className="max-w-lg space-y-3 text-sm">
          <p>✅ Organization created: {orgName}</p>
          <p>✅ {customersImported} customers imported</p>
          <p>✅ {equipmentImported} equipment records imported</p>
          <p>✅ {docsIndexed} documents indexed</p>
          <p>✅ Agent configured ({industry} taxonomy)</p>
          <div className="mt-4 flex gap-2">
            <Link
              href="/dashboard"
              className="rounded-lg bg-indigo-600 px-4 py-2 text-white"
            >
              Go to Dashboard
            </Link>
            <Link
              href="/dashboard/admin"
              className="rounded-lg border px-4 py-2"
            >
              View Organization
            </Link>
          </div>
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
}) {
  return (
    <div className="max-w-lg space-y-3">
      <h2 className="text-lg font-semibold">{title}</h2>
      {note && <p className="text-sm text-gray-600">{note}</p>}
      <button type="button" onClick={onDownload} className="text-sm text-indigo-600 underline">
        Download template
      </button>
      <input
        type="file"
        accept=".csv"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      <div className="flex gap-2">
        <button
          type="button"
          disabled={!file}
          onClick={onDryRun}
          className="rounded border px-3 py-1 text-sm disabled:opacity-50"
        >
          Preview (dry run)
        </button>
        <button
          type="button"
          disabled={!file}
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
