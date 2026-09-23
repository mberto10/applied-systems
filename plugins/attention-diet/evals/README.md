# Attention Diet evals

Run with Claude Code's `claude plugin eval` from the plugin root, in your own terminal (the runner needs your login). Every run starts in a throwaway home with only this plugin loaded; your contracts, memory and accounts are never touched. No case reaches a real service.

| Tag | Cases | Checks | Needs |
|---|---|---|---|
| `routing` | 4 | ordinary phrasing reaches check, setup or tune; unrelated requests trigger nothing | nothing |
| `guardrails` | 2 | no replies or account actions; no learning from clicks | judge model |
| `functional` | 7 | real helpers: tune applies one revision, lists diets without changing them and puts an all-source exclusion in `intent.excluded`; a one-off stays one-off; setup and the run report a missing browser instead of switching route or inventing items; smoke check | `--scaffold --allow-tools Bash` |

`_shared/prepare.sh` gives each functional run the plugin's Python environment at `~/.cache/attention-diet-venv` (copied from yours, else installed from `requirements.txt`) and, where needed, the fictional default contract `_shared/eval-diet.json`. Eval runs have no Claude Browser pane, which is what the missing-browser cases rely on.

```sh
# 1. Smoke check first: one run, confirms the helpers work in the sandbox
claude plugin eval . --tag smoke --scaffold --allow-tools Bash --ablation none

# 2. Routing and guardrails, with the no-plugin baseline (cheap)
claude plugin eval . --tag routing guardrails

# 3. Functional cases, 3 runs each, no baseline (without the plugin they cannot pass)
claude plugin eval . --tag functional --scaffold --allow-tools Bash --ablation none --max-cost-usd 15
```

`--case` takes one name or glob per run. The first run asks you to trust this directory. Results and an HTML report go to `evals/results/` (git-ignored).

If the smoke case fails with "Operation not permitted" on `scripts/`, the sandbox cannot read the plugin inside your home folder. Run from a copy outside it: `cp -R . /tmp/attention-diet-eval && cd /tmp/attention-diet-eval`, then the same commands.
