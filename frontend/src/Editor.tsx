import { useEffect, useState, type FormEvent } from "react";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowUpRight,
  Check,
  ChevronDown,
  Copy,
  ExternalLink,
  Eye,
  FileText,
  Globe2,
  History,
  LoaderCircle,
  Mail,
  MoreHorizontal,
  PencilLine,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  AlertTriangle,
} from "lucide-react";
import {
  api,
  channelNames,
  words,
  type Channel,
  type Content,
  type Item,
  type Revision,
  type Connection,
  destinationLabel,
} from "./api";
import { ChannelIcon, Modal, Status } from "./ui";

export default function Editor({
  item,
  onClose,
  onUpdated,
  notify,
  connections,
}: {
  item: Item;
  onClose: () => void;
  onUpdated: () => Promise<void>;
  notify: (message: string) => void;
  connections: Connection[];
}) {
  const [content, setContent] = useState<Content | null>(item.content),
    [channels, setChannels] = useState<string[]>(item.channels),
    [revision, setRevision] = useState(item.revision),
    [tab, setTab] = useState<Channel>("linkedin"),
    [mode, setMode] = useState("preview"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [confirm, setConfirm] = useState(false),
    [rejecting, setRejecting] = useState(false),
    [reason, setReason] = useState(""),
    [history, setHistory] = useState<Revision[] | null>(null),
    [historyTab, setHistoryTab] = useState<Channel>("website");
  const dirty =
    JSON.stringify(content) !== JSON.stringify(item.content) ||
    JSON.stringify([...channels].sort()) !==
      JSON.stringify([...item.channels].sort());
  const inFlight = item.jobs.some((j) => j.status === "publishing"),
    currentJobs = item.jobs.filter((j) => j.revision === item.revision);
  useEffect(() => {
    if (!content && item.content) {
      setContent(item.content);
      setChannels(item.channels);
      setRevision(item.revision);
    }
  }, [item.content]);
  function reload() {
    setContent(item.content);
    setChannels(item.channels);
    setRevision(item.revision);
    setError("");
  }
  useEffect(() => {
    function warn(e: BeforeUnloadEvent) {
      if (dirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    }
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  function close() {
    if (
      !dirty ||
      window.confirm("Leave this story and discard your unsaved changes?")
    )
      onClose();
  }
  async function save() {
    if (!content) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<Item>("/items/" + item.id, {
        method: "PUT",
        body: JSON.stringify({ revision, content, channels }),
      });
      setContent(result.content);
      setChannels(result.channels);
      setRevision(result.revision);
      await onUpdated();
      notify(
        "Draft saved. A fresh approval is required before publishing changes.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function approve() {
    setBusy(true);
    setError("");
    try {
      await api("/items/" + item.id + "/approve", {
        method: "POST",
        body: JSON.stringify({
          revision,
          channels,
          destinations: Object.fromEntries(
            connections
              .filter((c) => channels.includes(c.id))
              .map((c) => [
                c.id,
                Object.fromEntries(
                  Object.entries(c).filter(([k]) =>
                    ["provider", "target", "account", "version"].includes(k),
                  ),
                ),
              ]),
          ),
        }),
      });
      setConfirm(false);
      await onUpdated();
      notify(
        "Approval recorded. Publishing has started for your selected destinations.",
      );
    } catch (e) {
      setError((e as Error).message);
      setConfirm(false);
    } finally {
      setBusy(false);
    }
  }
  async function reject(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/items/" + item.id + "/reject", {
        method: "POST",
        body: JSON.stringify({ revision, reason }),
      });
      setRejecting(false);
      setReason("");
      await onUpdated();
      notify("Changes requested. Unstarted publication jobs were cancelled.");
    } catch (e) {
      setError((e as Error).message);
      setRejecting(false);
    } finally {
      setBusy(false);
    }
  }
  const stale = revision !== item.revision;
  const activeApproval = item.approvals.find(
    (a) => a.revision === item.revision && a.status === "active",
  );
  const draft = content?.[tab];
  return (
    <div className="editor-page">
      <div className="editor-heading">
        <button className="text-button" onClick={close}>
          <ArrowLeft size={14} />
          Back to stories
        </button>
        <div className="editor-heading-actions">
          {content && (
            <a
              className="button secondary small"
              href={"/api/items/" + item.id + "/export"}
            >
              <ArrowDownToLine size={14} />
              Export drafts
            </a>
          )}
          <button
            className="button primary small"
            onClick={save}
            disabled={
              !content ||
              busy ||
              inFlight ||
              stale ||
              (!dirty && item.status !== "rejected")
            }
          >
            {busy ? (
              <LoaderCircle size={14} className="spin" />
            ) : (
              <Check size={14} />
            )}
            Save changes
          </button>
        </div>
      </div>
      <div className="story-title-heading">
        <span className="eyebrow">
          STORY WORKSPACE / {item.project_name.toUpperCase()}
        </span>
        <h1>{item.title}</h1>
        <div className="story-meta">
          <Status status={item.status} />
          <span>Revision {revision}</span>
          <span className={"saved-indicator " + (dirty ? "unsaved" : "")}>
            {dirty ? "Unsaved changes" : "All changes saved"}
          </span>
        </div>
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {stale && (
        <div className="stale-banner">
          <AlertTriangle size={16} />A newer saved revision is available. Reload
          before approving.
          <button className="text-button" onClick={reload}>
            Load current revision
          </button>
        </div>
      )}
      {!content ? (
        <section className="generation-panel">
          {item.status === "generation_failed" ? (
            <>
              <AlertTriangle size={32} />
              <h2>Your source is safe.</h2>
              <p>{item.error}</p>
              <button
                className="button primary"
                onClick={async () => {
                  try {
                    await api("/items/" + item.id + "/retry-generation", {
                      method: "POST",
                    });
                    onUpdated();
                  } catch (e) {
                    setError((e as Error).message);
                  }
                }}
              >
                <RefreshCw size={16} />
                Retry generation
              </button>
            </>
          ) : (
            <>
              <LoaderCircle size={32} className="spin" />
              <h2>Preparing channel drafts</h2>
              <p>
                Preparing LinkedIn, newsletter, and website drafts from your
                source.
              </p>
              <small>Nothing will be published without your approval.</small>
            </>
          )}
        </section>
      ) : (
        <div className="editor-layout">
          <section className="draft-panel">
            <div
              className="channel-tabs"
              role="tablist"
              aria-label="Channel draft"
            >
              {(["linkedin", "newsletter", "website"] as Channel[]).map((c) => (
                <button
                  role="tab"
                  aria-selected={tab === c}
                  key={c}
                  className={tab === c ? "selected" : ""}
                  onClick={() => setTab(c)}
                >
                  <ChannelIcon channel={c} size={16} />
                  {channelNames[c]}
                </button>
              ))}
            </div>
            <div className="draft-toolbar">
              <span>
                {tab === "linkedin"
                  ? "A professional conversation starter"
                  : tab === "newsletter"
                    ? "A concise update for your stakeholders"
                    : "A considered announcement for your website"}
              </span>
              <div
                className="mode-toggle"
                role="group"
                aria-label="Editor mode"
              >
                <button
                  className={mode === "edit" ? "selected" : ""}
                  onClick={() => setMode("edit")}
                >
                  <PencilLine size={13} />
                  Edit
                </button>
                <button
                  className={mode === "preview" ? "selected" : ""}
                  onClick={() => setMode("preview")}
                >
                  <Eye size={13} />
                  Preview
                </button>
              </div>
            </div>
            {mode === "edit" ? (
              <div className="draft-edit">
                <label>
                  Headline
                  <input
                    value={draft?.title || ""}
                    maxLength={300}
                    disabled={inFlight}
                    onChange={(e) =>
                      setContent({
                        ...content,
                        [tab]: { ...content[tab], title: e.target.value },
                      })
                    }
                  />
                </label>
                <label>
                  Draft
                  <textarea
                    rows={19}
                    disabled={inFlight}
                    value={draft?.body || ""}
                    onChange={(e) =>
                      setContent({
                        ...content,
                        [tab]: { ...content[tab], body: e.target.value },
                      })
                    }
                  />
                </label>
              </div>
            ) : (
              <div className={"preview-container " + tab}>
                <div className="preview-topline">
                  <span>CHANNEL PREVIEW</span>
                  <span>UNPUBLISHED DRAFT</span>
                </div>
                {tab === "linkedin" ? (
                  <div className="linkedin-preview">
                    <div className="linkedin-profile">
                      <span>YK</span>
                      <div>
                        <strong>Dispatch</strong>
                        <small>Research and project updates</small>
                        <small>
                          Draft · <Globe2 size={9} />
                        </small>
                      </div>
                      <MoreHorizontal size={19} />
                    </div>
                    <h2>{draft?.title}</h2>
                    <div className="draft-prose">
                      {draft?.body.split(/\n\s*\n/).map((p, i) => (
                        <p key={i}>{p}</p>
                      ))}
                    </div>
                    <div className="linkedin-preview-footer">
                      A preview of your text. Final platform appearance may
                      vary.
                    </div>
                  </div>
                ) : tab === "newsletter" ? (
                  <div className="newsletter-preview">
                    <div className="newsletter-brand">
                      DISPATCH NOTES
                      <span>Ideas & updates from Dispatch</span>
                    </div>
                    <div className="newsletter-rule" />
                    <span className="eyebrow">PROJECT UPDATE</span>
                    <h2>{draft?.title}</h2>
                    <div className="draft-prose">
                      {draft?.body.split(/\n\s*\n/).map((p, i) => (
                        <p key={i}>{p}</p>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="website-preview">
                    <span className="eyebrow">DISPATCH / RESEARCH & IDEAS</span>
                    <h2>{draft?.title}</h2>
                    <div className="website-byline">
                      {item.project_name} · Editorial draft
                    </div>
                    <div className="draft-prose">
                      {draft?.body.split(/\n\s*\n/).map((p, i) => (
                        <p key={i}>{p}</p>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
            <div className="draft-footer">
              <span>
                {words(draft?.body || "")} words <span>·</span>{" "}
                {(draft?.body.length || 0).toLocaleString()} characters
              </span>
              <button
                className="text-button"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(
                      (draft?.title || "") + "\n\n" + (draft?.body || ""),
                    );
                    notify("Channel draft copied.");
                  } catch {
                    setError(
                      "Clipboard access is unavailable. Use Export drafts instead.",
                    );
                  }
                }}
              >
                <Copy size={12} />
                Copy draft
              </button>
            </div>
          </section>
          <aside className="review-sidebar">
            <section className="source-panel">
              <div className="side-section-heading">
                <FileText size={15} />
                <h2>Source material</h2>
              </div>
              <p className="source-description">
                {item.update_type} · {item.project_name}
              </p>
              <details>
                <summary>
                  Read original source
                  <ChevronDown size={13} />
                </summary>
                <div className="source-text">{item.source}</div>
              </details>
              <div className="audience">
                <small>WRITTEN FOR</small>
                <p>{item.audience}</p>
              </div>
            </section>
            <section className="destinations-panel">
              <div className="side-section-heading">
                <Send size={15} />
                <h2>Choose your destinations</h2>
              </div>
              <p>Only the channels you select will publish.</p>
              {["website", "linkedin"].map((c) => (
                <label
                  key={c}
                  className={
                    "destination " + (channels.includes(c) ? "checked" : "")
                  }
                >
                  <input
                    type="checkbox"
                    checked={channels.includes(c)}
                    disabled={inFlight}
                    onChange={(e) =>
                      setChannels(
                        e.target.checked
                          ? [...channels, c]
                          : channels.filter((v) => v !== c),
                      )
                    }
                  />
                  <ChannelIcon channel={c} size={17} />
                  <span>
                    {channelNames[c]}
                    <small>
                      {destinationLabel(
                        connections.find((connection) => connection.id === c),
                      )}
                    </small>
                  </span>
                </label>
              ))}
              <div className="newsletter-export">
                <Mail size={15} />
                <span>
                  Newsletter<small>Draft available in export</small>
                </span>
                <ArrowDownToLine size={13} />
              </div>
            </section>
            <section className="approval-panel">
              <ShieldCheck size={24} />
              <h2>Review and approve</h2>
              <p>
                {dirty
                  ? "Save your edits and destination choices before approving."
                  : channels.length
                    ? `Approve revision ${revision} for ${channels.map((c) => channelNames[c]).join(" and ")}.`
                    : "Choose and save at least one destination to enable approval."}
              </p>
              <button
                className="button primary full"
                onClick={() => setConfirm(true)}
                disabled={
                  busy ||
                  dirty ||
                  stale ||
                  !channels.length ||
                  inFlight ||
                  item.status === "rejected" ||
                  !!activeApproval
                }
              >
                <ShieldCheck size={15} />
                {activeApproval ? "Approval recorded" : "Approve & publish"}
              </button>
              <div className="approval-secondary">
                <button
                  disabled={busy || inFlight || stale}
                  onClick={() => setRejecting(true)}
                >
                  Request changes
                </button>
                {item.status === "draft" && (
                  <button
                    disabled={busy || dirty || stale}
                    onClick={async () => {
                      try {
                        await api("/items/" + item.id + "/ready", {
                          method: "POST",
                          body: JSON.stringify({ revision }),
                        });
                        onUpdated();
                        notify("The saved draft is ready for review.");
                      } catch (e) {
                        setError((e as Error).message);
                      }
                    }}
                  >
                    Mark ready
                  </button>
                )}
              </div>
              {activeApproval && (
                <small className="approval-record">
                  Approved by {activeApproval.reviewer}
                  <br />
                  {new Date(activeApproval.created_at).toLocaleString("en-GB")}
                </small>
              )}
            </section>
            <button
              className="history-button"
              onClick={async () => {
                try {
                  setHistory(
                    await api<Revision[]>("/items/" + item.id + "/history"),
                  );
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              <History size={15} />
              Revision history
              <ArrowUpRight size={13} />
            </button>
          </aside>
        </div>
      )}
      {currentJobs.length > 0 && (
        <section className="editor-publications">
          <div className="section-heading">
            <div>
              <h2>Publication results</h2>
              <span className="count-pill">Revision {item.revision}</span>
            </div>
            <span className="section-hint">Updates automatically</span>
          </div>
          {currentJobs.map((job) => (
            <div className="publication-result" key={job.id}>
              <span className="connection-icon">
                <ChannelIcon channel={job.channel} />
              </span>
              <div>
                <strong>{channelNames[job.channel]}</strong>
                {job.error && <p>{job.error}</p>}
                {job.url && (
                  <a href={job.url} target="_blank" rel="noreferrer">
                    Open published{" "}
                    {job.channel === "website" ? "article" : "post"}{" "}
                    <ExternalLink size={12} />
                  </a>
                )}
              </div>
              <Status status={job.status} />
              {["failed", "uncertain"].includes(job.status) && (
                <button
                  className="button secondary small"
                  onClick={async () => {
                    try {
                      await api("/jobs/" + job.id + "/retry", {
                        method: "POST",
                      });
                      onUpdated();
                      notify(
                        "Destination queued. Successful channels will not be republished.",
                      );
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  <RefreshCw size={13} />
                  {job.status === "uncertain" ? "Check outcome" : "Retry"}
                </button>
              )}
            </div>
          ))}
        </section>
      )}
      <details className="generation-details">
        <summary>
          <Sparkles size={13} />
          Generation notes · {item.provider || "Pending"}
        </summary>
        <ul>
          {item.warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      </details>
      {confirm && (
        <Modal
          title="Ready to share this version?"
          onClose={() => setConfirm(false)}
        >
          <div className="confirmation-body">
            <span className="confirmation-mark">
              <ShieldCheck size={28} />
            </span>
            <h3>{item.title}</h3>
            <p>
              You’re approving <strong>revision {revision}</strong>. The exact
              saved drafts will be sent to:
            </p>
            {channels.map((c) => (
              <div className="confirm-destination" key={c}>
                <ChannelIcon channel={c} size={19} />
                <strong>{channelNames[c]}</strong>
                <span>
                  {destinationLabel(
                    connections.find((connection) => connection.id === c),
                  )}
                </span>
                <Check size={16} />
              </div>
            ))}
            <div className="confirmation-note">
              Any later edit will require a new approval. Newsletter sending is
              not part of this action.
            </div>
          </div>
          <div className="modal-actions">
            <button
              className="button secondary"
              disabled={busy}
              onClick={() => setConfirm(false)}
            >
              Keep reviewing
            </button>
            <button
              className="button primary"
              disabled={busy}
              onClick={approve}
            >
              {busy ? (
                <LoaderCircle className="spin" size={15} />
              ) : (
                <Send size={15} />
              )}
              Approve & publish
            </button>
          </div>
        </Modal>
      )}
      {rejecting && (
        <Modal
          title="A little more work to do."
          onClose={() => setRejecting(false)}
        >
          <form onSubmit={reject}>
            <div className="rejection-body">
              <p>
                Record what needs to change. This revokes current approval and
                cancels unstarted publication jobs.
              </p>
              <label>
                Reviewer feedback
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  rows={5}
                  required
                  minLength={3}
                  maxLength={1000}
                  placeholder="What should be clarified or revised?"
                />
              </label>
            </div>
            <div className="modal-actions">
              <button
                type="button"
                className="button secondary"
                onClick={() => setRejecting(false)}
              >
                Cancel
              </button>
              <button className="button primary" disabled={busy}>
                Request changes
              </button>
            </div>
          </form>
        </Modal>
      )}
      {history && (
        <Modal
          title="Every version has a place."
          onClose={() => setHistory(null)}
          wide
        >
          <div className="history-content">
            <div className="tabs">
              {(["website", "linkedin", "newsletter"] as Channel[]).map((c) => (
                <button
                  className={historyTab === c ? "selected" : ""}
                  key={c}
                  onClick={() => setHistoryTab(c)}
                >
                  {channelNames[c]}
                </button>
              ))}
            </div>
            {history.map((rev) => (
              <details
                className="revision-entry"
                key={rev.revision}
                open={rev.revision === item.revision}
              >
                <summary>
                  <strong>Revision {rev.revision}</strong>
                  <span>
                    {new Date(rev.created_at).toLocaleString("en-GB")}
                  </span>
                  <small>
                    {rev.channels.map((c) => channelNames[c]).join(", ") ||
                      "No destinations selected"}
                  </small>
                </summary>
                <h3>{rev.content[historyTab].title}</h3>
                <div className="history-prose">
                  {rev.content[historyTab].body}
                </div>
              </details>
            ))}
          </div>
        </Modal>
      )}
    </div>
  );
}
