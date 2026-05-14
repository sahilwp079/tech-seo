export type AuditStatus = "queued" | "running" | "completed" | "failed";
export type Severity = "critical" | "warning" | "info";

export interface ValidationCheck {
  name: string;
  status: "passed" | "warning" | "failed" | "skipped";
  message: string;
  details: Record<string, string>[];
}

export interface ValidationResult {
  status: "passed" | "warnings" | "failed" | "skipped";
  confidence: number;
  checks: ValidationCheck[];
}

export interface Issue {
  tool_name: string;
  issue_type: string;
  severity: Severity;
  title: string;
  description: string | null;
  affected_url: string | null;
  recommendation: string | null;
}

export interface ReportSection {
  score: number | null;
  issues: Issue[];
  data: Record<string, unknown>;
}

export interface AuditReport {
  audit_id: string;
  url: string;
  status: AuditStatus;
  overall_score: number | null;
  pages_crawled: number;
  validation_status: string | null;
  confidence_score: number | null;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  summary: {
    total_issues: number;
    critical: number;
    warnings: number;
    info: number;
  };
  sections: Record<string, ReportSection>;
  ai_summary: string | null;
}
