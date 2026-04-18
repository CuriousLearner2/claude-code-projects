# Project: parse-real-estate-email

## Token Efficiency Rules (CRITICAL)
- **Terminal Output**: Never `cat` files. Use `grep`, `head -n 20`, or `tail -n 20` to inspect output.
- **Large Files**: If a file is >100 lines, use `read_file` with `offset` and `limit`.
- **Bash Results**: If a command produces massive output (e.g., npm install, tests), summarize the result instead of reading the full log.
- **Context Management**: Proactively suggest a `/compact` if the message history exceeds 50k tokens.

## Technical Stack
- **Runtime**: Node.js / TypeScript
- **MCP Tools**: Gmail and Google Calendar (for email parsing/scheduling)
- **Memory**: Reference `.claude/projects/.../memory/MEMORY.md` for persistent state.

## Coding Style
- Use functional programming patterns where possible.
- Always include JSDoc comments for new functions.
- Prefer `import` over `require`.
- **Documentation**: Use verbose Google-style docstrings for all Python functions, including Args, Returns, and a brief description of the BeautifulSoup logic used.
- **Complexity**: For complex BeautifulSoup selectors, add inline comments explaining the specific DOM path being targeted.


## Commands
- **Build**: `npm run build`
- **Test**: `npm test`
- **Lint**: `npm run lint`

## Python Environment & Tools
- **Virtual Env**: Always use the local `venv/` for running scripts. Prefix commands with `source venv/bin/activate` if needed.
- **Database**: `listings.db` is a SQLite file. Never `cat` it. Use `sqlite3 listings.db "SELECT ..."` for inspection.
- **Gmail/Google API**: Use `credentials.json` and `token.json` for auth. Do not modify these files unless explicitly asked.
- **Testing**: Run tests using `pytest` or directly via `python <filename>.py`.

## Efficiency Rules (Python Specific)
- **Large Lists**: If a script (like `gmail_search.py`) outputs a long list of items, only show the first 5 results to save tokens.
- **Dependency Management**: Check `requirements.txt` before suggesting new packages.
- **Logging**: If a script fails, read only the last 20 lines of the traceback.

