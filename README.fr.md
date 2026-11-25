# Virtual Flush Meter

[🇬🇧 English version](README.md)

<img src="https://raw.githubusercontent.com/rambobinator/ha-virtual-flush-meter/main/docs/logo.jpg" alt="Logo Virtual Flush Meter" width="160">

Intégration [Home Assistant](https://www.home-assistant.io/) qui **compte les chasses d'eau** et estime l'**eau chassée (en litres)** à partir d'une seule sonde de température plongée dans la cuvette des WC (ex. Sonoff SNZB-02D). L'entité litres peut être ajoutée dans la section **Eau** du tableau de bord Énergie comme appareil d'eau individuel.

> 🚧 Version préliminaire (0.1) : les seuils de détection restent à valider sur des données réelles.

## Entités

| Entité | Description |
|---|---|
| Litres | Eau chassée (L), cumulée. À ajouter dans Énergie → Eau → Appareils d'eau individuels. |
| Chasses | Nombre de chasses, cumulé (compatible `utility_meter`). |
| Eau froide | Température la plus basse de la cuvette sur les dernières heures, proche de celle de l'eau du réseau (reconstruite depuis l'historique après un redémarrage). |
| Chasse | ON pendant une chasse, pour les automatisations. |

## Principe

Après une chasse, la cuvette se remplit d'eau fraîche du réseau, plus froide que l'eau qui stagnait, puis se réchauffe lentement vers la température de la pièce. Une chasse est détectée comme une baisse **vers la température de l'eau du réseau** :

- un événement démarre dès que la température s'écarte de 0,3 °C de sa valeur calme en 30 min, quelle que soit la vitesse ;
- il est compté si la baisse atteint **min(1,0 °C ; 35 % de l'écart disponible)**, l'écart disponible étant la température calme moins la plus basse des 12 dernières heures (≈ eau du réseau) ;
- si l'écart disponible est inférieur à 0,8 °C, la sonde ne distingue plus une chasse du bruit : rien n'est compté ;
- le réchauffement vers la température de la pièce n'est jamais compté, puisqu'il va dans l'autre sens ;
- au moins 5 min entre deux chasses.

```
Litres = chasses × volume par chasse × calibration
```

Le capteur binaire **Chasse** expose les chiffres du dernier événement (valeur calme, écart disponible, seuil, amplitude) pour aider à régler les paramètres.

## Configuration

| Champ | Défaut |
|---|---|
| Sonde de température dans la cuvette | obligatoire |
| Seuil de départ (°C d'écart à la valeur calme) | 0,3 |
| Amplitude pour compter une chasse, plafond (°C) | 1,0 |
| Part de l'écart disponible exigée | 0,35 |
| Plancher de bruit : écart disponible minimal (°C) | 0,8 |
| Fenêtre de détection (min) | 30 |
| Délai minimal entre deux chasses (min) | 5 |
| Volume par chasse (L) | 6 |
| Facteur de calibration | 1 |
| Fenêtre du minimum glissant eau froide (h) | 12 |

Tous les champs sauf la sonde sont modifiables ensuite via **Configurer** sur la carte de l'intégration.

## Limites connues

- Chasses manquées quand l'eau du réseau et l'eau de la cuvette sont à peu près à la même température (intersaison) : sous le plancher de bruit, rien n'est compté.
- Aveugle quand l'eau du réseau est plus chaude que la cuvette : seules les baisses sont comptées.
- La sonde ne remonte que les variations d'au moins 0,1 °C : la partie la plus rapide de la variation est mal mesurée.
- Distinguer les chasses de 3 L et de 6 L est expérimental.

## Installation

Via [HACS](https://hacs.xyz/) → Dépôts personnalisés → `https://github.com/rambobinator/ha-virtual-flush-meter` (catégorie : Intégration), puis redémarrer Home Assistant et ajouter **Virtual Flush Meter** depuis Paramètres → Appareils et services.

## Licence

MIT
