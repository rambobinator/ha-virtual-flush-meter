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
- `meter.py` : logique pure du compteur d'eau optionnel (prises d'eau, association
  chasse ↔ prise d'eau, volume mesuré ou de repli, demi/complète), testée par
  `tests/test_meter.py`.
- `coordinator.py` : relie la sonde source (et le compteur optionnel) au détecteur (événementiel, pas de polling,
  minuteur pour clore un événement sans nouvel échantillon).
- `entity.py` : entité de base (appareil unique par entrée, abonnement au coordinator).
- `sensor.py` : litres chassés, nombre de chasses, T eau froide réseau.
- `binary_sensor.py` : chasse en cours.
- `strings.json` (EN, référence hassfest) + `translations/en.json`, `translations/fr.json`.
  Les traductions vivent DANS le composant, jamais à la racine du dépôt.
- `brand/icon.png` (256 px) et `brand/icon@2x.png` (512 px), générés depuis `docs/logo.jpg`.

## Détection d'une chasse (v3 : contrôle asymétrique)
- Physique : une chasse peut MONTER (l'après-midi, l'eau stagnant dans les tuyaux de la
  maison s'est réchauffée) ou descendre (le matin, réseau froid). La dérive ambiante
  monte aussi : c'est la vitesse qui distingue, pas le sens.
- La vitesse se lit dans la TAILLE D'UN PAS, jamais dans un débit °C/min : HA ne voit
  aucun changement quand la sonde répète la même valeur, donc un saut après 90 min
  tenues paraît plus lent que la dérive (0,007 vs 0,027 °C/min sur données réelles).
  La SNZB-02LD envoie un rapport immédiat à ±0,5 °C, sinon toutes les 15,0 min.
- Départ : |valeur − valeur calme| ≥ `start_threshold` (0.3 °C) dans la fenêtre
  `window` (30 min), dans les deux sens. La valeur tenue au début de la fenêtre compte.
  Les échantillons antérieurs à la fin de l'événement précédent, ou issus du recorder,
  ne sont jamais « calmes ». Un événement est daté de son premier échantillon en écart.
- Comptage :
  - pas unique ≥ `fast_step` (0.5 °C), dans les deux sens, même en cécité ;
  - ou baisse ≥ min(`min_amplitude`, `gap_fraction` × écart), écart = valeur calme −
    minimum glissant réseau ; cécité si écart < `min_gap` (règle d'amplitude seulement) ;
  - une montée lente n'est jamais comptée.
- Fin : un candidat non compté reste ouvert toute la fenêtre (le second pas peut arriver
  15 min plus tard) ; un événement compté se ferme après `debounce` min sans nouvel
  extrême. Nouvelle chasse : `debounce` min après le départ de la précédente.
- Redémarrage : un pas rapide dans l'historique recorder vaut chasse déjà comptée
  (anti-rebond), pour ne pas recompter une chasse en cours.
- Artefacts : un point isolé à plus de ±2 °C sans continuité est ignoré (`OUTLIER_THRESHOLD`).
- Ignorer les états `unknown` / `unavailable` et les valeurs non numériques.
- Régressions obligatoires (tests/test_detector.py) : rejeu réel 14/14 (dont 4 montantes),
  zéro faux positif ; nuits sans chasse (dérive, refroidissement, bruit) = zéro détection.

## Entités
- `sensor.<name>_litres` : device_class water, state_class total_increasing, unité L,
  incrémenté du volume de chaque chasse : mesuré au compteur si configuré (ajouté
  quelques minutes après la chasse), sinon flush_volume × calibration (un changement d'options
  ne réécrit jamais le passé), restauré au redémarrage. Doit apparaître
  dans Énergie → Eau → Appareils d'eau individuels.
- `sensor.<name>_flushes` : nombre de chasses, total_increasing (utilisable par utility_meter).
- `sensor.<name>_cold_water` : minimum glissant de la source sur `cold_water_window`
  (12 h par défaut), réutilisable par ha-virtual-boiler-water-meter. Historique reconstruit depuis le
  recorder au démarrage (`after_dependencies: recorder`).
- Avec compteur seulement : `sensor.<name>_last_flush_volume` (device_class volume, sans
  state_class), `sensor.<name>_half_flushes`, `sensor.<name>_full_flushes`.
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

## Compteur d'eau (optionnel)
- La sonde décide qu'il y a chasse ; le compteur ne fait que mesurer le volume. Il ne
  peut pas détecter seul (un robinet a le même profil). Ne pas l'utiliser pour
  détecter sans données de rejeu le justifiant.
- Volumes appris (`recent_volumes`) persistés via `Store`, supprimés avec l'entrée.
- Constantes de cadence (`METER_*` dans const.py) : liées au rythme d'émission du
  compteur, pas des réglages utilisateur.
- Rejeu sur données réelles : demi-chasse 3,3 L mesurée, chasses 6,3 et 6,7 L mesurées,
  douche / lavage de mains rejetés (repli).

## Limites connues
- Faux négatifs quand T réseau ≈ T cuvette (intersaison) : cécité assumée sous `min_gap`.
- Une chasse tiède qui monte de moins de `fast_step` est ratée ; une sonde qui rapporte
  chaque 0,1 °C ne voit aucune chasse montante (seule la règle de baisse s'applique).
- La sonde n'émet que sur changement ≥ 0.1 °C : la cinétique du pic est écrêtée.
- Sans compteur, la classification 3 L / 6 L n'existe pas. Avec compteur, elle est
  mesurée mais une chasse mêlée à un autre usage est classée « complète » par défaut.
