# Release Process

How to cut a release: version bump, build, tag and publish. Releases live at https://github.com/happyshohaku/mtg-stories/releases with `MTG to EPUB.exe` attached.

## Versioning

- `vMAJOR.MINOR.PATCH`. New features bump MINOR (`v1.2.0`); fixes bump PATCH (`v1.1.1`)
- **Tag releases, not commits.** One tag per release, pointing at the exact commit the exe was built from
- Once a release has been out long enough that someone may have downloaded it, leave its tag and exe alone. The next change becomes a new version. Moving a tag is only acceptable while a release is still being finished

## Steps

1. **Tests pass**
   ```bash
   python -m pytest
   ```

2. **Bump the version** in three places
   - `src/__init__.py` → `__version__`
   - `README.md` → version badge
   - `docs/gui.md` → window layout diagram

3. **Commit** the bump

4. **Build the exe**
   ```bash
   rm -rf build dist
   pyinstaller --noconfirm mtg_stories.spec
   ```
   Output: `dist/MTG to EPUB.exe` (about 31 MB). `build/` and `dist/` are git-ignored.

5. **Smoke-test the exe**
   - It launches and the title bar shows the new version
   - The window and the exe show the app icon
   - Generate one small set
   - Nothing is left behind: no `.mtg-stories-working-*` folder in the output directory, no `MTG-Stories` folder under `%LOCALAPPDATA%`

6. **Tag and push**
   ```bash
   git tag -a v1.2.0 -m "v1.2.0"
   git push origin main --tags
   ```

7. **Publish the release** with the exe attached
   ```bash
   gh release create v1.2.0 "dist/MTG to EPUB.exe" --title "v1.2.0" --notes-file notes.md
   ```

## Release notes format

Keep the same three sections as previous releases, with short bullets and no explanations:

```markdown
Download `MTG to EPUB.exe` below — no Python installation required.

### What it does
Converts Magic: The Gathering stories from the official Wizards of the Coast website into EPUB files for e-readers like Kindle.

### What's new in 1.2.0
- One line per user-visible change
- No internal details (retries, refactors, dedup rules)

### Features
- Retrieves stories from WotC website and mtg.wiki archive
- ...
```

## Updating a release that is still in progress

If a fix lands minutes after publishing and nobody has the download yet:

```bash
git tag -f -a v1.2.0 -m "v1.2.0"
git push -f origin v1.2.0
gh release upload v1.2.0 "dist/MTG to EPUB.exe" --clobber
```

Rebuild and smoke-test the exe first, so the tag, the source and the download all match.

## Changing the icon

Replace `assets/icon.ico` and rebuild. The spec embeds it in the exe and bundles it so the window can load it.
