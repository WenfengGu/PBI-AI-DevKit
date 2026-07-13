"""
Claude Power BI MCP — Connection Test & Auto-Config
=====================================================
Tests all connections and auto-generates .mcp.json if needed.
"""
import sys, os, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from ssas_client import find_powerbi_bin, discover_pbi_instances, connect_to_instance, get_database_name
    from ssas_client import get_all_tables, get_all_measures

    # ── 1. Detect Power BI Desktop ──
    print("=" * 60)
    print("Claude Power BI MCP — Connection Test")
    print("=" * 60)

    print("\n[1] Detecting Power BI Desktop...")
    pbi_path = find_powerbi_bin()
    print(f"    Found: {pbi_path}")

    # ── 2. Discover instances ──
    print("\n[2] Discovering Power BI instances...")
    instances = discover_pbi_instances()
    if not instances:
        print("    [FAIL] No Power BI Desktop instances found.")
        print("    Please open a PBIX file in Power BI Desktop and try again.")
        sys.exit(1)

    for inst in instances:
        print(f"    Port: {inst['port']}, Title: {inst.get('title', 'Unknown')}, PID: {inst['pid']}")

    # ── 3. Connect ──
    print("\n[3] Connecting...")
    conn = None
    db = ""
    for inst in instances:
        try:
            conn = connect_to_instance(inst["port"])
            db = get_database_name(conn)
            if db:
                print(f"    Connected to port {inst['port']}! Database: {db}")
                break
            conn.Close()
            conn = None
        except Exception as e:
            print(f"    Port {inst['port']}: {e}")
            continue

    if not conn:
        print("    [FAIL] Could not connect to any instance with a valid database.")
        print("    Please open a PBIX file in Power BI Desktop and make sure it's fully loaded.")
        sys.exit(1)

    # ── 4. Model summary ──
    print("\n[4] Model Summary:")
    tables = get_all_tables(conn)
    measures = get_all_measures(conn)
    visible = [t for t in tables if t.get("IsHidden") != "True"]
    print(f"    Tables: {len(visible)} visible ({len(tables)} total)")
    print(f"    Measures: {len(measures)}")
    conn.Close()

    # ── 5. Auto-generate .mcp.json ──
    print("\n[5] Configuring Claude Code...")
    install_dir = os.path.dirname(os.path.abspath(__file__))
    mcp_path = os.path.join(install_dir, ".mcp.json")

    if os.path.exists(mcp_path):
        print(f"    .mcp.json already exists: {mcp_path}")
        print("    Skipping auto-generation.")
    else:
        mcp_config = {
            "mcpServers": {
                "claude-powerbi": {
                    "command": "python",
                    "args": [install_dir + "\\server.py"],
                    "env": {
                        "PATH": f"{str(pbi_path)};${{PATH}}"
                    }
                }
            }
        }
        with open(mcp_path, "w", encoding="utf-8") as f:
            json.dump(mcp_config, f, indent=2)
        print(f"    Generated: {mcp_path}")
        print(f"    PBI bin:   {pbi_path}")

    # ── 6. Check Skill ──
    print("\n[6] Checking Claude Code Skill...")
    skill_dst = os.path.join(os.environ["USERPROFILE"], ".claude", "skills", "powerbi-model.md")
    skill_src = os.path.join(install_dir, ".claude", "skills", "powerbi-model.md")
    if os.path.exists(skill_dst):
        print(f"    Skill installed: {skill_dst}")
    elif os.path.exists(skill_src):
        os.makedirs(os.path.dirname(skill_dst), exist_ok=True)
        with open(skill_src, "r", encoding="utf-8") as src:
            with open(skill_dst, "w", encoding="utf-8") as dst:
                dst.write(src.read())
        print(f"    Skill installed: {skill_dst}")
    else:
        print("    Skill file not found. Run setup.bat first.")

    # ── Done ──
    print("\n" + "=" * 60)
    print("ALL CHECKS PASSED!")
    print("=" * 60)
    print("""
  Your Power BI MCP Server is ready.

  Next steps:
    1. Copy .mcp.json to your Claude Code project root
    2. Restart Claude Code
    3. Open a PBIX file and ask Claude: "Show me this Power BI model"
""")

except Exception as e:
    print(f"\n[FAIL] {e}")
    sys.exit(1)