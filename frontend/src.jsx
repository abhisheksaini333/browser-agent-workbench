import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
const labels = {
  proposed: "Needs approval",
  approved: "Ready to run",
  dispatched: "Running",
  completed: "Receipt confirmed",
  outcome_unknown: "Needs reconciliation",
  cancelled: "Cancelled",
};
function App() {
  const [key, setKey] = useState(""),
    [open, setOpen] = useState(false),
    [actions, setActions] = useState([]),
    [selected, setSelected] = useState(null),
    [task, setTask] = useState("purchase 2 WIDGET"),
    [mode, setMode] = useState("baseline"),
    [adapter, setAdapter] = useState("playwright"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [events, setEvents] = useState([]),
    [decision, setDecision] = useState(null);
  async function api(path, data) {
    const r = await fetch("/api" + path, {
      method: data === undefined ? "GET" : "POST",
      headers: {
        Authorization: "Bearer " + key,
        "Content-Type": "application/json",
      },
      body: data === undefined ? undefined : JSON.stringify(data),
    });
    const value = await r.json();
    if (!r.ok) throw new Error(value.error || "Request failed");
    return value;
  }
  async function refresh(id) {
    const list = await api("/actions");
    setActions(list);
    if (id) {
      const a = list.find((a) => a.id === id);
      setSelected(a);
      setEvents(await api("/actions/" + id + "/events"));
    }
  }
  async function work(fn) {
    setError("");
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function submit(event) {
    event.preventDefault();
    await work(async () => {
      const result = await api("/tasks", { task, mode });
      setDecision(result.decision);
      await refresh(result.action.id);
    });
  }
  async function action(verb) {
    await work(async () => {
      const data =
        verb === "approve"
          ? { args: selected.args, precondition: selected.precondition }
          : verb === "run"
            ? { adapter }
            : {};
      await api("/actions/" + selected.id + "/" + verb, data);
      await refresh(selected.id);
    });
  }
  const pending = actions.filter((a) => a.status === "proposed").length,
    completed = actions.filter((a) => a.status === "completed").length;
  return (
    <>
      <header>
        <a className="brand" href="/">
          ▧{" "}
          <span>
            FIELDWORK<span className="brand-sub">Operations console</span>
          </span>
        </a>
        <span className="environment">
          <i /> Owned local workspace
        </span>
        {open && (
          <button
            className="text-button"
            onClick={() => {
              setOpen(false);
              setKey("");
              setActions([]);
              setSelected(null);
            }}
          >
            Lock workspace
          </button>
        )}
      </header>
      <main>
        <div className="intro">
          <p className="eyebrow">BROWSER AGENT WORKBENCH</p>
          <h1>
            Every action.
            <br />
            <em>Accounted for.</em>
          </h1>
          <p className="intro-copy">
            Propose a task, inspect the exact change, and approve it.
            <br />
            Keep the application receipt when the browser disappears.
          </p>
        </div>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {!open ? (
          <form
            className="login panel"
            onSubmit={(e) => {
              e.preventDefault();
              work(async () => {
                await refresh();
                setOpen(true);
              });
            }}
          >
            <p className="eyebrow">OPERATOR ACCESS</p>
            <h2>Open your workspace</h2>
            <label htmlFor="operator-key">Operator key</label>
            <input
              id="operator-key"
              type="password"
              autoComplete="off"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              required
            />
            <p className="muted">
              Use the local operator key configured when the service starts. It
              stays in this page's memory.
            </p>
            <button disabled={busy}>Open workspace</button>
          </form>
        ) : (
          <>
            <section className="stats" aria-label="Workspace summary">
              <div>
                <b>{actions.length.toString().padStart(2, "0")}</b>
                <span>Total actions</span>
              </div>
              <div>
                <b>{pending.toString().padStart(2, "0")}</b>
                <span>Awaiting approval</span>
              </div>
              <div>
                <b>{completed.toString().padStart(2, "0")}</b>
                <span>Confirmed receipts</span>
              </div>
              <p>
                Approval authorizes an exact change.
                <br />A receipt confirms its effect.
              </p>
            </section>
            <section className="compose panel">
              <div>
                <p className="eyebrow">01 / DEFINE THE WORK</p>
                <h2>What needs to happen?</h2>
              </div>
              <form onSubmit={submit}>
                <label htmlFor="task">Task</label>
                <input
                  id="task"
                  value={task}
                  onChange={(e) => setTask(e.target.value)}
                  maxLength={1000}
                  required
                />
                <div className="compose-controls">
                  <label>
                    Selection method
                    <select
                      value={mode}
                      onChange={(e) => setMode(e.target.value)}
                    >
                      <option value="baseline">Structured baseline</option>
                      <option value="model">Local language model</option>
                    </select>
                  </label>
                  <label>
                    Browser executor
                    <select
                      value={adapter}
                      onChange={(e) => setAdapter(e.target.value)}
                    >
                      <option value="playwright">Playwright</option>
                      <option value="browser-use">Browser Use</option>
                    </select>
                  </label>
                  <button disabled={busy}>
                    {busy ? "Working…" : "Propose action"}
                  </button>
                </div>
                <p className="muted">
                  Baseline format: purchase, reservation, or inventory ·
                  quantity · WIDGET, DESK, or ROOM.
                </p>
              </form>
            </section>
            <div className="workspace">
              <section className="panel queue">
                <div className="section-heading">
                  <div>
                    <p className="eyebrow">02 / ACTION QUEUE</p>
                    <h2>Review the work</h2>
                  </div>
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() => work(() => refresh(selected?.id))}
                  >
                    Refresh
                  </button>
                </div>
                {actions.length === 0 ? (
                  <p className="empty">
                    Your first proposal will appear here.
                    <br />
                    Nothing executes without approval.
                  </p>
                ) : (
                  actions.map((a) => (
                    <button
                      className={
                        "action-row " +
                        (a.id === selected?.id ? "selected" : "")
                      }
                      key={a.id}
                      onClick={() => work(() => refresh(a.id))}
                    >
                      <span className="row-title">
                        {a.kind}
                        <strong>
                          {a.args.quantity} × {a.args.sku}
                        </strong>
                      </span>
                      <span className={"badge " + a.status}>
                        {labels[a.status]}
                      </span>
                    </button>
                  ))
                )}
              </section>
              <section className="panel detail" aria-label="Action detail">
                {!selected ? (
                  <div className="empty detail-empty">
                    <span>◎</span>
                    <h2>A clear record of every change</h2>
                    <p>
                      Select an action to inspect its approval,
                      <br />
                      application receipt and recovery history.
                    </p>
                  </div>
                ) : (
                  <>
                    <p className="eyebrow">03 / EXACT CHANGE</p>
                    <div className="section-heading">
                      <h2>
                        {selected.kind} · {selected.args.sku}
                      </h2>
                      <span className={"badge " + selected.status}>
                        {labels[selected.status]}
                      </span>
                    </div>
                    <dl className="facts">
                      <div>
                        <dt>Quantity</dt>
                        <dd>{selected.args.quantity}</dd>
                      </div>
                      <div>
                        <dt>Available before</dt>
                        <dd>{selected.precondition.available}</dd>
                      </div>
                      <div>
                        <dt>Resource version</dt>
                        <dd>{selected.precondition.version}</dd>
                      </div>
                    </dl>
                    <p className="muted">
                      Approval is bound to these arguments and this resource
                      version. Changed data requires a fresh proposal.
                    </p>
                    <div className="actions">
                      {selected.status === "proposed" && (
                        <button
                          disabled={busy}
                          onClick={() => action("approve")}
                        >
                          Approve exact action
                        </button>
                      )}
                      {selected.status === "approved" && (
                        <button disabled={busy} onClick={() => action("run")}>
                          Run approved action
                        </button>
                      )}
                      {["proposed", "approved"].includes(selected.status) && (
                        <button
                          className="secondary"
                          disabled={busy}
                          onClick={() => action("cancel")}
                        >
                          Cancel action
                        </button>
                      )}
                      {["dispatched", "outcome_unknown"].includes(
                        selected.status,
                      ) && (
                        <button
                          disabled={busy}
                          onClick={() => action("reconcile")}
                        >
                          Find application receipt
                        </button>
                      )}
                    </div>
                    {selected.status === "outcome_unknown" && (
                      <p className="warning">
                        The outcome is unresolved. Do not submit this operation
                        again. Reconcile its receipt or investigate the
                        application record.
                      </p>
                    )}
                    {selected.receipt && (
                      <div className="receipt">
                        <p className="eyebrow">APPLICATION RECEIPT</p>
                        <h3>Confirmed by the owned portal</h3>
                        <code>{selected.receipt.action_id}</code>
                        <p>
                          {selected.receipt.args.quantity} ×{" "}
                          {selected.receipt.args.sku} · resource version{" "}
                          {selected.receipt.resource_version}
                        </p>
                      </div>
                    )}
                    {events.length > 0 && (
                      <ol className="timeline" aria-label="Action history">
                        {events.map((event, index) => (
                          <li key={index}>
                            <span>{event.event.replaceAll("_", " ")}</span>
                            <time>
                              {new Date(
                                event.created * 1000,
                              ).toLocaleTimeString()}
                            </time>
                          </li>
                        ))}
                      </ol>
                    )}
                    {decision && (
                      <details>
                        <summary>Selection evidence</summary>
                        <pre>{JSON.stringify(decision, null, 2)}</pre>
                      </details>
                    )}
                  </>
                )}
              </section>
            </div>
          </>
        )}
        <footer>
          <span>FIELDWORK / BROWSER OPERATIONS</span>
          <span>Propose → Approve → Execute → Verify</span>
        </footer>
      </main>
    </>
  );
}
createRoot(document.getElementById("root")).render(<App />);
