# Next up for ChatGPT

A work panel beside your conversation: browse a hierarchical plan or verified issues, curate Up next, and choose what to work on. The original inline continuation cards remain available.

This is the ChatGPT sibling of the [Next up Claude mod](../next-up/). The active model supplies suggestions and verified source snapshots; the server renders them and saves personal workboards. There is no extra model call, background turn hook, or stored provider credential. Inline cards and conversation panels are separate supported surfaces.

## Shared work plan · 0.4.1

The panel now has **Plan**, **Now** and **Sources** views. Plan holds a goal, steps and typed acceptance criteria. Edit goals, step titles and criteria directly in the panel; adding or materially editing a criterion reopens its acceptance state. Now shows the controlling run’s last reported action and remaining work. Recent changes exposes evidence and revision history.

Model-facing tools create/edit the plan, acknowledge its definition revision, report activity, record evidence for a criterion, and mark a step done only when its criteria are satisfied. See the [tool workflow](docs/progress-tools.md). Updates appear while the panel is visible, through a three-second local-store poll. Idempotency keys protect retries; stale criterion results remain in history without completing the changed criterion. Human-review criteria can be marked needs review, but this release cannot attest human approval.

**This first slice is board-owned.** It does not yet bind or write a live Markdown file, synchronize provider status, launch/interrupt an agent, or prove native Codex panel support. Imported Markdown and issue snapshots stay under Sources. Definition edits have their own revision, so activity reports do not conflict with an open editor; simultaneous definition edits still require reconciliation. Evidence is agent-reported and labeled accordingly, not independently certified by the store.

The preview’s **Record sample progress** button exercises the real tools with explicitly synthetic evidence. It preserves the board across theme changes. Try recording a result, editing that criterion, and seeing both the reopened criterion and pending acknowledgment.

## Source browser


Open **Next up · Work panel** from a conversation's plugin panels, or ask “Open my Next up work panel.” ChatGPT controls placement; this build's native right-side placement still needs a live host check.

- **Markdown:** import a `.md` file or paste its text. Headings and nested checkboxes become a navigable outline. The source order and completion markers are preserved. Documents are read-only snapshots, up to 40 KB / 250 nodes. Optional `<!-- next-up:stable-id -->` markers keep pins attached across edits. Anonymous references are revision-scoped and become missing after an edit rather than risk matching the wrong task.
- **Linear / GitHub:** ask ChatGPT to read a named project/repository through its existing connectors and load a verified snapshot. Status and assignee filters, source identifiers, descriptions, and verified parent/sub-issue relationships appear in the panel. Missing hierarchy and partial results are labeled. Each mode holds one scoped snapshot of at most 100 nodes; tool requests must fit within 64 KB.
- **Suggestions:** request up to three contextual next actions. Refreshing them never replaces your personal queue.
- **Up next:** pin items across modes, move them up/down, or remove them. Pins are personal priorities and do not change source status. Missing items remain visible.
- **Work on this:** inspect an item, choose Plan / Investigate / Implement or work / Review, edit its prompt, then explicitly send. Browsing and pinning send no message. Sending leaves the panel usable.
- **Saved:** name, reopen, or create workboards. A new panel creates a separate board unless given an explicit saved board reference. Reopening a saved board deliberately shares its queue with that conversation.

**Fetch latest sends a chat request.** The backend does not inherit other connectors' credentials. The panel checks its own stored revision every five seconds while visible; this does not poll Linear/GitHub. Direct provider adapters, live document watching, source write-back and autonomous execution are not implemented.

Workboards persist in `~/.local/share/next-up-chatgpt/boards.sqlite` (override with `NEXT_UP_DB`). The database stores source snapshots, pins, and prompt-delivery hashes/outcomes; it does not store complete sent prompts or full chat transcripts. Keep this private single-user deployment local or behind the existing authenticated private tunnel. It has no multi-user authorization layer. The HTTP executable refuses non-loopback binding.

After updating, restart the server/tunnel runtime, refresh the connection's tools in ChatGPT, and reopen the panel. Old v0.2 ephemeral panel references are not migrated. Existing inline cards remain supported.

Local panel preview: `http://127.0.0.1:3038/?panel`. The preview uses real MCP calls and a separate explicitly labeled sample workboard. “Load sample issues” adds synthetic Linear/GitHub fixtures. Sending captures the prompt locally and makes no model call. For isolated testing, use a temporary `NEXT_UP_DB` path.

## Update an existing installation

The marketplace package and the MCP server are separate. Updating the plugin loads its metadata and skill; it does **not** rebuild or restart a server already running from another checkout or cached plugin directory. The shipped `mcp.json` connects to `http://127.0.0.1:3038/mcp`.

1. Once this release is on the marketplace branch you follow, update the installed **Next up for ChatGPT** plugin through your host's plugin manager. A PR alone does not update a main-branch installation. A separately configured private ChatGPT tunnel connection also needs its own tool refresh.
2. In the updated `plugins/next-up-chatgpt` directory (or the updated installed package directory), run:

   ```sh
   npm ci
   npm run build
   ```

3. Stop the old Next up server using the terminal or supervisor that started it, then run `npm start` from this updated directory. Keep the same `NEXT_UP_DB` if you used a custom database path; the default database persists automatically. Do not run the sample preview database as your real workboard database.
4. Check the local server:

   ```sh
   curl -fsS http://127.0.0.1:3038/healthz
   ```

   Its version should be `0.4.1`. For a supervised private tunnel, reconnect/restart the existing runtime against the updated `server/stdio.mjs` with the existing setup script below; do not create another credential merely to upgrade. HTTP health checks do not verify a separate tunnel runtime.
5. Reconnect/refresh the plugin's tools in the host and start a fresh chat if the current chat retains the old tool list. Confirm that `read_work_plan`, `apply_plan_patch` and `record_criterion_result` are available alongside `open_next_steps_panel`. Reopen the panel so it loads the new versioned resource.

### First real plugin test

Ask in a chat with the updated tools enabled:

> Open my Next up work panel. Create a small shared plan for a real task I name, with two steps and explicit acceptance criteria. Show me the plan first; don't start execution yet.

Give a concrete small task, inspect the generated plan, then explicitly ask the agent to work through it and record evidence with the progress tools. While it works, edit a criterion in the panel. Check that it reads and acknowledges the revision before recording completion. Inspect the evidence and Recent changes; reopen the same saved workboard to check persistence.

This tests the installed tools and real agent behavior. The local preview's synthetic progress button is not a substitute. Native embedded placement is a separate host compatibility check: if the tools work but the panel cannot open, report that limitation rather than claiming installation failed or showing the synthetic preview as the real board.

## Run locally

Requires Node.js 22.13 or later (SQLite support).

```sh
cd plugins/next-up-chatgpt
npm ci
npm run build
npm run preview
```

Open `http://127.0.0.1:3038/`. The local preview uses the official MCP Apps host bridge and the actual production card. Clicking captures a prompt locally; it does **not** call a model or send it to ChatGPT. Try rejection, unavailable messaging, narrow widths, and both themes.

For the MCP server without preview routes:

```sh
npm start
```

The Streamable HTTP endpoint is `http://127.0.0.1:3038/mcp`. Health: `/healthz`. Local binding is the default. `PORT` and loopback `HOST` configure the local endpoint. Comma-separated `MCP_ALLOWED_HOSTS` permits expected host headers through a private proxy. Both server and preview refuse non-loopback binding.

## Connect in ChatGPT

The localhost URL in `mcp.json` is for clients running on this computer. Ordinary cloud ChatGPT cannot reach it directly. For private testing use an [OpenAI Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels):

1. In [Platform tunnel settings](https://platform.openai.com/settings/organization/tunnels), create or select a tunnel associated with the target ChatGPT workspace. A runtime API key and Tunnels Read/Use permissions are required; creation also requires Manage.
2. Install OpenAI's official `tunnel-client`, then run `tunnel-client help quickstart`. Configure an HTTP profile pointing at `http://127.0.0.1:3038/mcp`, using the tunnel ID. Keep the credential in the client's environment or supported secret configuration, never in this repository or a prompt.
3. Run the server and tunnel client. Use the client's `doctor` command to check readiness.
4. In ChatGPT, enable Developer mode under **Settings → Security and login** if needed. Open **Plugins → + → Create custom MCP server**, enter a name and description, choose **Tunnel**, and select that tunnel. This renderer uses **No authentication** at the MCP layer; the private tunnel authenticates access. Create the plugin and connect it. Discovery includes `render_next_steps`, the work-panel tools, and `import_work_source`.
5. Open the installed plugin and choose **Try in chat**, then ask: **“Show three useful next-step buttons for this conversation using render_next_steps.”**

A public or multi-user deployment requires authentication, per-user ownership checks, and an explicit deployment design. This version is a private single-user server. No public endpoint has been deployed.

See [Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt) for current account and workspace requirements. A successful local preview does not establish that your account supports the ChatGPT host integration.

### Managed local tunnel launcher

Once you have a tunnel ID, an official `tunnel-client` installation, and a runtime API key, run:

```sh
python3 scripts/connect-tunnel.py --tunnel-id YOUR_TUNNEL_ID
```

The launcher asks for the key with hidden terminal input and saves it to `~/.config/next-up-chatgpt/runtime-key` with owner-only permissions. The credential is neither a command-line argument nor a repository file. It uses the official client's managed runtime to launch `server/stdio.mjs`, so the MCP server does not depend on the preview terminal staying open. The tunnel remains private. Inspect `tunnel-client runtimes status next-up-chatgpt --json`; only a running, healthy, ready runtime establishes a working connection. Creating the tunnel alone is insufficient.

## Add the skill

The root `plugin.json`, `mcp.json`, and `skills/next-up/SKILL.md` form the local plugin. It is discoverable in this repository's OpenAI marketplace. Build and run the server before enabling the local plugin. Installing only the developer-mode MCP connection does not install its packaged skill.

For a developer-mode ChatGPT test without an installed skill, use:

> Enable Next up for this conversation. After completing useful chunks of work, use render_next_steps to offer up to three specific continuation prompts. Use conversation context and verified Linear issues from my connected Linear tools where relevant. Do not interrupt required questions or approvals, invent issues, or execute a suggestion before I select it. Stop offering suggestions when I ask.

For local plugin discovery and installation, follow [OpenAI's local marketplace instructions](https://developers.openai.com/plugins/build/plugins#install-a-local-plugin-manually). In cloud ChatGPT, use the registered tunnel connection; the local marketplace's localhost server configuration is not a substitute for it.

## Linear

The skill reads issues through the **existing Linear connector** and gives the renderer verified issue IDs and URLs. A card alone cannot read other connectors or verify the model's claims. When no Linear connector is available, it can still offer conversation continuations. It never updates issue status merely because a suggestion was clicked.

## Checks

```sh
npm test
```

`npm test` exercises the live MCP endpoint with the official client: discovery, resource reads, valid and invalid suggestions, request limits, and independent calls. Verify the UI in the local preview: select a step, preview and edit another, dismiss, reject a message, and disable messaging. The preview uses the official MCP Apps bridge, not a live ChatGPT account. See [the validation record](docs/validation.md) for what was actually verified and what remains.

## Data and behavior

- No telemetry, transcript capture, external model requests, or direct provider requests.
- Workboards, shared plans, criterion evidence, activity events, idempotency records and imported source content persist in the private SQLite database; source descriptions remain untrusted data.
- Browsing, filtering, pinning, editing and importing Markdown send no chat prompt. Explicit source-fetch, suggestion and Send prompt actions use the host's `ui/message` bridge.
- Each panel send reserves a delivery record before messaging. Explicit rejection permits retry; uncertain delivery blocks automatic retry. Identical sent prompts require an intentional edit before another send. This does not mark an issue started or completed.
- Sources use stable provider IDs; Markdown IDs are explicit or revision-scoped. Concurrent writes require the current board revision.
- Widget state can restore view state where supported. Durable workboards live on the server, not browser storage.
- See [the work-panel plan](docs/work-panel-plan.md) for the remaining direct-adapter work, and [validation](docs/validation.md) for the checked boundaries.
- The [shared work-plan draft](docs/shared-work-plan.md) describes the wider roadmap; the board-owned progress loop is implemented, while live source editing and native host orchestration remain future work.

## Official references

- [MCP Apps UI](https://developers.openai.com/plugins/build/chatgpt-ui)
- [Plugin Extensions](https://developers.openai.com/plugins/build/extensions)
- [Packaging](https://developers.openai.com/plugins/build/plugins)

MIT, matching the repository license.
