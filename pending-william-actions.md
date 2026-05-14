# Pending actions for William

This is the punch list from the half-done mid-week pipeline migration.
Items in this session were either blocked on tools not attached here
or require credentials/UI access that has to happen on William's
machine. Everything that could be done in code has been.

## Blockers from this session

- **scheduled-tasks MCP not connected.** `mcp__scheduled-tasks__list_scheduled_tasks`
  and friends are not in the tool list for this session, so the
  one-shot at `claude-ops/scheduled-tasks/register-new-tulsagays-tasks/SKILL.md`
  could not run. Re-run register-new-tulsagays-tasks from a session
  that has the scheduler MCP attached (likely a session started from
  the `claude-ops` repo, which presumably has the MCP wired up in its
  `.mcp.json` or web-app project settings).
- **GitHub MCP scope is restricted to DistrictOfRyan/tulsagays here.**
  claude-ops PR #23 cannot be marked ready or merged from this session.
  Do that from a session with claude-ops scope.

## Manual steps required on William's machine

1. **Rotate the leaked Tulsa Gays Page access token.** The token
   previously committed at `meta_api_config.json:30` is in git
   history. Generate a new permanent page token (see
   `meta_api_config.json` `how_to_get_page_token` for the exact curl)
   and put it in `.env` as `TULSAGAYS_PAGE_ACCESS_TOKEN=...`. The old
   token stays in git history but becomes worthless once rotated.
   `.env` is already gitignored.
2. **Provide HHHH Page credentials** to use the new `post-hhhh` CLI:
   set `HHHH_PAGE_ID` and `HHHH_PAGE_ACCESS_TOKEN` in `.env`.
3. **One-time Playwright login for HHHH group posting:**
   ```
   pip install playwright
   playwright install chromium
   python -m posting.group_post --setup
   ```
   Set `HHHH_GROUP_URL` in `.env` first.
4. **Disarm tulsagays-wednesday-social in the cloud scheduler tonight
   so it cannot fire again.** On 2026-05-13 9:38pm CT this task posted
   a text-only caption (post id 1086906044497675_122112310964853065).
   The on-disk SKILL.md is disabled but the cloud scheduler does not
   read SKILL.md files.
5. **If you choose the GHA fallback path** for the four mid-week
   tasks instead of waiting for the scheduled-tasks MCP, add these
   repo secrets to DistrictOfRyan/tulsagays: `ANTHROPIC_API_KEY`,
   `META_ACCESS_TOKEN`, `META_IG_USER_ID`, `TULSAGAYS_PAGE_ID`,
   `TULSAGAYS_PAGE_ACCESS_TOKEN`. The workflow
   `.github/workflows/scheduled-tulsagays-tasks.yml` will run all
   four crons. The handler stubs in `tools/run_scheduled_task.py`
   need real logic ported from the corresponding SKILL.md files
   before the runs do anything useful.

## What got done in this session

- Added HHHH Page posting via Graph API (`posting/facebook.py` +
  `post-hhhh` CLI subcommand in `main.py`).
- Added HHHH Group posting via Playwright browser automation
  (`posting/group_post.py`).
- Moved Tulsa Gays page access token out of `meta_api_config.json`
  to a `TULSAGAYS_PAGE_ACCESS_TOKEN` env var; updated
  `tools/post_weekly.py` to read it from env.
- Created `.env.example` documenting every required env var.
- Scaffolded `.github/workflows/scheduled-tulsagays-tasks.yml` as a
  fallback scheduler for the four mid-week tasks, with stub handlers
  in `tools/run_scheduled_task.py`.
