# Releasing

Releases are published by GitHub Actions (`.github/workflows/release.yml`) when a tag `vX.Y.Z` is
pushed: the CI runs again, then `swfactory` goes to PyPI, `swfactory` to npm, and a
GitHub release is created with the notes of that version in `CHANGELOG.md`. No tokens are stored:
PyPI and npm trust this workflow through OIDC ("trusted publishing").

## Each release

1. Set the same version in `pyproject.toml` and `npm/package.json`, and add its section to
   `CHANGELOG.md` (`## [X.Y.Z] - YYYY-MM-DD` plus the link at the bottom). `uv lock` updates
   `uv.lock`. `tests/test_release.py` checks that they agree.
2. Commit on `main` and wait for the CI to pass.
3. Tag and push: `git tag -a vX.Y.Z -m "swfactory X.Y.Z" && git push origin vX.Y.Z`.
4. Watch the "Release" workflow. The npm job waits for PyPI, because the launcher runs the PyPI
   package of the same version.

Versions follow semantic versioning. The public interface is the `swfactory` commands and their
`--json` output, the files under `.factory/` (`schema_version`) and the skills' names and
triggers. A change to a skill or role template also bumps the `@N` in its `factory-template` mark.

## One-time setup

1. **GitHub**: in the repository settings, create the environments `pypi` and `npm` (optionally
   with required reviewers, so every publish waits for an approval).
2. **PyPI**: on <https://pypi.org/manage/account/publishing/>, add a *pending publisher*: project
   `swfactory`, owner `MarianodelRio`, repository `swfactory`, workflow `release.yml`,
   environment `pypi`. The first release creates the project.
3. **npm**: trusted publishing can only be configured for a package that already exists, so the
   first version is published by hand from a clean checkout of the release commit:
   ```bash
   npm login
   cp LICENSE npm/LICENSE && cd npm && npm publish --access public
   ```
   Then, on npmjs.com → `swfactory` → Settings → Trusted publishing, add GitHub Actions
   with owner `MarianodelRio`, repository `swfactory`, workflow `release.yml`, environment `npm`.
   Until that is done, the npm job of a release fails and can be re-run afterwards.
