import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  Inbox,
  Loader2,
  LogOut,
  Mail,
  RefreshCw,
  Save,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { API_BASE, apiFetch } from "./api";
import {
  authConfigured,
  clearSession,
  loadSession,
  login,
  type Session,
} from "./auth";
import { Badge, Button, Field, Panel, TextInput, cx } from "./ui";
import { FIELD_META, type Enriched, type Flash, type QueueCase } from "./types";
import "./styles.css";

function docLabel(d: Record<string, unknown>): string {
  return String(
    d.document_type || d.doc_type || d.predicted_type || d.label || d.document_id || "document",
  );
}

function checkTone(c: Record<string, unknown>): { tone: "ok" | "fail" | "wait"; label: string } {
  const status = String(c.status || "").toUpperCase();
  if (status === "PASSED" || status === "PASS" || c.passed === true) return { tone: "ok", label: "Pass" };
  if (status === "UNRESOLVABLE") return { tone: "wait", label: "Human" };
  return { tone: "fail", label: status === "FAILED" ? "Fail" : "Review" };
}

function phaseTone(phase: string, waiting: boolean): "wait" | "ok" | "warn" | "neutral" {
  if (waiting || phase === "awaiting_adjuster") return "wait";
  if (phase === "complete") return "ok";
  if (phase === "rejected") return "warn";
  return "neutral";
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
  const [filter, setFilter] = useState<"all" | "waiting">("all");
  const [rightTab, setRightTab] = useState<"signals" | "docs" | "draft">("signals");

  const authed = !needsAuth || Boolean(session);

  const loadQueue = useCallback(async () => {
    try {
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
      setFlash((prev) => (prev?.kind === "err" && prev.text.startsWith("Queue") ? null : prev));
    } catch (err) {
      const text = err instanceof Error ? err.message : String(err);
      setFlash({
        kind: "err",
        text: text.includes("Failed to fetch")
          ? "Queue: cannot reach API (CORS/network). Check API Gateway and refresh."
          : `Queue: ${text}`,
      });
      throw err;
    }
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
        for (const f of data.review.fields) next[f.name] = String(f.effective_value ?? "");
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
    const t = window.setInterval(() => void loadQueue().catch(() => undefined), 6000);
    return () => window.clearInterval(t);
  }, [authed, loadQueue]);

  useEffect(() => {
    if (authed && selectedId) void loadCase(selectedId);
  }, [authed, selectedId, loadCase]);

  const filteredQueue = useMemo(() => {
    if (filter === "waiting") return queue.filter((c) => c.waiting_on_adjuster);
    return queue;
  }, [queue, filter]);

  const waitingCount = queue.filter((c) => c.waiting_on_adjuster).length;
  const dirtyCount = useMemo(() => {
    if (!detail) return 0;
    return detail.review.fields.filter((f) => (edits[f.name] ?? "") !== String(f.effective_value ?? "")).length;
  }, [detail, edits]);

  const steps = useMemo(() => {
    const phase = detail?.review.phase ?? "processing";
    const waiting = Boolean(detail?.review.waiting_on_adjuster);
    return [
      { label: "Intake", done: true, active: false },
      { label: "AI extract", done: phase !== "processing", active: phase === "processing" },
      {
        label: "Human review",
        done: ["complete", "sending", "rejected"].includes(phase),
        active: waiting || phase === "awaiting_adjuster" || phase === "ai_done",
      },
      { label: "Outbound", done: phase === "complete", active: phase === "sending" },
    ];
  }, [detail]);

  async function onLogin(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setFlash(null);
    try {
      const s = await login(username, password);
      setSession(s);
    } catch (err) {
      setFlash({ kind: "err", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setLoading(false);
    }
  }

  async function saveCorrections(e?: FormEvent) {
    e?.preventDefault();
    if (!detail) return;
    const claimId = String(detail.case.claim_id);
    const changed: Record<string, string> = {};
    for (const f of detail.review.fields) {
      const current = edits[f.name] ?? "";
      if (current !== String(f.effective_value ?? "")) changed[f.name] = current;
    }
    if (!Object.keys(changed).length) {
      setFlash({ kind: "ok", text: "Nothing to save — working values already match." });
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
      setDetail((await res.json()) as Enriched);
      setFlash({ kind: "ok", text: `Saved ${Object.keys(changed).length} correction(s).` });
      await loadQueue();
    } catch (err) {
      setFlash({ kind: "err", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setLoading(false);
    }
  }

  async function approveAndSend(skipEmail: boolean) {
    if (!detail) return;
    setLoading(true);
    setFlash(null);
    try {
      const res = await apiFetch(`/cases/${String(detail.case.claim_id)}/approve-and-send`, session, {
        method: "POST",
        body: JSON.stringify({ skip_email: skipEmail }),
      });
      if (!res.ok) throw new Error(await res.text());
      setDetail((await res.json()) as Enriched);
      setFlash({
        kind: "ok",
        text: skipEmail ? "Approved — workflow resumed (email skipped)." : "Approved — SES will send the draft.",
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
    setLoading(true);
    setFlash(null);
    try {
      const res = await apiFetch(`/cases/${String(detail.case.claim_id)}/review/reject`, session, {
        method: "POST",
        body: JSON.stringify({ reason: rejectReason }),
      });
      if (!res.ok) throw new Error(await res.text());
      setDetail((await res.json()) as Enriched);
      setFlash({ kind: "ok", text: "Case rejected and closed." });
      await loadQueue();
    } catch (err) {
      setFlash({ kind: "err", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setLoading(false);
    }
  }

  if (needsAuth && !session) {
    return (
      <div className="flex min-h-full items-center justify-center p-6">
        <div className="animate-fade-up w-full max-w-md rounded-3xl border border-line bg-panel/95 p-8 shadow-[0_24px_60px_rgba(18,26,22,0.08)]">
          <div className="mb-6">
            <p className="font-display text-3xl font-medium tracking-tight text-brand">Elm &amp; Stone</p>
            <p className="mt-1 text-sm text-muted">Adjuster workspace · sign in to continue</p>
          </div>
          <form className="grid gap-4" onSubmit={(e) => void onLogin(e)}>
            <Field label="Username">
              <TextInput value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
            </Field>
            <Field label="Password">
              <TextInput
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </Field>
            <Button type="submit" disabled={loading} className="mt-1 w-full">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Sign in
            </Button>
          </form>
          {flash && (
            <p className={cx("mt-4 rounded-lg px-3 py-2 text-sm", flash.kind === "ok" ? "bg-ok-soft text-ok" : "bg-rose-soft text-rose")}>
              {flash.text}
            </p>
          )}
          <p className="mt-5 truncate text-xs text-muted">{API_BASE}</p>
        </div>
      </div>
    );
  }

  const review = detail?.review;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex shrink-0 items-center justify-between gap-4 border-b border-line/80 bg-[#0f2b21] px-4 py-3 text-[#f4f7f5]">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/10 ring-1 ring-white/15">
            <ShieldCheck className="h-4 w-4" />
          </div>
          <div>
            <p className="font-display text-lg leading-none tracking-tight">Elm &amp; Stone</p>
            <p className="mt-1 text-xs text-[#b7c8bf]">Claims intake · human review</p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <Badge tone="ok">{waitingCount} waiting</Badge>
          <span className="hidden text-[#b7c8bf] sm:inline">{session?.username ?? "local operator"}</span>
          {session && (
            <Button
              variant="ghost"
              className="text-[#d7e4dd] hover:bg-white/10 hover:text-white"
              onClick={() => {
                clearSession();
                setSession(null);
                setDetail(null);
                setQueue([]);
              }}
            >
              <LogOut className="h-4 w-4" />
              Sign out
            </Button>
          )}
        </div>
      </header>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[300px_minmax(0,1fr)_320px]">
        {/* Queue — inbox template */}
        <aside className="flex min-h-0 flex-col border-r border-line/80 bg-white/55 backdrop-blur">
          <div className="flex items-center justify-between gap-2 border-b border-line/70 px-3 py-3">
            <div className="flex items-center gap-2">
              <Inbox className="h-4 w-4 text-brand" />
              <h2 className="text-sm font-semibold">Review queue</h2>
            </div>
            <Button variant="ghost" className="!px-2 !py-1.5" onClick={() => void loadQueue()} title="Refresh">
              <RefreshCw className={cx("h-4 w-4", loading && "animate-spin")} />
            </Button>
          </div>
          <div className="flex gap-1 border-b border-line/70 p-2">
            {(
              [
                ["all", `All (${queue.length})`],
                ["waiting", `Waiting (${waitingCount})`],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setFilter(key)}
                className={cx(
                  "flex-1 rounded-lg px-2 py-1.5 text-xs font-semibold transition",
                  filter === key ? "bg-brand text-white" : "text-muted hover:bg-brand-soft",
                )}
              >
                {label}
              </button>
            ))}
          </div>
          <ul className="min-h-0 flex-1 space-y-1 overflow-auto p-2">
            {filteredQueue.map((item) => {
              const active = selectedId === item.claim_id;
              return (
                <li key={item.claim_id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(item.claim_id)}
                    className={cx(
                      "w-full rounded-xl border px-3 py-3 text-left transition",
                      active
                        ? "border-brand/30 bg-brand-soft shadow-sm"
                        : "border-transparent bg-transparent hover:border-line hover:bg-white/80",
                    )}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="font-semibold tracking-tight">{item.claim_id}</span>
                      <Badge tone={item.waiting_on_adjuster ? "wait" : "neutral"} pulse={item.waiting_on_adjuster}>
                        {item.waiting_on_adjuster ? "You" : item.status}
                      </Badge>
                    </div>
                    <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted">
                      {item.summary || "No summary yet"}
                    </p>
                    <p className="mt-2 text-[11px] text-muted">
                      {item.n_conflicts ? `${item.n_conflicts} conflicts` : "No conflicts"}
                      {item.updated_at ? ` · ${new Date(item.updated_at).toLocaleString()}` : ""}
                    </p>
                  </button>
                </li>
              );
            })}
            {!filteredQueue.length && (
              <li className="px-3 py-8 text-center text-sm text-muted">
                {filter === "waiting" ? "No cases waiting on you." : "Queue empty — upload a claim to the inbox."}
              </li>
            )}
          </ul>
        </aside>

        {/* Main review */}
        <main className="relative flex min-h-0 flex-col">
          {!review && (
            <div className="flex flex-1 items-center justify-center p-8 text-sm text-muted">
              Select a claim from the queue to begin review.
            </div>
          )}
          {review && detail && (
            <>
              <div className="animate-fade-up min-h-0 flex-1 overflow-auto px-4 py-4 pb-36 sm:px-6">
                <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h1 className="font-display text-2xl font-medium tracking-tight sm:text-3xl">
                        Claim {String(detail.case.claim_id)}
                      </h1>
                      <Badge tone={phaseTone(review.phase, review.waiting_on_adjuster)} pulse={review.waiting_on_adjuster}>
                        {review.phase_label}
                      </Badge>
                    </div>
                    <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
                      {review.instruction ||
                        "Compare AI values to citations. Correct only mistakes, then release or reject."}
                    </p>
                    {review.summary && <p className="mt-1 max-w-2xl text-xs text-muted/90">{review.summary}</p>}
                  </div>
                </div>

                <ol className="mb-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {steps.map((s, i) => (
                    <li
                      key={s.label}
                      className={cx(
                        "rounded-xl border px-3 py-2.5",
                        s.active ? "border-brand bg-brand-soft" : "border-line/80 bg-white/70",
                        s.done && !s.active && "opacity-70",
                      )}
                    >
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Step {i + 1}</p>
                      <p className="text-sm font-semibold">{s.label}</p>
                    </li>
                  ))}
                </ol>

                <Panel
                  title="Field workspace"
                  subtitle="Edit a working value only when it disagrees with the citation. Saving does not send email."
                  action={
                    <Button type="button" disabled={loading || dirtyCount === 0} onClick={() => void saveCorrections()}>
                      <Save className="h-4 w-4" />
                      Save{dirtyCount ? ` (${dirtyCount})` : ""}
                    </Button>
                  }
                  className="mb-4"
                >
                  <div className="space-y-3">
                    {review.fields.map((f) => {
                      const meta = FIELD_META[f.name] ?? { label: f.name, help: "Correct if AI misread the source." };
                      const ai = f.ai_value == null || f.ai_value === "" ? "—" : String(f.ai_value);
                      const dirty = (edits[f.name] ?? "") !== String(f.effective_value ?? "");
                      const corrected = f.corrected_value != null;
                      return (
                        <div
                          key={f.name}
                          className={cx(
                            "grid gap-3 rounded-xl border border-line/80 bg-white/80 p-3 md:grid-cols-[160px_1fr_1.1fr]",
                            dirty && "border-amber/40 bg-amber-soft/30",
                          )}
                        >
                          <div>
                            <div className="flex flex-wrap items-center gap-1.5">
                              <p className="text-sm font-semibold">{meta.label}</p>
                              {corrected && <Badge tone="wait">Corrected</Badge>}
                              {dirty && <Badge tone="warn">Unsaved</Badge>}
                            </div>
                            <p className="mt-1 text-xs leading-snug text-muted">{meta.help}</p>
                          </div>
                          <div>
                            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted">AI extracted</p>
                            <p className="rounded-lg bg-paper px-2.5 py-2 text-sm text-ink/90">{ai}</p>
                            <p className="mt-2 text-[10px] font-semibold uppercase tracking-wide text-muted">Citation</p>
                            <p className="mt-1 text-xs leading-relaxed text-muted">
                              {f.citation || "No citation captured"}
                              {f.document_id ? ` · ${f.document_id}` : ""}
                            </p>
                          </div>
                          <div>
                            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted">Working value</p>
                            <TextInput
                              value={edits[f.name] ?? ""}
                              onChange={(ev) => setEdits((prev) => ({ ...prev, [f.name]: ev.target.value }))}
                              aria-label={meta.label}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </Panel>

                {/* Mobile-only context */}
                <div className="space-y-4 lg:hidden">
                  <ContextPanels review={review} />
                </div>

                <details className="mt-4 rounded-2xl border border-line/80 bg-white/60 px-4 py-3">
                  <summary className="cursor-pointer text-sm font-semibold">
                    Audit trail ({detail.audit.length})
                  </summary>
                  <div className="mt-3 max-h-48 space-y-2 overflow-auto">
                    {detail.audit.map((a, i) => (
                      <div key={i} className="border-t border-line/60 pt-2 text-xs text-muted">
                        {a.created_at || "—"} · {a.component}/{a.action}
                      </div>
                    ))}
                  </div>
                </details>
              </div>

              {/* Sticky decision dock */}
              <div className="absolute inset-x-0 bottom-0 border-t border-line/80 bg-panel/95 px-4 py-3 shadow-[0_-12px_40px_rgba(18,26,22,0.06)] backdrop-blur sm:px-6">
                {flash && (
                  <div
                    className={cx(
                      "mb-2 rounded-lg px-3 py-2 text-sm",
                      flash.kind === "ok" ? "bg-ok-soft text-ok" : "bg-rose-soft text-rose",
                    )}
                  >
                    {flash.text}
                  </div>
                )}
                <div className="flex flex-wrap items-center gap-2">
                  <Button disabled={loading || !review.can_approve_send} onClick={() => void approveAndSend(false)}>
                    <Mail className="h-4 w-4" />
                    Approve &amp; send
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={loading || !review.can_approve_send}
                    onClick={() => void approveAndSend(true)}
                  >
                    <CheckCircle2 className="h-4 w-4" />
                    Approve only
                  </Button>
                  <Button variant="danger" disabled={loading || !review.can_reject} onClick={() => void rejectReview()}>
                    <XCircle className="h-4 w-4" />
                    Reject
                  </Button>
                  <TextInput
                    className="min-w-[16rem] flex-1"
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                    placeholder="Reject reason"
                    aria-label="Reject reason"
                  />
                </div>
                {!review.waiting_on_adjuster && (
                  <p className="mt-2 text-xs text-muted">
                    Workflow is not paused on a task token — approve/reject stay disabled until WaitForHumanReview.
                  </p>
                )}
              </div>
            </>
          )}
        </main>

        {/* Right context rail — desktop */}
        <aside className="hidden min-h-0 flex-col border-l border-line/80 bg-white/45 backdrop-blur lg:flex">
          <div className="flex gap-1 border-b border-line/70 p-2">
            {(
              [
                ["signals", "Signals"],
                ["docs", "Documents"],
                ["draft", "Draft"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setRightTab(key)}
                className={cx(
                  "flex-1 rounded-lg px-2 py-1.5 text-xs font-semibold transition",
                  rightTab === key ? "bg-brand text-white" : "text-muted hover:bg-brand-soft",
                )}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1 overflow-auto p-3">
            {review ? (
              rightTab === "signals" ? (
                <SignalsPanel review={review} />
              ) : rightTab === "docs" ? (
                <DocsPanel review={review} />
              ) : (
                <DraftPanel review={review} />
              )
            ) : (
              <p className="p-4 text-sm text-muted">Select a claim to see checks, documents, and draft.</p>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

function ContextPanels({ review }: { review: Enriched["review"] }) {
  return (
    <>
      <SignalsPanel review={review} />
      <DocsPanel review={review} />
      <DraftPanel review={review} />
    </>
  );
}

function SignalsPanel({ review }: { review: Enriched["review"] }) {
  return (
    <div className="space-y-3">
      <Panel title="Policy checks" subtitle="Intake signals — not a coverage decision">
        <div className="space-y-2">
          {review.policy_checks.map((c, i) => {
            const badge = checkTone(c);
            return (
              <div key={i} className="rounded-lg border border-line/70 bg-white/70 px-3 py-2">
                <div className="flex items-center gap-2">
                  <Badge tone={badge.tone}>{badge.label}</Badge>
                  <span className="text-sm font-medium">{String(c.rule_id || c.name || "check")}</span>
                </div>
                <p className="mt-1 text-xs text-muted">{String(c.reason || c.detail || "")}</p>
              </div>
            );
          })}
          {!review.policy_checks.length && <p className="text-sm text-muted">No checks recorded.</p>}
        </div>
      </Panel>
      <Panel title="Conflicts" subtitle="Amount mismatches across documents">
        <div className="space-y-2">
          {review.conflicts.map((c, i) => (
            <div key={i} className="flex gap-2 rounded-lg border border-amber/25 bg-amber-soft/40 px-3 py-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber" />
              <div>
                <p className="text-sm font-semibold">{String(c.kind || c.field || "amount")}</p>
                <p className="text-xs text-muted">{String(c.summary || c.reason || JSON.stringify(c))}</p>
              </div>
            </div>
          ))}
          {!review.conflicts.length && <p className="text-sm text-muted">No amount conflicts flagged.</p>}
        </div>
      </Panel>
    </div>
  );
}

function DocsPanel({ review }: { review: Enriched["review"] }) {
  return (
    <Panel title="Documents" subtitle="AI classifications for this package">
      <div className="space-y-2">
        {review.documents.map((d, i) => (
          <div key={i} className="flex gap-2 rounded-lg border border-line/70 bg-white/70 px-3 py-2">
            <FileText className="mt-0.5 h-4 w-4 shrink-0 text-brand" />
            <div>
              <p className="text-sm font-semibold">{docLabel(d)}</p>
              <p className="text-xs text-muted">
                {String(d.document_id || d.doc_id || "")}
                {d.confidence != null ? ` · ${d.confidence}` : ""}
              </p>
            </div>
          </div>
        ))}
        {!review.documents.length && <p className="text-sm text-muted">No classifications yet.</p>}
      </div>
    </Panel>
  );
}

function DraftPanel({ review }: { review: Enriched["review"] }) {
  return (
    <Panel title="Outbound draft" subtitle="Sent only after Approve & send">
      <pre className="max-h-[28rem] overflow-auto whitespace-pre-wrap rounded-xl bg-paper p-3 text-xs leading-relaxed text-ink/90">
        {review.draft || "No missing-docs draft on this case."}
      </pre>
    </Panel>
  );
}
