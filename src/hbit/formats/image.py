"""
Handler de imágenes para H-Bit.

Encapsula la lógica existente de PIL/NumPy en la interfaz MediaHandler,
permitiendo que el pipeline trate imágenes como un formato más.

Estrategia: LSB/DCT en canales RGB (la más resiliente para imágenes).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from hbit.formats.base import (
    MediaHandler,
    CarrierData,
    EmbedResult,
    ExtractResult,
    EmbeddingStrategy,
    MediaCategory,
)
from hbit.encoders.lsb import encode_lsb, decode_lsb
from hbit.core.sync import wrap_payload_with_sync, find_payload_boundaries, SYNC_SEQUENCE_LENGTH


class ImageHandler(MediaHandler):
    """Handler para formatos de imagen (PNG, JPEG, BMP, TIFF, WebP).

    Estrategia principal: LSB en el canal con menor percepción visual.
    Estrategia secundaria: DCT en frecuencias medias (JPEG-resilient).

    La imagen se carga como array NumPy RGB de 8 bits. Los bits se
    incrustan en el LSB de los valores de píxel del canal seleccionado.
    """

    @property
    def category(self) -> MediaCategory:
        return MediaCategory.IMAGE

    @property
    def supported_extensions(self) -> list[str]:
        return ["png", "jpg", "jpeg", "bmp", "tiff", "tif", "webp"]

    def load(self, path: Path) -> CarrierData:
        """Carga una imagen como array RGB.

        Args:
            path: Ruta a la imagen.

        Returns:
            CarrierData con el array RGB como raw_data.
        """
        img = Image.open(path)
        original_format = img.format or "PNG"
        img_rgb = img.convert("RGB")
        image_data = np.array(img_rgb, dtype=np.uint8)

        h, w, c = image_data.shape
        # Capacidad LSB: 1 bit por píxel por canal
        capacity = h * w  # Un canal a la vez

        return CarrierData(
            raw_data=image_data.tobytes(),
            metadata={
                "width": w,
                "height": h,
                "channels": c,
                "format": original_format,
                "dtype": "uint8",
                "shape": (h, w, c),
            },
            capacity_bits=capacity,
            strategy=EmbeddingStrategy.LSB,
            category=MediaCategory.IMAGE,
            original_path=path,
            format_info={"pil_format": original_format},
        )

    def save(self, data: bytes, path: Path, carrier: CarrierData) -> Path:
        """Guarda la imagen modificada.

        Args:
            data: Bytes del array RGB modificado.
            path: Ruta de salida.
            carrier: CarrierData original.

        Returns:
            Path del archivo guardado.
        """
        shape = carrier.metadata["shape"]
        image_data = np.frombuffer(data, dtype=np.uint8).reshape(shape)
        img = Image.fromarray(image_data)

        path.parent.mkdir(parents=True, exist_ok=True)

        ext = path.suffix.lower()
        if ext in (".jpg", ".jpeg"):
            # DCT maneja la robustez JPEG, usamos calidad alta para minimizar degradación visual
            img.save(path, "JPEG", quality=100)
        elif ext in (".tiff", ".tif"):
            img.save(path, "TIFF")
        elif ext == ".bmp":
            img.save(path, "BMP")
        elif ext == ".webp":
            img.save(path, "WEBP", lossless=True)
        else:
            img.save(path, "PNG")

        return path

    def embed(self, carrier: CarrierData, payload_bits: str) -> EmbedResult:
        """Incrusta bits usando LSB o DCT según el formato.

        Args:
            carrier: Datos de la imagen cargados.
            payload_bits: Bits a incrustar.

        Returns:
            EmbedResult con la imagen modificada.
        """
        shape = carrier.metadata["shape"]
        image_data = np.frombuffer(
            carrier.raw_data, dtype=np.uint8
        ).reshape(shape).copy()

        # Determinar estrategia según formato original
        # Si es JPEG/WEBP (formatos con pérdida) -> Usar DCT
        fmt = carrier.metadata.get("format", "").upper()
        if fmt in ["JPEG", "JPG", "WEBP"]:
            # Usar DCT (robusto a compresión)
            from hbit.encoders.dct import encode_dct, compute_adaptive_strength
            
            # Auto-adaptar fuerza según textura de la imagen
            adaptive_strength = compute_adaptive_strength(image_data, channel=1)
            
            # Nota: UniversalEncoder YA envuelve el payload con marcadores de sincronización.
            wrapped = payload_bits
            print(f"DEBUG: Embedding DCT. Strength={adaptive_strength:.1f}, Payload len: {len(wrapped)}")
            
            dct_result = encode_dct(
                image_data, 
                wrapped, 
                channel=1, # Canal Verde
                strength=adaptive_strength, # Auto-adaptativo según textura
                use_jnd=False # DESACTIVADO: El decoder debe coincidir con el paso de cuantización
            )
            
            # Almacenar strength en metadata para que el decoder la conozca
            carrier.metadata["dct_strength"] = adaptive_strength
            
            return EmbedResult(
                output_data=dct_result.encoded_image.tobytes(),
                bits_embedded=dct_result.bits_embedded,
                capacity_used=0.0, # DCT es diferente
                strategy_used=EmbeddingStrategy.DCT,
            )
        else:
            # Usar LSB (estándar para PNG/BMP)
            # Canal 2 (azul) por defecto — menor percepción visual
            channel = 2
            # wrapped = wrap_payload_with_sync(payload_bits) # UniversalEncoder ya lo hace
            wrapped = payload_bits

            lsb_result = encode_lsb(
                image_data, wrapped, channel=channel
            )

            return EmbedResult(
                output_data=lsb_result.encoded_image.tobytes(),
                bits_embedded=len(wrapped),
                capacity_used=lsb_result.capacity_used,
                strategy_used=EmbeddingStrategy.LSB,
            )

    def extract(
        self,
        carrier: CarrierData,
        expected_length: Optional[int] = None,
    ) -> ExtractResult:
        """Extrae bits usando LSB y DCT como fallback.

        Args:
            carrier: Datos de la imagen.
            expected_length: Longitud esperada del payload.

        Returns:
            ExtractResult con los bits extraídos.
        """
        shape = carrier.metadata["shape"]
        image_data = np.frombuffer(
            carrier.raw_data, dtype=np.uint8
        ).reshape(shape).copy()

        # Determinación de estrategia basada en formato
        # Si es JPEG/WEBP, la firma LSB es improbable que sobreviva, y puede dar falsos positivos.
        # Priorizamos DCT.
        fmt = carrier.metadata.get("format", "").upper()
        is_lossy = fmt in ["JPEG", "JPG", "WEBP"]
        
        print(f"DEBUG: ImageHandler.extract called. Format: {fmt}, IsLossy: {is_lossy}")

        # 1. Intentar LSB (Solo si NO es lossy, o como fallback después)
        # En realidad, si firmamos un JPEG, usamos DCT. Si recibimos un JPEG, debemos buscar DCT.
        if not is_lossy:
            for ch in [2, 0, 1]:
                lsb_result = decode_lsb(image_data, channel=ch)
                if lsb_result.payloads_found > 0:
                    print(f"DEBUG: LSB Found in channel {ch}")
                    # Re-envolver con sync markers para que UniversalDecoder
                    # pueda desenvolver de manera consistente con todos los handlers.
                    # decode_lsb ya quitó los sync markers internamente.
                    rewrapped = wrap_payload_with_sync(lsb_result.payload_bits)
                    return ExtractResult(
                        payload_bits=rewrapped,
                        confidence=lsb_result.confidence,
                        strategy_used=EmbeddingStrategy.LSB,
                        payloads_found=lsb_result.payloads_found,
                    )

        # 2. Intentar DCT (Canal Verde principalmente)
        # Esto se ejecuta si es lossy, o si LSB falló en non-lossy
        dct_result = None
        try:
            from hbit.decoders.dct import decode_dct
            
            # Probar canal 1 (Verde) con fuerza 30.0 (usada en embed)
            dct_result = decode_dct(
                image_data, 
                channel=1, 
                strength=35.0,
                expected_payload_length=None # El decoder intentará inferir
            )
            print(f"DEBUG: DCT Extract. Conf: {dct_result.confidence}, Bits: {len(dct_result.payload_bits)}")
        except Exception as e:
            print(f"DEBUG: DCT Crash: {e}")
            import traceback
            traceback.print_exc()
            dct_result = None

        if dct_result:
            # FIX CRÍTICO: UniversalDecoder espera un payload "limpio".
            # decode_dct devuelve un stream continuo. Debemos buscar los marcadores AQUÍ.
            # find_payload_boundaries ahora devuelve TODOS los pares candidatos.
            # Usamos threshold default (0.85) y filtramos por longitud.
            boundaries = find_payload_boundaries(dct_result.payload_bits)
            # print(f"DEBUG: Raw boundaries found: {[b[1]-b[0] for b in boundaries]}")

            # Filtrar boundaries muy cortos (falsos positivos)
            
            # Filtrar boundaries muy cortos (falsos positivos)
            # Un payload H-Bit mínimo tiene ~600 bits. Máximo ~1100 bits.
            # Limitamos a < 1200 bits.
            # ADEMÁS: El contenido del payload debe ser múltiplo de 8 bits (bytes).
            valid_boundaries = [
                b for b in boundaries 
                if 500 < (b[1] - b[0]) < 1200 and (b[1] - b[0]) % 8 == 0
            ]
            # print(f"DEBUG: Valid boundaries: {len(valid_boundaries)}, {[b[1]-b[0] for b in valid_boundaries]}")
            
            if valid_boundaries:
                # Tomar el payload más FRECUENTE (consenso) en lugar del más largo.
                # Esto evita que un solo falso positivo largo (e.g. 832 bits) eclipse a los 100+ correctos (592 bits).
                from collections import Counter
                lengths = [b[1] - b[0] for b in valid_boundaries]
                common_length = Counter(lengths).most_common(1)[0][0]
                
                # Filtrar candidates con ese length
                raw_candidates = [b for b in valid_boundaries if (b[1] - b[0]) == common_length]
                # Ordenar por posición de inicio
                raw_candidates.sort(key=lambda x: x[0])
                
                # De-bounce / Eliminar solapamientos (mismo payload detectado múltiples veces con offset de 1-2 bits)
                candidates = []
                last_end = -1
                for b in raw_candidates:
                    # Si el nuevo candidato empieza después del final del anterior (dejando margen)
                    # O si está muy lejos del anterior inicio (más simple: start > last_start + 5)
                    # Usamos last_end para garantizar no solapamiento
                    if b[0] > last_end:
                        candidates.append(b)
                        last_end = b[1]
                
                # RECONSTRUCCION POR VOTACION (MAJORITY VOTING)
                # Extraer todas las copias del payload
                # find_payload_boundaries devuelve (start, end) del CONTENIDO (sin markers)
                payloads = [dct_result.payload_bits[b[0]:b[1]] for b in candidates]
                
                # Reconstruir bit a bit
                consensus_bits = []
                n_bits = common_length
                for i in range(n_bits):
                    # Tomar el i-ésimo bit de cada copia
                    bits_at_i = [p[i] for p in payloads]
                    # Votación (0 vs 1)
                    # '0'.count > '1'.count -> '0' else '1'
                    zero_count = bits_at_i.count('0')
                    consensus_bit = '0' if zero_count > len(payloads) / 2 else '1'
                    consensus_bits.append(consensus_bit)
                
                payload_content = "".join(consensus_bits)
                
                # UniversalDecoder espera el payload ENVUELTO (con Sync headers/footers)
                # find_payload_boundaries devuelve el contenido limpio.
                # Debemos envolverlo de nuevo para que UniversalDecoder.decode() pueda hacer strip() correctamente.
                final_payload_bits = wrap_payload_with_sync(payload_content)

                return ExtractResult(
                    payload_bits=final_payload_bits,
                    confidence=dct_result.confidence, # Podríamos mejorar confidence basado en consenso
                    strategy_used=EmbeddingStrategy.DCT,
                    payloads_found=len(candidates)
                )
            elif dct_result.confidence > 0.4 and len(dct_result.payload_bits) > 100:
                # Fallback: si no se encuentran marcadores, pasamos todo el stream
                print(f"DEBUG: DCT Raw Fallback (Conf {dct_result.confidence})")
                return ExtractResult(
                    payload_bits=dct_result.payload_bits,
                    confidence=dct_result.confidence,
                    strategy_used=EmbeddingStrategy.DCT,
                    payloads_found=1,
                )

        return ExtractResult(
            payload_bits="",
            confidence=0.0,
            strategy_used=EmbeddingStrategy.LSB, # Default
            payloads_found=0,
        )
