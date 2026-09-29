from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "roblox_runtime" / "src"

FILES = [
    ("ReplicatedStorage/Shared/Config", RUNTIME / "ReplicatedStorage" / "Shared" / "Config.lua"),
    ("ReplicatedStorage/Shared/NumberFormatter", RUNTIME / "ReplicatedStorage" / "Shared" / "NumberFormatter.lua"),
    ("ReplicatedStorage/Shared/Remotes", RUNTIME / "ReplicatedStorage" / "Shared" / "Remotes.lua"),
    ("ReplicatedStorage/Shared/AnalyticsRegistry", RUNTIME / "ReplicatedStorage" / "Shared" / "AnalyticsRegistry.lua"),
    ("ServerScriptService/Services/PlayerDataService", RUNTIME / "ServerScriptService" / "Services" / "PlayerDataService.lua"),
    ("ServerScriptService/Services/CombatService", RUNTIME / "ServerScriptService" / "Services" / "CombatService.lua"),
    ("ServerScriptService/Services/ShadowArmyService", RUNTIME / "ServerScriptService" / "Services" / "ShadowArmyService.lua"),
    ("ServerScriptService/Services/RemoteService", RUNTIME / "ServerScriptService" / "Services" / "RemoteService.lua"),
    ("ServerScriptService/RuntimeBootstrap", RUNTIME / "ServerScriptService" / "RuntimeBootstrap.server.lua"),
]

def generate_install_luau() -> str:
    lines = [
        "local ReplicatedStorage = game:GetService('ReplicatedStorage')",
        "local ServerScriptService = game:GetService('ServerScriptService')",
        "",
        "local function ensureFolder(parent, name)",
        "    local folder = parent:FindFirstChild(name)",
        "    if not folder then",
        "        folder = Instance.new('Folder')",
        "        folder.Name = name",
        "        folder.Parent = parent",
        "    end",
        "    return folder",
        "end",
        "",
        "local repShared = ensureFolder(ReplicatedStorage, 'Shared')",
        "local sssServices = ensureFolder(ServerScriptService, 'Services')",
        "",
    ]

    for rel_path, path in FILES:
        content = path.read_text(encoding="utf-8")
        is_script = rel_path.endswith("RuntimeBootstrap")
        class_name = "Script" if is_script else "ModuleScript"
        parent_var = "repShared" if "ReplicatedStorage/Shared" in rel_path else ("sssServices" if "ServerScriptService/Services" in rel_path else "ServerScriptService")
        mod_name = path.stem.replace(".server", "")
        escaped_source = json.dumps(content)

        lines.extend([
            f"do",
            f"    local existing = {parent_var}:FindFirstChild('{mod_name}')",
            f"    if existing then existing:Destroy() end",
            f"    local mod = Instance.new('{class_name}')",
            f"    mod.Name = '{mod_name}'",
            f"    mod.Source = {escaped_source}",
            f"    mod.Parent = {parent_var}",
            f"end",
        ])

    lines.append("return 'Installed all runtime modules successfully'")
    return "\n".join(lines)


if __name__ == "__main__":
    luau_code = generate_install_luau()
    (ROOT / "scratch_install_runtime.lua").write_text(luau_code, encoding="utf-8")
    print(f"Generated installation script: {len(luau_code)} characters")
