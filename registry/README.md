# Studio Bridge Registries

`bridge_allowlist.json` is the executable security boundary for manifest actions, instance classes, generated folders, terrain shapes, and forbidden model-authored payload keys.

`asset_registry.json` maps stable logical keys to reviewed materials, colors, prefabs, and audio. Generated artifacts and manifests reference these keys; they never provide arbitrary Roblox asset IDs. A registry entry must be reviewed outside the model pipeline before its status becomes `approved`.

Placeholder entries are allowed for local contract tests. They produce a dry-run warning and keep `releaseReady` false.
