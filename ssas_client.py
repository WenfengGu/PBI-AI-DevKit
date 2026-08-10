"""
Claude Power BI MCP — SSAS Client
==================================
Connects to local Power BI Desktop SSAS instances or remote Power BI XMLA endpoints.
Auto-detects Power BI Desktop installation path.
Supports Azure AD token-based auth for remote connections.
"""

import os
import sys
import subprocess
import re
import json
import time
from pathlib import Path


# ──────────────────────────────────────────────────────────────
#  Azure AD Token Cache (for remote XMLA connections)
# ──────────────────────────────────────────────────────────────

TOKEN_CACHE_FILE = Path(__file__).parent / ".pbi_token_cache.json"

# Power BI China Azure AD endpoints
AAD_AUTHORITY_CN = "https://login.partner.microsoftonline.cn/organizations"
PBI_SCOPE_CN = "https://analysis.chinacloudapi.cn/powerbi/api/.default"

# Power BI Global Azure AD endpoints
AAD_AUTHORITY_GLOBAL = "https://login.microsoftonline.com/organizations"
PBI_SCOPE_GLOBAL = "https://analysis.windows.net/powerbi/api/.default"


def _get_cached_token() -> dict | None:
    """Load cached token from disk."""
    if TOKEN_CACHE_FILE.exists():
        try:
            with open(TOKEN_CACHE_FILE, 'r') as f:
                data = json.load(f)
            # Check expiry with 5 min buffer
            if data.get('expires_on', 0) > time.time() + 300:
                return data
        except Exception:
            pass
    return None


def _save_token_cache(data: dict):
    """Save token to disk cache."""
    try:
        with open(TOKEN_CACHE_FILE, 'w') as f:
            json.dump(data, f)
    except Exception:
        pass


def acquire_token(server_url: str, force_refresh: bool = False,
                  username: str = None, password: str = None) -> str:
    """Acquire an Azure AD access token for Power BI XMLA.

    Uses username/password authentication. Falls back to device code
    flow if no credentials are set. Token is cached to disk for reuse.

    Args:
        server_url: XMLA endpoint URL. Used to determine China vs Global cloud.
        force_refresh: If True, skip cache and get a new token.
        username: Azure AD username (email). Falls back to PBI_USERNAME env var.
        password: Azure AD password. Falls back to PBI_PASSWORD env var.
    """
    # Check cache first
    if not force_refresh:
        cached = _get_cached_token()
        if cached:
            return cached['access_token']

    # Resolve credentials
    username = username or os.environ.get("PBI_USERNAME", "")
    password = password or os.environ.get("PBI_PASSWORD", "")

    # Determine cloud based on server URL
    if 'api.powerbi.cn' in server_url or 'chinacloudapi.cn' in server_url:
        authority = AAD_AUTHORITY_CN
        scope = PBI_SCOPE_CN
    else:
        authority = AAD_AUTHORITY_GLOBAL
        scope = PBI_SCOPE_GLOBAL

    try:
        import msal
    except ImportError:
        raise RuntimeError(
            "msal package required for remote connections. Install: pip install msal"
        )

    app = msal.PublicClientApplication(
        "1950a258-227b-4e31-a9cf-717495945fc2",
        authority=authority,
    )

    # ── Method 1: Username/password ──
    if username and password:
        result = app.acquire_token_by_username_password(
            username=username,
            password=password,
            scopes=[scope],
        )
        if "access_token" in result:
            _save_token(result, scope)
            return result['access_token']
        raise RuntimeError(
            f"Authentication failed: "
            f"{result.get('error_description', result.get('error', 'Unknown'))}"
        )

    # ── Method 2: Device code fallback ──
    flow = app.initiate_device_flow(scopes=[scope])
    print(f"\nToken expired. Please authenticate:")
    print(f"  1. Open: {flow['verification_uri']}")
    print(f"  2. Enter code: {flow['user_code']}")
    print(f"  Waiting for authentication...", file=sys.stderr)
    sys.stderr.flush()

    result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        error = result.get("error_description", result.get("error", "Unknown"))
        raise RuntimeError(f"Device code authentication failed: {error}")

    _save_token(result, scope)
    return result['access_token']


def _save_token(result: dict, scope: str):
    """Save token result to disk cache."""
    data = {
        'access_token': result['access_token'],
        'expires_on': result.get('expires_on', time.time() + 3600),
        'scope': scope,
    }
    _save_token_cache(data)


# ──────────────────────────────────────────────────────────────
#  PBIX Path & Live Connection Detection
# ──────────────────────────────────────────────────────────────

def _extract_pbix_path() -> str | None:
    """Extract the PBIX file path from the running PBIDesktop.exe process."""
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name='PBIDesktop.exe'", "get", "CommandLine"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if ".pbix" in line.lower():
                # Command line looks like: "C:\...\PBIDesktop.exe" "D:\path\file.pbix"
                match = re.search(r'"([^"]+\.pbix)"', line, re.IGNORECASE)
                if match:
                    return match.group(1)
    except Exception:
        pass
    return None


def _parse_connection_string(conn_str: str) -> dict:
    """Parse a Power BI connection string to extract server and database."""
    result = {"remote_server": "", "remote_database": ""}
    # Parse "Data Source=...;Initial Catalog=...;..."
    ds_match = re.search(r'Data Source\s*=\s*([^;]+)', conn_str, re.IGNORECASE)
    if ds_match:
        result["remote_server"] = ds_match.group(1).strip()
    ic_match = re.search(r'Initial Catalog\s*=\s*([^;]+)', conn_str, re.IGNORECASE)
    if ic_match:
        result["remote_database"] = ic_match.group(1).strip()
    return result


def _read_pbix_connections(pbix_path: str) -> dict:
    """Read the Connections file from a PBIX to detect live connection info.

    Returns a dict with 'remote_server' and 'remote_database', or empty dict
    if no live connection info is found.
    """
    try:
        import zipfile
        with zipfile.ZipFile(pbix_path, 'r') as zf:
            if 'Connections' not in zf.namelist():
                return {}
            conn_data = json.loads(zf.read('Connections'))
            connections = conn_data.get("Connections", [])
            if not connections:
                return {}
            # Look for the first connection with a powerbi:// or Data Source
            for conn in connections:
                conn_str = conn.get("ConnectionString", "")
                if not conn_str:
                    # Some live connections use "RemoteArtifact" field
                    remote = conn.get("RemoteArtifact", {})
                    if remote:
                        ws = remote.get("GroupId", "")
                        ds = remote.get("DatasetId", "")
                        if ws and ds:
                            return {"remote_server": f"powerbi://api.powerbi.com/v1.0/myorg/{ws}",
                                    "remote_database": ds}
                # Try to parse connection string
                parsed = _parse_connection_string(conn_str)
                if parsed["remote_server"]:
                    return parsed
    except Exception:
        pass
    return {}


# ──────────────────────────────────────────────────────────────
#  Auto-detect Power BI Desktop installation
# ──────────────────────────────────────────────────────────────

def find_powerbi_bin() -> Path:
    """Auto-detect Power BI Desktop bin directory."""
    # Method 1: Check running PBIDesktop process
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name='PBIDesktop.exe'", "get", "ExecutablePath"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.lower().endswith("pbidesktop.exe"):
                p = Path(line).parent
                if p.exists():
                    return p
    except Exception:
        pass

    # Method 2: Check common install paths
    common_paths = [
        Path(r"D:\Program Files\Microsoft Power BI Desktop\bin"),
        Path(r"C:\Program Files\Microsoft Power BI Desktop\bin"),
        Path(r"C:\Program Files (x86)\Microsoft Power BI Desktop\bin"),
    ]
    for p in common_paths:
        adomd = p / "Microsoft.PowerBI.AdomdClient.dll"
        if adomd.exists():
            return p

    # Method 3: Search Program Files
    try:
        for base in [r"C:\Program Files", r"C:\Program Files (x86)", r"D:\Program Files"]:
            base_path = Path(base)
            if base_path.exists():
                for d in base_path.rglob("Microsoft Power BI Desktop"):
                    if d.is_dir():
                        bin_dir = d / "bin"
                        adomd = bin_dir / "Microsoft.PowerBI.AdomdClient.dll"
                        if adomd.exists():
                            return bin_dir
    except Exception:
        pass

    raise RuntimeError(
        "Power BI Desktop not found. Please install Power BI Desktop first.\n"
        "Download: https://www.microsoft.com/en-us/power-platform/products/power-bi/desktop"
    )


PBI_BIN = find_powerbi_bin()
ADOMD_DLL = PBI_BIN / "Microsoft.PowerBI.AdomdClient.dll"

# Ensure Power BI bin is in PATH for DLL resolution
os.environ["PATH"] = str(PBI_BIN) + os.pathsep + os.environ.get("PATH", "")

# --- Load .NET assemblies ---
import clr
clr.AddReference(str(ADOMD_DLL))

from Microsoft.AnalysisServices.AdomdClient import (
    AdomdConnection,
    AdomdCommand,
    AccessToken,
)


# ──────────────────────────────────────────────────────────────
#  Discovery
# ──────────────────────────────────────────────────────────────

def discover_pbi_instances() -> list[dict]:
    """Find running Power BI Desktop SSAS instances.

    Returns a list of dicts, each with:
      - port: int          SSAS port number
      - pid: int           Process ID
      - title: str         PBIX window title (filename)
      - pbix_path: str     Full path to the .pbix file
      - remote_server: str Live connection server URL ("" if not a live connection)
      - remote_database: str Live connection database name ("" if not a live connection)
    """
    instances = []

    # Find msmdsrv processes
    result = subprocess.run(
        ["netstat", "-ano"],
        capture_output=True, text=True, timeout=10
    )

    # Find msmdsrv PIDs
    msmdsrv_pids = set()
    proc_result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq msmdsrv.exe", "/FO", "CSV"],
        capture_output=True, text=True, timeout=10
    )
    for line in proc_result.stdout.splitlines():
        if "msmdsrv" in line.lower():
            parts = line.replace('"', '').split(",")
            if len(parts) >= 2:
                try:
                    msmdsrv_pids.add(int(parts[1].strip()))
                except ValueError:
                    pass

    # Find ports for msmdsrv PIDs
    for line in result.stdout.splitlines():
        if "LISTENING" not in line:
            continue
        match = re.search(r'127\.0\.0\.1:(\d+)\s+.*\s+(\d+)$', line)
        if match:
            port = int(match.group(1))
            pid = int(match.group(2))
            if pid in msmdsrv_pids:
                instances.append({"port": port, "pid": pid, "title": "",
                                   "pbix_path": "", "remote_server": "", "remote_database": ""})

    # Get PBI window titles
    try:
        pbi_result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq PBIDesktop.exe", "/FO", "CSV", "/V"],
            capture_output=True, text=True, timeout=10
        )
        title_idx = 0
        for line in pbi_result.stdout.splitlines():
            parts = line.replace('"', '').split(",")
            if len(parts) >= 9:
                title = parts[8].strip()
                if title and title != "N/A":
                    if title_idx < len(instances):
                        instances[title_idx]["title"] = title
                        title_idx += 1
    except Exception:
        pass

    # Get PBIX path from PBIDesktop command line
    pbix_path = _extract_pbix_path()
    if pbix_path and instances:
        # Read live connection info from the PBIX
        conn_info = _read_pbix_connections(pbix_path)
        for inst in instances:
            inst["pbix_path"] = pbix_path
            if conn_info:
                inst["remote_server"] = conn_info.get("remote_server", "")
                inst["remote_database"] = conn_info.get("remote_database", "")

    return instances


def connect_to_instance(port: int) -> AdomdConnection:
    """Connect to a Power BI Desktop SSAS instance."""
    conn_str = f"Data Source=localhost:{port};Catalog="
    conn = AdomdConnection(conn_str)
    conn.Open()
    return conn


def connect_to_remote(server: str, database: str = "") -> AdomdConnection:
    """Connect to a remote Power BI XMLA endpoint (Premium / Fabric).

    Args:
        server: XMLA endpoint URL, e.g. 'powerbi://api.powerbi.cn/v1.0/myorg/MyWorkspace'
        database: Semantic model name, e.g. 'Sales Report'
    """
    token = acquire_token(server)

    # Get expiration from cache for AccessToken constructor
    cached = _get_cached_token()
    expires_on = cached.get('expires_on', time.time() + 3600) if cached else time.time() + 3600

    from System import DateTime, DateTimeOffset, TimeSpan

    # Convert Unix timestamp to DateTimeOffset
    dt = DateTime(1970, 1, 1).AddSeconds(expires_on)
    dto = DateTimeOffset(dt, TimeSpan.Zero)

    conn_str = (
        f"Data Source={server};"
        f"Initial Catalog={database};"
    )

    conn = AdomdConnection()
    conn.ConnectionString = conn_str
    conn.AccessToken = AccessToken(token, dto, None)
    conn.Open()
    return conn


# ──────────────────────────────────────────────────────────────
#  Remote REST API Client (Power BI Service)
# ──────────────────────────────────────────────────────────────

def _find_bim_file(database_name: str, search_roots: list = None) -> str:
    """Auto-discover the best matching BIM file for a database.

    Searches recursively in search_roots for .bim files, scores them
    by keyword match against the database name, and returns the best
    match (latest by modification time when scores are equal).

    Args:
        database_name: e.g. "SalesAndCrm - target_China_FG"
        search_roots: directories to search; defaults to
            [os.environ.get('PBI_BIM_SEARCH_PATH', r'D:\\LVMH_Max')]

    Returns:
        Path to best matching BIM file, or None if no match found.
    """
    if search_roots is None:
        default_root = os.environ.get("PBI_BIM_SEARCH_PATH", r"D:\LVMH_Max")
        search_roots = [default_root]

    # Extract keywords from database name (lowercase, alphanumeric)
    # "SalesAndCrm - target_China_FG" -> ["salesandcrm", "fendi", "china", "fg"]
    keywords = re.findall(r'[a-zA-Z0-9]+', database_name.lower())
    if not keywords:
        return None

    # Collect all .bim files with their match scores
    candidates = []
    for root in search_roots:
        if not os.path.exists(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for f in filenames:
                if not f.lower().endswith('.bim'):
                    continue
                full_path = os.path.join(dirpath, f)
                name_lower = f.lower().replace('.bim', '')
                # Count how many keywords match in the filename
                match_count = sum(1 for kw in keywords if kw in name_lower)
                if match_count > 0:
                    mtime = os.path.getmtime(full_path)
                    candidates.append((match_count, mtime, full_path))

    if not candidates:
        return None

    # Sort by match count (desc), then by modification time (desc)
    candidates.sort(key=lambda x: (-x[0], -x[1]))

    best = candidates[0]
    # Require at least 2 keyword matches for confidence
    if best[0] < 2:
        return None

    return best[2]


class RemotePowerBI:
    """Connect to Power BI Service via REST API for DAX queries.

    Uses the executeQueries REST API endpoint to run DAX against
    published datasets. Supports workspace/dataset discovery.
    """

    def __init__(self, server: str = "", database: str = ""):
        self.server = server  # powerbi:// URL
        self.database = database  # Dataset name
        self._token = None
        # Detect cloud from server URL (same logic as acquire_token)
        if 'api.powerbi.cn' in server or 'chinacloudapi.cn' in server:
            self._api_base = "https://api.powerbi.cn/v1.0/myorg"
        else:
            self._api_base = "https://api.powerbi.com/v1.0/myorg"
        self._ws_id = None
        self._ds_id = None
        self._resolved = False

    @property
    def token(self) -> str:
        if self._token is None:
            self._token = acquire_token(self.server or "powerbi://api.powerbi.cn/")
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _ensure_resolved(self):
        """Resolve workspace/dataset names to IDs."""
        if self._resolved:
            return
        if self.server and self.database:
            self._resolve_from_url()
        self._resolved = True

    def _resolve_from_url(self):
        """Find workspace and dataset IDs from the powerbi:// URL."""
        # Extract workspace name from URL
        import urllib.parse
        ws_name = ""
        if "myorg/" in self.server:
            ws_name = self.server.split("myorg/")[-1].strip("/")
            ws_name = urllib.parse.unquote(ws_name)

        # Find workspace
        groups = self.list_workspaces()
        for g in groups:
            if g["name"] == ws_name or g["id"] == ws_name:
                self._ws_id = g["id"]
                break

        if not self._ws_id:
            # Try fuzzy match
            for g in groups:
                if ws_name.lower() in g["name"].lower():
                    self._ws_id = g["id"]
                    break

        if self._ws_id:
            # Find dataset
            datasets = self.list_datasets(self._ws_id)
            for ds in datasets:
                if ds["name"] == self.database:
                    self._ds_id = ds["id"]
                    break

    def list_workspaces(self) -> list[dict]:
        """List all accessible Power BI workspaces."""
        import requests
        r = requests.get(f"{self._api_base}/groups", headers=self._headers())
        if r.status_code == 200:
            return r.json().get("value", [])
        raise RuntimeError(f"Failed to list workspaces: {r.status_code} {r.text[:200]}")

    def list_datasets(self, workspace_id: str = None) -> list[dict]:
        """List datasets in a workspace."""
        import requests
        ws_id = workspace_id or self._ws_id
        if not ws_id:
            raise RuntimeError("Workspace ID not resolved")
        r = requests.get(
            f"{self._api_base}/groups/{ws_id}/datasets",
            headers=self._headers(),
        )
        if r.status_code == 200:
            return r.json().get("value", [])
        raise RuntimeError(f"Failed to list datasets: {r.status_code} {r.text[:200]}")

    def execute_dax(self, query: str) -> list[dict]:
        """Execute a DAX query via REST API executeQueries endpoint."""
        import requests
        self._ensure_resolved()
        if not self._ds_id or not self._ws_id:
            raise RuntimeError(
                f"Dataset not resolved. Server: {self.server}, Database: {self.database}\n"
                f"Workspace ID: {self._ws_id}, Dataset ID: {self._ds_id}"
            )

        url = f"{self._api_base}/groups/{self._ws_id}/datasets/{self._ds_id}/executeQueries"
        body = {
            "queries": [{"query": query}],
            "serializerSettings": {"includeNulls": True},
        }
        r = requests.post(url, json=body, headers=self._headers(), timeout=60)
        if r.status_code != 200:
            # Try to extract a meaningful error message from the response
            try:
                err = r.json()
                detail = err.get("error", {}).get("details", [{}])
                if detail and isinstance(detail, list) and len(detail) > 0:
                    detail_msg = detail[0].get("detail", {}).get("message", "")
                    if detail_msg:
                        raise RuntimeError(f"DAX query failed: {detail_msg}")
                msg = err.get("error", {}).get("message", "")
                if msg:
                    raise RuntimeError(f"DAX query failed: {msg}")
            except RuntimeError:
                raise
            except (ValueError, KeyError, IndexError, TypeError):
                pass
            raise RuntimeError(f"DAX query failed: {r.status_code} {r.text[:300]}")

        result = r.json()
        tables = result.get("results", [{}])[0].get("tables", [])
        if not tables:
            return []

        rows = tables[0].get("rows", [])
        return rows

    def execute_dax_raw(self, query: str) -> list[dict]:
        """Execute DAX and return raw rows (dict per row)."""
        return self.execute_dax(query)

    @staticmethod
    def row_val(row: dict, key: str, default=None):
        """Get a value from a REST API ROW() result.

        The Power BI REST API wraps column names in brackets: [Key].
        This helper tries both bare key and [Key] formats.
        """
        if key in row:
            return row[key]
        bracketed = "[%s]" % key
        if bracketed in row:
            return row[bracketed]
        return default

    def execute_dax_scalar(self, query: str):
        """Execute a DAX query and return the first scalar value."""
        rows = self.execute_dax(query)
        if rows:
            return list(rows[0].values())[0]
        return None

    def get_info(self) -> dict:
        """Get connection info summary."""
        self._ensure_resolved()
        return {
            "server": self.server,
            "database": self.database,
            "workspace_id": self._ws_id,
            "dataset_id": self._ds_id,
            "mode": "REST API",
        }

    def close(self):
        """No-op for REST API (stateless)."""
        pass

    def Close(self):
        """Alias for close() — matching server.py convention."""
        self.close()


class RemotePowerBIWithSchema(RemotePowerBI):
    """Remote Power BI client with BIM schema awareness.

    Loads a BIM file to get the exact table/column/measure names,
    then uses the REST API to query the remote dataset.

    This solves the metadata discovery problem: BIM provides the schema,
    REST API provides the data.
    """

    def __init__(self, server: str = "", database: str = "", bim_path: str = ""):
        super().__init__(server, database)
        self._bim_path = bim_path
        self._bim_data = None
        self._tables = {}       # name -> {columns, measures, isHidden}
        self._table_list = []   # ordered list of table names
        self._column_index = {} # (table, column) -> info
        self._measure_index = {} # (table, measure) -> info
        self._loaded = False

    def load_schema(self, bim_path: str = ""):
        """Load schema from a BIM JSON file."""
        import json
        path = bim_path or self._bim_path
        if not path:
            raise RuntimeError("No BIM file path provided")
        with open(path, 'r', encoding='utf-8-sig') as f:
            self._bim_data = json.load(f)
        self._parse_schema()
        self._loaded = True

    def _parse_schema(self):
        """Parse BIM model into lookup structures."""
        model = self._bim_data.get('model', {})
        self._tables.clear()
        self._table_list.clear()
        self._column_index.clear()
        self._measure_index.clear()

        for t in model.get('tables', []):
            tname = t['name']
            self._table_list.append(tname)
            columns = {}
            for c in t.get('columns', []):
                cname = c['name']
                columns[cname] = {
                    'dataType': c.get('dataType', 'string'),
                    'isHidden': c.get('isHidden', False),
                    'sourceColumn': c.get('sourceColumn', cname),
                }
                self._column_index[(tname, cname)] = columns[cname]

            measures = {}
            for m in t.get('measures', []):
                mname = m['name']
                measures[mname] = {
                    'expression': self._expr_str(m.get('expression', '')),
                    'displayFolder': m.get('displayFolder', ''),
                    'formatString': m.get('formatString', ''),
                }
                self._measure_index[(tname, mname)] = measures[mname]

            self._tables[tname] = {
                'columns': columns,
                'measures': measures,
                'isHidden': t.get('isHidden', False),
            }

    def _expr_str(self, expr) -> str:
        """Convert BIM expression (string or list) to string."""
        if isinstance(expr, list):
            return '\n'.join(str(e) for e in expr)
        return str(expr or '')

    def get_schema_summary(self) -> dict:
        """Get schema summary."""
        if not self._loaded:
            self.load_schema()
        total_cols = sum(len(t['columns']) for t in self._tables.values())
        total_meas = sum(len(t['measures']) for t in self._tables.values())
        return {
            'tables': len(self._table_list),
            'visible_tables': len([n for n in self._table_list if not self._tables[n]['isHidden']]),
            'columns': total_cols,
            'measures': total_meas,
            'bim_path': self._bim_path,
        }

    def get_tables(self) -> list[dict]:
        """Get all tables from BIM schema."""
        if not self._loaded:
            self.load_schema()
        return [
            {'Name': n, 'IsHidden': str(self._tables[n]['isHidden'])}
            for n in self._table_list
        ]

    def get_columns(self, table_name: str) -> list[dict]:
        """Get columns for a table from BIM schema."""
        if not self._loaded:
            self.load_schema()
        t = self._tables.get(table_name)
        if not t:
            return []
        return [
            {'Name': c, 'DataType': i['dataType'], 'IsHidden': str(i['isHidden'])}
            for c, i in t['columns'].items()
        ]

    def get_measures(self, table_filter: str = None, name_filter: str = None) -> list[dict]:
        """Get all measures from BIM schema, with optional filters."""
        if not self._loaded:
            self.load_schema()
        results = []
        for tname, tinfo in self._tables.items():
            if table_filter and table_filter.lower() not in tname.lower():
                continue
            for mname, minfo in tinfo['measures'].items():
                if name_filter and name_filter.lower() not in mname.lower():
                    continue
                results.append({
                    'Name': mname,
                    'TableName': tname,
                    'Expression': minfo['expression'],
                    'DisplayFolder': minfo['displayFolder'],
                    'FormatString': minfo['formatString'],
                })
        return results

    def search_dax(self, pattern: str, case_sensitive: bool = False) -> list[dict]:
        """Search within all measure DAX expressions."""
        if not self._loaded:
            self.load_schema()
        matches = []
        for tname, tinfo in self._tables.items():
            for mname, minfo in tinfo['measures'].items():
                expr = minfo['expression']
                if case_sensitive:
                    found = pattern in expr
                else:
                    found = pattern.lower() in expr.lower()
                if found:
                    matches.append({
                        'Name': mname,
                        'TableName': tname,
                        'Expression': expr,
                        'DisplayFolder': minfo['displayFolder'],
                    })
        return matches

    def get_table_row_count(self, table_name: str) -> int:
        """Query remote server for row count of a table."""
        rows = self.execute_dax(f"EVALUATE ROW(\"Rows\", COUNTROWS('{table_name}'))")
        if rows:
            return rows[0].get("[Rows]", 0)
        return 0

    def get_column_values(self, table_name: str, column_name: str, top_n: int = 100) -> list:
        """Query remote server for distinct values of a column."""
        if top_n:
            rows = self.execute_dax(
                f"EVALUATE TOPN({top_n}, VALUES('{table_name}'[{column_name}]))"
            )
        else:
            rows = self.execute_dax(f"EVALUATE VALUES('{table_name}'[{column_name}])")
        return [list(r.values())[0] for r in rows]

    def get_relationships(self) -> list[dict]:
        """Get relationships from BIM schema."""
        if not self._loaded:
            self.load_schema()
        model = self._bim_data.get('model', {})
        return model.get('relationships', [])

    def get_model_info(self) -> dict:
        """Get combined model info from BIM schema + remote connection."""
        schema = self.get_schema_summary()
        info = self.get_info()
        info.update({
            'tables': schema['tables'],
            'visible_tables': schema['visible_tables'],
            'columns': schema['columns'],
            'measures': schema['measures'],
            'bim_path': schema['bim_path'],
        })
        return info


def list_databases(conn: AdomdConnection) -> list[str]:
    """List all databases on the connected server."""
    cmd = conn.CreateCommand()
    cmd.CommandText = "SELECT [CATALOG_NAME] FROM $SYSTEM.DBSCHEMA_CATALOGS"
    reader = cmd.ExecuteReader()
    dbs = []
    while reader.Read():
        val = reader[0]
        if val is not None:
            dbs.append(str(val))
    reader.Close()
    return dbs


def get_database_name(conn: AdomdConnection) -> str:
    """Get the database name from the connection.

    For local PBI instances, tries TOM first (more reliable for local models),
    then falls back to DMV. For live connection PBIX files, the DMV will
    return an empty string.
    """
    db_name = ""

    # Try DMV query first (fast, no TOM overhead)
    try:
        cmd = conn.CreateCommand()
        cmd.CommandText = "SELECT [CATALOG_NAME] FROM $SYSTEM.DBSCHEMA_CATALOGS"
        reader = cmd.ExecuteReader()
        if reader.Read():
            val = reader[0]
            db_name = str(val) if val is not None else ""
        reader.Close()
    except Exception:
        pass

    # If DMV returns empty and we have a local port, try TOM
    if not db_name:
        try:
            conn_str = conn.ConnectionString or ""
            port_match = re.search(r'localhost:(\d+)', conn_str)
            if port_match:
                port = int(port_match.group(1))
                db_name = _get_database_name_via_tom(port)
        except Exception:
            pass

    if not db_name:
        import sys
        print("WARNING: Empty database — this PBIX is likely a live connection. "
              "Use remote mode or set PBI_XMLA_SERVER.",
              file=sys.stderr)

    return db_name


def _get_database_name_via_tom(port: int) -> str:
    """Get the database name using TOM (more reliable for local models)."""
    import clr
    clr.AddReference(str(PBI_BIN / "Microsoft.AnalysisServices.Server.Tabular.dll"))
    clr.AddReference(str(PBI_BIN / "Microsoft.PowerBI.Tabular.dll"))
    from Microsoft.AnalysisServices.Tabular import Server

    server = Server()
    try:
        server.Connect(f"Data Source=localhost:{port};Catalog=")
        if server.Databases.Count > 0:
            return server.Databases[0].Name
    finally:
        server.Disconnect()
    return ""


# ──────────────────────────────────────────────────────────────
#  DMV Query Helpers
# ──────────────────────────────────────────────────────────────

def execute_dmv(conn: AdomdConnection, query: str) -> list[dict]:
    """Execute a DMV query and return results as list of dicts."""
    try:
        cmd = conn.CreateCommand()
        cmd.CommandText = query
        reader = cmd.ExecuteReader()
        results = []
        while reader.Read():
            row = {}
            for i in range(reader.FieldCount):
                name = reader.GetName(i)
                try:
                    val = reader[i]
                    row[name] = str(val) if val is not None else None
                except Exception:
                    row[name] = None
            results.append(row)
        reader.Close()
        return results
    except Exception as e:
        err_msg = str(e)
        if "CurrentCatalog" in err_msg or "XML/A" in err_msg:
            raise RuntimeError(
                "Cannot query local model: this is a live connection PBIX. "
                "The local SSAS instance has no database. "
                "Use remote mode or set PBI_XMLA_SERVER env var."
            ) from e
        raise


def execute_dax(conn: AdomdConnection, query: str) -> list[dict]:
    """Execute a DAX query and return results as list of dicts."""
    query = query.strip()
    cmd = conn.CreateCommand()
    if not query.upper().startswith("EVALUATE"):
        query = f"EVALUATE {query}"
    cmd.CommandText = query
    reader = cmd.ExecuteReader()
    results = []
    while reader.Read():
        row = {}
        for i in range(reader.FieldCount):
            name = reader.GetName(i)
            try:
                val = reader[i]
                row[name] = str(val) if val is not None else None
            except Exception:
                row[name] = None
        results.append(row)
    reader.Close()
    return results


# ──────────────────────────────────────────────────────────────
#  Table/Measure Helpers
# ──────────────────────────────────────────────────────────────

def get_all_tables(conn: AdomdConnection) -> list[dict]:
    return execute_dmv(
        conn,
        "SELECT [ID], [Name], [IsHidden], [Description] FROM $SYSTEM.TMSCHEMA_TABLES"
    )


def get_all_measures(conn: AdomdConnection) -> list[dict]:
    return execute_dmv(
        conn,
        "SELECT [ID], [TableID], [Name], [Expression], [Description], "
        "[IsHidden], [FormatString], [DisplayFolder], [ErrorMessage] "
        "FROM $SYSTEM.TMSCHEMA_MEASURES"
    )


def get_all_columns(conn: AdomdConnection) -> list[dict]:
    return execute_dmv(
        conn,
        "SELECT [Name], [TableID], [DataType], [IsHidden], [IsNullable], "
        "[SourceColumn], [SummarizeBy] "
        "FROM $SYSTEM.TMSCHEMA_COLUMNS"
    )


# ──────────────────────────────────────────────────────────────
#  Model Modification (TOM)
# ──────────────────────────────────────────────────────────────

def replace_in_measure(port: int, table_name: str, measure_name: str,
                       old_text: str, new_text: str) -> bool:
    """Replace text in a measure's DAX expression using TOM."""
    import clr
    clr.AddReference(str(PBI_BIN / "Microsoft.AnalysisServices.Server.Tabular.dll"))
    clr.AddReference(str(PBI_BIN / "Microsoft.PowerBI.Tabular.dll"))

    from Microsoft.AnalysisServices.Tabular import Server

    server = Server()
    try:
        server.Connect(f"Data Source=localhost:{port};Catalog=")
        db = server.Databases[0]
        model = db.Model

        for t in model.Tables:
            if t.Name == table_name:
                for m in t.Measures:
                    if m.Name == measure_name:
                        if old_text in m.Expression:
                            m.Expression = m.Expression.replace(old_text, new_text)
                            model.SaveChanges()
                            return True
                        return False
                break
        return False
    finally:
        server.Disconnect()