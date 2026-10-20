# Sync avis Inflate → métachamps Shopify (Natura Force)

Script GitHub Actions qui synchronise chaque nuit les notes/avis Inflate vers les
métachamps Shopify des produits Natura Force (`inflate.rating` / `inflate.rating_count`),
pour alimenter le JSON-LD `aggregateRating` servi à Google.

## Fichiers

- `sync_inflate_ratings.py` — le script de synchronisation
- `.github/workflows/sync-inflate.yml` — le workflow GitHub Actions (cron quotidien 05:00 Paris)

## Secrets à configurer (Settings → Secrets and variables → Actions)

| Secret | Valeur |
|---|---|
| `SHOPIFY_ACCESS_TOKEN` | Le token Admin API Shopify (`shpat_…`) |
| `SHOPIFY_SHOP` | `natura-force-dev.myshopify.com` |
| `INFLATE_API_KEY` | Clé API Inflate (optionnel, a une valeur par défaut) |

## Déploiement

1. Créer un repo GitHub **privé**
2. Copier ces fichiers à la racine (le dossier `.github/workflows/` tel quel)
3. Ajouter les 3 secrets ci-dessus
4. Activer les Actions si demandé
5. Test manuel : onglet **Actions** → workflow → **Run workflow**

## Test en local

```bash
export SHOPIFY_ACCESS_TOKEN=... SHOPIFY_SHOP=...
python3 sync_inflate_ratings.py --dry-run   # sans écrire
python3 sync_inflate_ratings.py             # écrit réellement
```

## Note fuseau horaire

Le cron GitHub Actions est en **UTC**. 05:00 heure de Paris =
- `0 4 * * *` UTC en hiver (UTC+1)
- `0 3 * * *` UTC en été (UTC+2)

Le workflow utilise `0 4 * * *` (hiver). Si l'heure précise compte peu (les avis
changent rarement), ce réglage convient toute l'année — à 05:00 Paris en été
l'exécution aura simplement lieu à 04:00. Ajustable librement.
