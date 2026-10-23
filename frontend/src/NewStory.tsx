import { useState, type FormEvent } from "react";
import { FileText, LoaderCircle, ShieldCheck, Sparkles } from "lucide-react";
import { api, channelNames, type Config, type Source } from "./api";
import { ChannelIcon, Modal } from "./ui";
export default function NewStory({
  config,
  onClose,
  onCreated,
}: {
  config: Config;
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const [form, setForm] = useState<Source>({
      title: "",
      source: "",
      project_id: config.projects[0]?.id || "",
      update_type: "Project update",
      audience: "Research partners and organizational stakeholders",
      cta: "",
    }),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  function change(key: keyof Source, value: string) {
    setForm({ ...form, [key]: value });
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api<{ id: string }>("/items", {
        method: "POST",
        body: JSON.stringify(form),
      });
      onCreated(result.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="New content" onClose={onClose} wide>
      <form onSubmit={submit}>
        <div className="new-story-layout">
          <section className="new-story-form">
            <p className="form-intro">
              Add the source material for your LinkedIn, newsletter, and website
              drafts.
            </p>
            <div className="form-grid">
              <label className="span-2">
                Working title
                <input
                  value={form.title}
                  onChange={(e) => change("title", e.target.value)}
                  placeholder="What is your update about?"
                  minLength={3}
                  maxLength={200}
                  required
                />
              </label>
              <label>
                Project
                <select
                  value={form.project_id}
                  onChange={(e) => change("project_id", e.target.value)}
                >
                  {config.projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Update type
                <select
                  value={form.update_type}
                  onChange={(e) => change("update_type", e.target.value)}
                >
                  {[
                    "Project update",
                    "Research findings",
                    "Event announcement",
                    "Project description",
                  ].map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
              </label>
              <label className="span-2">
                Source material
                <textarea
                  rows={9}
                  value={form.source}
                  onChange={(e) => change("source", e.target.value)}
                  placeholder="What happened? What did you learn? Include the context, limitations, and next steps you can confirm."
                  minLength={30}
                  maxLength={30000}
                  required
                />
                <span className="field-help">
                  At least 30 characters. Use fictional or public information.
                </span>
              </label>
              <label className="span-2">
                Intended audience
                <input
                  value={form.audience}
                  onChange={(e) => change("audience", e.target.value)}
                  maxLength={1000}
                />
              </label>
              <label className="span-2">
                Call to action <span className="optional">optional</span>
                <input
                  value={form.cta}
                  onChange={(e) => change("cta", e.target.value)}
                  maxLength={1000}
                  placeholder="What should readers do next?"
                />
              </label>
            </div>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
          </section>
          <aside className="new-story-aside">
            <span className="eyebrow">CHANNEL FORMATS</span>
            {["linkedin", "newsletter", "website"].map((c) => (
              <div className="channel-explainer" key={c}>
                <ChannelIcon channel={c} size={21} />
                <div>
                  <h3>{channelNames[c]}</h3>
                  <p>
                    {c === "linkedin"
                      ? "A concise post with the main findings and next step."
                      : c === "newsletter"
                        ? "A concise summary that keeps stakeholders informed."
                        : "A structured announcement with the full context."}
                  </p>
                </div>
              </div>
            ))}
            <div className="source-principle">
              <ShieldCheck size={22} />
              <h3>Check before approval</h3>
              <p>
                Check the facts, refine the voice, and approve the exact version
                you want to share.
              </p>
            </div>
            <button
              type="button"
              className="button secondary full"
              onClick={() => setForm({ ...config.sample })}
            >
              <FileText size={15} />
              Use fictional research example
            </button>
            <label className="button secondary full source-import">
              <FileText size={15} /> Import source file
              <input
                type="file"
                accept=".json,.txt,text/plain,application/json"
                onChange={async (event) => {
                  const file = event.target.files?.[0];
                  if (!file) return;
                  setError("");
                  try {
                    if (file.size > 65536)
                      throw new Error("Use a source file smaller than 64 KB.");
                    const text = await file.text();
                    if (file.name.toLowerCase().endsWith(".json")) {
                      const value = JSON.parse(text);
                      if (
                        !value ||
                        typeof value !== "object" ||
                        typeof value.source !== "string"
                      )
                        throw new Error(
                          "The JSON file needs a source text field.",
                        );
                      const imported = { ...form };
                      for (const key of [
                        "title",
                        "source",
                        "project_id",
                        "update_type",
                        "audience",
                        "cta",
                      ] as (keyof Source)[]) {
                        if (typeof value[key] === "string")
                          imported[key] = value[key];
                      }
                      if (
                        !config.projects.some(
                          (p) => p.id === imported.project_id,
                        )
                      )
                        imported.project_id = form.project_id;
                      setForm(imported);
                    } else {
                      setForm((previous) => ({ ...previous, source: text }));
                    }
                  } catch (e) {
                    setError((e as Error).message);
                  }
                  event.target.value = "";
                }}
              />
            </label>
            <small className="mode-label">
              {config.ai_mode === "live"
                ? "Live AI generation enabled"
                : "Demo mode · local templates, no AI call"}
            </small>
          </aside>
        </div>
        <div className="modal-actions">
          <button
            type="button"
            className="button secondary"
            onClick={onClose}
            disabled={busy}
          >
            Cancel
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? (
              <LoaderCircle size={16} className="spin" />
            ) : (
              <Sparkles size={16} />
            )}
            Prepare channel drafts
          </button>
        </div>
      </form>
    </Modal>
  );
}
