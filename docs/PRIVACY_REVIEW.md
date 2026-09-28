# Privacy review before publication

Reviewed on 2026-09-28 before publication. Scope: all 47 staged public files, their working copies, Git objects, repository configuration and the documentation image. At review time no remote repository or commit history existed. The public repository URL was added after the owner authorized publication; its GitHub account name is intentional public attribution.

## Result

No actual credentials or owner-specific identifiers were found in the final public content. The private comparison included Telegram API credentials, the configured destination ID and label, selected local geography, owner identifiers, private cloud resource identifiers, phone numbers and usernames stored in the local Telegram session, and the session authentication key. Values were compared locally and were not printed or copied into this report.

This is a review of the current prepared content, not a guarantee about files added in the future.

## What was checked

| Surface | Result |
| --- | --- |
| `.env.example` | Credential values are blank. |
| `config.example.yaml` | Destination ID is a placeholder; local areas are fictional. The public official city channel is retained. |
| Source and scripts | Credential loading is runtime-only; no hard-coded real credential, phone, private destination or personal path was found. |
| Tests | IDs and credential strings are synthetic fixtures, including a repeating hexadecimal test hash. They do not match the owner's actual values. |
| README and other documents | Source examples are fictional; cloud names and project ID are placeholders. The repository URL identifies the owner's public GitHub account. No private email, private invite link or production resource identifier was found. |
| Telegram-style image | Visual review shows only demonstration content. PNG contains no text metadata, EXIF or trailing payload. Staged and working image bytes match. |
| Public file inventory | No environment file, authenticated session, collected journal, export, backup, credential file or model artifact is staged. No unexpected nonignored file is waiting to be added. |
| Git object database | Reviewed every existing blob as well as the final staged content. Removed unreachable obsolete pre-commit versions, then repeated the review: no private comparison values were found in any remaining object. No commit history was changed. |
| Git history and remotes | The prepublication review started with no commits, published history or remote URL. Public commit metadata uses the GitHub alias and noreply address. |
| Effective Git identity | The currently configured display name matches the alias in its GitHub noreply email. Reconfirm both before creating the first public commit; commit identity is visible on GitHub. |
| Docker | Build copies only requirements, source and scripts. Runtime credentials, configuration and `.local` are supplied outside the image; private artifact patterns are excluded from the build context. |

## Corrections made during review

- Renamed the public Windows scheduled task to `Kyiv District Alerts`. Its previous generic label overlapped with the private destination's label; this did not include a group ID or invitation link.
- Extended Git and Docker exclusion rules for alternative SQLite/database names and sidecars, rotated logs, local config variants, archives, exports, credential directories, service-account JSON and private-key files.
- Retained explicit Git exceptions for `.env.example` and `config.example.yaml` so setup templates remain public.

The actual production environment, session, journal and scheduled task were not edited or copied into the public project.

## Before pushing

Publish from this public source repository, not from the parent operational directory or a zip of the entire working folder. Virtual environments can contain local filesystem paths even though they contain no application credentials; `.venv` and Python caches are excluded from Git.

Review `git diff --cached` and `git ls-files` after any new changes. Confirm a suitable public author name and GitHub noreply email before committing. Git ignore rules prevent normal accidental additions but do not stop `git add --force` or copying secrets into a tracked source file. Repeat the content check after replacing deployment placeholders with the final public repository URL.
