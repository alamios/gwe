# Release procedure

The project home is [alamios/gwe](https://github.com/alamios/gwe). Publish source and native `.deb`
assets through GitHub Releases. Development uses `main`; release versions use annotated tags.
Preparation does not authorize pushing or publishing.

## Prepare a candidate

1. Update the application version, AppStream metadata and [changelog](CHANGELOG.md) together. Keep source,
   support and changelog links pointing to this fork; retain original credits and AI-maintenance disclosure.
2. Review configuration/schema changes and the [backup/rollback procedure](docs/configuration-backup.md).
3. Run relevant simulated and isolated GTK checks. Perform affected installed acceptance with authorization;
   do not substitute evidence from an older runtime. Update [validation](docs/validation.md).
4. Build into a new directory using [reviewed inputs](docs/packaging.md) and a fixed source epoch.
5. Inspect package/source contents, dependencies, ownership, licenses, icon identity and compiled resources.
   Exclude private profiles, UUIDs, databases, screenshots, logs and local build inputs.
6. Record the exact source commit, package checksum, build runtime, validation and limitations in `BUILD_INFO`.
   Retain tested rollback bytes. Never overwrite published assets or move a published version tag.

Application versions use SemVer, for example `1.0.0-rc1`; Debian prerelease versions use `~`, for example
`1.0.0~rc1-9`. Choose a new package revision when changing distributed bytes. The latest prepared
candidate and its outstanding gates are in [validation](docs/validation.md).

## Tag and generate source assets

After review and acceptance, set the desired new tag name and create it on the reviewed commit:

```bash
GWE_RELEASE_TAG=v1.0.0-rc2
GWE_SOURCE_ARCHIVE=gwe-1.0.0-rc2-source.tar.gz
git tag -a "$GWE_RELEASE_TAG" -m 'GreenWithEnvy 1.0.0-rc2'
git archive --format=tar.gz --prefix=gwe-1.0.0-rc2/ "$GWE_RELEASE_TAG" > "$GWE_SOURCE_ARCHIVE"
```

These are examples for a new release, not instructions to retag an existing candidate. Tag the intended
reviewed commit explicitly if it is not HEAD. Do not create a stable tag while required acceptance is pending.

Retain four publication assets together: the tested `.deb`, tagged source archive, `BUILD_INFO` and
`SHA256SUMS`. Generate checksums after all asset contents are final, then verify them:

```bash
sha256sum -- *.deb *-source.tar.gz BUILD_INFO > SHA256SUMS
sha256sum --check SHA256SUMS
```

Run this in a dedicated release-asset directory containing only the intended package/source assets.
GitHub's automatically generated source ZIP/tar downloads are source archives, not installers.

## Publish with owner authorization

Push the intended branch and specific new version tag to the fork. Avoid pushing all tags indiscriminately.
In GitHub, open **Releases → Draft a new release**, select that tag, add reviewed notes and attach the
four assets. Mark candidates as prereleases. Save and inspect the draft before publication.

Release notes should describe resulting behavior, supported/validated scope, known limitations and
installation. Users verify checksums, Quit GWE, finish recovery and install through APT. No development
venv or repository installation wrapper is required.
