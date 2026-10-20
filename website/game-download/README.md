# Draci Zvesti protected downloads

This buildless static site serves AES-256-GCM encrypted Windows and Linux game
builds. The password is never stored in HTML, JavaScript, metadata, or hosting
settings. The visitor's browser derives the key and decrypts the selected game
package locally.

## Prepare a release

First build both playable packages. Build the `.exe` on Windows and the
AppImage on Linux as documented in `../../packager/README.md`. Copy both files
to this machine if they were built elsewhere.

From this directory, run:

```bash
node tools/prepare-release.mjs \
  --version 0.1.2 \
  --windows-installer /absolute/path/to/DraciZvesti-0.1.2-Windows-x64-Setup.exe \
  --windows-portable /absolute/path/to/DraciZvesti-0.1.2-Windows-x64-portable.zip \
  --linux /absolute/path/to/DraciZvesti-0.1.2-Linux-x86_64.AppImage \
  --output dist
```

The script requests one password interactively, encrypts and verifies every
selected package, and updates `dist/release.json`. Linux and at least one Windows format
are required; omit either `--windows-installer` or `--windows-portable` when you
only want to publish one of them. The legacy `--windows` option remains an alias
for `--windows-installer`. Publish the resulting static directory. Encrypted
chunks are reassembled and decrypted in the visitor's browser.

Do not place raw installers or source archives in `dist`; only the generated
encrypted chunks should be hosted.
