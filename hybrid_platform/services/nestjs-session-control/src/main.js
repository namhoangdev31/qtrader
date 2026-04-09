import express from "express";
import crypto from "crypto";

const app = express();
app.use(express.json());

let activeSession = null;

app.get("/health", (_req, res) => {
  res.json({ service: "session-control", status: "ok", active_session: activeSession });
});

app.post("/internal/session/start", (_req, res) => {
  if (!activeSession) {
    activeSession = `sess_${crypto.randomUUID()}`;
  }
  res.json({ status: "started", session_id: activeSession });
});

app.post("/internal/session/stop", (_req, res) => {
  const previous = activeSession;
  activeSession = null;
  res.json({ status: "stopped", previous_session_id: previous });
});

app.listen(3010, () => {
  // eslint-disable-next-line no-console
  console.log("session-control listening on :3010");
});
