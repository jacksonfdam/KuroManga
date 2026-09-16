"""MangaFire signs every `/api/` request with a `vrf` parameter.

A port of `VrfSigner.kt` from the site's own Tachiyomi extension
(`src/all/mangafire` in yuzono/tachiyomi-extensions, read 2026-09-16) rather
than anything reverse engineered from traffic. Three substitution passes over
the request path, each with its own 256-byte table, key and initialisation
value, then URL-safe base64 with the padding stripped.

Its own module with its own tests for one reason. The site has every incentive
to rotate these tables, and when it does every request fails at once with
nothing in the failure naming the cause - which is the risk this port was
called out for in the first place. A signer that is separate and covered is one
whose tests go red the moment the constants stop matching the extension they
came from.

The constants below were extracted from that file programmatically, not
transcribed. They are 256-byte tables in base64, and a single wrong character
is invisible to review while producing a signature the site rejects.
"""

import base64

_STAGES_B64: list[tuple[str, str, int]] = [
    (
        (
            "yINlmUNho8VYJT+ibTIP+9ESiULpVEtMOoD6U6lRE0R/xwXo/Xp9NrUgC4cw/Lmo33vUyjUE40kUoEWI"
            "r/fxfNNcq2s79ShQ5NhNrFnJ4hXPwOu/SuXzIbuTQKGFvfm08E9jvCfqAtoDqvQq3dVWPQFmJjgvkISB"
            "eXY3BgANR+yVnjGbcxZ47d6kLNfZPIayTq3/YGySb1KuVZodWp/WGNAO5pfMcpaK53Hhs0allBszaMax"
            "uouOwdxbwgxIw6YunSsXjI05Yi0j9j4eHKfSXR8Ifo/Od+8iamRfCXTyvm7NGRGYdcQ0ywcK/u6RXhrb"
            "cCm4t2eCtrDgQVecJGkQ+A=="
        ),
        "0Ec58JOY3uBzJK9m3zqIOpdlF7UFiax9DmA=",
        0x5A,
    ),
    (
        (
            "IUFltCxD3Oc2cwCgkJffthaOg9cgPUb0LgW6H/VtfcF0kc5F25t+aWj6JH9VOhOaY0rAFdUxlDnl5BLN"
            "vwEJvQtP5qcw7vdb/K+chnbwnspSHT8mz5lqwz41TezG0hkO06FTjJZhsyNuFLDpD2ZZxQj/QIRcF90z"
            "pmQ7Byu483WsQqUE0C342HL+JXngRB6fRzxRyVTaKu83h7UYTJ0QMt6ixFh6S3F8gqkKwrGTL3jHNBsD"
            "45UnifK8+RGtishQV2K3rujLKEkiZxpr2dYcudFW4oFsDKhad3CLBvuyTqsCo4B7mL5IKQ1vXo/MOOvq"
            "1I1d8ar9X6Ttu5KF4fZgiA=="
        ),
        "AAdjb1iPY8CiDmq9H34tKTBF8a3oDQ==",
        0x35,
    ),
    (
        (
            "NQHlu1/wVO5EmkwQymF810qqY2xG1k2obcas4Z9mCsPEIFl9pRIjFxbJ7ybMHbBckT5Ton85E0FOeHez"
            "bh/mjlEYpmpnlXOS8dgrqeq2KfxImTh1YK9y0PeMNhzA1OQzSY9brYOJq/l2QnE/hwOeZIhPixVSKIUl"
            "Db5vLcH6RWKxkIEMuP0bDwIqQ71AJJaEaMJL7A6YtyIwoRT+L5v4aZzodN/0+3nOGsfblFjgxSfPzVDj"
            "NFeNl5P26+kEC/8AHgdrpAbt3hHz3HrRN1Y6e+JHgF7ncFWnoF0y3THL1S71WgWGCa6KtSzTCCG58n68"
            "nTyj2T3Sshk7utqCtMi/ZQ=="
        ),
        "DELOJgPsVaCcblDtTGMdHzM=",
        0xBA,
    ),
]

_STAGES: list[tuple[bytes, bytes, int]] = [
    (base64.b64decode(table), base64.b64decode(key), iv) for table, key, iv in _STAGES_B64
]


def sign(path: str) -> str:
    """The `vrf` value for a request path.

    `path` is the path with the leading `/api` removed followed by the query
    string, parameters sorted by name - not the URL as it will be sent. A key
    ending `[]` carries its index instead (`genres[0]`, `genres[1]`), which is
    what the site's own client signs over.
    """
    data = path.encode()
    for table, key, iv in _STAGES:
        out = bytearray(len(data))
        previous = iv
        for index, byte in enumerate(data):
            previous = table[(byte ^ key[index % len(key)] ^ previous) & 0xFF]
            out[index] = previous
        data = bytes(out)
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def canonical(path: str, params: list[tuple[str, str]]) -> str:
    """What the signature is computed over, which is not the URL as sent.

    Ported from `VrfSigner.interceptor()`. Three rules, each one a way to get
    this wrong silently — the signature is rejected and the site simply answers
    as though the request were unauthorised:

    - The leading `/api` is dropped, so `/api/titles` signs as `/titles`.
    - Parameters are sorted by name. The sort is by name only and stable, so two
      values under one name keep the order they were given.
    - A name ending `[]` is written with its index instead: the first
      `genres[]` becomes `genres[0]`, the second `genres[1]`. The counter
      restarts for each distinct name.
    """
    ordered = sorted(params, key=lambda pair: pair[0])

    rendered: list[str] = []
    last_name = ""
    index = 0
    for name, value in ordered:
        if name.endswith("[]"):
            if name != last_name:
                index = 0
                last_name = name
            rendered.append(f"{name[:-2]}[{index}]={value}")
            index += 1
        else:
            rendered.append(f"{name}={value}")

    stem = path.removeprefix("/api")
    return f"{stem}?{'&'.join(rendered)}" if rendered else stem
