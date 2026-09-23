---
description: "Environment check: the plugin's Python helpers run inside an eval sandbox."
tags: [functional, smoke]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Skill, Read, Glob, Grep, Bash]
---

Use Attention Diet's tune skill to show me the current settings of my default attention diet. Don't change anything.
