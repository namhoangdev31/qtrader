import express from "express";
import crypto from "crypto";

const app = express();
app.use(express.json());

const executionUrl = process.env.EXECUTION_URL || "http://localhost:8002";
const idempotencyStore = new Map();

app.get("/health", (_req, res) => {
  res.json({ service: "oms-workflow", status: "ok", idempotency_cache: idempotencyStore.size });
});

app.post("/internal/orders", async (req, res) => {
  const payload = req.body || {};
  const key = String(payload.idempotency_key || "").trim();

  if (!key) {
    return res.status(400).json({ error: "missing_idempotency_key" });
  }

  if (idempotencyStore.has(key)) {
    return res.json({ status: "duplicate", data: idempotencyStore.get(key) });
  }

  const orderCommand = {
    order_id: payload.order_id || `ord_${crypto.randomUUID()}`,
    symbol: payload.symbol,
    side: payload.side,
    qty: payload.qty,
    price: payload.price ?? null,
    order_type: payload.order_type || "MARKET",
    idempotency_key: key,
    trace_id: payload.trace_id || `tr_${crypto.randomUUID()}`
  };

  try {
    const r = await fetch(`${executionUrl}/execute`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(orderCommand)
    });
    const body = await r.json();

    const response = {
      status: r.ok ? "accepted" : "rejected",
      order: orderCommand,
      execution: body
    };
    idempotencyStore.set(key, response);
    return res.status(r.ok ? 202 : 422).json(response);
  } catch (err) {
    return res.status(502).json({ error: "execution-core unavailable", detail: String(err) });
  }
});

app.listen(3020, () => {
  // eslint-disable-next-line no-console
  console.log("oms-workflow listening on :3020");
});
