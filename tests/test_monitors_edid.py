import monitors


def _make_edid(manufacturer="GSM", product=0x1234, serial=0x01020304, hdmi=False):
    edid = bytearray(128)
    edid[0:8] = b"\x00\xff\xff\xff\xff\xff\xff\x00"
    letters = [ord(c) - ord("A") + 1 for c in manufacturer]
    value = (letters[0] << 10) | (letters[1] << 5) | letters[2]
    edid[8] = (value >> 8) & 0xFF
    edid[9] = value & 0xFF
    edid[10:12] = product.to_bytes(2, "little")
    edid[12:16] = serial.to_bytes(4, "little")
    if hdmi:
        edid[126] = 1
        ext = bytearray(128)
        ext[0] = 0x02  # CEA-861 extension block
        ext[1] = 0x03
        ext[2] = 4     # DTD offset -> data block collection starts at 4
        ext[4:7] = b"\x00\x0c\x03"  # HDMI OUI
        edid = edid + ext
    return bytes(edid)


def test_parse_edid_reads_identity():
    info = monitors._parse_edid(_make_edid())
    assert info["manufacturer"] == "GSM"
    assert info["model"] == str(0x1234)
    assert info["serial"] == str(0x01020304)
    assert info["is_hdmi"] is False


def test_parse_edid_detects_hdmi_oui():
    info = monitors._parse_edid(_make_edid(hdmi=True))
    assert info["is_hdmi"] is True


def test_parse_edid_rejects_bad_header():
    assert monitors._parse_edid(b"\x00" * 128) == {}


def _encode_mfg(text):
    letters = [ord(c) - ord("A") + 1 for c in text]
    value = (letters[0] << 10) | (letters[1] << 5) | letters[2]
    return bytes([(value >> 8) & 0xFF, value & 0xFF])


def test_decode_edid_manufacturer():
    assert monitors._decode_edid_manufacturer(_encode_mfg("DEL")) == "DEL"
    # Tercera letra inválida (0): solo devuelve las válidas.
    value = (1 << 10) | (2 << 5)
    assert monitors._decode_edid_manufacturer(
        bytes([value >> 8, value & 0xFF])) == "AB"


def test_windows_edid_map_empty_off_windows():
    assert monitors._windows_edid_map() == {}


def test_monitor_id_prefers_edid_on_windows(monkeypatch):
    monkeypatch.setattr(monitors, "IS_WINDOWS", True)
    monitor = {"name": "DISPLAY1", "manufacturer": "GSM",
               "model": "1234", "serial": "99"}
    assert monitors.monitor_id(monitor) == "GSM|1234|99"


def test_monitor_id_uses_name_off_windows():
    monitor = {"name": "HDMI-A-1", "manufacturer": "", "model": "X", "serial": ""}
    assert monitors.monitor_id(monitor) == "HDMI-A-1|X|"
