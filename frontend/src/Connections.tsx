import { useState } from "react";
import {
  FileText,
  LoaderCircle,
  RefreshCw,
  Server,
  Settings2,
} from "lucide-react";
import { api, channelNames, destinationLabel, type Config } from "./api";
import { ChannelIcon, Modal } from "./ui";

export default function Connections({
  config,
  onClose,
  onRefresh,
}: {
  config: Config;
  onClose: () => void;
  onRefresh: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const ai = config.ai_connection;
  async function check() {
    setBusy(true);
    setError("");
    try {
      await api("/connections/check", { method: "POST" });
      await onRefresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Connections" onClose={onClose}>
      <div className="connection-content">
        <p className="connection-intro">
          Review the AI provider and publishing destinations. Credentials stay
          on the server.
        </p>
        <div className="connection">
          <span className="connection-icon">
            <Server size={21} />
          </span>
          <div>
            <h3>OpenAI</h3>
            <p>
              {ai.model} ·{" "}
              {ai.mode === "live"
                ? "Live requests enabled"
                : "Demo templates enabled"}
            </p>
            <small>
              {ai.key_configured ? "KEY CONFIGURED" : "API KEY MISSING"}
            </small>
            <p className="connection-check">
              {ai.check?.detail ||
                "Add OPENAI_API_KEY to the server .env file and restart Dispatch."}
            </p>
          </div>
        </div>
        {config.connections.map((c) => (
          <div className="connection" key={c.id}>
            <span className="connection-icon">
              <ChannelIcon channel={c.id} size={21} />
            </span>
            <div>
              <h3>{channelNames[c.id]}</h3>
              <p>{destinationLabel(c)}</p>
              <small>{c.status.replaceAll("_", " ").toUpperCase()}</small>
              <p className="connection-check">{c.check?.detail || c.detail}</p>
              {c.check?.checked_at && (
                <span className="connection-time">
                  Checked {new Date(c.check.checked_at).toLocaleString("en-GB")}
                </span>
              )}
            </div>
          </div>
        ))}
        <div className="connection">
          <span className="connection-icon">
            <FileText size={21} />
          </span>
          <div>
            <h3>Newsletter</h3>
            <p>Editable draft and text export. No email is sent.</p>
            <small>DRAFT EXPORT</small>
          </div>
        </div>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <button
          className="button secondary full"
          onClick={check}
          disabled={busy}
        >
          {busy ? (
            <LoaderCircle size={15} className="spin" />
          ) : (
            <Settings2 size={15} />
          )}
          Check connections
        </button>
        <p className="connection-footnote">
          Checks do not publish content. OpenAI checks key and model access;
          WordPress checks account permissions. LinkedIn write access remains
          unverified until an approved post succeeds.
        </p>
        <details className="connection-setup">
          <summary>Set up WordPress or LinkedIn</summary>
          <p>
            In the server .env file, choose WEBSITE_PROVIDER=wordpress or
            SOCIAL_PROVIDER=linkedin. Add that service’s credentials and
            restart. See the README for the required fields and permissions. The
            local website and social sandbox remain available when selected.
          </p>
        </details>
        {config.connections.find((c) => c.id === "linkedin")?.provider ===
          "sandbox" && (
          <div className="recovery-test">
            <h3>Test failure recovery</h3>
            <p>
              Fail the next social sandbox request once, then retry that
              destination from the publication log.
            </p>
            <button
              className="button secondary"
              disabled={config.fail_next.linkedin}
              onClick={async () => {
                try {
                  await api("/sandbox/fail-next", {
                    method: "POST",
                    body: JSON.stringify({ channel: "linkedin" }),
                  });
                  await onRefresh();
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              <RefreshCw size={15} />
              {config.fail_next.linkedin
                ? "One-time failure is armed"
                : "Fail the next social request once"}
            </button>
          </div>
        )}
      </div>
    </Modal>
  );
}
