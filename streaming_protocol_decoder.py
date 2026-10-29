"""
Streaming Binary Protocol Decoder con Máquina de Estados Finita (FSM).
Implementación autocontenida de alta eficiencia, tolerancia a fragmentación arbitraria,
resincronización determinista ante ruido y validación de integridad CRC-16.
"""
from __future__ import annotations

import enum
import struct
import unittest
from dataclasses import dataclass
from typing import List, Optional


# =====================================================================
# CONSTANTES DE PROTOCOLO Y FORMATOS BINARIOS
# =====================================================================

MAGIC_INT: int = 0xDEADBEEF
MAGIC_BYTES: bytes = struct.pack(">I", MAGIC_INT)

# Formato de Encabezado: >IHH (Magic: uint32, MsgID: uint16, PayloadLen: uint16)
HEADER_FORMAT: str = ">IHH"
HEADER_SIZE: int = struct.calcsize(HEADER_FORMAT)  # 8 bytes

# Formato de Trailer: >H (Checksum CRC-16: uint16)
TRAILER_FORMAT: str = ">H"
TRAILER_SIZE: int = struct.calcsize(TRAILER_FORMAT)  # 2 bytes

DEFAULT_MAX_PAYLOAD_SIZE: int = 65535


# =====================================================================
# ESTRUCTURAS DE DATOS INMUTABLES (@dataclass puro con slots)
# =====================================================================

@dataclass(slots=True, frozen=True)
class FrameHeader:
    """Metadatos de la cabecera de trama."""
    magic: int
    msg_id: int
    payload_length: int


@dataclass(slots=True, frozen=True)
class BinaryFrame:
    """Trama binaria decodificada y validada."""
    header: FrameHeader
    payload: bytes
    checksum: int


# =====================================================================
# MÁQUINA DE ESTADOS FINITA (FSM)
# =====================================================================

class DecoderState(enum.Enum):
    """Estados del autómata de decodificación streaming."""
    AWAIT_MAGIC = "AWAIT_MAGIC"
    AWAIT_HEADER = "AWAIT_HEADER"
    AWAIT_PAYLOAD = "AWAIT_PAYLOAD"
    AWAIT_TRAILER = "AWAIT_TRAILER"


# =====================================================================
# INTEGRIDAD DETERMINISTA (CRC-16-CCITT)
# =====================================================================

def compute_crc16(data: bytes | bytearray | memoryview) -> int:
    """
    Calcula el Checksum CRC-16-CCITT (Polinomio 0x1021, Init 0xFFFF)
    de forma determinista sobre la cabecera y el cuerpo de la trama.
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def encode_frame(msg_id: int, payload: bytes) -> bytes:
    """
    Empaqueta un mensaje binario con el formato canónico del protocolo:
    [MAGIC (4B)] [MSG_ID (2B)] [PAYLOAD_LEN (2B)] [PAYLOAD (NB)] [CRC16 (2B)]
    """
    header_bytes = struct.pack(HEADER_FORMAT, MAGIC_INT, msg_id, len(payload))
    data_to_verify = header_bytes + payload
    checksum = compute_crc16(data_to_verify)
    trailer_bytes = struct.pack(TRAILER_FORMAT, checksum)
    return header_bytes + payload + trailer_bytes


# =====================================================================
# DECODIFICADOR STREAMING BINARIO (FEED & FSM)
# =====================================================================

class StreamingProtocolDecoder:
    """
    Decodificador de protocolo binario por flujo continuo.
    
    Características arquitecturales:
    - Búfer acumulador continuo basado en bytearray para O(1) amortizado.
    - FSM de 4 estados para tolerancia total a fragmentación arbitraria (1B a NB).
    - Desempaquetado exacto vía struct.unpack('>IHH', ...).
    - Búsqueda y resincronización ante ruido o centinelas inválidos sin bloquear.
    - Cero dependencias externas y tipado estricto.
    """

    def __init__(self, max_payload_size: int = DEFAULT_MAX_PAYLOAD_SIZE):
        self.max_payload_size: int = max_payload_size
        self._buffer: bytearray = bytearray()
        self._state: DecoderState = DecoderState.AWAIT_MAGIC
        self._current_header: Optional[FrameHeader] = None
        self._current_payload: Optional[bytes] = None

    @property
    def state(self) -> DecoderState:
        """Devuelve el estado actual del autómata."""
        return self._state

    @property
    def buffer_size(self) -> int:
        """Cantidad de bytes actualmente retenidos en el búfer."""
        return len(self._buffer)

    def _reset_frame_state(self) -> None:
        """Reinicia los acumuladores temporales de la trama activa."""
        self._current_header = None
        self._current_payload = None
        self._state = DecoderState.AWAIT_MAGIC

    def feed(self, chunk: bytes) -> List[BinaryFrame]:
        """
        Alimenta el decodificador con un bloque de bytes crudos.
        Procesa de forma iterativa y no bloqueante todas las tramas completas,
        manejando fragmentación, concatenación y resincronización byte a byte.
        """
        if not chunk:
            return []

        self._buffer.extend(chunk)
        decoded_frames: List[BinaryFrame] = []

        while True:
            # -------------------------------------------------------------
            # ESTADO 1: AWAIT_MAGIC
            # -------------------------------------------------------------
            if self._state == DecoderState.AWAIT_MAGIC:
                if len(self._buffer) < 4:
                    # No hay suficientes bytes para verificar el centinela
                    break

                magic_index = self._buffer.find(MAGIC_BYTES)
                if magic_index == -1:
                    # El centinela no está en el búfer; conservar únicamente
                    # los últimos 3 bytes para no romper el magic si llega dividido
                    del self._buffer[:-3]
                    break
                elif magic_index > 0:
                    # Descartar ruido/basura previo al centinela hallado
                    del self._buffer[:magic_index]

                # Centinela validado en la posición 0 del búfer
                self._state = DecoderState.AWAIT_HEADER

            # -------------------------------------------------------------
            # ESTADO 2: AWAIT_HEADER
            # -------------------------------------------------------------
            if self._state == DecoderState.AWAIT_HEADER:
                if len(self._buffer) < HEADER_SIZE:
                    break

                # Desempaquetado exacto de cabecera: >IHH (8 bytes)
                magic, msg_id, payload_len = struct.unpack(
                    HEADER_FORMAT, self._buffer[:HEADER_SIZE]
                )

                # Doble verificación de centinela
                if magic != MAGIC_INT:
                    del self._buffer[:1]
                    self._reset_frame_state()
                    continue

                # Validación de cota superior de payload
                if payload_len > self.max_payload_size:
                    # Payload monstruoso/corrupto: descartar centinela y resincronizar
                    del self._buffer[:1]
                    self._reset_frame_state()
                    continue

                self._current_header = FrameHeader(
                    magic=magic,
                    msg_id=msg_id,
                    payload_length=payload_len
                )
                self._state = DecoderState.AWAIT_PAYLOAD

            # -------------------------------------------------------------
            # ESTADO 3: AWAIT_PAYLOAD
            # -------------------------------------------------------------
            if self._state == DecoderState.AWAIT_PAYLOAD:
                assert self._current_header is not None
                total_payload_needed = HEADER_SIZE + self._current_header.payload_length

                if len(self._buffer) < total_payload_needed:
                    break

                # Extracción del payload
                self._current_payload = bytes(self._buffer[HEADER_SIZE:total_payload_needed])
                self._state = DecoderState.AWAIT_TRAILER

            # -------------------------------------------------------------
            # ESTADO 4: AWAIT_TRAILER
            # -------------------------------------------------------------
            if self._state == DecoderState.AWAIT_TRAILER:
                assert self._current_header is not None
                assert self._current_payload is not None
                total_frame_size = HEADER_SIZE + self._current_header.payload_length + TRAILER_SIZE

                if len(self._buffer) < total_frame_size:
                    break

                # Extracción del Checksum del trailer: >H (2 bytes)
                trailer_offset = total_frame_size - TRAILER_SIZE
                received_checksum = struct.unpack(
                    TRAILER_FORMAT, self._buffer[trailer_offset:total_frame_size]
                )[0]

                # Validación de integridad determinista sobre (Header + Payload)
                data_to_verify = self._buffer[:trailer_offset]
                expected_checksum = compute_crc16(data_to_verify)

                if received_checksum == expected_checksum:
                    # Trama válida y verificada
                    frame = BinaryFrame(
                        header=self._current_header,
                        payload=self._current_payload,
                        checksum=received_checksum
                    )
                    decoded_frames.append(frame)

                    # Poda de la trama consumida
                    del self._buffer[:total_frame_size]
                    self._reset_frame_state()
                else:
                    # Checksum corrupto: descartar centinela para buscar el siguiente en el flujo
                    del self._buffer[:1]
                    self._reset_frame_state()

        return decoded_frames


# =====================================================================
# SUITE DE PRUEBAS UNITARIAS (UNITTEST)
# =====================================================================

class TestStreamingProtocolDecoder(unittest.TestCase):
    """Batería de pruebas exhaustiva para verificar streaming, FSM y resincronización."""

    def setUp(self):
        self.decoder = StreamingProtocolDecoder(max_payload_size=1024)

    def test_single_complete_frame(self):
        """Verifica la decodificación inmediata de una trama única completa."""
        payload = b"PING_ALIVE"
        raw_bytes = encode_frame(msg_id=101, payload=payload)

        frames = self.decoder.feed(raw_bytes)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].header.msg_id, 101)
        self.assertEqual(frames[0].header.payload_length, len(payload))
        self.assertEqual(frames[0].payload, payload)
        self.assertEqual(self.decoder.buffer_size, 0)
        self.assertEqual(self.decoder.state, DecoderState.AWAIT_MAGIC)

    def test_zero_length_payload(self):
        """Verifica el soporte para tramas con cuerpo vacío (señales/heartbeats)."""
        raw_bytes = encode_frame(msg_id=200, payload=b"")

        frames = self.decoder.feed(raw_bytes)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].header.msg_id, 200)
        self.assertEqual(frames[0].header.payload_length, 0)
        self.assertEqual(frames[0].payload, b"")
        self.assertEqual(self.decoder.buffer_size, 0)

    def test_extreme_fragmentation_byte_by_byte(self):
        """Inyección byte a byte (fragmentación máxima) para verificar la continuidad de la FSM."""
        payload = b"DATOS_FRAGMENTADOS_AL_LIMITE_BYTE_A_BYTE"
        raw_bytes = encode_frame(msg_id=305, payload=payload)

        collected_frames: List[BinaryFrame] = []
        for i, byte_val in enumerate(raw_bytes):
            res = self.decoder.feed(bytes([byte_val]))
            if i < len(raw_bytes) - 1:
                self.assertEqual(len(res), 0, f"No debería emitir trama en el byte {i}")
            else:
                collected_frames.extend(res)

        self.assertEqual(len(collected_frames), 1)
        self.assertEqual(collected_frames[0].header.msg_id, 305)
        self.assertEqual(collected_frames[0].payload, payload)
        self.assertEqual(self.decoder.buffer_size, 0)

    def test_multiple_concatenated_frames(self):
        """Verifica la decodificación de múltiples tramas empaquetadas en un único búfer."""
        f1 = encode_frame(msg_id=1, payload=b"FRAME_UNO")
        f2 = encode_frame(msg_id=2, payload=b"FRAME_DOS_LARGO")
        f3 = encode_frame(msg_id=3, payload=b"FRAME_TRES_FINAL")
        stream = f1 + f2 + f3

        frames = self.decoder.feed(stream)
        self.assertEqual(len(frames), 3)
        self.assertEqual([f.header.msg_id for f in frames], [1, 2, 3])
        self.assertEqual(frames[0].payload, b"FRAME_UNO")
        self.assertEqual(frames[1].payload, b"FRAME_DOS_LARGO")
        self.assertEqual(frames[2].payload, b"FRAME_TRES_FINAL")
        self.assertEqual(self.decoder.buffer_size, 0)

    def test_resynchronization_after_noise_and_invalid_magic(self):
        """Verifica la recuperación automática tras inyección de ruido y falsos centinelas."""
        noise_prefix = b"\x00\xff\xee\xcc\x12\x34\xde\xad\xaa\xbb"  # Incluye prefijo falso \xde\xad
        valid_frame = encode_frame(msg_id=999, payload=b"DATOS_VALIDOS_POST_RUIDO")
        stream = noise_prefix + valid_frame

        frames = self.decoder.feed(stream)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].header.msg_id, 999)
        self.assertEqual(frames[0].payload, b"DATOS_VALIDOS_POST_RUIDO")
        self.assertEqual(self.decoder.buffer_size, 0)

    def test_corrupted_checksum_discard_and_recovery(self):
        """Verifica que una trama con Checksum corrupto sea descartada y la siguiente decodificada."""
        # 1. Trama corrupta (alteramos los 2 últimos bytes del trailer)
        corrupted_frame = bytearray(encode_frame(msg_id=400, payload=b"PAYLOAD_A_CORROMPER"))
        corrupted_frame[-1] ^= 0xFF
        corrupted_frame[-2] ^= 0xFF

        # 2. Trama subsiguiente válida
        valid_frame = encode_frame(msg_id=401, payload=b"PAYLOAD_SANO_SIGUIENTE")

        stream = bytes(corrupted_frame) + valid_frame
        frames = self.decoder.feed(stream)

        # La corrupta debe ser descartada; la válida debe ser emitida
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].header.msg_id, 401)
        self.assertEqual(frames[0].payload, b"PAYLOAD_SANO_SIGUIENTE")
        self.assertEqual(self.decoder.buffer_size, 0)

    def test_arbitrary_chunk_sizes(self):
        """Prueba de estrés con bloques de tamaños desiguales (primos: 3, 7, 11, 13 bytes)."""
        stream = b"".join(
            encode_frame(msg_id=idx, payload=f"MSG_INDEX_{idx}".encode())
            for idx in range(1, 15)
        )

        chunk_sizes = [3, 7, 11, 13, 5, 2]
        c_idx = 0
        collected: List[BinaryFrame] = []

        ptr = 0
        while ptr < len(stream):
            size = chunk_sizes[c_idx % len(chunk_sizes)]
            chunk = stream[ptr:ptr + size]
            collected.extend(self.decoder.feed(chunk))
            ptr += size
            c_idx += 1

        self.assertEqual(len(collected), 14)
        for i, frame in enumerate(collected, start=1):
            self.assertEqual(frame.header.msg_id, i)
            self.assertEqual(frame.payload, f"MSG_INDEX_{i}".encode())
        self.assertEqual(self.decoder.buffer_size, 0)

    def test_oversized_payload_rejection(self):
        """Verifica que cabeceras con payload mayor a max_payload_size sean descartadas."""
        # Simular cabecera corrupta con longitud 5000 (supera el límite configurado de 1024)
        malicious_header = struct.pack(HEADER_FORMAT, MAGIC_INT, 1, 5000)
        valid_frame = encode_frame(msg_id=10, payload=b"OK")

        frames = self.decoder.feed(malicious_header + valid_frame)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].header.msg_id, 10)


if __name__ == "__main__":
    unittest.main()
