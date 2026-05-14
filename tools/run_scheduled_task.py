"""Dispatcher for the four mid-week Tulsa Gays scheduled tasks.

Invoked by .github/workflows/scheduled-tulsagays-tasks.yml as a fallback
when the scheduled-tasks MCP is not the chosen execution path. Each
task id maps to a handler in this file.

The handlers are intentionally thin stubs right now: the original
implementations live as SKILL.md files in the claude-ops repo, which
this checkout does not have access to. Fill each handler in by porting
the corresponding SKILL.md's logic to plain Python, or by adding a
call into the Anthropic API that runs the SKILL.md content as a system
prompt against a tool-using Claude agent.

Until ported, the workflow runs but each task no-ops with a clear
log line and a non-zero exit so the failed run is visible.
"""

import sys


def task_tuesday_community_prompt() -> int:
    print("STUB: tulsagays-tuesday-community-prompt is not yet ported from SKILL.md")
    return 78  # neutral failure


def task_tuesday_reply_scraper() -> int:
    print("STUB: tulsagays-tuesday-reply-scraper is not yet ported from SKILL.md")
    return 78


def task_wednesday_lastminute() -> int:
    print("STUB: tulsagays-wednesday-lastminute is not yet ported from SKILL.md")
    return 78


def task_thursday_spotlight() -> int:
    print("STUB: tulsagays-thursday-spotlight is not yet ported from SKILL.md")
    return 78


HANDLERS = {
    "tulsagays-tuesday-community-prompt": task_tuesday_community_prompt,
    "tulsagays-tuesday-reply-scraper":    task_tuesday_reply_scraper,
    "tulsagays-wednesday-lastminute":     task_wednesday_lastminute,
    "tulsagays-thursday-spotlight":       task_thursday_spotlight,
}


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python tools/run_scheduled_task.py <task-id>")
        return 2
    task_id = sys.argv[1]
    handler = HANDLERS.get(task_id)
    if handler is None:
        print(f"Unknown task id: {task_id}")
        return 2
    return handler()


if __name__ == "__main__":
    sys.exit(main())
