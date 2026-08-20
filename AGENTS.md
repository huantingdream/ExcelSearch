# Project Instructions

## Platform baseline

- This is a cross-platform project targeting Windows and macOS.
- Windows is the primary production and user platform.
- macOS is the primary development platform and must remain fully usable for local development, testing, and debugging.
- Unless a task explicitly says otherwise, every design and implementation decision must work on both Windows and macOS.
- When platform behavior differs, preserve one shared implementation where practical and isolate the smallest possible platform-specific adapter behind a common interface.
- Do not silently drop support for either platform. If a requested feature cannot be implemented equivalently, document the limitation and provide the closest safe fallback.

## Compatibility requirements

- Do not assume a Unix-only shell, filesystem layout, command, permission model, or process behavior.
- Do not assume Windows drive letters, backslashes, registry access, PowerShell, or COM are available on macOS.
- Use language/runtime path APIs instead of manually joining paths. Accept both `/` and `\\` in external input when relevant.
- Never hard-code absolute local paths, usernames, drive letters, line endings, path separators, or case-sensitive filesystem behavior.
- Treat filenames as potentially case-insensitive and avoid names that differ only by case.
- Avoid Windows reserved filenames and invalid filename characters.
- Handle spaces and non-ASCII characters in paths and filenames correctly.
- Use UTF-8 explicitly for text files and I/O unless a required external format specifies another encoding.
- Keep generated and committed text files on LF line endings; allow Windows tooling to handle checkout/runtime conversion where necessary.
- Use platform-neutral configuration and environment variables. Provide documented defaults instead of relying on machine-specific state.
- Prefer cross-platform dependencies. A platform-specific dependency requires a clear reason, isolation, and an alternative or graceful failure on the other platform.

## Commands and scripts

- Prefer cross-platform task runners or scripts implemented in the project's primary language.
- If native shell scripts are necessary, provide equivalent PowerShell (`.ps1`) and POSIX shell (`.sh`) entry points, or a shared cross-platform implementation invoked by both.
- Documentation must show Windows commands first, followed by macOS commands when they differ.
- Do not make `bash`, GNU-only utilities, Homebrew, WSL, or a specific terminal a prerequisite for Windows users.
- Do not make PowerShell-only behavior a prerequisite for macOS developers.

## UI and desktop integration

- Treat Windows conventions as the primary UX baseline while preserving native, usable behavior on macOS.
- Account for DPI/display scaling, font availability, keyboard shortcuts, window behavior, file dialogs, and permission differences on both platforms.
- Use platform-appropriate shortcuts where they differ (for example, Ctrl on Windows and Command on macOS).
- Any Excel or Office integration must state whether it uses portable file-level APIs or platform-specific application automation. Platform-specific automation must be optional and isolated.

## Testing and delivery

- Add automated tests for platform-neutral behavior and targeted tests for platform-specific adapters.
- CI should run on both `windows-latest` and `macos-latest` once executable code exists.
- A change is not complete if it is known to break either supported platform.
- When only one platform can be tested locally, run all available platform-neutral checks and clearly note which platform still requires CI or manual verification.
- Release and setup documentation must cover Windows first and macOS second.

## Decision priority

When requirements compete, use this order:

1. Correct and reliable behavior on Windows.
2. Functional parity and developer usability on macOS.
3. A shared, maintainable cross-platform codebase.
4. Native polish and platform-specific enhancements.

These are standing project requirements and do not need to be restated in future tasks.
