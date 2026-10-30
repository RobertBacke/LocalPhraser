# Design skill selection and review

The user requested popular GitHub design skills, preferably from repositories with more
than 50,000 stars. GitHub metadata checked on 2026-10-30 reported:

| Selected skill | Repository stars | Pinned commit |
| --- | ---: | --- |
| [frontend-design](https://github.com/anthropics/skills/tree/main/skills/frontend-design) | 185,023 | `ca45fc496a3436251f191354091d557da31c15b5` |
| [UI/UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 142,875 | `28b3b8dee8c976df4fa3e94aed4e092ad43fcb03` |

Popularity is a selection signal, not a safety guarantee. The selected skill directories
were downloaded into an ignored review directory at these immutable revisions before
installation. The first contained only its instruction document and license. The second
contained 73 UTF-8 text/Python files: guidance, CSV/JSON catalogs and Python helpers/tests.
No executable binaries, linked paths, npm dependencies or repository installers were needed.

The review inspected instructions, imports and dynamic/I/O call sites. The production
Python helpers used standard-library/local modules; no shell/process execution, executable
downloads or network-client calls were found in those helpers. URL parsing in validation
is not a network fetch. Optional design-system persistence writes explicitly requested files;
it was not used to modify the project. Installed files were compared against SHA-256 hashes
of the reviewed contents. Local search used generic design terms, never transcript data.

This was a scoped static source review, not a full repository security audit or antivirus
certification. No antivirus scan result is claimed. Future upstream versions would need
review again. The skills are development aids outside the application and are not bundled
with LocalPhraser or given access to transcript history.
