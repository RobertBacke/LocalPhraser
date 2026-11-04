# Development and the user's working app

- Treat `dist/LocalPhraser` as the user's stable, working installation. Do not build into,
  replace, stop or remove it during development. Switch it only when the user is ready.
- Build development executables under `.cache/development-build`, and launch them only
  with an explicit separate `--config .cache/development-profile/config.json` (absolute path).
- Keep development settings, history, vocabulary, instance locks and model downloads separate
  from the user's profile. Default development shortcut: Ctrl+Shift+F11; automatic insertion,
  microphone keep-ready, live preview and startup are disabled in the initial dev profile.
- Use owned fixtures and synthetic data for tests. Do not capture the user's microphone or
  read their transcripts/messages. Avoid foreground-stealing native fixtures while the user
  is using the working app; background and offscreen checks can continue.
- Stage and verify an update completely before proposing a switch. Never use the stable
  installation as a test executable. Keep its existing launcher path on an approved switch.
