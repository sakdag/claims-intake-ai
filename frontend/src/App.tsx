import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  authConfigured,
  clearSession,
  loadSession,
  login,
  type Session,
} from "./auth";
import "./styles.css";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://127.0.0.1:8000";

const FIELD_META: Record<string, { label: string; help: string }> = {
  claimId: {
    label: "Claim ID",
    help: "Correct only if the ID on the FNOL/email does not match this case.",
  },
  policyId: {
    label: "Policy number",
    help: "Must match the policy document. Fix typos or OCR misses.",
  },
  dateOfLoss: {
    label: "Date of loss",
    help: "Incident / loss date from the claim form or notice.",
  },
  dateOfReported: {
    label: "Date reported",
    help: "When the insured reported the claim (often later than loss date).",
  },
  lossEvent: {
    label: "Loss event",
    help: "Short description of what happened (water damage, fire, theft, etc.).",
  },
  claimant: {
    label: "Claimant / insured",
    help: "Person or household named on the claim.",
  },
  product: {
    label: "Product / cover",
    help: "Policy product line if stated (e.g. home contents).",
  },
};

type QueueCase = {
  claim_id: string;
  status: string;
  summary?: string | null;
  waiting_on_adjuster: boolean;
  n_conflicts: number;
  updated_at?: string | null;
};

type FieldRow = {
  name: string;
  ai_value: string | null;
  citation: string | null;
  document_id: string | null;
  corrected_value: string | null;
  effective_value: string | null;
};

type Enriched = {
  case: Record<string, unknown>;
  audit: Array<{ component?: string; action?: string; created_at?: string; output?: unknown }>;
  review: {
    phase: string;
    phase_label: string;
    waiting_on_adjuster: boolean;
    can_approve_send: boolean;
    can_reject: boolean;
    instruction?: string;
    fields: FieldRow[];
    documents: Array<Record<string, unknown>>;
    conflicts: Array<Record<string, unknown>>;
    policy_checks: Array<Record<string, unknown>>;
    draft: string | null;
    summary?: string | null;
    execution_arn?: string | null;
    outbound_message_id?: string | null;
  };
};

type Flash = { kind: "ok" | "err"; text: string } | null;

function chipClass(phase: string, waiting: boolean): string {
  if (waiting || phase === "awaiting_adjuster") return "pending";
  if (phase === "complete") return "ok";
  if (phase === "rejected") return "warn";
  return "pending";
}

function docLabel(d: Record<string, unknown>): string {
  return String(
    d.document_type || d.doc_type || d.predicted_type || d.label || d.document_id || d.doc_id || "document",
  );
}

function checkBadge(c: Record<string, unknown>): { cls: string; label: string } {
  const status = String(c.status || "").toUpperCase();
  if (status === "PASSED" || status === "PASS" || c.passed === true) {
    return { cls: "pass", label: "Pass" };
  }
  if (status === "UNRESOLVABLE") {
    return { cls: "human", label: "Human" };
  }
  return { cls: "fail", label: status === "FAILED" ? "Fail" : "Review" };
}

async function apiFetch(path: string, session: Session | null, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  if (session?.idToken && authConfigured()) {
    headers.set("Authorization", `Bearer ${session.idToken}`);
  }
  return fetch(`${API_BASE}${path}`, { ...init, headers });
}

export default function App() {
  const needsAuth = authConfigured();
  const [session, setSession] = useState<Session | null>(() => loadSession());
  const [username, setUsername] = useState("adjuster");
  const [password, setPassword] = useState("");
  const [queue, setQueue] = useState<QueueCase[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<Enriched | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [rejectReason, setRejectReason] = useState("Needs more investigation before outbound");
  const [loading, setLoading] = useState(false);
  const [flash, setFlash] = useState<Flash>(null);

  const authed = !needsAuth || Boolean(session);

  const loadQueue = useCallback(async () => {
    const res = await apiFetch("/queue", session);
    if (res.status === 401 || res.status === 403) {
      clearSession();
      setSession(null);
      throw new Error("Session expired — sign in again");
    }
    if (!res.ok) throw new Error(`Queue failed (${res.status})`);
    const data = (await res.json()) as { cases: QueueCase[] };
    const cases = data.cases ?? [];
    setQueue(cases);
    setSelectedId((prev) => prev ?? (cases[0]?.claim_id ?? null));
  }, [session]);

  const loadCase = useCallback(
    async (claimId: string) => {
      setLoading(true);
      setFlash(null);
      try {
        const res = await apiFetch(`/cases/${claimId}`, session);
        if (!res.ok) throw new Error(`Case load failed (${res.status})`);
        const data = (await res.json()) as Enriched;
        setDetail(data);
        const next: Record<string, string> = {};
        for (const f of data.review.fields) {
          next[f.name] = String(f.effective_value ?? "");
        }
        setEdits(next);
      } catch (err) {
        setFlash({ kind: "err", text: err instanceof Error ? err.message : String(err) });
      } finally {
        setLoading(false);
      }
    },
    [session],
  );

  useEffect(() => {
    if (!authed) return;
    void loadQueue().catch((err) =>
      setFlash({ kind: "err", text: err instanceof Error ? err.message : String(err) }),
    );
    const t = window.setInterval(() => {
      void loadQueue().catch(() => undefined);
    }, 6000);
    return () => window.clearInterval(t);
  }, [authed, loadQueue]);

  useEffect(() => {
    if (authed && selectedId) void loadCase(selectedId);
  }, [authed, selectedId, loadCase]);

  const steps = useMemo(() => {
    const phase = detail?.review.phase ?? "processing";
    const waiting = Boolean(detail?.review.waiting_on_adjuster);
    return [
      { n: "1", label: "Intake", done: true, active: false },
      { n: "2", label: "AI extract & checks", done: phase !== "processing", active: phase === "processing" },
      {
        n: "3",
        label: "Your review",
        done: ["complete", "sending", "rejected"].includes(phase),
        active: waiting || phase === "awaiting_adjuster" || phase === "ai_done",
      },
      {
        n: "4",
        label: "Outbound / close",
        done: phase === "complete",
        active: phase === "sending",
      },
    ];
  }, [detail]);

  async function onLogin(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setFlash(null);
    try {
      const s = await login(username, password);
      setSession(s);
      setFlash({ kind: "ok", text: `Signed in as ${s.username}` });
    } catch (err) {
      setFlash({ kind: "err", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setLoading(false);
    }
  }

  async function saveCorrections(e: FormEvent) {
    e.preventDefault();
    if (!detail) return;
    const claimId = String(detail.case.claim_id);
    const changed: Record<string, string> = {};
    for (const f of detail.review.fields) {
      const current = edits[f.name] ?? "";
      const baseline = String(f.effective_value ?? "");
      if (current !== baseline) changed[f.name] = current;
    }
    if (!Object.keys(changed).length) {
      setFlash({ kind: "ok", text: "No field changes to save — working values already match." });
      return;
    }
    setLoading(true);
    setFlash(null);
    try {
      const res = await apiFetch(`/cases/${claimId}/corrections`, session, {
        method: "POST",
        body: JSON.stringify({
          fields: changed,
          note: "Adjuster corrected AI extraction against source citation",
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as Enriched;
      setDetail(data);
      setFlash({
        kind: "ok",
        text: `Saved ${Object.keys(changed).length} correction(s). AI originals stay in audit; your values are now the working fields.`,
      });
      await loadQueue();
    } catch (err) {
      setFlash({ kind: "err", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setLoading(false);
    }
  }

  async function approveAndSend(skipEmail: boolean) {
    if (!detail) return;
    const claimId = String(detail.case.claim_id);
    setLoading(true);
    setFlash(null);
    try {
      const res = await apiFetch(`/cases/${claimId}/approve-and-send`, session, {
        method: "POST",
        body: JSON.stringify({ skip_email: skipEmail }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as Enriched;
      setDetail(data);
      setFlash({
        kind: "ok",
        text: skipEmail
          ? "Review approved. Workflow resumed without sending email."
          : "Review approved. Workflow resumed — SES will send the missing-docs draft.",
      });
      await loadQueue();
    } catch (err) {
      setFlash({ kind: "err", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setLoading(false);
    }
  }

  async function rejectReview() {
    if (!detail) return;
    const claimId = String(detail.case.claim_id);
    setLoading(true);
    setFlash(null);
    try {
      const res = await apiFetch(`/cases/${claimId}/review/reject`, session, {
        method: "POST",
        body: JSON.stringify({ reason: rejectReason }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as Enriched;
      setDetail(data);
      setFlash({ kind: "ok", text: "Case rejected. Step Functions task failed; case closed." });
      await loadQueue();
    } catch (err) {
      setFlash({ kind: "err", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setLoading(false);
    }
  }

  const review = detail?.review;

  if (needsAuth && !session) {
    return (
      <div className="app-shell">
        <header className="topbar">
          <div>
            <strong>Elm &amp; Stone</strong>
            <span> · Adjuster sign-in</span>
          </div>
          <span>Hosted API · Cognito</span>
        </header>
        <main className="main" style={{ maxWidth: 420, margin: "3rem auto" }}>
          <section className="card">
            <h3>Sign in</h3>
            <p className="hint">Use your Cognito adjuster credentials to open the review queue.</p>
            <form onSubmit={(e) => void onLogin(e)}>
              <div className="actions" style={{ flexDirection: "column", alignItems: "stretch" }}>
                <label>
                  Username
                  <input value={username} onChange={(ev) => setUsername(ev.target.value)} autoComplete="username" />
                </label>
                <label>
                  Password
                  <input
                    type="password"
                    value={password}
                    onChange={(ev) => setPassword(ev.target.value)}
                    autoComplete="current-password"
                  />
                </label>
                <button type="submit" disabled={loading}>
                  Sign in
                </button>
              </div>
            </form>
            {flash && <div className={`flash ${flash.kind}`}>{flash.text}</div>}
            <p className="cite" style={{ marginTop: "0.75rem" }}>
              API: {API_BASE}
            </p>
          </section>
        </main>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <strong>Elm &amp; Stone</strong>
          <span> · Adjuster review console</span>
        </div>
        <span>
          {session ? (
            <>
              {session.username} ·{" "}
              <button
                type="button"
                className="secondary"
                style={{ padding: "0.2rem 0.55rem", fontSize: "0.85rem" }}
                onClick={() => {
                  clearSession();
                  setSession(null);
                  setDetail(null);
                  setQueue([]);
                }}
              >
                Sign out
              </button>
            </>
          ) : (
            "Local API (no Cognito env)"
          )}
        </span>
      </header>

      <div className="workspace">
        <aside className="queue">
          <div className="queue-head">
            <h2>Queue</h2>
            <button type="button" className="secondary" onClick={() => void loadQueue()}>
              Refresh
            </button>
          </div>
          <ul className="queue-list">
            {queue.map((item) => (
              <li key={item.claim_id}>
                <button
                  type="button"
                  className={`queue-item${selectedId === item.claim_id ? " active" : ""}`}
                  onClick={() => setSelectedId(item.claim_id)}
                >
                  <span className="id">{item.claim_id}</span>
                  <span className="sub">
                    {item.n_conflicts ? `${item.n_conflicts} conflict(s)` : "No conflicts"} ·{" "}
                    {item.updated_at ? new Date(item.updated_at).toLocaleString() : "—"}
                  </span>
                  <span className={`chip ${item.waiting_on_adjuster ? "pending" : "ok"}`}>
                    {item.waiting_on_adjuster ? "Waiting on you" : item.status}
                  </span>
                </button>
              </li>
            ))}
            {!queue.length && (
              <li className="empty">No open cases. Upload a claim package to the demo inbox.</li>
            )}
          </ul>
        </aside>

        <main className="main">
          {!review && <p className="empty">Select a claim from the queue.</p>}
          {review && detail && (
            <>
              <div className="case-header">
                <div>
                  <h1>Claim {String(detail.case.claim_id)}</h1>
                  <p>
                    {review.instruction ||
                      review.summary ||
                      "Compare each AI field to its citation. Correct mistakes, then approve & send the draft — or reject."}
                  </p>
                  {review.summary && (
                    <p className="cite" style={{ marginTop: "0.35rem" }}>
                      {review.summary}
                    </p>
                  )}
                </div>
                <span className={`chip ${chipClass(review.phase, review.waiting_on_adjuster)}`}>
                  {review.phase_label}
                </span>
              </div>

              <div className="steps">
                {steps.map((s) => (
                  <div
                    key={s.n}
                    className={`step${s.active ? " active" : ""}${s.done && !s.active ? " done" : ""}`}
                  >
                    <div className="n">Step {s.n}</div>
                    <div>{s.label}</div>
                  </div>
                ))}
              </div>

              <div className="grid-2">
                <section className="card">
                  <h3>Field workspace</h3>
                  <p className="hint">
                    <strong>What “correct a field” means:</strong> the AI filled these from documents.
                    If the <em>Working value</em> matches the citation, leave it. If it is wrong, edit
                    the box and click <em>Save corrections</em>. That only updates structured data —
                    it does <em>not</em> approve coverage or send email.
                  </p>
                  <form onSubmit={(e) => void saveCorrections(e)}>
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Field</th>
                          <th>AI extracted</th>
                          <th>Working value</th>
                          <th>Source citation</th>
                        </tr>
                      </thead>
                      <tbody>
                        {review.fields.map((f) => {
                          const meta = FIELD_META[f.name] ?? {
                            label: f.name,
                            help: "Correct if AI missed or misread the source.",
                          };
                          const ai = f.ai_value == null || f.ai_value === "" ? "—" : String(f.ai_value);
                          const corrected = f.corrected_value != null;
                          return (
                            <tr key={f.name}>
                              <td>
                                <div>{meta.label}</div>
                                <div className="cite">{meta.help}</div>
                                {corrected && <span className="badge human">Corrected</span>}
                              </td>
                              <td className="cite">{ai}</td>
                              <td>
                                <input
                                  value={edits[f.name] ?? ""}
                                  onChange={(ev) =>
                                    setEdits((prev) => ({ ...prev, [f.name]: ev.target.value }))
                                  }
                                  aria-label={meta.label}
                                />
                              </td>
                              <td className="cite">
                                {f.citation || "No citation captured"}
                                {f.document_id ? (
                                  <>
                                    <br />
                                    <span>doc: {f.document_id}</span>
                                  </>
                                ) : null}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    <div className="actions">
                      <button type="submit" disabled={loading}>
                        Save corrections
                      </button>
                      <span className="cite">Only changed fields are written to the audit trail.</span>
                    </div>
                  </form>
                </section>

                <div style={{ display: "grid", gap: "1rem" }}>
                  <section className="card">
                    <h3>Policy checks</h3>
                    <p className="hint">Intake / eligibility signals — not a coverage decision.</p>
                    {review.policy_checks.map((c, i) => {
                      const badge = checkBadge(c);
                      return (
                        <div className="check-row" key={i}>
                          <div>
                            <span className={`badge ${badge.cls}`}>{badge.label}</span>{" "}
                            {String(c.rule_id || c.name || c.check || "check")}
                          </div>
                          <div className="cite">
                            {String(c.reason || c.detail || c.message || "")}
                          </div>
                        </div>
                      );
                    })}
                    {!review.policy_checks.length && <p className="cite">No checks recorded.</p>}
                  </section>

                  <section className="card">
                    <h3>Conflicts</h3>
                    {review.conflicts.map((c, i) => (
                      <div className="conflict-row" key={i}>
                        <strong>{String(c.kind || c.field || "amount")}</strong>
                        <span className="cite">
                          {String(c.summary || c.reason || c.message || JSON.stringify(c))}
                        </span>
                      </div>
                    ))}
                    {!review.conflicts.length && <p className="cite">No amount conflicts flagged.</p>}
                  </section>

                  <section className="card">
                    <h3>Documents</h3>
                    {review.documents.map((d, i) => (
                      <div className="doc-row" key={i}>
                        <strong>{docLabel(d)}</strong>
                        <span className="cite">
                          {String(d.document_id || d.doc_id || "")}
                          {d.confidence != null ? ` · confidence ${d.confidence}` : ""}
                        </span>
                      </div>
                    ))}
                    {!review.documents.length && <p className="cite">No classifications yet.</p>}
                  </section>
                </div>
              </div>

              <section className="card" style={{ marginTop: "1rem" }}>
                <h3>Decision — release or reject</h3>
                <p className="hint">
                  After you are satisfied with the field workspace, either approve the draft
                  missing-documents email (resumes Step Functions → SES) or reject the case.
                </p>
                <div className="draft">{review.draft || "No missing-docs draft on this case."}</div>
                <div className="actions">
                  <button
                    type="button"
                    disabled={loading || !review.can_approve_send}
                    onClick={() => void approveAndSend(false)}
                  >
                    Approve &amp; send email
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    disabled={loading || !review.can_approve_send}
                    onClick={() => void approveAndSend(true)}
                  >
                    Approve without email
                  </button>
                  <button
                    type="button"
                    className="danger"
                    disabled={loading || !review.can_reject}
                    onClick={() => void rejectReview()}
                  >
                    Reject case
                  </button>
                </div>
                <div className="actions">
                  <label className="cite">
                    Reject reason{" "}
                    <input
                      value={rejectReason}
                      onChange={(ev) => setRejectReason(ev.target.value)}
                      style={{ minWidth: "22rem" }}
                    />
                  </label>
                </div>
                {!review.waiting_on_adjuster && (
                  <p className="cite" style={{ marginTop: "0.75rem" }}>
                    Workflow is not paused on a task token right now — approve/reject stay disabled
                    until Step Functions reaches WaitForHumanReview.
                  </p>
                )}
                {flash && <div className={`flash ${flash.kind}`}>{flash.text}</div>}
              </section>

              <section className="audit">
                <details>
                  <summary>Audit trail ({detail.audit.length})</summary>
                  {detail.audit.map((a, i) => (
                    <div className="audit-item" key={i}>
                      {a.created_at || "—"} · {a.component}/{a.action}
                    </div>
                  ))}
                </details>
              </section>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
