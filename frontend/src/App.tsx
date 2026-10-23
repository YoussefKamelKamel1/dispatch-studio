import { useEffect, useState } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  CheckCheck,
  ChevronRight,
  CircleHelp,
  Clock3,
  ExternalLink,
  FileText,
  LayoutGrid,
  List,
  LoaderCircle,
  LogOut,
  PencilLine,
  Plus,
  Radio,
  RefreshCw,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  SquarePen,
  X,
  AlertTriangle,
} from "lucide-react";
import {
  api,
  setCsrf,
  channelNames,
  date,
  type Activity,
  type Config,
  type Item,
  type Job,
  type Session,
  type Channel,
} from "./api";
import { Brand, ChannelIcon, Modal, Status } from "./ui";
import Login from "./Login";
import NewStory from "./NewStory";
import Editor from "./Editor";
import Connections from "./Connections";

export default function App() {
  const [session, setSession] = useState<Session | null>(null),
    [authLoading, setAuthLoading] = useState(true),
    [config, setConfig] = useState<Config | null>(null),
    [items, setItems] = useState<Item[]>([]),
    [activity, setActivity] = useState<Activity[]>([]),
    [publications, setPublications] = useState<Job[]>([]),
    [page, setPage] = useState("studio"),
    [selected, setSelected] = useState<string | null>(null),
    [creating, setCreating] = useState(false),
    [filter, setFilter] = useState("all"),
    [project, setProject] = useState(""),
    [search, setSearch] = useState(""),
    [layout, setLayout] = useState("grid"),
    [guide, setGuide] = useState(false),
    [connections, setConnections] = useState(false),
    [toast, setToast] = useState(""),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  async function refresh() {
    try {
      const [c, i, a, p] = await Promise.all([
        api<Config>("/config"),
        api<Item[]>("/items"),
        api<Activity[]>("/activity"),
        api<Job[]>("/publications"),
      ]);
      setConfig(c);
      setItems(i);
      setActivity(a);
      setPublications(p);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    api<Session>("/auth/me")
      .then((s) => {
        setCsrf(s.csrf);
        setSession(s);
      })
      .catch(() => {})
      .finally(() => setAuthLoading(false));
  }, []);
  useEffect(() => {
    if (!session) return;
    refresh();
    const interval = setInterval(refresh, 3000);
    return () => clearInterval(interval);
  }, [session]);
  useEffect(() => {
    if (!toast) return;
    const timeout = setTimeout(() => setToast(""), 5500);
    return () => clearTimeout(timeout);
  }, [toast]);
  if (authLoading)
    return (
      <div className="boot">
        <Brand />
        <LoaderCircle className="spin" />
      </div>
    );
  if (!session) return <Login onLogin={setSession} />;
  const current = items.find((i) => i.id === selected);
  const visible = items.filter(
    (i) =>
      (!project || i.project_id === project) &&
      (filter === "all" ||
        (filter === "attention"
          ? ["partial", "failed", "generation_failed"].includes(i.status)
          : i.status === filter)) &&
      [i.title, i.source, i.project_name]
        .join(" ")
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const counts = {
    review: items.filter((i) => i.status === "ready").length,
    published: items.filter((i) => i.status === "published").length,
    attention: items.filter((i) =>
      ["partial", "failed", "generation_failed"].includes(i.status),
    ).length,
  };
  function navigate(next: string) {
    setPage(next);
    setSelected(null);
  }
  async function logout() {
    try {
      await api("/auth/logout", { method: "POST" });
      setCsrf("");
      setSession(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand />
        <div className="workspace-switch">
          <span className="workspace-avatar">d</span>
          <div>
            Dispatch<small>Editorial workspace</small>
          </div>
        </div>
        <span className="nav-label">CREATE & COMMUNICATE</span>
        <nav aria-label="Main navigation">
          <button
            className={"nav-item " + (page === "studio" ? "active" : "")}
            onClick={() => navigate("studio")}
          >
            <SquarePen size={18} />
            Content studio<span className="nav-count">{items.length}</span>
          </button>
          <button
            className={"nav-item " + (page === "publications" ? "active" : "")}
            onClick={() => navigate("publications")}
          >
            <Radio size={18} />
            Publishing log
          </button>
          <button
            className={"nav-item " + (page === "activity" ? "active" : "")}
            onClick={() => navigate("activity")}
          >
            <Clock3 size={18} />
            Activity
          </button>
        </nav>
        <div className="channels-nav">
          <span className="nav-label">YOUR CHANNELS</span>
          {["website", "linkedin", "newsletter"].map((c) => (
            <button key={c} onClick={() => setConnections(true)}>
              <ChannelIcon channel={c} />
              <span>{channelNames[c]}</span>
              <small>
                {c === "newsletter"
                  ? "EXPORT"
                  : config?.connections
                      .find((connection) => connection.id === c)
                      ?.provider?.toUpperCase() || "LOCAL"}
              </small>
            </button>
          ))}
        </div>
        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <span className="small-mark">✳</span>
            <strong>Approval required</strong>
            <p>Review and approve a saved revision before publishing.</p>
          </div>
          <button className="nav-item" onClick={() => setGuide(true)}>
            <CircleHelp size={17} />
            Editorial guide
            <ArrowUpRight size={14} />
          </button>
          <div className="user">
            <span className="user-avatar">YK</span>
            <div>
              {session.name}
              <small>Editor & reviewer</small>
            </div>
            <button className="icon-button" onClick={logout} title="Sign out">
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace
            <ChevronRight size={13} />
            <button onClick={() => navigate("studio")}>
              {page === "studio"
                ? "Content studio"
                : page === "publications"
                  ? "Publishing log"
                  : "Activity"}
            </button>
            {selected && (
              <>
                <ChevronRight size={13} />
                <span>Story workspace</span>
              </>
            )}
          </div>
          <div className="topbar-right">
            <span className="environment">
              <span />
              Publishing connections
            </span>
            <button
              className="icon-button"
              onClick={() => setConnections(true)}
              title="Publishing connections"
            >
              <Settings2 size={17} />
            </button>
          </div>
        </header>
        <main>
          {error && (
            <div className="error-banner" role="alert">
              <AlertTriangle size={17} />
              {error}
              <button onClick={refresh}>Try again</button>
            </div>
          )}
          {loading && !config ? (
            <div className="loading-panel">
              <LoaderCircle className="spin" />
              Preparing your editorial workspace…
            </div>
          ) : current ? (
            <Editor
              key={current.id}
              item={current}
              onClose={() => setSelected(null)}
              onUpdated={refresh}
              notify={setToast}
              connections={config?.connections || []}
            />
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <span className="eyebrow">
                    {page === "studio"
                      ? "CONTENT WORKSPACE"
                      : page === "publications"
                        ? "PUBLISHING"
                        : "WORKSPACE HISTORY"}
                  </span>
                  <h1>
                    {page === "studio"
                      ? "Content studio"
                      : page === "publications"
                        ? "Publication results"
                        : "Activity"}
                  </h1>
                  <p>
                    {page === "studio"
                      ? "Create channel drafts from project updates, edit them, and approve selected destinations."
                      : page === "publications"
                        ? "Follow each approved revision from the first request to its published destination."
                        : "Source updates, editorial decisions, and publishing outcomes. All in one place."}
                  </p>
                </div>
                <button
                  className="button primary"
                  onClick={() => setCreating(true)}
                >
                  <Plus size={17} />
                  New story
                </button>
              </div>
              {page === "studio" && (
                <>
                  <div className="studio-intro">
                    <div className="intro-copy">
                      <span className="eyebrow">
                        LINKEDIN / NEWSLETTER / WEBSITE
                      </span>
                      <h2>
                        One source.
                        <br />
                        <em>Three channel drafts.</em>
                      </h2>
                      <p>
                        Add a project update or research summary. Review each
                        draft before choosing where to publish.
                      </p>
                      <button
                        className="text-button"
                        onClick={() => setCreating(true)}
                      >
                        Start with a project update <ArrowRight size={15} />
                      </button>
                    </div>
                    <div className="intro-channels">
                      <div>
                        <ChannelIcon channel="linkedin" size={21} />
                        <span>In the conversation</span>
                        <small>LINKEDIN</small>
                      </div>
                      <div>
                        <ChannelIcon channel="newsletter" size={21} />
                        <span>In the loop</span>
                        <small>NEWSLETTER</small>
                      </div>
                      <div>
                        <ChannelIcon channel="website" size={21} />
                        <span>On the record</span>
                        <small>WEBSITE</small>
                      </div>
                      <span className="intro-connector" aria-hidden="true" />
                    </div>
                  </div>
                  <div className="studio-stats">
                    <button onClick={() => setFilter("all")}>
                      <strong>
                        {items.length.toString().padStart(2, "0")}
                      </strong>
                      <span>Stories in your workspace</span>
                      <ArrowUpRight size={16} />
                    </button>
                    <button onClick={() => setFilter("ready")}>
                      <strong>
                        {counts.review.toString().padStart(2, "0")}
                      </strong>
                      <span>Waiting for review</span>
                      <span className="stat-dot amber" />
                    </button>
                    <button onClick={() => setFilter("published")}>
                      <strong>
                        {counts.published.toString().padStart(2, "0")}
                      </strong>
                      <span>Published with approval</span>
                      <CheckCheck size={17} />
                    </button>
                  </div>
                  <section className="stories-section">
                    <div className="section-heading">
                      <div>
                        <h2>Your stories</h2>
                        <span className="count-pill">{visible.length}</span>
                      </div>
                      <div
                        className="layout-toggle"
                        role="group"
                        aria-label="Story layout"
                      >
                        <button
                          aria-label="Grid view"
                          className={layout === "grid" ? "selected" : ""}
                          onClick={() => setLayout("grid")}
                        >
                          <LayoutGrid size={15} />
                        </button>
                        <button
                          aria-label="List view"
                          className={layout === "list" ? "selected" : ""}
                          onClick={() => setLayout("list")}
                        >
                          <List size={16} />
                        </button>
                      </div>
                    </div>
                    <div className="stories-toolbar">
                      <div
                        className="tabs"
                        role="group"
                        aria-label="Story status"
                      >
                        {[
                          ["all", "All stories"],
                          ["ready", "Awaiting review"],
                          ["published", "Published"],
                          ["attention", "Needs attention"],
                        ].map(([value, label]) => (
                          <button
                            className={filter === value ? "selected" : ""}
                            key={value}
                            onClick={() => setFilter(value)}
                          >
                            {label}
                            {value === "attention" && counts.attention > 0 && (
                              <span>{counts.attention}</span>
                            )}
                          </button>
                        ))}
                      </div>
                      <div className="toolbar-controls">
                        <label className="search-input">
                          <Search size={15} />
                          <input
                            placeholder="Find a story…"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            aria-label="Search stories"
                          />
                        </label>
                        <label>
                          <span className="sr-only">Project</span>
                          <select
                            className="project-filter"
                            value={project}
                            onChange={(e) => setProject(e.target.value)}
                          >
                            <option value="">All projects</option>
                            {config?.projects.map((p) => (
                              <option key={p.id} value={p.id}>
                                {p.name}
                              </option>
                            ))}
                          </select>
                        </label>
                      </div>
                    </div>
                    <div
                      className={
                        "story-grid " + (layout === "list" ? "list-view" : "")
                      }
                    >
                      {visible.map((item, index) => (
                        <article
                          className={"story-card tone-" + (index % 3)}
                          key={item.id}
                        >
                          <div className="story-card-top">
                            <span className="project-tag">
                              <span
                                style={{ background: item.project_color }}
                              />
                              {item.project_name}
                            </span>
                            <Status status={item.status} />
                          </div>
                          <div className="story-card-body">
                            <span className="story-kind">
                              {item.update_type}
                            </span>
                            <h3>
                              <button onClick={() => setSelected(item.id)}>
                                {item.title}
                              </button>
                            </h3>
                            <p>{item.source}</p>
                          </div>
                          <div className="story-channel-row">
                            <div>
                              {(
                                [
                                  "linkedin",
                                  "newsletter",
                                  "website",
                                ] as Channel[]
                              ).map((c) => (
                                <span key={c} title={channelNames[c]}>
                                  <ChannelIcon channel={c} size={13} />
                                </span>
                              ))}
                              <small>
                                {item.content
                                  ? "3 channel drafts"
                                  : "Drafts pending"}
                              </small>
                            </div>
                            <span className="revision-label">
                              V{item.revision}
                            </span>
                          </div>
                          <div className="story-card-footer">
                            <small>Updated {date(item.updated_at)}</small>
                            <button
                              className="text-button"
                              onClick={() => setSelected(item.id)}
                            >
                              {item.status === "published"
                                ? "View story"
                                : "Open story"}
                              <ArrowUpRight size={14} />
                            </button>
                          </div>
                        </article>
                      ))}
                    </div>
                    {!visible.length && (
                      <div className="empty-state">
                        <BookOpen size={35} />
                        <h3>No content to display</h3>
                        <p>
                          {items.length
                            ? "Try a different search or status filter."
                            : "Add a project update to prepare channel drafts."}
                        </p>
                        <button
                          className="button secondary"
                          onClick={() =>
                            items.length
                              ? (setSearch(""),
                                setFilter("all"),
                                setProject(""))
                              : setCreating(true)
                          }
                        >
                          {items.length ? "Clear filters" : "Create a story"}
                        </button>
                      </div>
                    )}
                  </section>
                  <div className="editorial-footer">
                    <ShieldCheck size={19} />
                    <span>
                      <strong>Source and revision history</strong> Every story
                      keeps its source material, revisions, and approval history
                      together.
                    </span>
                    <button
                      className="text-button"
                      onClick={() => setGuide(true)}
                    >
                      Editorial guide <ArrowRight size={14} />
                    </button>
                  </div>
                </>
              )}
              {page === "publications" && (
                <PublicationLog
                  jobs={publications}
                  onOpen={setSelected}
                  onRetry={async (id) => {
                    try {
                      await api("/jobs/" + id + "/retry", { method: "POST" });
                      refresh();
                      setToast(
                        "The destination is queued. Its result will update automatically.",
                      );
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                  onConnections={() => setConnections(true)}
                />
              )}
              {page === "activity" && (
                <section className="activity-panel">
                  <div className="section-heading">
                    <div>
                      <h2>Editorial history</h2>
                      <span className="count-pill">{activity.length}</span>
                    </div>
                  </div>
                  {activity.map((a) => (
                    <div className="activity-row" key={a.id}>
                      <span className="activity-icon">
                        {a.action === "approved" ? (
                          <ShieldCheck size={16} />
                        ) : a.action === "published" ? (
                          <Send size={15} />
                        ) : (
                          <PencilLine size={16} />
                        )}
                      </span>
                      <div>
                        <strong>{a.action.replaceAll("_", " ")}</strong>
                        <p>{a.detail}</p>
                        <small>
                          {new Date(a.created_at).toLocaleString("en-GB")}
                        </small>
                      </div>
                      {a.item_id && (
                        <button
                          className="text-button"
                          onClick={() => setSelected(a.item_id)}
                        >
                          Open story <ArrowUpRight size={14} />
                        </button>
                      )}
                    </div>
                  ))}
                </section>
              )}
            </>
          )}
          <footer className="page-footer">
            <span>◎ Dispatch by Youssef Kamel</span>
            <span>Drafts, approvals, and publication records</span>
          </footer>
        </main>
      </div>
      {creating && config && (
        <NewStory
          config={config}
          onClose={() => setCreating(false)}
          onCreated={async (id) => {
            setCreating(false);
            await refresh();
            setSelected(id);
            setToast(
              "Your source is saved. Three channel drafts are being prepared.",
            );
          }}
        />
      )}
      {guide && (
        <Modal title="Editorial guide" onClose={() => setGuide(false)}>
          <div className="guide">
            <div>
              <FileText />
              <h3>1. Add source material</h3>
              <p>
                Provide the findings, context, limitations, and next steps you
                actually know. Drafts should preserve preliminary findings and
                avoid invented outcomes.
              </p>
            </div>
            <div>
              <PencilLine />
              <h3>2. Review channel drafts</h3>
              <p>
                Review and edit all three versions. Save your changes and choose
                publishing destinations explicitly.
              </p>
            </div>
            <div>
              <ShieldCheck />
              <h3>3. Approve selected destinations</h3>
              <p>
                Approve & publish records your exact revision and destinations.
                A later edit revokes approval; already published versions stay
                in the history.
              </p>
            </div>
            <div className="mode-note">
              <strong>
                {config?.ai_mode === "live"
                  ? "Live AI generation"
                  : "Local template demonstration"}
              </strong>
              <p>
                {config?.ai_mode === "live"
                  ? "Drafts use the configured OpenAI model. Review factual accuracy before approval."
                  : "No live AI call is made in demo mode. The local template rearranges supplied source text. Configure a server API key for live generation."}
              </p>
            </div>
          </div>
        </Modal>
      )}
      {connections && config && (
        <Connections
          config={config}
          onClose={() => setConnections(false)}
          onRefresh={refresh}
        />
      )}
      {toast && (
        <div className="toast" role="status">
          <Check size={17} />
          <span>{toast}</span>
          <button
            className="icon-button"
            aria-label="Dismiss notification"
            onClick={() => setToast("")}
          >
            <X size={15} />
          </button>
        </div>
      )}
    </div>
  );
}

function PublicationLog({
  jobs,
  onOpen,
  onRetry,
  onConnections,
}: {
  jobs: Job[];
  onOpen: (id: string) => void;
  onRetry: (id: string) => void;
  onConnections: () => void;
}) {
  return (
    <>
      <section className="publication-log">
        <div className="section-heading">
          <div>
            <h2>Publication log</h2>
            <span className="count-pill">{jobs.length} destinations</span>
          </div>
          <a className="button secondary small" href="/api/export/publications">
            <ArrowDownToLine size={14} />
            Export CSV
          </a>
        </div>
        {jobs.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>STORY / APPROVED VERSION</th>
                  <th>DESTINATION</th>
                  <th>STATUS</th>
                  <th>LAST UPDATED</th>
                  <th>RESULT</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id}>
                    <td>
                      <button
                        className="table-title"
                        onClick={() => onOpen(job.item_id)}
                      >
                        {job.title}
                      </button>
                      <small>
                        Revision {job.revision} · {job.reviewer}
                      </small>
                    </td>
                    <td>
                      <span className="channel-name">
                        <ChannelIcon channel={job.channel} size={14} />
                        {channelNames[job.channel]}
                      </span>
                    </td>
                    <td>
                      <Status status={job.status} />
                      {job.error && (
                        <small className="job-error">{job.error}</small>
                      )}
                    </td>
                    <td className="log-date">
                      {new Date(job.updated_at).toLocaleString("en-GB")}
                    </td>
                    <td>
                      {job.url ? (
                        <a
                          className="text-button"
                          href={job.url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Open post <ExternalLink size={12} />
                        </a>
                      ) : ["failed", "uncertain"].includes(job.status) ? (
                        <button
                          className="text-button"
                          onClick={() => onRetry(job.id)}
                        >
                          <RefreshCw size={12} />
                          {job.status === "uncertain"
                            ? "Check outcome"
                            : "Retry destination"}
                        </button>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <Radio size={35} />
            <h3>Your first publication starts with approval.</h3>
            <p>
              Review a story, select destinations, save, and approve the version
              you want to share.
            </p>
          </div>
        )}
      </section>
      <div className="log-note">
        <ShieldCheck size={18} />
        <p>
          Each result belongs to an approved revision. Successful destinations
          are preserved when another needs a retry.
        </p>
        <button className="text-button" onClick={onConnections}>
          Test failure recovery <ArrowRight size={14} />
        </button>
      </div>
    </>
  );
}
