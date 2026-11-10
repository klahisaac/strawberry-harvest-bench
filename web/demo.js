/* The demo page: renders everything from window.DEMO, written by `harvest demo-bake`. */
(() => {
  const D = window.DEMO;
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const SVG = "http://www.w3.org/2000/svg";
  if (!D) {
    document.querySelector("main").innerHTML =
      '<p class="note">No demo data yet. Run <code>uv run harvest demo-bake --agent</code>.</p>';
    return;
  }
  const V = D.meta.versions;
  const inline = (t) => esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
  /* Just enough markdown for the agent's text: bullets, **bold**, `code`. */
  function md(text) {
    const out = [];
    let list = [];
    const flush = () => { if (list.length) { out.push(`<ul>${list.map((l) => `<li>${inline(l)}</li>`).join("")}</ul>`); list = []; } };
    for (const raw of (text || "").split("\n")) {
      const l = raw.trim();
      if (!l) { flush(); continue; }
      if (/^[-*] /.test(l)) list.push(l.slice(2)); else { flush(); out.push(`<p>${inline(l)}</p>`); }
    }
    flush();
    return out.join("");
  }
  const how = (title, items) => `<p class="how-title">${esc(title)}</p><ul>${items.map((i) => `<li>${i}</li>`).join("")}</ul>`;

  // ---- the stack ----------------------------------------------------------------
  $("stack").innerHTML = [
    ["Physics", `MuJoCo ${esc(V.mujoco)}`],
    ["Rendering", "MuJoCo's OpenGL renderer, on the GPU"],
    ["Perception", "colour threshold on rendered RGB-D"],
    ["Video", "H.264 via ffmpeg"],
    ["AI agent", `Claude Code ${esc(V.claude_code)} · ${esc(D.agent.model)}`],
  ].map(([k, v]) => `<div><span>${k}</span><b>${v}</b></div>`).join("");

  // ---- 1: logs --------------------------------------------------------------------
  $("logTable").innerHTML = `<thead><tr><th>time (UTC)</th><th>robot</th><th>row</th><th>scenario</th><th>pick</th>
      <th>event</th><th>outcome</th><th>ripeness</th><th>force</th><th>cycle</th><th>flags</th></tr></thead><tbody>` +
    D.logs.map((r) => {
      const bad = r.abnormal;
      return `<tr class="${bad ? "abnormal picked-row" : ""}">
        <td>${esc(r.time.slice(11, 19))}</td><td>${esc(r.robot)}</td><td>${esc(r.row)}</td>
        <td>${esc(r.scenario)}</td><td>${esc(r.pick)}</td><td>${esc(r.event)}</td>
        <td><span class="pill ${bad ? "bad" : "ok"}">${esc(r.outcome)}</span></td>
        <td class="num">${r.est_ripeness.toFixed(2)}</td><td class="num">${r.peak_force_n.toFixed(1)} N</td>
        <td class="num">${r.cycle_s.toFixed(1)} s</td>
        <td>${r.flags.length ? r.flags.map((f) => `<span class="pill bad">${esc(f)}</span>`).join(" ") : '<span class="pill muted">none</span>'}</td>
      </tr>`;
    }).join("") + "</tbody>";
  const inc = D.incident;
  $("incTitle").textContent = `${inc.row.scenario} / ${inc.row.pick}: ${inc.row.outcome.replace("_", " ")}`;
  $("incWhy").innerHTML = inc.flags.map((f) => `<b>${esc(f.kind)}</b> — ${esc(f.why)}`).join("<br>");
  $("incEvents").innerHTML = inc.events.map((e) => {
    const keep = ["est_ripeness", "reached", "error_m", "outcome", "peak_force_n", "cut_berry_id"];
    const extra = keep.filter((k) => k in e && e[k] !== null).map((k) => `${k}=${JSON.stringify(e[k])}`).join(" ");
    return `<div class="${e.event === "pick.failed" ? "bad" : ""}"><span class="t">${e.t.toFixed(2).padStart(5)}s</span>  ${esc(e.event.padEnd(18))} ${esc(extra)}</div>`;
  }).join("");

  // ---- 2: photo -> simulation -----------------------------------------------------
  const P = D.photo;
  $("blobSvg").innerHTML = P.blobs.map((b) => {
    const ripe = b.kind === "ripe";
    return `<ellipse cx="${b.cx}" cy="${b.cy}" rx="${b.width / 2}" ry="${b.height / 2}" fill="none"
        stroke="${ripe ? "#ff3b55" : "#ffe27a"}" stroke-width="1.2" ${ripe ? "" : 'stroke-dasharray="3 2"'}/>
      <text x="${b.cx}" y="${b.cy + 2.5}" text-anchor="middle" font-size="6" font-weight="700" fill="#fff"
        paint-order="stroke" stroke="#000" stroke-width="1.4">${ripe ? "ripe" : "unripe"}</text>`;
  }).join("");
  $("berryTable").innerHTML = `<thead><tr><th>berry</th><th>colour class</th><th>radius</th>
      <th>position in the simulator (m)</th><th>depth</th></tr></thead><tbody>` +
    P.berries.map((b) => `<tr><td>${esc(b.id)}</td>
      <td><span class="pill ${b.ripeness > 0.6 ? "bad" : "muted"}">${b.ripeness > 0.6 ? "ripe" : "unripe"}</span></td>
      <td class="num">${b.radius_mm.toFixed(1)} mm</td><td class="num">(${b.pos.map((v) => v.toFixed(3)).join(", ")})</td>
      <td>${b.in_front ? '<span class="pill bad">in front of the ripe berry</span>' : '<span class="pill muted">beside</span>'}</td></tr>`).join("") +
    "</tbody>";
  const A = P.assumptions;
  $("howSim").innerHTML = how("How the simulation was built", [
    `<b>Engine.</b> MuJoCo ${esc(V.mujoco)}, the open-source physics engine, stepping at 2 ms with an implicit integrator. Contacts, friction and joint servos are all simulated; nothing about an outcome is decided by a lookup table.`,
    `<b>The world.</b> A scene file (MJCF) generated in Python: a gutter, a canopy of leaves behind it, grow lights, and the fruit. Each berry is a free 22 g ellipsoid held to its hanging point by a weld constraint that stands in for the stem — cutting the stem means switching that constraint off. Berries are textured by ripeness, pale green to deep red.`,
    `<b>The robot.</b> A five-joint arm on a rail — rail, yaw, shoulder, elbow, wrist — driven by position servos, with a cutter and a catch tray the wrist keeps level. It sees through a simulated RGB-D survey camera.`,
    `<b>From the photo.</b> Colour separates ripe (red) from unripe (pale) fruit and gives each berry's centre and size in pixels. A photo has no scale and no depth, so two numbers are assumed: the ripe berry is <b>${A.ripe_radius_mm} mm</b> in radius, which sets ${(P.m_per_px * 1000).toFixed(2)} mm per pixel, and the unripe berry that overlaps it hangs <b>${A.front_depth_mm} mm</b> in front of it.`,
    `<b>The render on the right</b> is MuJoCo's own OpenGL renderer, looking at the simulated cluster from where the photographer stood.`,
  ]);

  // ---- 3 and 4: the simulated attempts --------------------------------------------
  function verdict(r, title) {
    const lines = r.attempts.map((a) => `<li><code>${esc(a.label)}</code> → ${esc(a.aimed_at)}: <b>${esc(a.outcome)}</b>
      ${a.cut ? ` · cut <code>${esc(a.cut)}</code>` : ""}${a.knocked.length ? ` · knocked ${a.knocked.map(esc).join(", ")}` : ""}
      ${a.note ? `<br><span>${esc(a.note)}</span>` : ""}</li>`).join("");
    return `<p class="big ${r.passed ? "ok" : "bad"}">${esc(title)}</p>
      <p>${r.passed ? "Cut at its own stem, caught and packed; no other fruit touched."
        : `Fruit damaged: ${r.damaged.map(esc).join(", ") || "—"}`}</p><ul>${lines}</ul>`;
  }
  const B = D.before, F = D.after;
  $("beforeVerdict").innerHTML = verdict(B, "Failure reproduced");
  const filmed = [
    `<b>Frames</b> are rendered by MuJoCo's OpenGL renderer from a fixed virtual camera beside the gutter, every 1/48 s of simulated time, and encoded with ffmpeg as H.264 at 24 frames per second — so the video plays at half speed. The last frame is held for a second.`,
    `<b>Nothing is animated by hand.</b> The arm moves because its servos drive it; fruit moves because the arm or gravity pushes it. Damage is read from contact forces: more than 6 N on fruit still attached is a torn stem, more than 1.5 N on a neighbour is a knock.`,
  ];
  $("howBefore").innerHTML = how("How this video was made", [
    `<b>The run.</b> The robot's code as it was, unchanged: the survey camera renders the scene, the colour detector finds the berries, the baseline policy picks the ripe one, and the arm plans and drives to its stem. Command: <code>python -m harvestbench.photocase run</code>.`,
    ...filmed,
  ]);
  $("cmpBefore").innerHTML = verdict(B, "Before: not harvested");
  $("cmpAfter").innerHTML = verdict(F, F.passed ? "After: harvested" : "After: still failing");
  $("howCompare").innerHTML = how("How these two videos were made", [
    `<b>The same experiment twice.</b> The same simulated cluster, the same camera, the same command. <i>Before</i> runs the original code; <i>after</i> runs the agent's edited copy, put first on the Python path. The experiment itself (<code>photocase.py</code>) is copied along unchanged, so only the robot's code differs.`,
    ...filmed,
  ]);

  // ---- 4: the agent ----------------------------------------------------------------
  const G = D.agent;
  const firstPass = G.checks.find((c) => c.passed);
  const last = G.checks[G.checks.length - 1];
  const clock = (t) => `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
  $("agentCard").innerHTML = `
    <div class="agent-stats">
      <div><span>agent</span><b>Claude Code ${esc(V.claude_code)}</b></div>
      <div><span>model</span><b>${esc(G.model)}</b></div>
      <div><span>time</span><b>${Math.floor(G.seconds / 60)} min ${G.seconds % 60} s</b></div>
      <div><span>turns</span><b>${G.turns}</b></div>
      <div><span>check runs</span><b>${G.checks.length}${firstPass ? ` · first pass at ${clock(firstPass.t)}` : ""} · last run ${last && last.passed ? "passed" : "failed"}</b></div>
    </div>
    <p class="agent-how">Run headless (<code>claude -p</code>) on a scratch copy of the code, with the field report as its
      prompt. It could read and edit the copy and run exactly one command, <code>./check.sh</code>: the photographed
      cluster, then both smoke tiers. It was told to fix the robot, not the experiment, and not to read the
      simulator's ground truth — only what the robot senses.</p>`;
  $("explain").innerHTML = md(D.pr.body);
  $("diff").innerHTML = D.diff.map((f) => `<div class="diff-file"><header><span>${esc(f.path)}</span>
      <span class="add">+${f.added}</span><span class="del">−${f.removed}</span></header>
      <pre>${f.diff.split("\n").map((l) => {
        const cls = l.startsWith("+") && !l.startsWith("+++") ? "add" : l.startsWith("-") && !l.startsWith("---") ? "del" : l.startsWith("@@") ? "hunk" : "";
        return `<span class="${cls}">${esc(l) || " "}</span>`;
      }).join("")}</pre></div>`).join("");
  $("sayings").innerHTML = G.transcript.filter((x) => x.say).map((x) =>
    `<div class="say"><span>${Math.floor(x.t / 60)}:${String(x.t % 60).padStart(2, "0")}</span><div>${md(x.say)}</div></div>`).join("");

  // ---- 5: smoke --------------------------------------------------------------------
  $("smoke").innerHTML = Object.entries(D.smoke).map(([tier, s]) => `
    <div class="smoke-row"><span class="pill ${s.passed ? "ok" : "bad"}">${s.passed ? "PASS" : "FAIL"}</span>
      <div><b>${tier === "demo" ? "Demo tier" : "Regular smoke tier"}</b> — ${s.scenarios.map(esc).join(", ")}
        <span class="muted">· judges ${esc(s.judges)}, against the recorded baseline</span></div></div>`).join("") +
    `<p class="smoke-note">${Object.values(D.smoke).every((s) => s.passed)
      ? "Both tiers pass on the agent's code: ordinary picking is no worse than before the fix."
      : "A smoke tier failed on the agent's code."}</p>`;

  // ---- 6: PR -------------------------------------------------------------------------
  const R = D.pr;
  const added = D.diff.reduce((s, f) => s + f.added, 0), removed = D.diff.reduce((s, f) => s + f.removed, 0);
  const allPass = F.passed && Object.values(D.smoke).every((s) => s.passed);
  $("pr").innerHTML = `<div class="pr-head"><h3>${esc((R.title || "").replace(/\*\*/g, ""))}</h3>
      <div class="pr-meta"><span class="pr-state">Open</span>
        <span><code>${esc(R.branch)}</code> → <code>${esc(R.base)}</code></span>
        <span>${D.diff.length} file${D.diff.length === 1 ? "" : "s"} · +${added} −${removed}</span>
        <span>opened by the agent</span></div></div>
    <div class="pr-body">${md(R.body)}</div>
    <div class="pr-checks">
      <span class="${F.passed ? "" : "fail"}">field case FIELD-0417</span>
      ${Object.entries(D.smoke).map(([t, s]) => `<span class="${s.passed ? "" : "fail"}">${t === "demo" ? "demo tier" : "smoke tier"}</span>`).join("")}
      <span class="${D.diff.some((f) => f.protected) ? "fail" : ""}">no protected files touched</span></div>
    <div class="pr-review"><b>Review requested from ${esc(R.reviewer)}.</b>
      ${allPass ? "All checks pass. Please review the change before it merges and goes to a field test."
        : "Some checks fail; please review."}</div>`;

  $("foot").textContent = `Recorded demo of real operations · generated ${D.meta.generated} by harvest demo-bake · MuJoCo ${V.mujoco} · Python ${V.python}`;
})();
