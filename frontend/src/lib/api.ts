const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

export const startAudit = async (url: string, max_pages = 50): Promise<{ audit_id: string }> => {
  const r = await fetch(`${BASE}/audit/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, max_pages }),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? "Failed to start audit");
  return r.json();
};

export const getAuditStatus = async (id: string) => {
  const r = await fetch(`${BASE}/audit/${id}/status`);
  if (!r.ok) throw new Error("Failed to fetch status");
  return r.json();
};

export const getAuditReport = async (id: string) => {
  const r = await fetch(`${BASE}/audit/${id}/report`);
  if (!r.ok) throw new Error("Failed to fetch report");
  return r.json();
};

export const listAudits = async () => {
  const r = await fetch(`${BASE}/audit/list`);
  if (!r.ok) throw new Error("Failed to list audits");
  return r.json();
};

export const getExcelUrl = (id: string) => `${BASE}/audit/${id}/excel`;

export const getWorkflowLog = async (id: string) => {
  const r = await fetch(`${BASE}/audit/${id}/workflow-log`);
  if (!r.ok) throw new Error("Failed to fetch workflow log");
  return r.json();
};
