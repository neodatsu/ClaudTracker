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
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.text import Text
from rich import box
from rich.columns import Columns

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

# Tarifs API (par million de tokens) - Février 2026
# Cache: read = 0.1x input, write 5min = 1.25x input, write 1h = 2x input
PRICING = {
    "claude-opus-4-5-20251101": {"input": 5.00, "output": 25.00, "cache_read": 0.50, "cache_write": 6.25},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write": 3.75},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00, "cache_read": 0.10, "cache_write": 1.25},
    "claude-opus-4-1": {"input": 15.00, "output": 75.00, "cache_read": 1.50, "cache_write": 18.75},
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

    def test_api(self, prompt: str = "Reply 'ok' in one word.") -> dict:
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


console = Console()


def format_number(n: int) -> str:
    """Formate un nombre avec séparateurs de milliers"""
    return f"{n:,}".replace(",", " ")


def format_cost(c: float) -> str:
    """Formate un coût en dollars"""
    return f"${c:.4f}" if c < 1 else f"${c:.2f}"


def create_kpi_panel(title: str, value: str, subtitle: str = "", color: str = "cyan") -> Panel:
    """Crée un panel KPI stylisé"""
    content = Text()
    content.append(f"{value}\n", style=f"bold {color}")
    if subtitle:
        content.append(subtitle, style="dim")
    return Panel(content, title=f"[bold]{title}[/bold]", border_style=color, padding=(0, 1))


def main():
    console.clear()

    # Header
    header = Text()
    header.append("  CLAUDE USAGE TRACKER  ", style="bold white on blue")
    header.append(f"  v2.0  ", style="bold black on cyan")
    console.print(Panel(header, subtitle=datetime.now().strftime("%Y-%m-%d %H:%M"), box=box.DOUBLE))
    console.print()

    history = UsageHistory()
    tracker = ClaudeCodeUsageTracker()
    sessions = tracker.get_all_sessions_stats()
    agg = tracker.get_aggregated_stats(sessions)

    if agg["total_sessions"] == 0:
        console.print(Panel("[yellow]Aucune session Claude Code trouvée.[/yellow]", title="Claude Code"))
    else:
        total_all = agg['total_input_tokens'] + agg['total_output_tokens'] + \
                    agg['total_cache_read_tokens'] + agg['total_cache_write_tokens']
        cost = tracker.calculate_equivalent_cost(agg, "claude-sonnet-4-20250514")

        # KPI Row 1 - Tuiles principales
        kpis_row1 = [
            create_kpi_panel("Sessions", str(agg['total_sessions']), f"{len(agg['projects'])} projets", "cyan"),
            create_kpi_panel("Messages", format_number(agg['total_messages']), "envoyés", "green"),
            create_kpi_panel("Tool Calls", format_number(agg['total_tool_calls']), "appels d'outils", "yellow"),
            create_kpi_panel("Coût API", format_cost(cost['total_cost']), "équivalent Sonnet", "magenta"),
        ]
        console.print(Columns(kpis_row1, equal=True, expand=True))
        console.print()

        # Tokens Panel
        tokens_table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
        tokens_table.add_column("Type", style="bold")
        tokens_table.add_column("Tokens", justify="right", style="green")
        tokens_table.add_column("Coût API", justify="right", style="yellow")

        tokens_table.add_row("Input", format_number(agg['total_input_tokens']), format_cost(cost['input_cost']))
        tokens_table.add_row("Output", format_number(agg['total_output_tokens']), format_cost(cost['output_cost']))
        tokens_table.add_row("Cache Read", format_number(agg['total_cache_read_tokens']), format_cost(cost['cache_read_cost']))
        tokens_table.add_row("Cache Write", format_number(agg['total_cache_write_tokens']), format_cost(cost['cache_write_cost']))
        tokens_table.add_row("[bold]TOTAL[/bold]", f"[bold]{format_number(total_all)}[/bold]", f"[bold]{format_cost(cost['total_cost'])}[/bold]")

        # Top Projets Panel
        project_stats = defaultdict(lambda: {"tokens": 0, "messages": 0})
        for s in sessions:
            project_stats[s["project"]]["tokens"] += s["input_tokens"] + s["output_tokens"]
            project_stats[s["project"]]["messages"] += s["messages_count"]
        sorted_projects = sorted(project_stats.items(), key=lambda x: x[1]["tokens"], reverse=True)[:5]

        projects_table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
        projects_table.add_column("Projet", style="bold")
        projects_table.add_column("Tokens", justify="right", style="cyan")
        projects_table.add_column("Messages", justify="right", style="green")

        for proj, data in sorted_projects:
            projects_table.add_row(proj[:20], format_number(data['tokens']), str(data['messages']))

        console.print(Columns([
            Panel(tokens_table, title="[bold cyan]Tokens & Coûts[/bold cyan]", border_style="cyan"),
            Panel(projects_table, title="[bold magenta]Top 5 Projets[/bold magenta]", border_style="magenta")
        ], equal=True, expand=True))
        console.print()

        # Usage 7 derniers jours
        daily = tracker.get_daily_stats(sessions, days=7)
        if daily:
            daily_table = Table(box=box.SIMPLE, show_header=True, header_style="bold blue")
            daily_table.add_column("Date", style="dim")
            daily_table.add_column("Tokens", justify="right", style="cyan")
            daily_table.add_column("Messages", justify="right", style="green")
            daily_table.add_column("Sessions", justify="right", style="yellow")

            for day, data in daily.items():
                daily_table.add_row(day, format_number(data['tokens']), str(data['messages']), str(data['sessions']))

            console.print(Panel(daily_table, title="[bold blue]7 Derniers Jours[/bold blue]", border_style="blue"))
            console.print()

        # Modèles utilisés
        if agg["models_used"]:
            models_text = " | ".join([f"[cyan]{m}[/cyan]" for m in agg["models_used"]])
            console.print(Panel(models_text, title="[bold]Modèles Utilisés[/bold]", border_style="dim"))
            console.print()

        # Sauvegarder snapshot
        history.add_snapshot({
            "total_tokens": total_all,
            "total_messages": agg["total_messages"],
            "total_sessions": agg["total_sessions"]
        })

    # API Platform
    platform = ClaudePlatformTracker(ANTHROPIC_API_KEY, history)

    if not ANTHROPIC_API_KEY:
        api_content = "[yellow]API Key non configurée[/yellow]\n\nPour configurer:\n1. Éditez [cyan].env[/cyan]\n2. Ajoutez: [dim]ANTHROPIC_API_KEY=sk-ant-...[/dim]"
    else:
        result = platform.test_api()
        if "error" in result:
            api_content = f"[green]API Key configurée[/green]\n[red]Erreur: {result['error']}[/red]"
        else:
            api_totals = history.get_api_totals()
            api_content = f"[green]Connexion OK[/green] ({result['model']})\n\n"
            api_content += f"Appels: [cyan]{api_totals['calls']}[/cyan] | "
            api_content += f"Tokens: [cyan]{format_number(api_totals['tokens_in'] + api_totals['tokens_out'])}[/cyan] | "
            api_content += f"Coût: [yellow]{format_cost(api_totals['cost'])}[/yellow]"

    # Plan Claude AI
    plan = os.getenv("CLAUDE_PLAN", "max").lower()
    plans_info = {
        "free": ("Free", "$0/mois", "Limité", "dim"),
        "pro": ("Pro", "$20/mois", "5x Free", "green"),
        "max": ("Max 5x", "$100/mois", "5x Pro", "cyan"),
        "max200": ("Max 20x", "$200/mois", "20x Pro", "magenta")
    }
    info = plans_info.get(plan, plans_info["max"])

    plan_content = f"[bold {info[3]}]{info[0]}[/bold {info[3]}]\n"
    plan_content += f"[{info[3]}]{info[1]}[/{info[3]}] - {info[2]}"

    if agg["total_sessions"] > 0 and cost["total_cost"] > 0:
        plan_price = 200 if plan == "max200" else (100 if "max" in plan else (20 if plan == "pro" else 0))
        if plan_price > 0:
            savings = cost["total_cost"] - plan_price
            if savings > 0:
                plan_content += f"\n\n[bold green]Économies: {format_cost(savings)}[/bold green]"

    console.print(Columns([
        Panel(api_content, title="[bold yellow]API Platform[/bold yellow]", border_style="yellow"),
        Panel(plan_content, title="[bold green]Abonnement[/bold green]", border_style="green")
    ], equal=True, expand=True))
    console.print()

    # Tarifs de référence
    pricing_table = Table(box=box.ROUNDED, show_header=True, header_style="bold")
    pricing_table.add_column("Modèle", style="cyan")
    pricing_table.add_column("Input/1M", justify="right", style="green")
    pricing_table.add_column("Output/1M", justify="right", style="yellow")
    pricing_table.add_column("Cache R/1M", justify="right", style="dim")

    for model, prices in PRICING.items():
        if model != "default":
            name = model.replace("claude-", "").replace("-20251101", "").replace("-20250514", "")
            pricing_table.add_row(name, f"${prices['input']:.2f}", f"${prices['output']:.2f}", f"${prices['cache_read']:.2f}")

    console.print(Panel(pricing_table, title="[bold]Tarifs API - Février 2026[/bold]", border_style="dim"))
    console.print()

    console.print(f"[dim]Historique sauvegardé: {HISTORY_FILE}[/dim]")
    console.print()


if __name__ == "__main__":
    main()
