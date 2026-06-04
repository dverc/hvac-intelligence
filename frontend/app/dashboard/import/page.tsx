"use client";

import { useCallback, useEffect, useState } from "react";

import {
  getDriveStatus,
  getImportTemplate,
  importCustomers,
  importEquipment,
  setupDriveFolder,
  syncDriveFolder,
  type CsvImportResult,
  type DriveStatus,
} from "@/lib/api";
import { getDashboardOrgId } from "@/lib/config";

type Tab = "customers" | "equipment" | "drive";

function ResultPanel({ result }: { result: CsvImportResult }) {
  return (
    <div className="mt-4 space-y-2 text-sm">
      {result.imported > 0 && (
        <p className="text-green-700 dark:text-green-300">
          Imported {result.imported} row(s) successfully
          {result.dry_run ? " (dry run — no data written)" : ""}.
        </p>
      )}
      {result.warnings.map((w) => (
        <p key={w} className="text-amber-700 dark:text-amber-300">
          {w}
        </p>
      ))}
      {result.errors.map((e) => (
        <p key={`${e.row}-${e.message}`} className="text-red-700 dark:text-red-300">
          Row {e.row}: {e.message}
        </p>
      ))}
    </div>
  );
}

export default function ImportPage() {
  const orgId = getDashboardOrgId();
  const [tab, setTab] = useState<Tab>("customers");
  const [dryRun, setDryRun] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CsvImportResult | null>(null);

  const [driveStatus, setDriveStatus] = useState<DriveStatus | null>(null);
  const [driveLoading, setDriveLoading] = useState(false);
  const [driveMessage, setDriveMessage] = useState<string | null>(null);

  const loadDriveStatus = useCallback(async () => {
    try {
      const status = await getDriveStatus(orgId);
      setDriveStatus(status);
    } catch (e) {
      setDriveStatus(null);
      setError(e instanceof Error ? e.message : "Failed to load Drive status");
    }
  }, [orgId]);

  useEffect(() => {
    if (tab === "drive") {
      void loadDriveStatus();
    }
  }, [tab, loadDriveStatus]);

  const handleDownloadTemplate = async (type: "customers" | "equipment") => {
    setError(null);
    try {
      const blob = await getImportTemplate(orgId, type);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${type}_template.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Template download failed");
    }
  };

  const handleCsvImport = async () => {
    if (!file) {
      setError("Choose a CSV file first");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data =
        tab === "customers"
          ? await importCustomers(orgId, file, dryRun)
          : await importEquipment(orgId, file, dryRun);
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setLoading(false);
    }
  };

  const handleDriveSetup = async () => {
    setDriveLoading(true);
    setError(null);
    setDriveMessage(null);
    try {
      const res = await setupDriveFolder(orgId);
      setDriveMessage(res.message);
      await loadDriveStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Drive setup failed");
    } finally {
      setDriveLoading(false);
    }
  };

  const handleDriveSync = async () => {
    setDriveLoading(true);
    setError(null);
    try {
      const res = await syncDriveFolder(orgId);
      setDriveMessage(
        `Synced ${res.synced} file(s), skipped ${res.skipped}, errors ${res.errors}`,
      );
      await loadDriveStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Drive sync failed");
    } finally {
      setDriveLoading(false);
    }
  };

  const tabs: { id: Tab; label: string }[] = [
    { id: "customers", label: "Import Customers" },
    { id: "equipment", label: "Import Equipment" },
    { id: "drive", label: "Google Drive Sync" },
  ];

  return (
    <div className="p-8">
      <h1 className="mb-2 text-2xl font-bold text-gray-900 dark:text-slate-100">
        Data Import
      </h1>
      <p className="mb-6 text-sm text-gray-600 dark:text-slate-400">
        Bulk onboard customers and equipment from CSV, or sync knowledge files
        from Google Drive.
      </p>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800 dark:bg-red-950 dark:text-red-200">
          {error}
        </div>
      )}

      <div className="mb-6 flex gap-2 border-b border-gray-200 dark:border-slate-700">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => {
              setTab(t.id);
              setFile(null);
              setResult(null);
              setError(null);
            }}
            className={`border-b-2 px-4 py-2 text-sm font-medium ${
              tab === t.id
                ? "border-indigo-600 text-indigo-700 dark:text-indigo-300"
                : "border-transparent text-gray-600 hover:text-gray-900 dark:text-slate-400"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {(tab === "customers" || tab === "equipment") && (
        <div className="max-w-xl rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-900">
          {tab === "equipment" && (
            <p className="mb-4 text-sm text-gray-600 dark:text-slate-400">
              Equipment is linked to customers by phone or email. Import
              customers first.
            </p>
          )}
          <button
            type="button"
            onClick={() =>
              void handleDownloadTemplate(
                tab === "customers" ? "customers" : "equipment",
              )
            }
            className="mb-4 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300"
          >
            Download template
          </button>
          <div className="mb-4">
            <input
              type="file"
              accept=".csv"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-gray-600"
            />
          </div>
          <label className="mb-4 flex items-center gap-2 text-sm text-gray-700 dark:text-slate-300">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
            />
            Dry run (validate only, no database writes)
          </label>
          <button
            type="button"
            disabled={loading || !file}
            onClick={() => void handleCsvImport()}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {loading ? "Importing…" : "Import CSV"}
          </button>
          {result && <ResultPanel result={result} />}
        </div>
      )}

      {tab === "drive" && (
        <div className="max-w-xl rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <p className="mb-4 text-sm text-gray-600 dark:text-slate-400">
            Drop PDF, Word, or text files in your Drive folder. They sync
            automatically every 30 minutes.
          </p>
          <p className="mb-2 text-sm text-gray-700 dark:text-slate-300">
            Google connected: {driveStatus?.connected ? "Yes" : "No"}
          </p>
          {driveStatus?.folder_url ? (
            <p className="mb-4 text-sm">
              <a
                href={driveStatus.folder_url}
                target="_blank"
                rel="noreferrer"
                className="text-indigo-600 underline dark:text-indigo-400"
              >
                Open in Drive
              </a>
              {" · "}
              {driveStatus.file_count} file(s)
              {driveStatus.last_sync
                ? ` · Last sync: ${new Date(driveStatus.last_sync).toLocaleString()}`
                : ""}
            </p>
          ) : (
            <p className="mb-4 text-sm text-gray-500">No folder configured yet.</p>
          )}
          {driveMessage && (
            <p className="mb-4 text-sm text-green-700 dark:text-green-300">
              {driveMessage}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={driveLoading}
              onClick={() => void handleDriveSetup()}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              Set Up Drive Folder
            </button>
            <button
              type="button"
              disabled={driveLoading || !driveStatus?.folder_id}
              onClick={() => void handleDriveSync()}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300 disabled:opacity-50"
            >
              Sync Now
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
