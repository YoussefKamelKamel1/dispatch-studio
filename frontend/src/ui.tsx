import { useEffect, useRef, type ReactNode } from "react";
import { Check, Globe2, Linkedin, LoaderCircle, Mail, X } from "lucide-react";
export function ChannelIcon({
  channel,
  size = 16,
}: {
  channel: string;
  size?: number;
}) {
  return channel === "website" ? (
    <Globe2 size={size} />
  ) : channel === "linkedin" ? (
    <Linkedin size={size} />
  ) : (
    <Mail size={size} />
  );
}
export function Brand() {
  return (
    <div className="brand">
      <span className="brand-symbol">
        <span />
        <span />
        <span />
      </span>
      <span>
        dispatch<span className="brand-stop">.</span>
      </span>
    </div>
  );
}
export function Status({ status }: { status: string }) {
  const names: Record<string, string> = {
    draft: "Draft",
    ready: "Ready for review",
    published: "Published",
    publishing: "Publishing",
    partial: "Partially published",
    failed: "Needs attention",
    generation_failed: "Generation failed",
    generating: "Generating drafts",
    queued_generation: "Generation queued",
    rejected: "Changes requested",
    succeeded: "Published",
    uncertain: "Outcome uncertain",
    queued: "Queued",
    reconciling: "Checking outcome",
    cancelled: "Cancelled",
  };
  return (
    <span className={"status " + status}>
      {[
        "publishing",
        "generating",
        "queued_generation",
        "reconciling",
      ].includes(status) ? (
        <LoaderCircle size={11} className="spin" />
      ) : ["published", "succeeded"].includes(status) ? (
        <Check size={11} />
      ) : (
        <span />
      )}
      {names[status] || status}
    </span>
  );
}
export function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    ref.current?.focus();
    function handler(e: KeyboardEvent) {
      if (e.key === "Escape") closeRef.current();
      if (e.key === "Tab") {
        const els = ref.current?.querySelectorAll<HTMLElement>(
          "button:not(:disabled),input:not(:disabled),select,textarea,a[href]",
        );
        if (!els?.length) return;
        const first = els[0],
          last = els[els.length - 1];
        if (
          e.shiftKey &&
          (document.activeElement === first ||
            document.activeElement === ref.current)
        ) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", handler);
    return () => {
      document.removeEventListener("keydown", handler);
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, []);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.currentTarget === e.target) onClose();
      }}
    >
      <div
        ref={ref}
        tabIndex={-1}
        className={"modal " + (wide ? "wide" : "")}
        role="dialog"
        aria-label={title}
        aria-modal="true"
      >
        <div className="modal-header">
          <div>
            <span className="eyebrow">DISPATCH / DISPATCH</span>
            <h2>{title}</h2>
          </div>
          <button
            className="icon-button"
            onClick={onClose}
            aria-label="Close dialog"
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
