import clsx from "clsx";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

export function cx(...parts: Array<string | false | null | undefined>) {
  return clsx(parts);
}

export function Badge({
  tone = "neutral",
  children,
  pulse,
}: {
  tone?: "neutral" | "wait" | "ok" | "warn" | "fail";
  children: ReactNode;
  pulse?: boolean;
}) {
  const tones = {
    neutral: "bg-white text-muted ring-line",
    wait: "bg-amber-soft text-amber ring-amber/20",
    ok: "bg-ok-soft text-ok ring-brand/15",
    warn: "bg-amber-soft text-amber ring-amber/20",
    fail: "bg-rose-soft text-rose ring-rose/20",
  } as const;
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ring-1",
        tones[tone],
      )}
    >
      {pulse && <span className="h-1.5 w-1.5 rounded-full bg-current animate-pulse-dot" />}
      {children}
    </span>
  );
}

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
}) {
  const variants = {
    primary: "bg-brand text-white hover:bg-[#163c2e] disabled:opacity-40",
    secondary:
      "bg-white text-brand ring-1 ring-line hover:bg-brand-soft disabled:opacity-40",
    ghost: "bg-transparent text-muted hover:bg-white/70 hover:text-ink disabled:opacity-40",
    danger:
      "bg-white text-rose ring-1 ring-rose/30 hover:bg-rose-soft disabled:opacity-40",
  } as const;
  return (
    <button
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-semibold transition disabled:cursor-not-allowed",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}

export function Field({
  label,
  children,
  className,
}: {
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cx("grid gap-1.5 text-sm", className)}>
      <span className="font-medium text-muted">{label}</span>
      {children}
    </label>
  );
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cx(
        "w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink outline-none transition placeholder:text-muted/70 focus:border-brand focus:ring-2 focus:ring-brand/15",
        props.className,
      )}
    />
  );
}

export function Panel({
  title,
  subtitle,
  action,
  children,
  className,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cx(
        "rounded-2xl border border-line/80 bg-panel/90 shadow-[0_1px_0_rgba(18,26,22,0.04),0_12px_32px_rgba(18,26,22,0.04)] backdrop-blur",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3 border-b border-line/70 px-4 py-3">
        <div>
          <h3 className="text-[15px] font-semibold tracking-tight text-ink">{title}</h3>
          {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
        </div>
        {action}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}
