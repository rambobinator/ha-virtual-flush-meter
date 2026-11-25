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
- `detector.py` : logique de détection pure (stdlib seule, sans Home Assistant), testée
  par `tests/test_detector.py` (`pytest -q tests`).
- `coordinator.py` : relie la sonde source au détecteur (événementiel, pas de polling,
  minuteur pour clore un événement sans nouvel échantillon).
- `entity.py` : entité de base (appareil unique par entrée, abonnement au coordinator).
- `sensor.py` : litres chassés, nombre de chasses, T eau froide réseau.
- `binary_sensor.py` : chasse en cours.
- `strings.json` (EN, référence hassfest) + `translations/en.json`, `translations/fr.json`.
  Les traductions vivent DANS le composant, jamais à la racine du dépôt.
- `brand/icon.png` (256 px) et `brand/icon@2x.png` (512 px), générés depuis `docs/logo.jpg`.

## Détection d'une chasse (v2 : amplitude en fenêtre glissante)
- Pas de porte de dérivée par pas : une vitesse entre deux échantillons dépend de la
  fréquence d'émission de la sonde (cause des chasses ratées en v1).
- Départ : |valeur − valeur calme| ≥ `start_threshold` (0.3 °C) dans la fenêtre
  `window` (30 min), dans les deux sens. Les échantillons antérieurs à la fin de
  l'événement précédent, ou issus de l'historique recorder, ne sont jamais « calmes ».
  La valeur tenue au début de la fenêtre (dernier échantillon avant) compte aussi :
  HA n'émet pas de changement d'état quand la sonde renvoie la même valeur.
- Un événement est daté de son premier échantillon en écart (pas de la valeur calme).
- Écart disponible = valeur calme − minimum glissant réseau (échantillons antérieurs
  à l'événement, sur `cold_water_window`).
- Comptage : excursion VERS la référence réseau (vers le bas) d'au moins
  min(`min_amplitude`, `gap_fraction` × écart). La dérive ambiante va toujours vers
  l'ambiance (sens opposé) : jamais comptée. Ne pas réintroduire le comptage à la hausse.
- Plancher de bruit : écart < `min_gap` (0.8 °C) → cécité assumée, rien n'est compté.
- Fin : `debounce` min sans nouvel extrême, ou `window` après le départ ; une nouvelle
  chasse exige `debounce` min depuis le départ de la précédente.
- Artefacts : un point isolé à plus de ±2 °C sans continuité est ignoré (`OUTLIER_THRESHOLD`).
- Ignorer les états `unknown` / `unavailable` et les valeurs non numériques.
- `gap_fraction` = 0.35 par défaut : rejeu de données réelles SNZB-02LD (pas de 0,5 °C,
  émission ~15 min), 6 chasses sur 7 détectées, zéro faux positif.
- Régressions obligatoires (tests/test_detector.py) : nuits sans chasse (dérive de
  réchauffement ≥ 0.4 °C/15 min, refroidissement, bruit) = zéro détection.

## Entités
- `sensor.<name>_litres` : device_class water, state_class total_increasing, unité L,
  incrémenté de flush_volume × calibration à chaque chasse (un changement d'options
  ne réécrit jamais le passé), restauré au redémarrage. Doit apparaître
  dans Énergie → Eau → Appareils d'eau individuels.
- `sensor.<name>_flushes` : nombre de chasses, total_increasing (utilisable par utility_meter).
- `sensor.<name>_cold_water` : minimum glissant de la source sur `cold_water_window`
  (12 h par défaut), réutilisable par ha-virtual-boiler-water-meter. Historique reconstruit depuis le
  recorder au démarrage (`after_dependencies: recorder`).
- `binary_sensor.<name>_flush` : ON pendant l'événement (pour automatisations), attributs
  de diagnostic du dernier événement (valeur calme, écart, seuil, cécité).

## Conventions
- Python 3.13, Home Assistant ≥ 2024.12, `iot_class: calculated`.
- `ruff check` + `ruff format` (config dans pyproject.toml), hassfest et HACS validate
  propres (workflows dans `.github/workflows/`).
- README.md (EN) et README.fr.md (FR) maintenus en parallèle, style et structure
  identiques à ha-virtual-boiler-water-meter.
- Tout paramètre doit être modifiable via Options (config_flow), jamais magique.
  Ajouter un paramètre = const.py + config_flow.py + strings.json + en.json + fr.json.
- Pas de requirements externes : stdlib + homeassistant uniquement.
- Release : bump `version` dans manifest.json ET pyproject.toml, commit, push, puis tag
  `X.Y.Z` (sans « v », comme ha-virtual-boiler-water-meter) sur ce commit. Le workflow
  release refuse un tag différent de la version du manifest. Ne pas réutiliser un tag existant.

## Limites connues
- Faux négatifs quand T réseau ≈ T cuvette (intersaison) : cécité assumée sous `min_gap`.
- Aveugle si l'eau du réseau est plus chaude que la cuvette (seules les baisses comptent).
- La sonde n'émet que sur changement ≥ 0.1 °C : la cinétique du pic est écrêtée.
- La classification 3 L / 6 L est expérimentale (étalonnage supervisé), ne pas la
  présenter comme fiable.
