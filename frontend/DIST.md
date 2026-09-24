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

## Fingerprint (hand-off)

- recorded: 2026-09-24, source HEAD `cfce18f`
- files: `55`
- bytes: `2,173,062`
- `manifest_sha256`: `dd2b4ad3acdc3d360468050e3b909055b0ebdc472dc0dfc362e51aa72d4fae2f`

`manifest_sha256` = sha256 over the LF-joined, path-sorted lines
`<sha256(file)>  <relpath>` (relpath uses `/`, relative to `dist/`).

## Verify fingerprint (PowerShell)

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
