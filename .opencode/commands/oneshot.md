---
description: Research ticket and launch planning session
agent: build
model: openai/gpt-5.3-codex
subtask: true
---


1. use SlashCommand() to call /ralph_research with the given ticket number
2. launch a new session with `npx humanlayer launch --model opus --dangerously-skip-permissions --dangerously-skip-permissions-timeout 14m --title "plan ENG-XXXX" "/oneshot_plan ENG-XXXX"`
