#!/usr/bin/env node
// Inspect Mirasim's local cloud RPC for machine entries and grant-shaped
// tokens. Run it on a member device while Mirasim is open:
//
//   node scripts/probe-cloud.mjs
//
// It prints claim fields, never the raw token. `createGatewaySession` and
// `enrollCloudMachine` are read-only here; nothing is installed or changed.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const dir = path.join(os.homedir(), ".mirasim", "run");
let files = [];
try {
  files = fs.readdirSync(dir).filter((f) => /^local-\d+\.token$/.test(f));
} catch (err) {
  console.error("cannot read", dir, String(err));
  process.exit(1);
}

function decode(value) {
  if (typeof value !== "string" || value.length < 40) return undefined;
  const parts = value.split(".");
  if (parts.length < 2) return { opaque: value.length };
  const out = {};
  for (let i = 0; i < Math.min(parts.length, 3); i++) {
    try {
      out[`part${i}`] = JSON.parse(Buffer.from(parts[i], "base64url").toString());
    } catch {
      out[`part${i}`] = `non-json(${parts[i].length})`;
    }
  }
  return out;
}

function walk(value, prefix = "") {
  if (value === null || value === undefined) return;
  if (typeof value === "string") {
    const d = decode(value);
    if (d) console.log(prefix, d);
    else if (value.length < 120) console.log(prefix, JSON.stringify(value));
    return;
  }
  if (Array.isArray(value)) {
    for (const [i, v] of value.slice(0, 4).entries()) walk(v, `${prefix}[${i}]`);
    return;
  }
  if (typeof value === "object") {
    for (const [k, v] of Object.entries(value)) {
      if (/email|ownerName|ownerEmail/i.test(k)) {
        console.log(prefix + k, "<redacted>");
        continue;
      }
      if (/token|secret|key|session|e2e|cert/i.test(k) && typeof v === "string") {
        const d = decode(v);
        console.log(prefix + k, d ?? `<${v.length} chars>`);
      } else {
        walk(v, prefix + k + ".");
      }
    }
  }
}

async function probe(port, token) {
  return new Promise((resolve) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      try { ws.close(); } catch {}
      resolve();
    };
    const ws = new WebSocket(`ws://127.0.0.1:${port}/ws?token=${encodeURIComponent(token)}`);
    let machines = [];
    let index = 0;
    const next = () => {
      if (index >= machines.length) return finish();
      const nodeId = machines[index++].nodeId;
      console.log(`\n== ${nodeId}: createGatewaySession`);
      ws.send(JSON.stringify({ type: "createGatewaySession", reqId: `probe-gw-${index}`, nodeId }));
    };
    ws.onopen = () => {
      console.log(`\n== port ${port}: listCloudMachines`);
      ws.send(JSON.stringify({ type: "listCloudMachines", reqId: "probe-list" }));
    };
    ws.onmessage = (event) => {
      let msg;
      try { msg = JSON.parse(event.data); } catch { return; }
      if (msg.type === "cloudMachines") {
        machines = msg.machines ?? [];
        console.log("ok=", msg.ok, "reason=", msg.reason, "machines=", machines.length);
        for (const m of machines) {
          console.log(`-- ${m.nodeId} kind=${m.kind ?? ""} role=${m.role ?? ""}`);
          walk(m, "");
        }
        next();
        return;
      }
      if (msg.type === "gatewaySession") {
        console.log("ok=", msg.ok, "reason=", msg.reason, "keys=", Object.keys(msg).sort().join(","));
        walk(msg, "");
        console.log(`\n== ${machines[index - 1]?.nodeId}: enrollCloudMachine`);
        ws.send(JSON.stringify({
          type: "enrollCloudMachine",
          reqId: `probe-enroll-${index}`,
          nodeId: machines[index - 1]?.nodeId,
        }));
        return;
      }
      if (msg.type === "cloudMachineGrant") {
        console.log("ok=", msg.ok, "reason=", msg.reason, "keys=", Object.keys(msg).sort().join(","));
        walk(msg, "");
        next();
      }
    };
    ws.onerror = () => finish();
    ws.onclose = () => finish();
    setTimeout(finish, 15000);
  });
}

for (const file of files) {
  const port = Number(file.match(/^local-(\d+)\.token$/)[1]);
  const token = fs.readFileSync(path.join(dir, file), "utf8").trim();
  if (token) await probe(port, token);
}
