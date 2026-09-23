# Claude Browser integration

Read when the plan resolves a thread to `claude_browser`. The [run skill](../../skills/attention-diet/SKILL.md) holds the rules shared by every browser.

## The browser

The isolated browser is the desktop app's built-in Browser pane, with tools named `mcp__Claude_Browser__*`. It is separate from the user's Chrome and keeps its own sign-in. Verify those tools exist before touching a source. The Claude in Chrome extension (`mcp__claude-in-chrome__*`) and computer use drive the user's everyday browser and desktop; they are not isolated and do not satisfy this access mode. If only those are available, as in a plain terminal session, report the missing dependency.

Open the first entry URL with `preview_start` and its `url`: it opens the pane when it is closed, and `tabs_create` works only while the pane is open. Keep the returned tab ID; that tab belongs to this task, so reuse it for that service. If login is required, ask the user to sign in inside the Browser pane and wait. Site permissions are requested per domain; a declined domain is an unavailable source.

## Reading

`get_page_text` and `read_page` return the whole page. On a list holding more items than the current window allows, that exposes excess cards, which count as inspected and force overrun recovery. Use them for single items, account checks and pages within the allowance. For lists, run the [bounded extraction helper](../../skills/attention-diet/references/browser-extraction.md) with `mcp__Claude_Browser__javascript_tool`: send the helper's source followed immediately by the call with `{window, recipe, previous}`; the result comes back as JSON and reads only up to the window's limit. Screenshots only when text is insufficient. Click only to navigate or expand content.

## Running the helpers

Invoke the Python helpers through Bash. Send JSON on stdin with a quoted heredoc delimiter (`<<'JSON'`) so source text is never expanded by the shell. Follow the run skill for bounded collection and capture payloads, and the plan's selected memory guide for remote history and storage.

## Finish

After `finalize`, close the tabs this task created with `tabs_close` and their tab IDs. Closing the last tab closes the pane; that is fine. Leave unrelated tabs and the Browser pane's sign-in alone.
