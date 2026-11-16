#!/usr/bin/env python3
"""macho-tools — 비공개 바이너리 조사 도우미 (docs/reverse-engineering.md).

  python3 scripts/macho-tools.py fields <바이너리>              Swift 필드 이름(__swift5_reflstr) — 구조체 속성·CodingKeys 후보
  python3 scripts/macho-tools.py symbols <바이너리> <정규식>     심볼을 풀어서(swift-demangle) 주소와 함께
  python3 scripts/macho-tools.py disasm <바이너리> <주소|정규식> [줄 수]
                                                             한 함수를 역어셈블 (Swift 심볼은 otool 라벨에 안 나와 주소로)
  python3 scripts/macho-tools.py calls <바이너리> <주소|정규식>  그 함수가 부르는 것만 (bl·b·blraa — 무엇을 부르는지 빠르게)

읽기만 한다. 필요한 것: Xcode 명령줄 도구(otool·nm·lldb·swift-demangle).
"""
import re
import subprocess
import sys


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace").stdout


def archs(path):
    out = run(["lipo", "-archs", path]).split()
    return "arm64e" if "arm64e" in out else (out[0] if out else "arm64")


def section(path, segname, sectname):
    """파일 안 구역 바이트 (otool -l로 위치를 찾아 그대로 읽는다 — otool -s는 4바이트씩 뒤집혀 나옴)."""
    out = run(["otool", "-arch", archs(path), "-l", path])
    m = re.search(r"sectname " + re.escape(sectname) + r"\n\s+segname " + re.escape(segname)
                  + r"\n\s+addr 0x[0-9a-f]+\n\s+size (0x[0-9a-f]+)\n\s+offset (\d+)", out)
    if not m:
        return b""
    size, off = int(m.group(1), 16), int(m.group(2))
    # 유니버설 바이너리면 오프셋이 그 아키텍처 조각 기준이라 lipo -thin 없이 맞지 않을 수 있다 → 단일 아키텍처 파일에 쓰기
    with open(path, "rb") as f:
        f.seek(off)
        return f.read(size)


def demangle(names):
    p = subprocess.run(["xcrun", "swift-demangle", "--simplified"], input="\n".join(names), capture_output=True, text=True)
    return p.stdout.splitlines()


def symbols(path, pattern):
    rows = []
    for line in run(["nm", "-arch", archs(path), path]).splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1] in "TtSsDd":
            rows.append((parts[0], parts[1], parts[2]))
    plain = demangle([r[2] for r in rows])
    return [(a, t, raw, d) for (a, t, raw), d in zip(rows, plain) if re.search(pattern, d) or re.search(pattern, raw)]


def resolve(path, target):
    if re.fullmatch(r"(0x)?[0-9a-fA-F]+", target):
        return int(target, 16)
    hits = [s for s in symbols(path, target) if s[1] in "Tt"]
    if not hits:
        sys.exit(f"함수를 찾지 못함: {target}")
    if len(hits) > 1:
        print("여러 개가 맞음 — 첫 번째를 씀:", file=sys.stderr)
        for a, _, _, d in hits[:8]:
            print(f"  0x{a.lstrip('0')}  {d}", file=sys.stderr)
    return int(hits[0][0], 16)


def disasm(path, addr, lines=400):
    out = run(["lldb", "--batch", "-o", f"target create --arch {archs(path)} {path}",
               "-o", f"disassemble -s {hex(addr)} -c {lines}"])
    body, started = [], False
    for l in out.splitlines():
        if re.search(r"\[0x[0-9a-f]+\] <\+", l):
            started = True
        elif started and not l.strip():
            break                         # 다음 함수 전에 빈 줄
        if started:
            body.append(l.strip())
            if re.search(r"\b(ret|retab)\b", l) and len(body) > 3 and not re.search(r"\bb\.", l):
                pass
    return body


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, path = sys.argv[1], sys.argv[2]
    if cmd == "fields":
        data = section(path, "__TEXT", "__swift5_reflstr")
        names = [s.decode(errors="replace") for s in data.split(b"\0") if s]
        print(f"{len(names)}개"); print(" ".join(names))
    elif cmd == "symbols":
        for a, t, _, d in symbols(path, sys.argv[3]):
            print(f"0x{a.lstrip('0') or '0'}  {t}  {d}")
    elif cmd in ("disasm", "calls"):
        addr = resolve(path, sys.argv[3])
        body = disasm(path, addr, int(sys.argv[4]) if len(sys.argv) > 4 else 400)
        for l in body:
            if cmd == "disasm" or re.search(r"\s(bl|b|blr|blraa|blraaz|braa|braaz|br)\s", l):
                print(l)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
