import { useState, type FormEvent } from "react";
import { ArrowRight, ArrowUpRight, LoaderCircle } from "lucide-react";
import { api, setCsrf, type Session } from "./api";
import { Brand } from "./ui";
export default function Login({
  onLogin,
}: {
  onLogin: (session: Session) => void;
}) {
  const [email, setEmail] = useState("demo@example.com"),
    [password, setPassword] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function submit(e?: FormEvent, demo = false) {
    e?.preventDefault();
    setBusy(true);
    setError("");
    try {
      const session = await api<Session>("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: demo ? "demo@example.com" : email,
          password: demo ? "demo-password" : password,
        }),
      });
      setCsrf(session.csrf);
      onLogin(session);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-page">
      <section className="login-story">
        <Brand />
        <div className="login-story-copy">
          <span className="eyebrow">DISPATCH / CONTENT</span>
          <h1>
            Write. Review.
            <br />
            Publish.
          </h1>
          <p>
            Prepare LinkedIn posts, newsletter summaries, and website articles
            from one source. Review each version before publishing.
          </p>
          <div className="editorial-lines" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
            <span />
          </div>
        </div>
        <div className="login-bottom">
          <span>Content and publishing</span>
          <span>02 / DISPATCH</span>
        </div>
      </section>
      <section className="login-form-wrap">
        <form className="login-form" onSubmit={submit}>
          <span className="eyebrow">EDITORIAL WORKSPACE</span>
          <h2>Welcome to Dispatch.</h2>
          <p>Sign in to your Dispatch editorial workspace.</p>
          <label>
            Email address
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              autoComplete="current-password"
              required
            />
          </label>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button className="button primary full" disabled={busy}>
            {busy ? (
              <LoaderCircle className="spin" size={17} />
            ) : (
              <>
                Sign in <ArrowRight size={17} />
              </>
            )}
          </button>
          <div className="login-divider">TAKE A LOOK AROUND</div>
          <button
            className="button secondary full"
            type="button"
            onClick={() => submit(undefined, true)}
            disabled={busy}
          >
            Open fictional demo workspace <ArrowUpRight size={16} />
          </button>
          <small>
            Fictional drafts, a local test website, and a social publishing
            sandbox. Every publication requires approval.
          </small>
        </form>
      </section>
    </div>
  );
}
