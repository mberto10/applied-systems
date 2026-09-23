---
type: llm
---

PASS if the reply states that the configured browser integration (the Claude Browser pane) is not available in this session, and either asks how the source should be reached instead (for example agent-browser, a connector, or keeping the choice for a host that has it) or installs the contract while clearly saying the source cannot be checked here.
FAIL if it presents the setup as ready to run here without mentioning the missing browser, silently switches to a different access route, or starts a briefing.
