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
  --version 0.2.0 \
  --windows /absolute/path/to/DraciZvesti-0.2.0-Windows-x64-Setup.exe \
  --linux /absolute/path/to/DraciZvesti-0.2.0-Linux-x86_64.AppImage \
  --output dist
```

The script requests one password interactively, encrypts and verifies both
packages, and updates `dist/release.json`. It refuses to create a release unless
both platforms are provided. Publish the resulting static directory. Encrypted
chunks are reassembled and decrypted in the visitor's browser.

Do not place raw installers or source archives in `dist`; only the generated
encrypted chunks should be hosted.
