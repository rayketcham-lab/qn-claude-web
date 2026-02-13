# /release — Build and Prepare a Release

Build the installer, run tests, and prepare a release artifact.

## Usage
Invoke with: `/release [version]` (e.g., `/release 1.4.2`)

## Process

1. **Version Validation**: Confirm the version string follows semver (X.Y.Z). Check if it conflicts with existing git tags.

2. **Pre-flight Checks**:
   - Run all unit tests (`tests/test_security.py`)
   - Run integration tests (`tests/test_integration.py`)
   - Verify no uncommitted changes (warn if dirty)
   - Check git is on master branch

3. **Build Installer**:
   - Run `bash build-installer.sh` — regenerates `install.sh` with fresh SHA-256 hashes
   - Verify `install.sh --verify-only` passes

4. **Build Release**:
   - Run `bash build-release.sh` — generates self-extracting `.sh` installer
   - Verify the artifact exists at `qn-code-assistant-v<VERSION>.sh`

5. **Version Bump**: Update version strings in:
   - `app.py` (VERSION constant)
   - Any other locations that reference the version

6. **Summary**: Report all results and next steps.

## Output
```
# Release: v[VERSION]

**Status**: READY / BLOCKED

## Checks
- [ ] Unit tests: [result]
- [ ] Integration tests: [result]
- [ ] Git clean: [yes/no]
- [ ] Installer built: [hash]
- [ ] Release artifact: [filename, size]

## Next Steps
[Manual steps remaining — commit, tag, push, copy to webserver]
```
