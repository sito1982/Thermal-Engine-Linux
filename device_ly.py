"""
Driver para Thermalright Trofeo Vision 9.16 LCD (0416:5408).
Protocolo LY USB bulk, basado en la implementación de thermalright-trcc-linux.
Resolución configurada: 1920x480
"""

import struct

import usb.core
import usb.util


LY_VID = 0x0416
LY_PID = 0x5408

HANDSHAKE_TIMEOUT_MS = 5000
WRITE_TIMEOUT_MS = 5000
READ_TIMEOUT_MS = 5000

HANDSHAKE_READ_SIZE = 512
CHUNK_SIZE = 512
CHUNK_HEADER_SIZE = 16
CHUNK_DATA_SIZE = 496
USB_WRITE_SIZE = 4096

# 16 bytes de cabecera + 2032 bytes a cero = 2048 bytes.
HANDSHAKE_PAYLOAD = bytes([
    0x02, 0xFF, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00,
    0x01, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00,
]) + bytes(2032)


class LYDevice:
    """Controlador del protocolo LY para el dispositivo USB 0416:5408."""

    def __init__(self):
        self.dev = None
        self.interface_number = 0
        self.ep_out = None
        self.ep_in = None
        self.pm = None
        self.sub_type = None
        # Resolución nativa del LCD Trofeo Vision 9.16
        self.width = 1920
        self.height = 480

    @property
    def is_open(self):
        return self.dev is not None and self.ep_out is not None

    def is_available(self):
        return usb.core.find(idVendor=LY_VID, idProduct=LY_PID) is not None

    def open(self):
        """Abre el dispositivo y ejecuta el handshake obligatorio."""
        self.dev = usb.core.find(idVendor=LY_VID, idProduct=LY_PID)
        if self.dev is None:
            raise OSError("LY device 0416:5408 not found")

        try:
            if self.dev.is_kernel_driver_active(self.interface_number):
                self.dev.detach_kernel_driver(self.interface_number)
                print("[LY] Kernel driver detached")
        except (NotImplementedError, usb.core.USBError):
            pass

        try:
            self.dev.set_configuration()
        except usb.core.USBError as exc:
            if exc.errno not in (16,):
                self.close()
                raise

        cfg = self.dev.get_active_configuration()
        interface = cfg[(self.interface_number, 0)]

        self.ep_out = usb.util.find_descriptor(
            interface,
            custom_match=lambda endpoint: (
                usb.util.endpoint_direction(endpoint.bEndpointAddress)
                == usb.util.ENDPOINT_OUT
                and usb.util.endpoint_type(endpoint.bmAttributes)
                == usb.util.ENDPOINT_TYPE_BULK
            ),
        )
        self.ep_in = usb.util.find_descriptor(
            interface,
            custom_match=lambda endpoint: (
                usb.util.endpoint_direction(endpoint.bEndpointAddress)
                == usb.util.ENDPOINT_IN
                and usb.util.endpoint_type(endpoint.bmAttributes)
                == usb.util.ENDPOINT_TYPE_BULK
            ),
        )

        if self.ep_out is None or self.ep_in is None:
            self.close()
            raise OSError("[LY] Bulk IN/OUT endpoints not found")

        print(
            "[LY] Endpoints found: "
            f"IN={hex(self.ep_in.bEndpointAddress)}, "
            f"OUT={hex(self.ep_out.bEndpointAddress)}"
        )

        try:
            usb.util.claim_interface(self.dev, self.interface_number)
        except usb.core.USBError:
            pass

        self._handshake()
        return True

    def _handshake(self):
        """Handshake LY: escritura de 2048 B y lectura/respuesta de 512 B."""
        if self.ep_out is None or self.ep_in is None:
            raise OSError("[LY] Device endpoints are not open")

        self.ep_out.write(HANDSHAKE_PAYLOAD, timeout=HANDSHAKE_TIMEOUT_MS)
        print("[LY] Handshake sent (2048 bytes)")

        response = bytes(
            self.ep_in.read(HANDSHAKE_READ_SIZE, timeout=HANDSHAKE_TIMEOUT_MS)
        )

        print(f"[LY] Handshake response (first 48 bytes): {response[:48].hex(' ')}")

        if len(response) < 37:
            raise OSError(
                f"[LY] Invalid handshake response: only {len(response)} bytes"
            )

        if response[0] != 0x03 or response[1] != 0xFF:
            raise OSError(
                "[LY] Handshake validation failed: "
                f"{response[0]:02x} {response[1]:02x} {response[8]:02x}"
            )

        if response[8] not in (0x01, 0x02):
            print(
                "[LY] Warning: unexpected handshake mode "
                f"0x{response[8]:02x}; continuing because the device signature is valid"
            )

        print(
            "[LY] Handshake response accepted: "
            f"signature={response[0]:02x} {response[1]:02x}, "
            f"mode=0x{response[8]:02x}"
        )

        # Protocolo específico del PID 0x5408.
        raw_pm = response[20]
        if raw_pm <= 3:
            raw_pm = 1

        self.pm = 64 + raw_pm
        self.sub_type = response[22] + 1

        print(
            "[LY] Handshake OK: "
            f"PM={self.pm}, SUB={self.sub_type}, "
            f"response={response[:24].hex()}"
        )

    def send_frame(self, jpeg_data):
        """
        Envía un JPEG usando bloques LY:
        16 bytes de cabecera + 496 bytes de datos por bloque.
        """
        if not self.is_open:
            self.open()

        total_size = len(jpeg_data)
        if total_size == 0:
            raise ValueError("[LY] Cannot send an empty JPEG frame")

        num_chunks = total_size // CHUNK_DATA_SIZE + 1
        last_chunk_data = total_size % CHUNK_DATA_SIZE

        chunks = bytearray(num_chunks * CHUNK_SIZE)

        for index in range(num_chunks):
            chunk_offset = index * CHUNK_SIZE
            is_last = index == num_chunks - 1
            data_length = last_chunk_data if is_last else CHUNK_DATA_SIZE

            # Cabecera LY de 16 bytes.
            chunks[chunk_offset] = 0x01
            chunks[chunk_offset + 1] = 0xFF
            struct.pack_into("<I", chunks, chunk_offset + 2, total_size)
            struct.pack_into("<H", chunks, chunk_offset + 6, data_length)
            chunks[chunk_offset + 8] = 0x02  # Modo reportado por el handshake (response[8]).
            struct.pack_into("<H", chunks, chunk_offset + 9, num_chunks)
            struct.pack_into("<H", chunks, chunk_offset + 11, index)

            source_offset = index * CHUNK_DATA_SIZE
            payload = jpeg_data[source_offset:source_offset + data_length]
            payload_offset = chunk_offset + CHUNK_HEADER_SIZE
            chunks[payload_offset:payload_offset + len(payload)] = payload

        # LY exige que el total de bloques sea múltiplo de cuatro.
        padded_chunks = num_chunks
        remainder = padded_chunks % 4
        if remainder:
            padded_chunks += 4 - remainder

        total_bytes = padded_chunks * CHUNK_SIZE
        send_buffer = bytes(chunks) + bytes(total_bytes - len(chunks))

        try:
            position = 0
            while position < total_bytes:
                remaining = total_bytes - position

                if remaining >= USB_WRITE_SIZE:
                    write_size = USB_WRITE_SIZE
                else:
                    write_size = min(2048, remaining)

                self.ep_out.write(
                    send_buffer[position:position + write_size],
                    timeout=WRITE_TIMEOUT_MS,
                )
                position += write_size

            # El dispositivo confirma la recepción del frame.
            self.ep_in.read(HANDSHAKE_READ_SIZE, timeout=READ_TIMEOUT_MS)


            return True

        except usb.core.USBError as exc:
            raise OSError(f"LY write failed: {exc}") from exc

    def close(self):
        if self.dev is None:
            return

        try:
            usb.util.release_interface(self.dev, self.interface_number)
        except Exception:
            pass

        try:
            usb.util.dispose_resources(self.dev)
        except Exception:
            pass

        self.dev = None
        self.ep_out = None
        self.ep_in = None
