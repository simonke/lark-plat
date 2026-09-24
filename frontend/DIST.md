# frontend/dist — build-artifact policy

`frontend/dist` is a generated Vite bundle and is **not committed**
(`.gitignore:24` -> `dist/`). This note records how to rebuild it and its
fingerprint at hand-off, so the artifact can be reproduced/verified without
being stored in git.

## Rebuild

```sh
cd frontend
npm ci
npm run build
```

`vite.config.ts` emits to `dist/` (default). Node 24 / npm 11.

## Consumer

`deploy/docker-compose.yml` mounts `../frontend/dist` for read-only serving.
No Docker is available in this environment, so that mount is inert here; the
artifact is produced locally by the steps above.

## Fingerprint (informational — NOT a gate)

The bundle is **toolchain-sensitive**: a rebuild under a different
Node/npm/toolchain (e.g. npm 11 with `allow-scripts` blocking the
`esbuild`/`vue-demi` postinstall) yields **different bytes**. Observed at
hand-off: `files` = 55 in every run, but total bytes `2,173,062` (this
build) vs `2,173,050` (independent rebuild), and the manifest digest differed
run-to-run. **Treat the numbers below as informational only; do NOT gate CI or
acceptance on them.**

- recorded: 2026-09-24, source HEAD `cfce18f` (this machine's on-disk artifact)
- files: `55`
- bytes: `2,173,062`
- `manifest_sha256`: `dd2b4ad3acdc3d360468050e3b909055b0ebdc472dc0dfc362e51aa72d4fae2f`

For a **reproducible** fingerprint instead, pin Node/npm, allow install scripts,
rebuild in a controlled environment, and record that digest.

`manifest_sha256` = sha256 over the LF-joined, path-sorted lines
`<sha256(file)>  <relpath>` (relpath uses `/`, relative to `dist/`).

## Verify fingerprint (informational)

```powershell
$root = (Resolve-Path frontend/dist).Path
$files = Get-ChildItem -Recurse -File frontend/dist |
  Sort-Object { $_.FullName.Substring($root.Length+1).Replace('\','/') }
$lines = foreach ($f in $files) {
  $rel = $f.FullName.Substring($root.Length+1).Replace('\','/')
  "$((Get-FileHash -Algorithm SHA256 $f.FullName).Hash.ToLower())  $rel"
}
$h = [System.Security.Cryptography.SHA256]::Create()
(($h.ComputeHash([Text.Encoding]::UTF8.GetBytes(($lines -join "`n"))) |
  ForEach-Object { $_.ToString('x2') }) -join '')
```
