"use client";

import { useCallback, useEffect, useState } from "react";

import {
  createServiceItem,
  deleteKnowledgeDocument,
  getKnowledgeDocuments,
  getServiceCatalog,
  updateServiceItem,
  uploadKnowledgeDocument,
  type KnowledgeDocument,
  type ServiceCatalogItem,
} from "@/lib/api";
import { getDashboardOrgId } from "@/lib/config";

const NAMESPACES = [
  "faq_general",
  "troubleshooting",
  "pricing",
  "equipment_manuals",
  "warranty_terms",
];

type Tab = "documents" | "catalog";

function formatPriceRange(item: ServiceCatalogItem): string {
  const base = item.base_price_usd != null ? Number(item.base_price_usd) : null;
  const max = item.price_max_usd != null ? Number(item.price_max_usd) : null;
  if (base != null && max != null) {
    if (base === max) return `$${base}`;
    return `$${base} - $${max}`;
  }
  if (base != null) return `$${base}`;
  if (max != null) return `Up to $${max}`;
  return "Quote";
}

function formatDuration(item: ServiceCatalogItem): string {
  const min = item.duration_minutes_min;
  const max = item.duration_minutes_max;
  if (min != null && max != null) {
    if (min === max) return `${min} min`;
    return `${min}-${max} min`;
  }
  if (min != null) return `${min}+ min`;
  if (max != null) return `Up to ${max} min`;
  return "—";
}

export default function KnowledgePage() {
  const orgId = getDashboardOrgId();
  const [tab, setTab] = useState<Tab>("documents");
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [catalog, setCatalog] = useState<ServiceCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [showAddService, setShowAddService] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadNamespace, setUploadNamespace] = useState("faq_general");
  const [uploadDocId, setUploadDocId] = useState("");

  const [serviceForm, setServiceForm] = useState({
    service_code: "",
    service_name: "",
    category: "diagnostic",
    description: "",
    base_price_usd: "",
    price_max_usd: "",
    price_notes: "",
    duration_minutes_min: "",
    duration_minutes_max: "",
  });

  const loadDocuments = useCallback(async () => {
    const data = await getKnowledgeDocuments(orgId);
    setDocuments(data.items);
  }, [orgId]);

  const loadCatalog = useCallback(async () => {
    const data = await getServiceCatalog(orgId);
    setCatalog(data.items);
  }, [orgId]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (tab === "documents") {
        await loadDocuments();
      } else {
        await loadCatalog();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [tab, loadDocuments, loadCatalog]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function handleUpload(event: React.FormEvent) {
    event.preventDefault();
    if (!uploadFile) return;
    const formData = new FormData();
    formData.append("file", uploadFile);
    formData.append("namespace", uploadNamespace);
    if (uploadDocId.trim()) {
      formData.append("document_id", uploadDocId.trim());
    }
    try {
      await uploadKnowledgeDocument(orgId, formData);
      setShowUpload(false);
      setUploadFile(null);
      setUploadDocId("");
      await loadDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    }
  }

  async function handleDeleteDocument(documentId: string) {
    if (!confirm(`Delete document "${documentId}"?`)) return;
    try {
      await deleteKnowledgeDocument(orgId, documentId);
      await loadDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  async function handleCreateService(event: React.FormEvent) {
    event.preventDefault();
    const payload: Record<string, unknown> = {
      service_code: serviceForm.service_code,
      service_name: serviceForm.service_name,
      category: serviceForm.category,
    };
    if (serviceForm.description) payload.description = serviceForm.description;
    if (serviceForm.base_price_usd) payload.base_price_usd = serviceForm.base_price_usd;
    if (serviceForm.price_max_usd) payload.price_max_usd = serviceForm.price_max_usd;
    if (serviceForm.price_notes) payload.price_notes = serviceForm.price_notes;
    if (serviceForm.duration_minutes_min) {
      payload.duration_minutes_min = Number(serviceForm.duration_minutes_min);
    }
    if (serviceForm.duration_minutes_max) {
      payload.duration_minutes_max = Number(serviceForm.duration_minutes_max);
    }
    try {
      if (editingId) {
        await updateServiceItem(orgId, editingId, payload);
        setEditingId(null);
      } else {
        await createServiceItem(orgId, payload);
      }
      setShowAddService(false);
      resetServiceForm();
      await loadCatalog();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    }
  }

  async function handleDeactivate(serviceId: string) {
    if (!confirm("Deactivate this service?")) return;
    try {
      await updateServiceItem(orgId, serviceId, { is_active: false });
      await loadCatalog();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Deactivate failed");
    }
  }

  function resetServiceForm() {
    setServiceForm({
      service_code: "",
      service_name: "",
      category: "diagnostic",
      description: "",
      base_price_usd: "",
      price_max_usd: "",
      price_notes: "",
      duration_minutes_min: "",
      duration_minutes_max: "",
    });
  }

  function startEdit(item: ServiceCatalogItem) {
    setEditingId(item.service_id);
    setShowAddService(true);
    setServiceForm({
      service_code: item.service_code,
      service_name: item.service_name,
      category: item.category,
      description: item.description ?? "",
      base_price_usd: item.base_price_usd != null ? String(item.base_price_usd) : "",
      price_max_usd: item.price_max_usd != null ? String(item.price_max_usd) : "",
      price_notes: item.price_notes ?? "",
      duration_minutes_min:
        item.duration_minutes_min != null ? String(item.duration_minutes_min) : "",
      duration_minutes_max:
        item.duration_minutes_max != null ? String(item.duration_minutes_max) : "",
    });
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-slate-100">
          Knowledge Base
        </h1>
        <p className="text-sm text-gray-500 dark:text-slate-400">
          Manage agent knowledge documents and service catalog pricing.
        </p>
      </header>

      <div className="flex gap-2 border-b border-gray-200 dark:border-slate-800">
        {(
          [
            ["documents", "Knowledge Documents"],
            ["catalog", "Service Catalog"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-medium ${
              tab === key
                ? "border-b-2 border-indigo-600 text-indigo-600 dark:text-indigo-400"
                : "text-gray-500 hover:text-gray-800 dark:text-slate-400"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {error}
        </div>
      )}

      {tab === "documents" && (
        <div className="space-y-4">
          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => setShowUpload((v) => !v)}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
            >
              Upload Document
            </button>
          </div>

          {showUpload && (
            <form
              onSubmit={handleUpload}
              className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900"
            >
              <div className="grid gap-3 md:grid-cols-2">
                <label className="text-sm">
                  <span className="mb-1 block text-gray-600 dark:text-slate-400">File</span>
                  <input
                    type="file"
                    accept=".md,.txt,.pdf,.docx"
                    onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
                    className="w-full text-sm"
                    required
                  />
                </label>
                <label className="text-sm">
                  <span className="mb-1 block text-gray-600 dark:text-slate-400">Namespace</span>
                  <select
                    value={uploadNamespace}
                    onChange={(e) => setUploadNamespace(e.target.value)}
                    className="w-full rounded border border-gray-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-800"
                  >
                    {NAMESPACES.map((ns) => (
                      <option key={ns} value={ns}>
                        {ns}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="text-sm md:col-span-2">
                  <span className="mb-1 block text-gray-600 dark:text-slate-400">
                    Document ID (optional)
                  </span>
                  <input
                    type="text"
                    value={uploadDocId}
                    onChange={(e) => setUploadDocId(e.target.value)}
                    className="w-full rounded border border-gray-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-800"
                    placeholder="auto-generated from filename if empty"
                  />
                </label>
              </div>
              <div className="mt-3 flex gap-2">
                <button
                  type="submit"
                  className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white"
                >
                  Submit
                </button>
                <button
                  type="button"
                  onClick={() => setShowUpload(false)}
                  className="rounded-lg border px-4 py-2 text-sm dark:border-slate-700"
                >
                  Cancel
                </button>
              </div>
            </form>
          )}

          {loading ? (
            <div className="h-32 animate-pulse rounded bg-gray-100 dark:bg-slate-800" />
          ) : documents.length === 0 ? (
            <p className="rounded-xl border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500 dark:border-slate-700 dark:text-slate-400">
              No documents indexed yet. Upload your first document to give your agent
              knowledge about your business.
            </p>
          ) : (
            <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <table className="min-w-full divide-y divide-gray-200 text-sm">
                <thead className="bg-gray-50 dark:bg-slate-800">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium">Filename</th>
                    <th className="px-4 py-3 text-left font-medium">Namespace</th>
                    <th className="px-4 py-3 text-left font-medium">Chunks</th>
                    <th className="px-4 py-3 text-left font-medium">Uploaded</th>
                    <th className="px-4 py-3 text-left font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-slate-800">
                  {documents.map((doc) => (
                    <tr key={doc.doc_id}>
                      <td className="px-4 py-3">{doc.filename}</td>
                      <td className="px-4 py-3">{doc.namespace}</td>
                      <td className="px-4 py-3">{doc.chunk_count}</td>
                      <td className="px-4 py-3">
                        {new Date(doc.uploaded_at).toLocaleDateString()}
                      </td>
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          onClick={() => handleDeleteDocument(doc.document_id)}
                          className="text-red-600 hover:underline dark:text-red-400"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === "catalog" && (
        <div className="space-y-4">
          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => {
                setEditingId(null);
                resetServiceForm();
                setShowAddService((v) => !v);
              }}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
            >
              Add Service
            </button>
          </div>

          {showAddService && (
            <form
              onSubmit={handleCreateService}
              className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900"
            >
              <div className="grid gap-3 md:grid-cols-2">
                {(
                  [
                    ["service_code", "Service Code"],
                    ["service_name", "Service Name"],
                    ["category", "Category"],
                    ["base_price_usd", "Base Price USD"],
                    ["price_max_usd", "Max Price USD"],
                    ["price_notes", "Price Notes"],
                    ["duration_minutes_min", "Min Duration (min)"],
                    ["duration_minutes_max", "Max Duration (min)"],
                  ] as const
                ).map(([field, label]) => (
                  <label key={field} className="text-sm">
                    <span className="mb-1 block text-gray-600 dark:text-slate-400">{label}</span>
                    <input
                      type="text"
                      value={serviceForm[field]}
                      onChange={(e) =>
                        setServiceForm((prev) => ({ ...prev, [field]: e.target.value }))
                      }
                      className="w-full rounded border border-gray-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-800"
                      required={field === "service_code" || field === "service_name"}
                    />
                  </label>
                ))}
                <label className="text-sm md:col-span-2">
                  <span className="mb-1 block text-gray-600 dark:text-slate-400">
                    Description
                  </span>
                  <textarea
                    value={serviceForm.description}
                    onChange={(e) =>
                      setServiceForm((prev) => ({ ...prev, description: e.target.value }))
                    }
                    className="w-full rounded border border-gray-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-800"
                    rows={2}
                  />
                </label>
              </div>
              <div className="mt-3 flex gap-2">
                <button
                  type="submit"
                  className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white"
                >
                  {editingId ? "Save Changes" : "Create Service"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowAddService(false);
                    setEditingId(null);
                  }}
                  className="rounded-lg border px-4 py-2 text-sm dark:border-slate-700"
                >
                  Cancel
                </button>
              </div>
            </form>
          )}

          {loading ? (
            <div className="h-32 animate-pulse rounded bg-gray-100 dark:bg-slate-800" />
          ) : catalog.filter((s) => s.is_active).length === 0 ? (
            <p className="rounded-xl border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500 dark:border-slate-700 dark:text-slate-400">
              No services in the catalog yet. Add your first service so the voice agent
              can quote exact pricing.
            </p>
          ) : (
            <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <table className="min-w-full divide-y divide-gray-200 text-sm">
                <thead className="bg-gray-50 dark:bg-slate-800">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium">Service</th>
                    <th className="px-4 py-3 text-left font-medium">Category</th>
                    <th className="px-4 py-3 text-left font-medium">Price Range</th>
                    <th className="px-4 py-3 text-left font-medium">Duration</th>
                    <th className="px-4 py-3 text-left font-medium">Status</th>
                    <th className="px-4 py-3 text-left font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-slate-800">
                  {catalog.map((item) => (
                    <tr key={item.service_id}>
                      <td className="px-4 py-3 font-medium">{item.service_name}</td>
                      <td className="px-4 py-3">{item.category}</td>
                      <td className="px-4 py-3">{formatPriceRange(item)}</td>
                      <td className="px-4 py-3">{formatDuration(item)}</td>
                      <td className="px-4 py-3">
                        {item.is_active ? "Active" : "Inactive"}
                      </td>
                      <td className="px-4 py-3 space-x-2">
                        <button
                          type="button"
                          onClick={() => startEdit(item)}
                          className="text-indigo-600 hover:underline dark:text-indigo-400"
                        >
                          Edit
                        </button>
                        {item.is_active && (
                          <button
                            type="button"
                            onClick={() => handleDeactivate(item.service_id)}
                            className="text-red-600 hover:underline dark:text-red-400"
                          >
                            Deactivate
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
