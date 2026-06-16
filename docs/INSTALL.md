# Installation

The engine is **pure Python standard library** — no third-party packages are
required to run a debate. You only need Python 3.8+ and an OpenRouter API key.

## 1. Get an OpenRouter API key

Create a key at <https://openrouter.ai/keys>, then export it:

```bash
export OPENROUTER_API_KEY=sk-or-...
```

(Add it to your shell profile to persist it. Never commit it to git.)

## 2. Get the code

```bash
git clone https://github.com/YOUR_USERNAME/multi-model-debate.git
cd multi-model-debate
```

## 3a. Use it directly (no install)

```bash
python -m multimodel_debate "Your question here"
```

## 3b. Install as a package (gives you the `mmdebate` command)

```bash
pip install -e .          # from the repo root
# now:
mmdebate "Your question here"
```

This also makes `from multimodel_debate import run_debate` importable anywhere,
which the Hermes adapter and your own scripts rely on.

## 4. Install as a Claude skill

The Claude skill is self-contained — copy it into your skills directory:

```bash
# Claude Code (personal skills)
cp -r skills/claude/multi-model-debate ~/.claude/skills/

# then restart Claude Code so it picks up the new skill
```

After restarting, phrasing like *"have a panel of models debate X to consensus"*
will trigger it. See [MANUAL.md](MANUAL.md) for how it behaves.

For **Claude.ai**, zip the `skills/claude/multi-model-debate/` directory and upload
it as a custom skill (Settings → Capabilities → Skills), or package it with the
skill-creator tooling.

## 5. Wire it into Hermes / another harness

See [`../skills/hermes/SKILL.md`](../skills/hermes/SKILL.md) — you can use the
Agent Skills directory directly, register the function schema in
[`../skills/hermes/tool.json`](../skills/hermes/tool.json), or import the package.

## Verifying

```bash
# lists live OpenRouter models (confirms your key works) — no token cost
python -m multimodel_debate --list-models deepseek
```

If you get an `OPENROUTER_API_KEY is not set` error, revisit step 1.
