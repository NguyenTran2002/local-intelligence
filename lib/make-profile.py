"""Create (or update) the Claude Code profile used by claude-local / claude-openrouter.

    py -3 lib\\make-profile.py local      --mode bypass|default [--exa]
    py -3 lib\\make-profile.py openrouter --mode bypass|default [--exa]

The profile is a separate Claude Code config folder (%USERPROFILE%\\.claude-local or
\\.claude-openrouter). Your normal `claude`, its login and ~/.claude are NOT touched.
An existing settings.json is backed up to settings.json.bak-<timestamp> before being rewritten.
--exa registers Exa's hosted web-search MCP server in that profile (search queries go to Exa).
Standard library only.
"""
import argparse, json, os, shutil, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REL = json.load(open(os.path.join(ROOT, "release.json"), encoding="utf-8"))
EXA_URL = "https://mcp.exa.ai/mcp?tools=web_search_exa"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=["local", "openrouter"])
    ap.add_argument("--mode", choices=["bypass", "default"], required=True)
    ap.add_argument("--exa", action="store_true")
    a = ap.parse_args()

    prof = os.path.join(os.path.expanduser("~"), ".claude-" + a.which)
    os.makedirs(prof, exist_ok=True)
    sp = os.path.join(prof, "settings.json")
    settings = {}
    if os.path.exists(sp):
        shutil.copy2(sp, sp + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
        try:
            settings = json.load(open(sp, encoding="utf-8"))
        except ValueError:
            settings = {}

    settings["autoUpdatesChannel"] = REL["tested"]["claude_code_channel"]
    # Claude Code's own WebSearch is server-side at Anthropic: against another endpoint it returns
    # nothing (and some models then loop on it). Exa replaces it when chosen.
    perms = settings.setdefault("permissions", {})
    deny = set(perms.get("deny", [])) | {"WebSearch"}
    perms["deny"] = sorted(deny)
    # WebFetch otherwise asks api.anthropic.com about every new hostname first.
    settings["skipWebFetchPreflight"] = True
    if a.mode == "bypass":
        perms["defaultMode"] = "bypassPermissions"
        settings["skipDangerousModePermissionPrompt"] = True
    else:
        perms["defaultMode"] = "default"
        settings.pop("skipDangerousModePermissionPrompt", None)
    json.dump(settings, open(sp, "w", encoding="utf-8"), indent=2)

    # Skip the first-run login/theme wizard: this profile never logs in to claude.ai.
    cj = os.path.join(prof, ".claude.json")
    state = {}
    if os.path.exists(cj):
        try:
            state = json.load(open(cj, encoding="utf-8"))
        except ValueError:
            state = {}
    state["hasCompletedOnboarding"] = True
    json.dump(state, open(cj, "w", encoding="utf-8"), indent=2)

    print("profile:", prof)
    print("settings:", json.dumps(settings))

    if a.exa:
        env = dict(os.environ, CLAUDE_CONFIG_DIR=prof)
        claude = shutil.which("claude") or shutil.which("claude.exe") or shutil.which("claude.cmd")
        if not claude:
            sys.exit("claude not found on PATH - cannot register Exa.")
        subprocess.run([claude, "mcp", "remove", "--scope", "user", "exa"], env=env, capture_output=True)
        r = subprocess.run([claude, "mcp", "add", "--transport", "http", "--scope", "user", "exa", EXA_URL],
                           env=env, capture_output=True, text=True)
        print("exa:", (r.stdout or r.stderr).strip())
        if r.returncode != 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
