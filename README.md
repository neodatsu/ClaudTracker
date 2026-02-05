# ClaudTracker

Outil de suivi d'utilisation pour Claude AI et Claude API.

## Description

ClaudTracker analyse votre utilisation de Claude Code en local et fournit :

- **Statistiques Claude Code** : parsing des fichiers JSONL locaux (`~/.claude/projects/`)
- **Comptage de tokens** : input, output, cache (lecture/écriture)
- **Estimation des coûts** : équivalent API basé sur les tarifs 2026
- **Historique persistant** : snapshots et appels API enregistrés
- **Analyse par projet** : top projets par consommation de tokens
- **Statistiques temporelles** : usage des 7 derniers jours

## Installation

```bash
# Cloner le dépôt
git clone https://github.com/votre-user/ClaudTracker.git
cd ClaudTracker

# Créer l'environnement virtuel
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# ou: venv\Scripts\activate  # Windows

# Installer les dépendances
pip install -r requirements.txt

# Configurer les variables d'environnement
cp .env.example .env
# Éditer .env avec votre clé API (optionnel)
```

## Configuration

Éditez le fichier `.env` :

```bash
# Clé API Anthropic (optionnel, pour tester l'API)
ANTHROPIC_API_KEY=sk-ant-api03-votre-clé-ici

# Votre plan Claude AI (free, pro, max, max200)
CLAUDE_PLAN=pro
```

## Usage

```bash
# Activer l'environnement virtuel
source venv/bin/activate

# Lancer le tracker
python claudtracker.py
```

### Exemple de sortie

```
══════════════════════════════════════════════════════════════
  CLAUDE USAGE TRACKER v2.0
══════════════════════════════════════════════════════════════

══════════════════════════════════════════════════════════════
  CLAUDE CODE - USAGE LOCAL
══════════════════════════════════════════════════════════════

  Sessions totales     : 55
  Projets              : 12
  Messages envoyés     : 3 849
  Appels d'outils      : 15 234

  TOKENS:
    Input              : 125 000 000
    Output             : 45 000 000
    ...

  COÛT ÉQUIVALENT API (Sonnet):
    TOTAL              : $547.50
```

## Fonctionnalités

| Fonctionnalité | Description |
|----------------|-------------|
| Analyse JSONL | Parse les sessions Claude Code locales |
| Multi-projets | Statistiques par projet |
| Historique | Sauvegarde automatique des snapshots |
| Test API | Vérifie la connexion à l'API Anthropic |
| Tarifs 2026 | Calcul basé sur les prix actuels |

## Structure

```
ClaudTracker/
├── claudtracker.py    # Script principal
├── .env.example       # Template de configuration
├── .env               # Configuration (non versionné)
├── .gitignore         # Fichiers ignorés par Git
├── requirements.txt   # Dépendances Python
└── usage_history.json # Historique (non versionné)
```

## Prérequis

- Python 3.8+
- Claude Code installé (`~/.claude/` doit exister)

## Licence

MIT
