"""
scenario_tools — qakit 시나리오 언어(.qa.yml) 처리.

- parse_yaml: 시나리오에 필요한 YAML 부분 집합 파서 (블록 맵·리스트, {} [] 인라인, 따옴표, 주석)
- load_scenario: 파일 읽기 + `use:` 공통 단계(steps/*.qa.yml) 펼치기 → 실행기(Swift)가 읽을 JSON 구조
- collect_ids / check_ids: 시나리오에 적힌 ID가 앱에 있는지 실행 전에 확인 (Swift 방식의 컴파일 에러 역할)

Python 3.9 표준 라이브러리만 사용.
"""

import json
import re
from pathlib import Path


# ─────────────────────────── YAML 부분 집합 파서 ───────────────────────────

class YamlError(ValueError):
    pass


def _strip_comment(line):
    out, quote = [], None
    for i, c in enumerate(line):
        if quote:
            out.append(c)
            if c == quote and not (quote == '"' and i > 0 and line[i - 1] == "\\"):
                quote = None
        elif c in "\"'":
            quote = c
            out.append(c)
        elif c == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        else:
            out.append(c)
    return "".join(out).rstrip()


def _scalar(text):
    t = text.strip()
    if t == "":
        return ""
    if t[0] in "\"'":
        return _parse_flow(t)
    if t in ("true", "yes"):
        return True
    if t in ("false", "no"):
        return False
    if t in ("null", "~"):
        return None
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    if re.fullmatch(r"-?\d+\.\d+", t):
        return float(t)
    return t


def _parse_flow(text):
    """{a: b, c: [x, y]} / [a, b] / "따옴표" 인라인 값."""
    pos = 0
    s = text.strip()

    def skip():
        nonlocal pos
        while pos < len(s) and s[pos] in " \t":
            pos += 1

    def quoted():
        nonlocal pos
        q = s[pos]
        pos += 1
        buf = []
        while pos < len(s):
            c = s[pos]
            if q == '"' and c == "\\" and pos + 1 < len(s):
                nxt = s[pos + 1]
                buf.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(nxt, "\\" + nxt))
                pos += 2
                continue
            if q == "'" and c == "'" and pos + 1 < len(s) and s[pos + 1] == "'":
                buf.append("'")
                pos += 2
                continue
            if c == q:
                pos += 1
                return "".join(buf)
            buf.append(c)
            pos += 1
        raise YamlError(f"따옴표가 닫히지 않음: {text}")

    def plain(stops):
        nonlocal pos
        start = pos
        while pos < len(s):
            if s[pos] in stops:
                break
            if s[pos] == ":" and ":" in stops and (pos + 1 == len(s) or s[pos + 1] in " ,}]"):
                break
            pos += 1
        return _scalar(s[start:pos])

    def value(stops):
        nonlocal pos
        skip()
        if pos >= len(s):
            return ""
        c = s[pos]
        if c == "{":
            pos += 1
            obj = {}
            while True:
                skip()
                if pos < len(s) and s[pos] == "}":
                    pos += 1
                    return obj
                key = quoted() if s[pos] in "\"'" else str(plain(":,}"))
                skip()
                if pos < len(s) and s[pos] == ":":
                    pos += 1
                    obj[key] = value(",}")
                else:
                    obj[key] = None
                skip()
                if pos < len(s) and s[pos] == ",":
                    pos += 1
                elif pos < len(s) and s[pos] == "}":
                    continue
                else:
                    raise YamlError(f"{{}} 형식 오류: {text}")
        if c == "[":
            pos += 1
            arr = []
            while True:
                skip()
                if pos < len(s) and s[pos] == "]":
                    pos += 1
                    return arr
                # [ key: value ] → 한 쌍짜리 맵 (YAML 규칙)
                start = pos
                if s[pos] not in "{[\"'":
                    key = plain(":,]")
                    if pos < len(s) and s[pos] == ":":
                        pos += 1
                        arr.append({str(key): value(",]")})
                        skip()
                        if pos < len(s) and s[pos] == ",":
                            pos += 1
                        continue
                    pos = start
                arr.append(value(",]"))
                skip()
                if pos < len(s) and s[pos] == ",":
                    pos += 1
                elif pos < len(s) and s[pos] == "]":
                    continue
                else:
                    raise YamlError(f"[] 형식 오류: {text}")
        if c in "\"'":
            return quoted()
        return plain(stops)

    result = value("")
    skip()
    if pos != len(s):
        raise YamlError(f"해석하지 못한 부분: {s[pos:]!r} (원문: {text})")
    return result


_KEY = re.compile(r"""^(?:"([^"]+)"|'([^']+)'|([^\s:{}\[\],#][^:]*?))\s*:(?:\s+(.*)|$)""")


def parse_yaml(text):
    lines = []
    for no, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise YamlError(f"{no}번째 줄: 들여쓰기에 탭을 쓰지 마세요")
        line = _strip_comment(raw)
        if line.strip():
            lines.append([len(line) - len(line.lstrip(" ")), line.strip(), no])
    if not lines:
        return {}
    value, i = _block(lines, 0, lines[0][0])
    if i != len(lines):
        raise YamlError(f"{lines[i][2]}번째 줄: 들여쓰기가 맞지 않음")
    return value


def _block(lines, i, indent):
    if lines[i][1].startswith("- ") or lines[i][1] == "-":
        return _seq(lines, i, indent)
    return _map(lines, i, indent)


def _seq(lines, i, indent):
    out = []
    while i < len(lines) and lines[i][0] == indent and (lines[i][1].startswith("- ") or lines[i][1] == "-"):
        content = lines[i][1][1:].strip()
        if content == "":
            i += 1
            if i < len(lines) and lines[i][0] > indent:
                v, i = _block(lines, i, lines[i][0])
            else:
                v = None
            out.append(v)
        elif _KEY.match(content) and content[0] not in "{[\"'":
            # "- key: value" → 이 위치에서 시작하는 맵
            sub_indent = indent + (len(lines[i][1]) - len(content))
            lines[i] = [sub_indent, content, lines[i][2]]
            v, i = _map(lines, i, sub_indent)
            out.append(v)
        else:
            out.append(_parse_flow(content) if content[0] in "{[\"'" else _scalar(content))
            i += 1
    return out, i


def _map(lines, i, indent):
    out = {}
    while i < len(lines) and lines[i][0] == indent and not lines[i][1].startswith("- "):
        m = _KEY.match(lines[i][1])
        if not m:
            raise YamlError(f"{lines[i][2]}번째 줄을 읽을 수 없음: {lines[i][1]}")
        key = (m.group(1) or m.group(2) or m.group(3)).strip()
        rest = (m.group(4) or "").strip()
        i += 1
        if rest == "":
            if i < len(lines) and (lines[i][0] > indent or
                                   (lines[i][0] == indent and lines[i][1].startswith("- "))):
                v, i = _block(lines, i, lines[i][0])
            else:
                v = None
        elif rest[0] in "{[\"'":
            v = _parse_flow(rest)
        else:
            v = _scalar(rest)
        out[key] = v
    return out, i


# ─────────────────────────── 시나리오 불러오기 ───────────────────────────

def find_scenario(qa_root, name):
    p = Path(name).expanduser()
    if p.exists():
        return p.resolve()
    for cand in (qa_root / "scenarios" / name, qa_root / "scenarios" / f"{name}.qa.yml"):
        if cand.exists():
            return cand.resolve()
    return None


def load_scenario(path, qa_root):
    """시나리오 파일 → 실행 구조. `use: <이름>`은 steps/<이름>.qa.yml 내용을 group으로 펼친다."""
    data = parse_yaml(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "steps" not in data:
        raise YamlError(f"{path}: 맨 위에 steps: 가 있어야 합니다")
    data.setdefault("name", Path(path).stem.replace(".qa", ""))
    data["steps"] = _expand(data["steps"], qa_root, [Path(path).name])
    if data.get("interrupts") is not None:
        data["interrupts"] = _expand(data["interrupts"], qa_root, [Path(path).name])
    return data


def _expand(steps, qa_root, stack):
    if not isinstance(steps, list):
        raise YamlError(f"steps는 목록이어야 합니다: {steps!r}")
    out = []
    for step in steps:
        if isinstance(step, dict) and "use" in step:
            name = step["use"]
            f = qa_root / "steps" / f"{name}.qa.yml"
            if not f.exists():
                raise YamlError(f"공통 단계 '{name}'이(가) 없습니다: {f}")
            if name in stack:
                raise YamlError(f"공통 단계가 자기 자신을 부릅니다: {' → '.join(stack + [name])}")
            sub = parse_yaml(f.read_text(encoding="utf-8"))
            group = {"group": name, "steps": _expand(sub.get("steps", []), qa_root, stack + [name])}
            vars_ = dict(sub.get("vars") or {})
            vars_.update(step.get("with") or {})
            if vars_:
                group["vars"] = vars_
            out.append(group)
            continue
        if isinstance(step, dict):
            step = dict(step)
            for k in ("then", "else", "steps"):
                if k in step and isinstance(step[k], list):
                    step[k] = _expand(step[k], qa_root, stack)
            if isinstance(step.get("repeat"), dict) and isinstance(step["repeat"].get("steps"), list):
                step["repeat"] = dict(step["repeat"], steps=_expand(step["repeat"]["steps"], qa_root, stack))
        out.append(step)
    return out


# ─────────────────────────── ID 정적 검사 ───────────────────────────

_ID_KEYS = {"id", "cell", "segment", "tap", "wait", "on", "of", "from", "in", "target",
            "exists", "missing", "visible", "selected", "hittable"}
_LOOKS_ID = re.compile(r"^[A-Z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$|^[A-Z][A-Za-z0-9_]*(Cell|View)$")
RULE_ID = re.compile(r"^Tab\.|\.(cell|header|footer|textField)$|\.(nav\.(left|right)|toolbar)\.\d+$")


def collect_ids(node, out=None, key=None):
    out = set() if out is None else out
    if isinstance(node, dict):
        for k, v in node.items():
            collect_ids(v, out, k)
    elif isinstance(node, list):
        for v in node:
            collect_ids(v, out, key)
    elif isinstance(node, str) and key in _ID_KEYS and _LOOKS_ID.match(node) and "{" not in node:
        out.add(node)
    return out


def check_ids(scenario, known_ids, extra_ok=()):
    """(알 수 없는 ID 목록). 위치 규칙 ID, 외부 SDK 접두어(extra_ok)는 통과."""
    unknown = []
    for i in sorted(collect_ids(scenario.get("steps", []) + (scenario.get("interrupts") or []))):
        if i in known_ids or RULE_ID.search(i) or any(i.startswith(p) for p in extra_ok):
            continue
        unknown.append(i)
    return unknown


def to_json(scenario):
    return json.dumps(scenario, ensure_ascii=False, indent=2)
