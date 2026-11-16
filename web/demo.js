/* The demo page: renders everything from window.DEMO, written by src/harvest/bake_demo.py. */
(() => {
  const D = window.DEMO;
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  if (!D) {
    document.querySelector("main").innerHTML =
      '<p class="note">No demo data yet. Run <code>uv run --group demo python src/harvest/bake_demo.py</code>.</p>';
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
      if (!l || /^#+\s*$/.test(l)) { flush(); continue; }
      if (/^[-*] /.test(l)) list.push(l.slice(2));
      else { flush(); out.push(`<p>${inline(l.replace(/^#+\s*/, ""))}</p>`); }
    }
    flush();
    return out.join("");
  }
  const how = (title, items) => `<p class="how-title">${esc(title)}</p><ul>${items.map((i) => `<li>${i}</li>`).join("")}</ul>`;
  const pill = (outcome) => `<span class="pill ${outcome === "picked" ? "ok" : "bad"}">${esc(outcome)}</span>`;
  const R = D.rules;
  const failed = D.logs.find((l) => l.pick === D.failed_pick);
  const before = D.before.find((r) => r.pick === D.failed_pick);
  const after = D.after.find((r) => r.pick === D.failed_pick);

  // ---- the stack ----------------------------------------------------------------
  $("stack").innerHTML = [
    ["Images", "Blender Cycles, RGB-D"],
    ["Physics", `MuJoCo ${esc(V.mujoco)}`],
    ["Robot", "6-axis arm with a cutter"],
    ["Perception", "YOLO11n + depth"],
    ["AI agent", `Claude Code ${esc(V.claude_code)} · ${esc(D.agent.model)}`],
  ].map(([k, v]) => `<div><span>${k}</span><b>${v}</b></div>`).join("");

  // ---- 1: the field log -----------------------------------------------------------
  $("logTable").innerHTML = `<thead><tr><th>time (UTC)</th><th>robot</th><th>row</th><th>pick</th>
      <th>event</th><th>outcome</th><th>ripeness</th><th>force</th><th>cycle</th><th>flags</th></tr></thead><tbody>` +
    D.logs.map((r) => `<tr class="${r.abnormal ? "abnormal picked-row" : ""}">
        <td>${esc(r.time.slice(11, 19))}</td><td>${esc(r.robot)}</td><td>${esc(r.row)}</td>
        <td>${esc(r.pick)}</td><td>${esc(r.event)}</td><td>${pill(r.outcome)}</td>
        <td class="num">${r.est_ripeness.toFixed(2)}</td><td class="num">${r.peak_force_n.toFixed(1)} N</td>
        <td class="num">${r.cycle_s.toFixed(1)} s</td>
        <td>${r.flags.length ? r.flags.map((f) => `<span class="pill bad">${esc(f)}</span>`).join(" ") : '<span class="pill muted">none</span>'}</td>
      </tr>`).join("") + "</tbody>";
  $("thumbs").innerHTML = D.logs.map((r) => `<figure class="${r.abnormal ? "bad" : ""}">
      <img src="demo/field/${r.pick}_rgb.png" alt="RGB image of ${r.pick}" loading="lazy">
      <figcaption>${esc(r.pick)} · ${esc(r.outcome)}</figcaption></figure>`).join("");
  $("incTitle").textContent = `${failed.pick}: ${failed.outcome.replace("_", " ")}`;
  $("incWhy").innerHTML = `<b>${esc(failed.flags.join(", "))}</b> — the cutter hit fruit with ${failed.peak_force_n.toFixed(1)} N, over the
    robot's ${R.force_limit_n} N limit, and the robot stopped the attempt after ${failed.cycle_s.toFixed(1)} s. Ripeness of the target, as
    the robot estimated it: ${failed.est_ripeness.toFixed(2)}.`;
  $("incRgb").src = `demo/field/${failed.pick}_rgb.png`;
  $("incDepth").src = `demo/field/${failed.pick}_depth.png`;

  // ---- 2: image -> simulation -------------------------------------------------------
  $("foundImg").src = `demo/field/${failed.pick}_rgb.png`;
  // YOLO's boxes, then their labels on top, so no box line crosses a label.
  const boxes = D.found.map((b) => {
    const [x0, y0, x1, y1] = b.box;
    const color = b.ripe ? "#ff3b55" : "#ffe27a";
    return `<rect x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}" rx="6" fill="none" stroke="${color}"
        stroke-width="${b.target ? 4 : 3}" ${b.ripe ? "" : 'stroke-dasharray="10 6"'}/>`;
  });
  const labels = D.found.map((b) => {
    const [x0, y0, x1, y1] = b.box;
    const label = `${b.ripe ? "ripe" : "unripe"} ${b.confidence.toFixed(2)}${b.target ? " · target" : ""}`;
    return `<text x="${(x0 + x1) / 2}" y="${b.target ? y1 + 26 : y0 - 8}" text-anchor="middle" font-size="20"
        font-weight="700" fill="#fff" paint-order="stroke" stroke="#000" stroke-width="4">${label}</text>`;
  });
  $("foundSvg").innerHTML = boxes.join("") + labels.join("");
  const target = D.found.find((b) => b.target);
  $("berryTable").innerHTML = `<thead><tr><th>berry</th><th>class</th><th>radius</th>
      <th>centre in the simulator (m)</th><th>relative to the target</th></tr></thead><tbody>` +
    D.found.map((b, i) => {
      const ahead = target && !b.target ? Math.round((target.center[1] - b.center[1]) * 1000) : null;
      const where = b.target ? '<span class="pill ok">the target</span>'
        : ahead > 30 ? `<span class="pill bad">${ahead} mm in front of it</span>`
        : `<span class="pill muted">beside or behind it</span>`;
      return `<tr><td>${i + 1}</td><td><span class="pill ${b.ripe ? "bad" : "muted"}">${b.ripe ? "ripe" : "unripe"}</span></td>
        <td class="num">${b.radius_mm.toFixed(1)} mm</td>
        <td class="num">(${b.center.map((v) => v.toFixed(3)).join(", ")})</td><td>${where}</td></tr>`;
    }).join("") + "</tbody>";
  $("howSim").innerHTML = how("How the simulation is built", [
    `<b>Finding berries.</b> A YOLO11n model, trained on 160 Blender RGB images of strawberry clusters, boxes each berry and labels it ripe or unripe. The depth in the middle of each box says how far away the berry is; depth farther than the gutter is left out.`,
    `<b>Placing them.</b> The depth image gives how far each berry's surface is; with the camera's focal length (600 px) that becomes a 3D centre and a radius. The robot's camera sits at the same place on the robot for every attempt, so every berry lands in the same frame as the arm.`,
    `<b>The robot.</b> A 6-axis arm — three joints in the shoulder and elbow, a wrist that pitches, yaws and rolls — with a cutter at the tip, driven by position servos. Its cutter follows straight lines at ${R.tool_speed_m_s} m/s, joint angles from inverse kinematics.`,
    `<b>The engine.</b> MuJoCo ${esc(V.mujoco)}, stepping at 2 ms. Berries are solid; when the arm presses on one, MuJoCo reports the contact force.`,
  ]);

  // ---- 3: reproduce -----------------------------------------------------------------
  const resultTable = (rows, compareField) => `<thead><tr><th>pick</th><th>field</th><th>simulation</th>
      <th>peak force on fruit</th><th>cycle</th><th>berries found</th><th></th></tr></thead><tbody>` +
    rows.map((r) => {
      const note = compareField ? (r.outcome === r.field ? "same as the field" : "differs from the field")
        : (r.outcome === "picked" ? "picked" : "not picked");
      const good = compareField ? r.outcome === r.field : r.outcome === "picked";
      return `<tr class="${r.pick === D.failed_pick ? "picked-row" : ""}"><td>${esc(r.pick)}</td><td>${pill(r.field)}</td>
        <td>${pill(r.outcome)}</td><td class="num">${r.peak_force_n.toFixed(1)} N</td><td class="num">${r.cycle_s.toFixed(1)} s</td>
        <td class="num">${r.berries}</td><td><span class="pill ${good ? "ok" : "bad"}">${note}</span></td></tr>`;
    }).join("") + "</tbody>";
  const same = D.before.filter((r) => r.outcome === r.field).length;
  const verdict = (r, title) => `<p class="big ${r.outcome === "picked" ? "ok" : "bad"}">${esc(title)}</p>
    <p>${r.outcome === "picked"
      ? `The cutter reached the stem and closed; no fruit was pressed harder than ${R.force_limit_n} N.`
      : `The cutter hit fruit with <b>${r.peak_force_n.toFixed(1)} N</b>, over the ${R.force_limit_n} N limit, and the robot stopped after ${r.cycle_s.toFixed(1)} s.`}</p>`;
  $("beforeVerdict").innerHTML = verdict(before, "Failure reproduced") +
    `<p>The field log said <b>${esc(failed.outcome)}</b>; the simulation says <b>${esc(before.outcome)}</b>.
      Across all ten attempts, <b>${same} of ${D.before.length}</b> end in the simulator as they did in the field.</p>`;
  $("beforeTable").innerHTML = resultTable(D.before, true);
  $("howBefore").innerHTML = how("How this was run and judged", [
    `<b>The robot's code as it was.</b> <code>robot_controller.py</code> picks the ripe berry nearest the camera's line of sight, lines the cutter up 12 cm in front of its stem, and goes straight in.`,
    `<b>The verdict</b> is read from the simulation: more than ${R.force_limit_n} N on any fruit is a collision, and the robot stops there, as the real one does; the cutter tip ending more than ${R.reach_mm} mm from the cut point is a miss; otherwise the berry is picked.`,
    `<b>The video</b> is rendered by MuJoCo's own renderer, 30 frames per simulated second, and encoded with ffmpeg as H.264.`,
  ]);

  // ---- 4: the agent ---------------------------------------------------------------
  const G = D.agent;
  const firstPass = (G.checks || []).find((c) => c.passed);
  const last = (G.checks || [])[(G.checks || []).length - 1];
  const clock = (t) => `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
  $("agentCard").innerHTML = `
    <div class="agent-stats">
      <div><span>agent</span><b>Claude Code ${esc(V.claude_code)}</b></div>
      <div><span>model</span><b>${esc(G.model)}</b></div>
      <div><span>time</span><b>${Math.floor(G.seconds / 60)} min ${G.seconds % 60} s</b></div>
      <div><span>turns</span><b>${G.turns}</b></div>
      <div><span>check runs</span><b>${(G.checks || []).length}${firstPass ? ` · first pass at ${clock(firstPass.t)}` : ""} · last ${last && last.passed ? "passed" : "failed"}</b></div>
    </div>
    <p class="agent-how">Run headless (<code>claude -p</code>) on a scratch copy of the code, with the field report as
      its prompt. It could read and edit the copy and run exactly one command, <code>./check.sh</code>, which reruns all
      ten logged attempts in the simulator. It was told to change only <code>robot_controller.py</code>: the simulator
      and the data are the experiment.</p>`;
  $("explain").innerHTML = md(D.pr.explanation || D.pr.body);
  $("diff").innerHTML = D.diff.map((f) => `<div class="diff-file"><header><span>${esc(f.path)}</span>
      <span class="add">+${f.added}</span><span class="del">−${f.removed}</span></header>
      <pre>${f.diff.split("\n").map((l) => {
        const cls = l.startsWith("+") && !l.startsWith("+++") ? "add" : l.startsWith("-") && !l.startsWith("---") ? "del" : l.startsWith("@@") ? "hunk" : "";
        return `<span class="${cls}">${esc(l) || " "}</span>`;
      }).join("")}</pre></div>`).join("") || '<p class="note">The agent changed nothing.</p>';
  $("sayings").innerHTML = (G.transcript || []).filter((x) => x.say).map((x) =>
    `<div class="say"><span>${clock(x.t)}</span><div>${md(x.say)}</div></div>`).join("");
  $("cmpBefore").innerHTML = verdict(before, "Before: not picked");
  $("cmpAfter").innerHTML = verdict(after, after.outcome === "picked" ? "After: picked" : "After: still failing");

  // ---- 5: rerun ----------------------------------------------------------------------
  const picked = D.after.filter((r) => r.outcome === "picked").length;
  $("afterTable").innerHTML = resultTable(D.after, false);
  $("afterNote").textContent = picked === D.after.length
    ? `All ${picked} attempts are picked with the agent's code: the nine ordinary picks still work, and ${D.failed_pick} now does too.`
    : `${picked} of ${D.after.length} attempts are picked with the agent's code.`;

  // ---- 6: PR -------------------------------------------------------------------------
  const P = D.pr;
  const added = D.diff.reduce((s, f) => s + f.added, 0), removed = D.diff.reduce((s, f) => s + f.removed, 0);
  const onlyController = D.diff.every((f) => !f.protected);
  const allPicked = picked === D.after.length;
  $("pr").innerHTML = `<div class="pr-head"><h3>${esc((P.title || "").replace(/\*\*/g, ""))}</h3>
      <div class="pr-meta"><span class="pr-state">Open</span>
        <span><code>${esc(P.branch)}</code> → <code>${esc(P.base)}</code></span>
        <span>${D.diff.length} file${D.diff.length === 1 ? "" : "s"} · +${added} −${removed}</span>
        <span>opened by the agent</span></div></div>
    <div class="pr-body">${md(P.body)}</div>
    <div class="pr-checks">
      <span class="${after.outcome === "picked" ? "" : "fail"}">field case ${esc(D.failed_pick)} picked</span>
      <span class="${allPicked ? "" : "fail"}">all ${D.after.length} logged attempts picked</span>
      <span class="${onlyController ? "" : "fail"}">only robot_controller.py changed</span></div>
    <div class="pr-review"><b>Review requested from ${esc(P.reviewer)}.</b>
      ${allPicked && onlyController ? "All checks pass. Please review the change before it merges and goes to a field test."
        : "Some checks fail; please review."}</div>`;

  $("foot").textContent = `Recorded demo · generated ${D.meta.generated} by bake_demo.py · MuJoCo ${V.mujoco} · Python ${V.python}`;
})();
