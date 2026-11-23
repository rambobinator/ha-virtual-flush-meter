# AGENTS.md — ha-virtual-flush-meter

## Projet
Intégration Home Assistant (HACS) qui compte les chasses d'eau et estime les litres
consommés à partir d'une seule sonde de température posée dans l'eau de la cuvette WC
(ex. Sonoff SNZB-02D).
Reprend le pattern de rambobinator/ha-virtual-boiler-water-meter (config_flow +
options flow, `async_track_state_change_event`, `RestoreSensor`, CI identique).
Domaine `virtual_flush_meter`, code dans `custom_components/virtual_flush_meter/`.

## Structure
- `__init__.py` : setup/unload, rechargement sur changement d'options.
- `const.py` : clés de config et valeurs par défaut (source unique de vérité).
- `config_flow.py` : config flow + options flow (la sonde source est figée après création).
- `coordinator.py` : moteur de détection de chasse (événementiel, pas de polling).
- `sensor.py` : litres chassés, nombre de chasses, T eau froide réseau.
- `binary_sensor.py` : chasse en cours.
- `strings.json` (EN, référence hassfest) + `translations/en.json`, `translations/fr.json`.
  Les traductions vivent DANS le composant, jamais à la racine du dépôt.
- `brand/icon.png` (256 px) et `brand/icon@2x.png` (512 px), générés depuis `docs/logo.jpg`.

## Détection d'une chasse
- Un événement = variation cumulée ≥ `min_amplitude` (1.0 °C) en ≤ `window` (30 min),
  points rapprochés regroupés, anti-rebond `debounce` (5 min),
  dérivée |dT/dt| ≥ `derivative_threshold` (0.3 °C/min).
- La trajectoire peut être en hausse OU en baisse (la cuvette converge vers la
  température du réseau).
- Artefacts : ignorer un seul point isolé au-delà de ±2 °C sans continuité
  (`OUTLIER_THRESHOLD`).
- Ignorer les états `unknown` / `unavailable` et les valeurs non numériques.

## Entités
- `sensor.<name>_litres` : device_class water, state_class total_increasing, unité L,
  = chasses × flush_volume × calibration, restauré au redémarrage. Doit apparaître
  dans Énergie → Eau → Appareils d'eau individuels.
- `sensor.<name>_flushes` : nombre de chasses, total_increasing (utilisable par utility_meter).
- `sensor.<name>_cold_water` : minimum glissant de la source sur `cold_water_window`
  (12 h par défaut), réutilisable par ha-virtual-boiler-water-meter.
- `binary_sensor.<name>_flush` : ON pendant l'événement (pour automatisations).

## Conventions
- Python 3.13, Home Assistant ≥ 2024.12, `iot_class: calculated`.
- `ruff check` + `ruff format` (config dans pyproject.toml), hassfest et HACS validate
  propres (workflows dans `.github/workflows/`).
- README.md (EN) et README.fr.md (FR) maintenus en parallèle, style et structure
  identiques à ha-virtual-boiler-water-meter.
- Tout paramètre doit être modifiable via Options (config_flow), jamais magique.
  Ajouter un paramètre = const.py + config_flow.py + strings.json + en.json + fr.json.
- Pas de requirements externes : stdlib + homeassistant uniquement.
- Release : bump `version` dans manifest.json, puis tag `vX.Y.Z` identique
  (le workflow release vérifie la concordance).

## Limites connues
- Faux négatifs quand T réseau ≈ T cuvette (intersaison).
- La sonde n'émet que sur changement ≥ 0.1 °C : la cinétique du pic est écrêtée.
- La classification 3 L / 6 L est expérimentale (étalonnage supervisé), ne pas la
  présenter comme fiable.
