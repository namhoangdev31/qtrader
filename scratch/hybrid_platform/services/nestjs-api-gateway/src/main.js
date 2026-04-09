import express from "express";

const app = express();
app.use(express.json());

const sessionUrl = process.env.SESSION_URL || "http://localhost:3010";
const omsUrl = process.env.OMS_URL || "http://localhost:3020";

app.get("/health", (_req, res) => {
  res.json({ service: "api-gateway", status: "ok", timestamp: new Date().toISOString() });
});

app.post("/api/v1/session/start", async (_req, res) => {
  try {
    const r = await fetch(`${sessionUrl}/internal/session/start`, { method: "POST" });
    const body = await r.json();
    res.status(r.status).json(body);
  } catch (err) {
    res.status(502).json({ error: "session-control unavailable", detail: String(err) });
  }
});

app.post("/api/v1/session/stop", async (_req, res) => {
  try {
    const r = await fetch(`${sessionUrl}/internal/session/stop`, { method: "POST" });
    const body = await r.json();
    res.status(r.status).json(body);
  } catch (err) {
    res.status(502).json({ error: "session-control unavailable", detail: String(err) });
  }
});

app.post("/api/v1/orders", async (req, res) => {
  const payload = req.body || {};
  if (!payload.symbol || !payload.side || !payload.qty || !payload.idempotency_key) {
    return res.status(400).json({
      error: "invalid_payload",
      required: ["symbol", "side", "qty", "idempotency_key"]
    });
  }

  try {
    const r = await fetch(`${omsUrl}/internal/orders`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
    const body = await r.json();
    return res.status(r.status).json(body);
  } catch (err) {
    return res.status(502).json({ error: "oms-workflow unavailable", detail: String(err) });
  }
});

app.listen(3000, () => {
  // eslint-disable-next-line no-console
  console.log("api-gateway listening on :3000");
});
