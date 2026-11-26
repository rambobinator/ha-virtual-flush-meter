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
| Volume dernière chasse | *Avec un compteur d'eau.* Volume de la dernière chasse, mesuré ou estimé (attribut `measured`). |
| Demi-chasses / Chasses complètes | *Avec un compteur d'eau.* Nombre de demi-chasses et de chasses complètes, cumulé. |

## Principe

Une chasse remplace l'eau qui stagne dans la cuvette par de l'eau fraîche des tuyaux. La sonde voit la température de la cuvette sauter, puis revenir lentement vers celle de la pièce.

**Une chasse peut aller dans les deux sens.** Le matin, l'eau du réseau arrive froide (13-14 °C) et la cuvette baisse. L'après-midi, l'eau qui stagne dans les tuyaux de la maison s'est réchauffée à la température de la pièce : une chasse peut apporter de l'eau *plus chaude* que la cuvette, et la température monte. Mais la dérive vers la température de la pièce monte aussi : le sens seul ne distingue pas une chasse de la dérive. La vitesse, si.

**La vitesse se lit dans la taille d'un pas, pas dans un débit.** Les sondes sur pile comme la Sonoff SNZB-02 envoient un rapport immédiat quand la température bouge de 0,5 °C, et sinon toutes les 15 min. Une chasse apparaît comme un seul grand pas (0,5 °C ou plus) entre deux lectures ; la dérive arrive par petits pas périodiques (au plus 0,4 °C par 15 min observés), et le bruit par pas de 0,1 °C. Une vitesse (°C/min) est inutilisable : Home Assistant ne voit aucun changement tant que la sonde répète la même valeur, si bien qu'un saut après 90 minutes de lectures identiques paraît plus lent que la dérive du soir.

Les règles :

- **Pas rapide, dans les deux sens** : un pas unique d'au moins 0,5 °C est une chasse ;
- **Forte baisse, à n'importe quelle vitesse** (pour les sondes qui rapportent par petits pas) : une baisse vers la température de l'eau du réseau d'au moins **min(1,0 °C ; 35 % de l'écart disponible)**, l'écart disponible étant la température calme moins la plus basse des 12 dernières heures (≈ eau du réseau). Si cet écart est inférieur à 0,8 °C, cette règle ne compte rien plutôt que de compter du bruit ;
- une montée lente n'est jamais comptée : c'est la dérive vers la température de la pièce ;
- un événement démarre quand la température s'écarte de 0,3 °C de sa valeur calme en 30 min ; au moins 5 min entre deux chasses.

Sur 57 h de données réelles vérifiées avec un compteur d'eau : 14 chasses sur 14, dont 4 montantes, aucune fausse détection.

```
Litres = chasses × volume par chasse × calibration
```

Le capteur binaire **Chasse** expose les chiffres du dernier événement (sens, valeur calme, écart disponible, seuil, amplitude, plus grand pas) pour aider à régler les paramètres.

Si votre sonde envoie un rapport immédiat pour une autre variation que 0,5 °C, réglez **Pas rapide** sur cette valeur. Une sonde qui rapporte chaque variation de 0,1 °C ne verra pas les chasses tièdes (montantes) : seule la règle de forte baisse s'applique.

## Configuration

| Champ | Défaut |
|---|---|
| Sonde de température dans la cuvette | obligatoire |
| Seuil de départ (°C d'écart à la valeur calme) | 0,3 |
| Amplitude pour compter une chasse, plafond (°C) | 1,0 |
| Part de l'écart disponible exigée | 0,35 |
| Plancher de bruit : écart disponible minimal (°C) | 0,8 |
| Pas rapide : un pas unique de cette taille compte comme une chasse (°C) | 0,5 |
| Fenêtre de détection (min) | 30 |
| Délai minimal entre deux chasses (min) | 5 |
| Volume par chasse (L) | 6 |
| Facteur de calibration | 1 |
| Fenêtre du minimum glissant eau froide (h) | 12 |
| Compteur d'eau de la maison (optionnel, mesure chaque chasse) | — |
| Plus petite chasse plausible au compteur (L) | 2 |
| Plus grande chasse plausible au compteur (L) | 9 |
| Demi-chasse en dessous de (L) | 4,5 |

Tous les champs sauf la sonde sont modifiables ensuite via **Configurer** sur la carte de l'intégration.

## Optionnel : mesurer chaque chasse avec un compteur d'eau

Si vous avez un compteur d'eau de la maison dans Home Assistant (wM-Bus via wmbusmeters, compteur d'impulsions, compteur communicant…), ajoutez-le à la configuration ou plus tard via **Configurer**. La sonde décide toujours *qu'il y a eu* une chasse ; le compteur dit *combien* d'eau elle a pris :

- la chasse est associée à la prise d'eau du compteur dans les 5 min autour d'elle, en privilégiant celle qui a commencé juste avant que la sonde ne bouge (le remplissage du réservoir démarre à la chasse) ;
- le volume est lu une fois le remplissage terminé : les litres sont donc ajoutés quelques minutes après la chasse ;
- une prise d'eau hors de 2 à 9 L signifie que la chasse s'est mêlée à un autre usage (douche, lavage de mains) : le volume retenu est alors celui d'une chasse complète typique, appris sur les dernières chasses mesurées ;
- en dessous de 4,5 L, la chasse compte comme une demi-chasse.

Le compteur ne peut pas détecter les chasses seul : un robinet ouvert une minute ressemble exactement à une chasse.

## Limites connues

- Chasses manquées quand l'eau du réseau et l'eau de la cuvette sont à peu près à la même température (intersaison) : sous le plancher de bruit, rien n'est compté.
- Une chasse tiède qui monte la cuvette de moins de 0,5 °C est ratée.
- La sonde ne remonte que les variations d'au moins 0,1 °C : la partie la plus rapide de la variation est mal mesurée.
- Sans compteur d'eau, chaque chasse compte pour le volume configuré : demi-chasses et chasses complètes ne sont pas distinguées.

## Installation

Via [HACS](https://hacs.xyz/) → Dépôts personnalisés → `https://github.com/rambobinator/ha-virtual-flush-meter` (catégorie : Intégration), puis redémarrer Home Assistant et ajouter **Virtual Flush Meter** depuis Paramètres → Appareils et services.

## Licence

MIT
