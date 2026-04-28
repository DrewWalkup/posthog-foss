---
description: Execute ralph plan and implementation for a ticket
agent: build
model: openai/gpt-5.3-codex
subtask: true
---

1. use SlashCommand() to call /ralph_plan with the given ticket number
2. use SlashCommand() to call /ralph_impl with the given ticket number
