#!/usr/bin/env python3
"""
Claude Usage Tracker v2.0
Suivi complet des usages Claude AI et Claude Platform (API)
- Lecture des fichiers JSONL locaux de Claude Code
- Historique persistant
- Métriques avancées et coûts estimés
"""

import os
import json
import glob
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path
from collections import defaultdict

import httpx

# Charger le fichier .env s'il existe
def load_dotenv():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())

load_dotenv()

# Configuration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_ADMIN_KEY = os.getenv("ANTHROPIC_ADMIN_KEY", "")
CLAUDE_DIR = Path.home() / ".claude"
HISTORY_FILE = Path(__file__).parent / "usage_history.json"

# Tarifs API (par million de tokens) - Janvier 2026
PRICING = {
    "claude-opus-4-5-20251101": {"input": 15.00, "output": 75.00, "cache_read": 1.50, "cache_write": 18.75},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write": 3.75},
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write": 3.75},
    "claude-3-5-haiku": {"input": 0.80, "output": 4.00, "cache_read": 0.08, "cache_write": 1.00},
    "claude-3-opus": {"input": 15.00, "output": 75.00, "cache_read": 1.50, "cache_write": 18.75},
    "default": {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write": 3.75}
}


class ClaudeCodeUsageTracker:
    """Tracker pour l'usage Claude Code via fichiers JSONL locaux"""

    def __init__(self):
        self.claude_dir = CLAUDE_DIR
        self.sessions = []
        self.total_stats = defaultdict(int)

    def find_jsonl_files(self) -> list:
        """Trouve tous les fichiers JSONL de sessions Claude Code"""
        pattern = str(self.claude_dir / "projects" / "**" / "*.jsonl")
        files = glob.glob(pattern, recursive=True)
        return sorted(files, key=os.path.getmtime, reverse=True)

    def parse_jsonl_file(self, filepath: str) -> dict:
        """Parse un fichier JSONL et extrait les statistiques"""
        stats = {
            "file": filepath,
            "project": self._extract_project_name(filepath),
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "messages_count": 0,
            "tool_calls": 0,
            "models_used": set(),
            "start_time": None,
            "end_time": None,
            "errors": 0
        }

        try:
            with open(filepath, 'r') as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        self._process_entry(entry, stats)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            stats["parse_error"] = str(e)

        stats["models_used"] = list(stats["models_used"])
        return stats

    def _extract_project_name(self, filepath: str) -> str:
        """Extrait le nom du projet depuis le chemin"""
        parts = filepath.split("/")
        for i, part in enumerate(parts):
            if part == "projects" and i + 1 < len(parts):
                project_path = parts[i + 1]
                # Convertir le format -Users-xxx-workspace-project en nom lisible
                if project_path.startswith("-"):
                    segments = project_path.split("-")
                    # Retourner le dernier segment significatif
                    return segments[-1] if segments else project_path
                return project_path
        return "unknown"

    def _process_entry(self, entry: dict, stats: dict):
        """Traite une entrée JSONL"""
        entry_type = entry.get("type", "")
        timestamp = entry.get("timestamp")

        if timestamp:
            try:
                ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                if stats["start_time"] is None or ts < stats["start_time"]:
                    stats["start_time"] = ts
                if stats["end_time"] is None or ts > stats["end_time"]:
                    stats["end_time"] = ts
            except:
                pass

        # Messages utilisateur
        if entry_type == "user":
            stats["messages_count"] += 1

        # Réponses assistant avec usage
        if entry_type == "assistant":
            message = entry.get("message", {})
            usage = message.get("usage", {})

            if usage:
                stats["input_tokens"] += usage.get("input_tokens", 0)
                stats["output_tokens"] += usage.get("output_tokens", 0)
                stats["cache_read_tokens"] += usage.get("cache_read_input_tokens", 0)
                stats["cache_write_tokens"] += usage.get("cache_creation_input_tokens", 0)

            model = message.get("model", "")
            if model:
                stats["models_used"].add(model)

            # Compter les tool calls
            content = message.get("content", [])
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_use":
                    stats["tool_calls"] += 1

        # Erreurs
        if "error" in entry_type.lower() or entry.get("error"):
            stats["errors"] += 1

    def get_all_sessions_stats(self, limit: int = None) -> list:
        """Récupère les stats de toutes les sessions"""
        files = self.find_jsonl_files()
        if limit:
            files = files[:limit]

        sessions = []
        for f in files:
            stats = self.parse_jsonl_file(f)
            if stats["messages_count"] > 0:  # Ignorer les sessions vides
                sessions.append(stats)

        return sessions

    def get_aggregated_stats(self, sessions: list = None) -> dict:
        """Agrège les statistiques de toutes les sessions"""
        if sessions is None:
            sessions = self.get_all_sessions_stats()

        agg = {
            "total_sessions": len(sessions),
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cache_read_tokens": 0,
            "total_cache_write_tokens": 0,
            "total_messages": 0,
            "total_tool_calls": 0,
            "total_errors": 0,
            "projects": set(),
            "models_used": set(),
            "oldest_session": None,
            "newest_session": None
        }

        for s in sessions:
            agg["total_input_tokens"] += s["input_tokens"]
            agg["total_output_tokens"] += s["output_tokens"]
            agg["total_cache_read_tokens"] += s["cache_read_tokens"]
            agg["total_cache_write_tokens"] += s["cache_write_tokens"]
            agg["total_messages"] += s["messages_count"]
            agg["total_tool_calls"] += s["tool_calls"]
            agg["total_errors"] += s["errors"]
            agg["projects"].add(s["project"])
            agg["models_used"].update(s["models_used"])

            if s["start_time"]:
                if agg["oldest_session"] is None or s["start_time"] < agg["oldest_session"]:
                    agg["oldest_session"] = s["start_time"]
            if s["end_time"]:
                if agg["newest_session"] is None or s["end_time"] > agg["newest_session"]:
                    agg["newest_session"] = s["end_time"]

        agg["projects"] = list(agg["projects"])
        agg["models_used"] = list(agg["models_used"])
        agg["total_tokens"] = agg["total_input_tokens"] + agg["total_output_tokens"]

        return agg

    def calculate_equivalent_cost(self, stats: dict, model: str = "default") -> dict:
        """Calcule le coût équivalent si c'était via l'API"""
        pricing = PRICING.get(model, PRICING["default"])

        input_cost = (stats.get("total_input_tokens", 0) / 1_000_000) * pricing["input"]
        output_cost = (stats.get("total_output_tokens", 0) / 1_000_000) * pricing["output"]
        cache_read_cost = (stats.get("total_cache_read_tokens", 0) / 1_000_000) * pricing["cache_read"]
        cache_write_cost = (stats.get("total_cache_write_tokens", 0) / 1_000_000) * pricing["cache_write"]

        return {
            "input_cost": input_cost,
            "output_cost": output_cost,
            "cache_read_cost": cache_read_cost,
            "cache_write_cost": cache_write_cost,
            "total_cost": input_cost + output_cost + cache_read_cost + cache_write_cost,
            "model_pricing": model
        }

    def get_daily_stats(self, sessions: list = None, days: int = 7) -> dict:
        """Statistiques par jour pour les N derniers jours"""
        if sessions is None:
            sessions = self.get_all_sessions_stats()

        cutoff = datetime.now().astimezone() - timedelta(days=days)
        daily = defaultdict(lambda: {"tokens": 0, "messages": 0, "sessions": 0})

        for s in sessions:
            if s["end_time"] and s["end_time"] > cutoff:
                day = s["end_time"].strftime("%Y-%m-%d")
                daily[day]["tokens"] += s["input_tokens"] + s["output_tokens"]
                daily[day]["messages"] += s["messages_count"]
                daily[day]["sessions"] += 1

        return dict(sorted(daily.items()))


class UsageHistory:
    """Gestion de l'historique persistant"""

    def __init__(self, filepath: Path = HISTORY_FILE):
        self.filepath = filepath
        self.data = self._load()

    def _load(self) -> dict:
        """Charge l'historique depuis le fichier"""
        if self.filepath.exists():
            try:
                with open(self.filepath) as f:
                    return json.load(f)
            except:
                pass
        return {"snapshots": [], "api_calls": []}

    def save(self):
        """Sauvegarde l'historique"""
        with open(self.filepath, 'w') as f:
            json.dump(self.data, f, indent=2, default=str)

    def add_snapshot(self, stats: dict):
        """Ajoute un snapshot des stats actuelles"""
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "stats": stats
        }
        self.data["snapshots"].append(snapshot)
        # Garder seulement les 100 derniers snapshots
        self.data["snapshots"] = self.data["snapshots"][-100:]
        self.save()

    def add_api_call(self, tokens_in: int, tokens_out: int, model: str, cost: float):
        """Enregistre un appel API"""
        call = {
            "timestamp": datetime.now().isoformat(),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "model": model,
            "cost": cost
        }
        self.data["api_calls"].append(call)
        self.data["api_calls"] = self.data["api_calls"][-1000:]
        self.save()

    def get_api_totals(self) -> dict:
        """Totaux des appels API"""
        totals = {"tokens_in": 0, "tokens_out": 0, "cost": 0, "calls": 0}
        for call in self.data["api_calls"]:
            totals["tokens_in"] += call.get("tokens_in", 0)
            totals["tokens_out"] += call.get("tokens_out", 0)
            totals["cost"] += call.get("cost", 0)
            totals["calls"] += 1
        return totals


class ClaudePlatformTracker:
    """Tracker pour l'API Claude Platform"""

    def __init__(self, api_key: str, history: UsageHistory):
        self.api_key = api_key
        self.history = history

    def test_api(self, prompt: str = "Réponds 'ok' en un mot.") -> dict:
        """Teste l'API et enregistre l'usage"""
        if not self.api_key:
            return {"error": "API key non configurée"}

        try:
            with httpx.Client() as client:
                response = client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 50,
                        "messages": [{"role": "user", "content": prompt}]
                    },
                    timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()
                    usage = data.get("usage", {})
                    model = data.get("model", "claude-sonnet-4-20250514")
                    tokens_in = usage.get("input_tokens", 0)
                    tokens_out = usage.get("output_tokens", 0)

                    # Calculer le coût
                    pricing = PRICING.get(model, PRICING["default"])
                    cost = (tokens_in / 1_000_000) * pricing["input"] + \
                           (tokens_out / 1_000_000) * pricing["output"]

                    # Enregistrer dans l'historique
                    self.history.add_api_call(tokens_in, tokens_out, model, cost)

                    return {
                        "status": "success",
                        "model": model,
                        "tokens_in": tokens_in,
                        "tokens_out": tokens_out,
                        "cost": cost
                    }
                else:
                    return {"error": f"HTTP {response.status_code}", "details": response.text}
        except Exception as e:
            return {"error": str(e)}


def format_number(n: int) -> str:
    """Formate un nombre avec séparateurs de milliers"""
    return f"{n:,}".replace(",", " ")


def format_cost(c: float) -> str:
    """Formate un coût en dollars"""
    return f"${c:.4f}" if c < 1 else f"${c:.2f}"


def print_separator(char: str = "─", length: int = 60):
    print(char * length)


def print_header(title: str):
    print()
    print_separator("═")
    print(f"  {title}")
    print_separator("═")


def main():
    print_header("CLAUDE USAGE TRACKER v2.0")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    history = UsageHistory()

    # ══════════════════════════════════════════════════════════════
    # SECTION 1: Claude Code (Usage local via JSONL)
    # ══════════════════════════════════════════════════════════════
    print_header("CLAUDE CODE - USAGE LOCAL")

    tracker = ClaudeCodeUsageTracker()
    sessions = tracker.get_all_sessions_stats()
    agg = tracker.get_aggregated_stats(sessions)

    if agg["total_sessions"] == 0:
        print("  Aucune session Claude Code trouvée.")
    else:
        print(f"\n  Sessions totales     : {agg['total_sessions']}")
        print(f"  Projets              : {len(agg['projects'])}")
        print(f"  Messages envoyés     : {format_number(agg['total_messages'])}")
        print(f"  Appels d'outils      : {format_number(agg['total_tool_calls'])}")

        print(f"\n  TOKENS:")
        print(f"    Input              : {format_number(agg['total_input_tokens'])}")
        print(f"    Output             : {format_number(agg['total_output_tokens'])}")
        print(f"    Cache lecture      : {format_number(agg['total_cache_read_tokens'])}")
        print(f"    Cache écriture     : {format_number(agg['total_cache_write_tokens'])}")
        print(f"    ─────────────────────────────────")
        total_all = agg['total_input_tokens'] + agg['total_output_tokens'] + \
                    agg['total_cache_read_tokens'] + agg['total_cache_write_tokens']
        print(f"    TOTAL              : {format_number(total_all)}")

        # Coût équivalent API
        cost = tracker.calculate_equivalent_cost(agg, "claude-sonnet-4-20250514")
        print(f"\n  COÛT ÉQUIVALENT API (Sonnet):")
        print(f"    Input              : {format_cost(cost['input_cost'])}")
        print(f"    Output             : {format_cost(cost['output_cost'])}")
        print(f"    Cache lecture      : {format_cost(cost['cache_read_cost'])}")
        print(f"    Cache écriture     : {format_cost(cost['cache_write_cost'])}")
        print(f"    ─────────────────────────────────")
        print(f"    TOTAL              : {format_cost(cost['total_cost'])}")

        # Modèles utilisés
        if agg["models_used"]:
            print(f"\n  Modèles utilisés:")
            for m in agg["models_used"]:
                print(f"    • {m}")

        # Stats par jour (7 derniers jours)
        daily = tracker.get_daily_stats(sessions, days=7)
        if daily:
            print(f"\n  USAGE 7 DERNIERS JOURS:")
            print(f"    {'Date':<12} {'Tokens':>12} {'Messages':>10} {'Sessions':>10}")
            print(f"    {'-'*12} {'-'*12} {'-'*10} {'-'*10}")
            for day, data in daily.items():
                print(f"    {day:<12} {format_number(data['tokens']):>12} {data['messages']:>10} {data['sessions']:>10}")

        # Top projets
        project_stats = defaultdict(lambda: {"tokens": 0, "messages": 0})
        for s in sessions:
            project_stats[s["project"]]["tokens"] += s["input_tokens"] + s["output_tokens"]
            project_stats[s["project"]]["messages"] += s["messages_count"]

        sorted_projects = sorted(project_stats.items(), key=lambda x: x[1]["tokens"], reverse=True)[:5]
        if sorted_projects:
            print(f"\n  TOP 5 PROJETS (par tokens):")
            for proj, data in sorted_projects:
                print(f"    • {proj:<20} {format_number(data['tokens']):>12} tokens")

        # Sauvegarder snapshot
        history.add_snapshot({
            "total_tokens": total_all,
            "total_messages": agg["total_messages"],
            "total_sessions": agg["total_sessions"]
        })

    # ══════════════════════════════════════════════════════════════
    # SECTION 2: API Platform
    # ══════════════════════════════════════════════════════════════
    print_header("CLAUDE API - PLATFORM")

    platform = ClaudePlatformTracker(ANTHROPIC_API_KEY, history)

    if not ANTHROPIC_API_KEY:
        print("  ⚠️  ANTHROPIC_API_KEY non configurée")
        print("\n  Pour configurer:")
        print("    1. Éditez le fichier .env")
        print("    2. Ajoutez: ANTHROPIC_API_KEY=sk-ant-...")
    else:
        print("  ✓ API Key configurée")

        # Test de l'API
        print("\n  Test de connexion...")
        result = platform.test_api()

        if "error" in result:
            print(f"  ✗ Erreur: {result['error']}")
        else:
            print(f"  ✓ Connexion réussie ({result['model']})")

        # Historique des appels API
        api_totals = history.get_api_totals()
        if api_totals["calls"] > 0:
            print(f"\n  HISTORIQUE API (cette installation):")
            print(f"    Appels totaux      : {api_totals['calls']}")
            print(f"    Tokens IN          : {format_number(api_totals['tokens_in'])}")
            print(f"    Tokens OUT         : {format_number(api_totals['tokens_out'])}")
            print(f"    Coût total         : {format_cost(api_totals['cost'])}")

    # ══════════════════════════════════════════════════════════════
    # SECTION 3: Plan Claude AI
    # ══════════════════════════════════════════════════════════════
    print_header("ABONNEMENT CLAUDE AI")

    plan = os.getenv("CLAUDE_PLAN", "max").lower()
    plans_info = {
        "free": ("Free", "$0/mois", "Limité"),
        "pro": ("Pro", "$20/mois", "5x plus que Free"),
        "max": ("Max $100", "$100/mois", "5x plus que Pro"),
        "max200": ("Max $200", "$200/mois", "20x plus que Pro, illimité")
    }

    info = plans_info.get(plan, plans_info["max"])
    print(f"\n  Plan actuel          : {info[0]}")
    print(f"  Prix                 : {info[1]}")
    print(f"  Limite messages      : {info[2]}")

    if agg["total_sessions"] > 0 and cost["total_cost"] > 0:
        plan_price = 100 if "max" in plan else (20 if plan == "pro" else 0)
        if plan_price > 0:
            savings = cost["total_cost"] - plan_price
            if savings > 0:
                print(f"\n  💰 ÉCONOMIES vs API   : {format_cost(savings)}")
                print(f"     (Coût API {format_cost(cost['total_cost'])} - Abo {format_cost(float(plan_price))})")

    print("\n  ℹ️  Pour voir l'usage exact du plan:")
    print("     → claude.ai → Paramètres → Usage")
    print("     → Ou utilisez /context dans Claude Code")

    # ══════════════════════════════════════════════════════════════
    # SECTION 4: Tarifs de référence
    # ══════════════════════════════════════════════════════════════
    print_header("TARIFS API - RÉFÉRENCE 2026")

    print("\n  Modèle                    Input/1M    Output/1M   Cache R/1M")
    print("  " + "-" * 56)
    for model, prices in PRICING.items():
        if model != "default":
            name = model.replace("claude-", "").replace("-20251101", "").replace("-20250514", "")
            print(f"  {name:<25} ${prices['input']:<9.2f} ${prices['output']:<10.2f} ${prices['cache_read']:.2f}")

    print()
    print_separator("═")
    print(f"\n  Historique sauvegardé: {HISTORY_FILE}")
    print()


if __name__ == "__main__":
    main()
