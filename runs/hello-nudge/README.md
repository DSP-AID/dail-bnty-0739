# hello-nudge — live proof of the pause fix

Run against an endpoint we own (`runner_local.py samples/hello`), after the
`agent_core.run_loop` pause-nudge fix. Step 1 is the exec that writes
`hello.txt`; step 2 was a content-only reply, which the harness now nudges once
instead of treating as a finish; step 3 is a verification `ls -la && cat -A`;
step 4 is the real final message. Before the fix this pattern stopped early —
see `runs/long-memo-retry` (7 steps, deliverables left unwritten).
