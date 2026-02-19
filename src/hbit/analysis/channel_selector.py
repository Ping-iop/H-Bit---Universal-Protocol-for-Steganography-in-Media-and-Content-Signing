"""
Selección inteligente de canal de color para el protocolo H-Bit.

Elige el canal RGB óptimo para la incrustación de la firma basándose
en entropía y penalización psicoacústica. Evita canales dominantes
que son más sensibles a modificaciones visibles.

Hito 1.2: El canal azul en cielos es arriesgado; el verde en follaje
es ideal. Se busca minimizar el impacto visual aprovechando las
limitaciones del ojo humano.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from dataclasses import dataclass

from hbit.analysis.entropy import analyze_channel_entropy, ChannelEntropy


@dataclass(frozen=True)
class ChannelSelection:
    """Resultado de la selección inteligente de canal.

    Attributes:
        selected_channel: Índice del canal seleccionado (0=R, 1=G, 2=B).
        scores: Puntuaciones de cada canal (R, G, B).
        entropy: Datos de entropía por canal.
        reason: Justificación textual de la selección.
    """

    selected_channel: int
    scores: tuple[float, float, float]
    entropy: ChannelEntropy
    reason: str

    @property
    def channel_name(self) -> str:
        """Nombre del canal seleccionado."""
        names = ("Red", "Green", "Blue")
        return names[self.selected_channel]


def compute_channel_dominance(image_data: NDArray[np.uint8]) -> NDArray[np.float64]:
    """Calcula la dominancia relativa de cada canal de color.

    Un canal "dominante" es aquel cuya media es significativamente
    mayor que la de los otros. El ojo humano es más sensible a
    cambios en canales dominantes.

    Args:
        image_data: Array 3D (H, W, 3) de la imagen RGB.

    Returns:
        Array de 3 elementos con la dominancia normalizada de cada canal.
        Valores altos = canal dominante = penalización mayor.
    """
    channel_means = np.array([
        image_data[:, :, 0].mean(),
        image_data[:, :, 1].mean(),
        image_data[:, :, 2].mean(),
    ], dtype=np.float64)

    total_mean = channel_means.sum()
    if total_mean > 0:
        dominance = channel_means / total_mean
    else:
        dominance = np.array([1/3, 1/3, 1/3])

    return dominance


def compute_visual_sensitivity(image_data: NDArray[np.uint8]) -> NDArray[np.float64]:
    """Calcula la sensibilidad visual a cambios por canal.

    El ojo humano tiene diferente sensibilidad a cada canal de color:
    - Verde: máxima sensibilidad (conos M, ~55% de la luminancia percibida)
    - Rojo: sensibilidad media (conos L, ~30%)
    - Azul: mínima sensibilidad (conos S, ~15%)

    Esta sensibilidad base se modula con la dominancia del canal en la imagen.

    Args:
        image_data: Array 3D (H, W, 3) de la imagen RGB.

    Returns:
        Array de 3 elementos con la sensibilidad visual normalizada (0.0 a 1.0).
        Valores altos = más sensible = peor para ocultación.
    """
    # Sensibilidad base del sistema visual humano por canal
    # Basada en funciones de igualación de color CIE y luminancia rel.
    base_sensitivity = np.array([0.30, 0.55, 0.15])

    # Modular con dominancia de la imagen
    dominance = compute_channel_dominance(image_data)

    # Sensibilidad compuesta: base * dominancia
    # Canal dominante + alta sensibilidad base = alta penalización
    combined = base_sensitivity * (0.5 + dominance)

    # Normalizar
    combined = combined / combined.max()

    return combined


def select_optimal_channel(
    image_data: NDArray[np.uint8],
    entropy_weight: float = 0.6,
    sensitivity_penalty: float = 0.4,
) -> ChannelSelection:
    """Selecciona el canal óptimo para la incrustación H-Bit.

    Combina dos factores:
    1. Entropía del canal (más entropía → mejor ocultación)
    2. Sensibilidad visual (menos sensible → más seguro)

    Score(canal) = entropy_weight * entropy_norm - penalty * sensitivity

    Args:
        image_data: Array 3D (H, W, 3) de la imagen RGB.
        entropy_weight: Peso relativo de la entropía (0.0 a 1.0).
        sensitivity_penalty: Peso de la penalización por sensibilidad.

    Returns:
        ChannelSelection con el canal óptimo y justificación.
    """
    # Análisis de entropía
    entropy = analyze_channel_entropy(image_data)
    entropy_values = np.array(entropy.values)
    max_entropy = entropy_values.max()
    if max_entropy > 0:
        entropy_normalized = entropy_values / max_entropy
    else:
        entropy_normalized = np.ones(3) / 3

    # Sensibilidad visual
    sensitivity = compute_visual_sensitivity(image_data)

    # Score final: alta entropía + baja sensibilidad = mejor
    scores = entropy_weight * entropy_normalized - sensitivity_penalty * sensitivity

    # Seleccionar canal con mayor score
    selected = int(np.argmax(scores))

    # Generar justificación
    channel_names = ("Rojo", "Verde", "Azul")
    reason = (
        f"Canal {channel_names[selected]} seleccionado: "
        f"entropía={entropy.values[selected]:.3f} bits, "
        f"sensibilidad visual={sensitivity[selected]:.3f}. "
    )

    if selected == 2:  # Azul
        reason += "Canal azul: mínima sensibilidad visual humana."
    elif selected == 0:  # Rojo
        reason += "Canal rojo: mejor relación entropía/sensibilidad para esta imagen."
    else:  # Verde
        reason += "Canal verde: alta entropía compensa su mayor sensibilidad."

    return ChannelSelection(
        selected_channel=selected,
        scores=tuple(float(s) for s in scores),
        entropy=entropy,
        reason=reason,
    )
